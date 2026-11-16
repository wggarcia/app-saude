"""
rnds_fhir.py — cliente único da RNDS (Rede Nacional de Dados em Saúde — DATASUS/MS).

Todo módulo que fala com a RNDS (e-SUS, SIPNI, CEAF/HÓRUS, Hospital, teste de
credenciais) passa por aqui. Não crie outro cliente HTTP da RNDS em views.

Fluxo oficial (rnds-guia.saude.gov.br — /docs/rnds/ambientes/, /docs/rnds/servicos/,
/docs/publico-alvo/ti/conhecer/):
  1. GET no servidor Auth com o certificado ICP-Brasil (mTLS) → token, válido 30 min.
     O servidor Auth é o único que exige o certificado.
  2. Requisições ao servidor EHR com os cabeçalhos
       X-Authorization-Server: Bearer <token>
       Authorization: <CNS do profissional>
     Homologação tem um host único; produção tem um host por estado (UF do CNES).

Serviços documentados no guia: POST /Bundle (resultado de exame; sumário de alta
"similar") e GET /Patient. Outros perfis enviados pelos módulos (Encounter,
Immunization, MedicationDispense) só se confirmam na homologação.
"""
import base64
import hashlib
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

RNDS_AUTH_URLS = {
    "homologacao": "https://ehr-auth-hmg.saude.gov.br/api/token",
    "producao":    "https://ehr-auth.saude.gov.br/api/token",
}
RNDS_EHR_HOMOLOGACAO = "https://ehr-services.hmg.saude.gov.br"
RNDS_EHR_PRODUCAO = "https://{uf}-ehr-services.saude.gov.br"
FHIR_PATH = "/api/fhir/r4"

UFS_VALIDAS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}

NAMING_SYSTEM = {
    "cpf":  "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cpf",
    "cns":  "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cns",
    "cnes": "http://rnds.saude.gov.br/fhir/r4/NamingSystem/cnes",
}

TOKEN_VALIDADE_S = 30 * 60
TOKEN_RENOVAR_ANTES_S = 60
TIMEOUT_TOKEN_S = 20
TIMEOUT_EHR_S = 60

_TOKEN_CACHE: dict = {}
_TOKEN_LOCK = threading.Lock()


class RndsErro(Exception):
    """Erro com mensagem já em português, pronta para mostrar ao gestor."""

    def __init__(self, mensagem, status_http=None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status_http = status_http


@dataclass
class RndsResultado:
    ok: bool
    status_http: int | None = None
    protocolo: str = ""
    erro: str = ""
    dados: dict = field(default_factory=dict)


def ambiente_de(cred) -> str:
    return "producao" if getattr(cred, "rnds_ambiente", "") == "producao" else "homologacao"


def uf_de(cred) -> str:
    return ((getattr(cred, "rnds_uf", "") or getattr(cred, "sus_uf", "") or "").strip().upper())


def url_ehr(cred) -> str:
    """Base FHIR do servidor EHR para o ambiente/UF da credencial."""
    if ambiente_de(cred) == "homologacao":
        return RNDS_EHR_HOMOLOGACAO + FHIR_PATH
    uf = uf_de(cred)
    if uf not in UFS_VALIDAS:
        raise RndsErro(
            "Em produção a RNDS usa um servidor por estado. Informe a UF do "
            "estabelecimento (a mesma do CNES) em Integrações → RNDS."
        )
    return RNDS_EHR_PRODUCAO.format(uf=uf.lower()) + FHIR_PATH


def _cns_profissional(cred) -> str:
    cns = (getattr(cred, "rnds_cns_profissional", "") or "").strip()
    if not cns:
        raise RndsErro(
            "Informe o CNS do profissional responsável em Integrações → RNDS. "
            "A RNDS exige esse CNS em toda requisição."
        )
    return cns


@contextmanager
def _arquivos_certificado(cred):
    """Converte o PKCS#12 em PEMs temporários (0600) e apaga ao sair."""
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, pkcs12,
    )

    pfx_b64 = getattr(cred, "rnds_certificado_pfx_b64", "") or ""
    if not pfx_b64:
        raise RndsErro("Certificado ICP-Brasil não cadastrado. Configure em Integrações → RNDS.")
    senha = cred.get_rnds_certificado_senha() if hasattr(cred, "get_rnds_certificado_senha") else ""
    try:
        chave, cert, _ = pkcs12.load_key_and_certificates(
            base64.b64decode(pfx_b64), senha.encode() if senha else None,
        )
    except Exception:
        raise RndsErro("Não foi possível abrir o certificado ICP-Brasil: senha incorreta ou arquivo inválido.")
    if chave is None or cert is None:
        raise RndsErro("O arquivo do certificado não contém chave privada e certificado.")

    caminhos = []
    try:
        for conteudo in (
            cert.public_bytes(Encoding.PEM),
            chave.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()),
        ):
            fd, caminho = tempfile.mkstemp(suffix=".pem")
            caminhos.append(caminho)
            os.chmod(caminho, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(conteudo)
        yield caminhos[0], caminhos[1]
    finally:
        for caminho in caminhos:
            try:
                os.unlink(caminho)
            except OSError:
                pass


def _chave_cache(cred):
    pfx = getattr(cred, "rnds_certificado_pfx_b64", "") or ""
    impressao = hashlib.sha256(pfx.encode()).hexdigest()[:16]
    return (getattr(cred, "empresa_id", None), ambiente_de(cred), impressao)


def invalidar_token(cred):
    with _TOKEN_LOCK:
        _TOKEN_CACHE.pop(_chave_cache(cred), None)


def obter_token(cred, forcar=False) -> str:
    """Token de acesso da RNDS, reaproveitado até ~1 min antes de vencer."""
    chave = _chave_cache(cred)
    agora = time.monotonic()
    if not forcar:
        with _TOKEN_LOCK:
            item = _TOKEN_CACHE.get(chave)
        if item and item[1] > agora:
            return item[0]

    url = RNDS_AUTH_URLS[ambiente_de(cred)]
    with _arquivos_certificado(cred) as (cert_path, key_path):
        try:
            resp = requests.get(url, cert=(cert_path, key_path), timeout=TIMEOUT_TOKEN_S)
        except requests.RequestException:
            raise RndsErro("Não foi possível conectar ao servidor de autenticação da RNDS. "
                           "Verifique a internet do servidor e tente de novo.")

    if resp.status_code != 200:
        logger.warning("RNDS token recusado: HTTP %s (%s)", resp.status_code, ambiente_de(cred))
        if resp.status_code in (401, 403):
            msg = ("A RNDS recusou o certificado ao gerar o token. Confira se o certificado "
                   "é o credenciado na RNDS para este estabelecimento e se o ambiente está certo.")
        else:
            msg = f"A RNDS não gerou o token (HTTP {resp.status_code}): {resp.text[:300]}"
        raise RndsErro(msg, status_http=resp.status_code)

    try:
        token = resp.json().get("access_token", "")
    except ValueError:
        token = ""
    if not token:
        raise RndsErro("A RNDS respondeu sem token de acesso.", status_http=resp.status_code)

    with _TOKEN_LOCK:
        _TOKEN_CACHE[chave] = (token, agora + TOKEN_VALIDADE_S - TOKEN_RENOVAR_ANTES_S)
    return token


def montar_cabecalhos(cred, token) -> dict:
    return {
        "X-Authorization-Server": f"Bearer {token}",
        "Authorization": _cns_profissional(cred),
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }


def _protocolo(resp, dados) -> str:
    return (dados.get("id") if isinstance(dados, dict) else "") or \
        resp.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]


