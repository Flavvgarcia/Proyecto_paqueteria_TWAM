from django.urls import path

from . import views, views_ia

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
]
