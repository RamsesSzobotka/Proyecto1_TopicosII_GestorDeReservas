from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


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

    def __str__(self):
        return f"Reserva de {self.resource.name} por {self.user.username}"

    def clean(self):
        """
        Validación para evitar que haya reservas solapadas con la misma franja horaria.
        """
        overlapping = Booking.objects.filter(
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

    class Meta:
        unique_together = ('resource', 'start_time', 'end_time')
