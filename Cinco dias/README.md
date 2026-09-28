# La empresa de entregas — Cinco días

Implementación incremental (día por día, cada carpeta `dia N` es una
foto completa del proyecto Django en ese punto) del caso *La empresa
de entregas*. El estado final y ejecutable es **`dia 5`**.

## Cómo correrlo

```bash
cd "dia 5"
python -m venv venv
venv/Scripts/activate        # o: source venv/bin/activate
pip install django
python manage.py migrate
python manage.py runserver
```

Rutas principales:

- `GET /pedidos/` — formulario para crear un pedido (también permite
  apagar/prender la IA simulada con el link "Cambiar estado").
- `POST /pedidos/` — da de alta el pedido y redirige (PRG) a su detalle.
- `GET /pedidos/<id>/` — seguimiento del pedido (panel web, HTML).
- `GET /pedidos/<id>/reporte/` — reporte gerencial del mismo pedido.
- `GET /pedidos/lista/` — lista de todos los pedidos.
- `GET /api/pedidos/<id>/` — **el mismo folio en JSON mínimo**
  (`folio`, `estado`, `eta`) para la futura app.

## Qué ya traía Django y no reescribimos

- **Front Controller**: `configuracion/urls.py` — intercepta toda
  petición y la enruta; no hicimos un enrutador propio.
- **Middleware**: sesión y CSRF (`settings.MIDDLEWARE`) — no
  implementamos Interceptor/Decorator para eso.
- **Template View + ORM**: `render()` y los modelos (`models.py`) —
  no armamos un Repository casero sobre el ORM.
- **Transacciones**: `django.db.transaction.atomic` y
  `transaction.on_commit` — no escribimos un Observer síncrono para
  encadenar el aviso al cobro.

## Qué escribimos nosotros (y en qué archivo)

| Patrón / pieza | Archivo | Qué resuelve |
|---|---|---|
| Adapter | `entregas/adapter.py` | Traduce la respuesta cruda de la IA (JSON con `route_hint`) a `Sugerencia(medio, motivo)`, el único formato que el dominio entiende. |
| Strategy | `entregas/strategy.py` | `MedioDeEntrega.planear()` con una clase por vehículo (Camioneta, Dron, Motocicleta, Bicicleta); sin `if/elif` de 200 líneas. |
| Factory (simple) | `entregas/factory.py` | `crear_medio(nombre)` centraliza el `new` a partir del string que ya llegó traducido por el Adapter. |
| El trámite (orquestador) | `entregas/services.py` → `registrar_pedido()` | Encadena Adapter → Factory → Strategy dentro de `transaction.atomic`; agenda el aviso con `on_commit`; `obtener_datos_seguimiento()` arma el contexto una sola vez y lo reutilizan detalle, reporte **y** el JSON. |
| Vista delgada / PRG | `entregas/views.py` | `crear_pedido` solo extrae el dato y delega; redirige tras el POST para que recargar no duplique el pedido. |
| Representación dual (Día 5) | `entregas/views.py` → `api_pedido` | Mismo folio, dos salidas: HTML para el panel, JSON mínimo para la app — sin duplicar consultas ni levantar 12 peticiones. |

## Qué se rechazó y por qué

- **Punto 7 del enunciado (PDF con Event Sourcing/CQRS/Redux)**: no se
  implementó nada de eso. Generar un PDF de guía es un trámite simple
  (leer el pedido de la BD y construir el archivo); Event Sourcing y
  CQRS son sobreingeniería especulativa para un caso que no tiene
  ninguna fuerza que lo justifique.
- **Observer síncrono clásico** dentro de la transacción de cobro: si
  el observador (el envío del correo) fallara, podría arruinar una
  transacción de base de datos que ya era válida. Se usó
  `transaction.on_commit` en su lugar.
- **Factory Method con jerarquía de fábricas**: no hay familias de
  trámites que redefinan el "gancho" de creación, solo un string ya
  traducido por el Adapter — la fábrica simple basta.
- **Microservicios / 12 endpoints REST** para armar una sola pantalla:
  un único recurso de agregación (`obtener_datos_seguimiento`) reutilizado
  por HTML y JSON es suficiente para esta etapa.

## Ensayo de tres minutos: "si mañana hay triciclo, ¿cuántos archivos abrimos?"

Uno: se agrega una clase `Triciclo(MedioDeEntrega)` en `strategy.py` y
se da de alta en el diccionario de `factory.py`. Ni la vista, ni el
`registrar_pedido`, ni la plantilla, ni el endpoint JSON necesitan
cambiar — ninguno de ellos conoce el nombre concreto del vehículo, solo
la interfaz `planear(pedido, contexto)`. Si la respuesta fuera "la
vista, el adaptador y el `registrar_pedido`", el Día 3 no habría
quedado bien resuelto (Strategy/Factory no estarían aislando el
cambio).
