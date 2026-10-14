El mismo pedido en JSON y la defensa (Día 5)

Objetivo del día: inconveniente 5 del enunciado (el panel web y la
futura app no tienen la misma "hambre" de datos) y dejar el repo en
condiciones de explicarse solo.

1. Un solo recurso de agregación, dos representaciones
En lugar de que la app arme su pantalla con varias peticiones sueltas
(el enunciado menciona doce), se agregó la vista api_pedido en
views.py, mapeada a GET /api/pedidos/<id>/. Reutiliza exactamente
la misma función de servicio que ya usaban detalle_pedido y
reporte_pedido: obtener_datos_seguimiento(pedido_id). No hay una
sola consulta SQL nueva; solo cambia el formato de salida
(JsonResponse en vez de render con una plantilla HTML), igual que en
el Día 2 vimos que el mismo trámite (registrar_pedido) puede
entregar HTML o JSON según quién pregunte.

El JSON se mantuvo mínimo a propósito: folio, estado y eta. Es el
contrato que necesitaría hoy una app para pintar una tarjeta de
seguimiento, sin arrastrar campos que solo tienen sentido en el panel
(el recuadro de mapa, el motivo detallado de la asignación).

2. Por qué no es Builder
En el análisis del 11-09-2026 ya se había descartado un patrón para
este inconveniente ("ninguno"), señalando que Builder pintaría
distintas representaciones del mismo proceso pero ese no era el
problema real: el problema era la falta de un endpoint por tipo de
cliente. Esa conclusión se sostiene: la solución no fue un patrón
GoF nuevo, fue simplemente no reinventar la vista —usar el mismo
servicio y dejar que Django devuelva render() o JsonResponse()
según la ruta.

3. Qué NO se hizo (punto 7 del enunciado)
No se implementó el PDF con Event Sourcing, CQRS ni Redux que un
proveedor hipotético propondría. Sigue sin haber ninguna fuerza en el
relato que lo justifique: es una operación de lectura simple (tomar
el pedido de la BD y construir un archivo). Se deja fuera de alcance
de este ciclo de cinco días a propósito.

4. Respuesta al ensayo de tres minutos
"Si mañana aparece un triciclo eléctrico, ¿cuántos archivos abrimos?"
Dos: se agrega la clase Triciclo(MedioDeEntrega) en strategy.py
(con su método planear) y se registra en el diccionario de
factory.py. Ni entregas/views.py, ni entregas/services.py, ni
las plantillas, ni el endpoint /api/pedidos/<id>/ cambian, porque
ninguno de ellos conoce el nombre concreto de un vehículo: todos
hablan con la interfaz MedioDeEntrega.planear(pedido, contexto).
Si la respuesta fuera "la vista, el adaptador y registrar_pedido",
señal de que el Día 3 no aisló bien el cambio.
