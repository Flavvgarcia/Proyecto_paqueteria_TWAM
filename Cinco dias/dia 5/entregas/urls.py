from django.urls import path
from . import views

urlpatterns = [
    path('pedidos/', views.crear_pedido, name='crear_pedido'),
    path('pedidos/<int:pedido_id>/', views.detalle_pedido, name='detalle_pedido'),
    path('pedidos/<int:pedido_id>/reporte/', views.reporte_pedido, name='reporte_pedido'),
    path('pedidos/lista/', views.lista_pedidos, name='lista_pedidos'),
    path('pedidos/toggle-ia/', views.toggle_ia, name='toggle_ia'),
    # Día 5: mismo folio que el panel, representación JSON para la app.
    path('api/pedidos/<int:pedido_id>/', views.api_pedido, name='api_pedido'),
]