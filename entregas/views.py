import socket

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import servicios
from .forms import CotizacionForm
from .models import Pedido
from .reglas import elegir_medio
from .servicios import nuevo_folio

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


def cotizar(request):
    form = CotizacionForm(request.GET)
    if not form.is_valid():
        errores = {campo: list(mensajes) for campo, mensajes in form.errors.items()}
        return JsonResponse({"errores": errores}, status=400,
                            json_dumps_params={"ensure_ascii": False})

    km = form.cleaned_data["km"]
    kg = form.cleaned_data["kg"]
    medio, motivo = elegir_medio(km, kg)
    return JsonResponse({"km": km, "kg": kg, "medio": medio, "motivo": motivo},
                        json_dumps_params={"ensure_ascii": False})


@csrf_exempt
@require_POST
def registrar_pedido(request):
    pedido = servicios.registrar_pedido(
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
        "medio": pedido.medio,
        "atendido_por": COPIA,
    }, json_dumps_params={"ensure_ascii": False})


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
