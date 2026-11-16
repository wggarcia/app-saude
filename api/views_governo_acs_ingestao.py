"""
Ingestão de visitas domiciliares vindas do PEC (e-SUS APS) do município.

O PEC roda dentro da rede da prefeitura, fora do alcance do servidor do SoloCRT.
Um coletor local (integracoes/coletor_pec/) lê o banco do PEC em modo leitura e
envia lotes para cá, autenticado por uma chave de API da empresa (ApiKeyEmpresa,
header "Authorization: ApiKey <chave>"), não pela sessão do usuário.

POST /api/governo/acs/ingestao/visitas
  {"visitas": [{"uuid_origem": "...", "acs_cns": "...", "data_visita": "AAAA-MM-DD",
                "turno": 1, "desfecho": 1, "motivos": [29, 5], ...}]}

Códigos turno/desfecho/motivos seguem a tabela LEDI APS (mesma do PEC). O
reenvio do mesmo uuid_origem atualiza em vez de duplicar. Visita importada nasce
com transmitido_esus=True: ela já está no e-SUS e nunca é reexportada.
"""
import json
import re
from datetime import date, timedelta

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

LIMITE_LOTE = 500
LIMITE_CORPO_BYTES = 5 * 1024 * 1024
_RE_UUID_ORIGEM = re.compile(r"^[A-Za-z0-9:._-]{1,64}$")

_TURNO_LEDI = {1: "M", 2: "T", 3: "N"}
_DESFECHO_LEDI = {1: "visita_realizada", 2: "recusou", 3: "ausente"}
# Primeiro código reconhecido decide o motivo principal (nosso modelo guarda um só).
_MOTIVO_LEDI = {
    1: "cadastramento", 29: "visita_rotineira", 30: "acompanhamento", 21: "acompanhamento",
    5: "pre_natal", 8: "puericultura", 7: "puericultura", 38: "pessoa_idosa",
    11: "portador_doenca_cronica", 12: "portador_doenca_cronica", 13: "portador_doenca_cronica",
    14: "portador_doenca_cronica", 15: "portador_doenca_cronica", 16: "portador_doenca_cronica",
    17: "portador_doenca_cronica", 18: "portador_doenca_cronica",
    22: "saude_mental", 23: "saude_mental", 24: "saude_mental",
    19: "domiciliado", 25: "egresso_internacao",
}
_MOTIVO_GESTANTE = 5


def _autenticar(request):
    from .services.integracao_auth import empresa_por_api_key
    empresa, _ = empresa_por_api_key(request)
    return empresa


def _digitos(valor, tamanho, campo, obrigatorio=False):
    if valor in (None, ""):
        if obrigatorio:
            raise ValueError(f"{campo} obrigatório")
        return ""
    s = str(valor).strip()
    if not s.isdigit() or len(s) != tamanho:
        raise ValueError(f"{campo} deve ter {tamanho} dígitos")
    return s


def _numero(valor, campo, minimo, maximo, inteiro=False):
    if valor in (None, ""):
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{campo} deve ser numérico")
    if not (minimo <= valor <= maximo):
        raise ValueError(f"{campo} fora da faixa {minimo}-{maximo}")
    return int(valor) if inteiro else valor


def _codigo(valor, tabela, campo, padrao):
    if valor in (None, ""):
        return tabela[padrao]
    if isinstance(valor, bool) or not isinstance(valor, int) or valor not in tabela:
        raise ValueError(f"{campo} inválido (use {sorted(tabela)})")
    return tabela[valor]


def _texto(valor, campo, maximo):
    if valor in (None, ""):
        return ""
    if not isinstance(valor, str):
        raise ValueError(f"{campo} deve ser texto")
    return valor.strip()[:maximo]


