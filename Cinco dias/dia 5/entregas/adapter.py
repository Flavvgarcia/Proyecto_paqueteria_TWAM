import json
from dataclasses import dataclass

# 1. Objeto de dominio limpio
@dataclass
class Sugerencia:
    medio: str
    motivo: str

# Variable para simular si la IA responde o esta caida (Inconveniente 6)
IA_ACTIVA = True

# 2. Sistema externo simulado
class IAPredictorFalso:
    def predecir(self, descripcion):
        if not IA_ACTIVA:
            raise ConnectionError("Servicio de IA no disponible")
        return '{"route_hint": "dron", "score": 0.98, "reason": "Trafico alto, peso ligero"}'

# 3. Adapter: traduce la respuesta externa a nuestro dominio
# Si la IA falla, devuelve una sugerencia por defecto (fallback)
def obtener_sugerencia_ia(descripcion) -> Sugerencia:
    try:
        api = IAPredictorFalso()
        respuesta_cruda = api.predecir(descripcion)
        datos = json.loads(respuesta_cruda)

        return Sugerencia(
            medio=datos.get("route_hint", "camioneta"),
            motivo=datos.get("reason", "Ruta estandar")
        )
    except Exception as e:
        # Fallback: se asigna camioneta por defecto si la IA no responde
        print(f"Aviso: Fallback activado ({e})")
        return Sugerencia(
            medio="camioneta",
            motivo="IA no disponible, asignacion por defecto"
        )