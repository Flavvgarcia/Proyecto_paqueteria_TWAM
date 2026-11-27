"""
Servicio RUTAS: calcula el plan de entrega (km, minutos, indicación) desde el almacén
hasta el destino. Usa OpenRouteService para moto, camioneta y bicicleta; el dron va en
línea recta y se calcula aquí mismo. Si ORS falla, estima (plan B) y lo dice.

GET  /salud     -> quién es y si tiene clave de ORS configurada
POST /distancia -> {"destino": {...}}: km por calle (en auto) desde el almacén; la usa el modelo
POST /plan      -> {"medio": "moto", "destino": {"lat": 19.70, "lng": -101.19}}
POST /recorrido -> {"medio": "moto", "paradas": [{"id": "A1B2", "lat": .., "lng": ..}, ...]}
                   orden de entrega de varias paradas (vecino más cercano + 2-opt)
"""
import math
import os
import re

import requests
from flask import Flask, jsonify, request

from recorrido import costo_ruta, ordenar

import id_peticion

app = Flask(__name__)
app.json.ensure_ascii = False  # acentos legibles en curl
id_peticion.instalar(app, "rutas")

# ORS se mudó: api.openrouteservice.org quedó obsoleto (responde 410 "Deprecated") y se
# apaga en noviembre de 2026. La dirección nueva es api.heigit.org/openrouteservice y
# acepta la misma clave. "or": si ORS_URL viene vacía, se usa la nueva.
ORS_URL = os.environ.get("ORS_URL") or "https://api.heigit.org/openrouteservice"
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
MAX_PUNTOS = 300  # el trazo de una ruta larga puede traer miles de puntos: se recorta


def simplificar(puntos, maximo=MAX_PUNTOS):
    """Se queda con ~maximo puntos repartidos (siempre con el primero y el último)
    y redondea a 5 decimales (~1 m): el mapa se ve igual y el pedido pesa mucho menos."""
    if len(puntos) > maximo:
        paso = len(puntos) / (maximo - 1)
        puntos = [puntos[int(i * paso)] for i in range(maximo - 1)] + [puntos[-1]]
    return [[round(lat, 5), round(lng, 5)] for lat, lng in puntos]


def decodificar_polyline(texto, precision=5):
    """ORS (en formato JSON) manda el trazo comprimido como "encoded polyline" (el
    algoritmo de Google): cada coordenada va como diferencia con la anterior, en grupos
    de 5 bits convertidos a letras. Aquí se regresa a una lista de (lat, lng)."""
    puntos, i, lat, lng = [], 0, 0, 0
    factor = 10 ** precision
    while i < len(texto):
        deltas = []
        for _ in range(2):                      # primero lat, luego lng
            resultado, desplazamiento = 0, 0
            while True:
                b = ord(texto[i]) - 63
                i += 1
                resultado |= (b & 0x1F) << desplazamiento
                desplazamiento += 5
                if b < 0x20:                    # sin el bit de "continúa": fin del número
                    break
            deltas.append(~(resultado >> 1) if resultado & 1 else resultado >> 1)
        lat += deltas[0]
        lng += deltas[1]
        puntos.append((lat / factor, lng / factor))
    return puntos


def linea_recta(origen, destino):
    """Trazo de dos puntos: para el dron y para cuando ORS no responde."""
    return [[origen["lat"], origen["lng"]], [destino["lat"], destino["lng"]]]


