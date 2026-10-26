from datetime import timedelta
import re

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

# Antelación mínima para que un cliente cancele su propia reserva (ISSUE-06).
# Un administrador (is_staff) no está sujeto a este margen, pero tampoco puede
# cancelar una reserva que ya empezó.
LIMITE_CANCELACION = timedelta(hours=2)

# Teléfono: + inicial opcional, dígitos, espacios o guiones; 7 a 20 caracteres en total.
# [0-9] y \Z en vez de \d y $: \d acepta dígitos Unicode ('１２３４') y $ un '\n' final.
TELEFONO_REGEX = r'^(?=.{7,20}\Z)\+?[0-9][0-9 \-]*[0-9]\Z'
ULTIMOS4_REGEX = r'^[0-9]{4}\Z'


class Resource(models.Model):
    """Recurso que puede reservarse (pistas, salas, etc.)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Availability(models.Model):
    """Horarios disponibles para cada recurso."""
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='availabilities')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    def __str__(self):
        return f"{self.resource.name} - {self.start_time} a {self.end_time}"

    def clean(self):
        """
        Valida el intervalo del bloqueo y cuenta las reservas que se solapan.

        Política acordada (ISSUE-07): la reserva existente gana. Si el bloqueo se
        solapa con reservas ya creadas, NO se rechaza: las reservas se mantienen
        intactas y el bloqueo solo impide reservas nuevas. Por eso el conteo
        de solapadas es un aviso, no un error.
        """
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({
                'end_time': 'El fin del bloqueo debe ser posterior al inicio.'
            })

        self.reservas_solapadas = 0
        if self.resource_id and self.start_time and self.end_time:
            self.reservas_solapadas = Booking.objects.filter(
                estado=Booking.Estado.ACTIVA,  # las canceladas ya no ocupan la franja (ISSUE-06)
                resource_id=self.resource_id,
                start_time__lt=self.end_time,
                end_time__gt=self.start_time
            ).count()

    class Meta:
        verbose_name = 'Bloqueo'
        verbose_name_plural = 'Bloqueos'


class Booking(models.Model):
    """Reserva de un recurso por un usuario."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name='bookings')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Estado(models.TextChoices):
        ACTIVA = 'activa', 'Activa'
        CANCELADA = 'cancelada', 'Cancelada'

    # Cancelación lógica (ISSUE-06): la fila se conserva para el historial,
    # pero una reserva cancelada deja de ocupar la franja.
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ACTIVA)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reservas_canceladas'
    )
    # Identificador común de las ocurrencias de una reserva recurrente.
    # Las reservas simples tienen serie nula.
    serie = models.UUIDField(null=True, blank=True, db_index=True)

    def __str__(self):
        return f"Reserva de {self.resource.name} por {self.user.username}"

    def clean(self):
        """
        Validación para evitar que haya reservas solapadas con la misma franja horaria.
        """
        if self.estado == self.Estado.CANCELADA:
            return  # una reserva cancelada no ocupa la franja

        overlapping = Booking.objects.filter(
            estado=Booking.Estado.ACTIVA,
            resource=self.resource,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)  # Excluimos la propia reserva al editar

        if overlapping.exists():
            raise ValidationError("Ya existe una reserva en esta franja horaria.")

        # Un bloqueo administrativo impide reservar en esa franja (ISSUE-07).
        bloqueado = Availability.objects.filter(
            resource_id=self.resource_id,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        )
        if bloqueado.exists():
            raise ValidationError("El intervalo está bloqueado por el administrador.")

    def puede_cancelar(self, usuario, ahora=None):
        """
        Devuelve ``(bool, motivo)``. Reglas (ISSUE-06): no se cancela lo ya
        cancelado ni lo que ya empezó; el cliente debe hacerlo con al menos
        ``LIMITE_CANCELACION`` de antelación; el staff puede hasta el inicio.
        La pertenencia (propietario o staff) la valida la vista.
        """
        ahora = ahora or timezone.now()
        if self.estado == self.Estado.CANCELADA:
            return False, 'Esta reserva ya está cancelada.'
        if self.start_time <= ahora:
            return False, 'La reserva ya comenzó o ya pasó; no se puede cancelar.'
        if not usuario.is_staff and self.start_time - ahora < LIMITE_CANCELACION:
            return False, 'Solo puedes cancelar hasta 2 horas antes del inicio de la reserva.'
        return True, ''

    def cancelar(self, por, ahora=None):
        """Marca la reserva como cancelada (no la borra)."""
        self.estado = self.Estado.CANCELADA
        self.cancelada_en = ahora or timezone.now()
        self.cancelada_por = por
        self.save(update_fields=['estado', 'cancelada_en', 'cancelada_por'])

    class Meta:
        constraints = [
            # Solo las reservas activas ocupan la franja: un horario cancelado
            # se puede volver a reservar.
            models.UniqueConstraint(
                fields=['resource', 'start_time', 'end_time'],
                condition=Q(estado='activa'),
                name='unique_reserva_activa_por_franja',
            ),
        ]


