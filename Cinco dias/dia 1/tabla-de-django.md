---
# yaml-language-server: $schema=schemas\page.schema.json
Object type:
    - Page
Creation date: "2026-09-25T19:28:54Z"
Created by:
    - 'Richard '
Emoji: "\U0001F40D"
id: bafyreiej5q7h5ktii5vda66wwgigoyx4aobhg7hdqvjrlrpgbjrvuaxbqq
---
# Tabla de Django   
Tabla de 7 problemas del caso   
|      <br> |                                                           Inconveniente del enunciado   <br> |                                                                                     Qué **ya trae **Django   <br> |                                                                                    Qué tendremos que escribir nosotros   <br> |                                                                                             Qué **no** vamos a copiar del libro   <br> |
|:----------|:---------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------|
|  1   <br> |                   Duplicación de código de sesión, logs y encabezados en +40 archivos   <br> |                                   Front Controller (urls.py), la pila de Middlewares (settings.MIDDLEWARE)   <br> |                                                                                           Vistas y las plantillas HTML   <br> |                No implementar un Front controller o servicio de rutas propias, tampoco nada que interprete las peticiones HTTP.   <br> |
|  2   <br> |             Switch de 200 líneas para calcular entregas (camioneta, moto, bici, dron)   <br> |                                                                                Lo básico, clases y objetos   <br> |                                      Uso de Strategy: crear clases separadas para el calculo de entregas de cada medio   <br> |         No meteremos condicionales if/else if gigantes dentro de las vistas ni usaremos clases abstractas pesadas del libro GoF   <br> |
| 2a   <br> |               La IA entrega formatos incompatibles (JSON, XML) diferentes al sistema.   <br> |                                     Librerías estándar de Python (json, módulos XML) para procesar textos.   <br> |           Clases adaptadoras (Adapter) que traduzcan la respuesta externa a una instancia de Sugerencia(medio, motivo)   <br> |          No colocaremos la traducción del JSON/XML directamente dentro de las vistas de Django ni dentro del objeto de dominio.   <br> |
|  3   <br> |           Las plantillas HTML hacen consultas SQL directamente para mapas y reportes.   <br> |                           Template View (motor de plantillas) y Django ORM para abstraer la base de datos.   <br> |   Capa de Servicio (Service Layer) o función de trámite que consulte la BD y entregue los datos listos a la plantilla.   <br> |  No usaremos un patrón Repository casero sobre el ORM de Django, ni ejecutaremos consultas de base de datos desde la plantilla.   <br> |
|  4   <br> |             Si el correo falla, no se guarda el envío. Un doble clic cobra dos veces.   <br> |  Manejador de transacciones transaction.atomic, gancho transaction.on\_commit y redirección HTTP para PRG.   <br> |      Envolver el alta y cobro en la transacción y agendar el envío de correo/aviso únicamente cuando el commit suceda.   <br> |               No implementaremos el patrón Observer síncrono clásico de GoF acoplado dentro de la transacción de base de datos.   <br> |
|  5   <br> |  El panel web necesita HTML y el teléfono necesita JSON, pero hoy hace 12 peticiones.   <br> |                    Funciones render() para HTML, JsonResponse() para la API y enrutador unificado urls.py.   <br> |                                Un servicio de agregación común y dos vistas delgadas (una de HTML y otra de API JSON).   <br> |                       No construiremos microservicios separados ni 12 endpoints REST individuales para armar una sola pantalla.   <br> |
|  6   <br> |          Si la IA o el mapa se caen, la app se traba y no deja ver pedidos guardados.   <br> |            Arquitectura desacoplada de Django y manejo de excepciones en Python (try/except con timeouts).   <br> |             Lógica de fallback para que la vista devuelva la información del pedido de la BD aunque la IA no responda.   <br> |        No implementaremos patrones GoF complejos en llamadas a red ni esperaremos respuestas síncronas bloqueantes sin timeout.   <br> |
|  7   <br> |          Proponen Event Sourcing / CQRS / Redux innecesario solo para generar un PDF.   <br> |                                    Vistas directas de Django y librerías de Python para generación de PDF.   <br> |                 Una vista/función simple que tome el pedido de la base de datos y construya el archivo PDF solicitado.   <br> |                               Ninguno. Rechazaremos Event Sourcing, CQRS y Event Stores por ser sobreingeniería para este caso.   <br> |

Al final del día: tres renglones.    
- ¿=urls.py= es Front Controller, Page Controller, o el camino hacia los dos?    
    - Es Front Controller: actúa como un punto central de entrada que intercepta todas las solicitudes web y las redirige a la vista correspondiente. Al contrario de Page Controller, el cual tiene un controlador para cada pagina o acción.   
- ¿La plantilla Jinja/Django puede hacer `SELECT`? ¿Por qué sí o por qué no?   
    - No. La plantilla toma los datos y rellena los huecos, la vista no habla SQL.   
   
   
