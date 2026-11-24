"""
Tarifa estimada del envío, con su desglose.

    total = (banderazo + km × precio_km + extras) × prioridad  +  seguro
            └──────────── servicio ────────────┘                 └ no se multiplica:
                                                                   depende del valor
                                                                   del paquete, no de
                                                                   la urgencia

Los precios están en tablas aparte de la fórmula: para cambiarlos no se toca la lógica.
Vive dentro de pedidos (no es un microservicio) porque es una fórmula: no tiene base
propia, no llama a nadie y no tarda.
"""

# Precios en pesos mexicanos.
PRECIOS = {
    #            banderazo  por km
    "bicicleta": (35,        6),
    "moto":      (45,        8),
    "dron":      (80,       12),
    "camioneta": (90,       12),
}
MULTIPLICADOR = {"normal": 1.0, "express": 1.3, "mismo_dia": 1.6}
EXTRA_FRAGIL = 25
EXTRA_REFRIGERADO = 60
PESO_INCLUIDO_KG = 5      # los primeros 5 kg van incluidos
POR_KG_EXTRA = 2
SEGURO = 0.005            # 0.5 % del valor declarado
MINIMO = 50


def _dinero(monto):
    return round(monto, 2)


def calcular(medio, km, paquete):
    """Regresa {"total", "moneda", "conceptos", ...} o None si el medio no tiene precio."""
    if medio not in PRECIOS or km is None:
        return None
    banderazo, por_km = PRECIOS[medio]
    km = round(float(km), 2)

    conceptos = [
        {"concepto": f"Banderazo {medio}", "monto": banderazo},
        {"concepto": f"{km} km × ${por_km}", "monto": _dinero(km * por_km)},
    ]
    kg_extra = paquete["peso_kg"] - PESO_INCLUIDO_KG
    if kg_extra > 0:
        conceptos.append({"concepto": f"Peso extra: {round(kg_extra, 2)} kg × ${POR_KG_EXTRA}",
                          "monto": _dinero(kg_extra * POR_KG_EXTRA)})
    if paquete.get("fragil"):
        conceptos.append({"concepto": "Frágil", "monto": EXTRA_FRAGIL})
    if paquete.get("refrigerado"):
        conceptos.append({"concepto": "Refrigerado", "monto": EXTRA_REFRIGERADO})

    servicio = _dinero(sum(c["monto"] for c in conceptos))
    prioridad = paquete.get("prioridad", "normal")
    factor = MULTIPLICADOR.get(prioridad, 1.0)
    seguro = _dinero(paquete["valor_declarado_mxn"] * SEGURO)

    calculado = servicio * factor + seguro
    total = max(MINIMO, round(calculado))
    return {
        "total": total,
        "moneda": "MXN",
        "conceptos": conceptos,
        "servicio": servicio,
        "prioridad": prioridad,
        "multiplicador": factor,
        "seguro": seguro,
        "km": km,
        "minimo_aplicado": total == MINIMO and calculado < MINIMO,
    }
