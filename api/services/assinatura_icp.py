"""Assinatura digital ICP-Brasil de documentos clínicos, em SaaS multi-tenant.

A ICP-Brasil (Infraestrutura de Chaves Públicas Brasileira, instituída pela
Medida Provisória 2.200-2/2001) dá validade jurídica ao documento eletrônico
assinado com certificado emitido por Autoridade Certificadora credenciada.

QUEM ASSINA. Prescrição é ato médico: assina o **médico, pessoa física**, com
certificado vinculado ao seu CPF e ao seu CRM. Não assina a empresa que fornece
o software, nem o hospital (e-CNPJ não assina ato médico). Por isso a
configuração é **por empresa e por profissional**, nunca global — um hospital
com 40 oncologistas tem 40 configurações.

ONDE FICA A CHAVE. O caminho principal é o certificado **em nuvem** (VIDaaS,
vinculado ao registro no CRM, ou BirdID): a chave privada fica no cofre do
provedor credenciado e o médico autoriza cada assinatura. O sistema nunca vê a
chave. Guardar arquivo A1 e senha de dezenas de médicos num servidor de SaaS
seria assumir a identidade jurídica deles.

CAMINHO DE MIGRAÇÃO DOS CLIENTES. Hospital que já tem um serviço próprio de
assinatura aponta a URL dele (`api_hospital`): mandamos o resumo, ele devolve a
assinatura e os dados do certificado. É o que permite migrar um cliente sem
obrigá-lo a trocar de provedor.

REGRA INEGOCIÁVEL: sem certificado utilizável, nada é marcado como assinado.
A operação falha explicitamente e diz o que falta. Um sistema que finge assinar
é pior que um sem assinatura, porque a mentira teria valor jurídico.
"""
import base64
import hashlib
import json
import logging
from datetime import datetime

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ALGORITMO_RESUMO = "SHA-256"

TIPO_PRESCRICAO_QUIMIO = "prescricao_quimio"
TIPO_PRESCRICAO_INTERNACAO = "prescricao_internacao"
TIPOS_DOCUMENTO = {
    TIPO_PRESCRICAO_QUIMIO: "Prescrição de quimioterapia",
    TIPO_PRESCRICAO_INTERNACAO: "Prescrição de internação",
}

# Tempo máximo esperando a API de assinatura do hospital. Assinar é síncrono na
# beira do leito: melhor falhar rápido e explicar do que pendurar a tela.
TIMEOUT_API_HOSPITAL = 20


# ── Conteúdo canônico ─────────────────────────────────────────────────────────
# O que é assinado precisa ser reprodutível byte a byte: se a serialização
# variar com a ordem de um dicionário, a mesma prescrição gera resumos
# diferentes e toda assinatura "quebra" sozinha na verificação seguinte.

