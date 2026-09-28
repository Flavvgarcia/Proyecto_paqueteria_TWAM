from .models import Pedido

def registrar_pedido(descripcion):
    # Aquí irá la lógica compleja (Strategy, Adapter) en los próximos días.
    nuevo_pedido = Pedido.objects.create(descripcion=descripcion)
    return nuevo_pedido