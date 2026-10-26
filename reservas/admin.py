from django.contrib import admin, messages
from django.utils import timezone
from .models import Resource, Availability, Booking

# --- CONFIGURACIÓN DEL PANEL ADMIN ---

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description')  # Columnas que veremos en el admin
    search_fields = ('name',)                     # Buscar recursos por nombre


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ('id', 'resource', 'start_time', 'end_time')
    list_filter = ('resource',)                   # Filtro por recurso
    search_fields = ('resource__name',)
    verbose_name = 'Bloqueo'
    verbose_name_plural = 'Bloqueos'

    def save_model(self, request, obj, form, change):
        """
        Avisa al admin cuando el bloque se solapa con reservas existentes.
        La política es que la reserva existente gana: el bloqueo se guarda y las
        reservas no se tocan.
        """
        super().save_model(request, obj, form, change)
        solapadas = getattr(obj, 'reservas_solapadas', 0)
        if solapadas:
            self.message_user(
                request,
                f"El bloqueo se guardó, pero se solapa con {solapadas} reserva(s) existente(s). "
                "Las reservas se mantienen y el bloqueo solo impide reservas nuevas.",
                level=messages.WARNING,
            )


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'resource', 'start_time', 'end_time', 'estado', 'serie', 'created_at')
    list_filter = ('resource', 'user', 'estado')
    search_fields = ('user__username', 'resource__name')
    readonly_fields = ('cancelada_en', 'cancelada_por', 'serie')

    def save_model(self, request, obj, form, change):
        """Registra quién y cuándo canceló si el admin cambia el estado a mano."""
        if obj.estado == Booking.Estado.CANCELADA and obj.cancelada_en is None:
            obj.cancelada_en = timezone.now()
            obj.cancelada_por = request.user
        elif obj.estado == Booking.Estado.ACTIVA:
            obj.cancelada_en = None
            obj.cancelada_por = None
        super().save_model(request, obj, form, change)
