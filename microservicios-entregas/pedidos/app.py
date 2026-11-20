"""
Servicio PEDIDOS: crea el pedido. NO carga el modelo: le pregunta a recomendar por HTTP.

GET  /salud    -> quién es y a qué URL llama
POST /pedidos  -> pide la sugerencia a recomendar, inventa un folio y lo guarda en memoria
GET  /pedidos  -> lista los pedidos guardados (útil para revisar)
"""
import os
import uuid

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.ensure_ascii = False  # acentos legibles en curl

# Dentro de Compose: http://recomendar:8002 (el nombre del servicio es el host).
RECOMENDAR_URL = os.environ.get("RECOMENDAR_URL", "http://localhost:8002")
MEDIO_POR_DEFECTO = "camioneta"

pedidos = []  # "base de datos" en memoria, como pide el enunciado


def nuevo_folio():
    return uuid.uuid4().hex[:8].upper()


@app.get("/salud")
def salud():
    return jsonify({"servicio": "pedidos", "estado": "ok",
                    "recomendar_url": RECOMENDAR_URL, "pedidos_en_memoria": len(pedidos)})


@app.get("/pedidos")
def listar():
    return jsonify(pedidos)


@app.post("/pedidos")
def crear():
    paquete = request.get_json(silent=True)
    if not isinstance(paquete, dict):
        return jsonify({"servicio": "pedidos", "error": "el cuerpo debe ser JSON"}), 400

    modelo = paquete.get("modelo", "arbol")
    recorrido = ["gateway recibió la petición", "pedidos recibió el paquete",
                 f"pedidos llamó a recomendar ({modelo})"]

    # Llamada por la red a recomendar. Si falla, NO se cae pedidos: plan B.
    try:
        r = requests.post(f"{RECOMENDAR_URL}/sugerir", json=paquete, timeout=5)
    except requests.RequestException as e:
        folio = nuevo_folio()
        pedido = {"folio": folio, "medio": MEDIO_POR_DEFECTO, "modelo": modelo,
                  "motivo": "recomendar no estuvo disponible; se asignó el medio por defecto",
                  "plan_b": True}
        pedidos.append(pedido)
        recorrido.append(f"recomendar NO respondió ({type(e).__name__}) → plan B")
        return jsonify({**pedido, "servicio": "pedidos", "recorrido": recorrido}), 503

    sugerencia = r.json()
    if r.status_code != 200:
        # Recomendar sí respondió, pero rechazó el paquete (faltan campos, modelo inexistente...)
        recorrido.append(f"recomendar respondió {r.status_code}: {sugerencia.get('error')}")
        return jsonify({"servicio": "pedidos", "error": "recomendar rechazó el paquete",
                        "detalle": sugerencia, "recorrido": recorrido}), r.status_code

    folio = nuevo_folio()
    pedido = {"folio": folio, "medio": sugerencia["medio"], "motivo": sugerencia["motivo"],
              "modelo": sugerencia.get("modelo", modelo), "plan_b": False}
    pedidos.append(pedido)
    recorrido.append(f"recomendar sugirió {sugerencia['medio']}")
    return jsonify({**pedido, "servicio": "pedidos",
                    "preferido_por_modelo": sugerencia.get("preferido_por_modelo"),
                    "corregido_por_reglas": sugerencia.get("corregido_por_reglas"),
                    "recorrido": recorrido}), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001)