"""
Orden de paradas de un vehículo con varios pedidos (el "agente viajero", TSP).

Encontrar el orden PERFECTO es NP-difícil (con 10 paradas hay 3.6 millones de órdenes),
así que se usa una heurística en dos pasos, que da una ruta buena en milisegundos:

  1. Vecino más cercano: desde el almacén, ir siempre a la parada pendiente más cercana.
     Rápido, pero a veces deja cruces (la ruta se "enreda").
  2. 2-opt: probar invertir cada tramo de la ruta; si la invertida es más corta, se queda.
     Repetir hasta que ningún cambio mejore. Invertir un tramo = deshacer un cruce.

Todo trabaja sobre una MATRIZ de costos: costo[i][j] = cuánto cuesta ir del punto i al j
(metros o segundos). El punto 0 es el almacén; 1..n son las paradas. La matriz la
calcula ORS (que por dentro usa Dijkstra y sus variantes, calle por calle).
"""


def costo_ruta(orden, costo, regresar=False):
    """Costo total de salir del almacén (0), visitar `orden` y, si se pide, volver."""
    total, actual = 0, 0
    for p in orden:
        total += costo[actual][p]
        actual = p
    if regresar and orden:
        total += costo[actual][0]
    return total


def vecino_mas_cercano(costo):
    """Paso 1: desde el almacén, siempre a la parada pendiente más cercana."""
    pendientes = set(range(1, len(costo)))
    orden, actual = [], 0
    while pendientes:
        siguiente = min(pendientes, key=lambda p: (costo[actual][p], p))  # empate: la de menor número
        orden.append(siguiente)
        pendientes.remove(siguiente)
        actual = siguiente
    return orden


def dos_opt(orden, costo, regresar=False):
    """Paso 2: invierte tramos mientras eso acorte la ruta (quita los cruces)."""
    mejor, mejor_costo = list(orden), costo_ruta(orden, costo, regresar)
    mejoro = True
    while mejoro:
        mejoro = False
        for i in range(len(mejor) - 1):
            for j in range(i + 1, len(mejor)):
                candidata = mejor[:i] + mejor[i:j + 1][::-1] + mejor[j + 1:]
                c = costo_ruta(candidata, costo, regresar)
                if c < mejor_costo - 1e-9:          # mejora real (no solo por redondeo)
                    mejor, mejor_costo, mejoro = candidata, c, True
    return mejor


def ordenar(costo, regresar=False):
    """Orden recomendado de las paradas 1..n (vecino más cercano + 2-opt)."""
    return dos_opt(vecino_mas_cercano(costo), costo, regresar)
