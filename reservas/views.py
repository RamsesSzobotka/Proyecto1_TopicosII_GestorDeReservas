import json
from datetime import datetime, timedelta, time
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_GET
from . import forecast
from .models import Resource, Booking, Availability


# Horario por defecto (si no hay Availability definida)
DEFAULT_START = time(9, 0)   # 09:00
DEFAULT_END = time(21, 0)    # 21:00


def calendario(request, resource_id):
    """
    Muestra un calendario semanal de reservas para un recurso.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = timezone.now()
    inicio_semana = hoy - timedelta(days=hoy.weekday())  # Lunes
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.filter(
        resource=resource,
        start_time__date__gte=inicio_semana,
        start_time__date__lte=inicio_semana + timedelta(days=6)
    ).order_by('start_time')

    reservas_por_dia = {date_format(dia, 'Y-m-d'): [] for dia in dias_semana}
    for reserva in reservas:
        clave = date_format(reserva.start_time, 'Y-m-d')
        reservas_por_dia[clave].append(reserva)

    return render(request, 'reservas/calendario.html', {
        'resource': resource,
        'dias_semana': dias_semana,
        'reservas_por_dia': reservas_por_dia,
    })


def calendario_navegable(request, resource_id):
    """
    Calendario semanal con botones de semana anterior/siguiente.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    hoy = timezone.now()
    delta = 0
    if request.GET.get('week') == 'prev':
        delta = -7
    elif request.GET.get('week') == 'next':
        delta = 7

    inicio_semana = (hoy - timedelta(days=hoy.weekday())) + timedelta(days=delta)
    dias_semana = [inicio_semana + timedelta(days=i) for i in range(7)]

    reservas = Booking.objects.filter(
        resource=resource,
        start_time__date__gte=inicio_semana,
        start_time__date__lte=inicio_semana + timedelta(days=6)
    ).order_by('start_time')

    reservas_por_dia = {date_format(dia, 'Y-m-d'): [] for dia in dias_semana}
    for reserva in reservas:
        clave = date_format(reserva.start_time, 'Y-m-d')
        reservas_por_dia[clave].append(reserva)

    return render(request, 'reservas/calendario.html', {
        'resource': resource,
        'dias_semana': dias_semana,
        'reservas_por_dia': reservas_por_dia,
    })


@ensure_csrf_cookie
def calendario_full(request, resource_id):
    """
    Calendario interactivo con FullCalendar.
    """
    resource = get_object_or_404(Resource, id=resource_id)

    reservas = Booking.objects.filter(resource=resource).order_by('start_time')
    bloqueos = Availability.objects.filter(resource=resource)

    # Lista de reservas
    reservas_json = [
        {
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "title": f"Reservado por {reserva.user.username}",
            "color": "#10b981",  # Verde reservas
        }
        for reserva in reservas
    ]

    # Lista de bloqueos (rojo)
    bloqueos_json = [
        {
            "start": bloqueo.start_time.isoformat(),
            "end": bloqueo.end_time.isoformat(),
        }
        for bloqueo in bloqueos
    ]

    return render(request, 'reservas/calendario_full.html', {
        'resource': resource,
        'reservas_json': json.dumps(reservas_json),
        'bloqueos_json': json.dumps(bloqueos_json),
        'is_authenticated': request.user.is_authenticated,
    })



def api_crear_reserva(request):
    """
    Endpoint para crear una nueva reserva, con soporte para repeticiones semanales.

    Protegido por CSRF: el cliente debe enviar el header X-CSRFToken con el valor
    de la cookie csrftoken (la emite la vista calendario_full vía ensure_csrf_cookie).

    Respuesta exitosa (200): {"success": True, "reservas": [{"start": ISO8601, "end": ISO8601}, ...]}
    con una entrada por ocurrencia creada (repeat_weeks + 1 en total).

    Errores: 400 (JSON/datetime/intervalo/petición inválidos), 403 (sin sesión o CSRF),
    404 (recurso inexistente), 405 (método), 409 (solape con reserva o bloqueo).
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Debes iniciar sesión para reservar.'}, status=403)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'El cuerpo de la petición no es JSON válido.'}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'error': 'El cuerpo JSON debe ser un objeto.'}, status=400)

    resource_id = data.get('resource_id')
    if not resource_id:
        return JsonResponse({'success': False, 'error': 'Falta el parámetro resource_id.'}, status=400)
    try:
        resource = Resource.objects.get(pk=resource_id)
    except (Resource.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'El recurso indicado no existe.'}, status=404)

    start_time = parse_datetime(str(data.get('start_time') or ''))
    end_time = parse_datetime(str(data.get('end_time') or ''))
    if start_time is None or end_time is None:
        return JsonResponse({
            'success': False,
            'error': 'start_time y end_time deben ser fechas ISO 8601 válidas.'
        }, status=400)
    # Con USE_TZ=True rechazamos datetimes sin offset: compararlos con los
    # almacenados (aware) lanza TypeError y Django los interpretaría como UTC.
    if start_time.tzinfo is None or end_time.tzinfo is None:
        return JsonResponse({
            'success': False,
            'error': 'start_time y end_time deben incluir la zona horaria (offset), p. ej. 2026-10-20T10:00:00-05:00.'
        }, status=400)
    if start_time >= end_time:
        return JsonResponse({
            'success': False,
            'error': 'start_time debe ser anterior a end_time.'
        }, status=400)

    try:
        repeat_weeks = int(data.get('repeat_weeks', 0))
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'repeat_weeks debe ser un número entero.'}, status=400)
    if not 0 <= repeat_weeks <= 52:
        return JsonResponse({'success': False, 'error': 'repeat_weeks debe estar entre 0 y 52.'}, status=400)

    semanas = [
        (start_time + timedelta(weeks=i), end_time + timedelta(weeks=i))
        for i in range(repeat_weeks + 1)
    ]

    # Todo-o-nada: chequeos de conflicto y creación dentro de la misma
    # transacción. IntegrityError (carrera concurrente sobre unique_together)
    # se traduce a 409 y revierte la serie completa.
    reservas_creadas = []
    try:
        with transaction.atomic():
            for i, (start, end) in enumerate(semanas):
                if Availability.objects.filter(resource=resource, start_time__lt=end, end_time__gt=start).exists():
                    return JsonResponse({
                        'success': False,
                        'error': f'Conflicto: hay un bloqueo en la semana {i + 1} ({start}).'
                    }, status=409)
                if Booking.objects.filter(resource=resource, start_time__lt=end, end_time__gt=start).exists():
                    return JsonResponse({
                        'success': False,
                        'error': f'Conflicto: hay una reserva en la semana {i + 1} ({start}).'
                    }, status=409)

            for start, end in semanas:
                Booking.objects.create(
                    user=request.user,
                    resource=resource,
                    start_time=start,
                    end_time=end
                )
                reservas_creadas.append({
                    'start': start.isoformat(),
                    'end': end.isoformat()
                })
    except IntegrityError:
        return JsonResponse({'success': False, 'error': 'Conflicto: la reserva ya existe.'}, status=409)
    except (ValueError, ValidationError) as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': True, 'reservas': reservas_creadas})


def login_view(request):
    """
    Vista para el inicio de sesión de usuarios.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('/')
        else:
            messages.error(request, "Usuario o contraseña incorrectos.")
    return render(request, 'reservas/login.html')


