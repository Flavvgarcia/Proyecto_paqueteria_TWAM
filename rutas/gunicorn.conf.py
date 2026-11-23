# Configuración de gunicorn para RUTAS (ver la explicación en pedidos/gunicorn.conf.py).

bind = "0.0.0.0:8003"
workers = 2
timeout = 30     # ORS tiene 5 s de timeout; sobra
