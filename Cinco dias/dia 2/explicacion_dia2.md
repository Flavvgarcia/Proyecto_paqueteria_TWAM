Camino de la petición POST /pedidos (Análisis de Arquitectura)

Petición HTTP: El usuario envía el formulario y entra la solicitud POST /pedidos.

Middlewares (settings.py): Django intercepta la petición, procesa la sesión y valida el token de seguridad (CSRF).

Nota: Esta línea no es un patrón GoF implementado por nosotros (como Interceptor o Decorator); el marco ya lo trae y lo instancia automáticamente.

Enrutador (urls.py): Mapea la URL entrante hacia la vista correspondiente.

Nota: Actúa como Front Controller, pero no es GoF propio; Django ya instancia y resuelve el enrutamiento.

Vista (views.py - Page Controller): La función crear_pedido intercepta la petición. Se mantiene "delgada" extrayendo únicamente el dato (descripcion) y delegando el procesamiento.

Servicio (services.py - Service Layer): La vista invoca a registrar_pedido(descripcion). Aquí vive la lógica de trámite, aislada de la red y del HTTP.

Base de Datos (models.py - ORM): El servicio persiste el nuevo registro mediante los modelos.

Nota: No es GoF implementado por nosotros (como Repository o Data Mapper); el ORM de Django ya lo instancia.

Redirección (Patrón PRG): Tras guardar el pedido, la vista ejecuta el patrón Post/Redirect/Get retornando un código HTTP 302 hacia GET /pedidos/<id>. Esto evita duplicar el alta si el usuario recarga la página.

Plantilla (Template View): Al procesar el GET subsecuente, la vista detalle_pedido inyecta un contexto estático al HTML (detalle.html). La plantilla no realiza consultas SQL.