"""
Vistas del panel web (HTML). Las vistas JSON siguen en views.py.
Son delgadas: validan con el Form, llaman al servicio y pintan.
"""
import socket

from django.shortcuts import get_object_or_404, redirect, render

from . import servicios
from .forms import PedidoForm
from .models import Pedido

COPIA = socket.gethostname()


def nuevo_pedido(request):
    if request.method == "POST":
        form = PedidoForm(request.POST)
        if form.is_valid():
            pedido = servicios.registrar_pedido(**form.cleaned_data)
            # PRG: después del POST se redirige; recargar no crea otro folio.
            return redirect("panel_pedido", folio=pedido.folio)
    else:
        form = PedidoForm()

    return render(request, "entregas/nuevo_pedido.html", {
        "form": form,
        "recientes": Pedido.objects.all()[:10],
        "copia": COPIA,
    })


def detalle_pedido(request, folio):
    pedido = get_object_or_404(Pedido, folio=folio)
    return render(request, "entregas/pedido.html", {"pedido": pedido, "copia": COPIA})
