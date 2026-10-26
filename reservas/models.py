from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

# Antelación mínima para que un cliente cancele su propia reserva (ISSUE-06).
# Un administrador (is_staff) no está sujeto a este margen, pero tampoco puede
# cancelar una reserva que ya empezó.
LIMITE_CANCELACION = timedelta(hours=2)


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
