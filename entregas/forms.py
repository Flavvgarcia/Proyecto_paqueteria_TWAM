from django import forms

# Rangos del dataset del curso (envios_medios.csv): km 0.34–59.12, kg 0.1–80.
KM_MIN, KM_MAX = 0.1, 60
KG_MIN, KG_MAX = 0.1, 80


class CotizacionForm(forms.Form):
    km = forms.FloatField(
        min_value=KM_MIN, max_value=KM_MAX,
        error_messages={
            "required": "Falta la distancia (km).",
            "invalid": "La distancia debe ser un número (usa punto: 5.5).",
            "min_value": "La distancia debe ser de al menos %(limit_value)s km.",
            "max_value": "No cubrimos más de %(limit_value)s km.",
        },
    )
    kg = forms.FloatField(
        min_value=KG_MIN, max_value=KG_MAX,
        error_messages={
            "required": "Falta el peso (kg).",
            "invalid": "El peso debe ser un número (usa punto: 2.5).",
            "min_value": "El peso debe ser de al menos %(limit_value)s kg.",
            "max_value": "No llevamos paquetes de más de %(limit_value)s kg.", # no levanto gordas
        },
    )