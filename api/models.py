from django.db import models
import uuid


class Empresa(models.Model):
    nome = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    senha = models.CharField(max_length=255)

    plano = models.CharField(max_length=20, default="free")
    ativo = models.BooleanField(default=False)
    data_pagamento = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.nome


class RegistroSintoma(models.Model):

    id_anonimo = models.UUIDField(default=uuid.uuid4, editable=False)

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)

    doenca = models.CharField(max_length=50, null=True, blank=True)

    febre = models.BooleanField(default=False)
    tosse = models.BooleanField(default=False)
    dor_corpo = models.BooleanField(default=False)
    cansaco = models.BooleanField(default=False)
    falta_ar = models.BooleanField(default=False)

    latitude = models.FloatField(null=True)
    longitude = models.FloatField(null=True)

    pais = models.CharField(max_length=100, null=True, blank=True)
    estado = models.CharField(max_length=100, null=True, blank=True)
    cidade = models.CharField(max_length=100, null=True, blank=True)
    bairro = models.CharField(max_length=100, null=True, blank=True)
    condado = models.CharField(max_length=100, null=True, blank=True)

    data_registro = models.DateTimeField(auto_now_add=True)

    doenca_confirmada = models.CharField(max_length=50, null=True, blank=True)
    grupo = models.CharField(max_length=50, null=True, blank=True)
    classificacao = models.CharField(max_length=100, null=True, blank=True)

    # 🔐 SEGURANÇA (NOVO)
    ip = models.GenericIPAddressField(null=True, blank=True)
    confianca = models.FloatField(default=1.0)
    suspeito = models.BooleanField(default=False)

    def __str__(self):
        return f"Sintoma {self.id_anonimo}"