"""
Servicio PEDIDOS: crea el pedido. NO carga el modelo: le pregunta a recomendar por HTTP.
Los pedidos se guardan en PostgreSQL (su propia base, solo de este servicio).

GET  /salud    -> quién es, a qué URL llama y si la base responde
POST /pedidos  -> (con encabezado opcional Idempotency-Key) mide la distancia real (rutas), pide el medio (recomendar) y el plan (rutas),
                  inventa un folio y lo guarda
GET  /pedidos  -> lista los pedidos guardados (los más recientes primero)
GET  /pedidos/<folio> -> seguimiento de un pedido
PATCH /pedidos/<folio> -> cambia el estado: {"estado": "en_camino"} (solo pasos permitidos)
                          SOLO operadores: encabezado "Authorization: Bearer <OPERADOR_CLAVE>"
GET  /operador -> comprueba la clave de operador (para el "modo operador" de la página)
"""
import hashlib
import hmac
import json
import os
import re
import uuid

import psycopg
import requests
from flask import Flask, jsonify, request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import id_peticion
import tarifa
from validacion import validar

app = Flask(__name__)
app.json.ensure_ascii = False  # acentos legibles en curl
id_peticion.instalar(app, "pedidos")

# Dentro de Compose: http://recomendar:8002 (el nombre del servicio es el host).
RECOMENDAR_URL = os.environ.get("RECOMENDAR_URL", "http://localhost:8002")
RUTAS_URL = os.environ.get("RUTAS_URL", "http://localhost:8003")
CLIMA_URL = os.environ.get("CLIMA_URL", "http://localhost:8004")
# Si no se puede saber el clima, se asume lluvia: es lo prudente (así el dron no vuela
# con un clima que nadie revisó). Queda marcado como "supuesto" en el pedido.
CLIMA_SI_FALLA = "lluvia"
MEDIO_POR_DEFECTO = "camioneta"

# Idempotency-Key: la manda el cliente (un UUID por cada intento de crear un pedido).
# Si la misma clave llega dos veces (doble clic, reintento por red lenta), NO se crea
# otro pedido: se regresa el primero.
CLAVE_VALIDA = re.compile(r"^[A-Za-z0-9-]{8,64}$")

# Clave de operador (del .env). Ver el seguimiento es público; CAMBIAR el estado no.
# Si no hay clave configurada, nadie puede cambiar estados (seguro por defecto).
OPERADOR_CLAVE = os.environ.get("OPERADOR_CLAVE", "")


def revisar_operador():
    """None si la petición trae la clave de operador correcta; si no, la respuesta de error.
      401 = no mandó credencial   403 = la mandó, pero no es válida"""
    if not OPERADOR_CLAVE:
        return jsonify({"servicio": "pedidos",
                        "error": "no hay OPERADOR_CLAVE configurada: el cambio de estado está deshabilitado"}), 503
    encabezado = request.headers.get("Authorization", "")
    if not encabezado.startswith("Bearer "):
        respuesta = jsonify({"servicio": "pedidos", "error": "solo un operador puede hacer esto: falta la clave"})
        respuesta.headers["WWW-Authenticate"] = "Bearer"
        return respuesta, 401
    # compare_digest tarda lo mismo acierte o falle: no deja adivinar la clave letra por letra
    # midiendo cuánto tarda la respuesta.
    if not hmac.compare_digest(encabezado[len("Bearer "):].encode(), OPERADOR_CLAVE.encode()):
        id_peticion.log("intento de operador con clave incorrecta")
        return jsonify({"servicio": "pedidos", "error": "clave de operador incorrecta"}), 403
    return None

