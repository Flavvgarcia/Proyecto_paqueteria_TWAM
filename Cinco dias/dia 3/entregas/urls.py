from django.urls import path
from . import views

urlpatterns = [
    path('pedidos/', views.crear_pedido, name='crear_pedido'),
    path('pedidos/<int:pedido_id>/', views.detalle_pedido, name='detalle_pedido'),
]