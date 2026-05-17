from django.db import models
import uuid


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

    plano = models.ForeignKey(PlanoSaude, on_delete=models.CASCADE, related_name="guias")
    beneficiario = models.ForeignKey(BeneficiarioPlano, on_delete=models.CASCADE, related_name="guias")
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
    justificativa_negativa = models.TextField(blank=True, default="")
    numero_autorizacao = models.CharField(max_length=50, blank=True, default="")
    validade_autorizacao = models.DateField(null=True, blank=True)
    solicitada_em = models.DateTimeField(auto_now_add=True)
    atualizada_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-solicitada_em"]

    def __str__(self):
        return f"Guia #{self.numero_guia or self.id} — {self.beneficiario.nome}"


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
    controlado         = models.BooleanField(default=False, help_text="Medicamento sujeito a controle especial (Portaria 344)")
    refrigerado        = models.BooleanField(default=False, help_text="Requer armazenamento refrigerado")
    validade_media_dias = models.PositiveIntegerField(default=365, help_text="Validade média em dias após fabricação")

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
        if self.quantidade_minima > 0 and self.quantidade_atual <= self.quantidade_minima * 1.1:
            return "critico"
        if self.quantidade_minima > 0 and self.quantidade_atual <= self.quantidade_minima * 1.5:
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

    empresa             = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="pacientes_internados")
    nome                = models.CharField(max_length=200)
    cpf                 = models.CharField(max_length=14, blank=True, default="")
    data_nascimento     = models.DateField(null=True, blank=True)
    data_internacao     = models.DateField()
    leito               = models.ForeignKey(LeitoHospitalar, on_delete=models.SET_NULL, null=True, blank=True, related_name="pacientes_internados")
    diagnostico_cid     = models.CharField(max_length=20, blank=True, default="")
    medico_responsavel  = models.CharField(max_length=200, blank=True, default="")
    convenio            = models.CharField(max_length=200, blank=True, default="")
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
    """Período de trial de 14 dias — self-service onboarding."""
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
