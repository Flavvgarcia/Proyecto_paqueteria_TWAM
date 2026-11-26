"""
Servicio CLIMA: dice qué clima habrá A LA HORA DE SALIDA del pedido, en las tres
categorías que entiende el modelo (despejado / lluvia / viento_fuerte).

Usa el pronóstico por hora de Open-Meteo (gratis, sin clave) y lo guarda en caché
1 hora por zona: como mucho ~24 consultas al día aunque haya cientos de pedidos.

GET /salud
GET /clima?hora=15&lat=19.70&lng=-101.19   (sin lat/lng: el almacén)
    -> {"clima": "lluvia", "fuente": "open-meteo", "hora": "2026-11-24T15:00", ...}
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request

import id_peticion

app = Flask(__name__)
app.json.ensure_ascii = False
id_peticion.instalar(app, "clima")

OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL") or "https://api.open-meteo.com/v1/forecast"
CACHE_MINUTOS = int(os.environ.get("CLIMA_CACHE_MINUTOS") or 60)
ALMACEN = {
    "lat": float(os.environ.get("ALMACEN_LAT") or "19.7229386"),
    "lng": float(os.environ.get("ALMACEN_LNG") or "-101.1858201"),
}

# Códigos WMO que usa Open-Meteo: llovizna (51-57), lluvia (61-67, 80-82),
# nieve (71-77, 85-86) y tormenta (95-99). Para entregar, todos cuentan como "lluvia".
CODIGOS_LLUVIA = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75, 77,
                  80, 81, 82, 85, 86, 95, 96, 97, 99}
LLUVIA_MM = 0.2          # mm en la hora: a partir de aquí ya moja
VIENTO_KMH = 35          # viento sostenido que ya complica volar un dron o ir en bici
RAFAGAS_KMH = 50


class ErrorClima(Exception):
    """Open-Meteo no respondió o respondió algo que no se entiende."""


# ---------------------------------------------------------------------------
# Caché: zona (lat/lng a 2 decimales, ~1 km) -> (cuándo caduca, pronóstico)
# Con hilos, dos peticiones podrían tocarla a la vez: por eso el Lock.
# ---------------------------------------------------------------------------
_cache = {}
_candado = threading.Lock()


def pronostico(lat, lng):
    """Pronóstico por hora de hoy y mañana. Regresa (datos, salio_de_cache)."""
    zona = (round(lat, 2), round(lng, 2))
    with _candado:
        guardado = _cache.get(zona)
        if guardado and guardado[0] > time.time():
            return guardado[1], True
    try:
        r = requests.get(OPEN_METEO_URL, timeout=5, params={
            "latitude": zona[0], "longitude": zona[1],
            "hourly": "precipitation,weather_code,wind_speed_10m,wind_gusts_10m",
            "timezone": "America/Mexico_City",
            "forecast_days": 2,
        })
    except requests.RequestException as e:
        raise ErrorClima(f"Open-Meteo no respondió ({type(e).__name__})")
    if r.status_code != 200:
        raise ErrorClima(f"Open-Meteo respondió {r.status_code}")
    try:
        datos = r.json()
        datos["hourly"]["time"]          # comprobar que trae lo que se necesita
        int(datos["utc_offset_seconds"])
    except (ValueError, KeyError, TypeError):
        raise ErrorClima("Open-Meteo respondió en un formato inesperado")
    with _candado:
        _cache[zona] = (time.time() + CACHE_MINUTOS * 60, datos)
    return datos, False


def categoria(lluvia_mm, codigo, viento_kmh, rafagas_kmh):
    """Traduce el pronóstico a las categorías del modelo. La lluvia pesa más que el viento."""
    if (lluvia_mm or 0) >= LLUVIA_MM or codigo in CODIGOS_LLUVIA:
        return "lluvia"
    if (viento_kmh or 0) >= VIENTO_KMH or (rafagas_kmh or 0) >= RAFAGAS_KMH:
        return "viento_fuerte"
    return "despejado"


def clima_a_la_hora(lat, lng, hora):
    """Clima a la hora de salida: hoy si esa hora no ha pasado; si ya pasó, mañana."""
    datos, de_cache = pronostico(lat, lng)
    # Hora local de Morelia sin depender de la zona horaria del contenedor:
    # Open-Meteo dice cuántos segundos está desfasada de UTC.
    ahora = datetime.now(timezone.utc) + timedelta(seconds=int(datos["utc_offset_seconds"]))
    dia = ahora.date() if hora >= ahora.hour else ahora.date() + timedelta(days=1)
    buscada = f"{dia.isoformat()}T{hora:02d}:00"
    horas = datos["hourly"]
    try:
        i = horas["time"].index(buscada)
        detalle = {
            "lluvia_mm": horas["precipitation"][i],
            "codigo": horas["weather_code"][i],
            "viento_kmh": horas["wind_speed_10m"][i],
            "rafagas_kmh": horas["wind_gusts_10m"][i],
        }
    except (ValueError, KeyError, IndexError):
        raise ErrorClima(f"el pronóstico no trae la hora {buscada}")
    return {"clima": categoria(**detalle), "hora": buscada, "detalle": detalle,
            "cache": de_cache}


@app.get("/salud")
def salud():
    return jsonify({"servicio": "clima", "estado": "ok", "fuente": "open-meteo",
                    "zonas_en_cache": len(_cache), "cache_minutos": CACHE_MINUTOS})


@app.get("/clima")
def clima():
    try:
        hora = int(request.args["hora"])
        if not 0 <= hora <= 23:
            raise ValueError
        lat = float(request.args.get("lat", ALMACEN["lat"]))
        lng = float(request.args.get("lng", ALMACEN["lng"]))
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError
    except (KeyError, ValueError):
        return jsonify({"servicio": "clima",
                        "error": "se necesita hora (0-23) y, opcional, lat y lng válidas"}), 400
    try:
        resultado = clima_a_la_hora(lat, lng, hora)
    except ErrorClima as e:
        # 503: el servicio está vivo, pero su fuente no; quien llama decide el plan B.
        return jsonify({"servicio": "clima", "error": str(e)}), 503
    id_peticion.log(f"clima {resultado['hora']}: {resultado['clima']}"
                    + (" (caché)" if resultado["cache"] else " (Open-Meteo)"))
    return jsonify({"servicio": "clima", "fuente": "open-meteo", **resultado})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8004)
