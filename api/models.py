import uuid
from decimal import Decimal

from django.db import models


def _codigo_acesso():
    return uuid.uuid4().hex


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
    codigo_acesso_corporativo = models.CharField(max_length=32, unique=True, default=_codigo_acesso)

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

    # ── Sintomas base (originais)
    febre = models.BooleanField(default=False)
    tosse = models.BooleanField(default=False)
    dor_corpo = models.BooleanField(default=False)
    cansaco = models.BooleanField(default=False)
    falta_ar = models.BooleanField(default=False)

    # ── Sintomas expandidos (IA 2.0 — diagnóstico diferencial preciso)
    dor_cabeca = models.BooleanField(default=False)          # cefaleia — dengue, gripe, meningite
    dor_articular = models.BooleanField(default=False)       # artralgia — chikungunya (intensa!), zika, dengue
    exantema = models.BooleanField(default=False)            # rash/manchas — dengue, zika, chikungunya, sarampo
    conjuntivite = models.BooleanField(default=False)        # hiperemia ocular — zika (patognomônico), sarampo
    vomito_nausea = models.BooleanField(default=False)       # dengue alarme, leptospirose, hepatite
    diarreia = models.BooleanField(default=False)            # rotavírus, cólera, dengue hemorrágico
    dor_abdominal = models.BooleanField(default=False)       # dengue, leptospirose, hepatite
    rigidez_nuca = models.BooleanField(default=False)        # MENINGITE — flag de urgência imediata
    ictericia = models.BooleanField(default=False)           # febre amarela, leptospirose, hepatite
    manchas_hemorragicas = models.BooleanField(default=False) # petéquias — dengue hemorrágico, meningite
    perda_olfato_paladar = models.BooleanField(default=False) # COVID-19 (quase patognomônico)
    dor_garganta = models.BooleanField(default=False)        # gripe, COVID, estreptococo, resfriado
    coriza = models.BooleanField(default=False)              # resfriado, gripe, RSV
    calafrios = models.BooleanField(default=False)           # malária (ciclico), dengue, leptospirose
    # Intensidade da febre (escala: None, baixa<38.5, moderada 38.5-39.5, alta>39.5)
    intensidade_febre = models.CharField(max_length=10, blank=True, default="",
        choices=[("", "Não informado"), ("baixa", "Baixa"), ("moderada", "Moderada"), ("alta", "Alta")])
    # Intensidade da dor articular (diferencia chikungunya de dengue)
    intensidade_articular = models.CharField(max_length=12, blank=True, default="",
        choices=[("", "Não informado"), ("leve", "Leve"), ("moderada", "Moderada"), ("intensa", "Intensa — incapacitante")])

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
    classificacao = models.CharField(max_length=300, null=True, blank=True)

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
    email = models.EmailField()
    senha = models.CharField(max_length=255)
    cargo = models.CharField(max_length=100, null=True, blank=True)
    ativo = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    sessao_ativa_chave = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_device_id = models.CharField(max_length=120, null=True, blank=True)
    sessao_ativa_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "email")

    def __str__(self):
        return f"{self.empresa.nome} - {self.email}"


class EmpresaUnidade(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="unidades_corporativas")
    nome = models.CharField(max_length=120)
    codigo = models.CharField(max_length=40, blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "nome")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.empresa.nome} - {self.nome}"


class EmpresaSetor(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="setores_corporativos")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="setores")
    nome = models.CharField(max_length=120)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "unidade", "nome")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.empresa.nome} - {self.nome}"


class EmpresaTurno(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="turnos_corporativos")
    nome = models.CharField(max_length=80)
    janela = models.CharField(max_length=80, blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "nome")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.empresa.nome} - {self.nome}"


class EmpresaCargoCorporativo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="cargos_corporativos")
    setor = models.ForeignKey("EmpresaSetor", on_delete=models.SET_NULL, null=True, blank=True, related_name="cargos")
    nome = models.CharField(max_length=120)
    codigo = models.CharField(max_length=40, blank=True, default="")
    nivel_inicial = models.CharField(max_length=40, blank=True, default="junior")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "setor", "nome")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.empresa.nome} - cargo - {self.nome}"


class FuncaoCriticaCorporativa(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="funcoes_criticas_corporativas")
    cargo = models.ForeignKey(EmpresaCargoCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="funcoes_criticas")
    setor = models.ForeignKey("EmpresaSetor", on_delete=models.SET_NULL, null=True, blank=True, related_name="funcoes_criticas")
    nome = models.CharField(max_length=140)
    descricao = models.TextField(blank=True, default="")
    criticidade = models.PositiveSmallIntegerField(default=3)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "cargo", "nome")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.empresa.nome} - funcao critica - {self.nome}"


class EquipamentoCorporativo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="equipamentos_corporativos")
    setor = models.ForeignKey("EmpresaSetor", on_delete=models.SET_NULL, null=True, blank=True, related_name="equipamentos")
    nome = models.CharField(max_length=140)
    codigo = models.CharField(max_length=60, blank=True, default="")
    categoria = models.CharField(max_length=80, blank=True, default="")
    criticidade = models.PositiveSmallIntegerField(default=3)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "setor", "nome")
        ordering = ["nome"]

    def __str__(self):
        return f"{self.empresa.nome} - equipamento - {self.nome}"


class ColaboradorAliasCorporativo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="aliases_corporativos")
    alias_publico = models.CharField(max_length=80, default=_codigo_acesso)
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="aliases")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="aliases")
    turno = models.ForeignKey(EmpresaTurno, on_delete=models.SET_NULL, null=True, blank=True, related_name="aliases")
    cargo = models.ForeignKey(EmpresaCargoCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="colaboradores")
    ativo = models.BooleanField(default=True)
    permite_contato = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("empresa", "alias_publico")
        ordering = ["-atualizado_em"]

    def __str__(self):
        return f"{self.empresa.nome} - {self.alias_publico}"


class CheckinDiarioCorporativo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="checkins_diarios_corporativos")
    alias = models.ForeignKey(ColaboradorAliasCorporativo, on_delete=models.CASCADE, related_name="checkins_diarios")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_diarios")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_diarios")
    turno = models.ForeignKey(EmpresaTurno, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_diarios")
    data_referencia = models.DateField()
    humor = models.PositiveSmallIntegerField(default=3)
    energia = models.PositiveSmallIntegerField(default=3)
    estresse = models.PositiveSmallIntegerField(default=3)
    sono = models.PositiveSmallIntegerField(default=3)
    dor_fisica = models.PositiveSmallIntegerField(default=1)
    fadiga = models.PositiveSmallIntegerField(default=1)
    ansiedade = models.PositiveSmallIntegerField(default=1)
    tristeza = models.PositiveSmallIntegerField(default=1)
    irritabilidade = models.PositiveSmallIntegerField(default=1)
    sintomas_respiratorios = models.BooleanField(default=False)
    dor_corporal = models.BooleanField(default=False)
    dor_cabeca = models.BooleanField(default=False)
    febre = models.BooleanField(default=False)
    apoio_solicitado = models.BooleanField(default=False)
    observacao = models.CharField(max_length=280, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "alias", "data_referencia")
        ordering = ["-data_referencia", "-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "data_referencia"]),
            models.Index(fields=["empresa", "unidade", "data_referencia"]),
            models.Index(fields=["empresa", "setor", "data_referencia"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} - diario - {self.data_referencia}"


class CheckinSemanalCorporativo(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="checkins_semanais_corporativos")
    alias = models.ForeignKey(ColaboradorAliasCorporativo, on_delete=models.CASCADE, related_name="checkins_semanais")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_semanais")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_semanais")
    turno = models.ForeignKey(EmpresaTurno, on_delete=models.SET_NULL, null=True, blank=True, related_name="checkins_semanais")
    semana_referencia = models.DateField()
    carga_emocional = models.PositiveSmallIntegerField(default=3)
    seguranca_psicologica = models.PositiveSmallIntegerField(default=3)
    apoio_percebido = models.PositiveSmallIntegerField(default=3)
    pressao_trabalho = models.PositiveSmallIntegerField(default=3)
    bem_estar_geral = models.PositiveSmallIntegerField(default=3)
    risco_burnout = models.PositiveSmallIntegerField(default=1)
    observacao = models.CharField(max_length=280, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "alias", "semana_referencia")
        ordering = ["-semana_referencia", "-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "semana_referencia"]),
            models.Index(fields=["empresa", "unidade", "semana_referencia"]),
            models.Index(fields=["empresa", "setor", "semana_referencia"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} - semanal - {self.semana_referencia}"


class PedidoApoioCorporativo(models.Model):
    STATUS_NOVO = "novo"
    STATUS_EM_ANALISE = "em_analise"
    STATUS_ENCAMINHADO = "encaminhado"
    STATUS_CONCLUIDO = "concluido"
    STATUS_CHOICES = [
        (STATUS_NOVO, "Novo"),
        (STATUS_EM_ANALISE, "Em analise"),
        (STATUS_ENCAMINHADO, "Encaminhado"),
        (STATUS_CONCLUIDO, "Concluido"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pedidos_apoio_corporativos")
    alias = models.ForeignKey(ColaboradorAliasCorporativo, on_delete=models.CASCADE, related_name="pedidos_apoio")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_apoio")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_apoio")
    turno = models.ForeignKey(EmpresaTurno, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_apoio")
    deseja_contato = models.BooleanField(default=False)
    canal_preferido = models.CharField(max_length=80, blank=True, default="")
    relato = models.CharField(max_length=280, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOVO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    atendente = models.CharField(max_length=160, blank=True, default="")
    resolucao = models.TextField(blank=True, default="")
    concluido_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.empresa.nome} - apoio - {self.status}"


class ProgramaCorporativo(models.Model):
    TIPO_FADIGA = "fadiga"
    TIPO_PSICOSSOCIAL = "psicossocial"
    TIPO_ERGONOMIA = "ergonomia"
    TIPO_COMPETENCIA = "competencia"
    TIPO_CULTURA = "cultura"
    TIPO_LIVRE = "livre"
    TIPOS = [
        (TIPO_FADIGA, "Fadiga e recuperacao"),
        (TIPO_PSICOSSOCIAL, "Risco psicossocial"),
        (TIPO_ERGONOMIA, "Ergonomia e saude fisica"),
        (TIPO_COMPETENCIA, "Competencia tecnica"),
        (TIPO_CULTURA, "Cultura e comunicacao"),
        (TIPO_LIVRE, "Programa livre"),
    ]

    STATUS_RASCUNHO = "rascunho"
    STATUS_ATIVO = "ativo"
    STATUS_PAUSADO = "pausado"
    STATUS_ENCERRADO = "encerrado"
    STATUS_CHOICES = [
        (STATUS_RASCUNHO, "Rascunho"),
        (STATUS_ATIVO, "Ativo"),
        (STATUS_PAUSADO, "Pausado"),
        (STATUS_ENCERRADO, "Encerrado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="programas_corporativos")
    titulo = models.CharField(max_length=160)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_LIVRE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RASCUNHO)
    owner = models.CharField(max_length=160)
    objetivo = models.TextField(blank=True, default="")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="programas")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="programas")
    prazo = models.DateField(null=True, blank=True)
    resultado = models.TextField(blank=True, default="")
    encerrado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["empresa", "status"])]

    def __str__(self):
        return f"{self.empresa.nome} - programa - {self.titulo}"


class AcaoCorporativa(models.Model):
    STATUS_ABERTA = "aberta"
    STATUS_EM_ANDAMENTO = "em_andamento"
    STATUS_CONCLUIDA = "concluida"
    STATUS_CANCELADA = "cancelada"
    STATUS_CHOICES = [
        (STATUS_ABERTA, "Aberta"),
        (STATUS_EM_ANDAMENTO, "Em andamento"),
        (STATUS_CONCLUIDA, "Concluida"),
        (STATUS_CANCELADA, "Cancelada"),
    ]

    ORIGEM_MANUAL = "manual"
    ORIGEM_RISCO = "risco"
    ORIGEM_APOIO = "apoio"
    ORIGEM_PROGRAMA = "programa"
    ORIGENS = [
        (ORIGEM_MANUAL, "Criada manualmente"),
        (ORIGEM_RISCO, "Gerada por risco"),
        (ORIGEM_APOIO, "Gerada por pedido de apoio"),
        (ORIGEM_PROGRAMA, "Vinculada a programa"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="acoes_corporativas")
    titulo = models.CharField(max_length=160)
    descricao = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ABERTA)
    origem = models.CharField(max_length=20, choices=ORIGENS, default=ORIGEM_MANUAL)
    owner = models.CharField(max_length=160)
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="acoes")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="acoes")
    prazo = models.DateField(null=True, blank=True)
    evidencia = models.TextField(blank=True, default="")
    programa = models.ForeignKey(ProgramaCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="acoes")
    pedido_apoio = models.ForeignKey(PedidoApoioCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="acoes")
    concluido_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "origem"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} - acao - {self.titulo}"


class TrilhaCompetenciaCorporativa(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="trilhas_competencia_corporativas")
    cargo = models.ForeignKey(EmpresaCargoCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="trilhas_competencia")
    funcao_critica = models.ForeignKey(FuncaoCriticaCorporativa, on_delete=models.SET_NULL, null=True, blank=True, related_name="trilhas_competencia")
    titulo = models.CharField(max_length=160)
    descricao = models.TextField(blank=True, default="")
    nivel_alvo = models.CharField(max_length=40, blank=True, default="")
    ordem = models.PositiveIntegerField(default=1)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("empresa", "cargo", "titulo")
        ordering = ["ordem", "titulo"]

    def __str__(self):
        return f"{self.empresa.nome} - trilha - {self.titulo}"


class CompetenciaItemCorporativo(models.Model):
    TIPO_CONHECIMENTO = "conhecimento"
    TIPO_PRATICA = "pratica"
    TIPO_SEGURANCA = "seguranca"
    TIPO_EQUIPAMENTO = "equipamento"
    TIPOS_ITEM = [
        (TIPO_CONHECIMENTO, "Conhecimento"),
        (TIPO_PRATICA, "Pratica"),
        (TIPO_SEGURANCA, "Seguranca"),
        (TIPO_EQUIPAMENTO, "Equipamento"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="itens_competencia_corporativos")
    trilha = models.ForeignKey(TrilhaCompetenciaCorporativa, on_delete=models.CASCADE, related_name="itens")
    equipamento = models.ForeignKey(EquipamentoCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens_competencia")
    titulo = models.CharField(max_length=160)
    tipo = models.CharField(max_length=20, choices=TIPOS_ITEM, default=TIPO_CONHECIMENTO)
    descricao = models.TextField(blank=True, default="")
    ordem = models.PositiveIntegerField(default=1)
    peso = models.PositiveSmallIntegerField(default=1)
    obrigatorio = models.BooleanField(default=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("trilha", "titulo")
        ordering = ["ordem", "titulo"]

    def __str__(self):
        return f"{self.trilha.titulo} - {self.titulo}"


class EvidenciaCompetenciaCorporativa(models.Model):
    STATUS_RASCUNHO = "rascunho"
    STATUS_ENVIADA = "enviada"
    STATUS_VALIDADA = "validada"
    STATUS_REVISAR = "revisar"
    STATUS_CHOICES = [
        (STATUS_RASCUNHO, "Rascunho"),
        (STATUS_ENVIADA, "Enviada"),
        (STATUS_VALIDADA, "Validada"),
        (STATUS_REVISAR, "Revisar"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="evidencias_competencia_corporativas")
    alias = models.ForeignKey(ColaboradorAliasCorporativo, on_delete=models.CASCADE, related_name="evidencias_competencia")
    item = models.ForeignKey(CompetenciaItemCorporativo, on_delete=models.CASCADE, related_name="evidencias")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias_competencia")
    setor = models.ForeignKey(EmpresaSetor, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias_competencia")
    equipamento = models.ForeignKey(EquipamentoCorporativo, on_delete=models.SET_NULL, null=True, blank=True, related_name="evidencias_competencia")
    titulo = models.CharField(max_length=160, blank=True, default="")
    descricao = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ENVIADA)
    pontuacao_autodeclarada = models.PositiveSmallIntegerField(default=1)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "alias"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} - evidencia - {self.item.titulo}"


class ValidacaoCompetenciaCorporativa(models.Model):
    RESULTADO_PENDENTE = "pendente"
    RESULTADO_APROVADA = "aprovada"
    RESULTADO_REPROVADA = "reprovada"
    RESULTADO_CHOICES = [
        (RESULTADO_PENDENTE, "Pendente"),
        (RESULTADO_APROVADA, "Aprovada"),
        (RESULTADO_REPROVADA, "Reprovada"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="validacoes_competencia_corporativas")
    evidencia = models.OneToOneField(EvidenciaCompetenciaCorporativa, on_delete=models.CASCADE, related_name="validacao")
    validado_por = models.ForeignKey(EmpresaUsuario, on_delete=models.SET_NULL, null=True, blank=True, related_name="validacoes_competencia")
    resultado = models.CharField(max_length=20, choices=RESULTADO_CHOICES, default=RESULTADO_PENDENTE)
    pontuacao_validador = models.PositiveSmallIntegerField(default=0)
    comentario = models.TextField(blank=True, default="")
    validado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-atualizado_em"]
        indexes = [
            models.Index(fields=["empresa", "resultado"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} - validacao - {self.resultado}"


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


class PasswordResetToken(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True)
    usuario = models.ForeignKey(EmpresaUsuario, on_delete=models.CASCADE, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    usado = models.BooleanField(default=False)

    def __str__(self):
        alvo = self.usuario.email if self.usuario else (self.empresa.email if self.empresa else "—")
        return f"reset:{alvo}"


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


# ── ESCALAS CORPORATIVAS ───────────────────────────────────────────────────────

class EscalaCorporativa(models.Model):
    TIPO_14x14 = "14x14"
    TIPO_28x28 = "28x28"
    TIPO_7x7 = "7x7"
    TIPO_PERSONALIZADO = "personalizado"
    TIPOS = [
        (TIPO_14x14, "14x14"),
        (TIPO_28x28, "28x28"),
        (TIPO_7x7, "7x7"),
        (TIPO_PERSONALIZADO, "Personalizado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="escalas_corporativas")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="escalas")
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_14x14)
    dias_embarcado = models.PositiveSmallIntegerField(default=14)
    dias_folga = models.PositiveSmallIntegerField(default=14)
    descricao = models.TextField(blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        indexes = [models.Index(fields=["empresa", "ativo"])]

    def __str__(self):
        return f"{self.empresa.nome} - escala - {self.nome}"


class ColaboradorEscalaCorporativa(models.Model):
    FASE_EMBARCADO = "embarcado"
    FASE_FOLGA = "folga"
    FASES = [
        (FASE_EMBARCADO, "Embarcado"),
        (FASE_FOLGA, "Folga"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="colaboradores_escala")
    alias = models.ForeignKey(ColaboradorAliasCorporativo, on_delete=models.CASCADE, related_name="escalas")
    escala = models.ForeignKey(EscalaCorporativa, on_delete=models.CASCADE, related_name="colaboradores")
    inicio_ciclo = models.DateField()
    fase_atual = models.CharField(max_length=20, choices=FASES, default=FASE_EMBARCADO)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("alias", "escala")
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "escala"]),
            models.Index(fields=["empresa", "fase_atual"]),
        ]

    def __str__(self):
        return f"{self.alias.alias_publico} - {self.escala.nome} - {self.fase_atual}"


# ─── SST / Saúde Ocupacional ────────────────────────────────────────────────

class FuncionarioSST(models.Model):
    CLASSE_RISCO = [("I", "Grau I"), ("II", "Grau II"), ("III", "Grau III"), ("IV", "Grau IV")]
    SEXO = [("M", "Masculino"), ("F", "Feminino"), ("O", "Outro")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="funcionarios_sst")
    unidade = models.ForeignKey(EmpresaUnidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="funcionarios_sst")
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=14, blank=True)
    matricula = models.CharField(max_length=40, blank=True)
    cargo = models.CharField(max_length=120)
    setor = models.CharField(max_length=120, blank=True)
    sexo = models.CharField(max_length=1, choices=SEXO, blank=True)
    data_nascimento = models.DateField(null=True, blank=True)
    data_admissao = models.DateField(null=True, blank=True)
    data_demissao = models.DateField(null=True, blank=True)
    classe_risco = models.CharField(max_length=4, choices=CLASSE_RISCO, default="II")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["empresa", "ativo"]),
            models.Index(fields=["empresa", "unidade"]),
        ]

    def __str__(self):
        return f"{self.nome} — {self.cargo} ({self.empresa.nome})"


class CredencialAppFuncionario(models.Model):
    """Login e senha criados pelo próprio funcionário no app."""
    funcionario = models.OneToOneField(
        FuncionarioSST, on_delete=models.CASCADE, related_name="credencial_app"
    )
    email = models.EmailField(unique=True)
    senha = models.CharField(max_length=255)  # bcrypt hash
    ativo = models.BooleanField(default=True)
    # FCM token para push notifications (atualizado a cada login)
    fcm_token = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.email} → {self.funcionario.nome}"


class NotificacaoFuncionario(models.Model):
    TIPO_ASO = "aso"
    TIPO_EXAME = "exame"
    TIPO_TREINAMENTO = "treinamento"
    TIPO_GERAL = "geral"
    TIPOS = [
        (TIPO_ASO, "ASO"),
        (TIPO_EXAME, "Exame"),
        (TIPO_TREINAMENTO, "Treinamento"),
        (TIPO_GERAL, "Geral"),
    ]

    funcionario = models.ForeignKey(
        FuncionarioSST, on_delete=models.CASCADE, related_name="notificacoes_app"
    )
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_GERAL)
    titulo = models.CharField(max_length=200)
    mensagem = models.TextField(blank=True)
    referencia_id = models.PositiveIntegerField(null=True, blank=True)
    lida = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["funcionario", "lida"])]

    def __str__(self):
        return f"{self.titulo} → {self.funcionario.nome}"


class CheckinBemEstar(models.Model):
    """
    Check-in de bem-estar do funcionário.
    Anônimo por padrão — a empresa só acessa dados agregados.
    Se o funcionário pedir ajuda E marcar quer_contato=True, a empresa
    pode ver o nome para oferecer suporte direto.
    """
    HUMOR = [
        ("otimo",   "Ótimo 😄"),
        ("bom",     "Bom 🙂"),
        ("regular", "Regular 😐"),
        ("ruim",    "Ruim 😔"),
        ("pessimo", "Péssimo 😞"),
    ]
    TIPO_AJUDA = [
        ("saude_fisica",  "Saúde física"),
        ("saude_mental",  "Saúde mental / ansiedade"),
        ("vicio",         "Dependência / vício"),
        ("trabalho",      "Problemas no trabalho"),
        ("financeiro",    "Dificuldade financeira"),
        ("familiar",      "Problema familiar"),
        ("outro",         "Outro"),
    ]

    funcionario  = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="checkins_bem_estar")
    empresa      = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="checkins_bem_estar")

    # ── resposta principal ────────────────────────────────────────────────────
    humor              = models.CharField(max_length=10, choices=HUMOR)
    saude_fisica       = models.PositiveSmallIntegerField(default=3)   # 1–5
    saude_mental       = models.PositiveSmallIntegerField(default=3)   # 1–5
    nivel_estresse     = models.PositiveSmallIntegerField(default=3)   # 1–5
    satisfacao_trabalho= models.PositiveSmallIntegerField(default=3)   # 1–5
    mensagem           = models.TextField(blank=True)  # sempre anônima

    # ── pedido de ajuda ───────────────────────────────────────────────────────
    precisa_ajuda  = models.BooleanField(default=False)
    tipo_ajuda     = models.CharField(max_length=20, choices=TIPO_AJUDA, blank=True)
    # Somente se o próprio funcionário consentir, a empresa vê o nome
    quer_contato   = models.BooleanField(default=False)
    contato_resolvido = models.BooleanField(default=False)  # empresa marca quando atendeu

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["empresa", "criado_em"])]

    def __str__(self):
        return f"Check-in {self.funcionario.nome} — {self.humor} ({self.criado_em:%d/%m/%Y})"


class ASOOcupacional(models.Model):
    TIPO = [
        ("admissional", "Admissional"),
        ("periodico", "Periódico"),
        ("retorno_trabalho", "Retorno ao Trabalho"),
        ("mudanca_risco", "Mudança de Risco"),
        ("demissional", "Demissional"),
    ]
    RESULTADO = [("apto", "Apto"), ("inapto", "Inapto"), ("apto_restricao", "Apto com Restrição")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="asos")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="asos")
    tipo = models.CharField(max_length=30, choices=TIPO)
    data_emissao = models.DateField()
    data_validade = models.DateField(null=True, blank=True)
    medico_responsavel = models.CharField(max_length=200, blank=True)
    crm = models.CharField(max_length=30, blank=True)
    resultado = models.CharField(max_length=20, choices=RESULTADO, default="apto")
    cid_inapto = models.CharField(max_length=10, blank=True, verbose_name="CID (quando inapto/restrito)")
    riscos_ocupacionais = models.TextField(blank=True, verbose_name="Riscos ocupacionais do cargo (NR-7)")
    restricoes = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_emissao"]
        indexes = [
            models.Index(fields=["empresa", "data_validade"]),
            models.Index(fields=["empresa", "resultado"]),
        ]

    def __str__(self):
        return f"ASO {self.tipo} — {self.funcionario.nome} ({self.data_emissao})"


class ExameOcupacional(models.Model):
    TIPO_EXAME = [
        ("audiometria", "Audiometria"),
        ("acuidade_visual", "Acuidade Visual"),
        ("espirometria", "Espirometria"),
        ("laboratorial", "Laboratorial"),
        ("eletrocardiograma", "Eletrocardiograma"),
        ("raio_x", "Raio-X"),
        ("psicologico", "Avaliação Psicológica"),
        ("outro", "Outro"),
    ]
    STATUS = [("pendente", "Pendente"), ("realizado", "Realizado"), ("vencido", "Vencido")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="exames_ocupacionais")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="exames")
    aso = models.ForeignKey(ASOOcupacional, on_delete=models.SET_NULL, null=True, blank=True, related_name="exames")
    tipo_exame = models.CharField(max_length=30, choices=TIPO_EXAME)
    data_realizacao = models.DateField(null=True, blank=True)
    data_validade = models.DateField(null=True, blank=True)
    resultado = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pendente")
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data_validade"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "data_validade"]),
        ]

    def __str__(self):
        return f"{self.tipo_exame} — {self.funcionario.nome}"


class CATOcupacional(models.Model):
    TIPO = [("tipico", "Típico"), ("trajeto", "De Trajeto"), ("doenca", "Doença Ocupacional")]
    STATUS_ESOCIAL = [
        ("nao_enviado", "Não Enviado"),
        ("pendente", "Pendente"),
        ("transmitido", "Transmitido"),
        ("erro", "Erro na Transmissão"),
        ("retificado", "Retificado"),
    ]
    GRAVIDADE = [("leve", "Leve"), ("moderado", "Moderado"), ("grave", "Grave"), ("fatal", "Fatal")]
    TP_CAT = [("1", "Inicial"), ("2", "Reabertura"), ("3", "Comunicação de Óbito")]
    LATERALIDADE = [("1", "Esquerdo"), ("2", "Direito"), ("3", "Ambos"), ("9", "Não Aplicável")]
    COD_PARTE_CORPO = [
        ("010", "Cabeça / Crânio"), ("020", "Ouvido(s)"), ("030", "Olho(s) / Face"),
        ("040", "Pescoço"), ("050", "Tronco / Tórax"), ("060", "Coluna Vertebral"),
        ("070", "Abdome"), ("080", "Membro Superior Direito"), ("081", "Membro Superior Esquerdo"),
        ("082", "Ambos os Membros Superiores"), ("090", "Membro Inferior Direito"),
        ("091", "Membro Inferior Esquerdo"), ("092", "Ambos os Membros Inferiores"),
        ("730", "Múltiplas Partes do Corpo"), ("800", "Sistema Nervoso"), ("900", "Órgãos Internos"),
        ("999", "Outras Partes"),
    ]
    COD_AGENTE = [
        ("0001", "Animais e insetos"), ("0002", "Choque elétrico"),
        ("0003", "Esforço excessivo / movimento repetitivo"), ("0004", "Explosão / implosão"),
        ("0005", "Incêndio"), ("0006", "Queda"), ("0007", "Substâncias químicas / gases / fumaças"),
        ("0008", "Temperatura extrema (calor ou frio)"), ("0009", "Máquinas e equipamentos"),
        ("0010", "Material cortante / perfurante"), ("0011", "Impacto por objeto / equipamento"),
        ("0012", "Acidente de trânsito"), ("0099", "Outros agentes"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="cats")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="cats")
    tipo = models.CharField(max_length=20, choices=TIPO, default="tipico")
    tp_cat = models.CharField(max_length=1, choices=TP_CAT, default="1", verbose_name="Tipo de CAT")
    gravidade = models.CharField(max_length=20, choices=GRAVIDADE, default="leve")
    data_acidente = models.DateField()
    hora_acidente = models.TimeField(null=True, blank=True)
    local_acidente = models.CharField(max_length=200, blank=True)
    descricao = models.TextField()
    parte_corpo = models.CharField(max_length=100, blank=True, verbose_name="Parte do corpo (descrição livre)")
    cod_parte_corpo = models.CharField(max_length=3, choices=COD_PARTE_CORPO, default="730", verbose_name="Código parte atingida (eSocial)")
    lateralidade = models.CharField(max_length=1, choices=LATERALIDADE, default="9", verbose_name="Lateralidade")
    cod_agente_causador = models.CharField(max_length=4, choices=COD_AGENTE, default="0099", verbose_name="Agente causador (eSocial)")
    cid = models.CharField(max_length=10, blank=True)
    numero_cat = models.CharField(max_length=30, blank=True)
    houve_afastamento = models.BooleanField(default=False)
    dias_afastamento = models.IntegerField(default=0)
    testemunha_nome = models.CharField(max_length=180, blank=True, verbose_name="Nome da testemunha")
    testemunha_telefone = models.CharField(max_length=20, blank=True, verbose_name="Telefone da testemunha")
    status_esocial = models.CharField(max_length=20, choices=STATUS_ESOCIAL, default="nao_enviado")
    protocolo_esocial = models.CharField(max_length=60, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_acidente"]
        indexes = [
            models.Index(fields=["empresa", "status_esocial"]),
            models.Index(fields=["empresa", "data_acidente"]),
        ]

    def __str__(self):
        return f"CAT {self.tipo} — {self.funcionario.nome} ({self.data_acidente})"


class eSocialEventoSST(models.Model):
    TIPO_EVENTO = [
        ("S-2210", "S-2210 — Comunicação de Acidente do Trabalho"),
        ("S-2220", "S-2220 — Monitoramento da Saúde do Trabalhador"),
        ("S-2230", "S-2230 — Afastamento Temporário"),
        ("S-2240", "S-2240 — Condições Ambientais do Trabalho"),
    ]
    STATUS = [
        ("pendente", "Pendente"),
        ("enviado", "Enviado"),
        ("transmitido", "Transmitido com Sucesso"),
        ("erro", "Erro"),
        ("retificacao", "Em Retificação"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="esocial_eventos")
    tipo_evento = models.CharField(max_length=10, choices=TIPO_EVENTO)
    status = models.CharField(max_length=20, choices=STATUS, default="pendente")
    referencia = models.CharField(max_length=200, blank=True)
    protocolo = models.CharField(max_length=60, blank=True)
    mensagem_erro = models.TextField(blank=True)
    xml_gerado = models.TextField(blank=True, default="")
    data_envio = models.DateTimeField(null=True, blank=True)
    data_retorno = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "tipo_evento"]),
        ]

    def __str__(self):
        return f"{self.tipo_evento} — {self.status} ({self.empresa.nome})"


