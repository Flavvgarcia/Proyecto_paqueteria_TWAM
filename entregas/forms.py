from django import forms

from .models import Pedido

# Rangos del dataset del curso (envios_medios.csv): km 0.34–59.12, kg 0.1–80.
KM_MIN, KM_MAX = 0.1, 60
KG_MIN, KG_MAX = 0.1, 80


# Las reglas de km y kg se escriben una sola vez y las usan los dos formularios.
def campo_km(label="Distancia (km)"):
    return forms.FloatField(
        label=label, min_value=KM_MIN, max_value=KM_MAX,
        error_messages={
            "required": "Falta la distancia (km).",
            "invalid": "La distancia debe ser un número (usa punto: 5.5).",
            "min_value": "La distancia debe ser de al menos %(limit_value)s km.",
            "max_value": "No cubrimos más de %(limit_value)s km.",
        },
    )


def campo_kg(label="Peso (kg)"):
    return forms.FloatField(
        label=label, min_value=KG_MIN, max_value=KG_MAX,
        error_messages={
            "required": "Falta el peso (kg).",
            "invalid": "El peso debe ser un número (usa punto: 2.5).",
            "min_value": "El peso debe ser de al menos %(limit_value)s kg.",
            "max_value": "No llevamos paquetes de más de %(limit_value)s kg.",
        },
    )


class CotizacionForm(forms.Form):
    """Para GET /entregas/cotizar/?km=..&kg=.."""
    km = campo_km()
    kg = campo_kg()


class PedidoForm(forms.ModelForm):
    """Para el formulario del panel."""
    distancia_km = campo_km()
    peso_kg = campo_kg()

    class Meta:
        model = Pedido
        fields = ["destino", "distancia_km", "peso_kg"]
        labels = {"destino": "Dirección de destino"}
        error_messages = {"destino": {"required": "Falta la dirección de destino."}}
        widgets = {"destino": forms.TextInput(attrs={"placeholder": "Calle Morelos 120, Centro"})}
