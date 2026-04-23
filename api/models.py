from django.db import models
import uuid


class Empresa(models.Model):
    TIPO_EMPRESA = "empresa"
    TIPO_GOVERNO = "governo"
    TIPOS_CONTA = [
        (TIPO_EMPRESA, "Empresa"),
        (TIPO_GOVERNO, "Governo"),
    ]

    nome = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    senha = models.CharField(max_length=255)

    tipo_conta = models.CharField(max_length=20, choices=TIPOS_CONTA, default=TIPO_EMPRESA)
    pacote_codigo = models.CharField(max_length=40, default="starter_5")
    plano = models.CharField(max_length=20, null=True, blank=True)
    ativo = models.BooleanField(default=False)
    acesso_governo = models.BooleanField(default=False)
    max_dispositivos = models.PositiveIntegerField(default=1)
    max_usuarios = models.PositiveIntegerField(default=1)
    sessao_ativa_chave = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_device_id = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_em = models.DateTimeField(null=True, blank=True)
    data_pagamento = models.DateField(null=True, blank=True)
    data_expiracao = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.nome


class RegistroSintoma(models.Model):
    ORIGEM_CIDADAO = "cidadao"
    ORIGEM_OFICIAL = "oficial"
    ORIGEM_IA = "ia_estimativa"
    ORIGEM_INSTITUCIONAL = "institucional"
    ORIGENS_DADO = [
        (ORIGEM_CIDADAO, "Relato cidadao"),
        (ORIGEM_OFICIAL, "Fonte oficial"),
        (ORIGEM_IA, "Estimativa IA"),
        (ORIGEM_INSTITUCIONAL, "Registro institucional"),
    ]

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
    device_id = models.CharField(max_length=120, null=True, blank=True)
    confianca = models.FloatField(default=1.0)
    suspeito = models.BooleanField(default=False)
    origem_dado = models.CharField(max_length=30, choices=ORIGENS_DADO, default=ORIGEM_CIDADAO)
    validade_epidemiologica = models.CharField(max_length=60, default="sinal_colaborativo")
    fonte_referencia = models.CharField(max_length=160, null=True, blank=True)
    revisado = models.BooleanField(default=False)

    def __str__(self):
        return f"Sintoma {self.id_anonimo}"


class DispositivoAutorizado(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="dispositivos")
    device_id = models.CharField(max_length=120)
    apelido = models.CharField(max_length=120, null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    ultimo_acesso = models.DateTimeField(auto_now=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "device_id")

    def __str__(self):
        return f"{self.empresa.nome} - {self.device_id}"


class EmpresaUsuario(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="usuarios")
    nome = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    senha = models.CharField(max_length=255)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    sessao_ativa_chave = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_device_id = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.empresa.nome} - {self.email}"


class DonoSaaS(models.Model):
    nome = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    senha = models.CharField(max_length=255)
    ativo = models.BooleanField(default=True)
    sessao_ativa_chave = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class FinanceiroEventoSaaS(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="eventos_financeiros")
    tipo_evento = models.CharField(max_length=40)
    pacote_codigo = models.CharField(max_length=40, null=True, blank=True)
    ciclo = models.CharField(max_length=20, null=True, blank=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=30, default="registrado")
    observacao = models.TextField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.empresa.nome} - {self.tipo_evento}"


class DonoAuditoriaAcao(models.Model):
    dono = models.ForeignKey(DonoSaaS, on_delete=models.CASCADE, related_name="auditorias")
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, related_name="auditorias_dono")
    acao = models.CharField(max_length=80)
    detalhes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        alvo = self.empresa.nome if self.empresa else "plataforma"
        return f"{self.dono.email} - {self.acao} - {alvo}"


