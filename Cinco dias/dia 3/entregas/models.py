from django.db import models
import uuid

class Pedido(models.Model):
    folio = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    descripcion = models.CharField(max_length=200)
    estado = models.CharField(max_length=50, default="Pendiente")
    eta = models.CharField(max_length=50, default="En 30 minutos")

    def __str__(self):
        return f"Pedido {self.folio}"