class ASOCompartilhamento(models.Model):
    aso              = models.ForeignKey(ASOOcupacional, on_delete=models.CASCADE, related_name="compartilhamentos")
    empresa_origem   = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="asos_compartilhados")
    token            = models.CharField(max_length=64, unique=True)
    empresa_destino_cnpj = models.CharField(max_length=18, blank=True, default="")
    empresa_destino_nome = models.CharField(max_length=200, blank=True, default="")
    email_destino    = models.EmailField(blank=True, default="")
    acessos          = models.PositiveIntegerField(default=0)
    max_acessos      = models.PositiveIntegerField(default=20)
    expira_em        = models.DateTimeField()
    ativo            = models.BooleanField(default=True)
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"ASO#{self.aso_id} → {self.empresa_destino_nome or 'link público'}"


class VinculoClinicaEmpresa(models.Model):
    """Vínculo permanente entre uma clínica (prestadora de exames) e uma empresa-cliente."""
    STATUS = [
        ("pendente", "Aguardando aceitação"),
        ("ativo", "Ativo"),
        ("suspenso", "Suspenso"),
        ("recusado", "Recusado"),
    ]

    clinica = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name="vinculos_como_clinica",
        verbose_name="Clínica / prestadora",
    )
    empresa_contratante = models.ForeignKey(
        Empresa, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="vinculos_como_empresa", verbose_name="Empresa contratante (conta SolusCRT)",
    )
    empresa_cnpj = models.CharField(max_length=18, blank=True, default="", verbose_name="CNPJ da empresa")
    empresa_nome = models.CharField(max_length=200, blank=True, default="", verbose_name="Nome da empresa")
    empresa_email_convite = models.EmailField(blank=True, default="", verbose_name="E-mail para convite")
    token_convite = models.CharField(max_length=64, unique=True, default=_codigo_acesso)
    status = models.CharField(max_length=20, choices=STATUS, default="pendente")
    criado_em = models.DateTimeField(auto_now_add=True)
    aceito_em = models.DateTimeField(null=True, blank=True)
    observacoes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-criado_em"]
        unique_together = [("clinica", "empresa_contratante")]
        indexes = [
            models.Index(fields=["clinica", "status"]),
            models.Index(fields=["empresa_contratante", "status"]),
            models.Index(fields=["token_convite"]),
        ]

    def __str__(self):
        return f"{self.clinica.nome} → {self.empresa_nome or (self.empresa_contratante.nome if self.empresa_contratante else '?')}"


class ASOEnviadoClinica(models.Model):
    """Registro de um ASO enviado pela clínica diretamente para a conta da empresa no SolusCRT."""
    STATUS = [
        ("enviado", "Enviado"),
        ("visualizado", "Visualizado"),
        ("importado", "Importado ao prontuário"),
        ("rejeitado", "Rejeitado pela empresa"),
    ]

    vinculo = models.ForeignKey(VinculoClinicaEmpresa, on_delete=models.CASCADE, related_name="asos_enviados")
    aso = models.ForeignKey(ASOOcupacional, on_delete=models.CASCADE, related_name="envios_clinica")
    status = models.CharField(max_length=20, choices=STATUS, default="enviado")
    enviado_em = models.DateTimeField(auto_now_add=True)
    visualizado_em = models.DateTimeField(null=True, blank=True)
    importado_em = models.DateTimeField(null=True, blank=True)
    observacao_empresa = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-enviado_em"]
        indexes = [
            models.Index(fields=["vinculo", "status"]),
        ]

    def __str__(self):
        return f"ASO#{self.aso_id} via {self.vinculo}"


class SolicitacaoExame(models.Model):
    """Pedido de exame ocupacional emitido pela empresa e enviado à clínica credenciada."""
    TIPO_ASO = [
        ("admissional", "Admissional"),
        ("periodico", "Periódico"),
        ("retorno_trabalho", "Retorno ao Trabalho"),
        ("mudanca_risco", "Mudança de Risco"),
        ("demissional", "Demissional"),
    ]
    STATUS = [
        ("pendente", "Pendente"),
        ("agendado", "Agendado"),
        ("realizado", "Realizado"),
        ("cancelado", "Cancelado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="solicitacoes_exame")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="solicitacoes_exame")
    clinica = models.ForeignKey(
        Empresa, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitacoes_recebidas", verbose_name="Clínica destinatária",
    )
    vinculo = models.ForeignKey(
        VinculoClinicaEmpresa, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="solicitacoes",
    )
    tipo_aso = models.CharField(max_length=30, choices=TIPO_ASO)
    exames = models.TextField(blank=True, default="", verbose_name="Exames solicitados (JSON)")
    urgente = models.BooleanField(default=False)
    observacoes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS, default="pendente")
    # Clínica externa (não cadastrada no SolusCRT)
    clinica_nome_externo = models.CharField(max_length=200, blank=True, default="")
    clinica_email_externo = models.EmailField(blank=True, default="")
    email_enviado = models.BooleanField(default=False)
    email_enviado_em = models.DateTimeField(null=True, blank=True)
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_agendamento = models.DateField(null=True, blank=True)
    data_realizacao = models.DateField(null=True, blank=True)
    resposta_clinica = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-data_solicitacao"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["clinica", "status"]),
        ]

    def __str__(self):
        return f"Solicita ASO {self.tipo_aso} — {self.funcionario.nome}"


class DocumentoSST(models.Model):
    TIPO = [
        ("PGR", "Programa de Gerenciamento de Riscos"),
        ("PCMSO", "Programa de Controle Médico de Saúde Ocupacional"),
        ("LTCAT", "Laudo Técnico das Condições Ambientais"),
        ("laudo_insalubridade", "Laudo de Insalubridade"),
        ("laudo_periculosidade", "Laudo de Periculosidade"),
        ("PPP", "Perfil Profissiográfico Previdenciário"),
        ("CIPA", "Comissão Interna de Prevenção de Acidentes"),
        ("outro", "Outro Documento SST"),
    ]
    STATUS = [
        ("vigente", "Vigente"),
        ("vencido", "Vencido"),
        ("em_revisao", "Em Revisão"),
        ("nao_cadastrado", "Não Cadastrado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="documentos_sst")
    tipo = models.CharField(max_length=30, choices=TIPO)
    titulo = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS, default="vigente")
    responsavel_tecnico = models.CharField(max_length=200, blank=True)
    registro_profissional = models.CharField(max_length=60, blank=True)
    data_emissao = models.DateField(null=True, blank=True)
    data_validade = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_emissao"]
        indexes = [
            models.Index(fields=["empresa", "tipo"]),
            models.Index(fields=["empresa", "status"]),
        ]

    def __str__(self):
        return f"{self.tipo} — {self.empresa.nome} ({self.status})"


class AfastamentoSST(models.Model):
    MOTIVO = [
        ("acidente_trabalho", "Acidente de Trabalho"),
        ("doenca_ocupacional", "Doença Ocupacional"),
        ("doenca_comum", "Doença Comum"),
        ("licenca_maternidade", "Licença Maternidade"),
        ("licenca_paternidade", "Licença Paternidade"),
        ("outro", "Outro"),
    ]
    STATUS = [("ativo", "Ativo"), ("encerrado", "Encerrado"), ("retorno_programado", "Retorno Programado")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="afastamentos_sst")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="afastamentos")
    cat = models.ForeignKey(CATOcupacional, on_delete=models.SET_NULL, null=True, blank=True, related_name="afastamentos")
    motivo = models.CharField(max_length=30, choices=MOTIVO)
    cid = models.CharField(max_length=10, blank=True)
    data_inicio = models.DateField()
    data_prevista_retorno = models.DateField(null=True, blank=True)
    data_retorno_real = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS, default="ativo")
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_inicio"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "motivo"]),
        ]

    def __str__(self):
        return f"Afastamento — {self.funcionario.nome} ({self.data_inicio})"

class TreinamentoNR(models.Model):
    """Treinamentos obrigatórios por NR — registro por funcionário."""
    NR_CHOICES = [
        ("NR-5",  "NR-5 · CIPA"),
        ("NR-6",  "NR-6 · EPI"),
        ("NR-10", "NR-10 · Segurança em Eletricidade"),
        ("NR-11", "NR-11 · Transporte de Cargas"),
        ("NR-12", "NR-12 · Segurança em Máquinas"),
        ("NR-18", "NR-18 · Construção Civil"),
        ("NR-20", "NR-20 · Inflamáveis e Combustíveis"),
        ("NR-23", "NR-23 · Proteção Contra Incêndios"),
        ("NR-33", "NR-33 · Espaços Confinados"),
        ("NR-34", "NR-34 · Construção Naval"),
        ("NR-35", "NR-35 · Trabalho em Altura"),
        ("outro", "Outro"),
    ]
    STATUS = [
        ("valido",    "Válido"),
        ("vencido",   "Vencido"),
        ("pendente",  "Pendente"),
        ("agendado",  "Agendado"),
    ]

    empresa     = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="treinamentos_nr")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="treinamentos")
    nr          = models.CharField(max_length=10, choices=NR_CHOICES)
    titulo      = models.CharField(max_length=200, blank=True, default="")
    instrutor   = models.CharField(max_length=120, blank=True, default="")
    carga_horaria = models.PositiveSmallIntegerField(default=0, help_text="em horas")
    data_realizacao  = models.DateField(null=True, blank=True)
    data_validade    = models.DateField(null=True, blank=True)
    status      = models.CharField(max_length=20, choices=STATUS, default="pendente")
    certificado = models.CharField(max_length=200, blank=True, default="")
    observacoes = models.TextField(blank=True, default="")
    criado_em   = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_realizacao"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "funcionario"]),
            models.Index(fields=["empresa", "data_validade"]),
        ]

    def __str__(self):
        return f"{self.nr} — {self.funcionario.nome} ({self.status})"


# ─────────────────────────────────────────────────────────────
#  COMUNICAÇÃO — Chat + Vídeo (Teams-like)
# ─────────────────────────────────────────────────────────────

class SalaChat(models.Model):
    TIPO_DIRETO = "direto"
    TIPO_GRUPO  = "grupo"
    TIPOS = [(TIPO_DIRETO, "Direto"), (TIPO_GRUPO, "Grupo")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="salas_chat")
    tipo    = models.CharField(max_length=10, choices=TIPOS, default=TIPO_DIRETO)
    nome    = models.CharField(max_length=120, blank=True, default="")
    alias   = models.ForeignKey(
        ColaboradorAliasCorporativo, on_delete=models.CASCADE,
        null=True, blank=True, related_name="salas_diretas"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    ativo     = models.BooleanField(default=True)

    class Meta:
        unique_together = [("empresa", "alias")]
        ordering = ["-criado_em"]

    def __str__(self):
        if self.tipo == self.TIPO_DIRETO and self.alias:
            return f"Direto: {self.alias.alias_publico} ({self.empresa.nome})"
        return f"Grupo: {self.nome} ({self.empresa.nome})"


class MensagemChat(models.Model):
    ORIGEM_EMPRESA     = "empresa"
    ORIGEM_COLABORADOR = "colaborador"
    ORIGENS = [(ORIGEM_EMPRESA, "Empresa"), (ORIGEM_COLABORADOR, "Colaborador")]

    sala    = models.ForeignKey(SalaChat, on_delete=models.CASCADE, related_name="mensagens")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE)
    origem  = models.CharField(max_length=12, choices=ORIGENS)
    texto   = models.TextField(max_length=2000)
    lida    = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["sala", "criado_em"]),
            models.Index(fields=["empresa", "lida"]),
        ]

    def __str__(self):
        return f"[{self.origem}] {self.texto[:60]}"


class SessaoVideo(models.Model):
    STATUS_ATIVA     = "ativa"
    STATUS_ENCERRADA = "encerrada"
    STATUS = [(STATUS_ATIVA, "Ativa"), (STATUS_ENCERRADA, "Encerrada")]

    empresa       = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="sessoes_video")
    alias         = models.ForeignKey(
        ColaboradorAliasCorporativo, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="sessoes_video"
    )
    sala_jitsi    = models.CharField(max_length=80, unique=True, default=_codigo_acesso)
    titulo        = models.CharField(max_length=120, blank=True, default="Reunião")
    status        = models.CharField(max_length=12, choices=STATUS, default=STATUS_ATIVA)
    criado_em     = models.DateTimeField(auto_now_add=True)
    encerrado_em  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["empresa", "status"])]

    def __str__(self):
        return f"{self.titulo} ({self.empresa.nome}) — {self.status}"


# ─────────────────────────────────────────────────────────────
#  SST — Reuniões
# ─────────────────────────────────────────────────────────────

class ReuniaoSST(models.Model):
    TIPO_FUNCIONARIOS  = "funcionarios"
    TIPO_GERENCIAL     = "gerencial"
    TIPO_CLINICA       = "clinica_empresa"
    TIPO_TODOS         = "todos"
    TIPOS = [
        (TIPO_FUNCIONARIOS, "Com Funcionários"),
        (TIPO_GERENCIAL,    "Gerencial"),
        (TIPO_CLINICA,      "Clínica & Empresa"),
        (TIPO_TODOS,        "Todos"),
    ]

    STATUS_AGENDADA    = "agendada"
    STATUS_EM_ANDAMENTO = "em_andamento"
    STATUS_ENCERRADA   = "encerrada"
    STATUS_CANCELADA   = "cancelada"
    STATUS_CHOICES = [
        (STATUS_AGENDADA,     "Agendada"),
        (STATUS_EM_ANDAMENTO, "Em andamento"),
        (STATUS_ENCERRADA,    "Encerrada"),
        (STATUS_CANCELADA,    "Cancelada"),
    ]

    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="reunioes_sst")
    titulo           = models.CharField(max_length=140)
    descricao        = models.TextField(blank=True, default="")
    tipo             = models.CharField(max_length=20, choices=TIPOS, default=TIPO_FUNCIONARIOS)
    data_hora        = models.DateTimeField()
    duracao_minutos  = models.PositiveSmallIntegerField(default=60)
    sala_jitsi       = models.CharField(max_length=80, unique=True, default=_codigo_acesso)
    link_externo     = models.URLField(blank=True, default="",
                                       help_text="Link externo (Meet, Teams, Zoom). Se vazio usa Jitsi.")
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AGENDADA)
    clinica          = models.ForeignKey(
        Empresa, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reunioes_clinica_sst",
        help_text="Clínica convidada (para reuniões Clínica & Empresa)",
    )
    participantes    = models.ManyToManyField(
        FuncionarioSST, blank=True, related_name="reunioes_sst",
        help_text="Funcionários convidados. Vazio = todos.",
    )
    notificar_funcionarios = models.BooleanField(default=True)
    observacoes      = models.TextField(blank=True, default="")
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_hora"]
        indexes  = [models.Index(fields=["empresa", "status", "data_hora"])]

    def __str__(self):
        return f"{self.titulo} — {self.get_status_display()} ({self.empresa.nome})"

    @property
    def link_reuniao(self):
        if self.link_externo:
            return self.link_externo
        return f"https://meet.jit.si/{self.sala_jitsi}"


# ─────────────────────────────────────────────────────────────
#  SST — Configurações + EPI/EPC
# ─────────────────────────────────────────────────────────────

class ConfiguracaoSST(models.Model):
    GRAU_CHOICES = [("1","Grau 1"),("2","Grau 2"),("3","Grau 3"),("4","Grau 4")]

    empresa = models.OneToOneField(Empresa, on_delete=models.CASCADE, related_name="configuracao_sst")
    # SESMT
    nome_medico_coordenador = models.CharField(max_length=120, blank=True, default="")
    crm_medico              = models.CharField(max_length=30,  blank=True, default="")
    especialidade_medico    = models.CharField(max_length=80,  blank=True, default="Medicina do Trabalho")
    nome_engenheiro         = models.CharField(max_length=120, blank=True, default="")
    crea_engenheiro         = models.CharField(max_length=30,  blank=True, default="")
    nome_tecnico            = models.CharField(max_length=120, blank=True, default="")
    registro_tecnico        = models.CharField(max_length=30,  blank=True, default="")
    nome_enfermeiro         = models.CharField(max_length=120, blank=True, default="")
    coren_enfermeiro        = models.CharField(max_length=30,  blank=True, default="")
    # Alertas
    alerta_aso_dias         = models.PositiveSmallIntegerField(default=30)
    alerta_exame_dias       = models.PositiveSmallIntegerField(default=30)
    alerta_treinamento_dias = models.PositiveSmallIntegerField(default=60)
    email_alertas           = models.EmailField(blank=True, default="")
    alertas_ativos          = models.BooleanField(default=True)
    # Empresa SST
    cnpj                    = models.CharField(max_length=18,  blank=True, default="")
    cnae_principal          = models.CharField(max_length=100, blank=True, default="")
    grau_risco              = models.CharField(max_length=1, choices=GRAU_CHOICES, default="2")
    numero_funcionarios     = models.PositiveIntegerField(default=0)
    endereco_completo       = models.TextField(blank=True, default="")
    atualizado_em           = models.DateTimeField(auto_now=True)
    # eSocial digital certificate (PKCS#12 stored as base64)
    certificado_pfx_b64     = models.TextField(blank=True, default="")
    certificado_senha       = models.CharField(max_length=255, blank=True, default="")
    certificado_validade    = models.DateField(null=True, blank=True)
    certificado_nome        = models.CharField(max_length=200, blank=True, default="")
    esocial_ambiente        = models.CharField(
        max_length=20,
        choices=[("homologacao", "Homologação"), ("producao", "Produção")],
        default="homologacao",
    )

    def __str__(self):
        return f"Config SST — {self.empresa.nome}"


class EPIItem(models.Model):
    TIPO_CHOICES = [
        ("auditiva",     "Proteção Auditiva"),
        ("respiratoria", "Proteção Respiratória"),
        ("visual",       "Proteção Visual"),
        ("maos",         "Proteção de Mãos"),
        ("pes",          "Proteção de Pés"),
        ("cabeca",       "Proteção de Cabeça"),
        ("altura",       "Proteção Contra Quedas"),
        ("corpo",        "Proteção do Corpo"),
        ("outro",        "Outro"),
    ]

    empresa      = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="epis")
    nome         = models.CharField(max_length=120)
    tipo         = models.CharField(max_length=20, choices=TIPO_CHOICES)
    ca_numero    = models.CharField(max_length=20, blank=True, default="")
    validade_ca  = models.DateField(null=True, blank=True)
    fornecedor   = models.CharField(max_length=120, blank=True, default="")
    descricao    = models.TextField(blank=True, default="")
    ativo        = models.BooleanField(default=True)
    criado_em    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "nome"]
        indexes  = [models.Index(fields=["empresa", "tipo"])]

    def __str__(self):
        return f"{self.nome} (CA {self.ca_numero}) — {self.empresa.nome}"


class EntregaEPI(models.Model):
    empresa      = models.ForeignKey(Empresa,      on_delete=models.CASCADE, related_name="entregas_epi")
    funcionario  = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="entregas_epi")
    epi          = models.ForeignKey(EPIItem,       on_delete=models.CASCADE, related_name="entregas")
    data_entrega = models.DateField()
    quantidade   = models.PositiveSmallIntegerField(default=1)
    data_devolucao = models.DateField(null=True, blank=True)
    observacoes  = models.TextField(blank=True, default="")
    biometria_confirmada = models.BooleanField(default=False)
    foto_entrega_base64  = models.TextField(blank=True, default="", help_text="Foto capturada no momento da entrega")
    criado_em    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_entrega"]
        indexes  = [
            models.Index(fields=["empresa", "funcionario"]),
            models.Index(fields=["empresa", "data_entrega"]),
        ]

    def __str__(self):
        return f"{self.funcionario.nome} — {self.epi.nome} em {self.data_entrega}"


# ─── SalaChat Groups — membros ────────────────────────────────
class MembroGrupoChat(models.Model):
    sala  = models.ForeignKey(SalaChat, on_delete=models.CASCADE, related_name="membros")
    alias = models.ForeignKey(ColaboradorAliasCorporativo, on_delete=models.CASCADE, related_name="grupos_chat")

    class Meta:
        unique_together = [("sala", "alias")]

    def __str__(self):
        return f"{self.sala.nome} ← {self.alias.alias_publico}"


# ─── Farmácia Operacional ─────────────────────────────────────────────────────

class FornecedorFarmacia(models.Model):
    empresa   = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="fornecedores_farmacia")
    nome      = models.CharField(max_length=200)
    cnpj      = models.CharField(max_length=18, blank=True, default="")
    contato   = models.CharField(max_length=200, blank=True, default="")
    email     = models.EmailField(blank=True, default="")
    telefone  = models.CharField(max_length=20, blank=True, default="")
    ativo     = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class ItemFarmacia(models.Model):
    CATEGORIA_CHOICES = [
        ("medicamento", "Medicamento"), ("material", "Material"),
        ("insumo", "Insumo"), ("outro", "Outro"),
    ]
    empresa         = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="itens_farmacia")
    fornecedor      = models.ForeignKey(FornecedorFarmacia, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens")
    nome            = models.CharField(max_length=200)
    codigo          = models.CharField(max_length=50, blank=True, default="")
    categoria       = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default="medicamento")
    descricao       = models.TextField(blank=True, default="")
    unidade_medida  = models.CharField(max_length=30, default="unidade")
    estoque_minimo  = models.PositiveIntegerField(default=0)
    estoque_atual   = models.IntegerField(default=0)
    ativo           = models.BooleanField(default=True)
    criado_em       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class MovimentoEstoque(models.Model):
    TIPO_CHOICES = [
        ("entrada", "Entrada"), ("saida", "Saída"),
        ("ajuste", "Ajuste"), ("vencimento", "Vencimento"),
    ]
    empresa           = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="movimentos_estoque")
    item              = models.ForeignKey(ItemFarmacia, on_delete=models.CASCADE, related_name="movimentos")
    tipo              = models.CharField(max_length=20, choices=TIPO_CHOICES)
    quantidade        = models.IntegerField()
    estoque_anterior  = models.IntegerField()
    estoque_posterior = models.IntegerField()
    motivo            = models.TextField(blank=True, default="")
    responsavel       = models.CharField(max_length=200, blank=True, default="")
    data_movimento    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_movimento"]

    def __str__(self):
        return f"{self.tipo} {self.quantidade} {self.item.nome}"


class PedidoCompraFarmacia(models.Model):
    STATUS_CHOICES = [
        ("rascunho", "Rascunho"), ("enviado", "Enviado"),
        ("aprovado", "Aprovado"), ("recebido", "Recebido"), ("cancelado", "Cancelado"),
    ]
    empresa      = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pedidos_compra_farmacia")
    fornecedor   = models.ForeignKey(FornecedorFarmacia, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="rascunho")
    observacoes  = models.TextField(blank=True, default="")
    criado_em    = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.pk} - {self.status}"


class ItemPedidoCompra(models.Model):
    pedido               = models.ForeignKey(PedidoCompraFarmacia, on_delete=models.CASCADE, related_name="itens")
    item                 = models.ForeignKey(ItemFarmacia, on_delete=models.CASCADE)
    quantidade_solicitada = models.PositiveIntegerField()
    quantidade_recebida  = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["item__nome"]


class DispensacaoMedicamento(models.Model):
    empresa       = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="dispensacoes")
    item          = models.ForeignKey(ItemFarmacia, on_delete=models.CASCADE, related_name="dispensacoes")
    paciente_nome = models.CharField(max_length=200)
    paciente_cpf  = models.CharField(max_length=14, blank=True, default="")
    quantidade    = models.PositiveIntegerField()
    responsavel   = models.CharField(max_length=200, blank=True, default="")
    observacoes   = models.TextField(blank=True, default="")
    dispensado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-dispensado_em"]

    def __str__(self):
        return f"{self.item.nome} → {self.paciente_nome}"


# ─── Farmácia — Módulos Avançados ─────────────────────────────────────────────

class PacienteFarmacia(models.Model):
    SEXO_CHOICES = [("M", "Masculino"), ("F", "Feminino"), ("O", "Outro")]
    empresa           = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pacientes_farmacia")
    nome              = models.CharField(max_length=200)
    cpf               = models.CharField(max_length=14, blank=True, default="")
    data_nascimento   = models.DateField(null=True, blank=True)
    sexo              = models.CharField(max_length=1, choices=SEXO_CHOICES, blank=True, default="")
    telefone          = models.CharField(max_length=20, blank=True, default="")
    email             = models.EmailField(blank=True, default="")
    endereco          = models.CharField(max_length=300, blank=True, default="")
    alergias          = models.TextField(blank=True, default="", help_text="Alergias e contraindicações conhecidas")
    condicoes_cronicas = models.TextField(blank=True, default="", help_text="CIDs ou condições crônicas em acompanhamento")
    medicamentos_uso_continuo = models.TextField(blank=True, default="")
    ativo             = models.BooleanField(default=True)
    criado_em         = models.DateTimeField(auto_now_add=True)
    atualizado_em     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class ReceitaMedica(models.Model):
    TIPO_CHOICES = [
        ("simples", "Receita Simples"),
        ("especial_branca", "Receita Especial Branca (2 vias)"),
        ("especial_amarela", "Receita Especial Amarela (Psicotrópico)"),
        ("alto_custo", "Medicamento de Alto Custo"),
    ]
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("dispensada", "Dispensada"),
        ("vencida", "Vencida"),
        ("cancelada", "Cancelada"),
    ]
    empresa         = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="receitas_farmacia")
    paciente        = models.ForeignKey(PacienteFarmacia, on_delete=models.SET_NULL, null=True, blank=True, related_name="receitas")
    paciente_nome   = models.CharField(max_length=200, blank=True, default="")
    paciente_cpf    = models.CharField(max_length=14, blank=True, default="")
    tipo            = models.CharField(max_length=25, choices=TIPO_CHOICES, default="simples")
    numero_receita  = models.CharField(max_length=50, blank=True, default="")
    medico_nome     = models.CharField(max_length=200, blank=True, default="")
    medico_crm      = models.CharField(max_length=30, blank=True, default="")
    data_emissao    = models.DateField()
    data_validade   = models.DateField(null=True, blank=True)
    item            = models.ForeignKey(ItemFarmacia, on_delete=models.SET_NULL, null=True, blank=True, related_name="receitas")
    medicamento_descricao = models.TextField(blank=True, default="")
    quantidade      = models.PositiveIntegerField(default=1)
    posologia       = models.TextField(blank=True, default="")
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    dispensacao     = models.ForeignKey(DispensacaoMedicamento, on_delete=models.SET_NULL, null=True, blank=True, related_name="receitas")
    observacoes     = models.TextField(blank=True, default="")
    criado_em       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Receita {self.numero_receita or self.pk} — {self.paciente_nome or (self.paciente.nome if self.paciente else '')}"


class InventarioFarmacia(models.Model):
    STATUS_CHOICES = [
        ("aberto", "Em andamento"),
        ("concluido", "Concluído"),
        ("cancelado", "Cancelado"),
    ]
    empresa       = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="inventarios_farmacia")
    descricao     = models.CharField(max_length=200, blank=True, default="")
    status        = models.CharField(max_length=15, choices=STATUS_CHOICES, default="aberto")
    responsavel   = models.CharField(max_length=200, blank=True, default="")
    iniciado_em   = models.DateTimeField(auto_now_add=True)
    concluido_em  = models.DateTimeField(null=True, blank=True)
    observacoes   = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-iniciado_em"]

    def __str__(self):
        return f"Inventário {self.pk} — {self.status} ({self.iniciado_em.date()})"


class ItemInventario(models.Model):
    inventario        = models.ForeignKey(InventarioFarmacia, on_delete=models.CASCADE, related_name="itens")
    item              = models.ForeignKey(ItemFarmacia, on_delete=models.CASCADE)
    estoque_sistema   = models.IntegerField()
    estoque_contado   = models.IntegerField(null=True, blank=True)
    diferenca         = models.IntegerField(null=True, blank=True)
    ajustado          = models.BooleanField(default=False)
    observacao        = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["item__nome"]
        unique_together = [("inventario", "item")]

    def __str__(self):
        return f"{self.item.nome} — contado: {self.estoque_contado}"


