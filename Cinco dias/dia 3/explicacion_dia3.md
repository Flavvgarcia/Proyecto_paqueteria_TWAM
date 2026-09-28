Implementación de Patrones GoF (Día 3)

Adapter (adapter.py): Actúa como un puente entre el sistema externo (la "IA" que devuelve JSON crudo) y nuestro dominio. Aísla el "idioma ajeno" y lo traduce a un objeto propio (Sugerencia) que el resto del sistema entiende.

Factory (factory.py): Implementa una fábrica simple para centralizar la creación de los objetos. Recibe un string (el medio sugerido) y retorna la instancia de la clase correcta, aislando los new del flujo principal.

Strategy (strategy.py): Define una interfaz común (MedioDeEntrega) para encapsular las lógicas de cada vehículo (Camioneta, Dron, etc.). Elimina la necesidad de usar un bloque gigante de if/elif en el servicio, permitiendo que el comportamiento varíe dinámicamente en tiempo de ejecución.