from .models import Pedido
from .adapter import obtener_sugerencia_ia
from .factory import crear_medio

def registrar_pedido(descripcion):
    # 1. Guardar en la base de datos (lo que ya teníamos)
    nuevo_pedido = Pedido.objects.create(descripcion=descripcion)
    
    # 2. ADAPTER: Consultar a la "IA" falsa y traducir su JSON a nuestro dominio
    sugerencia = obtener_sugerencia_ia(descripcion)
    
    # 3. FACTORY: Crear el objeto del vehículo correcto basándonos en el string de la sugerencia
    vehiculo = crear_medio(sugerencia.medio)
    
    # 4. STRATEGY: Ejecutar el plan de entrega delegando la acción, sin usar un solo if/else
    resultado_plan = vehiculo.planear(nuevo_pedido, sugerencia)
    
    # Imprimimos en la terminal de VS Code para comprobar que la lógica funcionó
    print("\n" + "="*50)
    print("🎯 PATRONES GoF EN ACCIÓN:")
    print(resultado_plan)
    print("="*50 + "\n")

    return nuevo_pedido