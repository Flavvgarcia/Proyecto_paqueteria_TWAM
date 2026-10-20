# Reglas del negocio. Viven aparte del modelo de IA: si mañana se cambia
# el árbol por otro modelo o por un proveedor externo, las reglas no cambian.


# Regla sencilla que usan /cotizar/ (solo km y kg).
def elegir_medio(km, kg):
    if kg > 20:
        return "camioneta", "paquete pesado"
    elif km <= 3:
        return "bicicleta", "distancia corta"
    elif km <= 15:
        return "moto", "distancia media"
    else:
        return "camioneta", "distancia larga"


# Límites que ningún modelo puede saltarse. El modelo aprende de ejemplos y
# a veces se equivoca; estas reglas vienen del negocio y no se negocian.
LIMITES = {
    "bicicleta": {"peso_kg": 8, "volumen_l": 40, "distancia_km": 7},
    "moto": {"peso_kg": 25, "volumen_l": 90, "distancia_km": 40},
    "camioneta": {"peso_kg": 1000, "volumen_l": 3000, "distancia_km": 1000},
    "dron": {"peso_kg": 2.5, "volumen_l": 12, "distancia_km": 15},
}


def es_posible(medio, paquete):
    limite = LIMITES[medio]
    if paquete["peso_kg"] > limite["peso_kg"]:
        return False
    if paquete["volumen_l"] > limite["volumen_l"]:
        return False
    if paquete["distancia_km"] > limite["distancia_km"]:
        return False
    if paquete["refrigerado"] and medio != "camioneta":
        return False
    noche = paquete["hora_salida"] >= 21 or paquete["hora_salida"] < 6
    if medio == "dron" and (
        paquete["clima"] != "despejado"
        or noche
        or paquete["zona_destino"] == "centro"
    ):
        return False
    if medio == "bicicleta" and paquete["zona_destino"] == "rural":
        return False
    return True