class DescarteItemFarmacia(models.Model):
    MOTIVO_CHOICES = [
        ("vencimento", "Vencimento"),
        ("avaria", "Avaria / Dano físico"),
        ("contaminacao", "Contaminação"),
        ("recolhimento", "Recolhimento ANVISA"),
        ("outro", "Outro"),
    ]
    empresa       = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="descartes_farmacia")
    item          = models.ForeignKey(ItemFarmacia, on_delete=models.CASCADE, related_name="descartes")
    lote          = models.ForeignKey("LoteMedicamento", on_delete=models.SET_NULL, null=True, blank=True)
    motivo        = models.CharField(max_length=20, choices=MOTIVO_CHOICES, default="vencimento")
    quantidade    = models.PositiveIntegerField()
    responsavel   = models.CharField(max_length=200, blank=True, default="")
    empresa_descarte = models.CharField(max_length=200, blank=True, default="", help_text="Empresa responsável pelo descarte")
    numero_manifesto = models.CharField(max_length=100, blank=True, default="")
    observacoes   = models.TextField(blank=True, default="")
    data_descarte = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_descarte"]

    def __str__(self):
        return f"Descarte {self.item.nome} ({self.quantidade}) — {self.motivo}"


# ─── Hospital Operacional ─────────────────────────────────────────────────────

class DepartamentoHospital(models.Model):
    empresa            = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="departamentos_hospital")
    nome               = models.CharField(max_length=200)
    tipo               = models.CharField(max_length=50, blank=True, default="")
    capacidade_leitos  = models.PositiveIntegerField(default=0)
    responsavel        = models.CharField(max_length=200, blank=True, default="")
    ativo              = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class LeitoHospital(models.Model):
    STATUS_CHOICES = [
        ("disponivel", "Disponível"), ("ocupado", "Ocupado"),
        ("manutencao", "Manutenção"), ("reservado", "Reservado"),
    ]
    empresa       = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="leitos_hospital")
    departamento  = models.ForeignKey(DepartamentoHospital, on_delete=models.CASCADE, related_name="leitos")
    numero        = models.CharField(max_length=20)
    tipo          = models.CharField(max_length=50, blank=True, default="")
    status        = models.CharField(max_length=20, choices=STATUS_CHOICES, default="disponivel")

    class Meta:
        ordering = ["departamento__nome", "numero"]
        unique_together = [("empresa", "numero")]

    def __str__(self):
        return f"Leito {self.numero} - {self.departamento.nome}"


class PacienteHospital(models.Model):
    SEXO_CHOICES = [("M", "Masculino"), ("F", "Feminino"), ("O", "Outro")]
    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pacientes_hospital")
    nome             = models.CharField(max_length=200)
    cpf              = models.CharField(max_length=14, blank=True, default="")
    data_nascimento  = models.DateField(null=True, blank=True)
    sexo             = models.CharField(max_length=1, choices=SEXO_CHOICES, blank=True, default="")
    telefone         = models.CharField(max_length=20, blank=True, default="")
    endereco         = models.TextField(blank=True, default="")
    tipo_sanguineo   = models.CharField(max_length=5, blank=True, default="")
    alergias         = models.TextField(blank=True, default="")
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class TriagemHospital(models.Model):
    PRIORIDADE_CHOICES = [
        ("vermelho", "Vermelho - Emergência"), ("laranja", "Laranja - Muito Urgente"),
        ("amarelo", "Amarelo - Urgente"), ("verde", "Verde - Pouco Urgente"),
        ("azul", "Azul - Não Urgente"),
    ]
    empresa            = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="triagens_hospital")
    paciente           = models.ForeignKey(PacienteHospital, on_delete=models.CASCADE, related_name="triagens")
    prioridade         = models.CharField(max_length=20, choices=PRIORIDADE_CHOICES)
    queixa_principal   = models.TextField()
    pressao_arterial   = models.CharField(max_length=20, blank=True, default="")
    temperatura        = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    saturacao          = models.PositiveSmallIntegerField(null=True, blank=True)
    frequencia_cardiaca = models.PositiveSmallIntegerField(null=True, blank=True)
    responsavel        = models.CharField(max_length=200, blank=True, default="")
    triado_em          = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-triado_em"]

    def __str__(self):
        return f"Triagem {self.paciente.nome} - {self.prioridade}"


class InternacaoHospital(models.Model):
    STATUS_CHOICES = [
        ("ativa", "Ativa"), ("alta", "Alta"),
        ("transferido", "Transferido"), ("obito", "Óbito"),
    ]
    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="internacoes_hospital")
    paciente            = models.ForeignKey(PacienteHospital, on_delete=models.CASCADE, related_name="internacoes")
    leito               = models.ForeignKey(LeitoHospital, on_delete=models.SET_NULL, null=True, blank=True, related_name="internacoes")
    diagnostico         = models.TextField()
    medico_responsavel  = models.CharField(max_length=200, blank=True, default="")
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativa")
    data_entrada        = models.DateTimeField(auto_now_add=True)
    data_saida          = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-data_entrada"]

    def __str__(self):
        return f"Internação {self.paciente.nome} - {self.status}"


class EvolucaoClinica(models.Model):
    internacao    = models.ForeignKey(InternacaoHospital, on_delete=models.CASCADE, related_name="evolucoes")
    descricao     = models.TextField()
    responsavel   = models.CharField(max_length=200, blank=True, default="")
    registrado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registrado_em"]

    def __str__(self):
        return f"Evolução {self.internacao.paciente.nome} - {self.registrado_em.date()}"


# ─── Governo — Gestão Avançada ────────────────────────────────────────────────

class ProgramaSaudeGov(models.Model):
    STATUS_CHOICES = [
        ("planejamento", "Planejamento"), ("ativo", "Ativo"),
        ("suspenso", "Suspenso"), ("concluido", "Concluído"),
    ]
    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="programas_saude_gov")
    nome                = models.CharField(max_length=200)
    descricao           = models.TextField(blank=True, default="")
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planejamento")
    populacao_alvo      = models.TextField(blank=True, default="")
    orcamento_previsto  = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    orcamento_executado = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    data_inicio         = models.DateField(null=True, blank=True)
    data_fim_prevista   = models.DateField(null=True, blank=True)
    responsavel         = models.CharField(max_length=200, blank=True, default="")
    criado_em           = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.nome


class IndicadorSaudeGov(models.Model):
    TIPO_CHOICES = [
        ("quantitativo", "Quantitativo"), ("percentual", "Percentual"), ("indice", "Índice"),
    ]
    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="indicadores_saude_gov")
    programa            = models.ForeignKey(ProgramaSaudeGov, on_delete=models.SET_NULL, null=True, blank=True, related_name="indicadores")
    nome                = models.CharField(max_length=200)
    descricao           = models.TextField(blank=True, default="")
    tipo                = models.CharField(max_length=20, choices=TIPO_CHOICES, default="quantitativo")
    meta                = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    valor_atual         = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    unidade             = models.CharField(max_length=50, blank=True, default="")
    periodo_referencia  = models.CharField(max_length=50, blank=True, default="")
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class OrcamentoSaudeGov(models.Model):
    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="orcamentos_saude_gov")
    ano              = models.PositiveSmallIntegerField()
    total_previsto   = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_executado  = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    fonte_recurso    = models.CharField(max_length=200, blank=True, default="")
    observacoes      = models.TextField(blank=True, default="")
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-ano"]
        unique_together = [("empresa", "ano")]

    def __str__(self):
        return f"Orçamento {self.ano}"


class PlanoAcaoGov(models.Model):
    PRIORIDADE_CHOICES = [("alta", "Alta"), ("media", "Média"), ("baixa", "Baixa")]
    STATUS_CHOICES = [
        ("pendente", "Pendente"), ("em_andamento", "Em Andamento"),
        ("concluido", "Concluído"), ("cancelado", "Cancelado"),
    ]
    empresa      = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="planos_acao_gov")
    programa     = models.ForeignKey(ProgramaSaudeGov, on_delete=models.SET_NULL, null=True, blank=True, related_name="planos_acao")
    titulo       = models.CharField(max_length=300)
    descricao    = models.TextField(blank=True, default="")
    responsavel  = models.CharField(max_length=200, blank=True, default="")
    prioridade   = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default="media")
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    prazo        = models.DateField(null=True, blank=True)
    progresso    = models.PositiveSmallIntegerField(default=0)
    criado_em    = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.titulo


# ─── SST Agendamento ───────────────────────────────────────────────────────────

class AgendamentoSST(models.Model):
    TIPO_CHOICES = [
        ("exame_admissional", "Exame Admissional"),
        ("exame_periodico", "Exame Periódico"),
        ("exame_retorno", "Retorno ao Trabalho"),
        ("exame_demissional", "Exame Demissional"),
        ("exame_mudanca", "Mudança de Função"),
        ("consulta", "Consulta Médica"),
        ("treinamento", "Treinamento NR"),
        ("outro", "Outro"),
    ]
    STATUS_CHOICES = [
        ("agendado", "Agendado"),
        ("confirmado", "Confirmado"),
        ("realizado", "Realizado"),
        ("faltou", "Não Compareceu"),
        ("cancelado", "Cancelado"),
        ("reagendado", "Reagendado"),
    ]
    empresa         = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="agendamentos_sst")
    funcionario     = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="agendamentos")
    tipo            = models.CharField(max_length=30, choices=TIPO_CHOICES, default="exame_periodico")
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="agendado")
    data_hora       = models.DateTimeField()
    local           = models.CharField(max_length=300, blank=True, default="")
    medico          = models.CharField(max_length=200, blank=True, default="")
    observacoes     = models.TextField(blank=True, default="")
    lembrete_enviado = models.BooleanField(default=False)
    criado_em       = models.DateTimeField(auto_now_add=True)
    atualizado_em   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_hora"]

    def __str__(self):
        return f"{self.funcionario.nome} – {self.get_tipo_display()} em {self.data_hora:%d/%m/%Y}"


# ─── Farmácia — Lotes e Rastreabilidade ───────────────────────────────────────

class LoteMedicamento(models.Model):
    """Rastreabilidade de lote de medicamento em estoque (FEFO)."""
    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="lotes_medicamento")
    item             = models.ForeignKey("ItemFarmacia", on_delete=models.CASCADE, related_name="lotes")
    numero_lote      = models.CharField(max_length=100)
    fabricante       = models.CharField(max_length=200, blank=True, default="")
    data_fabricacao  = models.DateField(null=True, blank=True)
    data_validade    = models.DateField()
    quantidade_inicial = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_atual = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    nota_fiscal      = models.CharField(max_length=100, blank=True, default="")
    fornecedor       = models.ForeignKey("FornecedorFarmacia", on_delete=models.SET_NULL, null=True, blank=True)
    bloqueado        = models.BooleanField(default=False, help_text="Lote bloqueado para dispensação (recall, suspeita de desvio)")
    motivo_bloqueio  = models.TextField(blank=True, default="")
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_validade"]  # FEFO — primeiro a vencer, primeiro a sair
        unique_together = [("empresa", "item", "numero_lote")]

    def __str__(self):
        return f"Lote {self.numero_lote} — {self.item.nome} (val: {self.data_validade})"

    @property
    def vencido(self):
        from datetime import date
        return self.data_validade < date.today()

    @property
    def dias_para_vencer(self):
        from datetime import date
        return (self.data_validade - date.today()).days


# ─── Hospital — Prescrição Médica ──────────────────────────────────────────────

class PrescricaoMedica(models.Model):
    """Prescrição médica vinculada a uma internação hospitalar."""
    STATUS_CHOICES = [
        ("ativa", "Ativa"),
        ("suspensa", "Suspensa"),
        ("concluida", "Concluída"),
        ("cancelada", "Cancelada"),
    ]
    VIA_CHOICES = [
        ("oral", "Oral"), ("ev", "Endovenosa"), ("im", "Intramuscular"),
        ("sc", "Subcutânea"), ("inalatoria", "Inalatória"), ("topica", "Tópica"),
        ("sublingual", "Sublingual"), ("outra", "Outra"),
    ]
    internacao       = models.ForeignKey("InternacaoHospital", on_delete=models.CASCADE, related_name="prescricoes")
    medicamento      = models.CharField(max_length=300)
    dose             = models.CharField(max_length=100, blank=True, default="")
    via              = models.CharField(max_length=20, choices=VIA_CHOICES, default="oral")
    frequencia       = models.CharField(max_length=100, blank=True, default="",
                                        help_text="Ex: 8/8h, 1x ao dia, SN")
    duracao_dias     = models.PositiveSmallIntegerField(null=True, blank=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativa")
    medico           = models.CharField(max_length=200, blank=True, default="")
    observacoes      = models.TextField(blank=True, default="")
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.medicamento} — {self.dose} ({self.via})"


# ─── Governo — Publicação / Ato Normativo ─────────────────────────────────────

class AtoNormativoGov(models.Model):
    """Atos normativos, portarias e resoluções de saúde pública."""
    TIPO_CHOICES = [
        ("portaria", "Portaria"),
        ("resolucao", "Resolução"),
        ("decreto", "Decreto"),
        ("lei", "Lei"),
        ("instrucao", "Instrução Normativa"),
        ("nota_tecnica", "Nota Técnica"),
        ("outro", "Outro"),
    ]
    STATUS_CHOICES = [
        ("vigente", "Vigente"),
        ("revogado", "Revogado"),
        ("suspenso", "Suspenso"),
        ("em_consulta", "Em Consulta Pública"),
    ]
    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="atos_normativos")
    tipo             = models.CharField(max_length=20, choices=TIPO_CHOICES, default="portaria")
    numero           = models.CharField(max_length=50, blank=True, default="")
    titulo           = models.CharField(max_length=400)
    ementa           = models.TextField(blank=True, default="")
    data_publicacao  = models.DateField(null=True, blank=True)
    data_vigencia    = models.DateField(null=True, blank=True)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="vigente")
    orgao_emissor    = models.CharField(max_length=200, blank=True, default="")
    url_documento    = models.URLField(blank=True, default="")
    programa         = models.ForeignKey("ProgramaSaudeGov", on_delete=models.SET_NULL, null=True, blank=True, related_name="atos")
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_publicacao", "-criado_em"]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.numero} — {self.titulo[:60]}"


# ─── Governo — Fase 2: Rede, Vigilância, Regulação, Produção, Contratos ──────

UF_CHOICES = [
    ("AC","Acre"),("AL","Alagoas"),("AP","Amapá"),("AM","Amazonas"),
    ("BA","Bahia"),("CE","Ceará"),("DF","Distrito Federal"),("ES","Espírito Santo"),
    ("GO","Goiás"),("MA","Maranhão"),("MT","Mato Grosso"),("MS","Mato Grosso do Sul"),
    ("MG","Minas Gerais"),("PA","Pará"),("PB","Paraíba"),("PR","Paraná"),
    ("PE","Pernambuco"),("PI","Piauí"),("RJ","Rio de Janeiro"),("RN","Rio Grande do Norte"),
    ("RS","Rio Grande do Sul"),("RO","Rondônia"),("RR","Roraima"),("SC","Santa Catarina"),
    ("SP","São Paulo"),("SE","Sergipe"),("TO","Tocantins"),
]


class UnidadeSaude(models.Model):
    TIPO_CHOICES = [
        ("ubs","UBS — Unidade Básica de Saúde"),("upa","UPA 24h"),
        ("caps_i","CAPS I"),("caps_ii","CAPS II"),("caps_iii","CAPS III — 24h"),
        ("caps_ad","CAPS AD"),("caps_inf","CAPS Infantil"),("hospital","Hospital"),
        ("amb","Ambulatório Especializado"),("ceo","CEO — Centro Odontológico"),
        ("policlinica","Policlínica"),("cerest","CEREST"),("laboratorio","Laboratório Público"),
        ("cco","CCO — Central de Regulação"),("outro","Outro"),
    ]
    STATUS_CHOICES = [
        ("ativa","Ativa"),("inativa","Inativa"),("obras","Em Obras"),("interditada","Interditada"),
    ]
    empresa         = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="unidades_saude")
    cnes            = models.CharField(max_length=7, blank=True, default="")
    nome            = models.CharField(max_length=200)
    tipo            = models.CharField(max_length=20, choices=TIPO_CHOICES)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativa")
    municipio       = models.CharField(max_length=100)
    uf              = models.CharField(max_length=2, choices=UF_CHOICES)
    bairro          = models.CharField(max_length=100, blank=True, default="")
    endereco        = models.CharField(max_length=300, blank=True, default="")
    telefone        = models.CharField(max_length=20, blank=True, default="")
    latitude        = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    longitude       = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    populacao_referenciada = models.PositiveIntegerField(default=0)
    leitos_sus      = models.PositiveSmallIntegerField(default=0)
    leitos_uti      = models.PositiveSmallIntegerField(default=0)
    diretor         = models.CharField(max_length=200, blank=True, default="")
    criado_em       = models.DateTimeField(auto_now_add=True)
    atualizado_em   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["municipio","nome"]
        indexes = [
            models.Index(fields=["empresa","tipo"]),
            models.Index(fields=["empresa","municipio"]),
        ]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()}) — {self.municipio}/{self.uf}"


class EquipeSaude(models.Model):
    TIPO_CHOICES = [
        ("esf","eSF — Saúde da Família"),("esb","eSB — Saúde Bucal"),
        ("nasf","NASF-AB"),("acs","ACS — Agentes"),("outro","Outro"),
    ]
    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="equipes_saude")
    unidade          = models.ForeignKey(UnidadeSaude, on_delete=models.CASCADE, related_name="equipes")
    nome             = models.CharField(max_length=200)
    tipo             = models.CharField(max_length=10, choices=TIPO_CHOICES, default="esf")
    ine              = models.CharField(max_length=10, blank=True, default="")
    area_codigo      = models.CharField(max_length=10, blank=True, default="")
    populacao_cadastrada = models.PositiveIntegerField(default=0)
    ativa            = models.BooleanField(default=True)
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["unidade","nome"]

    def __str__(self):
        return f"{self.nome} ({self.get_tipo_display()}) — {self.unidade.nome}"


class SurtoEpidemiologico(models.Model):
    STATUS_CHOICES = [
        ("ativo","Ativo — Investigação em Curso"),("controlado","Controlado"),("encerrado","Encerrado"),
    ]
    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="surtos_epidemiologicos")
    doenca           = models.CharField(max_length=100)
    municipio        = models.CharField(max_length=100)
    uf               = models.CharField(max_length=2)
    bairro           = models.CharField(max_length=100, blank=True, default="")
    data_inicio      = models.DateField()
    data_encerramento = models.DateField(null=True, blank=True)
    total_casos      = models.PositiveIntegerField(default=0)
    total_obitos     = models.PositiveIntegerField(default=0)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativo")
    nivel_alerta     = models.CharField(max_length=10, choices=[
        ("verde","Verde"),("amarelo","Amarelo"),("laranja","Laranja"),("vermelho","Vermelho"),
    ], default="amarelo")
    acoes_resposta   = models.TextField(blank=True, default="")
    responsavel_investigacao = models.CharField(max_length=200, blank=True, default="")
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_inicio"]

    def __str__(self):
        return f"Surto {self.doenca} — {self.municipio}/{self.uf}"


class NotificacaoCompulsoria(models.Model):
    DOENCA_CHOICES = [
        ("dengue","Dengue"),("zika","Zika Vírus"),("chikungunya","Chikungunya"),
        ("malaria","Malária"),("febre_amarela","Febre Amarela"),
        ("leishmaniose_visceral","Leishmaniose Visceral"),("leishmaniose_tegumentar","Leishmaniose Tegumentar"),
        ("leptospirose","Leptospirose"),("esquistossomose","Esquistossomose"),
        ("doenca_chagas","Doença de Chagas"),("tuberculose","Tuberculose"),
        ("hanseniase","Hanseníase"),("hiv_aids","HIV/AIDS"),("sifilis","Sífilis"),
        ("sifilis_congenita","Sífilis Congênita"),("hepatite_a","Hepatite A"),
        ("hepatite_b","Hepatite B"),("hepatite_c","Hepatite C"),
        ("meningite","Meningite"),("sarampo","Sarampo"),("rubeola","Rubéola"),
        ("coqueluche","Coqueluche"),("difteria","Difteria"),("tetano","Tétano"),
        ("raiva","Raiva"),("antraz","Antraz/Carbúnculo"),
        ("influenza_grave","Influenza Grave"),("covid19","COVID-19"),
        ("mpox","Mpox"),("botulismo","Botulismo"),("colera","Cólera"),
        ("plague","Peste"),("variola","Varíola"),("ebola","Ebola"),
        ("intoxicacao","Intoxicação Exógena"),("acidente_trabalho","Acidente de Trabalho Grave"),
        ("violencia","Violência Interpessoal/Autoprovocada"),("outro","Outro"),
    ]
    EVOLUCAO_CHOICES = [
        ("ativo","Em Acompanhamento"),("curado","Curado"),("obito","Óbito"),("ignorado","Ignorado/Inconclusivo"),
    ]
    empresa               = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="notificacoes_compulsorias")
    doenca                = models.CharField(max_length=30, choices=DOENCA_CHOICES)
    data_notificacao      = models.DateField()
    data_inicio_sintomas  = models.DateField(null=True, blank=True)
    municipio_notificacao = models.CharField(max_length=100)
    uf_notificacao        = models.CharField(max_length=2)
    unidade_notificante   = models.ForeignKey(UnidadeSaude, on_delete=models.SET_NULL, null=True, blank=True, related_name="notificacoes")
    idade_paciente        = models.PositiveSmallIntegerField(null=True, blank=True)
    sexo                  = models.CharField(max_length=1, choices=[("M","Masculino"),("F","Feminino"),("I","Ignorado")], default="I")
    zona                  = models.CharField(max_length=10, choices=[("urbana","Urbana"),("rural","Rural"),("periurbana","Periurbana")], default="urbana")
    status_investigacao   = models.CharField(max_length=20, choices=[("aberto","Aberto"),("em_investigacao","Em Investigação"),("encerrado","Encerrado")], default="aberto")
    evolucao              = models.CharField(max_length=20, choices=EVOLUCAO_CHOICES, default="ativo")
    surto                 = models.ForeignKey(SurtoEpidemiologico, on_delete=models.SET_NULL, null=True, blank=True, related_name="notificacoes")
    observacoes           = models.TextField(blank=True, default="")
    criado_em             = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_notificacao"]
        indexes = [
            models.Index(fields=["empresa","doenca"]),
            models.Index(fields=["empresa","data_notificacao"]),
            models.Index(fields=["empresa","municipio_notificacao"]),
        ]

    def __str__(self):
        return f"Notif. {self.get_doenca_display()} — {self.data_notificacao}"


class RegulacaoLeito(models.Model):
    TIPO_LEITO_CHOICES = [
        ("uti_adulto","UTI Adulto"),("uti_neo","UTI Neonatal"),("uti_ped","UTI Pediátrica"),
        ("clinico","Clínico"),("cirurgico","Cirúrgico"),("obstetricia","Obstetrícia"),
        ("psiquiatria","Psiquiatria"),("queimados","Queimados"),("outro","Outro"),
    ]
    PRIORIDADE_CHOICES = [
        ("emergencia","Emergência"),("urgencia","Urgência"),("eletivo","Eletivo"),
    ]
    STATUS_CHOICES = [
        ("solicitado","Solicitado"),("regulado","Regulado — Aguardando Vaga"),
        ("internado","Internado"),("cancelado","Cancelado"),("obito_espera","Óbito na Fila"),
    ]
    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="regulacoes_leito")
    numero_solicitacao  = models.CharField(max_length=20, unique=True)
    unidade_origem      = models.ForeignKey(UnidadeSaude, on_delete=models.SET_NULL, null=True, blank=True, related_name="solicitacoes_regulacao")
    unidade_destino     = models.ForeignKey(UnidadeSaude, on_delete=models.SET_NULL, null=True, blank=True, related_name="vagas_regulacao")
    tipo_leito          = models.CharField(max_length=20, choices=TIPO_LEITO_CHOICES)
    prioridade          = models.CharField(max_length=20, choices=PRIORIDADE_CHOICES, default="urgencia")
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="solicitado")
    cid_principal       = models.CharField(max_length=10, blank=True, default="")
    diagnostico         = models.CharField(max_length=300, blank=True, default="")
    idade_paciente      = models.PositiveSmallIntegerField(null=True, blank=True)
    municipio_origem    = models.CharField(max_length=100, blank=True, default="")
    medico_solicitante  = models.CharField(max_length=200, blank=True, default="")
    data_solicitacao    = models.DateTimeField(auto_now_add=True)
    data_regulacao      = models.DateTimeField(null=True, blank=True)
    data_internacao     = models.DateTimeField(null=True, blank=True)
    tempo_espera_horas  = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    observacoes         = models.TextField(blank=True, default="")
    criado_em           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_solicitacao"]
        indexes = [
            models.Index(fields=["empresa","status"]),
            models.Index(fields=["empresa","tipo_leito"]),
        ]

    def __str__(self):
        return f"Reg. {self.numero_solicitacao} — {self.get_tipo_leito_display()}"


class ProducaoAmbulatorial(models.Model):
    empresa                   = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="producoes_ambulatoriais")
    unidade                   = models.ForeignKey(UnidadeSaude, on_delete=models.CASCADE, related_name="producoes")
    competencia               = models.CharField(max_length=7)  # YYYY-MM
    consultas_basicas         = models.PositiveIntegerField(default=0)
    consultas_especializadas  = models.PositiveIntegerField(default=0)
    procedimentos_basicos     = models.PositiveIntegerField(default=0)
    procedimentos_especializados = models.PositiveIntegerField(default=0)
    exames_realizados         = models.PositiveIntegerField(default=0)
    visitas_domiciliares      = models.PositiveIntegerField(default=0)
    acolhimentos              = models.PositiveIntegerField(default=0)
    criado_em                 = models.DateTimeField(auto_now_add=True)
    atualizado_em             = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa","unidade","competencia")]
        ordering = ["-competencia"]

    def __str__(self):
        return f"Produção {self.unidade.nome} — {self.competencia}"


class MetaPrevine(models.Model):
    INDICADOR_CHOICES = [
        ("prenatal_6","Pré-natal — ≥6 consultas + 1º trim."),
        ("prenatal_sifilis_hiv","Pré-natal — Sífilis e HIV"),
        ("gestante_odonto","Gestantes com atendimento odontológico"),
        ("consumo_alcool","Usuários de álcool/drogas com avaliação"),
        ("hipertensos","Hipertensos com PA aferida"),
        ("diabeticos","Diabéticos com HbA1c solicitada"),
        ("criancas_obesidade","Crianças <5 anos com avaliação nutricional"),
        ("saude_bucal_ab","Saúde bucal — procedimentos clínicos"),
        ("visita_puerpera","Puérperas com visita na 1ª semana"),
    ]
    empresa              = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="metas_previne")
    indicador            = models.CharField(max_length=30, choices=INDICADOR_CHOICES)
    competencia          = models.CharField(max_length=7)  # YYYY-MM
    municipio            = models.CharField(max_length=100, blank=True, default="")
    denominador          = models.PositiveIntegerField(default=0)
    numerador            = models.PositiveIntegerField(default=0)
    meta_percentual      = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    resultado_percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    atingiu_meta         = models.BooleanField(default=False)
    criado_em            = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("empresa","indicador","competencia","municipio")]
        ordering = ["-competencia","indicador"]

    def __str__(self):
        return f"Previne {self.get_indicador_display()} — {self.competencia}"


class ContratoGestao(models.Model):
    TIPO_CHOICES = [
        ("hospital","Hospital Contratado"),("clinica","Clínica/AMB"),("laboratorio","Laboratório"),
        ("imagem","Imagem/Diagnóstico"),("sadt","SADT"),("oss","OSS"),
        ("convenio_federal","Convênio Federal"),("convenio_estadual","Convênio Estadual"),("outro","Outro"),
    ]
    STATUS_CHOICES = [
        ("vigente","Vigente"),("vencido","Vencido"),("suspenso","Suspenso"),("rescindido","Rescindido"),
    ]
    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="contratos_gestao")
    numero_contrato     = models.CharField(max_length=50)
    fornecedor_nome     = models.CharField(max_length=300)
    fornecedor_cnpj     = models.CharField(max_length=18, blank=True, default="")
    tipo                = models.CharField(max_length=20, choices=TIPO_CHOICES)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="vigente")
    objeto              = models.TextField()
    valor_total         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_mensal        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data_inicio         = models.DateField()
    data_fim            = models.DateField()
    gestor_contrato     = models.CharField(max_length=200, blank=True, default="")
    producao_prevista   = models.JSONField(default=dict)
    producao_realizada  = models.JSONField(default=dict)
    observacoes         = models.TextField(blank=True, default="")
    criado_em           = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_inicio"]
        indexes = [
            models.Index(fields=["empresa","status"]),
            models.Index(fields=["empresa","tipo"]),
        ]

    def __str__(self):
        return f"Contrato {self.numero_contrato} — {self.fornecedor_nome[:40]}"


class AtendimentoUrgencia(models.Model):
    TIPO_UNIDADE_CHOICES = [
        ("samu","SAMU 192"),("upa","UPA 24h"),("pronto_socorro","Pronto-Socorro"),("cco","CCO"),
    ]
    DESFECHO_CHOICES = [
        ("alta","Alta"),("internado","Internado"),("transferido","Transferido"),
        ("obito","Óbito"),("evasao","Evasão"),
    ]
    empresa                  = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="atendimentos_urgencia")
    unidade                  = models.ForeignKey(UnidadeSaude, on_delete=models.SET_NULL, null=True, blank=True, related_name="atendimentos_urgencia")
    tipo_unidade             = models.CharField(max_length=20, choices=TIPO_UNIDADE_CHOICES)
    data_atendimento         = models.DateField()
    total_atendimentos       = models.PositiveIntegerField(default=0)
    vermelho                 = models.PositiveIntegerField(default=0)
    laranja                  = models.PositiveIntegerField(default=0)
    amarelo                  = models.PositiveIntegerField(default=0)
    verde                    = models.PositiveIntegerField(default=0)
    azul                     = models.PositiveIntegerField(default=0)
    obitos                   = models.PositiveIntegerField(default=0)
    tempo_espera_medio_min   = models.PositiveSmallIntegerField(default=0)
    criado_em                = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_atendimento"]
        unique_together = [("empresa","unidade","data_atendimento")]

    def __str__(self):
        return f"Urgência {self.get_tipo_unidade_display()} — {self.data_atendimento}"


