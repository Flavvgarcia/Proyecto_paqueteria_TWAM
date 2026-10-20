"""
Vistas del recomendador de IA (Etapa 4 de la página del curso).
Van aparte de views.py para no mezclar el panel/pedidos con el modelo.
"""
import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .medios import crear_medio
from .recomendador import (
    CAMPOS,
    CAMPOS_NUMERICOS,
    MODELOS,
    modelos_disponibles,
    obtener_recomendador,
)


def formulario_recomendar(request):
    """Página HTML para probar el modelo desde el navegador."""
    return render(
        request,
        "entregas/recomendar.html",
        {"modelos": modelos_disponibles()},
    )


@csrf_exempt
@require_POST
def recomendar(request):
    try:
        cuerpo = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "el cuerpo debe ser JSON"}, status=400)

    modelo_id = cuerpo.pop("modelo", "arbol") or "arbol"
    if modelo_id not in MODELOS:
        return JsonResponse(
            {"error": "modelo desconocido", "modelos": list(MODELOS.keys())},
            status=400,
        )

    faltantes = [campo for campo in CAMPOS if campo not in cuerpo]
    if faltantes:
        return JsonResponse({"error": "faltan campos", "campos": faltantes}, status=400)

    try:
        for campo in CAMPOS_NUMERICOS:
            cuerpo[campo] = float(cuerpo[campo])
    except (TypeError, ValueError):
        return JsonResponse({"error": f"el campo {campo} debe ser un número"}, status=400)

    try:
        recomendador = obtener_recomendador(modelo_id)
        resultado = recomendador.explicar(cuerpo)
    except FileNotFoundError as error:
        return JsonResponse({"error": str(error)}, status=503)

    plan = crear_medio(resultado.medio).planear(cuerpo)
    respuesta = resultado.a_dict()
    respuesta["plan"] = plan
    return JsonResponse(respuesta, json_dumps_params={"ensure_ascii": False})
