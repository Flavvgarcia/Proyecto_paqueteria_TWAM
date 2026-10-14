class MedioDeEntrega:
    def planear(self, pedido, contexto):
        raise NotImplementedError("Debe implementar el método planear")

class Camioneta(MedioDeEntrega):
    def planear(self, pedido, contexto):
        return f"Camioneta asignada al folio {pedido.folio} ({contexto.motivo})"

class Dron(MedioDeEntrega):
    def planear(self, pedido, contexto):
        return f"Dron asignado al folio {pedido.folio} ({contexto.motivo})"

class Motocicleta(MedioDeEntrega):
    def planear(self, pedido, contexto):
        return f"Moto asignada al folio {pedido.folio} ({contexto.motivo})"

class Bicicleta(MedioDeEntrega):
    def planear(self, pedido, contexto):
        return f"Bici asignada al folio {pedido.folio} ({contexto.motivo})"