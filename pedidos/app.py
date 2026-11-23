"""
Servicio PEDIDOS: crea el pedido. NO carga el modelo: le pregunta a recomendar por HTTP.
Los pedidos se guardan en PostgreSQL (su propia base, solo de este servicio).

GET  /salud    -> quién es, a qué URL llama y si la base responde
POST /pedidos  -> mide la distancia real (rutas), pide el medio (recomendar) y el plan (rutas),
                  inventa un folio y lo guarda
GET  /pedidos  -> lista los pedidos guardados (los más recientes primero)
GET  /pedidos/<folio> -> seguimiento de un pedido
"""
import os
import uuid

import psycopg
import requests
from flask import Flask, jsonify, request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

app = Flask(__name__)
app.json.ensure_ascii = False  # acentos legibles en curl

# Dentro de Compose: http://recomendar:8002 (el nombre del servicio es el host).
RECOMENDAR_URL = os.environ.get("RECOMENDAR_URL", "http://localhost:8002")
RUTAS_URL = os.environ.get("RUTAS_URL", "http://localhost:8003")
MEDIO_POR_DEFECTO = "camioneta"

# Datos de conexión a la base. En Compose, POSTGRES_HOST vale "db-pedidos".
CONEXION = (
    f"host={os.environ.get('POSTGRES_HOST', 'localhost')} "
    f"dbname={os.environ.get('POSTGRES_DB', 'pedidos')} "
    f"user={os.environ.get('POSTGRES_USER', 'pedidos')} "
    f"password={os.environ.get('POSTGRES_PASSWORD', 'pedidos')}"
)


# Columnas que se devuelven al cliente. La fecha sale en hora de México y en texto legible.
COLUMNAS = """folio, medio, motivo, modelo, plan_b, estado, plan,
    to_char(creado_en AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS') AS creado_en"""


def conectar():
    """Abre una conexión nueva. Devuelve las filas como diccionarios."""
    return psycopg.connect(CONEXION, row_factory=dict_row, connect_timeout=3)


def crear_tabla():
    """Crea la tabla la primera vez. Si ya existe, no hace nada."""
    with conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id         SERIAL PRIMARY KEY,
                folio      VARCHAR(12) UNIQUE NOT NULL,
                medio      VARCHAR(20) NOT NULL,
                motivo     TEXT NOT NULL,
                modelo     VARCHAR(20) NOT NULL,
                plan_b     BOOLEAN NOT NULL DEFAULT FALSE,
                estado     VARCHAR(20) NOT NULL DEFAULT 'registrado',
                paquete    JSONB NOT NULL,
                creado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        # La tabla ya existía antes del plan: se le agrega la columna si le falta.
        conn.execute("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS plan JSONB")


def guardar(pedido, paquete):
    """Inserta el pedido y lo devuelve tal como quedó en la base."""
    with conectar() as conn:
        return conn.execute(
            """
            INSERT INTO pedidos (folio, medio, motivo, modelo, plan_b, paquete, plan)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING """ + COLUMNAS,
            (pedido["folio"], pedido["medio"], pedido["motivo"], pedido["modelo"],
             pedido["plan_b"], Jsonb(paquete), Jsonb(pedido["plan"]) if pedido["plan"] else None),
        ).fetchone()


class DestinoInvalido(Exception):
    """rutas dijo que el destino no sirve (400): es un error del cliente, no se crea folio."""


def medir_distancia(destino):
    """Le pide a rutas los km por calle hasta el destino. Regresa (km, fuente, nota).
    Si rutas no responde, km = None. Si el destino es inválido, lanza DestinoInvalido."""
    try:
        r = requests.post(f"{RUTAS_URL}/distancia", json={"destino": destino}, timeout=8)
    except requests.RequestException as e:
        return None, None, f"rutas NO respondió al medir la distancia ({type(e).__name__})"
    if r.status_code == 400:
        raise DestinoInvalido(r.json().get("error"))
    if r.status_code != 200:
        return None, None, f"rutas respondió {r.status_code} al medir la distancia"
    d = r.json()
    return d["km"], d["fuente"], f"rutas midió {d['km']} km por calle ({d['fuente']})"


def pedir_plan(medio, destino):
    """Le pide a rutas el plan de entrega. Regresa (plan, nota). Si falla, plan = None."""
    if not destino:
        return None, "sin destino: no se calculó el plan"
    try:
        r = requests.post(f"{RUTAS_URL}/plan", json={"medio": medio, "destino": destino}, timeout=8)
    except requests.RequestException as e:
        return None, f"rutas NO respondió ({type(e).__name__}): pedido sin plan"
    if r.status_code != 200:
        return None, f"rutas respondió {r.status_code}: {r.json().get('error')}"
    plan = r.json()
    datos = {c: plan.get(c) for c in ("km", "minutos", "indicacion", "fuente", "aviso")}
    return datos, f"rutas calculó el plan: {datos['minutos']} min ({datos['fuente']})"