class AlertaGovernamental(models.Model):
    STATUS_RASCUNHO = "rascunho"
    STATUS_EM_REVISAO = "em_revisao"
    STATUS_APROVADO = "aprovado"
    STATUS_PUBLICADO = "publicado"
    STATUS_REVOGADO = "revogado"
    STATUS_CHOICES = [
        (STATUS_RASCUNHO, "Rascunho"),
        (STATUS_EM_REVISAO, "Em revisao"),
        (STATUS_APROVADO, "Aprovado"),
        (STATUS_PUBLICADO, "Publicado"),
        (STATUS_REVOGADO, "Revogado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="alertas_governo")
    titulo = models.CharField(max_length=160)
    mensagem = models.TextField()
    estado = models.CharField(max_length=100, null=True, blank=True)
    cidade = models.CharField(max_length=100, null=True, blank=True)
    bairro = models.CharField(max_length=100, null=True, blank=True)
    nivel = models.CharField(max_length=20, default="moderado")
    ativo = models.BooleanField(default=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)
    protocolo = models.CharField(max_length=40, null=True, blank=True)
    justificativa = models.TextField(blank=True, default="")
    criado_por = models.CharField(max_length=160, blank=True, default="")
    revisado_por = models.CharField(max_length=160, blank=True, default="")
    aprovado_por = models.CharField(max_length=160, blank=True, default="")
    aprovado_em = models.DateTimeField(null=True, blank=True)
    publicado_em = models.DateTimeField(null=True, blank=True)
    revogado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["empresa", "status", "ativo"]),
            models.Index(fields=["estado", "cidade", "bairro"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} - {self.titulo}"


class AuditoriaInstitucional(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.SET_NULL, null=True, blank=True, related_name="auditorias_institucionais")
    principal_tipo = models.CharField(max_length=40, default="sistema")
    principal_id = models.CharField(max_length=80, blank=True, default="")
    principal_nome = models.CharField(max_length=160, blank=True, default="")
    acao = models.CharField(max_length=100)
    objeto_tipo = models.CharField(max_length=80, blank=True, default="")
    objeto_id = models.CharField(max_length=80, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    detalhes = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "acao"]),
            models.Index(fields=["objeto_tipo", "objeto_id"]),
        ]

    def __str__(self):
        alvo = self.empresa.nome if self.empresa else "plataforma"
        return f"{alvo} - {self.acao}"


class DispositivoPushPublico(models.Model):
    device_id = models.CharField(max_length=120)
    token = models.CharField(max_length=255, unique=True)
    plataforma = models.CharField(max_length=20, default="unknown")
    estado = models.CharField(max_length=100, null=True, blank=True)
    cidade = models.CharField(max_length=100, null=True, blank=True)
    bairro = models.CharField(max_length=100, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.plataforma} - {self.device_id}"


class AceiteLegalPublico(models.Model):
    device_id = models.CharField(max_length=120)
    versao = models.CharField(max_length=30)
    plataforma = models.CharField(max_length=30, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    metadados = models.JSONField(default=dict, blank=True)
    aceito_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-aceito_em"]
        indexes = [
            models.Index(fields=["device_id", "versao"]),
            models.Index(fields=["aceito_em"]),
        ]

    def __str__(self):
        return f"{self.device_id} - {self.versao}"


class FonteOficialExecucao(models.Model):
    STATUS_PENDENTE = "pendente"
    STATUS_EXECUTANDO = "executando"
    STATUS_CONCLUIDA = "concluida"
    STATUS_FALHOU = "falhou"
    STATUS_SEM_DADOS = "sem_dados"

    fonte_id = models.CharField(max_length=80)
    fonte_nome = models.CharField(max_length=160)
    status = models.CharField(max_length=30, default=STATUS_PENDENTE)
    modo = models.CharField(max_length=40, default="catalogo_seguro")
    periodo_inicio = models.CharField(max_length=20, null=True, blank=True)
    periodo_fim = models.CharField(max_length=20, null=True, blank=True)
    uf = models.CharField(max_length=2, null=True, blank=True)
    registros_lidos = models.PositiveIntegerField(default=0)
    agregados_gerados = models.PositiveIntegerField(default=0)
    mensagem = models.TextField(blank=True, default="")
    metadados = models.JSONField(default=dict, blank=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.fonte_id} - {self.status}"


class FonteOficialAgregado(models.Model):
    fonte_id = models.CharField(max_length=80)
    indicador = models.CharField(max_length=120)
    pais = models.CharField(max_length=80, default="Brasil")
    estado = models.CharField(max_length=100, null=True, blank=True)
    cidade = models.CharField(max_length=100, null=True, blank=True)
    codigo_ibge = models.CharField(max_length=20, null=True, blank=True)
    periodo = models.CharField(max_length=20)
    valor = models.FloatField(default=0)
    unidade = models.CharField(max_length=40, default="casos")
    taxa_100k = models.FloatField(null=True, blank=True)
    fonte_nome = models.CharField(max_length=160)
    versao_fonte = models.CharField(max_length=80, null=True, blank=True)
    metadados = models.JSONField(default=dict, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("fonte_id", "indicador", "codigo_ibge", "estado", "cidade", "periodo")
        indexes = [
            models.Index(fields=["fonte_id", "indicador", "periodo"]),
            models.Index(fields=["estado", "cidade"]),
        ]

    def __str__(self):
        local = self.cidade or self.estado or self.pais
        return f"{self.fonte_id} - {self.indicador} - {local} - {self.periodo}"