def validar_item(item):
    """Valida e normaliza uma visita vinda do coletor. Levanta ValueError com o
    motivo em português, que volta ao coletor na lista de rejeitadas."""
    if not isinstance(item, dict):
        raise ValueError("item deve ser um objeto")
    uuid_origem = item.get("uuid_origem")
    if not isinstance(uuid_origem, str) or not _RE_UUID_ORIGEM.match(uuid_origem):
        raise ValueError("uuid_origem obrigatório (até 64 caracteres: letras, números, : . _ -)")

    data_raw = item.get("data_visita")
    try:
        data_visita = date.fromisoformat(data_raw) if isinstance(data_raw, str) else None
    except ValueError:
        data_visita = None
    if not data_visita:
        raise ValueError("data_visita obrigatória no formato AAAA-MM-DD")
    if data_visita > timezone.localdate() + timedelta(days=1) or data_visita.year < 2000:
        raise ValueError("data_visita fora do período aceito")

    motivos = item.get("motivos") or []
    if not isinstance(motivos, list) or not all(isinstance(m, int) and not isinstance(m, bool) for m in motivos):
        raise ValueError("motivos deve ser uma lista de códigos numéricos LEDI")
    motivo = next((_MOTIVO_LEDI[m] for m in motivos if m in _MOTIVO_LEDI), "outro")

    gestante = item.get("gestante")
    if gestante is not None and not isinstance(gestante, bool):
        raise ValueError("gestante deve ser verdadeiro ou falso")

    return {
        "uuid_origem": uuid_origem,
        "acs_cns": _digitos(item.get("acs_cns"), 15, "acs_cns", obrigatorio=True),
        "acs_nome": _texto(item.get("acs_nome"), "acs_nome", 160),
        "cnes": _digitos(item.get("cnes"), 7, "cnes"),
        "ine": _digitos(item.get("ine"), 10, "ine"),
        "microarea": _texto(item.get("microarea"), "microarea", 10),
        "data_visita": data_visita,
        "turno": _codigo(item.get("turno"), _TURNO_LEDI, "turno", 1),
        "desfecho": _codigo(item.get("desfecho"), _DESFECHO_LEDI, "desfecho", 1),
        "motivo": motivo,
        "gestante": bool(gestante) or _MOTIVO_GESTANTE in motivos,
        "paciente_nome": _texto(item.get("paciente_nome"), "paciente_nome", 160),
        "cpf_paciente": _digitos(item.get("cpf_paciente"), 11, "cpf_paciente"),
        "cns_paciente": _digitos(item.get("cns_paciente"), 15, "cns_paciente"),
        "peso_kg": _numero(item.get("peso_kg"), "peso_kg", 0, 500),
        "pa_sistolica": _numero(item.get("pa_sistolica"), "pa_sistolica", 0, 300, inteiro=True),
        "pa_diastolica": _numero(item.get("pa_diastolica"), "pa_diastolica", 0, 300, inteiro=True),
        "glicemia": _numero(item.get("glicemia"), "glicemia", 0, 1000),
    }


def _acs_por_cns(empresa, dados, cache):
    from .models import AgenteComunidadeSaude
    cns = dados["acs_cns"]
    if cns in cache:
        return cache[cns]
    acs = AgenteComunidadeSaude.objects.filter(empresa=empresa, cns=cns).first()
    if not acs:
        acs = AgenteComunidadeSaude.objects.create(
            empresa=empresa, cns=cns,
            nome=dados["acs_nome"] or f"ACS CNS {cns} (importado do PEC)",
            cnes_usf=dados["cnes"], ine_equipe=dados["ine"], microarea=dados["microarea"],
        )
    cache[cns] = acs
    return acs


_CAMPOS_VISITA = ("data_visita", "turno", "motivo", "desfecho", "gestante", "paciente_nome",
                  "cpf_paciente", "cns_paciente", "peso_kg", "pa_sistolica", "pa_diastolica", "glicemia")


@csrf_exempt
@require_http_methods(["POST"])
def api_ingestao_visitas_pec(request):
    """POST /api/governo/acs/ingestao/visitas — lote de visitas do coletor PEC."""
    from .views import _rate_limit_publico
    if _rate_limit_publico(request, bucket="ingestao_pec", limite=60):
        return JsonResponse({"erro": "Muitas requisições. Aguarde um minuto."}, status=429)

    empresa = _autenticar(request)
    if not empresa:
        return JsonResponse({"erro": "Chave de API inválida. Use o header Authorization: ApiKey <chave>."},
                            status=401)

    from .access_control import get_setor
    if get_setor(empresa) != "governo":
        return JsonResponse({"erro": "Ingestão do PEC disponível apenas para o segmento Governo."}, status=403)

    if len(request.body or b"") > LIMITE_CORPO_BYTES:
        return JsonResponse({"erro": "Corpo da requisição grande demais."}, status=413)
    try:
        corpo = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)
    visitas = corpo.get("visitas") if isinstance(corpo, dict) else None
    if not isinstance(visitas, list) or not visitas:
        return JsonResponse({"erro": "Envie {\"visitas\": [...]} com ao menos uma visita."}, status=400)
    if len(visitas) > LIMITE_LOTE:
        return JsonResponse({"erro": f"Lote acima do limite de {LIMITE_LOTE} visitas."}, status=413)

    from .middleware import _rls_set_empresa
    from .models import VisitaDomiciliar
    _rls_set_empresa(empresa.id)

    criadas, atualizadas, rejeitadas = 0, 0, []
    cache_acs = {}
    for i, item in enumerate(visitas):
        try:
            dados = validar_item(item)
        except ValueError as exc:
            rejeitadas.append({"indice": i, "uuid_origem": (item or {}).get("uuid_origem") if isinstance(item, dict) else None,
                               "motivo": str(exc)})
            continue
        with transaction.atomic():
            acs = _acs_por_cns(empresa, dados, cache_acs)
            existente = (VisitaDomiciliar.objects.select_for_update()
                         .filter(empresa=empresa, uuid_origem=dados["uuid_origem"]).first())
            valores = {c: dados[c] for c in _CAMPOS_VISITA}
            if existente:
                for c, val in valores.items():
                    setattr(existente, c, val)
                existente.acs = acs
                existente.save()
                atualizadas += 1
            else:
                VisitaDomiciliar.objects.create(
                    empresa=empresa, acs=acs, uuid_origem=dados["uuid_origem"],
                    origem="pec", transmitido_esus=True, **valores,
                )
                criadas += 1

    return JsonResponse({"criadas": criadas, "atualizadas": atualizadas,
                         "rejeitadas": rejeitadas, "recebidas": len(visitas)})
