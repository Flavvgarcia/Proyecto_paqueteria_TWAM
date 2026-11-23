"""
Validación del paquete, campo por campo, ANTES de llamar a otros servicios.

Pedidos es la puerta de entrada: si un dato viene mal, se responde 400 con TODOS los
errores juntos ({"peso_kg": "debe ser mayor que 0", ...}) y no se gasta ni una
llamada a rutas o a recomendar.

Los máximos salen de la camioneta (recomendar/reglas.py): si ni la camioneta puede
llevarlo, ningún medio puede.
"""
import math

# campo -> (mínimo, máximo, ¿el mínimo se permite?)
NUMEROS = {
    "peso_kg": (0, 1000, False),             # 0 kg no es un paquete
    "largo_cm": (0, 500, False),
    "ancho_cm": (0, 500, False),
    "alto_cm": (0, 500, False),
    "volumen_l": (0, 3000, False),
    "valor_declarado_mxn": (0, 10_000_000, True),
    "distancia_km": (0, 1000, False),
}
ENTEROS = {"hora_salida": (0, 23)}
CASILLAS = ["fragil", "refrigerado"]          # 0/1 (o true/false)
OPCIONES = {
    "prioridad": ["normal", "express", "mismo_dia"],
    "zona_destino": ["centro", "residencial", "periferia", "rural"],
    "clima": ["despejado", "lluvia", "viento_fuerte"],
    "trafico": ["bajo", "medio", "alto"],
    "modelo": ["arbol", "bosque", "red"],
}
# Opcionales: la distancia la mide rutas, el volumen se calcula, el modelo tiene default.
OPCIONALES = {"distancia_km", "volumen_l", "modelo", "destino"}


def a_numero(valor):
    """float(valor) solo si es un número de verdad (no "abc", no true, no NaN)."""
    if isinstance(valor, bool):
        raise ValueError
    if isinstance(valor, str):
        valor = valor.strip()
    numero = float(valor)            # lanza ValueError / TypeError si no se puede
    if not math.isfinite(numero):
        raise ValueError
    return numero


def validar(paquete):
    """Regresa (paquete_limpio, errores). Si errores está vacío, el paquete está bien."""
    limpio = dict(paquete)
    errores = {}

    obligatorios = (list(NUMEROS) + list(ENTEROS) + CASILLAS + list(OPCIONES))
    for campo in obligatorios:
        if campo not in OPCIONALES and paquete.get(campo) in (None, ""):
            errores[campo] = "es obligatorio"

    for campo, (minimo, maximo, incluye_minimo) in NUMEROS.items():
        if campo in errores or paquete.get(campo) in (None, ""):
            continue
        try:
            n = a_numero(paquete[campo])
        except (TypeError, ValueError):
            errores[campo] = "debe ser un número"
            continue
        if n < minimo or (n == minimo and not incluye_minimo):
            errores[campo] = f"debe ser mayor {'o igual ' if incluye_minimo else ''}que {minimo}"
        elif n > maximo:
            errores[campo] = f"no puede pasar de {maximo:,}"
        else:
            limpio[campo] = n

    for campo, (minimo, maximo) in ENTEROS.items():
        if campo in errores:
            continue
        try:
            n = a_numero(paquete[campo])
        except (TypeError, ValueError):
            errores[campo] = "debe ser un número entero"
            continue
        if n != int(n) or not minimo <= n <= maximo:
            errores[campo] = f"debe ser un entero de {minimo} a {maximo}"
        else:
            limpio[campo] = int(n)

    for campo in CASILLAS:
        if campo in errores:
            continue
        valor = paquete[campo]
        if valor in (0, 1) or isinstance(valor, bool):   # True == 1 y False == 0
            limpio[campo] = int(valor)
        else:
            errores[campo] = "debe ser 0 o 1"

    for campo, permitidas in OPCIONES.items():
        if campo in errores or campo not in paquete:
            continue
        if paquete[campo] not in permitidas:
            errores[campo] = "debe ser una de: " + ", ".join(permitidas)

    # Destino: si viene, lat y lng numéricos y en rango (rutas lo vuelve a revisar).
    if paquete.get("destino") is not None:
        d = paquete["destino"]
        try:
            lat, lng = a_numero(d["lat"]), a_numero(d["lng"])
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                errores["destino"] = "coordenadas fuera de rango"
            else:
                limpio["destino"] = {"lat": lat, "lng": lng}
        except (TypeError, ValueError, KeyError):
            errores["destino"] = "debe tener lat y lng numéricos"

    # Volumen: si no viene, se calcula con las medidas (cm³ / 1000 = litros).
    if paquete.get("volumen_l") in (None, "") and not errores.keys() & {"largo_cm", "ancho_cm", "alto_cm"}:
        limpio["volumen_l"] = round(limpio["largo_cm"] * limpio["ancho_cm"] * limpio["alto_cm"] / 1000, 2)

    # Sin destino, la distancia escrita a mano es la única forma de decidir.
    if paquete.get("destino") is None and paquete.get("distancia_km") in (None, ""):
        errores.setdefault("distancia_km", "es obligatoria si no hay destino")

    return limpio, errores
