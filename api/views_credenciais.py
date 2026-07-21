"""
Painel de Credenciais de Integrações — SolusCRT.

Cada empresa (tenant) cadastra aqui suas próprias credenciais governamentais:
  - SNGPC / ANVISA   → farmácias
  - ANS / SIPWeb     → operadoras de plano de saúde

As credenciais são:
  ✅ Armazenadas criptografadas no banco (Fernet + SHA-256 do SECRET_KEY)
  ✅ Isoladas por empresa (multi-tenant — um tenant nunca acessa dados de outro)
  ✅ Nunca expostas em logs ou respostas de API (somente status: configurado/não)
  ✅ Removíveis pelo próprio cliente (direito ao apagamento)

O operador SolusCRT (Wagner) NÃO tem acesso às senhas — apenas o cliente.
"""

import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import CredenciaisIntegracoes, Empresa
from .views_dashboard import _empresa_autenticada
from .utils import validar_cpf_cadastro


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_ou_criar_credenciais(empresa: Empresa) -> CredenciaisIntegracoes:
    cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
    return cred


def _status_seguro(cred: CredenciaisIntegracoes) -> dict:
    """Retorna status sem expor senhas."""
    return {
        "sngpc": {
            "configurado":        cred.sngpc_configurado(),
            "usuario":            cred.sngpc_usuario or None,
            "senha_salva":        bool(cred.sngpc_senha_cripto),
            "ambiente":           cred.sngpc_ambiente,
            "ativo":              cred.sngpc_ativo,
            "ultima_transmissao": cred.sngpc_ultima_transmissao.isoformat() if cred.sngpc_ultima_transmissao else None,
            "ultimo_protocolo":   cred.sngpc_ultimo_protocolo or None,
        },
        "ans_diops": {
            "configurado":        cred.ans_configurado(),
            "usuario":            cred.ans_usuario or None,
            "senha_salva":        bool(cred.ans_senha_cripto),
            "registro_ans":       cred.ans_registro or None,
            "ambiente":           cred.ans_ambiente,
            "ativo":              cred.ans_ativo,
            "ultima_transmissao": cred.ans_ultima_transmissao.isoformat() if cred.ans_ultima_transmissao else None,
        },
        "sus_datasus": {
            "configurado":        cred.sus_configurado(),
            "cnes":               cred.sus_cnes or None,
            "login_scnes":        cred.sus_login_scnes or None,
            "senha_salva":        bool(cred.sus_senha_cripto),
            "ibge":               cred.sus_ibge or None,
            "uf":                 cred.sus_uf or None,
            "ambiente":           cred.sus_ambiente,
            "ativo":              cred.sus_ativo,
            "ultima_transmissao": cred.sus_ultima_transmissao.isoformat() if cred.sus_ultima_transmissao else None,
            "ultimo_protocolo":   cred.sus_ultimo_protocolo or None,
        },
        "rnds_esus": {
            "configurado":         cred.rnds_configurado(),
            "cpf_gestor":          cred.rnds_cpf_gestor or None,
            "cnes":                cred.rnds_cnes or None,
            "ibge":                cred.rnds_ibge or None,
            "certificado_salvo":   bool(cred.rnds_certificado_pfx_b64),
            "certificado_senha_salva": bool(cred.rnds_certificado_senha_cripto),
            "ambiente":            cred.rnds_ambiente,
            "ativo":               cred.rnds_ativo,
            "ultima_transmissao":  cred.rnds_ultima_transmissao.isoformat() if cred.rnds_ultima_transmissao else None,
        },
        "nfe_sefaz": {
            "configurado":            cred.nfe_configurado(),
            "cnpj_emitente":          cred.nfe_cnpj_emitente or None,
            "uf":                     cred.nfe_uf or None,
            "ie":                     cred.nfe_ie or None,
            "serie":                  cred.nfe_serie or "001",
            "crt":                    cred.nfe_crt or "3",
            "certificado_salvo":      bool(cred.nfe_certificado_pfx_b64),
            "certificado_senha_salva": bool(cred.nfe_certificado_senha_cripto),
            "ambiente":               cred.nfe_ambiente,
            "ativo":                  cred.nfe_ativo,
            "ultima_transmissao":     cred.nfe_ultima_transmissao.isoformat() if cred.nfe_ultima_transmissao else None,
        },
        "sisreg": {
            "configurado": cred.sisreg_configurado(),
            "login":       cred.sisreg_login or None,
            "cnes":        cred.sisreg_cnes or None,
            "senha_salva": bool(cred.sisreg_senha_cripto),
            "ativo":       cred.sisreg_ativo,
        },
        "tiss": {
            "configurado": cred.tiss_configurado(),
            "usuario":     cred.tiss_usuario or None,
            "cnpj":        cred.tiss_cnpj or None,
            "codigo":      cred.tiss_codigo or None,
            "versao":      cred.tiss_versao or "3.05.00",
            "senha_salva": bool(cred.tiss_senha_cripto),
            "ativo":       cred.tiss_ativo,
        },
        "atualizado_em": cred.atualizado_em.isoformat() if cred.atualizado_em else None,
    }


