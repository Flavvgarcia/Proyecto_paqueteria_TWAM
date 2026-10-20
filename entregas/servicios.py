"""
Casos de uso (Service Layer). Las vistas solo reciben la petición y
llaman a estas funciones; aquí vive el trámite.
"""
import uuid

from django.db import transaction

from .models import Pedido
from .reglas import elegir_medio


def nuevo_folio():
    return uuid.uuid4().hex[:8].upper()


@transaction.atomic
def registrar_pedido(destino, distancia_km=None, peso_kg=None):
    medio, motivo = "", ""
    if distancia_km is not None and peso_kg is not None:
        medio, motivo = elegir_medio(distancia_km, peso_kg)

    return Pedido.objects.create(
        folio=nuevo_folio(),
        destino=destino,
        distancia_km=distancia_km,
        peso_kg=peso_kg,
        medio=medio,
        motivo=motivo,
    )
