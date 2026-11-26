# Configuración de gunicorn para CLIMA (ver la explicación en pedidos/gunicorn.conf.py).

bind = "0.0.0.0:8004"
# UN solo worker a propósito: la caché del pronóstico vive en la memoria del proceso.
# Con 2 workers habría 2 cachés y se consultaría Open-Meteo el doble.
workers = 1
threads = 4          # pero atiende varias peticiones a la vez con hilos
timeout = 30
