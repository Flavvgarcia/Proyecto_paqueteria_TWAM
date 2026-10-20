from django.urls import path

from . import views, views_ia, views_panel

urlpatterns = [
    path("hola/", views.hola, name="hola"),
    path("estado/", views.estado, name="estado"),
    path("pedidos/", views.registrar_pedido, name="registrar_pedido"),
    path("pedidos/<str:folio>/", views.seguimiento, name="seguimiento"),
    path("pedidos-mal/", views.registrar_pedido_mal, name="registrar_pedido_mal"),
    path("pedidos-mal/<str:folio>/", views.seguimiento_mal, name="seguimiento_mal"),
    path("cotizar/", views.cotizar, name="cotizar"),

    # Recomendador de IA (árbol / bosque / red)
    path("", views_ia.formulario_recomendar, name="inicio"),
    path("recomendar/", views_ia.recomendar, name="recomendar"),

    # Panel web (Día 2): formulario HTML + PRG + seguimiento
    path("panel/", views_panel.nuevo_pedido, name="panel_nuevo_pedido"),
    path("panel/pedidos/<str:folio>/", views_panel.detalle_pedido, name="panel_pedido"),
]