# ── Aliases para retrocompatibilidade com código de conformidade ──────────────
ExameMedico = ExameOcupacional
ASOSSE = ASOOcupacional
CATRegistro = CATOcupacional


# ─── Contratos de Saúde / Convênios ───────────────────────────────────────────

class ContratoSaude(models.Model):
    TIPO_CHOICES = [
        ("plano_saude", "Plano de Saúde"),
        ("convenio_medico", "Convênio Médico"),
        ("seguro_saude", "Seguro Saúde"),
        ("convenio_odontologico", "Convênio Odontológico"),
        ("medicina_trabalho", "Medicina do Trabalho"),
        ("outro", "Outro"),
    ]
    STATUS_CHOICES = [
        ("ativo", "Ativo"),
        ("vencido", "Vencido"),
        ("suspenso", "Suspenso"),
        ("em_renovacao", "Em Renovação"),
        ("cancelado", "Cancelado"),
    ]
    ABRANGENCIA_CHOICES = [
        ("municipal", "Municipal"),
        ("estadual", "Estadual"),
        ("nacional", "Nacional"),
        ("internacional", "Internacional"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="contratos_saude")
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES)
    operadora = models.CharField(max_length=300)
    numero_contrato = models.CharField(max_length=100, blank=True, default="")
    registro_ans = models.CharField(max_length=50, blank=True, default="", help_text="Registro na ANS")
    descricao = models.CharField(max_length=500, blank=True, default="")
    abrangencia = models.CharField(max_length=20, choices=ABRANGENCIA_CHOICES, default="nacional")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    valor_mensal = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    valor_per_capita = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_beneficiarios = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativo")
    cobertura_detalhes = models.TextField(blank=True, default="")
    carencias = models.TextField(blank=True, default="")
    contato_operadora = models.CharField(max_length=200, blank=True, default="")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_inicio"]

    @property
    def dias_para_vencer(self):
        if not self.data_fim:
            return None
        from datetime import date
        return (self.data_fim - date.today()).days

    @property
    def vencido(self):
        if not self.data_fim:
            return False
        from datetime import date
        return self.data_fim < date.today()

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.operadora}"


class BeneficiarioContrato(models.Model):
    contrato = models.ForeignKey(ContratoSaude, on_delete=models.CASCADE, related_name="beneficiarios")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="contratos_saude")
    numero_carteirinha = models.CharField(max_length=100, blank=True, default="")
    data_inclusao = models.DateField(null=True, blank=True)
    data_exclusao = models.DateField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    dependentes = models.PositiveSmallIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["funcionario__nome"]
        unique_together = [("contrato", "funcionario")]

    def __str__(self):
        return f"{self.funcionario.nome} - {self.contrato.operadora}"


# ─── Indicadores Epidemiológicos com Série Temporal ───────────────────────────

class SerieEpidemiologica(models.Model):
    GRANULARIDADE_CHOICES = [
        ("diario", "Diário"),
        ("semanal", "Semanal"),
        ("mensal", "Mensal"),
        ("trimestral", "Trimestral"),
        ("anual", "Anual"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="series_epidemiologicas")
    nome = models.CharField(max_length=200)
    descricao = models.TextField(blank=True, default="")
    unidade = models.CharField(max_length=50, default="casos", help_text="Ex: casos, óbitos, internações")
    granularidade = models.CharField(max_length=15, choices=GRANULARIDADE_CHOICES, default="mensal")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        unique_together = [("empresa", "nome")]

    def __str__(self):
        return f"{self.nome} ({self.unidade})"


class PontoSerie(models.Model):
    serie = models.ForeignKey(SerieEpidemiologica, on_delete=models.CASCADE, related_name="pontos")
    data_referencia = models.DateField()
    valor = models.DecimalField(max_digits=14, decimal_places=4)
    fonte = models.CharField(max_length=200, blank=True, default="")
    observacoes = models.CharField(max_length=300, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data_referencia"]
        unique_together = [("serie", "data_referencia")]

    def __str__(self):
        return f"{self.serie.nome} - {self.data_referencia}: {self.valor}"


# ─── Empresa SST — PGR, planos de ação e vacinação ───────────────────────────

class RiscoOcupacional(models.Model):
    """Risco identificado no PGR (Programa de Gerenciamento de Riscos)."""
    TIPO_CHOICES = [
        ("fisico", "Físico"),
        ("quimico", "Químico"),
        ("biologico", "Biológico"),
        ("ergonomico", "Ergonômico"),
        ("acidente", "Acidente / Mecânico"),
        ("psicossocial", "Psicossocial"),
    ]
    NIVEL_CHOICES = [
        ("I", "I - Muito Baixo"),
        ("II", "II - Baixo"),
        ("III", "III - Médio"),
        ("IV", "IV - Alto"),
        ("V", "V - Muito Alto / Crítico"),
    ]
    STATUS_CHOICES = [
        ("identificado", "Identificado"),
        ("em_controle", "Em Controle"),
        ("controlado", "Controlado"),
        ("residual", "Risco Residual"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="riscos_ocupacionais")
    setor = models.CharField(max_length=150)
    tipo_risco = models.CharField(max_length=20, choices=TIPO_CHOICES)
    agente = models.CharField(max_length=200, help_text="Ex: ruido, poeira, virus, postura inadequada")
    descricao = models.TextField(blank=True, default="")
    nivel = models.CharField(max_length=5, choices=NIVEL_CHOICES, default="III")
    probabilidade = models.PositiveSmallIntegerField(
        default=3,
        help_text="1=Raro  2=Improvavel  3=Possivel  4=Provavel  5=Quase certo",
    )
    severidade = models.PositiveSmallIntegerField(
        default=3,
        help_text="1=Insignificante  2=Leve  3=Moderado  4=Grave  5=Catastrofico",
    )
    nr_referencia = models.CharField(max_length=50, blank=True, default="", help_text="Ex: NR-15, NR-17, NR-36")
    medida_controle_existente = models.TextField(blank=True, default="")
    medida_controle_proposta = models.TextField(blank=True, default="")
    prazo = models.DateField(null=True, blank=True)
    responsavel = models.CharField(max_length=150, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="identificado")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-probabilidade", "-severidade"]

    @property
    def grr(self):
        return self.probabilidade * self.severidade

    def __str__(self):
        return f"[{self.tipo_risco}] {self.agente} - {self.setor}"


class PostoTrabalho(models.Model):
    """Posto/função de trabalho com exposição a agentes nocivos — base do S-2240."""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="postos_trabalho")
    nome = models.CharField(max_length=200, verbose_name="Nome do posto / função")
    setor = models.CharField(max_length=150, blank=True, default="")
    descricao = models.TextField(blank=True, default="", verbose_name="Descrição das atividades")
    responsavel_tecnico = models.CharField(max_length=180, blank=True, default="", verbose_name="Responsável técnico (Eng. Segurança / Médico)")
    responsavel_registro = models.CharField(max_length=30, blank=True, default="", verbose_name="CRM ou CREA do responsável")
    data_laudo = models.DateField(null=True, blank=True, verbose_name="Data do laudo (LTCAT/PPRA/PGR)")
    vigencia_inicio = models.CharField(max_length=7, blank=True, default="", verbose_name="Início de vigência (AAAA-MM)")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["setor", "nome"]
        indexes = [models.Index(fields=["empresa", "ativo"])]

    def __str__(self):
        return f"{self.nome} — {self.setor or 'sem setor'}"


class AgenteNocivoPostoTrabalho(models.Model):
    """Agente nocivo (físico, químico ou biológico) de um posto de trabalho — eSocial Tabela 24."""
    TIPO_AGENTE = [
        ("fisico", "Físico"),
        ("quimico", "Químico"),
        ("biologico", "Biológico"),
    ]
    # Agentes eSocial Tabela 24 — principais
    COD_AGENTE_CHOICES = [
        # Físicos
        ("01.01.001", "Ruído contínuo / intermitente"),
        ("01.01.002", "Ruído de impacto"),
        ("01.02.001", "Vibração em membros superiores"),
        ("01.02.002", "Vibração em corpo inteiro"),
        ("01.03.001", "Calor (IBUTG)"),
        ("01.04.001", "Radiação ionizante"),
        ("01.05.001", "Pressão hiperbárica"),
        ("01.06.001", "Frio"),
        ("01.07.001", "Umidade"),
        # Químicos
        ("02.01.001", "Arsênio e compostos"),
        ("02.01.002", "Benzeno"),
        ("02.01.003", "Chumbo e compostos"),
        ("02.01.004", "Mercúrio e compostos"),
        ("02.01.005", "Sílica livre cristalizada"),
        ("02.01.006", "Asbestos / Amianto"),
        ("02.01.007", "Manganês e compostos"),
        ("02.01.008", "Cromo hexavalente"),
        ("02.01.009", "Poeiras minerais em geral"),
        ("02.01.010", "Poeiras orgânicas (madeira, couro, etc.)"),
        ("02.01.011", "Fumos metálicos"),
        ("02.01.012", "Névoas e neblinas"),
        ("02.01.013", "Gases e vapores químicos em geral"),
        # Biológicos
        ("03.01.001", "Vírus — Hepatite B (HBV)"),
        ("03.01.002", "Vírus — HIV"),
        ("03.01.003", "Vírus — outros"),
        ("03.02.001", "Bactérias — tuberculose (Mycobacterium)"),
        ("03.02.002", "Bactérias — outras"),
        ("03.03.001", "Protozoários"),
        ("03.04.001", "Fungos"),
        ("03.05.001", "Parasitas / helmintos"),
    ]

    posto = models.ForeignKey(PostoTrabalho, on_delete=models.CASCADE, related_name="agentes_nocivos")
    tipo_agente = models.CharField(max_length=15, choices=TIPO_AGENTE)
    cod_agente = models.CharField(max_length=20, choices=COD_AGENTE_CHOICES, verbose_name="Código eSocial (Tabela 24)")
    dsc_agente = models.CharField(max_length=300, blank=True, default="", verbose_name="Descrição complementar do agente")
    tec_medicao = models.CharField(max_length=200, blank=True, default="", verbose_name="Técnica de medição utilizada")
    intensidade = models.CharField(max_length=50, blank=True, default="", verbose_name="Intensidade / concentração medida")
    limite_tolerancia = models.CharField(max_length=50, blank=True, default="", verbose_name="Limite de tolerância (NR/ACGIH)")
    epc_descricao = models.CharField(max_length=300, blank=True, default="", verbose_name="EPC instalado (proteção coletiva)")
    epc_eficaz = models.BooleanField(default=False, verbose_name="EPC é eficaz na neutralização")
    epi_descricao = models.CharField(max_length=300, blank=True, default="", verbose_name="EPI fornecido (proteção individual)")
    epi_ca = models.CharField(max_length=20, blank=True, default="", verbose_name="Número CA do EPI")
    epi_eficaz = models.BooleanField(default=False, verbose_name="EPI é eficaz na neutralização")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo_agente", "cod_agente"]

    def __str__(self):
        return f"{self.get_cod_agente_display()} — {self.posto.nome}"


class FuncionarioPostoTrabalho(models.Model):
    """Vínculo de um funcionário a um posto de trabalho para o S-2240."""
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="postos_vinculados")
    posto = models.ForeignKey(PostoTrabalho, on_delete=models.CASCADE, related_name="funcionarios_vinculados")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-data_inicio"]
        indexes = [models.Index(fields=["posto", "data_fim"])]

    def ativo(self):
        return self.data_fim is None

    def __str__(self):
        return f"{self.funcionario.nome} → {self.posto.nome}"


class PlanoAcaoSST(models.Model):
    """Plano de ação SST vinculado ou não a um risco ocupacional."""
    ORIGEM_CHOICES = [
        ("risco", "Risco Ocupacional"),
        ("cat", "CAT / Acidente"),
        ("afastamento", "Afastamento"),
        ("auditoria", "Auditoria Interna"),
        ("conformidade", "Não-Conformidade"),
        ("outro", "Outro"),
    ]
    PRIORIDADE_CHOICES = [
        ("baixa", "Baixa"),
        ("media", "Média"),
        ("alta", "Alta"),
        ("critica", "Crítica"),
    ]
    STATUS_CHOICES = [
        ("aberto", "Aberto"),
        ("em_andamento", "Em Andamento"),
        ("concluido", "Concluído"),
        ("cancelado", "Cancelado"),
        ("atrasado", "Atrasado"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="planos_acao_sst")
    risco = models.ForeignKey(RiscoOcupacional, on_delete=models.SET_NULL, null=True, blank=True, related_name="planos_acao")
    titulo = models.CharField(max_length=250)
    descricao = models.TextField(blank=True, default="")
    origem = models.CharField(max_length=20, choices=ORIGEM_CHOICES, default="risco")
    prioridade = models.CharField(max_length=10, choices=PRIORIDADE_CHOICES, default="media")
    responsavel = models.CharField(max_length=150, blank=True, default="")
    setor = models.CharField(max_length=150, blank=True, default="")
    data_prazo = models.DateField(null=True, blank=True)
    data_conclusao = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aberto")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return self.titulo


class CampanhaVacinacao(models.Model):
    STATUS_CHOICES = [
        ("planejada", "Planejada"),
        ("em_andamento", "Em Andamento"),
        ("concluida", "Concluída"),
        ("cancelada", "Cancelada"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="campanhas_vacinacao")
    nome = models.CharField(max_length=200)
    vacina = models.CharField(max_length=150, help_text="Ex: Influenza, Hepatite B, COVID-19")
    descricao = models.TextField(blank=True, default="")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    meta_doses = models.PositiveIntegerField(default=0)
    doses_aplicadas = models.PositiveIntegerField(default=0)
    local = models.CharField(max_length=200, blank=True, default="")
    responsavel = models.CharField(max_length=150, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planejada")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_inicio"]

    def __str__(self):
        return f"{self.nome} - {self.vacina}"


class RegistroVacinacao(models.Model):
    DOSE_CHOICES = [
        ("1a_dose", "1ª Dose"),
        ("2a_dose", "2ª Dose"),
        ("3a_dose", "3ª Dose"),
        ("reforco", "Reforço"),
        ("dose_unica", "Dose Única"),
    ]

    campanha = models.ForeignKey(CampanhaVacinacao, on_delete=models.CASCADE, related_name="registros")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="vacinacoes")
    data_aplicacao = models.DateField()
    dose = models.CharField(max_length=15, choices=DOSE_CHOICES, default="dose_unica")
    lote_vacina = models.CharField(max_length=80, blank=True, default="")
    aplicador = models.CharField(max_length=150, blank=True, default="")
    observacoes = models.CharField(max_length=300, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_aplicacao"]
        unique_together = [("campanha", "funcionario", "dose")]

    def __str__(self):
        return f"{self.funcionario.nome} - {self.campanha.vacina} ({self.get_dose_display()})"


# ─── REDE (NETWORK) ──────────────────────────────────────────────────────────

class Rede(models.Model):
    """Network grouping multiple pharmacy/hospital units under one brand."""
    TIPO_FARMACIA = "farmacia"
    TIPO_HOSPITAL = "hospital"
    TIPO_MISTO = "misto"
    TIPOS = [
        (TIPO_FARMACIA, "Rede de Farmácias"),
        (TIPO_HOSPITAL, "Rede Hospitalar"),
        (TIPO_MISTO, "Rede Mista"),
    ]

    nome = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_FARMACIA)
    cnpj_raiz = models.CharField(max_length=18, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")
    descricao = models.TextField(blank=True, default="")
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)
    codigo_convite = models.CharField(max_length=24, blank=True, default="", unique=True, null=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class UnidadeRede(models.Model):
    """A pharmacy or hospital unit, either standalone or part of a Rede."""
    TIPO_FARMACIA = "farmacia"
    TIPO_HOSPITAL = "hospital"
    TIPOS = [
        (TIPO_FARMACIA, "Farmácia"),
        (TIPO_HOSPITAL, "Hospital"),
    ]

    empresa = models.OneToOneField(
        "Empresa",
        on_delete=models.CASCADE,
        related_name="unidade_rede",
    )
    rede = models.ForeignKey(
        Rede,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="unidades",
    )
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_FARMACIA)
    nome_unidade = models.CharField(max_length=200, blank=True, default="")
    codigo_unidade = models.CharField(max_length=20, blank=True, default="")
    endereco = models.TextField(blank=True, default="")
    cidade = models.CharField(max_length=100, blank=True, default="")
    estado = models.CharField(max_length=2, blank=True, default="")
    responsavel = models.CharField(max_length=150, blank=True, default="")
    telefone = models.CharField(max_length=20, blank=True, default="")
    ativa = models.BooleanField(default=True)
    criada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome_unidade"]

    def __str__(self):
        return self.nome_unidade or str(self.empresa)


class TransferenciaEstoque(models.Model):
    """Stock transfer request between units of the same network."""
    STATUS_PENDENTE = "pendente"
    STATUS_APROVADA = "aprovada"
    STATUS_ENVIADA = "enviada"
    STATUS_RECEBIDA = "recebida"
    STATUS_CANCELADA = "cancelada"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_APROVADA, "Aprovada"),
        (STATUS_ENVIADA, "Enviada"),
        (STATUS_RECEBIDA, "Recebida"),
        (STATUS_CANCELADA, "Cancelada"),
    ]

    rede = models.ForeignKey(Rede, on_delete=models.CASCADE, related_name="transferencias")
    unidade_solicitante = models.ForeignKey(
        UnidadeRede, on_delete=models.CASCADE, related_name="transferencias_solicitadas"
    )
    unidade_fornecedora = models.ForeignKey(
        UnidadeRede, on_delete=models.CASCADE, related_name="transferencias_fornecidas"
    )
    item_farmacia = models.ForeignKey(
        "ItemFarmacia",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="transferencias",
    )
    nome_item = models.CharField(max_length=200, blank=True, default="")
    quantidade_solicitada = models.DecimalField(max_digits=10, decimal_places=3)
    quantidade_aprovada = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    motivo = models.TextField(blank=True, default="")
    observacoes = models.TextField(blank=True, default="")
    urgente = models.BooleanField(default=False)
    solicitado_por = models.CharField(max_length=150, blank=True, default="")
    aprovado_por = models.CharField(max_length=150, blank=True, default="")
    solicitado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-solicitado_em"]

    def __str__(self):
        return f"Transferência #{self.id} — {self.nome_item}"


class MensagemRede(models.Model):
    """Internal message between units within a network."""
    TIPO_GERAL = "geral"
    TIPO_TRANSFERENCIA = "transferencia"
    TIPO_ALERTA = "alerta"
    TIPO_CHOICES = [
        (TIPO_GERAL, "Mensagem Geral"),
        (TIPO_TRANSFERENCIA, "Sobre Transferência"),
        (TIPO_ALERTA, "Alerta"),
    ]

    rede = models.ForeignKey(Rede, on_delete=models.CASCADE, related_name="mensagens")
    remetente = models.ForeignKey(
        UnidadeRede, on_delete=models.CASCADE, related_name="mensagens_enviadas"
    )
    destinatario = models.ForeignKey(
        UnidadeRede, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="mensagens_recebidas",
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_GERAL)
    assunto = models.CharField(max_length=200, blank=True, default="")
    corpo = models.TextField()
    transferencia = models.ForeignKey(
        TransferenciaEstoque, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="mensagens"
    )
    lida = models.BooleanField(default=False)
    enviada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-enviada_em"]

    def __str__(self):
        return f"[{self.tipo}] {self.remetente} → {self.destinatario or 'todos'}"


# ─── PLANO DE SAÚDE ──────────────────────────────────────────────────────────

class PlanoSaude(models.Model):
    """Health insurance operator (operadora)."""
    STATUS_ATIVO = "ativo"
    STATUS_INATIVO = "inativo"
    STATUS_CHOICES = [
        (STATUS_ATIVO, "Ativo"),
        (STATUS_INATIVO, "Inativo"),
    ]
    MODALIDADE_CHOICES = [
        ("cooperativa", "Cooperativa Médica"),
        ("autogestao", "Autogestão"),
        ("seguradora", "Seguradora"),
        ("filantropico", "Filantrópico"),
        ("outro", "Outro"),
    ]

    empresa = models.ForeignKey(
        "Empresa", on_delete=models.CASCADE,
        related_name="planos_saude", null=True, blank=True,
    )
    nome = models.CharField(max_length=200)
    registro_ans = models.CharField(max_length=20, blank=True, default="")
    cnpj = models.CharField(max_length=18, blank=True, default="")
    modalidade = models.CharField(max_length=20, choices=MODALIDADE_CHOICES, blank=True, default="")
    telefone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    site = models.URLField(blank=True, default="")
    abrangencia = models.CharField(max_length=50, blank=True, default="nacional")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ATIVO)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class BeneficiarioPlano(models.Model):
    """Patient enrolled in a health plan."""
    SITUACAO_ATIVO = "ativo"
    SITUACAO_SUSPENSO = "suspenso"
    SITUACAO_CANCELADO = "cancelado"
    SITUACAO_CHOICES = [
        (SITUACAO_ATIVO, "Ativo"),
        (SITUACAO_SUSPENSO, "Suspenso"),
        (SITUACAO_CANCELADO, "Cancelado"),
    ]

    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="beneficiarios")
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=14, blank=True, default="")
    numero_carteirinha = models.CharField(max_length=50, blank=True, default="")
    data_nascimento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=1, blank=True, default="")
    telefone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    data_inicio_vigencia = models.DateField(null=True, blank=True)
    data_fim_vigencia = models.DateField(null=True, blank=True)
    situacao = models.CharField(max_length=15, choices=SITUACAO_CHOICES, default=SITUACAO_ATIVO)
    plano_tipo = models.CharField(max_length=100, blank=True, default="")
    acomodacao = models.CharField(max_length=50, blank=True, default="enfermaria", choices=[("enfermaria","Enfermaria"),("apartamento","Apartamento"),("uti","UTI")])
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} — {self.plano.nome}"


class PrestadorPlanoSaude(models.Model):
    """Prestador credenciado da operadora: hospital, clinica, laboratorio, imagem."""
    STATUS_CREDENCIADO = "credenciado"
    STATUS_IMPLANTACAO = "implantacao"
    STATUS_SUSPENSO = "suspenso"
    STATUS_DESCREDENCIADO = "descredenciado"
    STATUS_CHOICES = [
        (STATUS_CREDENCIADO, "Credenciado"),
        (STATUS_IMPLANTACAO, "Em implantação"),
        (STATUS_SUSPENSO, "Suspenso"),
        (STATUS_DESCREDENCIADO, "Descredenciado"),
    ]
    TIPO_HOSPITAL = "hospital"
    TIPO_CLINICA = "clinica"
    TIPO_LABORATORIO = "laboratorio"
    TIPO_IMAGEM = "imagem"
    TIPO_PRONTO_ATENDIMENTO = "pronto_atendimento"
    TIPO_HOMECARE = "homecare"
    TIPO_CHOICES = [
        (TIPO_HOSPITAL, "Hospital"),
        (TIPO_CLINICA, "Clínica / AMB"),
        (TIPO_LABORATORIO, "Laboratório"),
        (TIPO_IMAGEM, "Imagem / Diagnóstico"),
        (TIPO_PRONTO_ATENDIMENTO, "Pronto Atendimento"),
        (TIPO_HOMECARE, "Home Care"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="prestadores_plano")
    codigo_rede = models.CharField(max_length=30, blank=True, default="")
    nome_fantasia = models.CharField(max_length=200)
    razao_social = models.CharField(max_length=200, blank=True, default="")
    cnpj = models.CharField(max_length=18, blank=True, default="")
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default=TIPO_CLINICA)
    registro_cnes = models.CharField(max_length=30, blank=True, default="")
    especialidades = models.TextField(blank=True, default="")
    cidade = models.CharField(max_length=100, blank=True, default="")
    estado = models.CharField(max_length=2, blank=True, default="")
    telefone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    contato_responsavel = models.CharField(max_length=150, blank=True, default="")
    sla_autorizacao_horas = models.PositiveSmallIntegerField(default=72)
    portal_ativo = models.BooleanField(default=True)
    score_qualidade = models.PositiveSmallIntegerField(default=85)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREDENCIADO)
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome_fantasia"]

    def __str__(self):
        return self.nome_fantasia


class CarenciaBeneficiario(models.Model):
    """Carência (waiting period) per beneficiary and procedure type."""
    TIPO_CONSULTA = "consulta"
    TIPO_EXAME = "exame"
    TIPO_INTERNACAO = "internacao"
    TIPO_PARTO = "parto"
    TIPO_URGENCIA = "urgencia"
    TIPO_ODONTO = "odontologico"
    TIPO_CHOICES = [
        (TIPO_CONSULTA, "Consultas"),
        (TIPO_EXAME, "Exames e Procedimentos"),
        (TIPO_INTERNACAO, "Internações"),
        (TIPO_PARTO, "Parto"),
        (TIPO_URGENCIA, "Urgência e Emergência"),
        (TIPO_ODONTO, "Odontológico"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="carencias")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="carencias")
    tipo_procedimento = models.CharField(max_length=30, choices=TIPO_CHOICES)
    data_inicio = models.DateField()
    dias_carencia = models.PositiveIntegerField(default=0, help_text="Período de carência em dias")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["data_inicio"]
        unique_together = [("beneficiario", "tipo_procedimento")]

    @property
    def data_fim(self):
        from datetime import timedelta
        return self.data_inicio + timedelta(days=self.dias_carencia)

    @property
    def ativa(self):
        from datetime import date
        return date.today() < self.data_fim

    @property
    def dias_restantes(self):
        from datetime import date, timedelta
        fim = self.data_inicio + timedelta(days=self.dias_carencia)
        delta = (fim - date.today()).days
        return max(0, delta)

    def __str__(self):
        return f"Carência {self.tipo_procedimento} — {self.beneficiario}"


class GuiaAutorizacao(models.Model):
    """Prior authorization request (guia) for procedure or medication."""
    TIPO_CONSULTA = "consulta"
    TIPO_EXAME = "exame"
    TIPO_INTERNACAO = "internacao"
    TIPO_MEDICAMENTO = "medicamento"
    TIPO_PROCEDIMENTO = "procedimento"
    TIPO_CHOICES = [
        (TIPO_CONSULTA, "Consulta"),
        (TIPO_EXAME, "Exame"),
        (TIPO_INTERNACAO, "Internação"),
        (TIPO_MEDICAMENTO, "Medicamento de Alto Custo"),
        (TIPO_PROCEDIMENTO, "Procedimento Cirúrgico"),
    ]
    STATUS_SOLICITADA = "solicitada"
    STATUS_EM_ANALISE = "em_analise"
    STATUS_AUTORIZADA = "autorizada"
    STATUS_NEGADA = "negada"
    STATUS_CANCELADA = "cancelada"
    STATUS_CHOICES = [
        (STATUS_SOLICITADA, "Solicitada"),
        (STATUS_EM_ANALISE, "Em Análise"),
        (STATUS_AUTORIZADA, "Autorizada"),
        (STATUS_NEGADA, "Negada"),
        (STATUS_CANCELADA, "Cancelada"),
    ]
    PRIORIDADE_ELETIVA = "eletiva"
    PRIORIDADE_URGENTE = "urgente"
    PRIORIDADE_ALTA_COMPLEXIDADE = "alta_complexidade"
    PRIORIDADE_INTERNACAO = "internacao"
    PRIORIDADE_CHOICES = [
        (PRIORIDADE_ELETIVA, "Eletiva"),
        (PRIORIDADE_URGENTE, "Urgente"),
        (PRIORIDADE_ALTA_COMPLEXIDADE, "Alta complexidade"),
        (PRIORIDADE_INTERNACAO, "Internação"),
    ]
    FILA_TRIAGEM = "triagem"
    FILA_AUDITORIA_CLINICA = "auditoria_clinica"
    FILA_AUDITORIA_MEDICA = "auditoria_medica"
    FILA_PENDENCIA_DOCUMENTAL = "pendencia_documental"
    FILA_DEVOLVIDA_PRESTADOR = "devolvida_prestador"
    FILA_AUTORIZADA = "autorizada"
    FILA_NEGADA = "negada"
    FILA_CHOICES = [
        (FILA_TRIAGEM, "Triagem"),
        (FILA_AUDITORIA_CLINICA, "Auditoria clínica"),
        (FILA_AUDITORIA_MEDICA, "Auditoria médica"),
        (FILA_PENDENCIA_DOCUMENTAL, "Pendência documental"),
        (FILA_DEVOLVIDA_PRESTADOR, "Devolvida ao prestador"),
        (FILA_AUTORIZADA, "Autorizada"),
        (FILA_NEGADA, "Negada"),
    ]

    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="guias")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="guias")
    prestador = models.ForeignKey(
        PrestadorPlanoSaude, on_delete=models.SET_NULL, null=True, blank=True, related_name="guias"
    )
    unidade = models.ForeignKey(
        UnidadeRede, on_delete=models.SET_NULL, null=True, blank=True, related_name="guias"
    )
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    numero_guia = models.CharField(max_length=50, blank=True, default="")
    codigo_procedimento = models.CharField(max_length=20, blank=True, default="")
    descricao_procedimento = models.TextField()
    cid = models.CharField(max_length=10, blank=True, default="")
    medico_solicitante = models.CharField(max_length=150, blank=True, default="")
    crm_medico = models.CharField(max_length=30, blank=True, default="")
    quantidade = models.PositiveIntegerField(default=1)
    valor_estimado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SOLICITADA)
    prioridade_clinica = models.CharField(max_length=30, choices=PRIORIDADE_CHOICES, default=PRIORIDADE_ELETIVA)
    fila_status = models.CharField(max_length=30, choices=FILA_CHOICES, default=FILA_TRIAGEM)
    auditor_responsavel = models.CharField(max_length=150, blank=True, default="")
    prazo_sla_em = models.DateTimeField(null=True, blank=True)
    observacao_auditoria = models.TextField(blank=True, default="")
    documentos_pendentes = models.TextField(blank=True, default="")
    justificativa_negativa = models.TextField(blank=True, default="")
    numero_autorizacao = models.CharField(max_length=50, blank=True, default="")
    validade_autorizacao = models.DateField(null=True, blank=True)
    solicitada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-solicitada_em"]

    def __str__(self):
        return f"Guia #{self.numero_guia or self.id} — {self.beneficiario.nome}"


