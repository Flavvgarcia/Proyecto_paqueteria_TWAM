from django.shortcuts import render, redirect, get_object_or_404
from .services import registrar_pedido, obtener_datos_seguimiento
from .models import Pedido
from . import adapter


def crear_pedido(request):
    """
    POST /pedidos/ → crea pedido → redirect a GET (PRG).
    La vista queda delgada: solo extrae el dato y delega.
    """
    if request.method == 'POST':
        descripcion = request.POST.get('descripcion')
        # La vista queda delgada: llama al trámite
        pedido = registrar_pedido(descripcion)
        # Redirigimos al GET para evitar duplicados si recargan la página (Patrón PRG)
        return redirect('detalle_pedido', pedido_id=pedido.id)

    return render(request, 'entregas/formulario.html', {'ia_activa': adapter.IA_ACTIVA})


def toggle_ia(request):
    """
    Permite alternar el flag de la IA (encendida / apagada) desde la interfaz
    para demostrar fácilmente el Inconveniente 6 y el mecanismo de fallback.
    """
    adapter.IA_ACTIVA = not adapter.IA_ACTIVA
    return redirect('crear_pedido')


def detalle_pedido(request, pedido_id):
    """
    GET /pedidos/<id>/ → muestra seguimiento con mapa y ETA.

    Inconveniente 3: La plantilla NO hace SQL.
    Usa obtener_datos_seguimiento() que arma el contexto completo.

    Inconveniente 6: Si la IA estaba caída cuando se creó el pedido,
    este GET sigue funcionando porque el pedido ya está en la BD.
    """
    contexto = obtener_datos_seguimiento(pedido_id)
    return render(request, 'entregas/detalle.html', contexto)


def reporte_pedido(request, pedido_id):
    """
    GET /pedidos/<id>/reporte/ → reporte gerencial del mismo pedido.

    Inconveniente 3: NO duplica las consultas de detalle_pedido.
    Reutiliza obtener_datos_seguimiento() (misma función, distinto formato).
    """
    contexto = obtener_datos_seguimiento(pedido_id)
    return render(request, 'entregas/reporte.html', contexto)


def lista_pedidos(request):
    """
    GET /pedidos/lista/ → lista todos los pedidos (vista para reporte gerencial).
    """
    pedidos = Pedido.objects.all().order_by('-id')
    return render(request, 'entregas/lista.html', {'pedidos': pedidos})