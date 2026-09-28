from django.db import models
import uuid

class Pedido(models.Model):
    folio = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    descripcion = models.CharField(max_length=200)
    estado = models.CharField(max_length=50, default="Pendiente")
    eta = models.CharField(max_length=50, default="En 30 minutos")
    # Día 4: Campos para registrar el medio asignado y su motivo
    medio_asignado = models.CharField(max_length=50, blank=True, null=True)
    motivo_asignacion = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"Pedido {self.folio}"