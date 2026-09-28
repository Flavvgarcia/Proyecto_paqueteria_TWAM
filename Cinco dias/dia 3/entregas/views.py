from django.shortcuts import render, redirect, get_object_or_404
from .services import registrar_pedido
from .models import Pedido

def crear_pedido(request):
    if request.method == 'POST':
        descripcion = request.POST.get('descripcion')
        # La vista queda delgada: llama al trámite
        pedido = registrar_pedido(descripcion)
        # Redirigimos al GET para evitar duplicados si recargan la página (Patrón PRG)
        return redirect('detalle_pedido', pedido_id=pedido.id)
    
    return render(request, 'entregas/formulario.html')

def detalle_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id)
    # Contexto listo, sin hacer consultas SQL desde el HTML
    return render(request, 'entregas/detalle.html', {'pedido': pedido})