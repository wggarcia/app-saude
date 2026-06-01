"""
CNES — Cadastro Nacional de Estabelecimentos de Saúde
Sincronização com a API pública do DATASUS.

GET  /api/governo/cnes/buscar?q=<nome_ou_cnes>&uf=SP&municipio=SAO+PAULO
GET  /api/governo/cnes/<codigo>            Consulta estabelecimento por código CNES
POST /api/governo/cnes/sincronizar         Sincroniza unidade local com dados DATASUS
GET  /api/governo/cnes/status              Status de sincronização das unidades locais
GET  /api/governo/cnes/kpis               KPIs de completude do cadastro

API DATASUS pública:
  https://apidadosabertos.saude.gov.br/cnes/estabelecimentos/{cnes}
  Documentação: https://datasus.saude.gov.br/api-cnes
"""
import json
import logging
import math

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)

_CNES_API_BASE   = "https://apidadosabertos.saude.gov.br/cnes"
_CNES_TIMEOUT    = 10  # segundos


def _gov(request):
    emp = empresa_autenticada_from_request(request)
    if emp and emp.tipo_conta == "governo":
        return emp
    return None


# ── Busca no DATASUS ──────────────────────────────────────────────────────────

def api_cnes_buscar(request):
    """
    GET /api/governo/cnes/buscar?q=<nome_ou_cnes>&uf=SP&municipio=Campinas&page=1

    Busca estabelecimentos de saúde na API pública do DATASUS.
    Retorna dados do DATASUS em tempo real (não armazenados localmente).
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    q         = (request.GET.get("q") or "").strip()
    uf        = (request.GET.get("uf") or "").strip().upper()
    municipio = (request.GET.get("municipio") or "").strip()
    page      = max(1, int(request.GET.get("page") or 1))

    if not q and not uf:
        return JsonResponse({"erro": "Informe ao menos 'q' (nome/CNES) ou 'uf'"}, status=400)

    # Se é um código CNES (7 dígitos), busca direto
    if q.isdigit() and len(q) == 7:
        dado = _buscar_cnes_api(q)
        if dado:
            return JsonResponse({"total": 1, "resultados": [_normalizar_datasus(dado)]})
        return JsonResponse({"total": 0, "resultados": [], "aviso": f"CNES {q} não encontrado no DATASUS"})

    # Busca por nome
    params = {"limit": 20, "offset": (page - 1) * 20}
    if q:
        params["no_fantasia"] = q
    if uf:
        params["co_uf"] = _uf_para_codigo(uf)
    if municipio:
        params["no_municipio"] = municipio

    resultado = _buscar_lista_cnes_api(params)

    return JsonResponse({
        "total":      resultado.get("total", 0),
        "pagina":     page,
        "resultados": [_normalizar_datasus(e) for e in resultado.get("estabelecimentos", [])],
        "fonte":      "DATASUS — CNES",
    })


def api_cnes_detalhe(request, codigo_cnes):
    """GET /api/governo/cnes/<codigo> — detalhe completo do DATASUS."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    codigo = str(codigo_cnes).strip().zfill(7)
    dado   = _buscar_cnes_api(codigo)

    if not dado:
        return JsonResponse({"erro": f"CNES {codigo} não encontrado no DATASUS"}, status=404)

    # Verifica se já existe localmente
    from .models import UnidadeSaude
    local = UnidadeSaude.objects.filter(empresa=empresa, cnes=codigo).first()

    return JsonResponse({
        **_normalizar_datasus(dado),
        "sincronizado_localmente": local is not None,
        "unidade_local_id":        local.id if local else None,
        "ultima_atualizacao_local": local.atualizado_em.isoformat() if local else None,
    })


# ── Sincronizar ───────────────────────────────────────────────────────────────

