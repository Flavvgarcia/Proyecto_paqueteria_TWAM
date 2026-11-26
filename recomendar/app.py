'''
    Sevicio de recomendar: solo recomienda el medio, no crea folios ni guarda pedidos

    GET  /salud    -> {"servicio": "recomendar", "estado": "ok"}
    POST /sugerir  -> recibe el paquete (14 campos + "modelo") y responde la sugerencia
'''
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from flask import Flask, jsonify, request

import id_peticion

from reglas import es_posible


app = Flask(__name__)
app.json.ensure_ascii = False
id_peticion.instalar(app, "recomendar")

CARPETA_MODELOS = Path(__file__).resolve().parent / "modelo"

MODELOS = {
    "arbol": ("modelo_medios.joblib", "árbol de decisión"),
    "bosque": ("modelo_bosque.joblib", "random forest"),
    "red": ("modelo_red.joblib", "red neuronal"),
}

CAMPOS_NUMERICOS = [
    "distancia_km", "peso_kg", "largo_cm", "ancho_cm", "alto_cm", "volumen_l",
    "fragil", "refrigerado", "valor_declarado_mxn", "hora_salida",
]

CAMPOS_TEXTO = ["prioridad", "zona_destino", "clima", "trafico"]

CAMPOS = CAMPOS_NUMERICOS + CAMPOS_TEXTO

@lru_cache(maxsize=3)
def cargar_modelo(key):
    """Cargamos el modelo solo una vez y lo reutiliza"""
    archivo,_=MODELOS[key]
    ruta=CARPETA_MODELOS / archivo
    if not ruta.exists():
        raise FileNotFoundError(f"No esta el archivo {archivo} en recomendar/modelo/")
    return joblib.load(ruta)


@app.get("/salud")
def salud():
    return jsonify({"servicio":"recomendar", "estado":"ok", "modelos": list(MODELOS)})

@app.post("/sugerir")
def sugerir():
    paquete = request.get_json(silent=True)
    if not isinstance(paquete, dict):
        return jsonify({"servicio": "recomendar", "error": "El cuerpo debe ser JSON"}), 400

    #1 Que modelo vamos a usar? esto nos lo dice el paquete
    model = paquete.pop("modelo", "arbol") or "arbol" # si no mandan modelo, se usa el árbol
    if model not in MODELOS:
        return jsonify({"servicio": "recomendar", "error": f"Modelo desconocido {model}", "modelos": list(MODELOS)}), 400

    #2 Validando campos
    faltantes = [c for c in CAMPOS if c not in paquete]
    if faltantes:
        return jsonify({"servicio": "recomendar", "error": "Faltan campos", "campos": faltantes}), 400

    try:
        for c in CAMPOS_NUMERICOS:
            paquete[c] = float(paquete[c])
    except(TypeError, ValueError):
        return jsonify({"servicio": "recomendar", "error": f"el campo {c} debe ser un número"}), 400

    #3 Cargamos el modelo, pero si no esta el modelo, error claro
    try:
        modelo = cargar_modelo(model)
    except FileNotFoundError as e:
        return jsonify({"servicio": "recomendar", "error": str(e), "modelo": model}), 503

    #4 El modelo da probabilidades -> ranking de mas a menos probable
    datos = pd.DataFrame([paquete], columns=CAMPOS)
    probabilidades = modelo.predict_proba(datos)[0]
    ranking = sorted(zip(modelo.classes_, probabilidades), key=lambda par: -par[1])
    preferido = str(ranking[0][0])

    # 5) Las reglas del negocio descartan lo imposible
    medio, confianza = "camioneta", 0.0
    for candidato, p in ranking:
        if es_posible(candidato, paquete):
            medio, confianza = str(candidato), float(p)
            break

    # Alternativas: todos los medios que SÍ cumplen las reglas, en orden de preferencia
    # del modelo. Si no hay vehículos del primero, la flota prueba con el siguiente.
    alternativas = [str(m) for m, _ in ranking if es_posible(m, paquete)]
    if medio not in alternativas:
        alternativas.insert(0, medio)

    nombre = MODELOS[model][1]
    motivo = f"{nombre}, confianza {confianza:.0%}"
    if medio != preferido:
        motivo += f"; se descartó {preferido} por las reglas del negocio"

    return jsonify({
        "servicio": "recomendar",
        "modelo": model,
        "medio": medio,
        "motivo": motivo,
        "preferido_por_modelo": preferido,
        "corregido_por_reglas": medio != preferido,
        "alternativas": alternativas,
        "ranking": [{"medio": str(m), "confianza": round(float(p), 3)} for m, p in ranking],
    })


# Paquete de ejemplo (el de paquete.json) para "calentar" cada modelo al arrancar.
EJEMPLO = {
    "distancia_km": 3.94, "peso_kg": 0.31, "largo_cm": 11.7, "ancho_cm": 7.6, "alto_cm": 10.6,
    "volumen_l": 0.94, "fragil": 0, "refrigerado": 0, "valor_declarado_mxn": 4603,
    "hora_salida": 3, "prioridad": "mismo_dia", "zona_destino": "periferia",
    "clima": "despejado", "trafico": "medio",
}


def precargar():
    """Carga los modelos al arrancar y hace una predicción de prueba con cada uno.
    Cargar el archivo no basta: scikit-learn termina de prepararse en la PRIMERA
    predicción (~2 s). Así esa espera ocurre aquí y no en el primer pedido de un cliente."""
    for model in MODELOS:
        try:
            modelo = cargar_modelo(model)
        except FileNotFoundError as e:
            print("Aviso:", e)
            continue
        try:
            modelo.predict_proba(pd.DataFrame([EJEMPLO], columns=CAMPOS))
            print(f"Modelo {model} listo (calentado)", flush=True)
        except Exception as e:  # el calentamiento nunca debe impedir que el servicio arranque
            print(f"Aviso: no se pudo calentar {model}: {e}", flush=True)


# En Docker arranca gunicorn (ver gunicorn.conf.py, que llama a precargar).
# "python app.py" queda para probar en tu compu sin Docker.
if __name__ == "__main__":
    precargar()
    app.run(host="0.0.0.0", port=8002)