def requisitar(cred, metodo, recurso, json_body=None, params=None) -> RndsResultado:
    """Requisição autenticada ao EHR. Renova o token uma vez se vier 401."""
    try:
        base = url_ehr(cred)
        _cns_profissional(cred)
        for tentativa in (1, 2):
            token = obter_token(cred, forcar=(tentativa == 2))
            try:
                resp = requests.request(
                    metodo, f"{base}/{recurso.lstrip('/')}",
                    headers=montar_cabecalhos(cred, token),
                    json=json_body, params=params, timeout=TIMEOUT_EHR_S,
                )
            except requests.RequestException:
                return RndsResultado(False, erro="Não foi possível conectar ao servidor da RNDS. "
                                                 "Verifique a internet do servidor e tente de novo.")
            if resp.status_code == 401 and tentativa == 1:
                invalidar_token(cred)
                continue
            break
    except RndsErro as e:
        return RndsResultado(False, status_http=e.status_http, erro=e.mensagem)

    try:
        dados = resp.json() if resp.content else {}
    except ValueError:
        dados = {}
    if 200 <= resp.status_code < 300:
        return RndsResultado(True, resp.status_code, _protocolo(resp, dados), "", dados if isinstance(dados, dict) else {})
    logger.warning("RNDS %s %s: HTTP %s", metodo, recurso, resp.status_code)
    return RndsResultado(False, resp.status_code, "",
                         f"A RNDS retornou HTTP {resp.status_code}: {resp.text[:400]}",
                         dados if isinstance(dados, dict) else {})


def enviar_bundle(cred, bundle: dict) -> RndsResultado:
    return requisitar(cred, "POST", "Bundle", json_body=bundle)


def consultar_paciente(cred, valor: str, tipo: str = "cpf") -> RndsResultado:
    """GET /Patient por identificador. O formato exato da busca só se confirma na homologação."""
    sistema = NAMING_SYSTEM.get(tipo)
    if not sistema:
        return RndsResultado(False, erro="Tipo de identificador inválido (use cpf ou cns).")
    return requisitar(cred, "GET", "Patient", params={"identifier": f"{sistema}|{valor}"})


def testar_conexao(cred) -> RndsResultado:
    """Só gera um token novo — prova certificado, credenciamento e ambiente sem enviar dados."""
    try:
        _cns_profissional(cred)
        url_ehr(cred)
        obter_token(cred, forcar=True)
    except RndsErro as e:
        return RndsResultado(False, status_http=e.status_http, erro=e.mensagem)
    return RndsResultado(True, 200)


def transmitir_bundle(bundle: dict, cred) -> tuple[bool, str, str]:
    """Atalho (ok, protocolo, erro) para os módulos que gravam só isso."""
    r = enviar_bundle(cred, bundle)
    return r.ok, r.protocolo, r.erro


def get_cred(empresa):
    """Retorna CredenciaisIntegracoes da empresa (cria se não existir)."""
    try:
        from api.models import CredenciaisIntegracoes
        cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
        return cred
    except Exception:
        return None