@csrf_exempt
def api_cnes_sincronizar(request):
    """
    POST /api/governo/cnes/sincronizar
    Body: {"cnes": "1234567"} — sincroniza ou atualiza uma UnidadeSaude local
    com os dados atuais do DATASUS.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cnes = str(body.get("cnes") or "").strip().zfill(7)
    if not cnes or len(cnes) != 7:
        return JsonResponse({"erro": "Código CNES inválido (7 dígitos)"}, status=400)

    dado = _buscar_cnes_api(cnes)
    if not dado:
        return JsonResponse({"erro": f"CNES {cnes} não encontrado no DATASUS"}, status=404)

    norm = _normalizar_datasus(dado)

    from .models import UnidadeSaude

    unidade, criado = UnidadeSaude.objects.get_or_create(
        empresa=empresa,
        cnes=cnes,
        defaults=_datasus_para_model(norm, empresa),
    )

    if not criado:
        # Atualiza campos do DATASUS
        campos = _datasus_para_model(norm, empresa)
        for campo, valor in campos.items():
            if campo not in ("empresa",):
                setattr(unidade, campo, valor)
        unidade.save()

    return JsonResponse({
        "ok":       True,
        "acao":     "criada" if criado else "atualizada",
        "unidade_id": unidade.id,
        "cnes":     cnes,
        "nome":     unidade.nome,
        "tipo":     unidade.tipo,
        "municipio": unidade.municipio,
        "uf":       unidade.uf,
        "dados_datasus": norm,
    }, status=201 if criado else 200)


@csrf_exempt
def api_cnes_sincronizar_todas(request):
    """
    POST /api/governo/cnes/sincronizar-todas
    Sincroniza todas as UnidadeSaude que têm CNES preenchido mas
    não foram atualizadas nos últimos 30 dias.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import UnidadeSaude
    from datetime import timedelta

    trinta_dias_atras = timezone.now() - timedelta(days=30)

    unidades = UnidadeSaude.objects.filter(
        empresa=empresa,
        ativo=True,
    ).exclude(cnes="").filter(
        atualizado_em__lt=trinta_dias_atras,
    )[:50]  # máximo 50 por requisição

    atualizadas  = 0
    erros        = 0
    resultados   = []

    for u in unidades:
        dado = _buscar_cnes_api(u.cnes)
        if not dado:
            erros += 1
            resultados.append({"cnes": u.cnes, "nome": u.nome, "ok": False, "motivo": "Não encontrado no DATASUS"})
            continue

        norm   = _normalizar_datasus(dado)
        campos = _datasus_para_model(norm, empresa)
        for campo, valor in campos.items():
            if campo != "empresa":
                setattr(u, campo, valor)
        try:
            u.save()
            atualizadas += 1
            resultados.append({"cnes": u.cnes, "nome": u.nome, "ok": True})
        except Exception as e:
            erros += 1
            resultados.append({"cnes": u.cnes, "nome": u.nome, "ok": False, "motivo": str(e)[:100]})

    return JsonResponse({
        "total_processadas": atualizadas + erros,
        "atualizadas":       atualizadas,
        "erros":             erros,
        "resultados":        resultados,
    })


# ── Status e KPIs ─────────────────────────────────────────────────────────────

def api_cnes_status(request):
    """GET /api/governo/cnes/status — status de sincronização das unidades locais."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import UnidadeSaude
    from datetime import timedelta

    todas        = UnidadeSaude.objects.filter(empresa=empresa, ativo=True)
    com_cnes     = todas.exclude(cnes="")
    sem_cnes     = todas.filter(cnes="")
    trinta_dias  = timezone.now() - timedelta(days=30)
    desatualizadas = com_cnes.filter(atualizado_em__lt=trinta_dias)

    return JsonResponse({
        "total_unidades":      todas.count(),
        "com_cnes":            com_cnes.count(),
        "sem_cnes":            sem_cnes.count(),
        "desatualizadas_30d":  desatualizadas.count(),
        "por_tipo": list(
            todas.values("tipo").annotate(
                total=__import__("django.db.models", fromlist=["Count"]).Count("id")
            ).order_by("-total")[:10]
        ),
        "aviso": (
            f"{sem_cnes.count()} unidade(s) sem CNES preenchido. "
            "Informe o CNES para habilitar a sincronização com o DATASUS."
        ) if sem_cnes.count() > 0 else None,
    })


def api_cnes_kpis(request):
    """GET /api/governo/cnes/kpis — completude do cadastro."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import UnidadeSaude
    from django.db.models import Count

    qs = UnidadeSaude.objects.filter(empresa=empresa, ativo=True)

    com_cnes      = qs.exclude(cnes="").count()
    com_geo       = qs.exclude(latitude=None).count()
    com_telefone  = qs.exclude(telefone="").count()
    com_diretor   = qs.exclude(diretor="").count()
    total         = qs.count()

    def pct(n):
        return round(n / total * 100, 1) if total else 0

    return JsonResponse({
        "total":            total,
        "completude": {
            "cnes_preenchido":   {"count": com_cnes,     "pct": pct(com_cnes)},
            "geolocalizado":     {"count": com_geo,       "pct": pct(com_geo)},
            "telefone":          {"count": com_telefone,  "pct": pct(com_telefone)},
            "diretor":           {"count": com_diretor,   "pct": pct(com_diretor)},
        },
        "score_completude_medio": round(
            (pct(com_cnes) + pct(com_geo) + pct(com_telefone) + pct(com_diretor)) / 4, 1
        ),
        "por_tipo": list(qs.values("tipo").annotate(total=Count("id")).order_by("-total")),
    })


# ── Helpers — API DATASUS ─────────────────────────────────────────────────────

