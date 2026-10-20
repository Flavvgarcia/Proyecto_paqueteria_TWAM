def elegir_medio(km, kg):
    if kg > 20:
        return "camioneta", "paquete pesado"
    elif km <= 3:
        return "bicicleta", "distancia corta"
    elif km <= 15:
        return "moto", "distancia media"
    else:
        return "camioneta", "distancia larga"