class ClienteORS:
    def _post(self, ruta, cuerpo):
        """POST a ORS con la clave. Regresa el JSON o lanza ErrorRuta con el motivo."""
        if not ORS_API_KEY:
            raise ErrorRuta("no hay ORS_API_KEY configurada")
        try:
            r = requests.post(f"{ORS_URL}{ruta}", json=cuerpo,
                              headers={"Authorization": ORS_API_KEY}, timeout=8)
        except requests.RequestException as e:
            raise ErrorRuta(f"ORS no respondió ({type(e).__name__})")
        if r.status_code != 200:
            # Se incluye el motivo: ORS suele explicarlo en la respuesta. Si es una página
            # HTML, basta con su título; si no, el inicio del texto.
            titulo = re.search(r"<title>(.*?)</title>", r.text, re.S | re.I)
            motivo = " ".join((titulo.group(1) if titulo else r.text[:120]).split())
            raise ErrorRuta(f"ORS respondió {r.status_code}: {motivo}")
        try:
            return r.json()
        except ValueError:
            raise ErrorRuta("ORS respondió en un formato inesperado")

    def ruta(self, perfil, origen, destino):
        """Regresa (km, minutos, trazo). trazo = [[lat, lng], ...] listo para Leaflet."""
        km, minutos, trazo, _ = self.ruta_por_paradas(perfil, [origen, destino])
        return km, minutos, trazo

    def ruta_por_paradas(self, perfil, puntos, max_puntos=MAX_PUNTOS):
        """Ruta que pasa por `puntos` EN ESE ORDEN. Regresa (km, minutos, trazo, tramos),
        tramos = [(km, minutos), ...] de cada punto al siguiente."""
        datos = self._post(f"/v2/directions/{perfil}",
                           {"coordinates": [[p["lng"], p["lat"]] for p in puntos]})  # ORS usa [lng, lat]
        try:
            ruta = datos["routes"][0]
            resumen = ruta["summary"]
            # Un "segment" por tramo entre puntos consecutivos.
            tramos = [(s.get("distance", 0) / 1000, s.get("duration", 0) / 60)
                      for s in ruta.get("segments", [])]
        except (KeyError, IndexError, TypeError):
            raise ErrorRuta("ORS respondió en un formato inesperado")
        # El trazo viene comprimido (encoded polyline): se descomprime a [(lat, lng), ...],
        # justo el orden que usa Leaflet. Traducir formatos es el trabajo del Adapter.
        # Si el trazo no viene o no se puede leer, se dibuja línea recta, pero los km y
        # minutos de ORS (lo importante) se conservan.
        try:
            trazo = simplificar(decodificar_polyline(ruta["geometry"]), max_puntos)
        except (KeyError, IndexError, TypeError):
            trazo = [[p["lat"], p["lng"]] for p in puntos]
        # Si origen y destino son el mismo punto, ORS manda el resumen vacío.
        return resumen.get("distance", 0) / 1000, resumen.get("duration", 0) / 60, trazo, tramos

    def matriz(self, perfil, puntos):
        """Matriz de km y minutos entre todos los puntos (ORS hace un Dijkstra por par).
        Regresa (km[i][j], minutos[i][j]); None donde no hay camino."""
        datos = self._post(f"/v2/matrix/{perfil}",
                           {"locations": [[p["lng"], p["lat"]] for p in puntos],
                            "metrics": ["distance", "duration"]})
        try:
            km = [[None if d is None else d / 1000 for d in fila] for fila in datos["distances"]]
            minutos = [[None if d is None else d / 60 for d in fila] for fila in datos["durations"]]
        except (KeyError, TypeError):
            raise ErrorRuta("ORS respondió en un formato inesperado")
        if len(km) != len(puntos):
            raise ErrorRuta("ORS regresó una matriz de otro tamaño")
        return km, minutos


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
        km, _, _ = ors.ruta("driving-car", origen, destino)
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
            km, minutos, trazo = ors.ruta(self.perfil, origen, destino)
            fuente, aviso = "openrouteservice", None
        except ErrorRuta as e:
            km = linea_recta_km(origen, destino) * FACTOR_CALLES
            minutos = km / self.velocidad_kmh * 60
            trazo = linea_recta(origen, destino)   # el mapa la dibuja punteada
            fuente, aviso = "estimado", str(e)
        return {"km": round(km, 2), "minutos": round(minutos), "fuente": fuente,
                "perfil": self.perfil, "indicacion": self.indicacion, "aviso": aviso,
                "trazo": trazo}


class EntregaDron:
    """El dron vuela en línea recta: no necesita API."""

    velocidad_kmh = 70

    def planear(self, origen, destino):
        km = linea_recta_km(origen, destino)
        return {"km": round(km, 2), "minutos": round(km / self.velocidad_kmh * 60),
                "fuente": "linea_recta", "perfil": None,
                "indicacion": "vuelo en línea recta", "aviso": None,
                "trazo": linea_recta(origen, destino)}


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


MAX_PARADAS = 25


def matriz_estimada(puntos, velocidad_kmh, factor):
    """Plan B (o el dron): km en línea recta × factor, minutos a velocidad fija."""
    km = [[linea_recta_km(a, b) * factor for b in puntos] for a in puntos]
    return km, [[k / velocidad_kmh * 60 for k in fila] for fila in km]


