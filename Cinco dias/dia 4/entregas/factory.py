from .strategy import Camioneta, Dron, Motocicleta, Bicicleta

def crear_medio(nombre_medio: str):
    medios = {
        "camioneta": Camioneta(),
        "dron": Dron(),
        "motocicleta": Motocicleta(),
        "bicicleta": Bicicleta(),
    }
    # Retorna el medio solicitado, o Camioneta por defecto si no lo encuentra
    return medios.get(nombre_medio.lower(), Camioneta())