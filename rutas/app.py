"""
Servicio RUTAS: calcula el plan de entrega (km, minutos, indicación) desde el almacén
hasta el destino. Usa OpenRouteService para moto, camioneta y bicicleta; el dron va en
línea recta y se calcula aquí mismo. Si ORS falla, estima (plan B) y lo dice.

GET  /salud     -> quién es y si tiene clave de ORS configurada
POST /distancia -> {"destino": {...}}: km por calle (en auto) desde el almacén; la usa el modelo
POST /plan      -> {"medio": "moto", "destino": {"lat": 19.70, "lng": -101.19}}
"""
import math
import os

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.json.ensure_ascii = False  # acentos legibles en curl

ORS_URL = os.environ.get("ORS_URL", "https://api.openrouteservice.org")
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")
ALMACEN = {
    # "or": si la variable no existe o viene vacía, se usa el TecNM Morelia
    "lat": float(os.environ.get("ALMACEN_LAT") or "19.7229386"),
    "lng": float(os.environ.get("ALMACEN_LNG") or "-101.1858201"),
}
FACTOR_CALLES = 1.3  # por calles se recorre ~30 % más que en línea recta


class ErrorRuta(Exception):
    """ORS no pudo dar la ruta (caído, sin clave, sin cuota o sin camino)."""


# ---------------------------------------------------------------------------
# Adapter: ORS habla en metros, segundos y JSON propio; nosotros en km y minutos.
# ---------------------------------------------------------------------------
class ClienteORS:
    def ruta(self, perfil, origen, destino):
        if not ORS_API_KEY:
            raise ErrorRuta("no hay ORS_API_KEY configurada")
        try:
            r = requests.post(
                f"{ORS_URL}/v2/directions/{perfil}",
                json={"coordinates": [[origen["lng"], origen["lat"]],     # ORS usa [lng, lat]
                                      [destino["lng"], destino["lat"]]]},
                headers={"Authorization": ORS_API_KEY},
                timeout=5,
            )
        except requests.RequestException as e:
            raise ErrorRuta(f"ORS no respondió ({type(e).__name__})")
        if r.status_code != 200:
            raise ErrorRuta(f"ORS respondió {r.status_code}")
        try:
            resumen = r.json()["routes"][0]["summary"]
        except (ValueError, KeyError, IndexError):
            raise ErrorRuta("ORS respondió en un formato inesperado")
        # Si origen y destino son el mismo punto, ORS manda el resumen vacío.
        return resumen.get("distance", 0) / 1000, resumen.get("duration", 0) / 60  # km, minutos


ors = ClienteORS()


def linea_recta_km(a, b):
    """Distancia en línea recta sobre la Tierra (fórmula de Haversine)."""
    radio = 6371
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlng = math.radians(b["lng"] - a["lng"])
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * radio * math.asin(math.sqrt(h))


def distancia_por_calle(origen, destino):
    """Km por calle en auto (la "distancia_km" del dataset). Si ORS falla, estima."""
    try:
        km, _ = ors.ruta("driving-car", origen, destino)
        return round(km, 2), "openrouteservice", None
    except ErrorRuta as e:
        return round(linea_recta_km(origen, destino) * FACTOR_CALLES, 2), "estimado", str(e)


# ---------------------------------------------------------------------------
# Strategy: cada medio sabe planear su entrega con la misma interfaz.
# ---------------------------------------------------------------------------
class EntregaPorCalle:
    """Moto, camioneta y bicicleta: ruta real con ORS; si falla, estimación."""

    def __init__(self, perfil, velocidad_kmh, indicacion):
        self.perfil = perfil                  # perfil de ORS
        self.velocidad_kmh = velocidad_kmh    # solo para el plan B
        self.indicacion = indicacion

    def planear(self, origen, destino):
        try:
            km, minutos = ors.ruta(self.perfil, origen, destino)
            fuente, aviso = "openrouteservice", None
        except ErrorRuta as e:
            km = linea_recta_km(origen, destino) * FACTOR_CALLES
            minutos = km / self.velocidad_kmh * 60
            fuente, aviso = "estimado", str(e)
        return {"km": round(km, 2), "minutos": round(minutos), "fuente": fuente,
                "perfil": self.perfil, "indicacion": self.indicacion, "aviso": aviso}


class EntregaDron:
    """El dron vuela en línea recta: no necesita API."""

    velocidad_kmh = 70

    def planear(self, origen, destino):
        km = linea_recta_km(origen, destino)
        return {"km": round(km, 2), "minutos": round(km / self.velocidad_kmh * 60),
                "fuente": "linea_recta", "perfil": None,
                "indicacion": "vuelo en línea recta", "aviso": None}


# Fábrica simple: el texto del medio -> la estrategia que sabe planearlo.
MEDIOS = {
    # driving-car en lugar de moto: ORS no tiene perfil de motocicleta.
    "moto": EntregaPorCalle("driving-car", 35, "ruta por avenidas (perfil de auto)"),
    "camioneta": EntregaPorCalle("driving-hgv", 30, "ruta de reparto (vehículo de carga)"),
    "bicicleta": EntregaPorCalle("cycling-regular", 15, "ruta en bicicleta"),
    "dron": EntregaDron(),
}


def leer_punto(dato, nombre):
    """Valida {"lat": .., "lng": ..} y lo regresa como números. Lanza ValueError si no sirve."""
    if not isinstance(dato, dict):
        raise ValueError(f"falta {nombre} con lat y lng")
    try:
        lat, lng = float(dato["lat"]), float(dato["lng"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{nombre} debe tener lat y lng numéricos")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError(f"{nombre} tiene coordenadas fuera de rango")
    return {"lat": lat, "lng": lng}


@app.get("/salud")
def salud():
    return jsonify({"servicio": "rutas", "estado": "ok",
                    "ors_configurado": bool(ORS_API_KEY), "almacen": ALMACEN})


@app.post("/distancia")
def distancia():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"servicio": "rutas", "error": "el cuerpo debe ser JSON"}), 400
    try:
        destino = leer_punto(datos.get("destino"), "destino")
        origen = leer_punto(datos["origen"], "origen") if "origen" in datos else ALMACEN
    except ValueError as e:
        return jsonify({"servicio": "rutas", "error": str(e)}), 400

    km, fuente, aviso = distancia_por_calle(origen, destino)
    return jsonify({"servicio": "rutas", "km": km, "fuente": fuente, "aviso": aviso,
                    "origen": origen, "destino": destino})


@app.post("/plan")
def plan():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"servicio": "rutas", "error": "el cuerpo debe ser JSON"}), 400

    medio = datos.get("medio")
    if medio not in MEDIOS:
        return jsonify({"servicio": "rutas", "error": f"medio desconocido: {medio}",
                        "medios": list(MEDIOS)}), 400
    try:
        destino = leer_punto(datos.get("destino"), "destino")
        origen = leer_punto(datos["origen"], "origen") if "origen" in datos else ALMACEN
    except ValueError as e:
        return jsonify({"servicio": "rutas", "error": str(e)}), 400

    resultado = MEDIOS[medio].planear(origen, destino)
    return jsonify({"servicio": "rutas", "medio": medio, "origen": origen,
                    "destino": destino, **resultado})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003)