@app.post("/recorrido")
def recorrido():
    """Orden de entrega de varias paradas para UN vehículo.
    {"medio": "moto", "paradas": [{"id": "A1B2C3D4", "lat": .., "lng": ..}, ...], "regresar": false}"""
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"servicio": "rutas", "error": "el cuerpo debe ser JSON"}), 400
    medio = datos.get("medio")
    if medio not in MEDIOS:
        return jsonify({"servicio": "rutas", "error": f"medio desconocido: {medio}",
                        "medios": list(MEDIOS)}), 400
    paradas = datos.get("paradas")
    if not isinstance(paradas, list) or not 1 <= len(paradas) <= MAX_PARADAS:
        return jsonify({"servicio": "rutas", "error": f"paradas debe ser una lista de 1 a {MAX_PARADAS}"}), 400
    try:
        puntos = [leer_punto(datos["origen"], "origen") if "origen" in datos else ALMACEN]
        ids = []
        for i, p in enumerate(paradas):
            puntos.append(leer_punto(p, f"parada {i + 1}"))
            ids.append(str(p.get("id", i + 1)))
    except ValueError as e:
        return jsonify({"servicio": "rutas", "error": str(e)}), 400
    regresar = bool(datos.get("regresar", False))

    # 1) Matriz de costos entre todos los puntos (0 = almacén). Calle por calle con ORS;
    #    el dron, o si ORS falla: línea recta (× FACTOR_CALLES si es por calle).
    estrategia, aviso = MEDIOS[medio], None
    if isinstance(estrategia, EntregaPorCalle):
        try:
            km, minutos = ors.matriz(estrategia.perfil, puntos)
            fuente = "openrouteservice"
            # Si ORS no encontró camino entre dos puntos, esa celda se estima.
            km_est, min_est = matriz_estimada(puntos, estrategia.velocidad_kmh, FACTOR_CALLES)
            km = [[k if k is not None else e for k, e in zip(f, fe)] for f, fe in zip(km, km_est)]
            minutos = [[m if m is not None else e for m, e in zip(f, fe)] for f, fe in zip(minutos, min_est)]
        except ErrorRuta as e:
            km, minutos = matriz_estimada(puntos, estrategia.velocidad_kmh, FACTOR_CALLES)
            fuente, aviso = "estimado", str(e)
    else:
        km, minutos = matriz_estimada(puntos, estrategia.velocidad_kmh, 1)
        fuente = "linea_recta"

    # 2) Orden: vecino más cercano + 2-opt sobre los km.
    orden = ordenar(km, regresar)
    sin_optimizar = costo_ruta(list(range(1, len(puntos))), km, regresar)

    # 3) Trazo y tramos en el orden elegido. Con ORS, la ruta real por todas las paradas.
    secuencia = [0] + orden + ([0] if regresar else [])
    tramos = [(km[a][b], minutos[a][b]) for a, b in zip(secuencia, secuencia[1:])]
    trazo = [[puntos[i]["lat"], puntos[i]["lng"]] for i in secuencia]
    if fuente == "openrouteservice":
        try:
            _, _, trazo, tramos_ors = ors.ruta_por_paradas(
                estrategia.perfil, [puntos[i] for i in secuencia], max_puntos=600)
            if len(tramos_ors) == len(tramos):
                tramos = tramos_ors
        except ErrorRuta as e:
            aviso = f"trazo en línea recta: {e}"   # el orden y los km de la matriz siguen siendo buenos

    # 4) Cada parada con su número, lo que cuesta llegar desde la anterior y lo acumulado.
    resultado, km_acum, min_acum = [], 0, 0
    for n, (i, (k, m)) in enumerate(zip(orden, tramos), start=1):
        km_acum += k
        min_acum += m
        resultado.append({"id": ids[i - 1], "orden": n, "lat": puntos[i]["lat"], "lng": puntos[i]["lng"],
                          "km_tramo": round(k, 2), "min_tramo": round(m),
                          "km_acumulado": round(km_acum, 2), "min_acumulado": round(min_acum)})
    return jsonify({
        "servicio": "rutas", "medio": medio, "metodo": "vecino más cercano + 2-opt",
        "fuente": fuente, "aviso": aviso, "regresa_al_almacen": regresar,
        "origen": puntos[0], "paradas": resultado,
        "km": round(sum(k for k, _ in tramos), 2), "minutos": round(sum(m for _, m in tramos)),
        "km_en_el_orden_recibido": round(sin_optimizar, 2),
        "trazo": trazo,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8003)