class PerfilReserva(models.Model):
    """
    Datos de contacto y referencia de pago SIMULADA de un usuario (ISSUE-03).

    Seguridad: nunca se guarda el número completo de tarjeta, el CVV ni la
    fecha de caducidad. Solo los 4 últimos dígitos, a modo de referencia.
    """

    class MetodoPago(models.TextChoices):
        EN_PISTA = 'en_pista', 'Pago en la pista'
        TARJETA = 'tarjeta', 'Tarjeta (simulada)'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_reserva')
    nombre_completo = models.CharField('nombre completo', max_length=100)
    telefono = models.CharField(
        'teléfono', max_length=20,
        validators=[RegexValidator(
            regex=TELEFONO_REGEX,
            message='Introduce un teléfono válido: entre 7 y 20 caracteres con dígitos, espacios, guiones o + inicial.',
        )],
    )
    email_contacto = models.EmailField('correo de contacto')
    metodo_pago = models.CharField('método de pago', max_length=10, choices=MetodoPago.choices)
    tarjeta_ultimos4 = models.CharField(
        'últimos 4 dígitos de la tarjeta', max_length=4, blank=True,
        validators=[RegexValidator(
            regex=ULTIMOS4_REGEX,
            message='Escribe exactamente 4 dígitos (solo los 4 últimos de la tarjeta).',
        )],
    )
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Datos de reserva'
        verbose_name_plural = 'Datos de reserva'

    def __str__(self):
        return f"Datos de reserva de {self.user.username}"

    def clean(self):
        """Coherencia entre método de pago y referencia de tarjeta."""
        if self.metodo_pago == self.MetodoPago.TARJETA and not self.tarjeta_ultimos4:
            raise ValidationError({
                'tarjeta_ultimos4': 'Indica los 4 últimos dígitos de la tarjeta o elige "Pago en la pista".'
            })
        if self.metodo_pago == self.MetodoPago.EN_PISTA:
            self.tarjeta_ultimos4 = ''

    def esta_completo(self):
        """True si todos los datos necesarios para reservar están presentes y son válidos."""
        if not (self.nombre_completo and self.telefono and self.email_contacto):
            return False
        if not re.match(TELEFONO_REGEX, self.telefono):
            return False
        if self.metodo_pago == self.MetodoPago.EN_PISTA:
            return True
        if self.metodo_pago == self.MetodoPago.TARJETA:
            return bool(re.match(ULTIMOS4_REGEX, self.tarjeta_ultimos4 or ''))
        return False

    def resumen(self):
        """Texto con los datos que se reutilizan al reservar (sin datos sensibles)."""
        pago = self.get_metodo_pago_display() or 'Sin método de pago'
        if self.metodo_pago == self.MetodoPago.TARJETA and self.tarjeta_ultimos4:
            pago = f"{pago} •••• {self.tarjeta_ultimos4}"
        return f"{self.nombre_completo} · {self.email_contacto} · {self.telefono} · {pago}"