class Sinistro(models.Model):
    """Sinistro / ocorrência de saúde registrada pela operadora."""
    TIPO_CHOICES = [
        ("consulta", "Consulta"),
        ("internacao", "Internação"),
        ("exame", "Exame / Diagnóstico"),
        ("procedimento", "Procedimento Cirúrgico"),
        ("urgencia", "Urgência / Emergência"),
        ("medicamento", "Medicamento de Alto Custo"),
        ("outro", "Outro"),
    ]
    STATUS_CHOICES = [
        ("aberto", "Aberto"),
        ("em_analise", "Em Análise"),
        ("aprovado", "Aprovado"),
        ("negado", "Negado"),
        ("pago", "Pago"),
        ("cancelado", "Cancelado"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="sinistros")
    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="sinistros")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="sinistros")
    guia = models.ForeignKey(GuiaAutorizacao, on_delete=models.SET_NULL, null=True, blank=True, related_name="sinistros")
    numero_sinistro = models.CharField(max_length=60, blank=True, default="")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="consulta")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aberto")
    cid = models.CharField(max_length=10, blank=True, default="")
    descricao_procedimento = models.TextField(blank=True, default="")
    prestador = models.CharField(max_length=200, blank=True, default="")
    medico = models.CharField(max_length=150, blank=True, default="")
    data_atendimento = models.DateField(null=True, blank=True)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data_abertura = models.DateTimeField(auto_now_add=True)
    data_fechamento = models.DateTimeField(null=True, blank=True)
    observacao = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-data_abertura"]

    def __str__(self):
        return f"Sinistro #{self.numero_sinistro or self.id} — {self.beneficiario.nome}"


class Reembolso(models.Model):
    """Solicitação de reembolso de despesa médica pelo beneficiário."""
    STATUS_CHOICES = [
        ("solicitado", "Solicitado"),
        ("em_analise", "Em Análise"),
        ("aprovado", "Aprovado"),
        ("pago", "Pago"),
        ("negado", "Negado"),
        ("cancelado", "Cancelado"),
    ]
    TIPO_DESPESA_CHOICES = [
        ("consulta", "Consulta Médica"),
        ("exame", "Exame / Diagnóstico"),
        ("internacao", "Internação"),
        ("medicamento", "Medicamento"),
        ("terapia", "Terapia / Reabilitação"),
        ("odonto", "Odontologia"),
        ("outro", "Outro"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="reembolsos")
    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="reembolsos")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="reembolsos")
    sinistro = models.ForeignKey(Sinistro, on_delete=models.SET_NULL, null=True, blank=True, related_name="reembolsos")
    numero_reembolso = models.CharField(max_length=60, blank=True, default="")
    tipo_despesa = models.CharField(max_length=20, choices=TIPO_DESPESA_CHOICES, default="consulta")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="solicitado")
    valor_solicitado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_aprovado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_pagamento = models.DateField(null=True, blank=True)
    banco = models.CharField(max_length=100, blank=True, default="")
    agencia = models.CharField(max_length=20, blank=True, default="")
    conta = models.CharField(max_length=30, blank=True, default="")
    descricao = models.TextField(blank=True, default="")
    observacao = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-data_solicitacao"]

    def __str__(self):
        return f"Reembolso #{self.numero_reembolso or self.id} — {self.beneficiario.nome}"


class GlosaItem(models.Model):
    """Item glosado em um sinistro — controle de glosas e recursos."""
    STATUS_GLOSADO = "glosado"
    STATUS_RECURSO_ENVIADO = "recurso_enviado"
    STATUS_RECURSO_ACEITO = "recurso_aceito"
    STATUS_MANTIDA = "mantida"
    STATUS_CHOICES = [
        (STATUS_GLOSADO, "Glosado"),
        (STATUS_RECURSO_ENVIADO, "Recurso Enviado"),
        (STATUS_RECURSO_ACEITO, "Recurso Aceito"),
        (STATUS_MANTIDA, "Glosa Mantida"),
    ]

    sinistro = models.ForeignKey(Sinistro, on_delete=models.CASCADE, related_name="glosas")
    codigo_procedimento = models.CharField(max_length=20, blank=True, default="")
    descricao = models.TextField()
    valor_original = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_glosado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    motivo = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_GLOSADO)
    data_glosa = models.DateField(null=True, blank=True)
    data_recurso = models.DateField(null=True, blank=True)
    resposta_recurso = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Glosa #{self.id} — {self.descricao[:40]}"


class CoparticipacaoRegra(models.Model):
    """Regra de coparticipação do beneficiário por tipo de atendimento."""
    TIPO_CONSULTA = "consulta"
    TIPO_EXAME = "exame"
    TIPO_INTERNACAO = "internacao"
    TIPO_CIRURGIA = "cirurgia"
    TIPO_TERAPIA = "terapia"
    TIPO_URGENCIA = "urgencia"
    TIPO_CHOICES = [
        (TIPO_CONSULTA, "Consulta"),
        (TIPO_EXAME, "Exame / Diagnóstico"),
        (TIPO_INTERNACAO, "Internação"),
        (TIPO_CIRURGIA, "Cirurgia"),
        (TIPO_TERAPIA, "Terapia / Reabilitação"),
        (TIPO_URGENCIA, "Urgência / Emergência"),
    ]

    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="regras_coparticipacao")
    tipo_atendimento = models.CharField(max_length=20, choices=TIPO_CHOICES)
    percentual = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                                     help_text="% cobrado do beneficiário (0 a 100)")
    valor_fixo = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                     help_text="Valor fixo por evento (R$)")
    teto_mensal = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                      help_text="Teto mensal de coparticipação (R$), se houver")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["plano", "tipo_atendimento"]
        unique_together = [("plano", "tipo_atendimento")]

    def __str__(self):
        return f"{self.plano.nome} — {self.get_tipo_atendimento_display()}"


class FaturamentoBeneficiario(models.Model):
    """Fatura mensal de um beneficiário (mensalidade + coparticipação)."""
    STATUS_PENDENTE = "pendente"
    STATUS_PAGO = "pago"
    STATUS_VENCIDO = "vencido"
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_PAGO, "Pago"),
        (STATUS_VENCIDO, "Vencido"),
        (STATUS_CANCELADO, "Cancelado"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="faturas_beneficiarios")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="faturas")
    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="faturas")
    competencia = models.CharField(max_length=7, help_text="YYYY-MM")
    valor_mensalidade = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_coparticipacao = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    vencimento = models.DateField(null=True, blank=True)
    pago_em = models.DateField(null=True, blank=True)
    observacao = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-competencia", "beneficiario__nome"]
        unique_together = [("empresa", "beneficiario", "competencia")]

    def __str__(self):
        return f"Fatura {self.competencia} — {self.beneficiario.nome}"


class ProgramaSaude(models.Model):
    """Programa de saúde gerenciado da operadora (DIP, crônicos, oncologia…)."""
    TIPO_CRONICO = "cronico"
    TIPO_PREVENTIVO = "preventivo"
    TIPO_ONCOLOGIA = "oncologia"
    TIPO_MATERNIDADE = "maternidade"
    TIPO_SAUDE_MENTAL = "saude_mental"
    TIPO_REABILITACAO = "reabilitacao"
    TIPO_CHOICES = [
        (TIPO_CRONICO, "Doença Crônica"),
        (TIPO_PREVENTIVO, "Preventivo / Wellness"),
        (TIPO_ONCOLOGIA, "Oncologia"),
        (TIPO_MATERNIDADE, "Maternidade / Pré-natal"),
        (TIPO_SAUDE_MENTAL, "Saúde Mental"),
        (TIPO_REABILITACAO, "Reabilitação"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="programas_saude")
    nome = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_CRONICO)
    descricao = models.TextField(blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class InscricaoPrograma(models.Model):
    """Inscrição de um beneficiário em um programa de saúde."""
    STATUS_ATIVO = "ativo"
    STATUS_CONCLUIDO = "concluido"
    STATUS_ABANDONOU = "abandonou"
    STATUS_CHOICES = [
        (STATUS_ATIVO, "Ativo"),
        (STATUS_CONCLUIDO, "Concluído"),
        (STATUS_ABANDONOU, "Abandonou"),
    ]

    programa = models.ForeignKey(ProgramaSaude, on_delete=models.CASCADE, related_name="inscricoes")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="inscricoes_programa")
    data_inscricao = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_ATIVO)
    observacao = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_inscricao"]
        unique_together = [("programa", "beneficiario")]

    def __str__(self):
        return f"{self.beneficiario.nome} — {self.programa.nome}"


# ─── Event Backbone / Outbox Pattern ─────────────────────────────────────────

class OutboxEvento(models.Model):
    """Eventos publicados via outbox pattern — garantia de entrega at-least-once."""
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("processando", "Processando"),
        ("entregue", "Entregue"),
        ("falha", "Falha"),
        ("dlq", "Dead Letter Queue"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="outbox_eventos", null=True, blank=True)
    tipo_evento = models.CharField(max_length=120)           # ex: "sst.exame.vencido"
    agregado_tipo = models.CharField(max_length=80, blank=True, default="")  # ex: "FuncionarioSST"
    agregado_id = models.CharField(max_length=80, blank=True, default="")
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente", db_index=True)
    tentativas = models.PositiveSmallIntegerField(default=0)
    max_tentativas = models.PositiveSmallIntegerField(default=3)
    proxima_tentativa = models.DateTimeField(null=True, blank=True)
    erro_ultimo = models.TextField(blank=True, default="")
    processado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["status", "proxima_tentativa"]),
            models.Index(fields=["tipo_evento", "status"]),
        ]

    def __str__(self):
        return f"{self.tipo_evento} [{self.status}]"


class SubscricaoEvento(models.Model):
    """Assinantes de tipos de eventos (webhook destinations)."""
    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="subscricoes_evento")
    tipo_evento_pattern = models.CharField(max_length=200)  # ex: "sst.*" ou "sst.exame.vencido"
    url_destino = models.URLField(max_length=500)
    secret_hmac = models.CharField(max_length=128, blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.tipo_evento_pattern} → {self.url_destino[:50]}"


# ─── Schema Registry / Data Contracts ────────────────────────────────────────

class SchemaContrato(models.Model):
    """Contrato de dados para um tipo de evento ou entidade."""
    COMPATIBILIDADE_CHOICES = [
        ("full", "Full (retrocompatível e forward)"),
        ("backward", "Backward (novos leitores leem old)"),
        ("forward", "Forward (old leitores leem new)"),
        ("none", "Nenhuma (breaking changes permitidas)"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="schema_contratos", null=True, blank=True)
    nome = models.CharField(max_length=200)                 # ex: "sst.exame.vencido"
    dominio = models.CharField(max_length=80, default="")   # ex: "sst", "farmacia"
    descricao = models.TextField(blank=True, default="")
    owner_equipe = models.CharField(max_length=120, blank=True, default="")
    compatibilidade = models.CharField(max_length=20, choices=COMPATIBILIDADE_CHOICES, default="backward")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "nome")]
        ordering = ["dominio", "nome"]

    def __str__(self):
        return self.nome


class VersaoSchema(models.Model):
    """Versão específica de um schema contrato (imutável após publicação)."""
    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("publicado", "Publicado"),
        ("deprecado", "Deprecado"),
    ]

    schema = models.ForeignKey(SchemaContrato, on_delete=models.CASCADE, related_name="versoes")
    versao = models.PositiveSmallIntegerField()
    schema_json = models.JSONField()                       # JSON Schema (draft-07)
    exemplo_payload = models.JSONField(default=dict)
    changelog = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="rascunho")
    publicado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("schema", "versao")]
        ordering = ["-versao"]

    def __str__(self):
        return f"{self.schema.nome} v{self.versao}"


# ─── MLOps Pipeline ───────────────────────────────────────────────────────────

class ModeloML(models.Model):
    """Registro de modelos de ML em produção."""
    TIPO_CHOICES = [
        ("classificacao", "Classificação"),
        ("regressao", "Regressão"),
        ("anomalia", "Detecção de Anomalia"),
        ("nlp", "NLP / Texto"),
        ("series_temporais", "Séries Temporais"),
        ("regras", "Motor de Regras"),
    ]
    STATUS_CHOICES = [
        ("staging", "Staging"),
        ("producao", "Produção"),
        ("deprecado", "Deprecado"),
        ("pausado", "Pausado"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="modelos_ml", null=True, blank=True)
    nome = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    tipo = models.CharField(max_length=30, choices=TIPO_CHOICES, default="classificacao")
    descricao = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="staging", db_index=True)
    versao_atual = models.CharField(max_length=30, default="1.0.0")
    owner_equipe = models.CharField(max_length=120, blank=True, default="")
    endpoint_inferencia = models.URLField(max_length=500, blank=True, default="")
    metricas_baseline = models.JSONField(default=dict)     # ex: {"accuracy":0.92,"f1":0.89}
    features_entrada = models.JSONField(default=list)      # lista de features
    feature_alvo = models.CharField(max_length=100, blank=True, default="")
    slo_latencia_ms = models.PositiveIntegerField(default=500)
    slo_precisao_min = models.FloatField(default=0.80)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "slug")]
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} v{self.versao_atual} [{self.status}]"


class RunModelo(models.Model):
    """Execução / predição de um modelo — log de inferências."""
    modelo = models.ForeignKey(ModeloML, on_delete=models.CASCADE, related_name="runs")
    versao = models.CharField(max_length=30)
    input_hash = models.CharField(max_length=64, blank=True, default="")  # sha256 do input
    predicao = models.JSONField(default=dict)
    confianca = models.FloatField(null=True, blank=True)
    latencia_ms = models.PositiveIntegerField(null=True, blank=True)
    ground_truth = models.JSONField(null=True, blank=True)  # preenchido depois (feedback loop)
    correto = models.BooleanField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["modelo", "criado_em"])]


class MonitoramentoModelo(models.Model):
    """Snapshot diário de métricas de um modelo em produção."""
    ALERTA_CHOICES = [
        ("ok", "OK"),
        ("atencao", "Atenção"),
        ("drift", "Drift Detectado"),
        ("degradacao", "Degradação de Performance"),
    ]

    modelo = models.ForeignKey(ModeloML, on_delete=models.CASCADE, related_name="monitoramentos")
    data_referencia = models.DateField(db_index=True)
    total_predicoes = models.PositiveIntegerField(default=0)
    precisao_periodo = models.FloatField(null=True, blank=True)
    f1_periodo = models.FloatField(null=True, blank=True)
    latencia_p50_ms = models.FloatField(null=True, blank=True)
    latencia_p95_ms = models.FloatField(null=True, blank=True)
    latencia_p99_ms = models.FloatField(null=True, blank=True)
    taxa_erro = models.FloatField(default=0.0)
    drift_score = models.FloatField(null=True, blank=True)    # 0-1, >0.3 = atenção
    status_alerta = models.CharField(max_length=20, choices=ALERTA_CHOICES, default="ok", db_index=True)
    distribuicao_features = models.JSONField(default=dict)   # estatísticas de features
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("modelo", "data_referencia")]
        ordering = ["-data_referencia"]

    def __str__(self):
        return f"{self.modelo.nome} {self.data_referencia} [{self.status_alerta}]"


# ─── GTM Machine ─────────────────────────────────────────────────────────────

class LeadComercial(models.Model):
    ETAPAS = [
        ("leads", "Lead Captado"),
        ("qualificados", "Qualificado (MQL)"),
        ("demo", "Demo Realizada"),
        ("proposta", "Proposta Enviada"),
        ("negociacao", "Em Negociação"),
        ("fechado", "Fechado (Won)"),
        ("perdido", "Perdido (Lost)"),
    ]
    SEGMENTOS = [
        ("industria", "Indústria"),
        ("saude", "Saúde"),
        ("varejo", "Varejo"),
        ("governo", "Governo"),
        ("financeiro", "Financeiro"),
        ("outros", "Outros"),
    ]

    nome_empresa = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=18, blank=True, default="")
    etapa = models.CharField(max_length=20, choices=ETAPAS, default="leads", db_index=True)
    segmento = models.CharField(max_length=20, choices=SEGMENTOS, default="outros")
    plano_interesse = models.CharField(max_length=50, blank=True, default="")
    valor_estimado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    owner = models.CharField(max_length=100, blank=True, default="")
    fonte = models.CharField(max_length=100, blank=True, default="")
    data_entrada = models.DateField(auto_now_add=True, db_index=True)
    data_conversao = models.DateField(null=True, blank=True)
    ciclo_dias = models.PositiveIntegerField(null=True, blank=True)
    notas = models.TextField(blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["etapa", "criado_em"], name="lead_etapa_idx"),
        ]

    def __str__(self):
        return f"{self.nome_empresa} [{self.etapa}]"


class ExpansaoContrato(models.Model):
    """Registra upsell/expansão de clientes existentes para cálculo de NRR real."""
    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="expansoes")
    pacote_anterior = models.CharField(max_length=50)
    pacote_novo = models.CharField(max_length=50)
    mrr_anterior = models.DecimalField(max_digits=10, decimal_places=2)
    mrr_novo = models.DecimalField(max_digits=10, decimal_places=2)
    delta_mrr = models.DecimalField(max_digits=10, decimal_places=2)
    motivo = models.CharField(max_length=200, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.empresa.nome} {self.pacote_anterior}→{self.pacote_novo}"


# ─── Feature Store ────────────────────────────────────────────────────────────

class FeatureRegistro(models.Model):
    """Catálogo persistente de features ML — substitui o dict in-memory."""
    FREQUENCIAS = [
        ("realtime", "Real-time"),
        ("diaria", "Diária"),
        ("semanal", "Semanal"),
        ("mensal", "Mensal"),
    ]
    TIPOS = [
        ("float", "Float"),
        ("int", "Integer"),
        ("bool", "Boolean"),
        ("str", "String"),
        ("embedding", "Embedding"),
    ]
    ENTIDADES = [
        ("colaborador", "Colaborador"),
        ("empresa", "Empresa"),
        ("unidade", "Unidade"),
    ]

    entidade = models.CharField(max_length=30, choices=ENTIDADES, db_index=True)
    nome = models.CharField(max_length=100)
    descricao = models.TextField()
    tipo = models.CharField(max_length=20, choices=TIPOS, default="float")
    fonte = models.CharField(max_length=100)
    frequencia_atualizacao = models.CharField(max_length=20, choices=FREQUENCIAS, default="diaria")
    sla_atraso_max_horas = models.PositiveIntegerField(default=25)
    owner = models.CharField(max_length=100)
    tags = models.JSONField(default=list)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("entidade", "nome")]
        ordering = ["entidade", "nome"]

    def __str__(self):
        return f"{self.entidade}.{self.nome}"


# ─── Financial OS — Unicorn Metrics ─────────────────────────────────────────

class CentroCusto(models.Model):
    TIPOS = [
        ("headcount", "Headcount"),
        ("infraestrutura", "Infraestrutura"),
        ("marketing", "Marketing"),
        ("vendas", "Vendas"),
        ("outros", "Outros"),
    ]

    nome = models.CharField(max_length=100)
    tipo = models.CharField(max_length=30, choices=TIPOS, default="outros")
    responsavel = models.CharField(max_length=100, blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "nome"]

    def __str__(self):
        return f"{self.nome} [{self.tipo}]"


class LancamentoDespesa(models.Model):
    """Lançamento mensal de despesas reais — base para Burn Multiple verdadeiro."""
    centro = models.ForeignKey(CentroCusto, on_delete=models.PROTECT, related_name="lancamentos")
    competencia = models.DateField(db_index=True)
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    descricao = models.CharField(max_length=200, blank=True, default="")
    recorrente = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-competencia"]
        indexes = [
            models.Index(fields=["competencia", "centro"], name="despesa_comp_idx"),
        ]

    def __str__(self):
        return f"{self.centro.nome} {self.competencia} R${self.valor}"


class CohortRetencao(models.Model):
    """Cohort mensal de retenção de receita — base para LTV/CAC real."""
    cohort_mes = models.DateField(db_index=True)
    empresas_adquiridas = models.PositiveIntegerField(default=0)
    mrr_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    mes_referencia = models.DateField(db_index=True)
    empresas_ativas = models.PositiveIntegerField(default=0)
    mrr_retido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    mrr_expandido = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    retencao_pct = models.FloatField(default=0.0)
    nrr_pct = models.FloatField(default=0.0)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("cohort_mes", "mes_referencia")]
        ordering = ["-cohort_mes", "-mes_referencia"]

    def __str__(self):
        return f"Cohort {self.cohort_mes} @ {self.mes_referencia} NRR={self.nrr_pct}%"


# ─── Compliance — SOC2 / ISO 27001 ───────────────────────────────────────────

class SOC2Controle(models.Model):
    CATEGORIAS_TSC = [
        ("CC", "Common Criteria"),
        ("A", "Availability"),
        ("C", "Confidentiality"),
        ("PI", "Processing Integrity"),
        ("P", "Privacy"),
    ]
    STATUS = [
        ("nao_iniciado", "Não Iniciado"),
        ("em_andamento", "Em Andamento"),
        ("implementado", "Implementado"),
        ("auditado", "Auditado"),
    ]

    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="soc2_controles")
    codigo = models.CharField(max_length=20)
    categoria = models.CharField(max_length=5, choices=CATEGORIAS_TSC, db_index=True)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS, default="nao_iniciado", db_index=True)
    responsavel = models.CharField(max_length=100, blank=True, default="")
    data_prevista = models.DateField(null=True, blank=True)
    data_implementacao = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "codigo")]
        ordering = ["categoria", "codigo"]

    def __str__(self):
        return f"{self.codigo} — {self.titulo} [{self.status}]"


class EvidenciaControle(models.Model):
    TIPOS = [
        ("screenshot", "Screenshot"),
        ("log", "Log de Sistema"),
        ("documento", "Documento"),
        ("politica", "Política"),
        ("procedimento", "Procedimento"),
        ("relatorio", "Relatório"),
    ]

    controle = models.ForeignKey(SOC2Controle, on_delete=models.CASCADE, related_name="evidencias")
    tipo = models.CharField(max_length=20, choices=TIPOS)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True, default="")
    arquivo_url = models.URLField(blank=True, default="")
    coletado_por = models.CharField(max_length=100, blank=True, default="")
    data_coleta = models.DateField(auto_now_add=True)
    valido_ate = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.controle.codigo} — {self.titulo}"


class TesteControle(models.Model):
    RESULTADOS = [
        ("aprovado", "Aprovado"),
        ("reprovado", "Reprovado"),
        ("excecao", "Exceção Documentada"),
    ]

    controle = models.ForeignKey(SOC2Controle, on_delete=models.CASCADE, related_name="testes")
    testado_por = models.CharField(max_length=100)
    data_teste = models.DateField(db_index=True)
    resultado = models.CharField(max_length=20, choices=RESULTADOS)
    observacoes = models.TextField(blank=True, default="")
    evidencias_ids = models.JSONField(default=list)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_teste"]

    def __str__(self):
        return f"{self.controle.codigo} {self.data_teste} [{self.resultado}]"


# ─── RBAC ────────────────────────────────────────────────────────────────────

class RBACPermissao(models.Model):
    codigo = models.CharField(max_length=100, unique=True)
    descricao = models.CharField(max_length=200)
    modulo = models.CharField(max_length=50, db_index=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["modulo", "codigo"]

    def __str__(self):
        return f"{self.modulo}.{self.codigo}"


class RBACAtribuicao(models.Model):
    empresa = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="rbac_atribuicoes")
    usuario = models.ForeignKey("EmpresaUsuario", on_delete=models.CASCADE, related_name="rbac_atribuicoes")
    permissao = models.ForeignKey(RBACPermissao, on_delete=models.CASCADE, related_name="atribuicoes")
    concedido_por = models.CharField(max_length=100, blank=True, default="")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "usuario", "permissao")]
        indexes = [
            models.Index(fields=["empresa", "usuario", "ativo"], name="rbac_emp_usr_idx"),
        ]

    def __str__(self):
        return f"{self.empresa.nome} / {self.usuario} / {self.permissao.codigo}"


# ─── Farmácia — Módulo Gestão Completa ───────────────────────────────────────

class MedicamentoFarmacia(models.Model):
    """Catálogo de medicamentos com controle de estoque e classificação ANVISA."""

    FORMA_CHOICES = [
        ("comprimido", "Comprimido"),
        ("capsula", "Cápsula"),
        ("solucao", "Solução"),
        ("suspensao", "Suspensão"),
        ("injetavel", "Injetável"),
        ("creme", "Creme"),
        ("pomada", "Pomada"),
        ("gel", "Gel"),
        ("gotas", "Gotas"),
        ("inalador", "Inalador"),
        ("supositorio", "Supositório"),
        ("outro", "Outro"),
    ]

    CLASSE_CHOICES = [
        ("analgesico", "Analgésico"),
        ("antibiotico", "Antibiótico"),
        ("anti_inflamatorio", "Anti-inflamatório"),
        ("antihipertensivo", "Anti-hipertensivo"),
        ("antidiabetes", "Antidiabetes"),
        ("cardiovascular", "Cardiovascular"),
        ("neurologico", "Neurológico"),
        ("psiquiatrico", "Psiquiátrico"),
        ("oncologico", "Oncológico"),
        ("vitamina", "Vitamina / Suplemento"),
        ("outro", "Outro"),
    ]

    # Identificação do produto
    empresa            = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="medicamentos_farmacia")
    nome               = models.CharField(max_length=200)
    principio_ativo    = models.CharField(max_length=200, blank=True, default="")
    forma_farmaceutica = models.CharField(max_length=20, choices=FORMA_CHOICES, default="comprimido")
    concentracao       = models.CharField(max_length=100, blank=True, default="", help_text="Ex: 500mg, 10mg/mL")
    registro_anvisa    = models.CharField(max_length=50, blank=True, default="")
    codigo_barras      = models.CharField(max_length=50, blank=True, default="")
    fabricante         = models.CharField(max_length=200, blank=True, default="")
    classe_terapeutica = models.CharField(max_length=30, choices=CLASSE_CHOICES, default="outro")

    # Estoque
    quantidade_atual   = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_minima  = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    quantidade_maxima  = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    preco_custo        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    preco_venda        = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Controle especial
    LISTA_PORTARIA_344 = [
        ("",    "Não controlado"),
        ("A1",  "Lista A1 — Entorpecentes"),
        ("A2",  "Lista A2 — Entorpecentes especiais"),
        ("A3",  "Lista A3 — Psicotrópicos"),
        ("B1",  "Lista B1 — Psicotrópicos"),
        ("B2",  "Lista B2 — Psicotrópicos anorexígenos"),
        ("C1",  "Lista C1 — Outras substâncias sujeitas a controle"),
        ("C2",  "Lista C2 — Retinoides"),
        ("C3",  "Lista C3 — Imunossupressores"),
        ("C4",  "Lista C4 — Antirretrovirais"),
        ("C5",  "Lista C5 — Anabolizantes"),
        ("D1",  "Lista D1 — Precursoras"),
    ]
    controlado             = models.BooleanField(default=False, help_text="Medicamento sujeito a controle especial (Portaria 344)")
    lista_portaria_344     = models.CharField(max_length=4, choices=LISTA_PORTARIA_344, blank=True, default="", help_text="Lista ANVISA Portaria 344")
    requer_notificacao_anvisa = models.BooleanField(default=False, help_text="Notificação ANVISA obrigatória na dispensação")
    refrigerado            = models.BooleanField(default=False, help_text="Requer armazenamento refrigerado")
    validade_media_dias    = models.PositiveIntegerField(default=365, help_text="Validade média em dias após fabricação")

    ativo              = models.BooleanField(default=True)
    criado_em          = models.DateTimeField(auto_now_add=True)
    atualizado_em      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]
        indexes = [
            models.Index(fields=["empresa", "ativo"], name="med_farm_emp_ativo_idx"),
        ]

    def __str__(self):
        return f"{self.nome} {self.concentracao}".strip()

    @property
    def status_estoque(self):
        if self.quantidade_atual <= 0:
            return "critico"
        margem_critica = Decimal("1.10")
        margem_alerta = Decimal("1.50")
        if self.quantidade_minima > 0 and self.quantidade_atual <= self.quantidade_minima * margem_critica:
            return "critico"
        if self.quantidade_minima > 0 and self.quantidade_atual <= self.quantidade_minima * margem_alerta:
            return "baixo"
        return "ok"


class EstoqueMovimento(models.Model):
    """Registro de movimentações de estoque de medicamentos."""

    TIPO_CHOICES = [
        ("entrada", "Entrada"),
        ("saida", "Saída"),
        ("ajuste", "Ajuste"),
        ("descarte", "Descarte"),
        ("transferencia", "Transferência"),
    ]

    empresa      = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="estoque_movimentos")
    medicamento  = models.ForeignKey(MedicamentoFarmacia, on_delete=models.CASCADE, related_name="movimentos_estoque")
    tipo         = models.CharField(max_length=20, choices=TIPO_CHOICES)
    quantidade   = models.DecimalField(max_digits=12, decimal_places=3)
    motivo       = models.TextField(blank=True, default="")
    lote         = models.CharField(max_length=100, blank=True, default="")
    data_validade = models.DateField(null=True, blank=True)
    responsavel  = models.CharField(max_length=200, blank=True, default="")
    observacao   = models.TextField(blank=True, default="")
    criado_em    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "medicamento"], name="estmov_emp_med_idx"),
        ]

    def __str__(self):
        return f"{self.tipo} {self.quantidade} — {self.medicamento.nome}"


class Dispensacao(models.Model):
    """Dispensação de medicamentos a pacientes com controle de receita."""

    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("dispensada", "Dispensada"),
        ("devolvida", "Devolvida"),
        ("parcial", "Parcialmente Dispensada"),
    ]

    empresa            = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="dispensacoes_farmacia")
    data               = models.DateTimeField(auto_now_add=True)
    paciente_nome      = models.CharField(max_length=200)
    paciente_cpf       = models.CharField(max_length=14, blank=True, default="")
    prescricao_numero  = models.CharField(max_length=50, blank=True, default="")
    medico_crm         = models.CharField(max_length=30, blank=True, default="")
    medicamentos       = models.JSONField(default=list, help_text="Lista de itens: [{medicamento_id, nome, quantidade, ...}]")
    valor_total        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    convenio           = models.CharField(max_length=200, blank=True, default="")
    status             = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    observacoes        = models.TextField(blank=True, default="")
    criado_em          = models.DateTimeField(auto_now_add=True)
    atualizado_em      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"], name="disp_farm_emp_status_idx"),
        ]

    def __str__(self):
        return f"Dispensação #{self.pk} — {self.paciente_nome} ({self.status})"


