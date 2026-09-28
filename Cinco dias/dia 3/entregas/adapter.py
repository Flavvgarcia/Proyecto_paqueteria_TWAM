import json
from dataclasses import dataclass

# 1. Nuestro objeto de dominio limpio
@dataclass
class Sugerencia:
    medio: str
    motivo: str

# 2. El sistema externo simulado (El idioma ajeno)
class IAPredictorFalso:
    def predecir(self, descripcion):
        # Simula una API que devuelve un string en JSON
        return '{"route_hint": "dron", "score": 0.98, "reason": "Tráfico alto, peso ligero"}'

# 3. El ADAPTER: Traduce el JSON externo a nuestro dominio
def obtener_sugerencia_ia(descripcion) -> Sugerencia:
    api = IAPredictorFalso()
    respuesta_cruda = api.predecir(descripcion)
    
    # Traducimos el idioma ajeno al nuestro
    datos = json.loads(respuesta_cruda)
    
    return Sugerencia(
        medio=datos.get("route_hint", "camioneta"),
        motivo=datos.get("reason", "Ruta estándar")
    )