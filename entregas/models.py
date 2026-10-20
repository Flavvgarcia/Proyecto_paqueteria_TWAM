from django.db import models


class Pedido(models.Model):
    folio = models.CharField(max_length=12, unique=True)
    destino = models.CharField(max_length=200)
    estado = models.CharField(max_length=20, default="registrado")
    creado = models.DateTimeField(auto_now_add=True)

    # Nuevos. Opcionales para que los pedidos que ya existen y el
    # POST /entregas/pedidos/ por curl sigan funcionando igual.
    distancia_km = models.FloatField(null=True, blank=True)
    peso_kg = models.FloatField(null=True, blank=True)
    medio = models.CharField(max_length=20, blank=True)
    motivo = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.folio} → {self.destino}"
