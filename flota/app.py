"""
Servicio FLOTA: el inventario de vehículos y a qué pedido está apartado cada uno.
Tiene su PROPIA base (db-flota): ningún otro servicio la toca; le piden cosas por HTTP.

Estados de un vehículo:
    disponible ──apartar──► apartado ──salida──► en_ruta
        ▲                      │                    │
        └────── liberar ───────┴────────────────────┘     (+ mantenimiento: fuera de servicio)

GET    /salud
GET    /vehiculos                 -> inventario completo + resumen por tipo
POST   /asignaciones              -> {"folio": "A1B2C3D4", "medios": ["moto", "camioneta"]}
                                     aparta el primer vehículo libre, probando los medios en orden
                                     (o {"folio", "vehiculo": "MOTO-03", "estado": ...}: compensación)
PATCH  /asignaciones/<folio>      -> {"estado": "en_ruta"} (salida) o {"estado": "apartado"} (deshacer)
DELETE /asignaciones/<folio>      -> libera el vehículo del pedido
"""
import os
import re

import psycopg
from flask import Flask, jsonify, request
from psycopg.rows import dict_row

import id_peticion

app = Flask(__name__)
app.json.ensure_ascii = False
id_peticion.instalar(app, "flota")

CONEXION = {
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "dbname": os.environ.get("POSTGRES_DB", "flota"),
    "user": os.environ.get("POSTGRES_USER", "flota"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
}

# Flota inicial: solo se carga si la tabla está vacía (la primera vez).
FLOTA_INICIAL = {"bicicleta": ("BICI", 5), "moto": ("MOTO", 8),
                 "camioneta": ("CAM", 4), "dron": ("DRON", 2)}
ESTADOS = ["disponible", "apartado", "en_ruta", "mantenimiento"]
FOLIO_VALIDO = re.compile(r"^[A-Z0-9]{4,12}$")

COLUMNAS = """clave, tipo, estado, folio,
    to_char(desde AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS') AS desde"""


def conectar():
    return psycopg.connect(**CONEXION, row_factory=dict_row, connect_timeout=3)


def crear_tablas():
    """Crea la tabla y carga la flota inicial si está vacía. La llama gunicorn al arrancar."""
    with conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vehiculos (
                id      SERIAL PRIMARY KEY,
                clave   VARCHAR(20) UNIQUE NOT NULL,
                tipo    VARCHAR(20) NOT NULL,
                estado  VARCHAR(20) NOT NULL DEFAULT 'disponible',
                folio   VARCHAR(12),
                desde   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        # Un pedido no puede tener dos vehículos: la base lo garantiza (aunque lleguen
        # dos peticiones iguales al mismo tiempo).
        conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS un_vehiculo_por_pedido
                        ON vehiculos (folio) WHERE folio IS NOT NULL""")
        if conn.execute("SELECT count(*) AS n FROM vehiculos").fetchone()["n"] == 0:
            for tipo, (prefijo, cuantos) in FLOTA_INICIAL.items():
                for i in range(1, cuantos + 1):
                    conn.execute("INSERT INTO vehiculos (clave, tipo) VALUES (%s, %s)",
                                 (f"{prefijo}-{i:02d}", tipo))
            print("Flota inicial cargada:", {t: c for t, (_, c) in FLOTA_INICIAL.items()}, flush=True)


def error(mensaje, codigo, **extra):
    return jsonify({"servicio": "flota", "error": mensaje, **extra}), codigo


def sin_base():
    return error("la base de datos de la flota no está disponible", 503)


@app.get("/salud")
def salud():
    try:
        with conectar() as conn:
            n = conn.execute("SELECT count(*) AS n FROM vehiculos").fetchone()["n"]
        base = "ok"
    except psycopg.Error:
        n, base = None, "no responde"
    return jsonify({"servicio": "flota", "estado": "ok", "base_de_datos": base, "vehiculos": n})


@app.get("/vehiculos")
def vehiculos():
    try:
        with conectar() as conn:
            filas = conn.execute("SELECT " + COLUMNAS + " FROM vehiculos ORDER BY tipo, clave").fetchall()
    except psycopg.Error:
        return sin_base()
    resumen = {}
    for v in filas:
        cuenta = resumen.setdefault(v["tipo"], {e: 0 for e in ESTADOS} | {"total": 0})
        cuenta[v["estado"]] += 1
        cuenta["total"] += 1
    return jsonify({"servicio": "flota", "resumen": resumen, "vehiculos": filas})


@app.post("/asignaciones")
def asignar():
    datos = request.get_json(silent=True) or {}
    folio = str(datos.get("folio", "")).upper()
    if not FOLIO_VALIDO.match(folio):
        return error("folio inválido", 400)
    try:
        with conectar() as conn:
            # Idempotente: si el pedido ya tiene vehículo (p. ej. un reintento), se regresa ese.
            ya = conn.execute("SELECT " + COLUMNAS + " FROM vehiculos WHERE folio = %s", (folio,)).fetchone()
            if ya:
                return jsonify({"servicio": "flota", "vehiculo": ya, "medio": ya["tipo"], "repetido": True})

            # Compensación: volver a apartar UN vehículo específico (si sigue libre).
            if datos.get("vehiculo"):
                estado = datos.get("estado", "apartado")
                if estado not in ("apartado", "en_ruta"):
                    return error("estado inválido", 400)
                v = conn.execute(
                    "UPDATE vehiculos SET estado = %s, folio = %s, desde = now() "
                    "WHERE clave = %s AND estado = 'disponible' RETURNING " + COLUMNAS,
                    (estado, folio, datos["vehiculo"])).fetchone()
                if v is None:
                    return error(f"{datos['vehiculo']} ya no está disponible", 409)
                id_peticion.log(f"folio={folio} recupera {v['clave']} (compensación)")
                return jsonify({"servicio": "flota", "vehiculo": v, "medio": v["tipo"]}), 201

            medios = datos.get("medios")
            if not isinstance(medios, list) or not medios or not all(m in FLOTA_INICIAL for m in medios):
                return error("medios debe ser una lista de: " + ", ".join(FLOTA_INICIAL), 400)
            for medio in medios:
                # FOR UPDATE SKIP LOCKED: si otro pedido está apartando un vehículo en este
                # mismo instante, se SALTA ese y toma el siguiente libre. Así dos pedidos
                # simultáneos nunca se quedan con el mismo vehículo, y ninguno espera al otro.
                v = conn.execute("""
                    UPDATE vehiculos SET estado = 'apartado', folio = %s, desde = now()
                    WHERE id = (SELECT id FROM vehiculos
                                WHERE tipo = %s AND estado = 'disponible'
                                ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED)
                    RETURNING """ + COLUMNAS, (folio, medio)).fetchone()
                if v:
                    id_peticion.log(f"folio={folio} apartó {v['clave']}"
                                    + (f" (no había {medios[0]})" if medio != medios[0] else ""))
                    return jsonify({"servicio": "flota", "vehiculo": v, "medio": medio,
                                    "cambio_de_medio": medio != medios[0]}), 201
    except psycopg.errors.UniqueViolation:
        # Dos peticiones del mismo pedido al mismo tiempo: la otra ganó. Se regresa la suya.
        with conectar() as conn:
            ya = conn.execute("SELECT " + COLUMNAS + " FROM vehiculos WHERE folio = %s", (folio,)).fetchone()
        return jsonify({"servicio": "flota", "vehiculo": ya, "medio": ya["tipo"], "repetido": True})
    except psycopg.Error:
        return sin_base()
    id_peticion.log(f"folio={folio} sin vehículos libres de: {', '.join(medios)}")
    return error("no hay vehículos disponibles de: " + ", ".join(medios), 409, medios=medios)


@app.patch("/asignaciones/<folio>")
def mover(folio):
    """Salida (apartado -> en_ruta) o su compensación (en_ruta -> apartado)."""
    folio = folio.upper()
    nuevo = (request.get_json(silent=True) or {}).get("estado")
    antes = {"en_ruta": "apartado", "apartado": "en_ruta"}.get(nuevo)
    if antes is None:
        return error("estado debe ser en_ruta o apartado", 400)
    try:
        with conectar() as conn:
            v = conn.execute(
                "UPDATE vehiculos SET estado = %s, desde = now() WHERE folio = %s AND estado = %s "
                "RETURNING " + COLUMNAS, (nuevo, folio, antes)).fetchone()
            if v is None:
                actual = conn.execute("SELECT estado FROM vehiculos WHERE folio = %s", (folio,)).fetchone()
    except psycopg.Error:
        return sin_base()
    if v is None:
        if actual is None:
            return error(f"el pedido {folio} no tiene vehículo", 404)
        if actual["estado"] == nuevo:       # ya estaba así: reintento, no es error
            return jsonify({"servicio": "flota", "estado": nuevo, "repetido": True})
        return error(f"el vehículo está {actual['estado']}, no {antes}", 409)
    id_peticion.log(f"folio={folio} {v['clave']} -> {nuevo}")
    return jsonify({"servicio": "flota", "vehiculo": v})


@app.delete("/asignaciones/<folio>")
def liberar(folio):
    """Libera el vehículo del pedido. Si no tenía, no pasa nada (idempotente)."""
    folio = folio.upper()
    try:
        with conectar() as conn:
            v = conn.execute(
                "UPDATE vehiculos SET estado = 'disponible', folio = NULL, desde = now() "
                "WHERE folio = %s RETURNING clave, tipo", (folio,)).fetchone()
    except psycopg.Error:
        return sin_base()
    if v:
        id_peticion.log(f"folio={folio} liberó {v['clave']}")
    return jsonify({"servicio": "flota", "liberado": v["clave"] if v else None})


if __name__ == "__main__":
    crear_tablas()
    app.run(host="0.0.0.0", port=8005)
