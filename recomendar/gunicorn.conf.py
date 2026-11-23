# Configuración de gunicorn para RECOMENDAR (ver la explicación en pedidos/gunicorn.conf.py).

bind = "0.0.0.0:8002"
workers = 2
timeout = 30
# preload_app: la app (y los modelos) se cargan UNA vez en el proceso principal y luego
# se copian a los workers. Sin esto, cada worker cargaría su propia copia de los modelos.
preload_app = True


def on_starting(server):
    from app import precargar
    precargar()