def _buscar_cnes_api(codigo_cnes):
    """Consulta estabelecimento na API pública do DATASUS CNES."""
    try:
        import requests as req
        url  = f"{_CNES_API_BASE}/estabelecimentos/{codigo_cnes}"
        resp = req.get(
            url,
            headers={"Accept": "application/json"},
            timeout=_CNES_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        logger.warning("CNES API error for %s: %s", codigo_cnes, e)
        return None


def _buscar_lista_cnes_api(params):
    """Busca lista de estabelecimentos na API DATASUS."""
    try:
        import requests as req
        resp = req.get(
            f"{_CNES_API_BASE}/estabelecimentos",
            params=params,
            headers={"Accept": "application/json"},
            timeout=_CNES_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"total": 0, "estabelecimentos": []}
    except Exception as e:
        logger.warning("CNES API list error: %s", e)
        return {"total": 0, "estabelecimentos": [], "erro": str(e)}


def _normalizar_datasus(dado):
    """Normaliza resposta do DATASUS para um dict padronizado."""
    if not dado:
        return {}
    return {
        "cnes":          dado.get("co_cnes") or dado.get("codigo_cnes") or "",
        "nome":          dado.get("no_fantasia") or dado.get("no_razao_social") or "",
        "razao_social":  dado.get("no_razao_social") or "",
        "cnpj":          dado.get("nu_cnpj") or "",
        "tipo":          dado.get("ds_tipo_unidade") or dado.get("co_tipo_unidade") or "",
        "municipio":     dado.get("no_municipio") or "",
        "uf":            dado.get("sg_uf") or "",
        "bairro":        dado.get("no_bairro") or "",
        "endereco":      _montar_endereco(dado),
        "telefone":      dado.get("nu_telefone") or "",
        "latitude":      dado.get("nu_latitude") or None,
        "longitude":     dado.get("nu_longitude") or None,
        "leitos_sus":    int(dado.get("qt_leito_sus") or 0),
        "leitos_uti":    int(dado.get("qt_leito_uti_sus") or 0),
        "diretor":       dado.get("no_diretor_cli") or "",
        "situacao":      dado.get("ds_situacao") or "ativa",
        "natureza_juridica": dado.get("ds_natureza_juridica") or "",
        "esfera_adm":    dado.get("ds_esfera_adm") or "",
    }


def _datasus_para_model(norm, empresa):
    """Converte dict normalizado para campos do modelo UnidadeSaude."""
    tipo_raw   = (norm.get("tipo") or "").lower()
    tipo_model = _mapear_tipo(tipo_raw)

    return {
        "empresa":   empresa,
        "cnes":      norm.get("cnes") or "",
        "nome":      norm.get("nome") or "Sem nome",
        "tipo":      tipo_model,
        "municipio": norm.get("municipio") or "",
        "uf":        norm.get("uf") or "",
        "bairro":    norm.get("bairro") or "",
        "endereco":  norm.get("endereco") or "",
        "telefone":  norm.get("telefone") or "",
        "leitos_sus": norm.get("leitos_sus") or 0,
        "leitos_uti": norm.get("leitos_uti") or 0,
        "diretor":   norm.get("diretor") or "",
        "latitude":  norm.get("latitude"),
        "longitude": norm.get("longitude"),
    }


def _montar_endereco(dado):
    partes = []
    for campo in ("no_logradouro", "nu_endereco", "no_complemento"):
        v = dado.get(campo) or ""
        if v:
            partes.append(v)
    return ", ".join(partes)


def _mapear_tipo(tipo_raw):
    """Mapeia tipo do DATASUS para choice do modelo UnidadeSaude."""
    _mapa = {
        "unidade básica de saúde": "ubs",
        "ubs": "ubs",
        "upa": "upa",
        "caps": "caps_ii",
        "hospital": "hospital",
        "ambulatório": "amb",
        "centro odontológico": "ceo",
        "ceo": "ceo",
        "cerest": "cerest",
        "policlínica": "policlinica",
        "laboratorio": "laboratorio",
        "laboratório": "laboratorio",
    }
    for k, v in _mapa.items():
        if k in tipo_raw:
            return v
    return "outro"


def _uf_para_codigo(sigla):
    """Converte sigla UF para código IBGE de 2 dígitos."""
    _ufs = {
        "AC": "12", "AL": "27", "AP": "16", "AM": "13", "BA": "29",
        "CE": "23", "DF": "53", "ES": "32", "GO": "52", "MA": "21",
        "MT": "51", "MS": "50", "MG": "31", "PA": "15", "PB": "25",
        "PR": "41", "PE": "26", "PI": "22", "RJ": "33", "RN": "24",
        "RS": "43", "RO": "11", "RR": "14", "SC": "42", "SP": "35",
        "SE": "28", "TO": "17",
    }
    return _ufs.get(sigla.upper(), sigla)
