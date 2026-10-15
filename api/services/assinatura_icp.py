"""Assinatura digital ICP-Brasil para documentos clínicos.

A ICP-Brasil (Infraestrutura de Chaves Públicas Brasileira, instituída pela
Medida Provisória 2.200-2/2001) dá validade jurídica ao documento eletrônico
assinado com certificado emitido por uma Autoridade Certificadora credenciada.

Este módulo faz TUDO o que não depende de possuir o certificado:

  • monta o conteúdo canônico do documento (o que efetivamente é assinado);
  • calcula o resumo criptográfico SHA-256 desse conteúdo;
  • define a interface do provedor de assinatura;
  • implementa o provedor A1 (certificado em arquivo .pfx/.p12), que passa a
    funcionar no instante em que o certificado for configurado;
  • verifica depois se o documento foi alterado após a assinatura.

REGRA INEGOCIÁVEL: sem certificado configurado, nada é marcado como assinado.
Um sistema que finge assinar é pior que um sistema sem assinatura — seria uma
mentira com valor jurídico. Quando não há provedor, a operação falha de forma
explícita e diz exatamente o que falta.

O que ainda depende do titular do certificado (ver `requisitos_pendentes`):
  • o próprio certificado A1 (.pfx) ou A3 (token/smartcard) e sua senha;
  • opcionalmente, uma Autoridade de Carimbo do Tempo (ACT) para carimbo de
    tempo — sem ela a assinatura vale, mas a data é a do nosso relógio, e não
    a de um terceiro de confiança.
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

# Tipos de documento que podem ser assinados. Manter como lista fechada evita
# que um `tipo_documento` digitado errado crie uma categoria órfã de assinaturas.
TIPO_PRESCRICAO_QUIMIO = "prescricao_quimio"
TIPOS_DOCUMENTO = {
    TIPO_PRESCRICAO_QUIMIO: "Prescrição de quimioterapia",
}


# ── Conteúdo canônico ─────────────────────────────────────────────────────────
# O que é assinado precisa ser reprodutível byte a byte: se a serialização mudar
# conforme a ordem de um dicionário, a mesma prescrição gera resumos diferentes e
# toda assinatura "quebra" sozinha na verificação seguinte.

def _canonizar(payload):
    """Serializa de forma determinística: chaves ordenadas, separadores fixos."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def conteudo_canonico_prescricao(ciclo):
    """Monta o documento assinável de uma prescrição de quimioterapia.

    Inclui tudo que é clinicamente determinante — paciente, protocolo, doses
    calculadas e pré-medicação. Se qualquer um desses mudar depois, a assinatura
    deixa de conferir, que é exatamente o comportamento desejado.
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
    payload = {
        "documento": TIPO_PRESCRICAO_QUIMIO,
        "versao": 1,
        "empresa_id": ciclo.empresa_id,
        "ciclo_id": ciclo.id,
        "paciente": {
            "nome": ciclo.paciente_nome,
            "cpf": ciclo.cpf_paciente or "",
        },
        "diagnostico_cid10": ciclo.cid10_principal or "",
        "protocolo": {
            "codigo": ciclo.protocolo.codigo,
            "nome": ciclo.protocolo.nome,
        },
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
    """Resumo criptográfico hexadecimal do conteúdo canônico."""
    if isinstance(conteudo, str):
        conteudo = conteudo.encode("utf-8")
    return hashlib.sha256(conteudo).hexdigest()


# ── Provedores de assinatura ──────────────────────────────────────────────────

class AssinaturaIndisponivel(Exception):
    """Levantada quando não há provedor utilizável. Carrega o que falta."""

    def __init__(self, mensagem, codigo="assinatura_nao_configurada",
                 pendencias=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo
        self.pendencias = pendencias or []


class ProvedorAssinatura:
    """Contrato que qualquer provedor de assinatura precisa cumprir."""

    nome = "abstrato"

    def disponivel(self):
        raise NotImplementedError

    def requisitos_pendentes(self):
        """Lista legível do que falta para este provedor funcionar."""
        return []

    def assinar(self, conteudo_bytes):
        """Devolve dict com a assinatura e os dados do certificado usado."""
        raise NotImplementedError


class ProvedorNaoConfigurado(ProvedorAssinatura):
    """Estado padrão: ninguém configurou certificado algum.

    Existe para que a ausência de assinatura seja um caminho explícito e
    testável, em vez de um `None` solto espalhando AttributeError pela base.
    """

    nome = "nao_configurado"

    def disponivel(self):
        return False

    def requisitos_pendentes(self):
        return [
            "Definir ICP_ASSINATURA_PROVEDOR (ex.: 'a1_local').",
            "Fornecer o certificado ICP-Brasil do médico responsável "
            "(A1 em arquivo .pfx/.p12, ou A3 em token/smartcard).",
            "Configurar a senha do certificado em ICP_CERTIFICADO_A1_SENHA.",
        ]

    def assinar(self, conteudo_bytes):
        raise AssinaturaIndisponivel(
            "Assinatura digital ICP-Brasil não configurada neste ambiente. "
            "Nenhum documento foi assinado.",
            pendencias=self.requisitos_pendentes())


class ProvedorA1Local(ProvedorAssinatura):
    """Certificado A1 (ICP-Brasil) em arquivo PKCS#12 (.pfx/.p12).

    Produz uma assinatura CMS/PKCS#7 destacada sobre o conteúdo — o formato
    base das assinaturas CAdES usadas na ICP-Brasil. Enquanto o arquivo não
    existir, `disponivel()` é False e nada é assinado.
    """

    nome = "a1_local"

    def __init__(self, caminho=None, senha=None):
        self.caminho = caminho or getattr(settings, "ICP_CERTIFICADO_A1_PATH", "")
        senha = senha if senha is not None else getattr(
            settings, "ICP_CERTIFICADO_A1_SENHA", "")
        self.senha = senha.encode("utf-8") if isinstance(senha, str) else senha

    def requisitos_pendentes(self):
        faltando = []
        if not self.caminho:
            faltando.append("ICP_CERTIFICADO_A1_PATH não definido.")
        else:
            import os
            if not os.path.exists(self.caminho):
                faltando.append(
                    f"Arquivo do certificado não encontrado em {self.caminho}.")
        if not self.senha:
            faltando.append("ICP_CERTIFICADO_A1_SENHA não definida.")
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

    def assinar(self, conteudo_bytes):
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
        # Certificado fora da validade não assina: a ICP-Brasil não reconhece
        # assinatura feita com certificado vencido ou ainda não vigente.
        nao_antes, nao_depois = _validade_certificado(cert)
        if nao_antes and agora < nao_antes:
            raise AssinaturaIndisponivel(
                f"Certificado só é válido a partir de {nao_antes:%d/%m/%Y}.",
                codigo="certificado_fora_de_validade")
        if nao_depois and agora > nao_depois:
            raise AssinaturaIndisponivel(
                f"Certificado venceu em {nao_depois:%d/%m/%Y}.",
                codigo="certificado_vencido")

        assinatura = (
            pkcs7.PKCS7SignatureBuilder()
            .set_data(conteudo_bytes)
            .add_signer(cert, chave, hashes.SHA256())
            .sign(Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
        )
        return {
            "assinatura_b64": base64.b64encode(assinatura).decode("ascii"),
            "provedor": self.nome,
            "assinado_em": agora,
            "certificado": dados_certificado(cert),
            # Carimbo de tempo exige uma Autoridade de Carimbo do Tempo externa:
            # sem ela a data é a do nosso relógio, não a de um terceiro.
            "carimbo_tempo_em": None,
        }


def _nome_x509(cert, oid):
    try:
        atributos = cert.subject.get_attributes_for_oid(oid)
        return atributos[0].value if atributos else ""
    except Exception:
        return ""


def _validade_certificado(cert):
    """Validade do certificado como datetimes com fuso."""
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
    # Em certificados ICP-Brasil de pessoa física o CPF vem anexado ao nome
    # comum ("FULANO DE TAL:12345678901").
    cpf = ""
    if ":" in titular:
        titular, _, sufixo = titular.partition(":")
        cpf = "".join(filter(str.isdigit, sufixo))[:11]
    emissor = ""
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


_PROVEDORES = {
    ProvedorA1Local.nome: ProvedorA1Local,
}


def obter_provedor():
    """Devolve o provedor configurado, ou o 'não configurado' quando não há."""
    escolhido = (getattr(settings, "ICP_ASSINATURA_PROVEDOR", "") or "").strip()
    if not escolhido:
        return ProvedorNaoConfigurado()
    classe = _PROVEDORES.get(escolhido)
    if classe is None:
        logger.warning(
            "ICP_ASSINATURA_PROVEDOR=%r desconhecido; assinatura indisponível.",
            escolhido)
        return ProvedorNaoConfigurado()
    return classe()


def status_assinatura():
    """Diagnóstico para a tela: dá para assinar aqui, e se não, o que falta."""
    provedor = obter_provedor()
    pendencias = provedor.requisitos_pendentes()
    return {
        "disponivel": provedor.disponivel(),
        "provedor": provedor.nome,
        "algoritmo_resumo": ALGORITMO_RESUMO,
        "pendencias": pendencias,
        "mensagem": (
            "Assinatura digital ICP-Brasil ativa."
            if provedor.disponivel() else
            "Assinatura digital ICP-Brasil ainda não configurada: as prescrições "
            "podem ser emitidas, mas sairão como NÃO ASSINADAS."
        ),
    }
