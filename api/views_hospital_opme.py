"""
OPME — Órteses, Próteses e Materiais Especiais
Gestão de catálogo, autorizações prévias e rastreabilidade de implantáveis.
ANVISA RDC 27/2008 | CFM Resolução 2.307/2022
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .utils import validar_cpf_cadastro
from .access_control import (
    api_requer_feature, api_requer_permissao_modulo, get_setor, requer_setor,
    requer_feature_pacote, requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)

# Tipos válidos de OPME — espelha CatalogoOPME.TIPO. Backstop server-side para
# impedir gravação de valor fora das choices (Django .create() não valida choices).
TIPOS_OPME_VALIDOS = {"ortese", "protese", "material", "implante"}

# Máquina de estados da autorização: de qual status se pode ir para qual ação.
# Impede negada→aprovada, reaprovar, agir sobre cancelada etc.
TRANSICOES_AUTORIZACAO = {
    "solicitada": {"aprovar", "negar", "parcial", "cancelar"},
    "aprovada":   {"cancelar"},
    "parcial":    {"cancelar"},
    "negada":     {"cancelar"},
    "cancelada":  set(),
}


class _AcaoInvalida(Exception):
    """Erro de regra de negócio em aprovação parcial — dispara rollback + 400."""
    def __init__(self, erros):
        self.erros = erros if isinstance(erros, list) else [str(erros)]
        super().__init__("; ".join(self.erros))


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _principal_nome(request, empresa):
    """Nome do operador logado, para trilha de auditoria de quem respondeu."""
    principal = getattr(request, "principal", None)
    return (getattr(principal, "nome", None) or getattr(principal, "email", None)
            or getattr(empresa, "nome", "") or "")


def _parse_json(request):
    """Parse seguro do corpo. Retorna (data, erro_response). Um dos dois é None."""
    try:
        return json.loads(request.body or b"{}"), None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, JsonResponse({"erro": "JSON inválido no corpo da requisição"}, status=400)


def _paginacao(request, limite_padrao=100, limite_max=500):
    """Extrai limit/offset da query string, com tetos sãos."""
    try:
        limite = int(request.GET.get("limit", limite_padrao))
    except (TypeError, ValueError):
        limite = limite_padrao
    try:
        offset = int(request.GET.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    limite = max(1, min(limite, limite_max))
    offset = max(0, offset)
    return limite, offset


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.opme", "OPME")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_opme_page(request):
    return render(request, "hospital_opme.html")


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_opme_models():
    from .models import CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, ImplantavelRegistro
    return CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, ImplantavelRegistro


def _get_proc_models():
    from .models import OPMEProcedimento, OPMEProcedimentoItem
    return OPMEProcedimento, OPMEProcedimentoItem


def _get_junta_model():
    from .models import JuntaMedicaOPME
    return JuntaMedicaOPME


# Formato real de registro ANVISA: numérico, 10 a 13 dígitos (ex.: produtos para
# saúde/OPME costumam vir como 8XXXXXXXXXX). Isto é uma checagem de FORMATO —
# não é uma consulta ao webservice da ANVISA (não há API pública estável e
# documentada pra validação em tempo real de registro; por isso não fingimos
# uma integração ao vivo aqui).
def _validar_formato_registro_anvisa(codigo):
    """Retorna (valido: bool, motivo: str|None)."""
    if not codigo:
        return True, None  # campo opcional — vazio não é erro
    digitos = "".join(ch for ch in str(codigo) if ch.isdigit())
    if len(digitos) < 10 or len(digitos) > 13:
        return False, (f"Código ANVISA '{codigo}' não tem formato válido "
                        f"(esperado 10 a 13 dígitos, recebido {len(digitos)}).")
    return True, None


def _anvisa_status(codigo_anvisa):
    """Cruza o registro com a base ANVISA sincronizada. Retorna dict com
    situação real (ou None se a base não está disponível / não tem o registro)."""
    from .models import RegistroAnvisaProdutoSaude
    if not codigo_anvisa:
        return None
    digitos = "".join(ch for ch in str(codigo_anvisa) if ch.isdigit())
    if not digitos or not RegistroAnvisaProdutoSaude.objects.exists():
        return None
    reg = RegistroAnvisaProdutoSaude.objects.filter(numero_registro=digitos).first()
    if not reg:
        return {"encontrado": False}
    vencido = bool(reg.data_vencimento and reg.data_vencimento < date.today())
    return {
        "encontrado": True,
        "situacao": reg.situacao,
        "valido": reg.situacao == "Válido",
        "vencido": vencido,
        "classe_risco": reg.classe_risco,
        "data_vencimento": reg.data_vencimento.isoformat() if reg.data_vencimento else None,
    }


def _item_clinico(a):
    """Serializa os atributos clínicos de um item do catálogo para comparação."""
    return {
        "id": a.id,
        "descricao": a.descricao,
        "fabricante": a.fabricante,
        "material": a.material,
        "especificacoes": a.especificacoes,
        "referencia": a.referencia,
        "codigo_anvisa": a.codigo_anvisa,
        "codigo_operadora": a.codigo_operadora,
        "homologado": a.homologado,
        "preferencial": a.preferencial,
        "preco_maximo": float(a.preco_maximo) if a.preco_maximo else None,
        "anvisa": _anvisa_status(a.codigo_anvisa),
    }


def _marcas_alternativas(empresa, opme_item, limite=3):
    """Busca até `limite` marcas/fabricantes alternativos homologados no mesmo
    grupo de equivalência clínica — base da exigência da RN 424/ANS (o médico
    assistente deve poder escolher entre ao menos 3 marcas registradas na
    ANVISA, quando existirem). Traz atributos clínicos (material, especificação,
    situação ANVISA) para o médico comparar QUALIDADE, não só preço."""
    from .models import CatalogoOPME
    if not opme_item.grupo_equivalencia:
        return []
    alternativos = list(
        CatalogoOPME.objects.filter(
            empresa=empresa, grupo_equivalencia=opme_item.grupo_equivalencia,
            ativo=True, homologado=True,
        ).exclude(id=opme_item.id).order_by("preco_maximo")[:limite]
    )
    return [_item_clinico(a) for a in alternativos]


def _detectar_padrao_fraude(empresa, medico_solicitante, opme_ids_solicitados,
                             AutorizacaoOPME, ItemAutorizacaoOPME):
    """Detecção de padrão atípico no pedido do médico — regra estatística sobre
    o histórico real de autorizações (não é machine learning; é contagem/
    proporção sobre os últimos 30 dias). Retorna lista de alertas (str)."""
    alertas = []
    if not medico_solicitante:
        return alertas
    janela = timezone.now() - timedelta(days=30)
    qs_medico = AutorizacaoOPME.objects.filter(
        empresa=empresa, medico_solicitante__iexact=medico_solicitante,
        solicitado_em__gte=janela,
    )
    total_medico = qs_medico.count()
    fora_padrao_medico = qs_medico.filter(itens__fora_padrao=True).distinct().count()
    if total_medico >= 5 and fora_padrao_medico / total_medico >= 0.6:
        pct = round(fora_padrao_medico / total_medico * 100)
        alertas.append(
            f"Padrão atípico: Dr(a). {medico_solicitante} teve {fora_padrao_medico}/"
            f"{total_medico} solicitações fora do padrão homologado nos últimos 30 "
            f"dias ({pct}% — acima do esperado)."
        )
    for opme_id in opme_ids_solicitados:
        repetidas = ItemAutorizacaoOPME.objects.filter(
            autorizacao__empresa=empresa,
            autorizacao__medico_solicitante__iexact=medico_solicitante,
            autorizacao__solicitado_em__gte=janela,
            opme_id=opme_id,
        ).count()
        if repetidas >= 3:
            alertas.append(
                f"Solicitação repetida: Dr(a). {medico_solicitante} já pediu este "
                f"mesmo material {repetidas}x nos últimos 30 dias."
            )
    return alertas


# Confiança mínima da IA para a Via Rápida disparar a pré-aprovação automática.
IA_SCORE_MINIMO_VIA_RAPIDA = 0.7


def _melhor_custo_beneficio(empresa, opme_item, preco_ref):
    """Melhor alternativa de MESMA QUALIDADE e menor custo, não só a mais barata.
    Qualidade = homologada + registro ANVISA válido (não vencido) + mesmo grupo
    de equivalência clínica. Retorna dict {para, economia, justificativa} ou None."""
    from .models import CatalogoOPME
    if not opme_item.grupo_equivalencia:
        return None
    candidatos = CatalogoOPME.objects.filter(
        empresa=empresa, grupo_equivalencia=opme_item.grupo_equivalencia,
        ativo=True, homologado=True,
    ).exclude(id=opme_item.id).order_by("preco_maximo")
    ref = preco_ref if preco_ref is not None else (
        float(opme_item.preco_maximo) if opme_item.preco_maximo else None)
    for c in candidatos:
        if c.preco_maximo is None or ref is None or float(c.preco_maximo) >= ref:
            continue
        anv = _anvisa_status(c.codigo_anvisa)
        # Mesma qualidade: registro válido e não vencido. Se a base ANVISA não
        # está disponível, ainda aceita (homologação da comissão já é um selo),
        # mas se ESTÁ e o registro é inválido/vencido/inexistente, descarta.
        if anv is not None and not (anv.get("encontrado") and anv.get("valido")
                                    and not anv.get("vencido")):
            continue
        economia = round(ref - float(c.preco_maximo), 2)
        just = (f"Mesmo grupo de equivalência clínica"
                + (f", material {c.material}" if c.material else "")
                + (f", registro ANVISA válido" if anv and anv.get("valido") else "")
                + f". Economia de R$ {economia:.2f} sem perda de qualidade.")
        return {
            "para_id": c.id, "para_descricao": c.descricao,
            "para_fabricante": c.fabricante, "para_preco": float(c.preco_maximo),
            "economia": economia, "justificativa": just,
        }
    return None


def _auditoria_ia_completa(empresa, procedimento_tuss, descricao_itens, cid10,
                           urgente, alertas_triagem, alertas_fraude, anvisa_ok):
    """IA de auditoria: consolida o motor de ML + triagem + fraude + ANVISA num
    parecer único e numa decisão. Retorna (decisao, score, justificativa, parecer).

    decisao ∈ {aprovada, revisao, negada}. É esta decisão + a ausência de
    ressalvas que habilita a Via Rápida."""
    ml_dec, ml_score, ml_just = _recomendacao_ia_opme(
        empresa, procedimento_tuss, descricao_itens, cid10, urgente)

    ressalvas = []
    if alertas_triagem:
        ressalvas.append(f"{len(alertas_triagem)} alerta(s) de triagem (fora do padrão)")
    if alertas_fraude:
        ressalvas.append("padrão atípico do solicitante")
    if anvisa_ok is False:
        ressalvas.append("registro ANVISA inválido/vencido/ausente")

    # Decisão final: o pior sinal manda. Sem ressalvas E ML aprova → aprovada.
    if ressalvas:
        decisao = "negada" if (alertas_fraude and alertas_triagem) else "revisao"
        score = min(ml_score or 0.5, 0.5)
    else:
        decisao = ml_dec if ml_dec in ("aprovada", "revisao", "negada") else "revisao"
        score = ml_score or 0.6

    if decisao == "aprovada" and not ressalvas:
        parecer = ("PARECER DA IA — APROVAR. Pedido em conformidade: material "
                   "homologado, dentro do teto e do procedimento padronizado, "
                   "registro ANVISA válido e sem padrão atípico. "
                   "Elegível para Via Rápida (pré-aprovação automática).")
    elif ressalvas:
        parecer = ("PARECER DA IA — " + ("NEGAR" if decisao == "negada" else "REVISAR")
                   + ". Ressalvas: " + "; ".join(ressalvas)
                   + ". Encaminhado à auditoria humana.")
    else:
        parecer = ("PARECER DA IA — REVISAR. Sem ressalvas objetivas, mas o "
                   "modelo não teve confiança suficiente para aprovação automática. "
                   "Encaminhado à auditoria humana.")
    return decisao, score, ml_just, parecer


def _triar_item(empresa, opme, quantidade, preco_solicitado, permitidos_por_opme):
    """Triagem de um item OPME. Retorna (fora_padrao: bool, alertas: list[str]).
    Regras: material homologado? dentro do teto de preço? permitido para o
    procedimento? quantidade dentro do máximo? preferencial disponível?"""
    alertas = []
    fora = False

    if not opme.homologado:
        alertas.append(f"'{opme.descricao}' NÃO está homologado pela operadora.")
        fora = True

    if preco_solicitado is not None and opme.preco_maximo is not None:
        if float(preco_solicitado) > float(opme.preco_maximo):
            alertas.append(
                f"'{opme.descricao}': preço solicitado R$ {float(preco_solicitado):.2f} "
                f"acima do teto R$ {float(opme.preco_maximo):.2f}.")
            fora = True

    regra = permitidos_por_opme.get(opme.id)
    if permitidos_por_opme:  # há uma lista de permitidos para o procedimento
        if regra is None:
            alertas.append(
                f"'{opme.descricao}' NÃO consta na lista padronizada para este procedimento.")
            fora = True
        else:
            if quantidade > regra["quantidade_maxima"]:
                alertas.append(
                    f"'{opme.descricao}': quantidade {quantidade} acima do máximo "
                    f"padronizado ({regra['quantidade_maxima']}) para o procedimento.")
                fora = True
            if not regra["preferencial"] and regra.get("tem_preferencial"):
                alertas.append(
                    f"'{opme.descricao}' não é o material preferencial do procedimento — "
                    f"existe alternativa padronizada de menor custo.")
    return fora, alertas


def _recomendacao_ia_opme(empresa, procedimento_tuss, descricao_itens, cid10, urgente):
    """Pluga o motor de IA de autorização clínica no fluxo de OPME. Retorna
    (decisao, score, justificativa). Nunca lança — cai em 'revisao' se indisponível."""
    try:
        from .views_hospital_ia_autorizacao import _analisar_solicitacao
        proc_txt = f"OPME para procedimento {procedimento_tuss or 's/ TUSS'}: {descricao_itens}"
        return _analisar_solicitacao(
            "procedimento", proc_txt, cid10, urgente, empresa_id=empresa.pk)
    except Exception:
        return "revisao", 0.5, "Encaminhado para revisão da auditoria (IA indisponível)."


# ── catálogo ───────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_catalogo(request):
    """GET/POST /api/hospital/opme/catalogo/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()

    if request.method == "GET":
        qs = CatalogoOPME.objects.filter(empresa=empresa)
        tipo = request.GET.get("tipo")
        q = request.GET.get("q")
        # ativo: "true" (padrão) só ativos, "false" só inativos, "all" todos.
        ativo = request.GET.get("ativo", "true")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if q:
            qs = qs.filter(Q(descricao__icontains=q) | Q(codigo_anvisa__icontains=q)
                           | Q(codigo_sigtap__icontains=q))
        if ativo == "true":
            qs = qs.filter(ativo=True)
        elif ativo == "false":
            qs = qs.filter(ativo=False)
        total = qs.count()
        limite, offset = _paginacao(request)
        return JsonResponse({
            "total": total,
            "offset": offset,
            "limite": limite,
            "itens": [
                {
                    "id": o.id,
                    "descricao": o.descricao,
                    "tipo": o.tipo,
                    "tipo_display": o.get_tipo_display(),
                    "codigo_anvisa": o.codigo_anvisa,
                    "codigo_sigtap": o.codigo_sigtap,
                    "fabricante": o.fabricante,
                    "referencia": o.referencia,
                    "material": o.material,
                    "especificacoes": o.especificacoes,
                    "preco_maximo": float(o.preco_maximo) if o.preco_maximo else None,
                    "homologado": o.homologado,
                    "preferencial": o.preferencial,
                    "codigo_operadora": o.codigo_operadora,
                    "grupo_equivalencia": o.grupo_equivalencia,
                    "data_validade_registro_anvisa": (
                        o.data_validade_registro_anvisa.isoformat()
                        if o.data_validade_registro_anvisa else None),
                    "registro_anvisa_vencido": bool(
                        o.data_validade_registro_anvisa
                        and o.data_validade_registro_anvisa < date.today()),
                    "ativo": o.ativo,
                }
                for o in qs.order_by("tipo", "descricao")[offset:offset + limite]
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro
    descricao = (data.get("descricao") or "").strip()
    if not descricao:
        return JsonResponse({"erro": "Descrição é obrigatória"}, status=400)
    tipo = data.get("tipo", "material")
    if tipo not in TIPOS_OPME_VALIDOS:
        return JsonResponse(
            {"erro": f"Tipo inválido: '{tipo}'. Use um de: {', '.join(sorted(TIPOS_OPME_VALIDOS))}"},
            status=400,
        )
    codigo_anvisa = data.get("codigo_anvisa", "")
    anvisa_ok, anvisa_erro = _validar_formato_registro_anvisa(codigo_anvisa)
    if not anvisa_ok:
        return JsonResponse({"erro": anvisa_erro}, status=400)
    with transaction.atomic():
        item = CatalogoOPME.objects.create(
            empresa=empresa,
            descricao=descricao,
            tipo=tipo,
            codigo_anvisa=codigo_anvisa,
            codigo_sigtap=data.get("codigo_sigtap", ""),
            fabricante=data.get("fabricante", ""),
            referencia=data.get("referencia", ""),
            material=data.get("material", ""),
            especificacoes=data.get("especificacoes", ""),
            preco_maximo=data.get("preco_maximo"),
            homologado=data.get("homologado", True),
            preferencial=data.get("preferencial", False),
            codigo_operadora=data.get("codigo_operadora", ""),
            grupo_equivalencia=data.get("grupo_equivalencia", ""),
            data_validade_registro_anvisa=data.get("data_validade_registro_anvisa") or None,
            ativo=data.get("ativo", True),
        )
    return JsonResponse({"id": item.id, "descricao": item.descricao}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_catalogo_detalhe(request, item_id):
    """GET/PUT/DELETE /api/hospital/opme/catalogo/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()
    try:
        item = CatalogoOPME.objects.get(id=item_id, empresa=empresa)
    except CatalogoOPME.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": item.id,
            "descricao": item.descricao,
            "tipo": item.tipo,
            "tipo_display": item.get_tipo_display(),
            "codigo_anvisa": item.codigo_anvisa,
            "codigo_sigtap": item.codigo_sigtap,
            "fabricante": item.fabricante,
            "referencia": item.referencia,
            "material": item.material,
            "especificacoes": item.especificacoes,
            "preco_maximo": float(item.preco_maximo) if item.preco_maximo else None,
            "codigo_operadora": item.codigo_operadora,
            "grupo_equivalencia": item.grupo_equivalencia,
            "data_validade_registro_anvisa": (
                item.data_validade_registro_anvisa.isoformat()
                if item.data_validade_registro_anvisa else None),
            "ativo": item.ativo,
        })

    if request.method in ("PUT", "PATCH"):
        data, erro = _parse_json(request)
        if erro:
            return erro
        if "tipo" in data and data["tipo"] not in TIPOS_OPME_VALIDOS:
            return JsonResponse(
                {"erro": f"Tipo inválido: '{data['tipo']}'. Use um de: "
                         f"{', '.join(sorted(TIPOS_OPME_VALIDOS))}"},
                status=400,
            )
        if "preco_maximo" in data and data["preco_maximo"] not in (None, ""):
            try:
                if float(data["preco_maximo"]) < 0:
                    return JsonResponse({"erro": "Preço máximo não pode ser negativo"}, status=400)
            except (TypeError, ValueError):
                return JsonResponse({"erro": "Preço máximo inválido"}, status=400)
        if "codigo_anvisa" in data:
            anvisa_ok, anvisa_erro = _validar_formato_registro_anvisa(data["codigo_anvisa"])
            if not anvisa_ok:
                return JsonResponse({"erro": anvisa_erro}, status=400)
        campos = ["descricao", "tipo", "codigo_anvisa", "codigo_sigtap",
                  "fabricante", "referencia", "preco_maximo", "ativo",
                  "homologado", "preferencial", "codigo_operadora",
                  "grupo_equivalencia", "data_validade_registro_anvisa",
                  "material", "especificacoes"]
        for c in campos:
            if c in data:
                setattr(item, c, data[c])
        item.save()
        return JsonResponse({"ok": True})

    # DELETE
    item.ativo = False
    item.save()
    return JsonResponse({"ok": True})


# ── autorizações ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_autorizacoes(request):
    """GET/POST /api/hospital/opme/autorizacoes/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, _ = _get_opme_models()

    if request.method == "GET":
        qs = AutorizacaoOPME.objects.filter(empresa=empresa).prefetch_related("itens__opme")
        status_f = request.GET.get("status")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(numero_protocolo__icontains=q)
                           | Q(cpf_paciente=q))
        total = qs.count()
        limite, offset = _paginacao(request)
        qs = qs.order_by("-solicitado_em")[offset:offset + limite]
        return JsonResponse({
            "total": total,
            "offset": offset,
            "limite": limite,
            "autorizacoes": [
                {
                    "id": a.id,
                    "numero_protocolo": a.numero_protocolo,
                    "paciente_nome": a.paciente_nome,
                    "cpf_paciente": a.cpf_paciente,
                    "medico_solicitante": a.medico_solicitante,
                    "crm_medico": a.crm_medico,
                    "cid10": a.cid10,
                    "procedimento_tuss": a.procedimento_tuss,
                    "status": a.status,
                    "status_display": a.get_status_display(),
                    "justificativa": a.justificativa,
                    "observacao_auditoria": a.observacao_auditoria,
                    "respondido_por": a.respondido_por,
                    "alertas_triagem": a.alertas_triagem or [],
                    "alertas_fraude": a.alertas_fraude or [],
                    "tem_alerta_fraude": a.tem_alerta_fraude,
                    "ia_decisao": a.ia_decisao,
                    "ia_score": a.ia_score,
                    "ia_justificativa": a.ia_justificativa,
                    "ia_parecer_auditoria": a.ia_parecer_auditoria,
                    "ia_recomendacao": a.ia_recomendacao or {},
                    "via_rapida": a.via_rapida,
                    "solicitado_em": a.solicitado_em.isoformat(),
                    "respondido_em": a.respondido_em.isoformat() if a.respondido_em else None,
                    "validade_ate": a.validade_ate.isoformat() if a.validade_ate else None,
                    "itens": [
                        {
                            "id": it.id,
                            "opme_descricao": it.opme.descricao,
                            "opme_tipo": it.opme.get_tipo_display(),
                            "opme_id": it.opme_id,
                            "fabricante": it.opme.fabricante,
                            "codigo_operadora": it.opme.codigo_operadora,
                            "quantidade": it.quantidade,
                            "quantidade_aprovada": it.quantidade_aprovada,
                            "preco_solicitado": (float(it.preco_solicitado)
                                                 if it.preco_solicitado else None),
                            "fora_padrao": it.fora_padrao,
                            "alerta_triagem": it.alerta_triagem,
                            "status": it.status,
                            "substituido_de": (it.substituido_de.descricao
                                               if it.substituido_de else None),
                            "economia_aplicada": (float(it.economia_aplicada)
                                                  if it.economia_aplicada else None),
                        }
                        for it in a.itens.all()
                    ],
                }
                for a in qs
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro
    itens_data = data.get("itens", [])
    if not itens_data:
        return JsonResponse({"erro": "Pelo menos 1 item OPME é obrigatório"}, status=400)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    medico_solicitante = (data.get("medico_solicitante") or "").strip()
    if not paciente_nome or not medico_solicitante:
        return JsonResponse(
            {"erro": "Nome do paciente e médico solicitante são obrigatórios"}, status=400)

    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)

    # Prazo padrão de validade da autorização: 90 dias corridos.
    validade_padrao = date.today() + timedelta(days=90)
    procedimento_tuss = (data.get("procedimento_tuss") or "").strip()

    # Lista padronizada de materiais permitidos para o procedimento (se houver).
    OPMEProcedimento, OPMEProcedimentoItem = _get_proc_models()
    permitidos_por_opme = {}
    if procedimento_tuss:
        proc = OPMEProcedimento.objects.filter(
            empresa=empresa, codigo_tuss=procedimento_tuss, ativo=True).first()
        if proc:
            itens_perm = list(proc.itens_permitidos.all())
            tem_pref = any(i.preferencial for i in itens_perm)
            for ip in itens_perm:
                permitidos_por_opme[ip.opme_id] = {
                    "quantidade_maxima": ip.quantidade_maxima,
                    "preferencial": ip.preferencial,
                    "tem_preferencial": tem_pref,
                }

    alertas_triagem = []
    descricao_itens = []
    opme_ids_solicitados = []
    marcas_alternativas_por_item = {}
    itens_avaliados = []   # (opme_obj, preco_sol, fora) — p/ ANVISA + custo-benefício
    try:
        with transaction.atomic():
            aut = AutorizacaoOPME.objects.create(
                empresa=empresa,
                paciente_nome=paciente_nome,
                cpf_paciente=data.get("cpf_paciente", ""),
                medico_solicitante=medico_solicitante,
                crm_medico=data.get("crm_medico", ""),
                cid10=data.get("cid10", ""),
                procedimento_tuss=procedimento_tuss,
                justificativa=data.get("justificativa", ""),
                numero_protocolo="",  # preenchido abaixo a partir do PK (race-free)
                validade_ate=data.get("validade_ate") or validade_padrao.isoformat(),
            )
            # Protocolo derivado do PK: único e sem race condition (o count()+1
            # anterior colidia em concorrência e ao apagar registros).
            aut.numero_protocolo = f"OPME-{aut.solicitado_em.year}-{aut.pk:06d}"

            itens_criados = 0
            for it in itens_data:
                opme_id = it.get("opme_id")
                try:
                    opme_obj = CatalogoOPME.objects.get(
                        id=opme_id, empresa=empresa, ativo=True)
                except (CatalogoOPME.DoesNotExist, ValueError, TypeError):
                    # Item inválido, de outro tenant, ou inativo: aborta tudo.
                    raise ValueError(
                        f"Item OPME inválido ou indisponível no catálogo: {opme_id!r}")
                qtd = it.get("quantidade", 1)
                try:
                    qtd = int(qtd)
                except (TypeError, ValueError):
                    raise ValueError(f"Quantidade inválida para item {opme_id!r}")
                if qtd < 1:
                    raise ValueError("Quantidade deve ser ≥ 1")

                preco_sol = it.get("preco_solicitado")
                if preco_sol not in (None, ""):
                    try:
                        preco_sol = float(preco_sol)
                    except (TypeError, ValueError):
                        raise ValueError(f"Preço solicitado inválido para item {opme_id!r}")
                else:
                    preco_sol = None

                # ── Triagem automática do item ──────────────────────────────
                fora, alertas_item = _triar_item(
                    empresa, opme_obj, qtd, preco_sol, permitidos_por_opme)
                alertas_triagem.extend(alertas_item)
                descricao_itens.append(opme_obj.descricao)
                opme_ids_solicitados.append(opme_obj.id)
                itens_avaliados.append((opme_obj, preco_sol, fora))

                # RN 424/ANS: quando o item diverge do padrão, já oferece até
                # 3 marcas/fabricantes alternativos do mesmo grupo clínico.
                if fora:
                    alternativas = _marcas_alternativas(empresa, opme_obj)
                    if alternativas:
                        marcas_alternativas_por_item[opme_obj.id] = alternativas

                # Substituição aceita: o solicitante trocou o material original
                # pela alternativa sugerida. Grava a economia COMPROVADA (é o
                # único número que a operadora pode auditar depois).
                substituido_de = None
                economia = None
                sub_id = it.get("substituido_de_id")
                if sub_id:
                    try:
                        substituido_de = CatalogoOPME.objects.get(
                            id=sub_id, empresa=empresa)
                    except (CatalogoOPME.DoesNotExist, ValueError, TypeError):
                        raise ValueError(
                            f"Material substituído inválido: {sub_id!r}")
                    preco_antigo = it.get("preco_substituido")
                    if preco_antigo in (None, ""):
                        preco_antigo = (float(substituido_de.preco_maximo)
                                        if substituido_de.preco_maximo else None)
                    else:
                        try:
                            preco_antigo = float(preco_antigo)
                        except (TypeError, ValueError):
                            raise ValueError("Preço do material substituído inválido")
                    preco_novo = preco_sol if preco_sol is not None else (
                        float(opme_obj.preco_maximo) if opme_obj.preco_maximo else None)
                    if preco_antigo is not None and preco_novo is not None:
                        economia = round((preco_antigo - preco_novo) * qtd, 2)
                        if economia <= 0:
                            economia = None  # troca não gerou economia — não infla o KPI

                ItemAutorizacaoOPME.objects.create(
                    autorizacao=aut, opme=opme_obj, quantidade=qtd,
                    preco_solicitado=preco_sol, fora_padrao=fora,
                    alerta_triagem=(alertas_item[0] if alertas_item else ""),
                    substituido_de=substituido_de, economia_aplicada=economia)
                itens_criados += 1

            if itens_criados == 0:
                raise ValueError("Nenhum item OPME válido foi informado")

            # RN 424/ANS: se algum item diverge do padrão homologado/preferencial,
            # a justificativa clínica passa a ser OBRIGATÓRIA (antes só alertava,
            # sem bloquear — o pedido "nascia errado" e só quebrava na auditoria).
            if alertas_triagem and not (data.get("justificativa") or "").strip():
                raise ValueError(
                    "Justificativa técnica é obrigatória quando o material solicitado "
                    "diverge do padrão homologado/preferencial (RN 424/ANS). Informe a "
                    "justificativa clínica ou escolha uma das marcas alternativas."
                )

            # ── Detecção de padrão atípico/fraude no pedido do médico ───────
            alertas_fraude = _detectar_padrao_fraude(
                empresa, medico_solicitante, opme_ids_solicitados,
                AutorizacaoOPME, ItemAutorizacaoOPME)

            # ── ANVISA: todos os itens têm registro válido e não vencido? ────
            # Só é True se a base está disponível E todos confirmam válidos.
            anvisa_ok = None
            for opme_obj, _preco, _fora in itens_avaliados:
                st = _anvisa_status(opme_obj.codigo_anvisa)
                if st is None:
                    anvisa_ok = None if anvisa_ok is None else anvisa_ok
                    continue
                item_ok = st.get("encontrado") and st.get("valido") and not st.get("vencido")
                anvisa_ok = item_ok if anvisa_ok is None else (anvisa_ok and item_ok)

            # ── IA de auditoria (consolida triagem + fraude + ANVISA + ML) ──
            ia_dec, ia_score, ia_just, ia_parecer = _auditoria_ia_completa(
                empresa, procedimento_tuss, "; ".join(descricao_itens),
                aut.cid10, bool(data.get("urgente", False)),
                alertas_triagem, alertas_fraude, anvisa_ok)

            # ── Melhor custo-benefício de MESMA qualidade (p/ itens fora) ───
            recomendacao = {}
            for opme_obj, preco_sol, fora in itens_avaliados:
                if fora:
                    mcb = _melhor_custo_beneficio(empresa, opme_obj, preco_sol)
                    if mcb:
                        recomendacao = {"de_id": opme_obj.id,
                                        "de_descricao": opme_obj.descricao, **mcb}
                        break

            # ── VIA RÁPIDA: pré-aprovação automática se TUDO passou ─────────
            elegivel_via_rapida = (
                ia_dec == "aprovada"
                and not alertas_triagem
                and not alertas_fraude
                and anvisa_ok is True
                and (ia_score or 0) >= IA_SCORE_MINIMO_VIA_RAPIDA
            )

            aut.alertas_triagem = alertas_triagem
            aut.ia_decisao = ia_dec
            aut.ia_score = ia_score
            aut.ia_justificativa = ia_just
            aut.ia_parecer_auditoria = ia_parecer
            aut.ia_recomendacao = recomendacao
            aut.alertas_fraude = alertas_fraude
            aut.tem_alerta_fraude = bool(alertas_fraude)

            if elegivel_via_rapida:
                aut.via_rapida = True
                aut.status = "aprovada"
                aut.respondido_por = "IA — Via Rápida (pré-aprovação automática)"
                aut.respondido_em = timezone.now()
                aut.observacao_auditoria = ia_parecer
                aut.itens.all().update(status="aprovado", quantidade_aprovada=F("quantidade"))

            aut.save()
    except ValueError as e:
        return JsonResponse({"erro": str(e)}, status=400)

    return JsonResponse({
        "id": aut.id,
        "numero_protocolo": aut.numero_protocolo,
        "alertas_triagem": alertas_triagem,
        "marcas_alternativas": marcas_alternativas_por_item,
        "alertas_fraude": aut.alertas_fraude,
        "via_rapida": aut.via_rapida,
        "status": aut.status,
        "ia": {"decisao": aut.ia_decisao, "score": aut.ia_score,
               "justificativa": aut.ia_justificativa,
               "parecer": aut.ia_parecer_auditoria},
        "recomendacao": aut.ia_recomendacao or {},
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_autorizacao_acao(request, aut_id):
    """POST /api/hospital/opme/autorizacoes/<id>/acao/ — aprovar/negar/cancelar/parcial."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, AutorizacaoOPME, ItemAutorizacaoOPME, _ = _get_opme_models()
    try:
        aut = AutorizacaoOPME.objects.get(id=aut_id, empresa=empresa)
    except AutorizacaoOPME.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"status": aut.status, "observacao": aut.observacao_auditoria})

    data, erro = _parse_json(request)
    if erro:
        return erro
    nova_acao = data.get("acao")
    mapa_status = {
        "aprovar": "aprovada",
        "negar": "negada",
        "cancelar": "cancelada",
        "parcial": "parcial",
    }
    if nova_acao not in mapa_status:
        return JsonResponse({"erro": f"Ação inválida: {nova_acao}"}, status=400)

    # Máquina de estados: impede transições inválidas (negada→aprovada, reaprovar,
    # agir sobre cancelada). Sem isso, qualquer POST mudava o status livremente.
    acoes_permitidas = TRANSICOES_AUTORIZACAO.get(aut.status, set())
    if nova_acao not in acoes_permitidas:
        return JsonResponse({
            "erro": f"Transição inválida: não é possível '{nova_acao}' uma autorização "
                    f"'{aut.get_status_display()}'.",
            "status_atual": aut.status,
        }, status=409)

    # Negar/cancelar exige motivo registrado (compliance ANS).
    observacao = (data.get("observacao") or "").strip()
    if nova_acao in ("negar", "cancelar") and not observacao:
        return JsonResponse(
            {"erro": "Informe o motivo da negativa/cancelamento na observação."}, status=400)

    try:
        with transaction.atomic():
            aut.status = mapa_status[nova_acao]
            aut.observacao_auditoria = observacao
            aut.respondido_em = timezone.now()
            aut.respondido_por = _principal_nome(request, empresa)
            aut.save(update_fields=[
                "status", "observacao_auditoria", "respondido_em", "respondido_por"])

            if nova_acao == "parcial":
                itens_payload = {str(i.get("id")): i for i in data.get("itens", [])}
                erros_itens = []
                for item in aut.itens.all():
                    item_data = itens_payload.get(str(item.id))
                    if item_data is None:
                        continue
                    try:
                        qtd_aprovada = int(item_data.get("quantidade_aprovada", 0))
                    except (TypeError, ValueError):
                        erros_itens.append(f"Quantidade aprovada inválida no item {item.id}")
                        continue
                    if qtd_aprovada < 0:
                        erros_itens.append(f"Quantidade aprovada negativa no item {item.id}")
                        continue
                    if qtd_aprovada > item.quantidade:
                        erros_itens.append(
                            f"Item {item.id}: aprovado ({qtd_aprovada}) excede o solicitado "
                            f"({item.quantidade})")
                        continue
                    item.quantidade_aprovada = qtd_aprovada
                    item.status = "aprovado" if qtd_aprovada > 0 else "negado"
                    item.motivo_negativa = item_data.get("motivo_negativa", "")
                    item.save(update_fields=[
                        "quantidade_aprovada", "status", "motivo_negativa"])
                if erros_itens:
                    # Aborta a transação inteira — nada de aprovação parcial pela metade.
                    raise _AcaoInvalida(erros_itens)
            elif nova_acao == "aprovar":
                aut.itens.all().update(status="aprovado", quantidade_aprovada=F("quantidade"))
            elif nova_acao == "negar":
                aut.itens.all().update(status="negado", quantidade_aprovada=0)
    except _AcaoInvalida as e:
        return JsonResponse({"erro": "Aprovação parcial inválida", "detalhes": e.erros}, status=400)

    return JsonResponse({"ok": True, "novo_status": aut.status})


# ── Junta Médica/Odontológica (RN nº 424/2017 — ANS) ────────────────────────────
# Mecanismo formal de resolução de divergência técnica entre o médico assistente
# e a operadora sobre marca/material de OPME. A RN 424 exige que, ao divergir,
# a operadora ofereça (ou o médico indique) ao menos 3 marcas de fabricantes
# diferentes regularizadas na ANVISA, quando existirem no catálogo.

TRANSICOES_JUNTA = {
    "aberta":              {"em_analise", "resolvida_medico", "resolvida_operadora", "cancelada"},
    "em_analise":          {"resolvida_medico", "resolvida_operadora", "cancelada"},
    "resolvida_medico":    set(),
    "resolvida_operadora": set(),
    "cancelada":           set(),
}


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_autorizacao_juntas(request, aut_id):
    """GET/POST /api/hospital/opme/autorizacoes/<id>/juntas/ — Junta Médica RN 424."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, AutorizacaoOPME, ItemAutorizacaoOPME, _ = _get_opme_models()
    JuntaMedicaOPME = _get_junta_model()
    try:
        aut = AutorizacaoOPME.objects.get(id=aut_id, empresa=empresa)
    except AutorizacaoOPME.DoesNotExist:
        return JsonResponse({"erro": "Autorização não encontrada"}, status=404)

    if request.method == "GET":
        juntas = aut.juntas_medicas.all()
        return JsonResponse({
            "juntas": [
                {
                    "id": j.id,
                    "item_id": j.item_id,
                    "motivo_divergencia": j.motivo_divergencia,
                    "marcas_alternativas_oferecidas": j.marcas_alternativas_oferecidas,
                    "status": j.status,
                    "status_display": j.get_status_display(),
                    "parecer": j.parecer,
                    "aberta_por": j.aberta_por,
                    "resolvida_por": j.resolvida_por,
                    "aberta_em": j.aberta_em.isoformat(),
                    "resolvida_em": j.resolvida_em.isoformat() if j.resolvida_em else None,
                }
                for j in juntas
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro
    motivo = (data.get("motivo_divergencia") or "").strip()
    if not motivo:
        return JsonResponse(
            {"erro": "Motivo da divergência técnica é obrigatório para abrir a Junta Médica."},
            status=400)

    item = None
    item_id = data.get("item_id")
    marcas = data.get("marcas_alternativas_oferecidas")
    if item_id:
        try:
            item = ItemAutorizacaoOPME.objects.get(id=item_id, autorizacao=aut)
        except (ItemAutorizacaoOPME.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"erro": "Item não encontrado nesta autorização"}, status=404)
        # Se não vieram marcas explícitas no payload, calcula automaticamente
        # a partir do grupo de equivalência clínica do item.
        if marcas is None:
            marcas = _marcas_alternativas(empresa, item.opme)

    junta = JuntaMedicaOPME.objects.create(
        empresa=empresa, autorizacao=aut, item=item,
        motivo_divergencia=motivo,
        marcas_alternativas_oferecidas=marcas or [],
        aberta_por=_principal_nome(request, empresa),
    )
    return JsonResponse({"id": junta.id, "status": junta.status}, status=201)


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_junta_detalhe(request, junta_id):
    """PUT /api/hospital/opme/juntas/<id>/ — avança status/parecer da Junta Médica."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    JuntaMedicaOPME = _get_junta_model()
    try:
        junta = JuntaMedicaOPME.objects.get(id=junta_id, empresa=empresa)
    except JuntaMedicaOPME.DoesNotExist:
        return JsonResponse({"erro": "Junta Médica não encontrada"}, status=404)

    data, erro = _parse_json(request)
    if erro:
        return erro
    novo_status = data.get("status")
    if novo_status and novo_status not in dict(JuntaMedicaOPME.STATUS):
        return JsonResponse({"erro": f"Status inválido: {novo_status}"}, status=400)
    if novo_status:
        permitidos = TRANSICOES_JUNTA.get(junta.status, set())
        if novo_status not in permitidos:
            return JsonResponse({
                "erro": f"Transição inválida: não é possível ir de "
                        f"'{junta.get_status_display()}' para '{novo_status}'.",
                "status_atual": junta.status,
            }, status=409)
        junta.status = novo_status
        if novo_status in ("resolvida_medico", "resolvida_operadora", "cancelada"):
            junta.resolvida_em = timezone.now()
            junta.resolvida_por = _principal_nome(request, empresa)
    if "parecer" in data:
        junta.parecer = data["parecer"]
    junta.save()
    return JsonResponse({"ok": True, "status": junta.status})


@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_juntas(request):
    """GET /api/hospital/opme/juntas/ — todas as Juntas Médicas da empresa."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    JuntaMedicaOPME = _get_junta_model()
    qs = JuntaMedicaOPME.objects.filter(empresa=empresa).select_related(
        "autorizacao", "item__opme")
    status_f = request.GET.get("status")
    if status_f:
        qs = qs.filter(status=status_f)
    total = qs.count()
    limite, offset = _paginacao(request)
    return JsonResponse({
        "total": total,
        "juntas": [
            {
                "id": j.id,
                "autorizacao_id": j.autorizacao_id,
                "protocolo": j.autorizacao.numero_protocolo,
                "paciente_nome": j.autorizacao.paciente_nome,
                "medico_solicitante": j.autorizacao.medico_solicitante,
                "material": j.item.opme.descricao if j.item else "",
                "motivo_divergencia": j.motivo_divergencia,
                "marcas_alternativas_oferecidas": j.marcas_alternativas_oferecidas,
                "status": j.status,
                "status_display": j.get_status_display(),
                "parecer": j.parecer,
                "aberta_por": j.aberta_por,
                "resolvida_por": j.resolvida_por,
                "aberta_em": j.aberta_em.isoformat(),
                "resolvida_em": j.resolvida_em.isoformat() if j.resolvida_em else None,
            }
            for j in qs.order_by("-aberta_em")[offset:offset + limite]
        ],
    })


@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_alternativas(request, item_id):
    """GET /api/hospital/opme/catalogo/<id>/alternativas/ — marcas equivalentes
    homologadas (RN 424/ANS) com a economia de cada uma frente ao item escolhido."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()
    try:
        item = CatalogoOPME.objects.get(id=item_id, empresa=empresa)
    except CatalogoOPME.DoesNotExist:
        return JsonResponse({"erro": "Item não encontrado"}, status=404)

    # Preço de referência: o informado pelo solicitante, senão o teto do item.
    try:
        preco_ref = float(request.GET.get("preco", "") or 0) or None
    except (TypeError, ValueError):
        preco_ref = None
    if preco_ref is None:
        preco_ref = float(item.preco_maximo) if item.preco_maximo else None

    alternativas = _marcas_alternativas(empresa, item)
    for a in alternativas:
        a["economia"] = (
            round(preco_ref - a["preco_maximo"], 2)
            if (preco_ref is not None and a["preco_maximo"] is not None
                and preco_ref > a["preco_maximo"]) else None
        )
    item_clinico = _item_clinico(item)
    item_clinico["grupo_equivalencia"] = item.grupo_equivalencia
    item_clinico["preco_referencia"] = preco_ref
    return JsonResponse({
        "item": item_clinico,
        "alternativas": alternativas,
    })


@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_economia(request):
    """GET /api/hospital/opme/economia/ — painel de custo evitado.

    Separa deliberadamente o que é FATO do que é ESTIMATIVA:
      - realizada:  substituições efetivamente aceitas (economia_aplicada gravada)
      - potencial:  itens fora do padrão ainda pendentes, com alternativa mais
                    barata disponível — dinheiro que dá para economizar se a
                    auditoria atuar, não economia já obtida.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from django.db.models import Sum
    CatalogoOPME, AutorizacaoOPME, ItemAutorizacaoOPME, _ = _get_opme_models()
    hoje = date.today()

    itens_qs = ItemAutorizacaoOPME.objects.filter(autorizacao__empresa=empresa)

    realizada = itens_qs.aggregate(t=Sum("economia_aplicada"))["t"] or 0
    substituicoes = itens_qs.filter(economia_aplicada__isnull=False).count()

    # Potencial em aberto: para cada item fora do padrão ainda pendente, a maior
    # diferença frente a uma alternativa homologada do mesmo grupo clínico.
    potencial = 0.0
    itens_risco = []
    pendentes = itens_qs.filter(
        fora_padrao=True, autorizacao__status="solicitada"
    ).select_related("opme", "autorizacao")
    for it in pendentes:
        preco = float(it.preco_solicitado) if it.preco_solicitado else (
            float(it.opme.preco_maximo) if it.opme.preco_maximo else None)
        if preco is None:
            continue
        alts = _marcas_alternativas(empresa, it.opme)
        baratas = [a["preco_maximo"] for a in alts
                   if a["preco_maximo"] is not None and a["preco_maximo"] < preco]
        if not baratas:
            continue
        dif = (preco - min(baratas)) * it.quantidade
        potencial += dif
        itens_risco.append({
            "protocolo": it.autorizacao.numero_protocolo,
            "paciente_nome": it.autorizacao.paciente_nome,
            "medico_solicitante": it.autorizacao.medico_solicitante,
            "material": it.opme.descricao,
            "opme_id": it.opme_id,          # permite abrir a comparação clínica
            "preco_solicitado": preco,
            "melhor_alternativa": min(baratas),
            "economia_possivel": round(dif, 2),
        })
    itens_risco.sort(key=lambda x: x["economia_possivel"], reverse=True)

    # Série dos últimos 6 meses: economia realizada por mês de solicitação.
    serie = []
    ref = date(hoje.year, hoje.month, 1)
    for _ in range(6):
        prox = date(ref.year + (ref.month // 12), (ref.month % 12) + 1, 1)
        total_mes = itens_qs.filter(
            autorizacao__solicitado_em__date__gte=ref,
            autorizacao__solicitado_em__date__lt=prox,
        ).aggregate(t=Sum("economia_aplicada"))["t"] or 0
        serie.append({"mes": ref.strftime("%m/%Y"), "economia": float(total_mes)})
        ref = date(ref.year - 1, 12, 1) if ref.month == 1 else date(ref.year, ref.month - 1, 1)
    serie.reverse()

    # Ranking de solicitantes por volume fora do padrão (últimos 90 dias).
    ranking = list(
        AutorizacaoOPME.objects.filter(
            empresa=empresa, itens__fora_padrao=True,
            solicitado_em__gte=timezone.now() - timedelta(days=90),
        ).values("medico_solicitante").annotate(n=Count("id", distinct=True)).order_by("-n")[:5]
    )

    return JsonResponse({
        "economia_realizada": float(realizada),
        "substituicoes_aceitas": substituicoes,
        "economia_potencial_aberta": round(potencial, 2),
        "serie_mensal": serie,
        "itens_em_risco": itens_risco[:10],
        "ranking_fora_padrao": ranking,
    })


# ── ANVISA: consulta contra a base oficial sincronizada ─────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_anvisa_consulta(request):
    """GET /api/hospital/opme/anvisa/consulta?registro=XXXX — valida o registro
    contra a base pública da ANVISA já sincronizada localmente. Devolve dados do
    produto para autopreenchimento do catálogo (nome, fabricante, validade,
    situação). NÃO é webservice ao vivo — é o espelho diário do CSV oficial."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import RegistroAnvisaProdutoSaude
    registro = "".join(ch for ch in (request.GET.get("registro") or "") if ch.isdigit())
    if not registro:
        return JsonResponse({"erro": "Informe o número de registro"}, status=400)

    # Base ainda não sincronizada? Diz isso em vez de fingir "não encontrado".
    if not RegistroAnvisaProdutoSaude.objects.exists():
        return JsonResponse({
            "encontrado": False,
            "base_indisponivel": True,
            "mensagem": "Base ANVISA ainda não sincronizada neste ambiente.",
        })

    reg = RegistroAnvisaProdutoSaude.objects.filter(numero_registro=registro).first()
    if not reg:
        return JsonResponse({
            "encontrado": False,
            "mensagem": f"Registro {registro} não encontrado na base da ANVISA.",
        })
    vencido = bool(reg.data_vencimento and reg.data_vencimento < date.today())
    return JsonResponse({
        "encontrado": True,
        "numero_registro": reg.numero_registro,
        "nome_produto": reg.nome_produto,
        "detentor": reg.detentor,
        "cnpj_detentor": reg.cnpj_detentor,
        "classe_risco": reg.classe_risco,
        "situacao": reg.situacao,
        "valido": reg.situacao == "Válido",
        "data_vencimento": reg.data_vencimento.isoformat() if reg.data_vencimento else None,
        "vencido": vencido,
        "atualizado_em": reg.atualizado_em.isoformat(),
    })


# ── Fornecedores (segmento Hospital) — com verificação de AFE ANVISA ─────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_fornecedores(request):
    """GET/POST /api/hospital/opme/fornecedores/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import FornecedorHospital, EmpresaAfeAnvisa

    if request.method == "GET":
        qs = FornecedorHospital.objects.filter(empresa=empresa)
        q = request.GET.get("q")
        if q:
            qs = qs.filter(Q(razao_social__icontains=q) | Q(cnpj=q)
                           | Q(nome_fantasia__icontains=q))
        total = qs.count()
        limite, offset = _paginacao(request)
        return JsonResponse({
            "total": total,
            "fornecedores": [
                {
                    "id": f.id, "razao_social": f.razao_social,
                    "nome_fantasia": f.nome_fantasia, "cnpj": f.cnpj,
                    "contato": f.contato, "telefone": f.telefone, "email": f.email,
                    "afe_numero": f.afe_numero, "afe_situacao": f.afe_situacao,
                    "afe_verificada_em": (f.afe_verificada_em.isoformat()
                                          if f.afe_verificada_em else None),
                    "ativo": f.ativo,
                }
                for f in qs.order_by("razao_social")[offset:offset + limite]
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro
    razao = (data.get("razao_social") or "").strip()
    if not razao:
        return JsonResponse({"erro": "Razão social é obrigatória"}, status=400)
    cnpj = "".join(ch for ch in (data.get("cnpj") or "") if ch.isdigit())
    if cnpj and len(cnpj) != 14:
        return JsonResponse({"erro": "CNPJ deve ter 14 dígitos"}, status=400)

    forn = FornecedorHospital.objects.create(
        empresa=empresa, razao_social=razao,
        nome_fantasia=data.get("nome_fantasia", ""), cnpj=cnpj,
        contato=data.get("contato", ""), telefone=data.get("telefone", ""),
        email=data.get("email", ""),
    )
    _verificar_afe(forn)
    return JsonResponse({"id": forn.id, "afe_situacao": forn.afe_situacao}, status=201)


def _verificar_afe(fornecedor):
    """Cruza o CNPJ do fornecedor com a base AFE da ANVISA sincronizada."""
    from .models import EmpresaAfeAnvisa
    if not fornecedor.cnpj:
        return
    if not EmpresaAfeAnvisa.objects.exists():
        return  # base não sincronizada — não afirma nada
    afe = EmpresaAfeAnvisa.objects.filter(cnpj=fornecedor.cnpj).order_by("-ativo").first()
    if not afe:
        fornecedor.afe_situacao = "não encontrada"
    else:
        fornecedor.afe_numero = afe.numero_afe
        fornecedor.afe_situacao = "ativa" if afe.ativo else "inativa"
    fornecedor.afe_verificada_em = timezone.now()
    fornecedor.save(update_fields=["afe_numero", "afe_situacao", "afe_verificada_em"])


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_fornecedores_verificar_afe(request):
    """POST — reverifica a AFE de todos os fornecedores com CNPJ (após sync ANVISA)."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    from .models import FornecedorHospital
    n = 0
    for f in FornecedorHospital.objects.filter(empresa=empresa).exclude(cnpj=""):
        _verificar_afe(f)
        n += 1
    return JsonResponse({"verificados": n})


# ── implantáveis ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_implantaveis(request):
    """GET/POST /api/hospital/opme/implantaveis/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, AutorizacaoOPME, _, ImplantavelRegistro = _get_opme_models()

    if request.method == "GET":
        qs = ImplantavelRegistro.objects.filter(empresa=empresa).select_related("opme")
        q = request.GET.get("q")
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q)
                           | Q(numero_serie__icontains=q))
        total = qs.count()
        limite, offset = _paginacao(request)
        return JsonResponse({
            "total": total,
            "offset": offset,
            "limite": limite,
            "implantaveis": [
                {
                    "id": i.id,
                    "opme_descricao": i.opme.descricao,
                    "opme_tipo": i.opme.get_tipo_display(),
                    "codigo_anvisa": i.opme.codigo_anvisa,
                    "paciente_nome": i.paciente_nome,
                    "cpf_paciente": i.cpf_paciente,
                    "numero_serie": i.numero_serie,
                    "lote_fabricante": i.lote_fabricante,
                    "data_implante": i.data_implante.isoformat(),
                    "medico_implantador": i.medico_implantador,
                    "hospital": i.hospital,
                }
                for i in qs.order_by("-data_implante")[offset:offset + limite]
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    try:
        opme = CatalogoOPME.objects.get(id=data.get("opme_id"), empresa=empresa)
    except (CatalogoOPME.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"erro": "OPME não encontrado no catálogo"}, status=404)

    # Vínculo com a autorização SEMPRE validado contra a MESMA empresa — sem isso,
    # o hospital A pendurava seu implante numa autorização do hospital B e, via
    # related_name, expunha nome/CPF do paciente de A para B (vazamento LGPD).
    autorizacao = None
    aut_id = data.get("autorizacao_id")
    if aut_id:
        try:
            autorizacao = AutorizacaoOPME.objects.get(id=aut_id, empresa=empresa)
        except (AutorizacaoOPME.DoesNotExist, ValueError, TypeError):
            return JsonResponse(
                {"erro": "Autorização não encontrada nesta empresa"}, status=404)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    data_implante = data.get("data_implante")
    if not paciente_nome or not data_implante:
        return JsonResponse(
            {"erro": "Nome do paciente e data do implante são obrigatórios"}, status=400)

    # Rastreabilidade ANVISA RDC 27/2008: nº de série e lote são OBRIGATÓRIOS no
    # registro de implantável — sem eles um recall não consegue identificar o
    # paciente, que é justamente o que a norma exige.
    numero_serie = (data.get("numero_serie") or "").strip()
    lote_fabricante = (data.get("lote_fabricante") or "").strip()
    if not numero_serie or not lote_fabricante:
        return JsonResponse({
            "erro": "Número de série e lote do fabricante são obrigatórios para "
                    "rastreabilidade (ANVISA RDC 27/2008)."
        }, status=400)

    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)

    impl = ImplantavelRegistro.objects.create(
        empresa=empresa,
        opme=opme,
        autorizacao=autorizacao,
        paciente_nome=paciente_nome,
        cpf_paciente=data.get("cpf_paciente", ""),
        numero_serie=numero_serie,
        lote_fabricante=lote_fabricante,
        data_implante=data_implante,
        medico_implantador=data.get("medico_implantador", ""),
        crm_medico=data.get("crm_medico", ""),
        hospital=data.get("hospital", ""),
        observacoes=data.get("observacoes", ""),
    )
    return JsonResponse({"id": impl.id}, status=201)


# ── KPIs ───────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_kpis(request):
    """GET /api/hospital/opme/kpis/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, AutorizacaoOPME, _, ImplantavelRegistro = _get_opme_models()

    hoje = date.today()
    total_catalogo = CatalogoOPME.objects.filter(empresa=empresa, ativo=True).count()
    aut_qs = AutorizacaoOPME.objects.filter(empresa=empresa)
    por_status = dict(aut_qs.values_list("status").annotate(n=Count("id")).order_by())
    impl_30d = ImplantavelRegistro.objects.filter(
        empresa=empresa,
        data_implante__gte=hoje - timedelta(days=30)
    ).count()
    taxa_aprovacao = 0
    total_resp = (por_status.get("aprovada", 0) + por_status.get("negada", 0)
                  + por_status.get("parcial", 0))
    if total_resp > 0:
        taxa_aprovacao = round(
            (por_status.get("aprovada", 0) + por_status.get("parcial", 0)) / total_resp * 100, 1
        )

    # ── Painel de RISCO: aging de pendências + autorizações vencidas ────────────
    pendentes = aut_qs.filter(status="solicitada")
    limite_sla = hoje - timedelta(days=5)  # SLA de referência: 5 dias corridos
    pendentes_atrasadas = pendentes.filter(solicitado_em__date__lt=limite_sla).count()
    vencidas = aut_qs.filter(
        status__in=["aprovada", "parcial"], validade_ate__lt=hoje).count()
    # Autorizações com pelo menos um material sinalizado fora do padrão pela triagem.
    fora_padrao = aut_qs.filter(itens__fora_padrao=True).distinct().count()

    # ── RN 424 / fraude / ANVISA ─────────────────────────────────────────────
    JuntaMedicaOPME = _get_junta_model()
    juntas_abertas = JuntaMedicaOPME.objects.filter(
        empresa=empresa, status__in=["aberta", "em_analise"]).count()
    medicos_padrao_atipico_30d = aut_qs.filter(
        tem_alerta_fraude=True, solicitado_em__gte=timezone.now() - timedelta(days=30)
    ).values("medico_solicitante").distinct().count()
    catalogo_anvisa_vencido = CatalogoOPME.objects.filter(
        empresa=empresa, ativo=True,
        data_validade_registro_anvisa__lt=hoje,
    ).count()

    # ── Via Rápida: quanto foi pré-aprovado automaticamente ─────────────────
    total_aut = aut_qs.count()
    via_rapida_total = aut_qs.filter(via_rapida=True).count()
    via_rapida_pct = round(via_rapida_total / total_aut * 100, 1) if total_aut else 0

    return JsonResponse({
        "catalogo_itens_ativos": total_catalogo,
        "autorizacoes_por_status": por_status,
        "autorizacoes_pendentes": por_status.get("solicitada", 0),
        "taxa_aprovacao_pct": taxa_aprovacao,
        "implantaveis_ultimos_30d": impl_30d,
        # risco
        "pendentes_atrasadas_sla": pendentes_atrasadas,
        "autorizacoes_vencidas": vencidas,
        "autorizacoes_fora_padrao": fora_padrao,
        # RN 424 / fraude / ANVISA
        "juntas_medicas_abertas": juntas_abertas,
        "medicos_padrao_atipico_30d": medicos_padrao_atipico_30d,
        "catalogo_registros_anvisa_vencidos": catalogo_anvisa_vencido,
        # Via Rápida (IA)
        "via_rapida_total": via_rapida_total,
        "via_rapida_pct": via_rapida_pct,
    })


# ── Procedimentos (catálogo inteligente: TUSS → OPME permitido) ──────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_procedimentos(request):
    """GET/POST /api/hospital/opme/procedimentos/ — padronização por procedimento."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()
    OPMEProcedimento, OPMEProcedimentoItem = _get_proc_models()

    if request.method == "GET":
        qs = OPMEProcedimento.objects.filter(empresa=empresa).prefetch_related(
            "itens_permitidos__opme")
        return JsonResponse({
            "total": qs.count(),
            "procedimentos": [
                {
                    "id": p.id,
                    "codigo_tuss": p.codigo_tuss,
                    "descricao": p.descricao,
                    "ativo": p.ativo,
                    "itens": [
                        {
                            "id": ip.id,
                            "opme_id": ip.opme_id,
                            "opme_descricao": ip.opme.descricao,
                            "quantidade_maxima": ip.quantidade_maxima,
                            "preferencial": ip.preferencial,
                        }
                        for ip in p.itens_permitidos.all()
                    ],
                }
                for p in qs.order_by("descricao")
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro
    codigo = (data.get("codigo_tuss") or "").strip()
    descricao = (data.get("descricao") or "").strip()
    if not codigo or not descricao:
        return JsonResponse({"erro": "Código TUSS e descrição são obrigatórios"}, status=400)
    if OPMEProcedimento.objects.filter(empresa=empresa, codigo_tuss=codigo).exists():
        return JsonResponse({"erro": f"Já existe procedimento com o código {codigo}"}, status=400)

    with transaction.atomic():
        proc = OPMEProcedimento.objects.create(
            empresa=empresa, codigo_tuss=codigo, descricao=descricao)
        for it in data.get("itens", []):
            try:
                opme = CatalogoOPME.objects.get(
                    id=it.get("opme_id"), empresa=empresa)
            except (CatalogoOPME.DoesNotExist, ValueError, TypeError):
                continue
            OPMEProcedimentoItem.objects.create(
                procedimento=proc, opme=opme,
                quantidade_maxima=max(1, int(it.get("quantidade_maxima", 1) or 1)),
                preferencial=bool(it.get("preferencial", False)))
    return JsonResponse({"id": proc.id, "codigo_tuss": proc.codigo_tuss}, status=201)


@csrf_exempt
@require_http_methods(["PUT", "PATCH", "DELETE"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_opme_procedimento_detalhe(request, proc_id):
    """PUT (redefine itens permitidos) / DELETE (inativa) /api/hospital/opme/procedimentos/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    CatalogoOPME, *_ = _get_opme_models()
    OPMEProcedimento, OPMEProcedimentoItem = _get_proc_models()
    try:
        proc = OPMEProcedimento.objects.get(id=proc_id, empresa=empresa)
    except OPMEProcedimento.DoesNotExist:
        return JsonResponse({"erro": "Procedimento não encontrado"}, status=404)

    if request.method == "DELETE":
        proc.ativo = False
        proc.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    data, erro = _parse_json(request)
    if erro:
        return erro
    if "descricao" in data:
        proc.descricao = data["descricao"]
    if "ativo" in data:
        proc.ativo = bool(data["ativo"])
    proc.save()
    # Redefine a lista de itens permitidos, se enviada.
    if "itens" in data:
        with transaction.atomic():
            proc.itens_permitidos.all().delete()
            for it in data["itens"]:
                try:
                    opme = CatalogoOPME.objects.get(id=it.get("opme_id"), empresa=empresa)
                except (CatalogoOPME.DoesNotExist, ValueError, TypeError):
                    continue
                OPMEProcedimentoItem.objects.create(
                    procedimento=proc, opme=opme,
                    quantidade_maxima=max(1, int(it.get("quantidade_maxima", 1) or 1)),
                    preferencial=bool(it.get("preferencial", False)))
    return JsonResponse({"ok": True})