class FornecedorFarmaciaGestao(models.Model):
    """Fornecedor de medicamentos para o módulo de gestão de farmácia."""

    empresa            = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="fornecedores_farmacia_gestao")
    nome               = models.CharField(max_length=200)
    cnpj               = models.CharField(max_length=18, blank=True, default="")
    contato            = models.CharField(max_length=200, blank=True, default="")
    email              = models.EmailField(blank=True, default="")
    telefone           = models.CharField(max_length=20, blank=True, default="")
    prazo_entrega_dias = models.PositiveSmallIntegerField(default=7, help_text="Prazo médio de entrega em dias")
    ativo              = models.BooleanField(default=True)
    criado_em          = models.DateTimeField(auto_now_add=True)
    atualizado_em      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class PedidoFarmacia(models.Model):
    """Pedido de compra de medicamentos para fornecedores."""

    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("enviado", "Enviado"),
        ("confirmado", "Confirmado"),
        ("recebido", "Recebido"),
        ("cancelado", "Cancelado"),
    ]

    empresa               = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pedidos_farmacia_gestao")
    fornecedor            = models.ForeignKey(FornecedorFarmaciaGestao, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_farmacia")
    data_pedido           = models.DateField(auto_now_add=True)
    data_entrega_prevista = models.DateField(null=True, blank=True)
    status                = models.CharField(max_length=20, choices=STATUS_CHOICES, default="rascunho")
    itens                 = models.JSONField(default=list, help_text="[{medicamento_id, quantidade, preco_unitario}]")
    valor_total           = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observacao            = models.TextField(blank=True, default="")
    criado_em             = models.DateTimeField(auto_now_add=True)
    atualizado_em         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Pedido #{self.pk} — {self.fornecedor.nome if self.fornecedor else 'sem fornecedor'} ({self.status})"


class TransferenciaFarmaciaMed(models.Model):
    """Transferência de MedicamentoFarmacia entre unidades de uma mesma Rede."""

    STATUS_CHOICES = [
        ("pendente",   "Pendente"),
        ("aprovada",   "Aprovada"),
        ("enviada",    "Enviada"),
        ("recebida",   "Recebida"),
        ("cancelada",  "Cancelada"),
        ("rejeitada",  "Rejeitada"),
    ]

    rede                = models.ForeignKey("Rede", on_delete=models.CASCADE, related_name="transferencias_farmacia")
    empresa_solicitante = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="transf_farm_solicitadas")
    empresa_fornecedora = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="transf_farm_fornecidas")
    medicamento         = models.ForeignKey(MedicamentoFarmacia, on_delete=models.PROTECT, related_name="transferencias_rede")
    lote                = models.ForeignKey(LoteMedicamento, on_delete=models.SET_NULL, null=True, blank=True, related_name="transferencias_rede")
    quantidade_solicitada = models.DecimalField(max_digits=12, decimal_places=3)
    quantidade_aprovada   = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    urgente             = models.BooleanField(default=False)
    motivo              = models.TextField(blank=True, default="")
    observacoes         = models.TextField(blank=True, default="")
    solicitado_por      = models.CharField(max_length=150, blank=True, default="")
    aprovado_por        = models.CharField(max_length=150, blank=True, default="")
    solicitado_em       = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-solicitado_em"]
        indexes = [
            models.Index(fields=["rede", "status"], name="transf_farm_rede_status_idx"),
            models.Index(fields=["empresa_solicitante", "status"], name="transf_farm_sol_status_idx"),
        ]

    def __str__(self):
        return f"Transf #{self.id} — {self.medicamento.nome} ({self.status})"


class LivroRegistroControlado(models.Model):
    """Livro de registro obrigatório para dispensação de controlados (Portaria 344 ANVISA)."""

    TIPO_CHOICES = [
        ("dispensacao", "Dispensação"),
        ("entrada", "Entrada em Estoque"),
        ("descarte", "Descarte / Inutilização"),
        ("transferencia", "Transferência"),
    ]

    empresa           = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="livro_registro_controlados")
    medicamento       = models.ForeignKey(MedicamentoFarmacia, on_delete=models.PROTECT, related_name="registros_controlados")
    lote              = models.ForeignKey(LoteMedicamento, on_delete=models.SET_NULL, null=True, blank=True, related_name="registros_controlados")
    tipo              = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data_operacao     = models.DateTimeField(auto_now_add=True)
    quantidade        = models.DecimalField(max_digits=12, decimal_places=3)
    saldo_apos        = models.DecimalField(max_digits=12, decimal_places=3)
    paciente_nome     = models.CharField(max_length=200, blank=True, default="")
    paciente_cpf      = models.CharField(max_length=14, blank=True, default="")
    prescricao_numero = models.CharField(max_length=50, blank=True, default="")
    medico_crm        = models.CharField(max_length=30, blank=True, default="")
    responsavel       = models.CharField(max_length=200, blank=True, default="")
    observacao        = models.TextField(blank=True, default="")
    dispensacao       = models.ForeignKey("Dispensacao", on_delete=models.SET_NULL, null=True, blank=True, related_name="registros_controlados")
    criado_em         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_operacao"]
        indexes = [
            models.Index(fields=["empresa", "medicamento"], name="livro_ctrl_emp_med_idx"),
            models.Index(fields=["empresa", "data_operacao"], name="livro_ctrl_emp_dt_idx"),
        ]

    def __str__(self):
        return f"Livro #{self.pk} — {self.medicamento.nome} {self.tipo} {self.quantidade}"


class FarmaciaAuditLog(models.Model):
    """Trilha de auditoria completa para todas as operações de farmácia."""

    ACAO_CHOICES = [
        ("criar", "Criar"),
        ("editar", "Editar"),
        ("excluir", "Excluir"),
        ("dispensar", "Dispensar"),
        ("bloquear_lote", "Bloquear Lote"),
        ("desbloquear_lote", "Desbloquear Lote"),
        ("ajuste_estoque", "Ajuste de Estoque"),
        ("descarte", "Descarte"),
        ("notificacao_anvisa", "Notificação ANVISA"),
    ]

    empresa       = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="farmacia_audit_logs")
    acao          = models.CharField(max_length=30, choices=ACAO_CHOICES)
    modelo        = models.CharField(max_length=100)
    objeto_id     = models.PositiveIntegerField(null=True, blank=True)
    descricao     = models.TextField()
    dados_antes   = models.JSONField(null=True, blank=True)
    dados_depois  = models.JSONField(null=True, blank=True)
    usuario       = models.CharField(max_length=200, blank=True, default="")
    ip            = models.GenericIPAddressField(null=True, blank=True)
    criado_em     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "acao"], name="farm_audit_emp_acao_idx"),
            models.Index(fields=["empresa", "criado_em"], name="farm_audit_emp_dt_idx"),
        ]

    def __str__(self):
        return f"Audit #{self.pk} — {self.acao} {self.modelo} ({self.criado_em})"


# ─── Hospital — Gestão Integrada (Manchester / Leitos / Internação) ──────────

class LeitoHospitalar(models.Model):
    TIPO_CHOICES = [
        ("uti", "UTI"),
        ("enfermaria", "Enfermaria"),
        ("particular", "Particular"),
        ("emergencia", "Emergência"),
        ("semi_intensivo", "Semi-Intensivo"),
    ]
    STATUS_CHOICES = [
        ("livre", "Livre"),
        ("ocupado", "Ocupado"),
        ("manutencao", "Manutenção"),
        ("bloqueado", "Bloqueado"),
    ]

    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="leitos_hospitalar")
    numero           = models.CharField(max_length=20)
    ala              = models.CharField(max_length=100, blank=True, default="")
    tipo             = models.CharField(max_length=20, choices=TIPO_CHOICES, default="enfermaria")
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="livre")
    paciente_nome    = models.CharField(max_length=200, null=True, blank=True)
    paciente_id      = models.UUIDField(null=True, blank=True)
    data_internacao  = models.DateField(null=True, blank=True)
    previsao_alta    = models.DateField(null=True, blank=True)
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ala", "numero"]
        unique_together = [("empresa", "numero")]

    def __str__(self):
        return f"Leito {self.numero} ({self.tipo}) — {self.status}"


class TriagemManchester(models.Model):
    NIVEL_CHOICES = [
        ("vermelho", "Vermelho — Emergência"),
        ("laranja", "Laranja — Muito Urgente"),
        ("amarelo", "Amarelo — Urgente"),
        ("verde", "Verde — Pouco Urgente"),
        ("azul", "Azul — Não Urgente"),
    ]
    STATUS_CHOICES = [
        ("aguardando", "Aguardando"),
        ("em_atendimento", "Em Atendimento"),
        ("atendido", "Atendido"),
        ("transferido", "Transferido"),
        ("evadiu", "Evadiu"),
    ]

    empresa                = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="triagens_manchester")
    data_hora              = models.DateTimeField()
    paciente_nome          = models.CharField(max_length=200)
    paciente_cpf           = models.CharField(max_length=14, null=True, blank=True)
    queixa_principal       = models.TextField()
    nivel                  = models.CharField(max_length=20, choices=NIVEL_CHOICES)
    tempo_espera_minutos   = models.PositiveIntegerField(default=0)
    status                 = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aguardando")
    medico_responsavel     = models.CharField(max_length=200, blank=True, default="")
    observacao             = models.TextField(blank=True, default="")
    criado_em              = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_hora"]

    def __str__(self):
        return f"Triagem {self.paciente_nome} [{self.nivel}] {self.data_hora.date()}"


class PacienteInternado(models.Model):
    STATUS_CHOICES = [
        ("internado", "Internado"),
        ("alta", "Alta"),
        ("transferido", "Transferido"),
        ("obito", "Óbito"),
    ]
    ISOLAMENTO_CHOICES = [
        ("nenhum",    "Sem isolamento"),
        ("contato",   "Precaução de contato"),
        ("gotículas", "Precaução por gotículas"),
        ("aerossol",  "Precaução por aerossol"),
        ("protetor",  "Isolamento protetor"),
    ]

    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pacientes_internados")
    nome                = models.CharField(max_length=200)
    cpf                 = models.CharField(max_length=14, blank=True, default="")
    data_nascimento     = models.DateField(null=True, blank=True)
    data_internacao     = models.DateField()
    leito               = models.ForeignKey(LeitoHospitalar, on_delete=models.SET_NULL, null=True, blank=True, related_name="pacientes_internados")
    diagnostico_cid     = models.CharField(max_length=20, blank=True, default="")
    diagnostico_descricao = models.TextField(blank=True, default="")
    medico_responsavel  = models.CharField(max_length=200, blank=True, default="")
    medico_crm          = models.CharField(max_length=30, blank=True, default="")
    convenio            = models.CharField(max_length=200, blank=True, default="")
    numero_prontuario   = models.CharField(max_length=50, blank=True, default="")
    tipo_sanguineo      = models.CharField(max_length=5, blank=True, default="")
    alergias            = models.TextField(blank=True, default="")
    peso_kg             = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    altura_cm           = models.PositiveSmallIntegerField(null=True, blank=True)
    tipo_isolamento     = models.CharField(max_length=20, choices=ISOLAMENTO_CHOICES, default="nenhum")
    motivo_isolamento   = models.TextField(blank=True, default="")
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="internado")
    prescricao_atual    = models.JSONField(default=dict)
    evolucao            = models.JSONField(default=list)
    criado_em           = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_internacao", "nome"]

    def __str__(self):
        return f"{self.nome} — {self.status}"


class PrescricaoHospitalar(models.Model):
    STATUS_CHOICES = [
        ("ativa", "Ativa"),
        ("encerrada", "Encerrada"),
        ("cancelada", "Cancelada"),
    ]

    empresa          = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="prescricoes_hospitalares")
    paciente         = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="prescricoes_hospitalares")
    data             = models.DateField()
    medicamentos     = models.JSONField(default=list)
    validade_horas   = models.PositiveSmallIntegerField(default=24)
    medico_crm       = models.CharField(max_length=30, blank=True, default="")
    medico_nome      = models.CharField(max_length=200, blank=True, default="")
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ativa")
    criado_em        = models.DateTimeField(auto_now_add=True)
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"Prescrição {self.paciente.nome} {self.data} [{self.status}]"


class PedidoExame(models.Model):
    """Pedido de exame laboratorial ou de imagem solicitado durante internação."""
    TIPO_CHOICES = [
        ("laboratorial", "Laboratorial"),
        ("imagem",       "Imagem (Rx/TC/RM/US)"),
        ("ecg",          "ECG / Eletrocardiograma"),
        ("endoscopia",   "Endoscopia"),
        ("outro",        "Outro"),
    ]
    PRIORIDADE_CHOICES = [
        ("rotina",   "Rotina"),
        ("urgente",  "Urgente"),
        ("emergencia", "Emergência"),
    ]
    STATUS_CHOICES = [
        ("solicitado",  "Solicitado"),
        ("coletado",    "Coletado / Em análise"),
        ("concluido",   "Concluído"),
        ("cancelado",   "Cancelado"),
    ]

    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pedidos_exame_hosp")
    paciente            = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="pedidos_exame")
    prescricao          = models.ForeignKey(PrescricaoHospitalar, on_delete=models.SET_NULL, null=True, blank=True, related_name="pedidos_exame")
    tipo                = models.CharField(max_length=20, choices=TIPO_CHOICES)
    exames              = models.JSONField(default=list, help_text='[{nome, codigo_tuss, instrucoes}]')
    prioridade          = models.CharField(max_length=20, choices=PRIORIDADE_CHOICES, default="rotina")
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="solicitado")
    solicitante         = models.CharField(max_length=200, blank=True, default="")
    solicitante_crm     = models.CharField(max_length=30, blank=True, default="")
    observacoes_clinicas = models.TextField(blank=True, default="", help_text="Hipótese diagnóstica / contexto clínico")
    jejum_horas         = models.PositiveSmallIntegerField(null=True, blank=True)
    material            = models.CharField(max_length=100, blank=True, default="", help_text="Ex: sangue venoso, urina 24h")
    data_solicitacao    = models.DateTimeField(auto_now_add=True)
    data_coleta         = models.DateTimeField(null=True, blank=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_solicitacao"]
        indexes = [
            models.Index(fields=["empresa", "status"], name="pedexame_emp_status_idx"),
            models.Index(fields=["paciente", "status"], name="pedexame_pac_status_idx"),
        ]

    def __str__(self):
        return f"Pedido #{self.id} {self.tipo} — {self.paciente.nome} ({self.status})"


class ResultadoExame(models.Model):
    """Resultado de exame vinculado ao pedido."""
    INTERPRETACAO_CHOICES = [
        ("normal",   "Normal / Dentro do esperado"),
        ("alterado", "Alterado"),
        ("critico",  "Crítico — requer ação imediata"),
        ("pendente", "Pendente de laudo"),
    ]

    pedido              = models.ForeignKey(PedidoExame, on_delete=models.CASCADE, related_name="resultados")
    paciente            = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="resultados_exame")
    data_resultado      = models.DateTimeField(auto_now_add=True)
    resultados_json     = models.JSONField(default=list, help_text='[{exame, valor, unidade, referencia, status}]')
    laudo               = models.TextField(blank=True, default="")
    interpretacao       = models.CharField(max_length=20, choices=INTERPRETACAO_CHOICES, default="pendente")
    responsavel_laudo   = models.CharField(max_length=200, blank=True, default="")
    crm_responsavel     = models.CharField(max_length=30, blank=True, default="")
    url_imagem          = models.URLField(blank=True, default="", help_text="Link do DICOM / PDF do laudo")
    visualizado_por     = models.CharField(max_length=200, blank=True, default="")
    visualizado_em      = models.DateTimeField(null=True, blank=True)
    criado_em           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_resultado"]

    def __str__(self):
        return f"Resultado #{self.id} — {self.pedido} [{self.interpretacao}]"


class AdministracaoMedicamento(models.Model):
    """Registro de administração de medicamento prescrito (5 certos)."""
    STATUS_CHOICES = [
        ("administrado", "Administrado"),
        ("recusado",     "Recusado pelo paciente"),
        ("omitido",      "Omitido"),
        ("suspenso",     "Suspenso"),
    ]

    prescricao          = models.ForeignKey(PrescricaoHospitalar, on_delete=models.CASCADE, related_name="administracoes")
    paciente            = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="administracoes")
    nome_medicamento    = models.CharField(max_length=200)
    dose                = models.CharField(max_length=100, blank=True, default="")
    via                 = models.CharField(max_length=50, blank=True, default="")
    horario_prescrito   = models.TimeField()
    horario_administrado = models.DateTimeField(null=True, blank=True)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="administrado")
    responsavel         = models.CharField(max_length=200, blank=True, default="")
    coren               = models.CharField(max_length=30, blank=True, default="")
    observacao          = models.TextField(blank=True, default="")
    criado_em           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["prescricao", "status"], name="adminmed_presc_status_idx"),
        ]

    def __str__(self):
        return f"Adm {self.nome_medicamento} — {self.paciente.nome} {self.status}"


class EvolucaoClinicaInternado(models.Model):
    """Evolução clínica estruturada vinculada a PacienteInternado (modelo moderno)."""
    TIPO_CHOICES = [
        ("medica",      "Evolução Médica"),
        ("enfermagem",  "Evolução de Enfermagem"),
        ("fisio",       "Fisioterapia"),
        ("nutricao",    "Nutrição"),
        ("psicologia",  "Psicologia"),
        ("social",      "Serviço Social"),
        ("farmacia",    "Farmácia Clínica"),
        ("outro",       "Outro"),
    ]

    paciente        = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="evolucoes_estruturadas")
    tipo            = models.CharField(max_length=20, choices=TIPO_CHOICES, default="medica")
    descricao       = models.TextField()
    responsavel     = models.CharField(max_length=200, blank=True, default="")
    crm_coren       = models.CharField(max_length=30, blank=True, default="")
    sinais_vitais   = models.JSONField(default=dict, help_text='{"pa":"120/80","temp":36.5,"spo2":98,"fc":72,"fr":16}')
    registrado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registrado_em"]

    def __str__(self):
        return f"Evolução {self.tipo} — {self.paciente.nome} {self.registrado_em.date()}"


class MonitoramentoUTI(models.Model):
    """Registro horário de monitoramento intensivo (UTI/Semi-intensivo)."""

    paciente            = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="monitoramentos_uti")
    registrado_em       = models.DateTimeField(auto_now_add=True)
    # Sinais vitais
    pressao_arterial    = models.CharField(max_length=20, blank=True, default="")
    pressao_arterial_media = models.PositiveSmallIntegerField(null=True, blank=True, help_text="PAM em mmHg")
    frequencia_cardiaca = models.PositiveSmallIntegerField(null=True, blank=True)
    frequencia_respiratoria = models.PositiveSmallIntegerField(null=True, blank=True)
    temperatura         = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    saturacao_o2        = models.PositiveSmallIntegerField(null=True, blank=True)
    diurese_ml          = models.PositiveSmallIntegerField(null=True, blank=True)
    # Escores
    glasgow_ocular      = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1-4")
    glasgow_verbal      = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1-5")
    glasgow_motor       = models.PositiveSmallIntegerField(null=True, blank=True, help_text="1-6")
    sofa_respiratorio   = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0-4")
    sofa_coagulacao     = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0-4")
    sofa_hepatico       = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0-4")
    sofa_cardiovascular = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0-4")
    sofa_neurologico    = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0-4")
    sofa_renal          = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0-4")
    # Ventilação mecânica
    ventilacao_mecanica = models.BooleanField(default=False)
    modo_ventilatorio   = models.CharField(max_length=50, blank=True, default="", help_text="Ex: VCV, PCV, SIMV, PSV")
    fio2_pct            = models.PositiveSmallIntegerField(null=True, blank=True, help_text="FiO2 em %")
    peep                = models.PositiveSmallIntegerField(null=True, blank=True, help_text="PEEP em cmH2O")
    volume_corrente_ml  = models.PositiveSmallIntegerField(null=True, blank=True)
    # Drenos e acessos
    drogas_vasoativas   = models.BooleanField(default=False)
    droga_vasoativa_desc = models.CharField(max_length=200, blank=True, default="")
    responsavel         = models.CharField(max_length=200, blank=True, default="")
    observacoes         = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-registrado_em"]
        indexes = [models.Index(fields=["paciente", "registrado_em"], name="mon_uti_pac_dt_idx")]

    @property
    def glasgow_total(self):
        vals = [self.glasgow_ocular, self.glasgow_verbal, self.glasgow_motor]
        if all(v is not None for v in vals):
            return sum(vals)
        return None

    @property
    def sofa_total(self):
        vals = [self.sofa_respiratorio, self.sofa_coagulacao, self.sofa_hepatico,
                self.sofa_cardiovascular, self.sofa_neurologico, self.sofa_renal]
        if all(v is not None for v in vals):
            return sum(vals)
        return None

    def __str__(self):
        return f"UTI {self.paciente.nome} {self.registrado_em.strftime('%d/%m %H:%M')}"


class SumarioAlta(models.Model):
    """Sumário de alta hospitalar formal com receituário e orientações."""
    TIPO_ALTA_CHOICES = [
        ("alta_medica",     "Alta Médica"),
        ("alta_voluntaria", "Alta a Pedido"),
        ("transferencia",   "Transferência"),
        ("obito",           "Óbito"),
        ("evasao",          "Evasão"),
    ]

    paciente            = models.OneToOneField(PacienteInternado, on_delete=models.CASCADE, related_name="sumario_alta")
    tipo_alta           = models.CharField(max_length=20, choices=TIPO_ALTA_CHOICES, default="alta_medica")
    data_alta           = models.DateTimeField()
    medico_responsavel  = models.CharField(max_length=200, blank=True, default="")
    medico_crm          = models.CharField(max_length=30, blank=True, default="")
    diagnostico_final   = models.TextField(blank=True, default="")
    cid_principal       = models.CharField(max_length=20, blank=True, default="")
    cid_secundarios     = models.JSONField(default=list, help_text='["J18.9", "E11"]')
    resumo_internacao   = models.TextField(blank=True, default="")
    procedimentos_realizados = models.TextField(blank=True, default="")
    medicamentos_alta   = models.JSONField(default=list, help_text='[{nome, dose, via, frequencia, duracao}]')
    orientacoes_paciente = models.TextField(blank=True, default="")
    retorno_previsao    = models.DateField(null=True, blank=True)
    restricoes_atividade = models.TextField(blank=True, default="")
    encaminhamentos     = models.TextField(blank=True, default="")
    condicao_alta       = models.CharField(max_length=20, choices=[
        ("curado","Curado"), ("melhorado","Melhorado"), ("inalterado","Inalterado"),
        ("piorado","Piorado"), ("obito","Óbito"),
    ], default="melhorado")
    criado_em           = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_alta"]

    def __str__(self):
        return f"Alta {self.paciente.nome} {self.data_alta.date()}"


class CentroCirurgico(models.Model):
    """Agendamento e registro de procedimentos cirúrgicos."""
    STATUS_CHOICES = [
        ("agendado",    "Agendado"),
        ("em_andamento","Em Andamento"),
        ("concluido",   "Concluído"),
        ("cancelado",   "Cancelado"),
        ("suspenso",    "Suspenso"),
    ]
    PORTE_CHOICES = [
        ("pequeno",  "Pequeno Porte"),
        ("medio",    "Médio Porte"),
        ("grande",   "Grande Porte"),
        ("especial", "Especial"),
    ]

    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="cirurgias")
    paciente            = models.ForeignKey(PacienteInternado, on_delete=models.SET_NULL, null=True, blank=True, related_name="cirurgias")
    data_hora_prevista  = models.DateTimeField()
    data_hora_inicio    = models.DateTimeField(null=True, blank=True)
    data_hora_fim       = models.DateTimeField(null=True, blank=True)
    sala                = models.CharField(max_length=50, blank=True, default="", help_text="Ex: Sala 1, CC-A")
    procedimento        = models.CharField(max_length=300)
    codigo_tuss         = models.CharField(max_length=20, blank=True, default="")
    porte               = models.CharField(max_length=20, choices=PORTE_CHOICES, default="medio")
    cirurgiao_principal = models.CharField(max_length=200, blank=True, default="")
    cirurgiao_crm       = models.CharField(max_length=30, blank=True, default="")
    anestesiologista    = models.CharField(max_length=200, blank=True, default="")
    tipo_anestesia      = models.CharField(max_length=50, blank=True, default="", help_text="Geral, Raqui, Peridural, Local")
    equipe              = models.JSONField(default=list, help_text='[{nome, funcao}]')
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="agendado")
    cid_indicacao       = models.CharField(max_length=20, blank=True, default="")
    relatorio_cirurgico = models.TextField(blank=True, default="")
    intercorrencias     = models.TextField(blank=True, default="")
    sangramento_ml      = models.PositiveIntegerField(null=True, blank=True)
    criado_em           = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["data_hora_prevista"]
        indexes = [
            models.Index(fields=["empresa", "status"], name="cc_emp_status_idx"),
            models.Index(fields=["empresa", "data_hora_prevista"], name="cc_emp_dt_idx"),
        ]

    def __str__(self):
        return f"Cirurgia #{self.id} — {self.procedimento} ({self.status})"


class FaturaHospitalar(models.Model):
    """Fatura consolidada de uma internação — convênio, SUS ou particular."""
    STATUS_CHOICES = [
        ("rascunho",  "Rascunho"),
        ("fechada",   "Fechada / Aguardando envio"),
        ("enviada",   "Enviada ao Convênio"),
        ("paga",      "Paga"),
        ("glosada",   "Glosada (parcial ou total)"),
        ("cancelada", "Cancelada"),
    ]
    CONVENIO_CHOICES = [
        ("sus",        "SUS"),
        ("convenio",   "Convênio / Plano de Saúde"),
        ("particular", "Particular"),
    ]

    empresa             = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="faturas_hosp")
    paciente            = models.OneToOneField(PacienteInternado, on_delete=models.CASCADE, related_name="fatura")
    numero_guia         = models.CharField(max_length=50, blank=True, default="")
    convenio            = models.CharField(max_length=20, choices=CONVENIO_CHOICES, default="particular")
    nome_convenio       = models.CharField(max_length=200, blank=True, default="")
    numero_carteirinha  = models.CharField(max_length=50, blank=True, default="")
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default="rascunho")
    valor_total         = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_glosa         = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_pago          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    observacoes         = models.TextField(blank=True, default="")
    data_envio          = models.DateTimeField(null=True, blank=True)
    data_pagamento      = models.DateTimeField(null=True, blank=True)
    criado_em           = models.DateTimeField(auto_now_add=True)
    atualizado_em       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"], name="fatura_hosp_emp_status_idx"),
        ]

    def recalcular_total(self):
        from django.db.models import Sum
        total = self.itens.aggregate(t=Sum("valor_total"))["t"] or 0
        self.valor_total = total
        self.save(update_fields=["valor_total", "atualizado_em"])

    def __str__(self):
        return f"Fatura #{self.id} — {self.paciente.nome}"


class ItemFaturamento(models.Model):
    """Linha de cobrança com código TUSS/CBhpm."""
    TIPO_CHOICES = [
        ("diaria",       "Diária / Acomodação"),
        ("procedimento", "Procedimento"),
        ("exame",        "Exame / Diagnóstico"),
        ("medicamento",  "Medicamento"),
        ("material",     "Material / OPME"),
        ("honorario",    "Honorário Médico"),
        ("taxa",         "Taxa / Pacote"),
        ("outro",        "Outro"),
    ]

    empresa             = models.ForeignKey("Empresa", on_delete=models.CASCADE, related_name="itens_faturamento_hosp")
    paciente            = models.ForeignKey(PacienteInternado, on_delete=models.CASCADE, related_name="itens_faturamento")
    fatura              = models.ForeignKey(FaturaHospitalar, on_delete=models.SET_NULL, null=True, blank=True, related_name="itens")
    tipo                = models.CharField(max_length=20, choices=TIPO_CHOICES, default="procedimento")
    codigo_tuss         = models.CharField(max_length=20, blank=True, default="")
    codigo_cbhpm        = models.CharField(max_length=20, blank=True, default="")
    descricao           = models.CharField(max_length=300)
    quantidade          = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    valor_unitario      = models.DecimalField(max_digits=10, decimal_places=2)
    valor_total         = models.DecimalField(max_digits=12, decimal_places=2)
    data_competencia    = models.DateField(auto_now_add=True)
    observacao          = models.TextField(blank=True, default="")
    criado_em           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "paciente"], name="itemfat_emp_pac_idx"),
        ]

    def save(self, *args, **kwargs):
        self.valor_total = self.quantidade * self.valor_unitario
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.descricao} × {self.quantidade} = R$ {self.valor_total}"


