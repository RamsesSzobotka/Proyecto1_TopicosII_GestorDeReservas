from django import forms

from .models import PerfilReserva


class PerfilReservaForm(forms.ModelForm):
    """Datos de reserva del usuario. No admite número de tarjeta, CVV ni caducidad."""

    class Meta:
        model = PerfilReserva
        fields = ['nombre_completo', 'telefono', 'email_contacto', 'metodo_pago', 'tarjeta_ultimos4']
        help_texts = {
            'telefono': 'Entre 7 y 20 caracteres: dígitos, espacios, guiones o + inicial.',
            'tarjeta_ultimos4': 'Solo los 4 últimos dígitos. Nunca escribas el número completo ni el CVV.',
        }
        widgets = {
            'tarjeta_ultimos4': forms.TextInput(attrs={
                'inputmode': 'numeric', 'autocomplete': 'off', 'maxlength': '4',
            }),
        }
        error_messages = {
            'nombre_completo': {
                'required': 'Escribe tu nombre completo.',
                'max_length': 'El nombre no puede superar los 100 caracteres.',
            },
            'telefono': {'required': 'Escribe un teléfono de contacto.'},
            'email_contacto': {
                'required': 'Escribe un correo de contacto.',
                'invalid': 'Introduce un correo válido, por ejemplo nombre@dominio.com.',
            },
            'metodo_pago': {
                'required': 'Elige un método de pago.',
                'invalid_choice': 'Elige un método de pago de la lista.',
            },
        }

    def clean(self):
        cleaned = super().clean()
        # Con pago en la pista los últimos 4 se descartan: su formato no debe bloquear el guardado.
        if cleaned.get('metodo_pago') == PerfilReserva.MetodoPago.EN_PISTA:
            self.errors.pop('tarjeta_ultimos4', None)
            cleaned['tarjeta_ultimos4'] = ''
        return cleaned