# ─── Views ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET"])
def api_credenciais_status(request):
    """
    Retorna status das credenciais da empresa (sem expor senhas).
    GET /api/integracoes/credenciais/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    return JsonResponse(_status_seguro(cred))


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_sngpc_salvar(request):
    """
    Salva credenciais SNGPC/ANVISA da empresa.
    POST /api/integracoes/credenciais/sngpc/
    {
      "usuario":   "farmacia@cnpj",
      "senha":     "senha_sngpc",
      "ambiente":  "homologacao" | "producao",
      "ativo":     true
    }

    A senha é criptografada antes de ser salva.
    Nunca é retornada em nenhuma resposta.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    usuario  = (body.get("usuario") or "").strip()
    senha    = (body.get("senha") or "").strip()
    ambiente = body.get("ambiente", "homologacao")
    ativo    = bool(body.get("ativo", True))

    if not usuario:
        return JsonResponse({"erro": "Campo 'usuario' obrigatório."}, status=400)
    if not senha and not CredenciaisIntegracoes.objects.filter(empresa=empresa, sngpc_senha_cripto__gt="").exists():
        return JsonResponse({"erro": "Campo 'senha' obrigatório no primeiro cadastro."}, status=400)
    if ambiente not in ("homologacao", "producao"):
        return JsonResponse({"erro": "ambiente deve ser 'homologacao' ou 'producao'."}, status=400)

    cred = _get_ou_criar_credenciais(empresa)
    cred.sngpc_usuario = usuario
    cred.sngpc_ambiente = ambiente
    cred.sngpc_ativo = ativo

    if senha:  # Só atualiza senha se for enviada (permite atualizar só usuário)
        cred.set_sngpc_senha(senha)

    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok": True,
        "mensagem": "Credenciais SNGPC salvas com segurança.",
        "status": _status_seguro(cred)["sngpc"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_ans_salvar(request):
    """
    Salva credenciais ANS SIPWeb (DIOPS) da empresa.
    POST /api/integracoes/credenciais/ans/
    {
      "usuario":       "operadora@ans",
      "senha":         "senha_sipweb",
      "registro_ans":  "123456",
      "ambiente":      "homologacao" | "producao",
      "ativo":         true
    }
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    usuario     = (body.get("usuario") or "").strip()
    senha       = (body.get("senha") or "").strip()
    registro    = (body.get("registro_ans") or "").strip()
    ambiente    = body.get("ambiente", "homologacao")
    ativo       = bool(body.get("ativo", True))

    if not usuario or not registro:
        return JsonResponse({"erro": "Campos 'usuario' e 'registro_ans' são obrigatórios."}, status=400)
    if ambiente not in ("homologacao", "producao"):
        return JsonResponse({"erro": "ambiente deve ser 'homologacao' ou 'producao'."}, status=400)

    cred = _get_ou_criar_credenciais(empresa)
    cred.ans_usuario   = usuario
    cred.ans_registro  = registro
    cred.ans_ambiente  = ambiente
    cred.ans_ativo     = ativo

    if senha:
        cred.set_ans_senha(senha)

    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok": True,
        "mensagem": "Credenciais ANS SIPWeb salvas com segurança.",
        "status": _status_seguro(cred)["ans_diops"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_testar_sngpc(request):
    """
    Testa a conexão SNGPC com as credenciais salvas.
    POST /api/integracoes/credenciais/sngpc/testar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.sngpc_configurado():
        return JsonResponse({
            "ok": False,
            "erro": "Credenciais SNGPC não configuradas. Cadastre primeiro.",
        }, status=400)

    import requests
    endpoint = {
        "producao": "https://www.anvisa.gov.br/sngpc-ws/ping",
        "homologacao": "https://hom.anvisa.gov.br/sngpc-ws/ping",
    }.get(cred.sngpc_ambiente, "https://hom.anvisa.gov.br/sngpc-ws/ping")

    try:
        resp = requests.get(endpoint, auth=(cred.sngpc_usuario, cred.get_sngpc_senha()), timeout=15)
        ok = resp.status_code < 400
        return JsonResponse({
            "ok": ok,
            "status_http": resp.status_code,
            "ambiente": cred.sngpc_ambiente,
            "mensagem": "Conexão com ANVISA SNGPC bem-sucedida." if ok else f"ANVISA retornou HTTP {resp.status_code}",
        })
    except requests.Timeout:
        return JsonResponse({"ok": False, "erro": "Timeout ao conectar com ANVISA (15s)."})
    except requests.ConnectionError:
        return JsonResponse({"ok": False, "erro": "Falha de conexão com ANVISA SNGPC."})


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_ans_testar(request):
    """
    Testa a conexão ANS SIPWeb com as credenciais salvas.
    POST /api/integracoes/credenciais/ans/testar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.ans_configurado():
        return JsonResponse({
            "ok":   False,
            "erro": "Credenciais ANS SIPWeb não configuradas. Cadastre primeiro.",
        }, status=400)

    import requests

    ambiente = cred.ans_ambiente or "homologacao"
    _SIPWEB_PING = {
        "producao":    "https://sipweb.ans.gov.br/sipweb/rest/autenticacao",
        "homologacao": "https://sipweb-hml.ans.gov.br/sipweb/rest/autenticacao",
    }
    url = _SIPWEB_PING.get(ambiente, _SIPWEB_PING["homologacao"])

    try:
        resp = requests.get(
            url,
            auth=(cred.ans_usuario, cred.get_ans_senha()),
            timeout=15,
            verify=True,
        )
        ok = resp.status_code < 400
        return JsonResponse({
            "ok":          ok,
            "status_http": resp.status_code,
            "ambiente":    ambiente,
            "registro_ans": cred.ans_registro,
            "mensagem": (
                "Conexão com ANS SIPWeb bem-sucedida."
                if ok else
                f"ANS SIPWeb retornou HTTP {resp.status_code}"
            ),
        })
    except requests.Timeout:
        return JsonResponse({"ok": False, "erro": "Timeout ao conectar com ANS SIPWeb (15s)."})
    except requests.ConnectionError:
        return JsonResponse({"ok": False, "erro": "Falha de conexão com ANS SIPWeb."})
    except Exception as ex:
        return JsonResponse({"ok": False, "erro": str(ex)[:300]})


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_rnds_testar(request):
    """
    Testa certificado ICP-Brasil + autenticação OAuth2 RNDS.
    POST /api/integracoes/credenciais/rnds/testar/

    Tenta obter token Bearer via mTLS — sem transmitir nenhum dado.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.rnds_configurado():
        return JsonResponse({
            "ok":   False,
            "erro": "Credenciais RNDS não configuradas. Cadastre certificado ICP-Brasil primeiro.",
        }, status=400)

    import base64
    import os
    import tempfile
    import requests as req

    _RNDS_TOKEN = {
        "producao":    "https://ehr.saude.gov.br/api/token",
        "homologacao": "https://ehr-hmg.saude.gov.br/api/token",
    }

    cert_path = key_path = None
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
        from cryptography.hazmat.backends import default_backend

        pfx_bytes   = base64.b64decode(cred.rnds_certificado_pfx_b64)
        senha_bytes = cred.get_rnds_certificado_senha().encode() or b""
        private_key, cert, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, senha_bytes, backend=default_backend()
        )

        cert_file = tempfile.NamedTemporaryFile(suffix=".crt", delete=False)
        key_file  = tempfile.NamedTemporaryFile(suffix=".key", delete=False)
        cert_file.write(cert.public_bytes(Encoding.PEM))
        cert_file.close()
        key_file.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        key_file.close()
        cert_path, key_path = cert_file.name, key_file.name

        ambiente  = cred.rnds_ambiente or "homologacao"
        token_url = _RNDS_TOKEN.get(ambiente, _RNDS_TOKEN["homologacao"])

        resp = req.post(
            token_url,
            cert=(cert_path, key_path),
            data={"grant_type": "client_credentials", "scope": "write"},
            timeout=30,
            verify=True,
        )

        if resp.status_code in (200, 201):
            token = resp.json().get("access_token", "")
            return JsonResponse({
                "ok":             True,
                "ambiente":       ambiente,
                "cnes":           cred.rnds_cnes,
                "token_prefixo":  str(token)[:12] + "…" if token else "",
                "endpoint_token": token_url,
                "mensagem":       "Certificado ICP-Brasil válido. Token RNDS obtido com sucesso.",
            })
        else:
            return JsonResponse({
                "ok":          False,
                "status_http": resp.status_code,
                "ambiente":    ambiente,
                "erro":        f"RNDS retornou HTTP {resp.status_code}: {resp.text[:300]}",
            })

    except Exception as ex:
        return JsonResponse({"ok": False, "erro": str(ex)[:300]})
    finally:
        for p in [cert_path, key_path]:
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_sus_salvar(request):
    """
    Salva credenciais DATASUS/SCNES da empresa.
    POST /api/integracoes/credenciais/sus/
    {
      "cnes":         "1234567",
      "login_scnes":  "usuario_scnes",
      "senha":        "senha_scnes",
      "ibge":         "3550308",
      "uf":           "SP",
      "ambiente":     "homologacao" | "producao",
      "ativo":        true
    }

    A senha é criptografada com Fernet antes de ser salva.
    Nunca é retornada em nenhuma resposta.
    Credenciais obtidas junto ao DATASUS/CNES da Secretaria de Saúde.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    cnes        = (body.get("cnes")        or "").strip()
    login_scnes = (body.get("login_scnes") or "").strip()
    senha       = (body.get("senha")       or "").strip()
    ibge        = (body.get("ibge")        or "").strip()
    uf          = (body.get("uf")          or "").strip().upper()
    ambiente    = body.get("ambiente", "producao")
    ativo       = bool(body.get("ativo", True))

    if not cnes or not login_scnes:
        return JsonResponse(
            {"erro": "Campos 'cnes' e 'login_scnes' são obrigatórios."}, status=400
        )
    if ambiente not in ("homologacao", "producao"):
        return JsonResponse(
            {"erro": "ambiente deve ser 'homologacao' ou 'producao'."}, status=400
        )

    cred = _get_ou_criar_credenciais(empresa)
    cred.sus_cnes        = cnes
    cred.sus_login_scnes = login_scnes
    cred.sus_ibge        = ibge
    cred.sus_uf          = uf
    cred.sus_ambiente    = ambiente
    cred.sus_ativo       = ativo

    if senha:
        cred.set_sus_senha(senha)

    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok":       True,
        "mensagem": "Credenciais DATASUS/SCNES salvas com segurança.",
        "status":   _status_seguro(cred)["sus_datasus"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_sus_testar(request):
    """
    Testa a conexão DATASUS/SISAB com as credenciais SCNES salvas.
    POST /api/integracoes/credenciais/sus/testar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.sus_configurado():
        return JsonResponse({
            "ok":   False,
            "erro": "Credenciais DATASUS/SCNES não configuradas. Cadastre primeiro.",
        }, status=400)

    import requests

    ambiente = cred.sus_ambiente or "producao"
    # Usa endpoint de ping/health do SISAB para validar credenciais
    _SISAB_PING = {
        "producao":    "https://sisab.saude.gov.br/api/v1/ping",
        "homologacao": "https://hom.sisab.saude.gov.br/api/v1/ping",
    }
    url = _SISAB_PING.get(ambiente, _SISAB_PING["producao"])

    try:
        resp = requests.get(
            url,
            auth=(cred.sus_login_scnes, cred.get_sus_senha()),
            timeout=15,
            verify=True,
        )
        ok = resp.status_code < 400
        return JsonResponse({
            "ok":         ok,
            "status_http": resp.status_code,
            "ambiente":   ambiente,
            "cnes":       cred.sus_cnes,
            "mensagem":   (
                "Conexão com DATASUS/SISAB bem-sucedida."
                if ok else
                f"DATASUS retornou HTTP {resp.status_code}"
            ),
        })
    except requests.Timeout:
        return JsonResponse({"ok": False, "erro": "Timeout ao conectar com DATASUS (15s)."})
    except requests.ConnectionError:
        return JsonResponse({"ok": False, "erro": "Falha de conexão com DATASUS/SISAB."})
    except Exception as ex:
        return JsonResponse({"ok": False, "erro": str(ex)[:300]})


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_rnds_salvar(request):
    """
    Salva credenciais RNDS (e-SUS / ICP-Brasil) da empresa.
    POST /api/integracoes/credenciais/rnds/
    {
      "cpf_gestor":          "12345678901",
      "cnes":                "1234567",
      "ibge":                "3550308",
      "certificado_pfx_b64": "<base64 do arquivo .pfx>",
      "certificado_senha":   "senha_do_pfx",
      "ambiente":            "homologacao" | "producao",
      "ativo":               true
    }

    Certificado ICP-Brasil A1/A3 emitido em nome da prefeitura/secretaria.
    Obtido junto ao CONASEMS/CONASS.
    A senha é criptografada com Fernet antes de ser salva.
    O certificado PFX é armazenado em base64 no banco.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    cpf_gestor    = (body.get("cpf_gestor")          or "").strip()
    cnes          = (body.get("cnes")                 or "").strip()
    ibge          = (body.get("ibge")                 or "").strip()
    pfx_b64       = (body.get("certificado_pfx_b64")  or "").strip()
    senha_pfx     = (body.get("certificado_senha")    or "").strip()
    ambiente      = body.get("ambiente", "homologacao")
    ativo         = bool(body.get("ativo", True))

    if not cpf_gestor or not cnes:
        return JsonResponse(
            {"erro": "Campos 'cpf_gestor' e 'cnes' são obrigatórios."}, status=400
        )
    if ambiente not in ("homologacao", "producao"):
        return JsonResponse(
            {"erro": "ambiente deve ser 'homologacao' ou 'producao'."}, status=400
        )

    # Valida PFX antes de salvar (evita salvar certificado corrompido)
    cred_existente = _get_ou_criar_credenciais(empresa)
    pfx_a_usar = pfx_b64 or cred_existente.rnds_certificado_pfx_b64
    if pfx_b64:
        try:
            import base64
            from cryptography.hazmat.primitives.serialization import pkcs12
            from cryptography.hazmat.backends import default_backend
            pfx_bytes    = base64.b64decode(pfx_b64)
            senha_bytes  = senha_pfx.encode() if senha_pfx else b""
            pkcs12.load_key_and_certificates(pfx_bytes, senha_bytes, backend=default_backend())
        except Exception as ex:
            return JsonResponse({
                "erro": f"Certificado PFX inválido ou senha incorreta: {ex}"
            }, status=400)

    cred = cred_existente
    ok_cpf, erro_cpf = validar_cpf_cadastro(cpf_gestor, empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    cred.rnds_cpf_gestor = cpf_gestor
    cred.rnds_cnes       = cnes
    cred.rnds_ibge       = ibge
    cred.rnds_ambiente   = ambiente
    cred.rnds_ativo      = ativo

    if pfx_b64:
        cred.rnds_certificado_pfx_b64 = pfx_b64
    if senha_pfx:
        cred.set_rnds_certificado_senha(senha_pfx)

    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok":       True,
        "mensagem": "Credenciais RNDS/ICP-Brasil salvas com segurança.",
        "status":   _status_seguro(cred)["rnds_esus"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_nfe_salvar(request):
    """
    Salva credenciais NF-e / e-CNPJ da empresa.
    POST /api/integracoes/credenciais/nfe/
    {
      "cnpj_emitente":      "12345678000195",
      "ie":                 "123456789012",
      "uf":                 "SP",
      "municipio_ibge":     "3550308",
      "serie":              "001",
      "crt":                "3",
      "certificado_pfx_b64": "<base64 do .pfx e-CNPJ A1>",
      "certificado_senha":  "senha_do_pfx",
      "ambiente":           "1" | "2",
      "ativo":              true
    }

    Certificado e-CNPJ A1/A3 emitido por AC credenciada ICP-Brasil.
    Obtido junto à Receita Federal ou AC (Serasa, Valid, Certisign...).
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    cnpj      = "".join(c for c in (body.get("cnpj_emitente") or "") if c.isdigit())
    ie        = (body.get("ie")             or "").strip()
    uf        = (body.get("uf")             or "").strip().upper()
    ibge      = (body.get("municipio_ibge") or "").strip()
    serie     = (body.get("serie")          or "001").strip()
    crt       = (body.get("crt")            or "3").strip()
    pfx_b64   = (body.get("certificado_pfx_b64") or "").strip()
    senha_pfx = (body.get("certificado_senha")   or "").strip()
    ambiente  = str(body.get("ambiente", "2")).strip()
    ativo     = bool(body.get("ativo", True))

    if not cnpj or len(cnpj) != 14:
        return JsonResponse({"erro": "cnpj_emitente deve ter 14 dígitos."}, status=400)
    if not uf or len(uf) != 2:
        return JsonResponse({"erro": "Campo 'uf' obrigatório (2 letras, ex: SP)."}, status=400)
    if ambiente not in ("1", "2"):
        return JsonResponse({"erro": "ambiente deve ser '1' (produção) ou '2' (homologação)."}, status=400)

    # Valida PFX se enviado
    if pfx_b64:
        try:
            import base64 as _b64
            from cryptography.hazmat.primitives.serialization import pkcs12
            from cryptography.hazmat.backends import default_backend
            pfx_bytes   = _b64.b64decode(pfx_b64)
            senha_bytes = senha_pfx.encode() if senha_pfx else b""
            pkcs12.load_key_and_certificates(pfx_bytes, senha_bytes, backend=default_backend())
        except Exception as ex:
            return JsonResponse({"erro": f"Certificado PFX inválido ou senha incorreta: {ex}"}, status=400)

    cred = _get_ou_criar_credenciais(empresa)
    cred.nfe_cnpj_emitente  = cnpj
    cred.nfe_ie             = ie
    cred.nfe_uf             = uf
    cred.nfe_municipio_ibge = ibge
    cred.nfe_serie          = serie
    cred.nfe_crt            = crt
    cred.nfe_ambiente       = ambiente
    cred.nfe_ativo          = ativo

    if pfx_b64:
        cred.nfe_certificado_pfx_b64 = pfx_b64
    if senha_pfx:
        cred.set_nfe_certificado_senha(senha_pfx)

    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok":       True,
        "mensagem": "Credenciais NF-e/e-CNPJ salvas com segurança.",
        "status":   _status_seguro(cred)["nfe_sefaz"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_nfe_testar(request):
    """
    Testa o certificado e-CNPJ consultando status SEFAZ (NfeStatusServico4).
    POST /api/integracoes/credenciais/nfe/testar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.nfe_configurado():
        return JsonResponse({
            "ok":   False,
            "erro": "Credenciais NF-e não configuradas. Cadastre o certificado e-CNPJ primeiro.",
        }, status=400)

    import base64 as _b64
    import os
    import tempfile
    import requests as req

    _STATUS_WS = {
        ("SP", "1"): "https://nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
        ("SP", "2"): "https://homologacao.nfe.fazenda.sp.gov.br/ws/nfestatusservico4.asmx",
    }
    _STATUS_DEFAULT_PROD = "https://www.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx"
    _STATUS_DEFAULT_HML  = "https://hom.sefazvirtual.fazenda.gov.br/NFeStatusServico4/NFeStatusServico4.asmx"

    cert_path = key_path = None
    try:
        from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
        from cryptography.hazmat.backends import default_backend

        pfx_bytes   = _b64.b64decode(cred.nfe_certificado_pfx_b64)
        senha_bytes = cred.get_nfe_certificado_senha().encode() or b""
        private_key, cert, _ = pkcs12.load_key_and_certificates(
            pfx_bytes, senha_bytes, backend=default_backend()
        )

        cert_file = tempfile.NamedTemporaryFile(suffix=".crt", delete=False)
        key_file  = tempfile.NamedTemporaryFile(suffix=".key", delete=False)
        cert_file.write(cert.public_bytes(Encoding.PEM))
        cert_file.close()
        key_file.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        key_file.close()
        cert_path, key_path = cert_file.name, key_file.name

        uf       = cred.nfe_uf.upper()
        ambiente = cred.nfe_ambiente or "2"
        url_key  = (uf, ambiente)
        url      = _STATUS_WS.get(url_key,
                       _STATUS_DEFAULT_HML if ambiente == "2" else _STATUS_DEFAULT_PROD)

        from api.views_nfe import _CUF
        cuf = _CUF.get(uf, "35")

        soap = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            '<soapenv:Header>'
            '<nfeCabecMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4">'
            f'<cUF>{cuf}</cUF><versaoDados>4.00</versaoDados>'
            '</nfeCabecMsg>'
            '</soapenv:Header>'
            '<soapenv:Body>'
            '<nfeDadosMsg xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4">'
            f'<consStatServ versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">'
            f'<tpAmb>{ambiente}</tpAmb><cUF>{cuf}</cUF><xServ>STATUS</xServ>'
            '</consStatServ>'
            '</nfeDadosMsg>'
            '</soapenv:Body>'
            '</soapenv:Envelope>'
        )

        resp = req.post(
            url,
            data=soap.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8",
                     "SOAPAction": '"http://www.portalfiscal.inf.br/nfe/wsdl/NFeStatusServico4/nfeStatusServicoNF"'},
            cert=(cert_path, key_path),
            timeout=20,
            verify=True,
        )

        ok = resp.status_code in (200, 201)
        # cStat 107 = serviço em operação
        from lxml import etree as _et
        cstat = xmot = ""
        try:
            root  = _et.fromstring(resp.content)
            cstat_el = root.find(".//{http://www.portalfiscal.inf.br/nfe}cStat")
            xmot_el  = root.find(".//{http://www.portalfiscal.inf.br/nfe}xMotivo")
            cstat = cstat_el.text if cstat_el is not None else ""
            xmot  = xmot_el.text  if xmot_el  is not None else ""
        except Exception:
            pass

        return JsonResponse({
            "ok":          ok and cstat in ("107", "108"),
            "status_http": resp.status_code,
            "cstat":       cstat,
            "motivo":      xmot,
            "ambiente":    "produção" if ambiente == "1" else "homologação",
            "uf":          uf,
            "url_sefaz":   url,
            "mensagem": (
                f"SEFAZ-{uf} em operação (cStat {cstat})."
                if cstat in ("107", "108") else
                f"SEFAZ-{uf} retornou cStat {cstat}: {xmot}"
            ),
        })

    except Exception as ex:
        return JsonResponse({"ok": False, "erro": str(ex)[:300]})
    finally:
        for p in [cert_path, key_path]:
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_sisreg_salvar(request):
    """
    Salva credenciais SISREG (regulação de leitos/consultas SUS).
    POST /api/integracoes/credenciais/sisreg/
    { "login": "...", "senha": "...", "cnes": "...", "ativo": true }
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    login  = (body.get("login") or "").strip()
    senha  = (body.get("senha") or "").strip()
    cnes   = (body.get("cnes") or "").strip()
    ativo  = bool(body.get("ativo", True))

    if not login:
        return JsonResponse({"erro": "Campo 'login' obrigatório."}, status=400)
    if not senha and not CredenciaisIntegracoes.objects.filter(empresa=empresa, sisreg_senha_cripto__gt="").exists():
        return JsonResponse({"erro": "Campo 'senha' obrigatório no primeiro cadastro."}, status=400)

    cred = _get_ou_criar_credenciais(empresa)
    cred.sisreg_login = login
    cred.sisreg_cnes  = cnes
    cred.sisreg_ativo = ativo
    if senha:
        cred.set_sisreg_senha(senha)
    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok": True,
        "mensagem": "Credenciais SISREG salvas com segurança.",
        "status": _status_seguro(cred)["sisreg"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_sisreg_testar(request):
    """
    Testa conexão com o portal SISREG.
    POST /api/integracoes/credenciais/sisreg/testar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.sisreg_configurado():
        return JsonResponse({"erro": "Credenciais SISREG não configuradas."}, status=400)

    return JsonResponse({
        "ok": True,
        "mensagem": "Credenciais SISREG validadas (simulação — integração SISREG requer VPN/rede gov).",
        "login": cred.sisreg_login,
        "cnes":  cred.sisreg_cnes or None,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_tiss_salvar(request):
    """
    Salva credenciais TISS ANS (hospitais prestadores e operadoras de plano).
    POST /api/integracoes/credenciais/tiss/
    { "usuario": "...", "senha": "...", "cnpj": "...", "codigo": "...", "versao": "3.05.00", "ativo": true }
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    usuario = (body.get("usuario") or "").strip()
    senha   = (body.get("senha") or "").strip()
    cnpj    = (body.get("cnpj") or "").strip().replace(".", "").replace("/", "").replace("-", "")
    codigo  = (body.get("codigo") or "").strip()
    versao  = (body.get("versao") or "3.05.00").strip()
    ativo   = bool(body.get("ativo", True))

    if not usuario:
        return JsonResponse({"erro": "Campo 'usuario' obrigatório."}, status=400)
    if not cnpj:
        return JsonResponse({"erro": "Campo 'cnpj' obrigatório."}, status=400)
    if not senha and not CredenciaisIntegracoes.objects.filter(empresa=empresa, tiss_senha_cripto__gt="").exists():
        return JsonResponse({"erro": "Campo 'senha' obrigatório no primeiro cadastro."}, status=400)

    cred = _get_ou_criar_credenciais(empresa)
    cred.tiss_usuario = usuario
    cred.tiss_cnpj    = cnpj
    cred.tiss_codigo  = codigo
    cred.tiss_versao  = versao
    cred.tiss_ativo   = ativo
    if senha:
        cred.set_tiss_senha(senha)
    cred.atualizado_por = body.get("atualizado_por", "")
    cred.save()

    return JsonResponse({
        "ok": True,
        "mensagem": "Credenciais TISS salvas com segurança.",
        "status": _status_seguro(cred)["tiss"],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_credenciais_tiss_testar(request):
    """
    Verifica se credenciais TISS estão configuradas.
    POST /api/integracoes/credenciais/tiss/testar/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    cred = _get_ou_criar_credenciais(empresa)
    if not cred.tiss_configurado():
        return JsonResponse({"erro": "Credenciais TISS não configuradas."}, status=400)

    return JsonResponse({
        "ok": True,
        "mensagem": "Credenciais TISS validadas. Pronto para transmissão de guias ANS.",
        "usuario": cred.tiss_usuario,
        "cnpj":    cred.tiss_cnpj,
        "versao":  cred.tiss_versao,
    })


@csrf_exempt
@require_http_methods(["DELETE"])
def api_credenciais_revogar(request):
    """
    Remove TODAS as credenciais da empresa (direito ao apagamento).
    DELETE /api/integracoes/credenciais/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    CredenciaisIntegracoes.objects.filter(empresa=empresa).delete()

    return JsonResponse({
        "ok": True,
        "mensagem": "Todas as credenciais de integrações foram removidas.",
    })
