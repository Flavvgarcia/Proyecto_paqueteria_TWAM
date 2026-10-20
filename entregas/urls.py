from django.urls import path
from . import views

urlpatterns = [
    path("estado/", views.estado, name="estado"),
]