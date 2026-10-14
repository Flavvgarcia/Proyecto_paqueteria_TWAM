Resolución de Inconvenientes 3, 4 y 6 (Día 4)

1. Plantilla limpia y reporte reutilizable (Inconveniente 3)
En lugar de hacer consultas SQL dentro del HTML, se creó la función de servicio obtener_datos_seguimiento(pedido_id) en services.py. La vista detalle_pedido consulta la base de datos a través de esta función y le pasa un diccionario con los datos listos a la plantilla detalle.html.
Para el reporte gerencial (reporte.html), se reutiliza la misma función de servicio, evitando duplicar consultas SQL. Solo cambia la presentación visual de los mismos datos.

2. Transacción atómica y aviso pos-commit (Inconveniente 4)
El alta del pedido y el cobro simulado se envolvieron dentro de un bloque transaction.atomic() en registrar_pedido(). Esto asegura que el pedido y el cobro se guarden juntos o ninguno.
El aviso (correo/notificación) se programó con transaction.on_commit(). Esto garantiza que el aviso solo se dispare si la transacción en la base de datos se confirmó exitosamente. Si el envío de correo falla por problemas de red, el pedido ya quedó guardado en la base de datos y no se pierde. Observer síncrono no se usa aquí porque si fallara el observador podría arruinar la transacción de base de datos.

Respuesta por escrito: ¿Qué haríamos si el cliente pulsa dos veces "crear"?
- Para la recarga accidental de página, el patrón PRG (Post/Redirect/Get) que implementamos en el Día 2 redirige inmediatamente tras el POST hacia un GET. Si el usuario refresca la pantalla, solo repite la consulta GET, no crea otro pedido.
- Si el usuario hace doble clic muy rápido sobre el botón de envío antes de que el servidor responda, la solución es usar una clave de idempotencia (idempotency_key o token único en el formulario). Cuando entra la petición, el backend verifica si ya existe una transacción con ese token; si ya existe, ignora el segundo intento o devuelve el pedido ya creado sin duplicar el cobro.
- No se necesita Event Sourcing ni arquitecturas complejas como CQRS para resolver este problema; con PRG y control de idempotencia básico es suficiente.

3. Tolerancia a fallos de la IA (Inconveniente 6)
En adapter.py se agregó manejo de excepciones (try/except) y una variable IA_ACTIVA para simular la caída del servicio externo.
Si la IA no responde o lanza error, la función obtener_sugerencia_ia() atrapa la falla y activa un fallback asignando el medio por defecto (camioneta) con su motivo. De este modo, la creación del pedido no se traba y el registro se completa.
Además, la consulta GET /pedidos/<id> de un pedido ya existente no depende de la IA ni de servicios externos; consulta directamente la base de datos local, por lo que sigue funcionando normalmente aunque la IA esté caída.