def _canonizar(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def _dados_emitente(empresa, cfg=None):
    """Identificação do médico e do estabelecimento, como o art. 2º exige.

    A Resolução CFM 2.299/2021 lista o conteúdo obrigatório do documento médico
    eletrônico: nome, CRM e endereço do médico, RQE quando houver, nome e
    documento do paciente, data e hora, e a assinatura. Assinar um documento
    sem esses campos deixa o documento incompleto mesmo com assinatura válida.
    """
    medico = {"nome": "", "crm": "", "rqe": "", "endereco": ""}
    if cfg is not None:
        medico = {
            "nome": cfg.profissional_nome or "",
            "crm": cfg.profissional_registro or "",
            "rqe": getattr(cfg, "profissional_rqe", "") or "",
            "endereco": getattr(cfg, "profissional_endereco", "") or "",
        }
    estabelecimento = {"nome": "", "crm": "", "endereco": "", "cnes": "",
                       "diretor_tecnico": "", "diretor_tecnico_crm": ""}
    rt = getattr(empresa, "responsabilidade_tecnica", None)
    if rt is not None:
        estabelecimento = {
            "nome": empresa.nome,
            "crm": rt.crm_pessoa_juridica or "",
            "endereco": rt.endereco or "",
            "cnes": rt.cnes or "",
            "diretor_tecnico": rt.diretor_tecnico_nome or "",
            "diretor_tecnico_crm": rt.diretor_tecnico_crm or "",
        }
    else:
        estabelecimento["nome"] = empresa.nome
    return medico, estabelecimento


def elementos_faltando_art2(ciclo, cfg=None):
    """Campos obrigatórios do art. 2º que ainda não estão preenchidos.

    Reportar isso é mais útil que recusar a assinatura: o documento pode ser
    emitido, mas quem assina precisa saber que ele sai incompleto.
    """
    medico, estab = _dados_emitente(ciclo.empresa, cfg)
    faltando = []
    if not medico["nome"]:
        faltando.append("nome do médico")
    if not medico["crm"]:
        faltando.append("CRM do médico")
    if not medico["endereco"] and not estab["endereco"]:
        faltando.append("endereço do médico ou do estabelecimento")
    if not ciclo.paciente_nome:
        faltando.append("nome do paciente")
    if not ciclo.cpf_paciente:
        faltando.append("número do documento legal do paciente")
    return faltando


def conteudo_canonico_prescricao(ciclo, cfg=None, emitido_em=None):
    """Documento assinável de uma prescrição de quimioterapia.

    Inclui tudo que é clinicamente determinante — paciente, protocolo, doses
    calculadas e pré-medicação. Se qualquer um mudar depois, a assinatura deixa
    de conferir, que é exatamente o comportamento desejado.
    """
    doses = [
        {
            "droga": d.get("droga"),
            "dose_referencia": d.get("dose_referencia"),
            "unidade": d.get("unidade"),
            "dose_calculada": d.get("dose_calculada"),
            "unidade_calculada": d.get("unidade_calculada"),
            "dia": d.get("dia"),
        }
        for d in (ciclo.doses_calculadas or [])
    ]
    suporte = [
        {
            "droga": m.get("droga"), "dose": m.get("dose"),
            "unidade": m.get("unidade"), "via": m.get("via"),
            "momento": m.get("momento"),
        }
        for m in (ciclo.protocolo.drogas_suporte or [])
    ]
    medico, estabelecimento = _dados_emitente(ciclo.empresa, cfg)
    # Data E HORA da emissão (art. 2º, "d"): a data do ciclo é dado clínico,
    # não o momento em que o documento foi emitido e assinado.
    emitido_em = emitido_em or timezone.now()
    payload = {
        "documento": TIPO_PRESCRICAO_QUIMIO,
        "versao": 2,
        "empresa_id": ciclo.empresa_id,
        "ciclo_id": ciclo.id,
        "emitido_em": timezone.localtime(emitido_em).isoformat(),
        "medico": medico,
        "estabelecimento": estabelecimento,
        "paciente": {"nome": ciclo.paciente_nome, "cpf": ciclo.cpf_paciente or ""},
        "diagnostico_cid10": ciclo.cid10_principal or "",
        "protocolo": {"codigo": ciclo.protocolo.codigo,
                      "nome": ciclo.protocolo.nome},
        "numero_ciclo": ciclo.numero_ciclo,
        "data_inicio": ciclo.data_inicio.isoformat() if ciclo.data_inicio else None,
        "superficie_corporal_m2": (float(ciclo.sc_m2) if ciclo.sc_m2 else None),
        "auc_alvo": float(ciclo.auc_alvo) if ciclo.auc_alvo else None,
        "doses": doses,
        "pre_medicacao": suporte,
        "medico_oncologista": ciclo.medico_oncologista or "",
    }
    return _canonizar(payload)


def resumo_sha256(conteudo):
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    return hashlib.sha256(conteudo).hexdigest()


# ── Provedores ────────────────────────────────────────────────────────────────

class AssinaturaIndisponivel(Exception):
    """Não há provedor utilizável. Carrega o que exatamente falta."""

    def __init__(self, mensagem, codigo="assinatura_nao_configurada",
                 pendencias=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo
        self.pendencias = pendencias or []


class ProvedorAssinatura:
    """Contrato que qualquer provedor precisa cumprir."""

    nome = "abstrato"
    rotulo = "Abstrato"

    def disponivel(self):
        raise NotImplementedError

    def requisitos_pendentes(self):
        return []

    def assinar(self, conteudo_bytes, contexto=None):
        raise NotImplementedError


class ProvedorNaoConfigurado(ProvedorAssinatura):
    """Estado padrão: o profissional não tem certificado configurado.

    Existe para que a ausência seja um caminho explícito e testável, em vez de
    um `None` solto espalhando AttributeError pela base.
    """

    nome = "nao_configurado"
    rotulo = "Não configurado"

    def __init__(self, motivo=None):
        self.motivo = motivo

    def disponivel(self):
        return False

    def requisitos_pendentes(self):
        if self.motivo:
            return [self.motivo]
        return [
            "Cadastrar o certificado do médico que assina, em Certificados de "
            "Assinantes do hospital.",
            "O certificado é do MÉDICO (pessoa física, e-CPF vinculado ao CRM) "
            "— não da empresa fornecedora do software nem do hospital.",
            "Caminho recomendado: certificado em nuvem (VIDaaS, ligado ao "
            "registro no CRM, ou BirdID), em que a chave fica com o provedor "
            "e o médico autoriza cada assinatura pelo celular.",
        ]

    def assinar(self, conteudo_bytes, contexto=None):
        raise AssinaturaIndisponivel(
            "Assinatura digital ICP-Brasil não configurada para este "
            "profissional. Nenhum documento foi assinado.",
            pendencias=self.requisitos_pendentes())


class ProvedorNuvemICP(ProvedorAssinatura):
    """Certificado em nuvem (VIDaaS / BirdID).

    O médico autoriza cada assinatura no celular e a chave nunca sai do cofre
    do provedor. Falta a credencial de aplicação, que é emitida pelo provedor
    para quem integra — por isso o provedor reporta a pendência em vez de
    simular uma assinatura.
    """

    nome = "nuvem"
    rotulo = "Certificado em nuvem"

    def __init__(self, cfg):
        self.cfg = cfg
        self.nome = cfg.provedor          # 'vidaas' ou 'birdid'
        self.rotulo = cfg.get_provedor_display()

    def requisitos_pendentes(self):
        faltando = []
        if not (self.cfg.identificador_provedor or self.cfg.profissional_cpf):
            faltando.append(
                "Informar o identificador do médico no provedor (normalmente o CPF).")
        if not self.cfg.cliente_id:
            faltando.append(
                f"Credencial de aplicação junto ao {self.cfg.get_provedor_display()}: "
                "cliente_id emitido pelo provedor para integração.")
        if not self.cfg.cliente_secreto:
            faltando.append("Segredo da aplicação (cliente_secreto) do provedor.")
        faltando.append(
            "Habilitar a integração no portal do provedor e autorizar o "
            "consentimento do médico (ele aprova a assinatura no celular).")
        return faltando

    def disponivel(self):
        # Enquanto não houver credencial de aplicação não há como assinar —
        # e dizer isso é mais útil que falhar na hora em que o médico clica.
        return bool(self.cfg.cliente_id and self.cfg.cliente_secreto
                    and (self.cfg.identificador_provedor
                         or self.cfg.profissional_cpf))

    def assinar(self, conteudo_bytes, contexto=None):
        raise AssinaturaIndisponivel(
            f"A integração com o {self.rotulo} ainda não está habilitada neste "
            "ambiente. Nenhum documento foi assinado.",
            codigo="provedor_nuvem_nao_habilitado",
            pendencias=self.requisitos_pendentes())


class ProvedorApiHospital(ProvedorAssinatura):
    """Serviço de assinatura do próprio hospital — o caminho de migração.

    O cliente que já tem assinatura funcionando aponta a URL dele. Mandamos o
    resumo e o identificador do profissional; ele devolve a assinatura e os
    dados do certificado usado. Nunca trafega chave privada nem senha de
    certificado por aqui.

    Contrato esperado (POST, JSON):
      envio   {"hash","algoritmo","tipo_documento","profissional":{"cpf","registro","nome"}}
      retorno {"assinatura_b64", "certificado":{"titular","cpf_cnpj","emissor",
               "numero_serie","valido_de","valido_ate"}, "carimbo_tempo_em"?}
    """

    nome = "api_hospital"
    rotulo = "API de assinatura do hospital"

    def __init__(self, cfg):
        self.cfg = cfg

    def requisitos_pendentes(self):
        faltando = []
        if not self.cfg.api_url:
            faltando.append("Informar a URL do serviço de assinatura do hospital.")
        elif not self.cfg.api_url.lower().startswith("https://"):
            # Resumo de documento clínico e token não saem em texto claro.
            faltando.append("A URL precisa ser HTTPS.")
        if not self.cfg.api_token:
            faltando.append("Informar o token de autenticação do serviço.")
        return faltando

    def disponivel(self):
        return not self.requisitos_pendentes()

    def assinar(self, conteudo_bytes, contexto=None):
        pendencias = self.requisitos_pendentes()
        if pendencias:
            raise AssinaturaIndisponivel(
                "Serviço de assinatura do hospital não configurado. Nenhum "
                "documento foi assinado.", pendencias=pendencias)

        import requests

        envio = {
            "hash": resumo_sha256(conteudo_bytes),
            "algoritmo": ALGORITMO_RESUMO,
            "tipo_documento": (contexto or {}).get("tipo_documento",
                                                   TIPO_PRESCRICAO_QUIMIO),
            "profissional": {
                "nome": self.cfg.profissional_nome,
                "cpf": self.cfg.profissional_cpf,
                "registro": self.cfg.profissional_registro,
            },
        }
        try:
            resp = requests.post(
                self.cfg.api_url, json=envio,
                headers={"Authorization": f"Bearer {self.cfg.api_token}",
                         "Content-Type": "application/json"},
                timeout=TIMEOUT_API_HOSPITAL)
        except Exception as exc:
            logger.warning("Assinatura: falha ao chamar API do hospital: %s", exc)
            raise AssinaturaIndisponivel(
                "Não foi possível falar com o serviço de assinatura do "
                f"hospital: {exc}", codigo="api_hospital_indisponivel")

        if resp.status_code >= 400:
            raise AssinaturaIndisponivel(
                f"O serviço de assinatura do hospital recusou a solicitação "
                f"(HTTP {resp.status_code}).",
                codigo="api_hospital_recusou")
        try:
            dados = resp.json()
        except ValueError:
            raise AssinaturaIndisponivel(
                "O serviço de assinatura do hospital não devolveu JSON válido.",
                codigo="api_hospital_resposta_invalida")

        assinatura = (dados or {}).get("assinatura_b64")
        if not assinatura:
            raise AssinaturaIndisponivel(
                "O serviço do hospital respondeu sem o campo 'assinatura_b64'. "
                "Nada foi marcado como assinado.",
                codigo="api_hospital_sem_assinatura")

        cert = (dados.get("certificado") or {})
        return {
            "assinatura_b64": assinatura,
            "provedor": self.nome,
            "assinado_em": timezone.now(),
            "certificado": {
                "titular": cert.get("titular") or self.cfg.profissional_nome,
                "cpf_cnpj": cert.get("cpf_cnpj") or self.cfg.profissional_cpf,
                "emissor": cert.get("emissor") or "",
                "numero_serie": cert.get("numero_serie") or "",
                "valido_de": _parse_dt(cert.get("valido_de")),
                "valido_ate": _parse_dt(cert.get("valido_ate")),
            },
            "carimbo_tempo_em": _parse_dt(dados.get("carimbo_tempo_em")),
        }


class ProvedorA1Local(ProvedorAssinatura):
    """Certificado A1 (.pfx/.p12) em arquivo — exceção para instalação dedicada.

    Produz assinatura CMS/PKCS#7 destacada, que é o formato base das assinaturas
    CAdES da ICP-Brasil. Não é o caminho recomendado em SaaS: guardar o arquivo
    e a senha do médico no servidor equivale a guardar a identidade jurídica
    dele. A senha fica cifrada em repouso.
    """

    nome = "a1_local"
    rotulo = "Arquivo A1 no servidor"

    def __init__(self, cfg=None, caminho=None, senha=None):
        self.cfg = cfg
        if cfg is not None:
            self.caminho = cfg.a1_caminho
            senha = cfg.a1_senha
        else:
            # Instalação dedicada (on-premise) pode configurar por ambiente.
            self.caminho = caminho or getattr(settings, "ICP_CERTIFICADO_A1_PATH", "")
            senha = senha if senha is not None else getattr(
                settings, "ICP_CERTIFICADO_A1_SENHA", "")
        self.senha = senha.encode("utf-8") if isinstance(senha, str) else senha

    def requisitos_pendentes(self):
        faltando = []
        if not self.caminho:
            faltando.append("Caminho do arquivo .pfx/.p12 não informado.")
        else:
            import os
            if not os.path.exists(self.caminho):
                faltando.append(
                    f"Arquivo do certificado não encontrado em {self.caminho}.")
        if not self.senha:
            faltando.append("Senha do certificado não informada.")
        return faltando

    def disponivel(self):
        return not self.requisitos_pendentes()

    def _carregar(self):
        from cryptography.hazmat.primitives.serialization import pkcs12
        with open(self.caminho, "rb") as fh:
            dados = fh.read()
        chave, cert, cadeia = pkcs12.load_key_and_certificates(dados, self.senha)
        if chave is None or cert is None:
            raise AssinaturaIndisponivel(
                "O arquivo informado não contém uma chave privada e um "
                "certificado válidos.", codigo="certificado_invalido")
        return chave, cert, (cadeia or [])

    def assinar(self, conteudo_bytes, contexto=None):
        pendencias = self.requisitos_pendentes()
        if pendencias:
            raise AssinaturaIndisponivel(
                "Certificado A1 não disponível. Nenhum documento foi assinado.",
                pendencias=pendencias)

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import Encoding
        from cryptography.hazmat.primitives.serialization import pkcs7

        chave, cert, _cadeia = self._carregar()

        agora = timezone.now()
        # A ICP-Brasil não reconhece assinatura feita com certificado fora da
        # validade.
        nao_antes, nao_depois = _validade_certificado(cert)
        if nao_antes and agora < nao_antes:
            raise AssinaturaIndisponivel(
                f"Certificado só é válido a partir de {nao_antes:%d/%m/%Y}.",
                codigo="certificado_fora_de_validade")
        if nao_depois and agora > nao_depois:
            raise AssinaturaIndisponivel(
                f"Certificado venceu em {nao_depois:%d/%m/%Y}.",
                codigo="certificado_vencido")

        # Envelope CAdES-BES ANEXADO (PKCS#7 DER), igual ao motor que já roda
        # em produção (api/assinatura_digital.py). Anexado é autocontido: o
        # validador do ITI consegue conferir sem receber o conteúdo à parte.
        assinatura = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(conteudo_bytes)
            .add_signer(cert, chave, hashes.SHA256())
            .sign(Encoding.DER, [pkcs7.PKCS7Options.Binary])
        )
        return {
            "assinatura_b64": base64.b64encode(assinatura).decode("ascii"),
            "provedor": self.nome,
            "assinado_em": agora,
            "certificado": dados_certificado(cert),
            "formato": "ICP-Brasil-CAdES-BES",
            # Certificado do próprio profissional: é o que o art. 4º da
            # Resolução CFM 2.299/2021 exige para ato médico.
            "conforme_cfm": True,
            # Carimbo de tempo exige Autoridade de Carimbo do Tempo externa:
            # sem ela a data é a do nosso relógio, não a de um terceiro.
            "carimbo_tempo_em": None,
        }


def _parse_dt(valor):
    """Converte ISO-8601 em datetime com fuso; None quando não dá."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _nome_x509(cert, oid):
    try:
        atributos = cert.subject.get_attributes_for_oid(oid)
        return atributos[0].value if atributos else ""
    except Exception:
        return ""


def _validade_certificado(cert):
    def _aware(valor):
        if valor is None:
            return None
        if timezone.is_naive(valor):
            return timezone.make_aware(valor, timezone.utc)
        return valor
    # A API nova (not_valid_before_utc) substitui a antiga; aceitamos as duas
    # para não quebrar conforme a versão da biblioteca no ambiente.
    inicio = getattr(cert, "not_valid_before_utc", None) or getattr(
        cert, "not_valid_before", None)
    fim = getattr(cert, "not_valid_after_utc", None) or getattr(
        cert, "not_valid_after", None)
    return _aware(inicio), _aware(fim)


def dados_certificado(cert):
    """Extrai do certificado o que precisa ficar registrado na assinatura."""
    from cryptography.x509.oid import NameOID
    nao_antes, nao_depois = _validade_certificado(cert)
    titular = _nome_x509(cert, NameOID.COMMON_NAME)
    # Em certificado ICP-Brasil de pessoa física o CPF vem anexado ao nome
    # comum ("FULANO DE TAL:12345678901").
    cpf = ""
    if ":" in titular:
        titular, _, sufixo = titular.partition(":")
        cpf = "".join(filter(str.isdigit, sufixo))[:11]
    try:
        atributos = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
        emissor = atributos[0].value if atributos else ""
    except Exception:
        emissor = ""
    return {
        "titular": titular.strip(),
        "cpf_cnpj": cpf,
        "emissor": emissor,
        "numero_serie": format(cert.serial_number, "x"),
        "valido_de": nao_antes,
        "valido_ate": nao_depois,
    }


def provedor_para(cfg):
    """Constrói o provedor a partir da configuração do profissional."""
    if cfg is None:
        return ProvedorNaoConfigurado()
    if cfg.status != "ativo":
        return ProvedorNaoConfigurado(
            motivo=f"A configuração de {cfg.profissional_nome} está "
                   f"'{cfg.get_status_display()}'.")
    if cfg.provedor in ("vidaas", "birdid"):
        return ProvedorNuvemICP(cfg)
    if cfg.provedor == "api_hospital":
        return ProvedorApiHospital(cfg)
    if cfg.provedor == "a1_local":
        return ProvedorA1Local(cfg=cfg)
    return ProvedorNaoConfigurado(
        motivo=f"Provedor '{cfg.provedor}' desconhecido.")


def localizar_certificado(empresa, nome=None, cpf=None, registro=None):
    """Acha a configuração do profissional que está assinando, dentro do tenant.

    Procura por CPF (identificador forte), depois por registro no conselho e só
    então por nome — nome é o critério mais frágil e fica por último.
    """
    from api.models import CertificadoAssinante

    base = CertificadoAssinante.objects.filter(empresa=empresa, status="ativo")
    cpf_limpo = "".join(filter(str.isdigit, cpf or ""))[:11]
    if cpf_limpo:
        achado = base.filter(profissional_cpf=cpf_limpo).first()
        if achado:
            return achado
    if registro:
        achado = base.filter(profissional_registro__iexact=registro.strip()).first()
        if achado:
            return achado
    if nome:
        achado = base.filter(profissional_nome__iexact=nome.strip()).first()
        if achado:
            return achado
    return None


def status_assinatura(empresa=None, nome=None, cpf=None, registro=None):
    """Diagnóstico para a tela: dá para assinar aqui, e se não, o que falta."""
    cfg = None
    if empresa is not None and (nome or cpf or registro):
        cfg = localizar_certificado(empresa, nome=nome, cpf=cpf, registro=registro)

    total_ativos = 0
    if empresa is not None:
        from api.models import CertificadoAssinante
        total_ativos = CertificadoAssinante.objects.filter(
            empresa=empresa, status="ativo").count()

    provedor = provedor_para(cfg)
    disponivel = provedor.disponivel()
    return {
        "disponivel": disponivel,
        "provedor": provedor.nome,
        "provedor_rotulo": provedor.rotulo,
        "algoritmo_resumo": ALGORITMO_RESUMO,
        "certificado_id": cfg.id if cfg else None,
        "profissional": cfg.profissional_nome if cfg else None,
        "assinantes_ativos": total_ativos,
        "pendencias": provedor.requisitos_pendentes(),
        "mensagem": (
            f"Assinatura ICP-Brasil ativa via {provedor.rotulo}."
            if disponivel else
            "Assinatura digital ICP-Brasil ainda não configurada para este "
            "profissional: as prescrições podem ser emitidas, mas sairão como "
            "NÃO ASSINADAS."
        ),
        # Deixa explícito de quem é o certificado — foi a confusão que motivou
        # este desenho: não é da empresa fornecedora, nem do hospital.
        "titularidade": (
            "O certificado é do médico (pessoa física, e-CPF vinculado ao CRM). "
            "Não é da empresa fornecedora do software nem do hospital."
        ),
    }


def conteudo_canonico_prescricao_internacao(internacao, itens, cfg=None,
                                            emitido_em=None):
    """Documento assinável da prescrição de um paciente internado.

    O art. 1º da Resolução CFM 2.299/2021 lista "Prescrição" entre os documentos
    médicos eletrônicos — não é privilégio da oncologia. Assina-se o CONJUNTO de
    itens, porque prescrição é um documento, não um medicamento solto: assinar
    item a item deixaria o conjunto sem garantia e permitiria acrescentar uma
    linha depois sem invalidar nada.
    """
    medico, estabelecimento = _dados_emitente(internacao.empresa, cfg)
    emitido_em = emitido_em or timezone.now()
    paciente = getattr(internacao, "paciente", None)
    linhas = [
        {
            "id": i.id,
            "medicamento": i.medicamento,
            "dose": i.dose or "",
            "via": i.via or "",
            "frequencia": i.frequencia or "",
            "duracao_dias": i.duracao_dias,
            "observacoes": i.observacoes or "",
        }
        for i in itens
    ]
    # Ordena pelo id para não depender da ordem que o banco devolveu.
    linhas.sort(key=lambda x: x["id"])
    payload = {
        "documento": TIPO_PRESCRICAO_INTERNACAO,
        "versao": 1,
        "empresa_id": internacao.empresa_id,
        "internacao_id": internacao.id,
        "emitido_em": timezone.localtime(emitido_em).isoformat(),
        "medico": medico,
        "estabelecimento": estabelecimento,
        "paciente": {
            "nome": getattr(paciente, "nome", "") or "",
            "cpf": getattr(paciente, "cpf", "") or "",
        },
        "diagnostico": internacao.diagnostico or "",
        "leito": str(internacao.leito) if internacao.leito_id else "",
        "medico_responsavel": internacao.medico_responsavel or "",
        "itens": linhas,
    }
    return _canonizar(payload)


def elementos_faltando_art2_internacao(internacao, cfg=None):
    """Campos obrigatórios do art. 2º ausentes na prescrição de internação."""
    medico, estab = _dados_emitente(internacao.empresa, cfg)
    paciente = getattr(internacao, "paciente", None)
    faltando = []
    if not medico["nome"]:
        faltando.append("nome do médico")
    if not medico["crm"]:
        faltando.append("CRM do médico")
    if not medico["endereco"] and not estab["endereco"]:
        faltando.append("endereço do médico ou do estabelecimento")
    if not getattr(paciente, "nome", ""):
        faltando.append("nome do paciente")
    if not getattr(paciente, "cpf", ""):
        faltando.append("número do documento legal do paciente")
    return faltando


class ProvedorCertificadoInstitucional(ProvedorAssinatura):
    """Certificado da INSTITUIÇÃO, guardado em CredenciaisIntegracoes.

    Existe porque o produto já assinava evoluções clínicas com o certificado do
    hospital antes deste módulo, e quebrar isso deixaria documento assinado sem
    caminho de verificação. Mantém o fluxo funcionando.

    MAS não satisfaz a Resolução CFM 2.299/2021 para ATO MÉDICO: o art. 4º
    exige a assinatura do médico, e um certificado institucional identifica a
    pessoa jurídica, não o profissional. Por isso devolve `conforme_cfm: False`
    — quem usar precisa saber o que tem na mão.
    """

    nome = "institucional"
    rotulo = "Certificado da instituição (não atende ao art. 4º para ato médico)"

    def __init__(self, empresa):
        self.empresa = empresa
        self._cred = None

    def _cred_obj(self):
        if self._cred is None:
            from api.models import CredenciaisIntegracoes
            self._cred = CredenciaisIntegracoes.objects.filter(
                empresa=self.empresa).first()
        return self._cred

    def requisitos_pendentes(self):
        cred = self._cred_obj()
        if not cred or not getattr(cred, "rnds_certificado_pfx_b64", ""):
            return ["Nenhum certificado institucional configurado."]
        return [
            "Este é o certificado da INSTITUIÇÃO. Para ato médico, a Resolução "
            "CFM 2.299/2021 (art. 4º) exige a assinatura do MÉDICO: cadastre o "
            "certificado de cada profissional.",
        ]

    def disponivel(self):
        cred = self._cred_obj()
        return bool(cred and getattr(cred, "rnds_certificado_pfx_b64", ""))

    def assinar(self, conteudo_bytes, contexto=None):
        if not self.disponivel():
            raise AssinaturaIndisponivel(
                "Nenhum certificado institucional configurado.",
                pendencias=self.requisitos_pendentes())
        from api.assinatura_digital import assinar_conteudo
        texto = conteudo_bytes.decode("utf-8") if isinstance(
            conteudo_bytes, bytes) else str(conteudo_bytes)
        ok, assinatura_b64, _hash, metodo, erro = assinar_conteudo(
            texto, self._cred_obj(), identificador=self.empresa.nome)
        if not ok:
            raise AssinaturaIndisponivel(
                f"Falha ao assinar com o certificado institucional: {erro}",
                codigo="falha_certificado_institucional")
        # O motor cai para SHA-256 quando não consegue usar o certificado. Isso
        # garante integridade, mas NÃO é assinatura com validade jurídica — e
        # marcar como assinada seria a mentira que este módulo inteiro evita.
        if metodo == "SHA256":
            raise AssinaturaIndisponivel(
                "O certificado institucional não pôde ser usado e o conteúdo "
                "receberia apenas resumo SHA-256, sem validade jurídica. "
                "Nenhum documento foi marcado como assinado.",
                codigo="apenas_hash_sem_validade",
                pendencias=self.requisitos_pendentes())
        return {
            "assinatura_b64": assinatura_b64,
            "provedor": self.nome,
            "formato": metodo,
            "conforme_cfm": False,
            "assinado_em": timezone.now(),
            "certificado": {"titular": self.empresa.nome, "cpf_cnpj": "",
                            "emissor": "", "numero_serie": "",
                            "valido_de": None, "valido_ate": None},
            "carimbo_tempo_em": None,
        }
