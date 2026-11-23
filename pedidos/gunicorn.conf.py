# Configuración de gunicorn para PEDIDOS. gunicorn la lee solo al arrancar
# (busca "gunicorn.conf.py" en la carpeta de trabajo).
#
# ¿Por qué gunicorn y no "python app.py"? El servidor de Flask es de desarrollo:
# atiende con un solo proceso y él mismo avisa "Do not use it in production".
# gunicorn levanta varios procesos (workers): si uno está ocupado, otro atiende.

bind = "0.0.0.0:8001"
workers = 2          # 2 procesos; para este proyecto sobra
timeout = 30         # un pedido puede esperar a rutas (8 s) + recomendar (5 s) + rutas (8 s)


def on_starting(server):
    """Corre UNA vez, en el proceso principal, antes de crear los workers.
    Así la tabla se crea una sola vez (y no dos workers a la vez).
    Si la base no responde, gunicorn no arranca y Compose lo reinicia (restart: on-failure)."""
    from app import crear_tabla
    crear_tabla()
