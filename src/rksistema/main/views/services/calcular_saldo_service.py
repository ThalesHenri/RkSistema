from django.db.models import Sum

from main.models.movimentacao import Movimentacao

TIPOS_ENTRADA = ("ENTRADA", "AJUSTE_POSITIVO")
TIPOS_SAIDA = ("SAIDA", "AJUSTE_NEGATIVO")


class CalcularSaldoService:
    """Calcula o saldo atual de um SKU, opcionalmente filtrado por depósito."""

    @staticmethod
    def executar(*, sku, deposito=None):
        qs = Movimentacao.objects.filter(sku=sku)
        if deposito is not None:
            qs = qs.filter(deposito=deposito)

        entradas = qs.filter(tipo__in=TIPOS_ENTRADA).aggregate(total=Sum("quantidade"))["total"] or 0
        saidas = qs.filter(tipo__in=TIPOS_SAIDA).aggregate(total=Sum("quantidade"))["total"] or 0

        return entradas - saidas
