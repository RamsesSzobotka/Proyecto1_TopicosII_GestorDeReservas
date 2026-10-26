import json
import uuid
from datetime import datetime, timedelta, time
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.dateparse import parse_datetime
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from . import forecast
from .models import Resource, Booking, Availability, LIMITE_CANCELACION


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
        estado=Booking.Estado.ACTIVA,
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
        estado=Booking.Estado.ACTIVA,
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

    return render(request, 'reservas/calendario_full.html', {
        'resource': resource,
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
    # Las ocurrencias de una reserva recurrente comparten un identificador de serie.
    serie = uuid.uuid4() if repeat_weeks > 0 else None
    reservas_creadas = []
    try:
        with transaction.atomic():
            for i, (start, end) in enumerate(semanas):
                if Availability.objects.filter(resource=resource, start_time__lt=end, end_time__gt=start).exists():
                    return JsonResponse({
                        'success': False,
                        'error': f'Conflicto: hay un bloqueo en la semana {i + 1} ({start}).'
                    }, status=409)
                if Booking.objects.filter(resource=resource, estado=Booking.Estado.ACTIVA,
                                          start_time__lt=end, end_time__gt=start).exists():
                    return JsonResponse({
                        'success': False,
                        'error': f'Conflicto: hay una reserva en la semana {i + 1} ({start}).'
                    }, status=409)

            for start, end in semanas:
                Booking.objects.create(
                    user=request.user,
                    resource=resource,
                    start_time=start,
                    end_time=end,
                    serie=serie
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

def _rango_eventos(request):
    """
    Lee el rango opcional ?start=&end= que envía FullCalendar (ISO 8601 con offset).
    Devuelve (inicio, fin, error): si faltan ambos, (None, None, None); si alguno es
    inválido o no lleva zona horaria, error es una JsonResponse 400.
    """
    crudo_inicio = request.GET.get('start')
    crudo_fin = request.GET.get('end')
    if crudo_inicio is None and crudo_fin is None:
        return None, None, None

    valores = []
    for crudo in (crudo_inicio, crudo_fin):
        try:
            # Un '+' sin codificar en la query llega como espacio.
            valor = parse_datetime(crudo.strip().replace(' ', '+')) if crudo else None
        except ValueError:
            valor = None
        if valor is None or timezone.is_naive(valor):
            return None, None, JsonResponse(
                {'error': 'Los parámetros start y end deben ser fechas ISO 8601 con zona horaria.'},
                status=400,
            )
        valores.append(valor)
    if valores[0] >= valores[1]:
        return None, None, JsonResponse(
            {'error': 'El parámetro start debe ser anterior a end.'},
            status=400,
        )
    return valores[0], valores[1], None


def api_reservas(request, resource_id):
    """
    API que devuelve las reservas de un recurso en formato JSON.
    Acepta ?start=&end= para limitar a las que solapan [start, end).
    Privacidad: el titular y el staff ven el nombre; el resto solo "Ocupado".
    """
    if not Resource.objects.filter(id=resource_id).exists():
        return JsonResponse({'error': 'Recurso no encontrado.'}, status=404)
    inicio, fin, error = _rango_eventos(request)
    if error:
        return error
    reservas = Booking.objects.filter(
        resource_id=resource_id, estado=Booking.Estado.ACTIVA
    ).order_by('start_time')
    if inicio and fin:
        reservas = reservas.filter(start_time__lt=fin, end_time__gt=inicio)

    def datos(reserva):
        propia = request.user.is_authenticated and reserva.user_id == request.user.id
        if propia:
            titulo, color = "Tu reserva", "#2563eb"  # Azul
        elif request.user.is_staff:
            titulo, color = f"Reservado por {reserva.user.username}", "#10b981"
        else:
            titulo, color = "Ocupado", "#10b981"  # Verde
        return {
            "title": titulo,
            "start": reserva.start_time.isoformat(),
            "end": reserva.end_time.isoformat(),
            "color": color,
            "kind": "reserva",
            "propia": propia,
        }

    eventos = [datos(reserva) for reserva in reservas.select_related('user')]
    return JsonResponse(eventos, safe=False)


def api_bloqueos(request, resource_id):
    """
    API que devuelve los bloqueos administrativos de un recurso en formato JSON
    para el calendario del cliente. Al servirse por URL (y no embebido en el
    HTML), el calendario refleja los cambios de bloqueos al refrescar.
    """
    if not Resource.objects.filter(id=resource_id).exists():
        return JsonResponse({'error': 'Recurso no encontrado.'}, status=404)
    inicio, fin, error = _rango_eventos(request)
    if error:
        return error
    bloqueos = Availability.objects.filter(resource_id=resource_id).order_by('start_time')
    if inicio and fin:
        bloqueos = bloqueos.filter(start_time__lt=fin, end_time__gt=inicio)
    eventos = [
        {
            "title": "Bloqueado",
            "start": bloqueo.start_time.isoformat(),
            "end": bloqueo.end_time.isoformat(),
            "color": "#ef4444",  # Rojo: bloqueos
            "textColor": "#fff",
            "kind": "bloqueo",
        }
        for bloqueo in bloqueos
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


def _anotar_serie(reservas):
    """
    Añade a cada reserva ``serie_n`` y ``serie_m`` (ocurrencia N de M) cuando
    pertenece a una serie. N y M se calculan por orden de start_time dentro de
    la serie contando todas las ocurrencias, también las canceladas.
    """
    series = {r.serie for r in reservas if r.serie}
    posiciones = {}
    totales = {}
    if series:
        filas = Booking.objects.filter(serie__in=series).order_by('start_time', 'pk').values_list('pk', 'serie')
        for pk, serie in filas:
            totales[serie] = totales.get(serie, 0) + 1
            posiciones[pk] = totales[serie]
    for r in reservas:
        r.serie_n = posiciones.get(r.pk) if r.serie else None
        r.serie_m = totales.get(r.serie) if r.serie else None
    return reservas


@login_required(login_url='login')
@require_GET
def mis_reservas(request):
    """
    Reservas del usuario autenticado (ISSUE-06): próximas activas primero y
    luego el historial (pasadas y canceladas). Solo lista las del propio usuario.
    """
    ahora = timezone.now()
    todas = list(
        Booking.objects.filter(user=request.user).select_related('resource')
        .order_by('start_time', 'pk')
    )
    _anotar_serie(todas)
    for r in todas:
        r.cancelable, r.motivo_no_cancelable = r.puede_cancelar(request.user, ahora)
        r.en_curso = r.estado == Booking.Estado.ACTIVA and r.start_time <= ahora < r.end_time
    proximas = [r for r in todas if r.estado == Booking.Estado.ACTIVA and r.end_time > ahora]
    historial = [r for r in todas if r not in proximas]
    historial.sort(key=lambda r: r.start_time, reverse=True)
    return render(request, 'reservas/mis_reservas.html', {
        'proximas': proximas,
        'historial': historial,
        'limite_horas': int(LIMITE_CANCELACION.total_seconds() // 3600),
    })


@require_POST
@login_required(login_url='login')
def cancelar_reserva(request, pk):
    """
    Cancela una reserva (ISSUE-06). Solo POST (con CSRF) y con sesión.

    ``alcance``: ``una`` (por defecto) o ``serie`` (esta y las siguientes
    ocurrencias activas de la serie que cumplan el límite). El propietario o un
    administrador pueden cancelar; para cualquier otro usuario, una reserva
    ajena responde 404 igual que una inexistente, sin revelar que existe.
    """
    ahora = timezone.now()
    with transaction.atomic():
        candidatas = Booking.objects.select_for_update().select_related('resource')
        if not request.user.is_staff:
            candidatas = candidatas.filter(user=request.user)
        reserva = candidatas.filter(pk=pk).first()
        if reserva is None:
            raise Http404('Reserva no encontrada.')

        alcance = request.POST.get('alcance', 'una')
        if alcance not in ('una', 'serie'):
            messages.error(request, 'El alcance de la cancelación no es válido.')
            return redirect('mis_reservas')

        puede, motivo = reserva.puede_cancelar(request.user, ahora)
        if not puede:
            messages.error(request, f'No se pudo cancelar la reserva: {motivo}')
            return redirect('mis_reservas')

        reserva.cancelar(request.user, ahora)
        canceladas = 1
        omitidas = 0
        if alcance == 'serie' and reserva.serie:
            siguientes = Booking.objects.select_for_update().filter(
                serie=reserva.serie, user_id=reserva.user_id,
                estado=Booking.Estado.ACTIVA, start_time__gt=reserva.start_time,
            ).order_by('start_time')
            for otra in siguientes:
                if otra.puede_cancelar(request.user, ahora)[0]:
                    otra.cancelar(request.user, ahora)
                    canceladas += 1
                else:
                    omitidas += 1

    fecha = reserva.start_time.strftime('%d/%m/%Y %H:%M')
    if alcance == 'serie' and reserva.serie:
        texto = f'Se cancelaron {canceladas} reserva(s) de la serie de {reserva.resource.name}, desde el {fecha} UTC.'
        if omitidas:
            texto += f' {omitidas} no se cancelaron porque no cumplen el límite de cancelación.'
    else:
        texto = f'Se canceló la reserva de {reserva.resource.name} del {fecha} UTC.'
    messages.success(request, texto)
    return redirect('mis_reservas')
