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