class AssinaturaDocumentoSST(models.Model):
    TIPO_CHOICES = [
        ("aso", "ASO"),
        ("cat", "CAT"),
        ("prontuario", "Prontuário SST"),
        ("documento_sst", "Documento SST"),
    ]
    STATUS_CHOICES = [
        ("pendente", "Pendente"),
        ("assinado", "Assinado"),
        ("cancelado", "Cancelado"),
    ]

    empresa              = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="assinaturas_sst")
    funcionario          = models.ForeignKey("FuncionarioSST", on_delete=models.SET_NULL, null=True, blank=True, related_name="assinaturas_sst")
    tipo_documento       = models.CharField(max_length=30, choices=TIPO_CHOICES)
    objeto_id            = models.PositiveIntegerField()
    titulo               = models.CharField(max_length=240)
    token                = models.CharField(max_length=64, unique=True, default=_codigo_acesso)
    status               = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pendente")
    hash_documento       = models.CharField(max_length=64)
    hash_assinatura      = models.CharField(max_length=64, blank=True, default="")
    signatario_nome      = models.CharField(max_length=180, blank=True, default="")
    signatario_email     = models.EmailField(blank=True, default="")
    signatario_cpf       = models.CharField(max_length=20, blank=True, default="")
    solicitado_por       = models.CharField(max_length=180, blank=True, default="")
    ip_solicitacao       = models.GenericIPAddressField(null=True, blank=True)
    ip_assinatura        = models.GenericIPAddressField(null=True, blank=True)
    user_agent_assinatura = models.CharField(max_length=300, blank=True, default="")
    assinado_em          = models.DateTimeField(null=True, blank=True)
    expiracao_em         = models.DateTimeField(null=True, blank=True)
    criado_em            = models.DateTimeField(auto_now_add=True)
    atualizado_em        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "tipo_documento", "objeto_id"]),
            models.Index(fields=["token"]),
        ]

    def __str__(self):
        return f"Assinatura {self.tipo_documento} [{self.status}] — {self.titulo}"


# ── CRESCIMENTO / UNICÓRNIO ───────────────────────────────────────────────────

class TrialEmpresa(models.Model):
    """Período de trial self-service da plataforma."""
    empresa      = models.OneToOneField(Empresa, on_delete=models.CASCADE, related_name="trial")
    iniciado_em  = models.DateTimeField(auto_now_add=True)
    expira_em    = models.DateTimeField()
    convertido   = models.BooleanField(default=False)
    convertido_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-iniciado_em"]

    def ativo(self):
        from django.utils import timezone
        return not self.convertido and self.expira_em > timezone.now()

    def dias_restantes(self):
        from django.utils import timezone
        delta = self.expira_em - timezone.now()
        return max(0, delta.days)

    def __str__(self):
        return f"Trial {self.empresa.nome} — {'ativo' if self.ativo() else 'expirado'}"


class OnboardingPasso(models.Model):
    """Rastreia quais passos do onboarding a empresa completou."""
    PASSOS = [
        ("primeiro_funcionario", "Primeiro funcionário cadastrado"),
        ("primeiro_aso",         "Primeiro ASO emitido"),
        ("primeiro_epi",         "Primeira ficha de EPI registrada"),
        ("esocial_config",       "eSocial configurado"),
        ("usuario_adicional",    "Usuário adicional criado"),
        ("relatorio_gerado",     "Relatório gerado"),
        ("assinatura_digital",   "Primeira assinatura digital enviada"),
    ]

    empresa      = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="onboarding_passos")
    passo        = models.CharField(max_length=40, choices=PASSOS)
    concluido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("empresa", "passo")]
        ordering = ["concluido_em"]

    def __str__(self):
        return f"{self.empresa.nome} — {self.passo}"


class IntegracaoRH(models.Model):
    """Conector com sistemas de RH (TOTVS, ADP, Senior, SAP)."""
    SISTEMAS = [
        ("totvs",   "TOTVS Protheus / RM"),
        ("adp",     "ADP Workforce"),
        ("senior",  "Senior Sistemas"),
        ("sap",     "SAP HCM"),
        ("esocial", "eSocial Gov (direto)"),
        ("outro",   "Outro / Custom"),
    ]
    STATUS = [
        ("ativo",   "Ativo"),
        ("inativo", "Inativo"),
        ("erro",    "Erro na última sync"),
    ]

    empresa               = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="integracoes_rh")
    sistema               = models.CharField(max_length=20, choices=SISTEMAS)
    nome                  = models.CharField(max_length=120, blank=True, default="")
    status                = models.CharField(max_length=10, choices=STATUS, default="inativo")
    webhook_secret        = models.CharField(max_length=64, default=_codigo_acesso)
    endpoint_destino      = models.URLField(blank=True, default="")
    funcionarios_importados = models.PositiveIntegerField(default=0)
    ultimo_sync_em        = models.DateTimeField(null=True, blank=True)
    ultimo_erro           = models.TextField(blank=True, default="")
    criado_em             = models.DateTimeField(auto_now_add=True)
    atualizado_em         = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "sistema")]
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.empresa.nome} ↔ {self.get_sistema_display()} [{self.status}]"


class ApiKeyEmpresa(models.Model):
    """Chave de API para acesso programático aos dados da empresa."""
    empresa    = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="api_keys")
    nome       = models.CharField(max_length=100)
    chave      = models.CharField(max_length=64, unique=True, default=_codigo_acesso)
    ativa      = models.BooleanField(default=True)
    total_chamadas = models.PositiveBigIntegerField(default=0)
    ultimo_uso_em  = models.DateTimeField(null=True, blank=True)
    criado_em  = models.DateTimeField(auto_now_add=True)
    revogada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"{self.empresa.nome} / {self.nome} ({'ativa' if self.ativa else 'revogada'})"


class UsoApiEmpresa(models.Model):
    """Uso mensal por endpoint para billing e analytics."""
    empresa    = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="uso_api")
    api_key    = models.ForeignKey(ApiKeyEmpresa, on_delete=models.SET_NULL, null=True, blank=True, related_name="uso")
    ano_mes    = models.CharField(max_length=7)   # ex.: "2026-05"
    endpoint   = models.CharField(max_length=120)
    chamadas   = models.PositiveBigIntegerField(default=0)

    class Meta:
        unique_together = [("empresa", "api_key", "ano_mes", "endpoint")]
        ordering = ["-ano_mes"]
        indexes = [models.Index(fields=["empresa", "ano_mes"])]

    def __str__(self):
        return f"{self.empresa.nome} {self.ano_mes} {self.endpoint}: {self.chamadas}"


class ConteudoSSTPublicado(models.Model):
    """Conteúdo publicado pelo gestor SST para os colaboradores (vídeos, treinamentos, comunicados, reuniões)."""
    TIPO_VIDEO = "video"
    TIPO_TREINAMENTO = "treinamento"
    TIPO_REUNIAO = "reuniao"
    TIPO_COMUNICADO = "comunicado"
    TIPO_CHOICES = [
        (TIPO_VIDEO, "Vídeo"),
        (TIPO_TREINAMENTO, "Treinamento"),
        (TIPO_REUNIAO, "Reunião de Vídeo"),
        (TIPO_COMUNICADO, "Comunicado"),
    ]

    AMBIENTE_ONSHORE = "onshore"
    AMBIENTE_OFFSHORE = "offshore"
    AMBIENTE_AMBOS = "ambos"
    AMBIENTE_CHOICES = [
        (AMBIENTE_ONSHORE, "Onshore"),
        (AMBIENTE_OFFSHORE, "Offshore"),
        (AMBIENTE_AMBOS, "Todos"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="conteudos_sst")
    titulo = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_COMUNICADO)
    descricao = models.TextField(blank=True, default="")
    url_conteudo = models.URLField(blank=True, default="")
    setor_alvo = models.ForeignKey("EmpresaSetor", on_delete=models.SET_NULL, null=True, blank=True, related_name="conteudos_sst")
    ambiente = models.CharField(max_length=10, choices=AMBIENTE_CHOICES, default=AMBIENTE_AMBOS)
    publicado_por = models.CharField(max_length=160, blank=True, default="")
    ativo = models.BooleanField(default=True)
    visualizacoes = models.PositiveIntegerField(default=0)
    publicado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publicado_em"]
        indexes = [
            models.Index(fields=["empresa", "tipo", "ativo"]),
            models.Index(fields=["empresa", "ambiente"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} — {self.get_tipo_display()}: {self.titulo}"


class RegistroConflitoCultural(models.Model):
    """Registro de conflito intercultural enviado pelo colaborador."""
    TIPO_COMUNICACAO = "comunicacao"
    TIPO_DISCRIMINACAO = "discriminacao"
    TIPO_IDIOMA = "idioma"
    TIPO_RELIGIAO = "religiao"
    TIPO_COMPORTAMENTO = "comportamento"
    TIPO_OUTRO = "outro"
    TIPO_CHOICES = [
        (TIPO_COMUNICACAO, "Barreira de comunicação"),
        (TIPO_DISCRIMINACAO, "Discriminação / preconceito"),
        (TIPO_IDIOMA, "Diferença de idioma"),
        (TIPO_RELIGIAO, "Diferença religiosa / cultural"),
        (TIPO_COMPORTAMENTO, "Comportamento inadequado"),
        (TIPO_OUTRO, "Outro"),
    ]

    STATUS_NOVO = "novo"
    STATUS_EM_ANALISE = "em_analise"
    STATUS_RESOLVIDO = "resolvido"
    STATUS_ARQUIVADO = "arquivado"
    STATUS_CHOICES = [
        (STATUS_NOVO, "Novo"),
        (STATUS_EM_ANALISE, "Em análise"),
        (STATUS_RESOLVIDO, "Resolvido"),
        (STATUS_ARQUIVADO, "Arquivado"),
    ]

    AMBIENTE_ONSHORE = "onshore"
    AMBIENTE_OFFSHORE = "offshore"
    AMBIENTE_CHOICES = [
        (AMBIENTE_ONSHORE, "Onshore"),
        (AMBIENTE_OFFSHORE, "Offshore"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="conflitos_culturais")
    alias = models.ForeignKey("ColaboradorAliasCorporativo", on_delete=models.CASCADE, related_name="conflitos_culturais")
    setor = models.ForeignKey("EmpresaSetor", on_delete=models.SET_NULL, null=True, blank=True, related_name="conflitos_culturais")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default=TIPO_OUTRO)
    ambiente = models.CharField(max_length=10, choices=AMBIENTE_CHOICES, default=AMBIENTE_ONSHORE)
    descricao = models.CharField(max_length=500, blank=True, default="")
    paises_envolvidos = models.CharField(max_length=200, blank=True, default="")
    anonimo = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOVO)
    observacao_gestor = models.CharField(max_length=280, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["empresa", "tipo"]),
        ]

    def __str__(self):
        return f"{self.empresa.nome} — conflito {self.get_tipo_display()} ({self.status})"


# ─── Plano de Saúde — módulos enterprise ─────────────────────────────────────

class ContratoGrupo(models.Model):
    """Contrato corporativo (empresa-cliente) com um plano de saúde."""
    STATUS_ATIVO = "ativo"
    STATUS_SUSPENSO = "suspenso"
    STATUS_ENCERRADO = "encerrado"
    STATUS_CHOICES = [
        (STATUS_ATIVO, "Ativo"),
        (STATUS_SUSPENSO, "Suspenso"),
        (STATUS_ENCERRADO, "Encerrado"),
    ]

    empresa_operadora = models.ForeignKey(
        "Empresa", on_delete=models.CASCADE,
        related_name="contratos_grupo_operados",
    )
    plano = models.ForeignKey(
        "PlanoSaude", on_delete=models.CASCADE,
        related_name="contratos_grupo",
    )
    razao_social = models.CharField(max_length=200)
    nome_fantasia = models.CharField(max_length=200, blank=True, default="")
    cnpj = models.CharField(max_length=18, blank=True, default="")
    contato_nome = models.CharField(max_length=100, blank=True, default="")
    contato_email = models.EmailField(blank=True, default="")
    contato_telefone = models.CharField(max_length=20, blank=True, default="")
    total_vidas = models.IntegerField(default=0)
    mensalidade_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    data_inicio = models.DateField()
    data_renovacao = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_ATIVO)
    logo_emoji = models.CharField(max_length=10, blank=True, default="🏢")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["razao_social"]

    def __str__(self):
        return f"{self.razao_social} — {self.plano.nome}"


class TeleconsultaAutorizacao(models.Model):
    """Autorização de teleconsulta emitida pela operadora."""
    STATUS_PENDENTE = "pendente"
    STATUS_AUTORIZADO = "autorizado"
    STATUS_NEGADO = "negado"
    STATUS_REALIZADO = "realizado"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_AUTORIZADO, "Autorizado"),
        (STATUS_NEGADO, "Negado"),
        (STATUS_REALIZADO, "Realizado"),
    ]

    empresa = models.ForeignKey(
        "Empresa", on_delete=models.CASCADE,
        related_name="teleconsultas",
    )
    beneficiario = models.ForeignKey(
        "BeneficiarioPlano", on_delete=models.CASCADE,
        related_name="teleconsultas",
    )
    especialidade = models.CharField(max_length=100)
    medico_solicitante = models.CharField(max_length=150, blank=True, default="")
    plataforma = models.CharField(
        max_length=50,
        choices=[
            ("conexa", "Conexa Saúde"),
            ("iclinic", "iClinic"),
            ("drconsulta", "Dr. Consulta"),
            ("outro", "Outro"),
        ],
        default="conexa",
    )
    link_consulta = models.URLField(blank=True, default="")
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_agendada = models.DateTimeField(null=True, blank=True)
    data_realizada = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    nota_satisfacao = models.IntegerField(null=True, blank=True)  # 1-5
    observacoes = models.TextField(blank=True, default="")
    autorizado_por = models.CharField(max_length=100, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_solicitacao"]

    def __str__(self):
        return f"Teleconsulta {self.beneficiario.nome} — {self.especialidade} ({self.status})"


class BeneficiarioOdonto(models.Model):
    """Beneficiário de plano odontológico vinculado à operadora."""
    STATUS_ATIVO = "ativo"
    STATUS_CARENCIA = "carencia"
    STATUS_SUSPENSO = "suspenso"
    STATUS_CANCELADO = "cancelado"
    STATUS_CHOICES = [
        (STATUS_ATIVO, "Ativo"),
        (STATUS_CARENCIA, "Em Carência"),
        (STATUS_SUSPENSO, "Suspenso"),
        (STATUS_CANCELADO, "Cancelado"),
    ]

    empresa = models.ForeignKey(
        "Empresa", on_delete=models.CASCADE,
        related_name="beneficiarios_odonto",
    )
    nome = models.CharField(max_length=200)
    cpf = models.CharField(max_length=14, blank=True, default="")
    data_nascimento = models.DateField(null=True, blank=True)
    telefone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    plano_odonto = models.CharField(max_length=100, blank=True, default="Odonto Básico")
    numero_carteirinha = models.CharField(max_length=50, blank=True, default="")
    data_inicio_vigencia = models.DateField(null=True, blank=True)
    data_fim_vigencia = models.DateField(null=True, blank=True)
    data_ultimo_uso = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_ATIVO)
    dentista_responsavel = models.CharField(max_length=150, blank=True, default="")
    cro_dentista = models.CharField(max_length=20, blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} — {self.plano_odonto}"


class GuiaOdonto(models.Model):
    """Guia/autorização de procedimento odontológico."""
    STATUS_PENDENTE = "pendente"
    STATUS_AUTORIZADO = "autorizado"
    STATUS_NEGADO = "negado"
    STATUS_EXECUTADO = "executado"
    STATUS_CHOICES = [
        (STATUS_PENDENTE, "Pendente"),
        (STATUS_AUTORIZADO, "Autorizado"),
        (STATUS_NEGADO, "Negado"),
        (STATUS_EXECUTADO, "Executado"),
    ]

    empresa = models.ForeignKey(
        "Empresa", on_delete=models.CASCADE,
        related_name="guias_odonto",
    )
    beneficiario = models.ForeignKey(
        BeneficiarioOdonto, on_delete=models.CASCADE,
        related_name="guias",
    )
    codigo_tuss = models.CharField(max_length=20, blank=True, default="")
    procedimento = models.CharField(max_length=200)
    dentista = models.CharField(max_length=150, blank=True, default="")
    clinica = models.CharField(max_length=200, blank=True, default="")
    data_solicitacao = models.DateTimeField(auto_now_add=True)
    data_execucao = models.DateField(null=True, blank=True)
    valor_estimado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default=STATUS_PENDENTE)
    justificativa_negacao = models.TextField(blank=True, default="")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_solicitacao"]

    def __str__(self):
        return f"{self.procedimento} — {self.beneficiario.nome} ({self.status})"


class MensagemPlano(models.Model):
    """Mensagem trocada entre a operadora e beneficiários ou prestadores."""
    TIPO_BENEFICIARIO = "beneficiario"
    TIPO_PRESTADOR = "prestador"
    TIPO_CHOICES = [
        (TIPO_BENEFICIARIO, "Beneficiário"),
        (TIPO_PRESTADOR, "Prestador"),
    ]
    CANAL_PLATAFORMA = "plataforma"
    CANAL_EMAIL = "email"
    CANAL_SMS = "sms"
    CANAL_CHOICES = [
        (CANAL_PLATAFORMA, "Plataforma"),
        (CANAL_EMAIL, "E-mail"),
        (CANAL_SMS, "SMS"),
    ]
    DIRECAO_SAIDA = "saida"
    DIRECAO_ENTRADA = "entrada"
    DIRECAO_CHOICES = [
        (DIRECAO_SAIDA, "Operadora → Destinatário"),
        (DIRECAO_ENTRADA, "Destinatário → Operadora"),
    ]

    empresa = models.ForeignKey(
        "Empresa", on_delete=models.CASCADE,
        related_name="mensagens_plano",
    )
    tipo_destinatario = models.CharField(max_length=15, choices=TIPO_CHOICES)
    beneficiario = models.ForeignKey(
        "BeneficiarioPlano", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="mensagens",
    )
    prestador = models.ForeignKey(
        "PrestadorPlanoSaude", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="mensagens",
    )
    canal = models.CharField(max_length=15, choices=CANAL_CHOICES, default=CANAL_PLATAFORMA)
    direcao = models.CharField(max_length=10, choices=DIRECAO_CHOICES, default=DIRECAO_SAIDA)
    assunto = models.CharField(max_length=200, blank=True, default="")
    conteudo = models.TextField()
    lida = models.BooleanField(default=False)
    enviado_por = models.CharField(max_length=100, blank=True, default="Operadora")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        dest = self.beneficiario.nome if self.beneficiario else (self.prestador.nome_fantasia if self.prestador else "?")
        return f"Msg → {dest} ({self.canal})"


# ═══════════════════════════════════════════════════════════
# MÓDULOS SST EXPANSÃO — PPP, LTCAT/LIP, REDE, LAB, FINANCEIRO
# ═══════════════════════════════════════════════════════════

class PPPFuncionario(models.Model):
    """Perfil Profissiográfico Previdenciário — IN INSS 128/2022."""
    STATUS = [("rascunho", "Rascunho"), ("finalizado", "Finalizado"), ("entregue", "Entregue ao trabalhador")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="ppps")
    funcionario = models.ForeignKey("FuncionarioSST", on_delete=models.CASCADE, related_name="ppps")
    nit_pis = models.CharField(max_length=20, blank=True, default="", verbose_name="NIT/PIS do trabalhador")
    cbo = models.CharField(max_length=10, blank=True, default="", verbose_name="CBO do cargo")
    data_geracao = models.DateField(default=__import__('datetime').date.today)
    data_desligamento = models.DateField(null=True, blank=True)
    data_finalizacao = models.DateField(null=True, blank=True)
    responsavel_tecnico = models.CharField(max_length=200, blank=True, default="")
    conselho_registro = models.CharField(max_length=100, blank=True, default="", verbose_name="CRM/CREA/CRQ")
    agentes_nocivos = models.JSONField(default=list, blank=True)
    monitoracao_biologica = models.JSONField(default=list, blank=True)
    historico_cargos = models.JSONField(default=list, blank=True)
    resultado_conclusao = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS, default="rascunho")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_geracao"]
        indexes = [models.Index(fields=["empresa", "funcionario"]), models.Index(fields=["empresa", "status"])]

    def __str__(self):
        return f"PPP {self.funcionario.nome} — {self.data_geracao}"


class LaudoTecnicoSST(models.Model):
    """LTCAT, LIP, LTIP, PGR, PCMSO — laudos técnicos SST."""
    TIPOS = [
        ("ltcat", "LTCAT"), ("lip", "LIP"), ("ltip", "LTIP"),
        ("pgr", "PGR"), ("pcmso", "PCMSO"),
    ]
    STATUS = [("rascunho", "Rascunho"), ("vigente", "Vigente"), ("vencido", "Vencido"), ("revogado", "Revogado")]
    GRAUS = [("minimo", "Mínimo (10%)"), ("medio", "Médio (20%)"), ("maximo", "Máximo (40%)"), ("nao_se_aplica", "Não se aplica")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="laudos_tecnicos")
    tipo = models.CharField(max_length=10, choices=TIPOS)
    posto_trabalho = models.CharField(max_length=200, blank=True, default="")
    setor = models.CharField(max_length=200, blank=True, default="")
    data_emissao = models.DateField(null=True, blank=True)
    data_assinatura = models.DateField(null=True, blank=True)
    responsavel_tecnico = models.CharField(max_length=200, blank=True, default="")
    conselho_registro = models.CharField(max_length=100, blank=True, default="")
    agentes_avaliados = models.JSONField(default=list, blank=True)
    metodologia = models.TextField(blank=True, default="")
    resultados = models.JSONField(default=list, blank=True)
    conclusao = models.TextField(blank=True, default="")
    grau_insalubridade = models.CharField(max_length=20, choices=GRAUS, blank=True, default="nao_se_aplica")
    adicional_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default="rascunho")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_emissao"]
        indexes = [models.Index(fields=["empresa", "tipo", "status"])]

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.empresa.nome} ({self.data_emissao})"


class ClinicaCredenciada(models.Model):
    """Rede nacional de clínicas credenciadas SolusCRT."""
    STATUS_CRED = [("pendente", "Pendente"), ("ativo", "Ativo"), ("suspenso", "Suspenso"), ("cancelado", "Cancelado")]
    TIPOS = [
        ("clinica_ocupacional", "Clínica de Medicina Ocupacional"),
        ("laboratorio", "Laboratório de Análises"),
        ("sesi", "SESI"), ("sesc", "SESC"), ("ame", "AME"),
        ("hospital", "Hospital"), ("policlinica", "Policlínica"),
    ]

    nome = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=18, unique=True)
    tipo = models.CharField(max_length=30, choices=TIPOS, default="clinica_ocupacional")
    especialidades = models.JSONField(default=list)
    endereco = models.CharField(max_length=300, blank=True, default="")
    cidade = models.CharField(max_length=100)
    uf = models.CharField(max_length=2)
    cep = models.CharField(max_length=9, blank=True, default="")
    telefone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    responsavel_tecnico = models.CharField(max_length=200, blank=True, default="")
    crm = models.CharField(max_length=20, blank=True, default="")
    horario_atendimento = models.CharField(max_length=100, blank=True, default="Seg–Sex 08h–18h")
    aceita_agendamento_online = models.BooleanField(default=True)
    tempo_medio_laudo_dias = models.PositiveSmallIntegerField(default=3)
    avaliacao_media = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_avaliacoes = models.PositiveIntegerField(default=0)
    lat = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    lng = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    status_credenciamento = models.CharField(max_length=20, choices=STATUS_CRED, default="pendente")
    ativa = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-avaliacao_media", "nome"]
        indexes = [
            models.Index(fields=["uf", "status_credenciamento"]),
            models.Index(fields=["cidade", "uf"]),
        ]

    def __str__(self):
        return f"{self.nome} — {self.cidade}/{self.uf}"


class LaboratorioIntegrado(models.Model):
    """Laboratório parceiro com integração de resultados."""
    TIPOS_INT = [("api", "API REST"), ("hl7", "HL7"), ("fhir", "FHIR R4"), ("csv", "CSV"), ("manual", "Manual")]

    nome = models.CharField(max_length=200)
    cnpj = models.CharField(max_length=18, unique=True)
    cidade = models.CharField(max_length=100, blank=True, default="")
    uf = models.CharField(max_length=2, blank=True, default="")
    tipo_integracao = models.CharField(max_length=10, choices=TIPOS_INT, default="manual")
    endpoint_api = models.URLField(blank=True, default="")
    token_api = models.CharField(max_length=500, blank=True, default="")
    ativo = models.BooleanField(default=True)
    total_resultados_enviados = models.PositiveIntegerField(default=0)
    ultima_sincronizacao = models.DateField(null=True, blank=True)
    empresas_vinculadas = models.ManyToManyField(Empresa, blank=True, related_name="laboratorios_integrados")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.tipo_integracao})"


class ResultadoExameLaboratorio(models.Model):
    """Resultado de exame importado de laboratório integrado."""
    CRITICIDADE = [("normal", "Normal"), ("atencao", "Atenção"), ("critico", "Crítico")]
    VIA = [("api", "API"), ("hl7", "HL7"), ("fhir", "FHIR"), ("csv", "CSV"), ("manual", "Manual")]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="resultados_laboratorio")
    funcionario = models.ForeignKey("FuncionarioSST", on_delete=models.CASCADE, related_name="resultados_laboratorio")
    laboratorio = models.ForeignKey(LaboratorioIntegrado, null=True, blank=True, on_delete=models.SET_NULL)
    laboratorio_nome = models.CharField(max_length=200)
    exame = models.CharField(max_length=200)
    data_coleta = models.DateField()
    data_resultado = models.DateField(null=True, blank=True)
    resultado = models.CharField(max_length=500)
    unidade = models.CharField(max_length=50, blank=True, default="")
    valor_referencia = models.CharField(max_length=200, blank=True, default="")
    alterado = models.BooleanField(default=False)
    criticidade = models.CharField(max_length=10, choices=CRITICIDADE, default="normal")
    medico_responsavel = models.CharField(max_length=200, blank=True, default="")
    importado_via = models.CharField(max_length=10, choices=VIA, default="manual")
    vinculado_aso = models.ForeignKey("ASOOcupacional", null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="resultados_lab")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_coleta"]
        indexes = [
            models.Index(fields=["empresa", "funcionario"]),
            models.Index(fields=["empresa", "alterado"]),
            models.Index(fields=["empresa", "criticidade"]),
        ]

    def __str__(self):
        return f"{self.exame} — {self.funcionario.nome} ({self.data_coleta})"


class FaturaClinica(models.Model):
    """Fatura de serviços emitida pela clínica para empresa-cliente."""
    STATUS = [
        ("pendente", "Pendente"), ("enviada", "Enviada"), ("paga", "Paga"),
        ("vencida", "Vencida"), ("cancelada", "Cancelada"),
        ("em_glosa", "Em glosa"), ("parcial", "Pago parcialmente"),
    ]

    clinica = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="faturas_emitidas")
    numero = models.CharField(max_length=30, unique=True)
    empresa_cliente_nome = models.CharField(max_length=200)
    empresa_cliente_cnpj = models.CharField(max_length=18)
    data_emissao = models.DateField()
    data_vencimento = models.DateField()
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pendente")
    itens = models.JSONField(default=list)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    forma_pagamento = models.CharField(max_length=50, blank=True, default="transferencia")
    glosa_valor = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    glosa_motivo = models.TextField(blank=True, default="")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_emissao"]
        indexes = [
            models.Index(fields=["clinica", "status"]),
            models.Index(fields=["clinica", "data_emissao"]),
        ]

    def __str__(self):
        return f"Fatura {self.numero} — {self.empresa_cliente_nome} R${self.total}"


class DespesaClinica(models.Model):
    """Despesa operacional da clínica (contas a pagar)."""
    CATEGORIAS = [
        ("pessoal", "Pessoal / Folha"),
        ("equipamentos", "Equipamentos / Manutenção"),
        ("insumos", "Insumos / Reagentes"),
        ("aluguel", "Aluguel / Imóvel"),
        ("sistema", "Sistemas / TI"),
        ("marketing", "Marketing"),
        ("impostos", "Impostos / Taxas"),
        ("outros", "Outros"),
    ]

    clinica = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="despesas_clinica")
    descricao = models.CharField(max_length=300)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default="outros")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    data_competencia = models.DateField()
    data_vencimento = models.DateField(null=True, blank=True)
    pago = models.BooleanField(default=False)
    data_pagamento = models.DateField(null=True, blank=True)
    fornecedor = models.CharField(max_length=200, blank=True, default="")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data_competencia"]
        indexes = [models.Index(fields=["clinica", "data_competencia"]), models.Index(fields=["clinica", "pago"])]

    def __str__(self):
        return f"{self.descricao} R${self.valor} ({self.data_competencia})"


class FAPEmpresa(models.Model):
    """
    FAP — Fator Acidentário de Prevenção.
    Registra o FAP anual publicado pelo INSS para a empresa,
    calculando impacto sobre o RAT (Risco Ambiental do Trabalho).
    """
    FONTE_CHOICES = [
        ("manual", "Informado manualmente"),
        ("inss_portal", "Importado do portal INSS/PLENUS"),
        ("importado", "Importado via arquivo"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="faps")
    ano = models.PositiveSmallIntegerField()                      # ex: 2026
    cnae = models.CharField(max_length=20, blank=True, default="")
    cnae_descricao = models.CharField(max_length=300, blank=True, default="")
    grau_risco = models.PositiveSmallIntegerField(default=2)     # 1, 2 ou 3
    rat_base_pct = models.DecimalField(
        max_digits=5, decimal_places=4, default=2.0,
        help_text="Alíquota RAT base: 1.0, 2.0 ou 3.0%"
    )
    fap_valor = models.DecimalField(
        max_digits=6, decimal_places=4,
        help_text="FAP publicado pelo INSS — entre 0.5000 e 2.0000"
    )
    folha_salarial_mensal = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        help_text="Folha de pagamento mensal bruta para cálculo do impacto"
    )
    fonte = models.CharField(max_length=20, choices=FONTE_CHOICES, default="manual")
    publicado_em = models.DateField(null=True, blank=True,
                                    help_text="Data de publicação do FAP pelo INSS no DOU")
    prazo_contestacao = models.DateField(null=True, blank=True,
                                         help_text="Prazo de contestação (publicação + 30 dias)")
    contestado = models.BooleanField(default=False)
    resultado_contestacao = models.CharField(max_length=200, blank=True, default="",
                                              help_text="Ex: Indeferido / Deferido — FAP reduzido para 0.8500")
    observacoes = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("empresa", "ano")]
        ordering = ["-ano"]
        indexes = [
            models.Index(fields=["empresa", "ano"]),
        ]

    def __str__(self):
        return f"FAP {self.ano} — {self.empresa.nome} — {self.fap_valor}"


# ─── CIPA — Comissão Interna de Prevenção de Acidentes ──────────────────────