def logout_view(request):
    """
    Cerrar sesión.
    """
    logout(request)
    return redirect('/login/')

def api_reservas(request, resource_id):
    """
    API que devuelve todas las reservas de un recurso en formato JSON.
    """
    reservas = Booking.objects.filter(resource_id=resource_id).order_by('start_time')
    eventos = [
        {
            "title": f"Reservado por {reserva.user.username}",
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "color": "#10b981",  # Verde
        }
        for reserva in reservas
    ]
    return JsonResponse(eventos, safe=False)

def home(request):
    """
    Vista principal que muestra todas las pistas (resources).
    """
    resources = Resource.objects.all()  # Obtenemos todas las pistas
    return render(request, 'reservas/home.html', {'resources': resources})


def _parsear_fecha(texto):
    """Convierte 'YYYY-MM-DD' en date; devuelve None si el formato no es válido."""
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except ValueError:
        return None


@staff_member_required
@require_GET
def prevision_demanda(request):
    """
    Previsión de la demanda de un recurso (solo administradores, solo lectura).

    Parámetros GET: recurso (id), desde y hasta (YYYY-MM-DD, rango [desde, hasta)).
    Muestra el histórico de reservas por semana y una estimación (media móvil)
    de las semanas siguientes. No escribe en la base de datos ni modifica
    precios o inventario. Errores de entrada: página con mensaje y status 400.
    """
    recursos = Resource.objects.order_by('name')
    contexto = {
        'recursos': recursos,
        'recurso': None,
        'error': None,
        'datos': None,
        'resultado': None,
        'ventana': forecast.VENTANA_SEMANAS,
        'horizonte': forecast.HORIZONTE_SEMANAS,
    }
    por_defecto_desde, por_defecto_hasta = forecast.rango_por_defecto(timezone.now().date())
    desde_txt = request.GET.get('desde', '').strip()
    hasta_txt = request.GET.get('hasta', '').strip()
    contexto['desde'] = desde_txt or por_defecto_desde.isoformat()
    contexto['hasta'] = hasta_txt or por_defecto_hasta.isoformat()
    recurso_txt = request.GET.get('recurso', '').strip()
    contexto['recurso_id'] = recurso_txt

    def con_error(mensaje):
        contexto['error'] = mensaje
        return render(request, 'reservas/prevision.html', contexto, status=400)

    if not recurso_txt:
        return render(request, 'reservas/prevision.html', contexto)

    # isdecimal y no isdigit: isdigit acepta '²', que int() no puede convertir.
    if not recurso_txt.isdecimal() or not Resource.objects.filter(pk=int(recurso_txt)).exists():
        return con_error('El recurso indicado no existe.')
    recurso = Resource.objects.get(pk=int(recurso_txt))
    contexto['recurso'] = recurso

    desde = _parsear_fecha(contexto['desde'])
    hasta = _parsear_fecha(contexto['hasta'])
    if desde is None or hasta is None:
        return con_error('Las fechas deben tener el formato AAAA-MM-DD y ser válidas.')
    if desde >= hasta:
        return con_error('La fecha "desde" debe ser anterior a la fecha "hasta".')
    if (hasta - desde) > timedelta(weeks=forecast.MAXIMO_SEMANAS_RANGO):
        return con_error(f'El rango no puede superar {forecast.MAXIMO_SEMANAS_RANGO} semanas.')

    semanas = forecast.agregar_semanas(recurso, desde, hasta)
    resultado = forecast.pronosticar(semanas)
    contexto['resultado'] = resultado
    contexto['semanas'] = semanas
    contexto['datos'] = {
        'recurso': recurso.name,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'suficiente': resultado['suficiente'],
        'historico': [
            {'inicio': s['inicio'].isoformat(), 'reservas': s['reservas'],
             'horas': s['horas'], 'completa': s['completa']}
            for s in semanas
        ],
        'prevision': [
            {'inicio': p['inicio'].isoformat(), 'reservas': p['reservas'], 'horas': p['horas']}
            for p in resultado['prevision']
        ],
    }
    return render(request, 'reservas/prevision.html', contexto)
