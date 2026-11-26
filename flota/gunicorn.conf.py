# Configuración de gunicorn para FLOTA (ver la explicación en pedidos/gunicorn.conf.py).

bind = "0.0.0.0:8005"
workers = 2          # aquí sí 2: el estado vive en la base, no en memoria
timeout = 30


def on_starting(server):
    """Crea la tabla y carga la flota inicial UNA vez, antes de los workers.
    Si la base no responde, gunicorn no arranca y Compose lo reinicia."""
    from app import crear_tablas
    crear_tablas()