def consultar_recomendar(paquete, modelo, recorrido):
    """Pide el medio a recomendar. Regresa (pedido, codigo, error_http).
    Si recomendar no responde: plan B. Si rechaza el paquete: error_http (sin folio)."""
    recorrido.append(f"pedidos llamó a recomendar ({modelo})")
    try:
        r = requests.post(f"{RECOMENDAR_URL}/sugerir", json=paquete, timeout=5)
    except requests.RequestException as e:
        recorrido.append(f"recomendar NO respondió ({type(e).__name__}) → plan B")
        pedido = {"folio": nuevo_folio(), "medio": MEDIO_POR_DEFECTO, "modelo": modelo,
                  "motivo": "recomendar no estuvo disponible; se asignó el medio por defecto",
                  "plan_b": True}
        return pedido, 503, None

    sugerencia = r.json()
    if r.status_code != 200:
        recorrido.append(f"recomendar respondió {r.status_code}: {sugerencia.get('error')}")
        error = jsonify({"servicio": "pedidos", "error": "recomendar rechazó el paquete",
                         "detalle": sugerencia, "recorrido": recorrido}), r.status_code
        return None, None, error

    recorrido.append(f"recomendar sugirió {sugerencia['medio']}")
    pedido = {"folio": nuevo_folio(), "medio": sugerencia["medio"],
              "motivo": sugerencia["motivo"],
              "modelo": sugerencia.get("modelo", modelo), "plan_b": False,
              "preferido_por_modelo": sugerencia.get("preferido_por_modelo"),
              "corregido_por_reglas": sugerencia.get("corregido_por_reglas")}
    return pedido, 201, None


def nuevo_folio():
    return uuid.uuid4().hex[:8].upper()


@app.get("/salud")
def salud():
    try:
        with conectar() as conn:
            conn.execute("SELECT 1")
        base = "ok"
    except psycopg.Error:
        base = "no responde"
    return jsonify({"servicio": "pedidos", "estado": "ok", "base_de_datos": base,
                    "recomendar_url": RECOMENDAR_URL})


@app.get("/pedidos")
def listar():
    try:
        with conectar() as conn:
            filas = conn.execute(
                "SELECT " + COLUMNAS + " FROM pedidos ORDER BY pedidos.creado_en DESC LIMIT 50"
            ).fetchall()
    except psycopg.Error:
        return jsonify({"servicio": "pedidos", "error": "la base de datos no está disponible"}), 503
    return jsonify(filas)


@app.get("/pedidos/<folio>")
def seguimiento(folio):
    folio = folio.strip().upper()  # "a1b2c3d4" y "A1B2C3D4" son el mismo folio
    try:
        with conectar() as conn:
            pedido = conn.execute(
                "SELECT " + COLUMNAS + " FROM pedidos WHERE folio = %s", (folio,)
            ).fetchone()
    except psycopg.Error:
        return jsonify({"servicio": "pedidos", "error": "la base de datos no está disponible"}), 503
    if pedido is None:
        return jsonify({"servicio": "pedidos", "error": f"no existe el folio {folio}"}), 404
    return jsonify(pedido)


@app.post("/pedidos")
def crear():
    paquete = request.get_json(silent=True)
    if not isinstance(paquete, dict):
        return jsonify({"servicio": "pedidos", "error": "el cuerpo debe ser JSON"}), 400

    modelo = paquete.get("modelo", "arbol")
    recorrido = ["gateway recibió la petición", "pedidos recibió el paquete"]

    # 1) Distancia real: la mide rutas con el destino. El modelo decide con ella.
    destino = paquete.get("destino")
    if destino:
        try:
            km, fuente, nota = medir_distancia(destino)
        except DestinoInvalido as e:
            recorrido.append(f"rutas rechazó el destino: {e}")
            return jsonify({"servicio": "pedidos", "error": f"destino inválido: {e}",
                            "recorrido": recorrido}), 400
        recorrido.append(nota)
        if km is not None:
            paquete["distancia_km"], paquete["distancia_fuente"] = km, fuente
    if "distancia_km" in paquete and "distancia_fuente" not in paquete:
        # Sin destino (o rutas caído): se usa la distancia que mandó el cliente.
        paquete["distancia_fuente"] = "manual"
        recorrido.append("se usa la distancia escrita a mano")

    # 2) Medio: lo decide recomendar (con la distancia real).
    if "distancia_km" not in paquete:
        # Sin distancia no se le puede preguntar al modelo: plan B directo.
        pedido = {"folio": nuevo_folio(), "medio": MEDIO_POR_DEFECTO, "modelo": modelo,
                  "motivo": "no se pudo medir la distancia; se asignó el medio por defecto",
                  "plan_b": True}
        recorrido.append("sin distancia no se consulta al modelo → plan B")
        codigo = 503
    else:
        pedido, codigo, error = consultar_recomendar(paquete, modelo, recorrido)
        if error:
            return error

    # 3) Plan de entrega con rutas. Si falla, el pedido se crea igual, sin plan.
    pedido["plan"], nota = pedir_plan(pedido["medio"], paquete.get("destino"))
    recorrido.append(nota)

    # 4) Guardar en la base. Si la base no responde, error claro (no se inventa un folio).
    try:
        guardado = guardar(pedido, paquete)
    except psycopg.Error:
        recorrido.append("la base de datos NO respondió: el pedido no se guardó")
        return jsonify({"servicio": "pedidos", "error": "la base de datos no está disponible",
                        "recorrido": recorrido}), 503
    recorrido.append("pedidos guardó el pedido en la base")

    respuesta = {**guardado, "servicio": "pedidos", "recorrido": recorrido,
                 "distancia_km": paquete.get("distancia_km"),
                 "distancia_fuente": paquete.get("distancia_fuente")}
    if not pedido["plan_b"]:
        respuesta["preferido_por_modelo"] = pedido["preferido_por_modelo"]
        respuesta["corregido_por_reglas"] = pedido["corregido_por_reglas"]
    return jsonify(respuesta), codigo


if __name__ == "__main__":
    crear_tabla()
    app.run(host="0.0.0.0", port=8001)