# Datos de conexión a la base. En Compose, POSTGRES_HOST vale "db-pedidos".
# La contraseña NO tiene valor por defecto en el código: viene del .env (vía Compose).
# Van como parámetros separados (no en un solo texto) para que una contraseña con
# espacios o comillas no rompa la conexión.
CONEXION = {
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "dbname": os.environ.get("POSTGRES_DB", "pedidos"),
    "user": os.environ.get("POSTGRES_USER", "pedidos"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
}


# Columnas que se devuelven al cliente. La fecha sale en hora de México y en texto legible.
# Ciclo de vida del pedido: desde cada estado, a cuáles se puede pasar.
#   registrado -> en_camino -> entregado
#        └────────────┴──────> cancelado
TRANSICIONES = {
    "registrado": ["en_camino", "cancelado"],
    "en_camino": ["entregado", "cancelado"],
    "entregado": [],   # estados finales: ya no cambian
    "cancelado": [],
}

# Un evento del historial: {"estado": ..., "fecha": "2026-11-22 20:30:00"} (hora de México).
EVENTO = """jsonb_build_object('estado', %s::text, 'fecha',
    to_char(now() AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS'))"""

# La distancia vive dentro del paquete (JSONB): "->" la saca tal cual (número o null).
COLUMNAS = """folio, medio, motivo, modelo, plan_b, estado, plan, historial, tarifa,
    paquete->'distancia_km' AS distancia_km, paquete->>'distancia_fuente' AS distancia_fuente,
    paquete->>'clima' AS clima, paquete->'clima_info' AS clima_info,
    to_char(creado_en AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS') AS creado_en"""


def conectar():
    """Abre una conexión nueva. Devuelve las filas como diccionarios."""
    return psycopg.connect(**CONEXION, row_factory=dict_row, connect_timeout=3)


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
        # Idempotencia: la clave que mandó el cliente y la "huella" del paquete que mandó con ella.
        # UNIQUE: la base garantiza que una clave no pueda guardarse dos veces, aunque
        # dos peticiones iguales lleguen al mismo tiempo.
        conn.execute("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS clave_idempotencia VARCHAR(64) UNIQUE")
        # Tarifa cotizada (con desglose). Se guarda tal cual: si cambian los precios,
        # los pedidos viejos conservan lo que se les cotizó.
        conn.execute("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS tarifa JSONB")
        conn.execute("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS huella CHAR(64)")
        # Historial de estados. A los pedidos viejos se les pone su registro con la fecha original.
        conn.execute("ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS historial JSONB NOT NULL DEFAULT '[]'")
        conn.execute("""
            UPDATE pedidos SET historial = jsonb_build_array(jsonb_build_object(
                'estado', 'registrado',
                'fecha', to_char(creado_en AT TIME ZONE 'America/Mexico_City', 'YYYY-MM-DD HH24:MI:SS')))
            WHERE historial = '[]'
        """)


def guardar(pedido, paquete, clave=None, huella=None):
    """Inserta el pedido y lo devuelve tal como quedó en la base.
    Si la clave de idempotencia ya existe, la base lanza UniqueViolation."""
    with conectar() as conn:
        return conn.execute(
            """
            INSERT INTO pedidos (folio, medio, motivo, modelo, plan_b, paquete, plan, historial,
                                 clave_idempotencia, huella, tarifa)
            VALUES (%s, %s, %s, %s, %s, %s, %s, jsonb_build_array(""" + EVENTO + """), %s, %s, %s)
            RETURNING """ + COLUMNAS,
            (pedido["folio"], pedido["medio"], pedido["motivo"], pedido["modelo"],
             pedido["plan_b"], Jsonb(paquete), Jsonb(pedido["plan"]) if pedido["plan"] else None,
             "registrado", clave, huella, Jsonb(pedido["tarifa"]) if pedido["tarifa"] else None),
        ).fetchone()


def buscar_por_clave(clave):
    """El pedido que ya se creó con esta clave (con su huella), o None."""
    with conectar() as conn:
        return conn.execute(
            "SELECT " + COLUMNAS + ", huella FROM pedidos WHERE clave_idempotencia = %s", (clave,)
        ).fetchone()


def huella_de(cuerpo):
    """Resumen (SHA-256) del paquete tal como llegó. Mismo paquete -> misma huella."""
    texto = json.dumps(cuerpo, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def responder_repetido(previo, huella, recorrido):
    """La clave ya se había usado: se regresa el pedido original (o 422 si el paquete es otro)."""
    huella_original = previo.pop("huella")
    if huella_original != huella:
        recorrido.append("la clave ya se usó con OTRO paquete: no se crea nada")
        id_peticion.log(f"clave repetida con otro paquete (folio original {previo['folio']})")
        return jsonify({"servicio": "pedidos",
                        "error": "esta Idempotency-Key ya se usó con un paquete distinto",
                        "folio": previo["folio"], "recorrido": recorrido}), 422
    recorrido.append(f"pedido repetido: ya existía el folio {previo['folio']}; no se creó otro")
    id_peticion.log(f"folio={previo['folio']} repetido (misma Idempotency-Key)")
    return jsonify({**con_siguientes(previo), "servicio": "pedidos", "repetido": True,
                    "recorrido": recorrido}), 200


def con_siguientes(pedido):
    """Agrega a qué estados se puede pasar desde el actual (el front arma los botones con esto)."""
    return {**pedido, "siguientes": TRANSICIONES.get(pedido["estado"], [])}


class DestinoInvalido(Exception):
    """rutas dijo que el destino no sirve (400): es un error del cliente, no se crea folio."""


def leer_json(r):
    """El cuerpo de la respuesta como dict. Si el otro servicio tronó y mandó HTML, {}."""
    try:
        cuerpo = r.json()
    except ValueError:
        return {}
    return cuerpo if isinstance(cuerpo, dict) else {}


def medir_distancia(destino):
    """Le pide a rutas los km por calle hasta el destino. Regresa (km, fuente, nota).
    Si rutas no responde, km = None. Si el destino es inválido, lanza DestinoInvalido."""
    try:
        r = requests.post(f"{RUTAS_URL}/distancia", json={"destino": destino}, timeout=8,
                          headers=id_peticion.cabeceras())
    except requests.RequestException as e:
        return None, None, f"rutas NO respondió al medir la distancia ({type(e).__name__})"
    if r.status_code == 400:
        raise DestinoInvalido(leer_json(r).get("error"))
    if r.status_code != 200:
        return None, None, f"rutas respondió {r.status_code} al medir la distancia"
    d = leer_json(r)
    if "km" not in d:
        return None, None, "rutas respondió algo inesperado al medir la distancia"
    return d["km"], d["fuente"], f"rutas midió {d['km']} km por calle ({d['fuente']})"


def consultar_clima(destino, hora):
    """Le pregunta al servicio clima por el pronóstico a la hora de salida.
    Regresa (clima, info, nota). Si falla, clima = None."""
    params = {"hora": hora}
    if destino:
        params.update(lat=destino["lat"], lng=destino["lng"])
    try:
        r = requests.get(f"{CLIMA_URL}/clima", params=params, timeout=8,
                         headers=id_peticion.cabeceras())
    except requests.RequestException as e:
        return None, None, f"clima NO respondió ({type(e).__name__})"
    d = leer_json(r)
    if r.status_code != 200 or "clima" not in d:
        return None, None, f"clima respondió {r.status_code}: {d.get('error')}"
    info = {"fuente": d.get("fuente"), "hora": d.get("hora"), "detalle": d.get("detalle")}
    return d["clima"], info, f"clima pronosticó {d['clima']} para {d.get('hora')} ({d.get('fuente')})"


def pedir_plan(medio, destino):
    """Le pide a rutas el plan de entrega. Regresa (plan, nota). Si falla, plan = None."""
    if not destino:
        return None, "sin destino: no se calculó el plan"
    try:
        r = requests.post(f"{RUTAS_URL}/plan", json={"medio": medio, "destino": destino}, timeout=8,
                          headers=id_peticion.cabeceras())
    except requests.RequestException as e:
        return None, f"rutas NO respondió ({type(e).__name__}): pedido sin plan"
    if r.status_code != 200:
        return None, f"rutas respondió {r.status_code}: {leer_json(r).get('error')}"
    plan = leer_json(r)
    # origen, destino y trazo: para dibujar el mapa de la ruta en la página.
    datos = {c: plan.get(c) for c in ("km", "minutos", "indicacion", "fuente", "aviso",
                                      "origen", "destino", "trazo")}
    return datos, f"rutas calculó el plan: {datos['minutos']} min ({datos['fuente']})"


def consultar_recomendar(paquete, modelo, recorrido):
    """Pide el medio a recomendar. Regresa (pedido, codigo, error_http).
    Si recomendar no responde: plan B. Si rechaza el paquete: error_http (sin folio)."""
    recorrido.append(f"pedidos llamó a recomendar ({modelo})")
    try:
        r = requests.post(f"{RECOMENDAR_URL}/sugerir", json=paquete, timeout=5,
                          headers=id_peticion.cabeceras())
    except requests.RequestException as e:
        falla = f"NO respondió ({type(e).__name__})"
    else:
        sugerencia = leer_json(r)
        # Si respondió pero tronó por dentro (500 o sin "medio"), es como si no respondiera.
        roto = r.status_code >= 500 or (r.status_code == 200 and "medio" not in sugerencia)
        falla = f"falló por dentro (HTTP {r.status_code})" if roto else None
    if falla:
        recorrido.append(f"recomendar {falla} → plan B")
        pedido = {"folio": nuevo_folio(), "medio": MEDIO_POR_DEFECTO, "modelo": modelo,
                  "motivo": "recomendar no estuvo disponible; se asignó el medio por defecto",
                  "plan_b": True}
        return pedido, 503, None

    if r.status_code != 200:
        recorrido.append(f"recomendar respondió {r.status_code}: {sugerencia.get('error')}")
        error = jsonify({"servicio": "pedidos", "error": "recomendar rechazó el paquete",
                         "detalle": sugerencia, "recorrido": recorrido}), r.status_code
        return None, None, error

    recorrido.append(f"recomendar sugirió {sugerencia['medio']}")
    pedido = {"folio": nuevo_folio(), "medio": sugerencia["medio"],
              "motivo": sugerencia.get("motivo") or "sin motivo",
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
    # En la lista no hace falta el trazo del mapa (50 pedidos × cientos de puntos): se quita.
    # Completo sigue en GET /pedidos/<folio>.
    for fila in filas:
        if fila["plan"]:
            fila["plan"].pop("trazo", None)
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
    return jsonify(con_siguientes(pedido))


@app.get("/operador")
def operador():
    """La página la usa para saber si la clave que escribió el operador es buena."""
    error = revisar_operador()
    return error or jsonify({"servicio": "pedidos", "operador": True})


@app.patch("/pedidos/<folio>")
def cambiar_estado(folio):
    error = revisar_operador()
    if error:
        return error
    folio = folio.strip().upper()
    datos = request.get_json(silent=True)
    nuevo = datos.get("estado") if isinstance(datos, dict) else None
    if nuevo not in TRANSICIONES:
        return jsonify({"servicio": "pedidos", "error": f"estado desconocido: {nuevo}",
                        "estados": list(TRANSICIONES)}), 400
    try:
        with conectar() as conn:
            fila = conn.execute("SELECT estado FROM pedidos WHERE folio = %s", (folio,)).fetchone()
            if fila is None:
                return jsonify({"servicio": "pedidos", "error": f"no existe el folio {folio}"}), 404
            actual = fila["estado"]
            if nuevo not in TRANSICIONES.get(actual, []):
                # 409 Conflict: la petición es válida, pero choca con el estado actual del pedido.
                return jsonify({"servicio": "pedidos", "estado": actual,
                                "error": f"no se puede pasar de {actual} a {nuevo}",
                                "siguientes": TRANSICIONES.get(actual, [])}), 409
            # "AND estado = actual": si alguien lo cambió justo antes, no se pisa su cambio.
            pedido = conn.execute(
                "UPDATE pedidos SET estado = %s, historial = historial || jsonb_build_array("
                + EVENTO + ") WHERE folio = %s AND estado = %s RETURNING " + COLUMNAS,
                (nuevo, nuevo, folio, actual),
            ).fetchone()
    except psycopg.Error:
        return jsonify({"servicio": "pedidos", "error": "la base de datos no está disponible"}), 503
    if pedido is None:
        return jsonify({"servicio": "pedidos", "error": "el pedido cambió mientras tanto; vuelve a consultarlo"}), 409
    id_peticion.log(f"folio={folio} cambió de {actual} a {nuevo}")
    return jsonify(con_siguientes(pedido))


@app.post("/pedidos")
def crear():
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        return jsonify({"servicio": "pedidos", "error": "el cuerpo debe ser JSON"}), 400

    recorrido = ["gateway recibió la petición", "pedidos recibió el paquete"]

    # 0) Validar campo por campo. Con un dato mal no se llama a nadie ni se crea folio.
    paquete, errores = validar(cuerpo)
    if errores:
        recorrido.append(f"pedidos rechazó el paquete: {len(errores)} campo(s) con error")
        return jsonify({"servicio": "pedidos", "error": "hay datos inválidos",
                        "errores": errores, "recorrido": recorrido}), 400
    recorrido.append("pedidos validó el paquete")

    # 0.5) Idempotencia: si esta clave ya creó un pedido, se regresa ese y no se llama a nadie.
    clave = request.headers.get("Idempotency-Key")
    huella = None
    if clave is not None:
        if not CLAVE_VALIDA.match(clave):
            return jsonify({"servicio": "pedidos",
                            "error": "Idempotency-Key inválida (8 a 64 letras, números o guiones)"}), 400
        huella = huella_de(cuerpo)
        try:
            previo = buscar_por_clave(clave)
        except psycopg.Error:
            return jsonify({"servicio": "pedidos", "error": "la base de datos no está disponible",
                            "recorrido": recorrido}), 503
        if previo:
            return responder_repetido(previo, huella, recorrido)
    modelo = paquete.get("modelo") or "arbol"

    # 0.8) Clima: si viene "auto" (o no viene), se consulta el pronóstico a la hora de salida.
    paquete.pop("clima_info", None)  # el origen del clima lo decide pedidos, no el cliente
    if paquete["clima"] == "auto":
        clima, info, nota = consultar_clima(paquete.get("destino"), paquete["hora_salida"])
        recorrido.append(nota)
        if clima is None:
            clima = CLIMA_SI_FALLA
            info = {"fuente": "supuesto", "aviso": nota}
            recorrido.append(f"no se pudo saber el clima: se asume {CLIMA_SI_FALLA} (prudente)")
        paquete["clima"], paquete["clima_info"] = clima, info
    else:
        paquete["clima_info"] = {"fuente": "manual"}
        recorrido.append(f"se usa el clima escrito a mano ({paquete['clima']})")

    # 1) Distancia real: la mide rutas con el destino. El modelo decide con ella.
    paquete.pop("distancia_fuente", None)  # la fuente la decide pedidos, no el cliente
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

    # 3.5) Tarifa: con los km del plan (los del medio elegido); si no hay plan, con la distancia.
    km = pedido["plan"]["km"] if pedido["plan"] else paquete.get("distancia_km")
    pedido["tarifa"] = tarifa.calcular(pedido["medio"], km, paquete)
    if pedido["tarifa"]:
        recorrido.append(f"pedidos calculó la tarifa: ${pedido['tarifa']['total']} MXN"
                         + (" (plan B, " + pedido["medio"] + ")" if pedido["plan_b"] else ""))
    else:
        recorrido.append("sin distancia: no se calculó la tarifa")

    # 4) Guardar en la base. Si la base no responde, error claro (no se inventa un folio).
    try:
        guardado = guardar(pedido, paquete, clave, huella)
    except psycopg.errors.UniqueViolation:
        # Dos peticiones con la misma clave llegaron al mismo tiempo y la otra guardó primero:
        # la base no dejó duplicar. Se regresa el pedido que sí se guardó.
        previo = buscar_por_clave(clave) if clave else None
        if previo is None:
            raise
        return responder_repetido(previo, huella, recorrido)
    except psycopg.Error:
        recorrido.append("la base de datos NO respondió: el pedido no se guardó")
        return jsonify({"servicio": "pedidos", "error": "la base de datos no está disponible",
                        "recorrido": recorrido}), 503
    recorrido.append("pedidos guardó el pedido en la base")
    id_peticion.log(f"folio={guardado['folio']} creado: {guardado['medio']}"
                    + (" (plan B)" if pedido["plan_b"] else "")
                    + (f", ${pedido['tarifa']['total']}" if pedido["tarifa"] else ""))

    respuesta = {**con_siguientes(guardado), "servicio": "pedidos", "recorrido": recorrido}
    if not pedido["plan_b"]:
        respuesta["preferido_por_modelo"] = pedido["preferido_por_modelo"]
        respuesta["corregido_por_reglas"] = pedido["corregido_por_reglas"]
    return jsonify(respuesta), codigo


# En Docker arranca gunicorn (ver gunicorn.conf.py, que también llama a crear_tabla).
# "python app.py" queda para probar en tu compu sin Docker.
if __name__ == "__main__":
    crear_tabla()
    app.run(host="0.0.0.0", port=8001)
