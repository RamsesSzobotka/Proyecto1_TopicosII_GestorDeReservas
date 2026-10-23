"""
Previsión de la demanda (issue #5).

Módulo de lógica pura: no lee el request ni llama a ``now()``. Las fechas
entran como parámetros, de modo que el mismo historial siempre produce el
mismo resultado. Solo lee reservas (``Booking``); nunca escribe en la base de
datos ni toca precios o inventario.

La previsión es una ESTIMACIÓN basada en el histórico, no una decisión
automática.

Nota sobre cancelaciones: el modelo ``Booking`` todavía no tiene estado de
cancelación (issue #6). Cuando exista, ``agregar_semanas`` deberá excluir las
reservas canceladas.
"""
from datetime import datetime, time, timedelta, timezone as dt_timezone

from .models import Booking

# Semanas del historial que se promedian para proyectar. Se eligen 4 (un mes)
# porque suavizan variaciones de una sola semana sin diluir cambios recientes.
VENTANA_SEMANAS = 4

# Semanas hacia adelante que se proyectan. Es igual a la ventana: no se
# proyecta más lejos de lo que el historial usado puede sostener.
HORIZONTE_SEMANAS = 4

# Mínimo de semanas completas en el rango para poder pronosticar. Es igual a
# la ventana: con menos semanas la media móvil no tendría sobre qué calcularse.
MINIMO_SEMANAS_COMPLETAS = VENTANA_SEMANAS

# Rango por defecto: las 12 semanas anteriores a la semana actual (la semana
# en curso se excluye porque está incompleta y sesgaría el promedio a la baja).
SEMANAS_RANGO_POR_DEFECTO = 12

# Tope del rango que se puede consultar, para acotar el costo de la consulta.
MAXIMO_SEMANAS_RANGO = 52


def inicio_de_semana(dia):
    """Lunes (``date``) de la semana ISO a la que pertenece ``dia`` (``date``)."""
    return dia - timedelta(days=dia.weekday())


def rango_por_defecto(hoy):
    """
    Devuelve ``(desde, hasta)`` como fechas: ``hasta`` es el lunes de la semana
    de ``hoy`` (excluido) y ``desde`` queda 12 semanas antes.
    """
    hasta = inicio_de_semana(hoy)
    return hasta - timedelta(weeks=SEMANAS_RANGO_POR_DEFECTO), hasta


def _a_datetime_utc(dia):
    return datetime.combine(dia, time.min, tzinfo=dt_timezone.utc)


def agregar_semanas(recurso, desde, hasta):
    """
    Agrupa las reservas de ``recurso`` por semana ISO (lunes 00:00 UTC) según
    ``start_time``, dentro de ``[desde, hasta)`` (fechas, 00:00 UTC).

    Devuelve una lista continua de semanas (incluye semanas con cero), cada una:
    ``{'inicio': date, 'reservas': int, 'horas': float, 'completa': bool}``.
    ``completa`` indica que la semana entera cae dentro del rango.
    """
    if desde >= hasta:
        raise ValueError("'desde' debe ser anterior a 'hasta'.")

    ini = _a_datetime_utc(desde)
    fin = _a_datetime_utc(hasta)
    filas = Booking.objects.filter(
        resource=recurso, start_time__gte=ini, start_time__lt=fin
    ).values_list('start_time', 'end_time')

    primera = inicio_de_semana(desde)
    ultima = inicio_de_semana(hasta - timedelta(days=1))
    semanas = {}
    lunes = primera
    while lunes <= ultima:
        completa = lunes >= desde and lunes + timedelta(days=7) <= hasta
        semanas[lunes] = {
            'inicio': lunes, 'reservas': 0, 'segundos': 0.0, 'completa': completa,
        }
        lunes += timedelta(days=7)

    for inicio, final in filas:
        clave = inicio_de_semana(inicio.astimezone(dt_timezone.utc).date())
        semanas[clave]['reservas'] += 1
        semanas[clave]['segundos'] += (final - inicio).total_seconds()

    return [
        {
            'inicio': s['inicio'],
            'reservas': s['reservas'],
            'horas': round(s['segundos'] / 3600, 2),
            'completa': s['completa'],
        }
        for s in semanas.values()
    ]


def pronosticar(semanas, ventana=VENTANA_SEMANAS, horizonte=HORIZONTE_SEMANAS,
                minimo=MINIMO_SEMANAS_COMPLETAS):
    """
    Media móvil simple de las últimas ``ventana`` semanas completas, proyectada
    como valor plano a ``horizonte`` semanas.

    Devuelve un dict con ``suficiente`` (bool), ``motivo`` (texto o ``None``) y
    ``prevision`` (lista de ``{'inicio', 'reservas', 'horas'}``; vacía si no hay
    historial suficiente).
    """
    completas = [s for s in semanas if s['completa']]
    total = sum(s['reservas'] for s in semanas)
    if total == 0:
        return {
            'suficiente': False,
            'motivo': 'No hay reservas registradas para este recurso en el periodo seleccionado.',
            'prevision': [],
        }
    if len(completas) < max(minimo, ventana):
        return {
            'suficiente': False,
            'motivo': (
                f'El historial es insuficiente: hay {len(completas)} semana(s) completa(s) '
                f'y se necesitan al menos {max(minimo, ventana)} para estimar.'
            ),
            'prevision': [],
        }

    ultimas = completas[-ventana:]
    media_reservas = round(sum(s['reservas'] for s in ultimas) / ventana, 2)
    media_horas = round(sum(s['horas'] for s in ultimas) / ventana, 2)
    primer_lunes = semanas[-1]['inicio'] + timedelta(days=7)
    prevision = [
        {
            'inicio': primer_lunes + timedelta(weeks=i),
            'reservas': media_reservas,
            'horas': media_horas,
        }
        for i in range(horizonte)
    ]
    return {'suficiente': True, 'motivo': None, 'prevision': prevision}
