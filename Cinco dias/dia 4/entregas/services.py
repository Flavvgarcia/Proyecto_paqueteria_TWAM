from django.db import transaction
from .models import Pedido
from .adapter import obtener_sugerencia_ia
from .factory import crear_medio


def registrar_pedido(descripcion):
    with transaction.atomic():
        # 1. Guardar en base de datos
        nuevo_pedido = Pedido.objects.create(descripcion=descripcion)

        # 2. Adapter: obtener sugerencia (trae fallback si la IA falla)
        sugerencia = obtener_sugerencia_ia(descripcion)

        # 3. Factory: crear la instancia del medio
        vehiculo = crear_medio(sugerencia.medio)

        # 4. Strategy: calcular plan de entrega
        resultado_plan = vehiculo.planear(nuevo_pedido, sugerencia)

        nuevo_pedido.medio_asignado = sugerencia.medio
        nuevo_pedido.motivo_asignacion = sugerencia.motivo
        nuevo_pedido.save()

        # 5. Cobro simulado dentro de la transaccion
        simular_cobro(nuevo_pedido)

        # 6. Notificacion pos-commit: solo se agenda si la transaccion tiene exito
        transaction.on_commit(lambda: enviar_aviso(nuevo_pedido))

        print(f"[Log] Plan calculado: {resultado_plan}")

    return nuevo_pedido


def simular_cobro(pedido, monto=150.0):
    # Simula el cobro dentro de la transaccion
    print(f"[Cobro] Acreditado cobro de ${monto:.2f} para pedido {pedido.folio}")
    return True


def enviar_aviso(pedido):
    # Simula el envio de correo. Si falla, el pedido ya quedo guardado en la BD
    try:
        print(f"[Notificacion] Correo enviado al cliente para pedido {pedido.folio}")
    except Exception as e:
        print(f"[Notificacion] Error al enviar correo ({e}), pero el pedido ya esta guardado.")


def obtener_datos_seguimiento(pedido_id):
    # Consulta la base de datos una sola vez y arma el contexto para la plantilla
    pedido = Pedido.objects.get(id=pedido_id)

    return {
        'pedido': pedido,
        'folio': str(pedido.folio),
        'descripcion': pedido.descripcion,
        'estado': pedido.estado,
        'eta': pedido.eta,
        'medio_asignado': pedido.medio_asignado or 'Sin asignar',
        'motivo_asignacion': pedido.motivo_asignacion or 'Pendiente',
        'mapa_origen': 'Centro de distribucion',
        'mapa_destino': 'Direccion de entrega',
    }