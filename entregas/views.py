import socket
import uuid

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Pedido

COPIA = socket.gethostname()

pedidos_en_memoria = {}


def hola(request):
    return HttpResponse("Hola. Plataforma de entregas (aún sin pedidos).")


def estado(request):
    return JsonResponse({
        "servicio": "entregas",
        "version": 1,
        "medios_disponibles": ["camioneta", "moto", "bicicleta", "dron"],
        "atendido_por": COPIA,
    })


def nuevo_folio():
    return uuid.uuid4().hex[:8].upper()


@csrf_exempt
@require_POST
def registrar_pedido(request):
    pedido = Pedido.objects.create(
        folio=nuevo_folio(),
        destino=request.POST.get("destino", "sin destino"),
    )
    return JsonResponse({"folio": pedido.folio, "registrado_por": COPIA}, status=201)


@require_GET
def seguimiento(request, folio):
    pedido = Pedido.objects.filter(folio=folio).first()
    if pedido is None:
        return JsonResponse({"error": "pedido no encontrado", "atendido_por": COPIA}, status=404)
    return JsonResponse({
        "folio": pedido.folio,
        "destino": pedido.destino,
        "estado": pedido.estado,
        "atendido_por": COPIA,
    })


@csrf_exempt
@require_POST
def registrar_pedido_mal(request):
    folio = nuevo_folio()
    pedidos_en_memoria[folio] = {
        "destino": request.POST.get("destino", "sin destino"),
        "estado": "registrado",
    }
    return JsonResponse({"folio": folio, "registrado_por": COPIA}, status=201)


@require_GET
def seguimiento_mal(request, folio):
    pedido = pedidos_en_memoria.get(folio)
    if pedido is None:
        return JsonResponse({"error": "pedido no encontrado", "atendido_por": COPIA}, status=404)
    return JsonResponse({"folio": folio, **pedido, "atendido_por": COPIA})