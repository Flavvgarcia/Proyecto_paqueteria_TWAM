"""
ID de petición (X-Request-ID): un mismo identificador viaja por todos los servicios
que atienden una petición, para poder seguirla en los logs de punta a punta.

    navegador ──► gateway ──► pedidos ──► rutas / recomendar
                  (lo crea)   (lo reenvía)  (lo reciben)

    docker compose logs | Select-String "id=3f9c..."   -> todos los pasos de ESE pedido

Cada servicio tiene su propia copia de este archivo (los microservicios no comparten
código: cada uno se construye y se despliega solo).
"""
import re
import time
import uuid

from flask import g, request

# Solo se acepta un ID "limpio": evita que alguien meta saltos de línea o texto raro en los logs.
ID_VALIDO = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def instalar(app, servicio):
    """Registra en la app lo que pasa antes y después de cada petición."""

    @app.before_request
    def tomar_id():
        recibido = request.headers.get("X-Request-ID", "")
        # Si llega por el gateway, trae ID; si llamaron directo al servicio, se crea uno.
        g.id_peticion = recibido if ID_VALIDO.match(recibido) else uuid.uuid4().hex
        g.inicio = time.perf_counter()

    @app.after_request
    def registrar(respuesta):
        id_peticion = g.get("id_peticion", "-")
        respuesta.headers["X-Request-ID"] = id_peticion
        if request.path != "/salud":  # la página pregunta la salud seguido: solo haría ruido
            ms = (time.perf_counter() - g.get("inicio", time.perf_counter())) * 1000
            print(f"[{servicio}] id={id_peticion} {request.method} {request.path} "
                  f"-> {respuesta.status_code} ({ms:.0f} ms)", flush=True)
        return respuesta


def cabeceras():
    """Encabezados para reenviar el ID cuando este servicio llama a otro."""
    return {"X-Request-ID": g.get("id_peticion", uuid.uuid4().hex)}
