from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
# Create your views here.

def estado(request):
    return JsonResponse({
        "servicio": "entregas",
        "version": 1,
        "medios_disponibles": ["camioneta", "moto", "bicicleta", "dron"],
    })