class ComissaoCIPA(models.Model):
    STATUS_CHOICES = [
        ("ativa", "Ativa"),
        ("encerrada", "Encerrada"),
        ("em_formacao", "Em Formação"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="comissoes_cipa")
    mandato_inicio = models.DateField()
    mandato_fim = models.DateField()
    numero_membros_eleitos = models.PositiveSmallIntegerField(default=0)
    numero_membros_indicados = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="em_formacao")
    designacao_nr5 = models.BooleanField(
        default=False,
        help_text="Empresa com até 19 funcionários — designação em vez de eleição"
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-mandato_inicio"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
        ]

    def __str__(self):
        return f"CIPA {self.empresa.nome} ({self.mandato_inicio} – {self.mandato_fim})"


class MembroCIPA(models.Model):
    CARGO_CHOICES = [
        ("presidente", "Presidente"),
        ("vice_presidente", "Vice-Presidente"),
        ("secretario", "Secretário"),
        ("membro_eleito", "Membro Eleito"),
        ("membro_indicado", "Membro Indicado"),
    ]
    TIPO_CHOICES = [
        ("eleito", "Eleito"),
        ("indicado", "Indicado"),
    ]

    comissao = models.ForeignKey(ComissaoCIPA, on_delete=models.CASCADE, related_name="membros")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="mandatos_cipa")
    cargo = models.CharField(max_length=30, choices=CARGO_CHOICES)
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES)
    data_posse = models.DateField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["cargo"]

    def __str__(self):
        return f"{self.funcionario.nome} — {self.cargo} (CIPA {self.comissao_id})"


class ReuniaoCIPA(models.Model):
    TIPO_CHOICES = [
        ("ordinaria", "Ordinária"),
        ("extraordinaria", "Extraordinária"),
    ]
    STATUS_CHOICES = [
        ("agendada", "Agendada"),
        ("realizada", "Realizada"),
        ("cancelada", "Cancelada"),
    ]

    comissao = models.ForeignKey(ComissaoCIPA, on_delete=models.CASCADE, related_name="reunioes")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="ordinaria")
    data_reuniao = models.DateTimeField()
    pauta = models.TextField(blank=True)
    ata = models.TextField(blank=True)
    local = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="agendada")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_reuniao"]

    def __str__(self):
        return f"Reunião CIPA {self.tipo} — {self.data_reuniao.date()} ({self.status})"


class ParticipanteReuniaoCIPA(models.Model):
    reuniao = models.ForeignKey(ReuniaoCIPA, on_delete=models.CASCADE, related_name="participantes")
    funcionario = models.ForeignKey(FuncionarioSST, on_delete=models.CASCADE, related_name="reunioes_cipa")
    presente = models.BooleanField(default=True)
    assinatura_token = models.CharField(max_length=64, blank=True)

    class Meta:
        unique_together = [("reuniao", "funcionario")]

    def __str__(self):
        return f"{self.funcionario.nome} — {'presente' if self.presente else 'ausente'}"


# ─── Biometria Facial para EPI ───────────────────────────────────────────────

class BiometriaFuncionario(models.Model):
    funcionario = models.OneToOneField(
        FuncionarioSST, on_delete=models.CASCADE, related_name="biometria"
    )
    foto_base64 = models.TextField(
        help_text="Foto de referência em base64 (JPEG/PNG, max 500KB)"
    )
    hash_foto = models.CharField(
        max_length=64, help_text="SHA-256 da foto original"
    )
    cadastrado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-cadastrado_em"]

    def __str__(self):
        return f"Biometria — {self.funcionario.nome}"


# ─── Psicossocial NR-01 ──────────────────────────────────────────────────────

class AvaliacaoPsicossocial(models.Model):
    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("ativa", "Ativa"),
        ("encerrada", "Encerrada"),
        ("processada", "Processada"),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="avaliacoes_psicossociais")
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True)
    setor_alvo = models.CharField(max_length=200, blank=True, help_text="Setor/departamento alvo")
    data_inicio = models.DateField()
    data_fim = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="rascunho")
    anonima = models.BooleanField(default=True)
    link_token = models.CharField(
        max_length=64, unique=True,
        help_text="Token para acesso do colaborador"
    )
    total_enviados = models.PositiveIntegerField(default=0)
    total_respondidos = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_inicio"]
        indexes = [
            models.Index(fields=["empresa", "status"]),
            models.Index(fields=["link_token"]),
        ]

    def __str__(self):
        return f"{self.titulo} — {self.empresa.nome} ({self.status})"


class QuestaoAvaliacaoPsicossocial(models.Model):
    CATEGORIA_CHOICES = [
        ("carga_trabalho", "Carga de Trabalho"),
        ("autonomia", "Autonomia e Controle"),
        ("relacionamento", "Relacionamento Interpessoal"),
        ("reconhecimento", "Reconhecimento e Recompensa"),
        ("seguranca", "Segurança no Emprego"),
        ("equilibrio", "Equilíbrio Trabalho-Vida"),
        ("violencia", "Violência e Assédio"),
    ]
    ESCALA_CHOICES = [
        ("likert5", "Likert 1-5"),
        ("sim_nao", "Sim/Não"),
    ]

    avaliacao = models.ForeignKey(
        AvaliacaoPsicossocial, on_delete=models.CASCADE, related_name="questoes"
    )
    texto = models.TextField()
    categoria = models.CharField(max_length=30, choices=CATEGORIA_CHOICES)
    ordem = models.PositiveSmallIntegerField(default=0)
    escala = models.CharField(max_length=15, choices=ESCALA_CHOICES, default="likert5")

    class Meta:
        ordering = ["ordem"]

    def __str__(self):
        return f"Q{self.ordem}: {self.texto[:60]}"


class RespostaPsicossocial(models.Model):
    avaliacao = models.ForeignKey(
        AvaliacaoPsicossocial, on_delete=models.CASCADE, related_name="respostas"
    )
    questao = models.ForeignKey(
        QuestaoAvaliacaoPsicossocial, on_delete=models.CASCADE, related_name="respostas"
    )
    resposta_num = models.PositiveSmallIntegerField(null=True, blank=True)   # 1-5 para Likert
    resposta_bool = models.BooleanField(null=True, blank=True)               # para sim/não
    respondido_em = models.DateTimeField(auto_now_add=True)
    # SEM FK para funcionário se anônima=True
    funcionario = models.ForeignKey(
        FuncionarioSST, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="respostas_psicossociais"
    )

    class Meta:
        ordering = ["-respondido_em"]

    def __str__(self):
        return f"Resposta — questao {self.questao_id} — avaliação {self.avaliacao_id}"


# ─────────────────────────────────────────────────────────────────────────────
# WHITE LABEL — Configuração de Marca
# ─────────────────────────────────────────────────────────────────────────────

class ConfiguracaoMarca(models.Model):
    """Personalização visual (white label) por empresa."""

    empresa = models.OneToOneField(
        Empresa, on_delete=models.CASCADE, related_name="configuracao_marca"
    )
    logo_url = models.URLField(blank=True, default="")
    cor_primaria = models.CharField(max_length=7, default="#00c9a7")   # teal padrão
    cor_secundaria = models.CharField(max_length=7, default="#1f6ff2") # azul padrão
    nome_marca = models.CharField(max_length=80, blank=True, default="")
    mostrar_powered_by = models.BooleanField(default=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração de Marca"
        verbose_name_plural = "Configurações de Marca"

    def __str__(self):
        return f"Marca — {self.empresa.nome}"


# ─────────────────────────────────────────────────────────────────────────────
# WHATSAPP — Integração e Logs
# ─────────────────────────────────────────────────────────────────────────────

class IntegracaoWhatsApp(models.Model):
    """Configuração de integração WhatsApp (Z-API ou Evolution API) por empresa."""

    PROVIDER_ZAPI = "z-api"
    PROVIDER_EVOLUTION = "evolution"
    PROVIDERS = [
        (PROVIDER_ZAPI, "Z-API"),
        (PROVIDER_EVOLUTION, "Evolution API"),
    ]

    empresa = models.OneToOneField(
        Empresa, on_delete=models.CASCADE, related_name="integracao_whatsapp"
    )
    provider = models.CharField(max_length=20, choices=PROVIDERS, default=PROVIDER_ZAPI)
    instance_id = models.CharField(max_length=120, blank=True, default="")
    token = models.CharField(max_length=255, blank=True, default="")
    numero_remetente = models.CharField(max_length=20, blank=True, default="")
    ativo = models.BooleanField(default=False)

    # Quais eventos disparam notificações
    notif_aso = models.BooleanField(default=True)
    notif_treinamento = models.BooleanField(default=True)
    notif_epi = models.BooleanField(default=True)
    notif_cat = models.BooleanField(default=True)
    notif_psicossocial = models.BooleanField(default=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Integração WhatsApp"
        verbose_name_plural = "Integrações WhatsApp"

    def __str__(self):
        return f"WhatsApp ({self.provider}) — {self.empresa.nome}"


class LogWhatsApp(models.Model):
    """Registro de cada mensagem enviada via WhatsApp."""

    STATUS_OK = "ok"
    STATUS_ERRO = "erro"
    STATUS_CHOICES = [(STATUS_OK, "Enviado"), (STATUS_ERRO, "Erro")]

    empresa = models.ForeignKey(
        Empresa, on_delete=models.CASCADE, related_name="logs_whatsapp"
    )
    numero_destino = models.CharField(max_length=20)
    mensagem = models.TextField()
    evento = models.CharField(max_length=60, default="manual")   # aso_vencendo, etc.
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OK)
    resposta_api = models.JSONField(default=dict, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-enviado_em"]
        verbose_name = "Log WhatsApp"
        verbose_name_plural = "Logs WhatsApp"


# ═════════════════════════════════════════════════════════════════════════════
# FARMÁCIA — PDV / PBM / DRE / DELIVERY
# ═════════════════════════════════════════════════════════════════════════════

class PDVSessao(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pdv_sessoes")
    operador = models.CharField(max_length=120)
    caixa_numero = models.PositiveSmallIntegerField(default=1)
    abertura = models.DateTimeField(auto_now_add=True)
    fechamento = models.DateTimeField(null=True, blank=True)
    fundo_caixa = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_vendas = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_dinheiro = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_pix = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_cartao_debito = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_cartao_credito = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_convenio = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    ativa = models.BooleanField(default=True)
    class Meta:
        ordering = ["-abertura"]
    def __str__(self):
        return f"Sessão PDV #{self.id} — {self.empresa.nome}"


class PDVVenda(models.Model):
    PGTO_DINHEIRO = "dinheiro"; PGTO_PIX = "pix"; PGTO_DEBITO = "debito"
    PGTO_CREDITO = "credito"; PGTO_CONVENIO = "convenio"
    PGTOS = [(PGTO_DINHEIRO,"Dinheiro"),(PGTO_PIX,"Pix"),(PGTO_DEBITO,"Débito"),
             (PGTO_CREDITO,"Crédito"),(PGTO_CONVENIO,"Convênio/PBM")]
    sessao = models.ForeignKey(PDVSessao, on_delete=models.CASCADE, related_name="vendas")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pdv_vendas")
    numero_cupom = models.CharField(max_length=40, blank=True)
    forma_pagamento = models.CharField(max_length=20, choices=PGTOS, default=PGTO_DINHEIRO)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    desconto = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    troco = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cpf_cliente = models.CharField(max_length=14, blank=True)
    cancelada = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-criado_em"]
    def __str__(self):
        return f"Venda #{self.id} — R${self.total}"


class PDVItemVenda(models.Model):
    venda = models.ForeignKey(PDVVenda, on_delete=models.CASCADE, related_name="itens")
    codigo_barras = models.CharField(max_length=40, blank=True)
    descricao = models.CharField(max_length=200)
    lote = models.CharField(max_length=40, blank=True)
    quantidade = models.DecimalField(max_digits=10, decimal_places=3, default=1)
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    desconto_item = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_item = models.DecimalField(max_digits=14, decimal_places=2)
    controlado = models.BooleanField(default=False)
    receita_numero = models.CharField(max_length=60, blank=True)


class PBMConvenio(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pbm_convenios")
    nome = models.CharField(max_length=120)  # Funcional, Epharma, Onofre...
    codigo_credenciado = models.CharField(max_length=60, blank=True)
    percentual_desconto_padrao = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"PBM {self.nome} — {self.empresa.nome}"


class FarmaciaPopularRegistro(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="farmacia_popular")
    mes_referencia = models.DateField()
    medicamentos_dispensados = models.PositiveIntegerField(default=0)
    valor_subsidiado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_copagamento = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    arquivos_transmitidos = models.BooleanField(default=False)
    enviado_em = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-mes_referencia"]


class DREFarmacia(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="dre_farmacia")
    mes_referencia = models.DateField()
    receita_bruta = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    devolucoes = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    impostos = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    cmv = models.DecimalField(max_digits=16, decimal_places=2, default=0)  # Custo Mercadorias
    despesas_operacionais = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    despesas_pessoal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    despesas_aluguel = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    outras_despesas = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-mes_referencia"]
        unique_together = [["empresa", "mes_referencia"]]


class PedidoDelivery(models.Model):
    STATUS_CHOICES = [("aguardando","Aguardando"),("confirmado","Confirmado"),
                      ("em_preparo","Em Preparo"),("saiu","Saiu para Entrega"),
                      ("entregue","Entregue"),("cancelado","Cancelado")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pedidos_delivery")
    numero_pedido = models.CharField(max_length=40)
    cliente_nome = models.CharField(max_length=120)
    cliente_telefone = models.CharField(max_length=20)
    cliente_endereco = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aguardando")
    origem = models.CharField(max_length=40, default="whatsapp")  # whatsapp, site, app
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-criado_em"]


# ═════════════════════════════════════════════════════════════════════════════
# HOSPITAL — EMR / LIS / RIS / CIRURGIA / FARMÁCIA HOSPITALAR / TISS / IA
# ═════════════════════════════════════════════════════════════════════════════

class ProntuarioHospitalar(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="prontuarios_hospitalares")
    numero_prontuario = models.CharField(max_length=40, blank=True)
    paciente_nome = models.CharField(max_length=160)
    paciente_cpf = models.CharField(max_length=14, blank=True)
    paciente_nascimento = models.DateField(null=True, blank=True)
    paciente_sexo = models.CharField(max_length=1, choices=[("M","M"),("F","F"),("O","O")], default="M")
    paciente_telefone = models.CharField(max_length=20, blank=True)
    alergias = models.TextField(blank=True)
    comorbidades = models.TextField(blank=True)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-criado_em"]
    def __str__(self):
        return f"Prontuário {self.paciente_nome} — {self.empresa.nome}"


class EvolucaoProntuario(models.Model):
    prontuario = models.ForeignKey(ProntuarioHospitalar, on_delete=models.CASCADE, related_name="evolucoes")
    profissional = models.CharField(max_length=120)
    crm_coren = models.CharField(max_length=40, blank=True)
    tipo = models.CharField(max_length=30, default="medica")  # medica, enfermagem, fisioterapia...
    texto = models.TextField()
    cid10 = models.CharField(max_length=10, blank=True)
    assinado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-assinado_em"]


class PrescricaoProntuario(models.Model):
    prontuario = models.ForeignKey(ProntuarioHospitalar, on_delete=models.CASCADE, related_name="prescricoes")
    profissional = models.CharField(max_length=120)
    medicamento = models.CharField(max_length=200)
    dose = models.CharField(max_length=60)
    via = models.CharField(max_length=40)
    frequencia = models.CharField(max_length=60)
    duracao = models.CharField(max_length=40, blank=True)
    dispensado = models.BooleanField(default=False)
    prescrito_em = models.DateTimeField(auto_now_add=True)
    ia_aprovada = models.BooleanField(null=True, blank=True)  # IA autorização
    ia_observacao = models.CharField(max_length=300, blank=True)
    class Meta:
        ordering = ["-prescrito_em"]


class BlocoCirurgico(models.Model):
    SITUACAO_CHOICES = [("agendada","Agendada"),("em_andamento","Em andamento"),
                        ("concluida","Concluída"),("cancelada","Cancelada"),("suspensa","Suspensa")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="bloco_cirurgico_agendas")
    prontuario = models.ForeignKey(ProntuarioHospitalar, null=True, blank=True, on_delete=models.SET_NULL)
    paciente_nome = models.CharField(max_length=160)
    tipo_cirurgia = models.CharField(max_length=200)
    cid10 = models.CharField(max_length=10, blank=True)
    cbhpm = models.CharField(max_length=20, blank=True)  # Classificação Brasileira de Procedimentos
    cirurgiao = models.CharField(max_length=120)
    anestesista = models.CharField(max_length=120, blank=True)
    sala = models.CharField(max_length=40, blank=True)
    data_hora = models.DateTimeField()
    duracao_prevista_min = models.PositiveSmallIntegerField(default=60)
    situacao = models.CharField(max_length=20, choices=SITUACAO_CHOICES, default="agendada")
    relatorio_cirurgico = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-data_hora"]


class FarmaciaHospitalarItem(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="farmacia_hospitalar")
    descricao = models.CharField(max_length=200)
    codigo_interno = models.CharField(max_length=60, blank=True)
    apresentacao = models.CharField(max_length=80, blank=True)
    principio_ativo = models.CharField(max_length=120, blank=True)
    classe_terapeutica = models.CharField(max_length=80, blank=True)
    controlado = models.BooleanField(default=False)
    estoque_atual = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    estoque_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unidade = models.CharField(max_length=20, default="un")
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["descricao"]


class ExameLIS(models.Model):
    STATUS_CHOICES = [("solicitado","Solicitado"),("coletado","Coletado"),
                      ("em_analise","Em análise"),("resultado","Resultado disponível"),
                      ("entregue","Entregue")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="exames_lis")
    prontuario = models.ForeignKey(ProntuarioHospitalar, null=True, blank=True, on_delete=models.SET_NULL)
    paciente_nome = models.CharField(max_length=160)
    tipo_exame = models.CharField(max_length=120)
    codigo_tuss = models.CharField(max_length=20, blank=True)
    solicitante = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="solicitado")
    resultado = models.TextField(blank=True)
    valores_referencia = models.TextField(blank=True)
    solicitado_em = models.DateTimeField(auto_now_add=True)
    resultado_em = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-solicitado_em"]


class ExameRIS(models.Model):
    MODALIDADES = [("rx","Raio-X"),("us","Ultrassom"),("tc","Tomografia"),
                   ("rm","Ressonância"),("mg","Mamografia"),("ec","Ecocardiograma"),("out","Outro")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="exames_ris")
    prontuario = models.ForeignKey(ProntuarioHospitalar, null=True, blank=True, on_delete=models.SET_NULL)
    paciente_nome = models.CharField(max_length=160)
    modalidade = models.CharField(max_length=10, choices=MODALIDADES, default="rx")
    regiao_anatomica = models.CharField(max_length=100)
    solicitante = models.CharField(max_length=120)
    laudo = models.TextField(blank=True)
    imagem_url = models.URLField(blank=True)  # link PACS / storage
    laudado_em = models.DateTimeField(null=True, blank=True)
    solicitado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-solicitado_em"]


class GuiaTISS(models.Model):
    TIPO_CHOICES = [("consulta","Consulta"),("sadt","SADT"),("internacao","Internação"),
                    ("sp_sadt","SP/SADT"),("resumo","Resumo de Internação")]
    STATUS_CHOICES = [("elaborada","Elaborada"),("enviada","Enviada"),("glosada","Glosada"),
                      ("paga","Paga"),("recurso","Em Recurso")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="guias_tiss")
    numero_guia = models.CharField(max_length=60, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="consulta")
    operadora_codigo = models.CharField(max_length=30, blank=True)
    operadora_nome = models.CharField(max_length=120, blank=True)
    beneficiario_nome = models.CharField(max_length=160)
    beneficiario_carteirinha = models.CharField(max_length=40, blank=True)
    cid10 = models.CharField(max_length=10, blank=True)
    procedimentos = models.JSONField(default=list)
    valor_apresentado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    valor_aprovado = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="elaborada")
    data_autorizacao = models.DateTimeField(null=True, blank=True)
    xml_tiss = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-criado_em"]


# ═════════════════════════════════════════════════════════════════════════════
# GOVERNO — e-SUS / PEC / FATURAMENTO SUS / FARMÁCIA BÁSICA / REGULAÇÃO /
#           TELECONSULTA / RAG-RDQA
# ═════════════════════════════════════════════════════════════════════════════

class ProntuarioCidadao(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="prontuarios_cidadao")
    cns = models.CharField(max_length=18, blank=True)  # Cartão Nacional de Saúde
    cpf = models.CharField(max_length=14, blank=True)
    nome_completo = models.CharField(max_length=160)
    data_nascimento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=1, choices=[("M","M"),("F","F"),("O","O")], default="M")
    telefone = models.CharField(max_length=20, blank=True)
    unidade_saude = models.CharField(max_length=120, blank=True)
    microarea = models.CharField(max_length=20, blank=True)
    acs_responsavel = models.CharField(max_length=120, blank=True)
    alergias = models.TextField(blank=True)
    condicoes_cronicas = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["nome_completo"]


class AtendimentoUBS(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="atendimentos_ubs")
    prontuario = models.ForeignKey(ProntuarioCidadao, null=True, blank=True, on_delete=models.SET_NULL)
    paciente_nome = models.CharField(max_length=160)
    cns = models.CharField(max_length=18, blank=True)
    profissional = models.CharField(max_length=120)
    cbo = models.CharField(max_length=10, blank=True)  # Classificação Brasileira de Ocupações
    procedimento_ab = models.CharField(max_length=20, blank=True)  # CIAP-2/AB
    cid10 = models.CharField(max_length=10, blank=True)
    unidade_saude = models.CharField(max_length=120, blank=True)
    turno = models.CharField(max_length=1, choices=[("M","Manhã"),("T","Tarde"),("N","Noite")], default="M")
    data_atendimento = models.DateField()
    texto_evolucao = models.TextField(blank=True)
    enviado_esus = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-data_atendimento"]


class FarmaciaBasicaItem(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="farmacia_basica")
    rename_codigo = models.CharField(max_length=20, blank=True)  # Código RENAME
    descricao = models.CharField(max_length=200)
    apresentacao = models.CharField(max_length=80, blank=True)
    estoque_atual = models.PositiveIntegerField(default=0)
    estoque_minimo = models.PositiveIntegerField(default=0)
    unidade_saude = models.CharField(max_length=120, blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["descricao"]


class DispensacaoFarmaciaBasica(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="dispensacoes_basica")
    item = models.ForeignKey(FarmaciaBasicaItem, on_delete=models.CASCADE)
    cns_cidadao = models.CharField(max_length=18, blank=True)
    paciente_nome = models.CharField(max_length=160)
    quantidade = models.PositiveIntegerField(default=1)
    profissional = models.CharField(max_length=120)
    receita_numero = models.CharField(max_length=40, blank=True)
    dispensado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-dispensado_em"]


class RegulacaoAssistencial(models.Model):
    TIPO_CHOICES = [("consulta_esp","Consulta Especializada"),("exame","Exame"),
                    ("internacao","Internação"),("cirurgia","Cirurgia Eletiva")]
    STATUS_CHOICES = [("aguardando","Aguardando"),("agendado","Agendado"),
                      ("realizado","Realizado"),("cancelado","Cancelado")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="regulacoes")
    paciente_nome = models.CharField(max_length=160)
    cns = models.CharField(max_length=18, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="consulta_esp")
    especialidade = models.CharField(max_length=120, blank=True)
    procedimento = models.CharField(max_length=200, blank=True)
    cid10 = models.CharField(max_length=10, blank=True)
    unidade_origem = models.CharField(max_length=120)
    unidade_destino = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="aguardando")
    data_solicitacao = models.DateField(auto_now_add=True)
    data_agendamento = models.DateField(null=True, blank=True)
    prioridade = models.CharField(max_length=10, choices=[("normal","Normal"),("urgente","Urgente"),("emergen","Emergência")], default="normal")
    class Meta:
        ordering = ["-data_solicitacao"]


class FaturamentoSUSLote(models.Model):
    COMP_CHOICES = [("bpa","BPA-C / BPA-I"),("apac","APAC"),("aih","AIH")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="faturamentos_sus")
    competencia = models.CharField(max_length=6)  # AAAAMM
    tipo = models.CharField(max_length=10, choices=COMP_CHOICES, default="bpa")
    estabelecimento_cnes = models.CharField(max_length=10, blank=True)
    total_registros = models.PositiveIntegerField(default=0)
    total_aprovado = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    enviado_cnes = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-competencia"]


class TeleconsultaGoverno(models.Model):
    STATUS_CHOICES = [("agendada","Agendada"),("em_curso","Em curso"),
                      ("concluida","Concluída"),("cancelada","Cancelada")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="teleconsultas_gov")
    paciente_nome = models.CharField(max_length=160)
    cns = models.CharField(max_length=18, blank=True)
    profissional = models.CharField(max_length=120)
    especialidade = models.CharField(max_length=80, blank=True)
    data_hora = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="agendada")
    link_sala = models.URLField(blank=True)
    resumo = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-data_hora"]


class RelatorioRAG(models.Model):
    TIPO_CHOICES = [("pas","PAS — Programação Anual"),("rdqa","RDQA — Relatório Quadrimestral"),
                    ("rag","RAG — Relatório Anual de Gestão")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="relatorios_rag")
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES, default="rag")
    exercicio = models.PositiveSmallIntegerField()
    quadrimestre = models.PositiveSmallIntegerField(null=True, blank=True)  # 1,2,3
    conteudo = models.JSONField(default=dict)
    enviado_digisus = models.BooleanField(default=False)
    enviado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-exercicio", "-quadrimestre"]


class LogESUS(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="logs_esus")
    ficha_tipo = models.CharField(max_length=60)  # fichaIndividual, fichaAtendimento...
    registros_enviados = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, default="pendente")
    resposta_rnds = models.JSONField(default=dict, blank=True)
    enviado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-enviado_em"]


# ═════════════════════════════════════════════════════════════════════════════
# PLANO DE SAÚDE — CORRETORES / REDE CREDENCIADA / DIOPS / SIB / IA /
#                  PORTAL BENEFICIÁRIO
# ═════════════════════════════════════════════════════════════════════════════

class CorretoraPlano(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="corretoras")
    razao_social = models.CharField(max_length=160)
    cnpj = models.CharField(max_length=18, blank=True)
    susep = models.CharField(max_length=20, blank=True)  # Registro SUSEP
    telefone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    ativa = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["razao_social"]


class CorretoraComissao(models.Model):
    corretora = models.ForeignKey(CorretoraPlano, on_delete=models.CASCADE, related_name="comissoes")
    competencia = models.CharField(max_length=6)  # AAAAMM
    vidas_vendidas = models.PositiveIntegerField(default=0)
    receita_base = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    percentual_comissao = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    valor_comissao = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pago = models.BooleanField(default=False)
    pago_em = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-competencia"]


class RedeCredenciadaPlano(models.Model):
    TIPO_CHOICES = [("hospital","Hospital"),("clinica","Clínica"),("laboratorio","Laboratório"),
                    ("imagem","Centro de Imagem"),("odonto","Odontologia"),("outro","Outro")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="rede_credenciada_plano")
    nome = models.CharField(max_length=160)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="clinica")
    cnpj = models.CharField(max_length=18, blank=True)
    cnes = models.CharField(max_length=10, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    especialidades = models.JSONField(default=list)
    tabela_preco = models.CharField(max_length=40, blank=True)  # CBHPM, SUS, própria
    ativo = models.BooleanField(default=True)
    contrato_vigente_ate = models.DateField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["nome"]


class DIOPSDeclaracao(models.Model):
    STATUS_CHOICES = [("em_elaboracao","Em elaboração"),("validada","Validada"),
                      ("enviada","Enviada ANS"),("retificada","Retificada")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="diops_declaracoes")
    trimestre = models.CharField(max_length=6)  # AAAAT (T=1-4)
    registro_ans = models.CharField(max_length=10, blank=True)
    receita_operacional = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    despesa_assistencial = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    despesa_administrativa = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    resultado_periodo = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    vidas_ativas = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="em_elaboracao")
    xml_gerado = models.TextField(blank=True)
    enviado_em = models.DateTimeField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-trimestre"]


class SIBRegistro(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="sib_registros")
    competencia = models.CharField(max_length=6)  # AAAAMM
    registro_ans = models.CharField(max_length=10, blank=True)
    vidas_incluidas = models.PositiveIntegerField(default=0)
    vidas_excluidas = models.PositiveIntegerField(default=0)
    vidas_alteradas = models.PositiveIntegerField(default=0)
    total_vidas = models.PositiveIntegerField(default=0)
    enviado = models.BooleanField(default=False)
    enviado_em = models.DateTimeField(null=True, blank=True)
    retorno_ans = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-competencia"]


class IAAutorizacaoGuia(models.Model):
    DECISAO_CHOICES = [("aprovada","Aprovada"),("negada","Negada"),("revisao","Revisão humana")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="ia_autorizacoes")
    numero_guia = models.CharField(max_length=60)
    beneficiario = models.CharField(max_length=160)
    procedimento = models.CharField(max_length=200)
    codigo_tuss = models.CharField(max_length=20, blank=True)
    cid10 = models.CharField(max_length=10, blank=True)
    decisao = models.CharField(max_length=20, choices=DECISAO_CHOICES, default="revisao")
    score_confianca = models.FloatField(default=0.0)
    justificativa_ia = models.TextField(blank=True)
    revisada_por = models.CharField(max_length=120, blank=True)
    decisao_final = models.CharField(max_length=20, choices=DECISAO_CHOICES, null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-criado_em"]
        verbose_name_plural = "Autorizações IA de guias"

    def __str__(self):
        return f"IA Guia {self.numero_guia} — {self.decisao} — {self.criado_em:%d/%m/%Y}"


class PortalBeneficiarioToken(models.Model):
    """Token de acesso ao portal do beneficiário (sem login)."""
    beneficiario = models.OneToOneField(
        BeneficiarioPlano,
        on_delete=models.CASCADE,
        related_name="portal_token",
    )
    token = models.CharField(max_length=64, unique=True, db_index=True)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Token portal — {self.beneficiario.nome}"
