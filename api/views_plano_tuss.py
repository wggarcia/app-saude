"""
TUSS + Rol ANS + NIP
Catálogo TUSS, cobertura obrigatória Rol ANS (RN 465/2021), Diretrizes de
Utilização e Notificação Intermediária de Pendência — ANS RN 389/2015.
"""
import json
import logging
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)

# Seed TUSS mínimo (Rol ANS RN 465/2021 — exemplos por segmento)
_TUSS_SEED = [
    ("10101012", "Consulta em consultório",                    "consulta",   True,  7, None),
    ("20101001", "Hemograma completo",                         "exame",      True,  3, None),
    ("20102038", "Glicemia em jejum",                          "exame",      True,  3, None),
    ("20103051", "Tomografia computadorizada do crânio",       "exame",      True, 10, None),
    ("40304361", "Apendicectomia",                             "cirurgia",   True, 21, None),
    ("30901030", "Radioterapia conformacional",                "terapia",    True, 30, None),
    ("20201068", "Ecocardiograma",                             "exame",      True,  7, None),
    ("10301012", "Consulta psiquiátrica",                      "saude_mental", True, 10, None),
    ("40101006", "Parto normal",                               "obstetricia",True, None, None),
    ("40101014", "Cesariana",                                  "obstetricia",True, None, None),
    ("40601138", "Hemodiálise",                                "terapia",    True, None, None),
    ("20501012", "Ressonância magnética de crânio",            "exame",      True, 10, None),
    ("30102015", "Fisioterapia motora",                        "fisioterapia",True, 10, None),
    ("87000502", "Internação clínica",                         "internacao", True, None, None),
    ("30719005", "Quimioterapia antineoplásica",               "terapia",    True, None, None),
]


def _get_tuss_models():
    from .models import ProcedimentoTUSS, CoberturaRolANS, DiretrizUtilizacao, NotificacaoNIP, RespostaNIP
    return ProcedimentoTUSS, CoberturaRolANS, DiretrizUtilizacao, NotificacaoNIP, RespostaNIP


def _calc_prazo_uteis_nip(dias_uteis: int) -> date:
    """Calcula prazo em dias úteis (RN 389/2015 — 5 dias úteis)."""
    d = date.today()
    uteis = 0
    while uteis < dias_uteis:
        d += timedelta(days=1)
        if d.weekday() < 5:
            uteis += 1
    return d


# ── Catálogo TUSS ──────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_tuss_procedimentos(request):
    """GET/POST /api/plano-saude/tuss/procedimentos/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProcedimentoTUSS, *_ = _get_tuss_models()

    # Seed automático
    if ProcedimentoTUSS.objects.filter(empresa=empresa).count() == 0:
        for cod, desc, seg, cob, prazo, valor in _TUSS_SEED:
            ProcedimentoTUSS.objects.get_or_create(
                empresa=empresa, codigo_tuss=cod,
                defaults={
                    "descricao": desc,
                    "segmento": seg,
                    "cobertura_obrigatoria": cob,
                    "prazo_atendimento": prazo,
                    "valor_referencia": valor,
                    "ativo": True,
                },
            )

    if request.method == "GET":
        qs = ProcedimentoTUSS.objects.filter(empresa=empresa, ativo=True)
        segmento_f = request.GET.get("segmento")
        cobertura_f = request.GET.get("cobertura_obrigatoria")
        q           = request.GET.get("q")

        if segmento_f:
            qs = qs.filter(segmento=segmento_f)
        if cobertura_f == "true":
            qs = qs.filter(cobertura_obrigatoria=True)
        if q:
            qs = qs.filter(Q(descricao__icontains=q) | Q(codigo_tuss__icontains=q))

        return JsonResponse({
            "total": qs.count(),
            "procedimentos": [
                {
                    "id": p.id,
                    "codigo_tuss": p.codigo_tuss,
                    "descricao": p.descricao,
                    "segmento": p.segmento,
                    "segmento_display": p.get_segmento_display(),
                    "cobertura_obrigatoria": p.cobertura_obrigatoria,
                    "prazo_atendimento": p.prazo_atendimento,
                    "valor_referencia": float(p.valor_referencia) if p.valor_referencia else None,
                }
                for p in qs.order_by("codigo_tuss")[:500]
            ],
        })

    data = json.loads(request.body)
    try:
        proc, created = ProcedimentoTUSS.objects.get_or_create(
            empresa=empresa,
            codigo_tuss=data["codigo_tuss"],
            defaults={
                "descricao": data["descricao"],
                "segmento": data.get("segmento", "exame"),
                "cobertura_obrigatoria": data.get("cobertura_obrigatoria", False),
                "prazo_atendimento": data.get("prazo_atendimento"),
                "valor_referencia": data.get("valor_referencia"),
            },
        )
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=400)

    return JsonResponse({"id": proc.id, "criado": created},
                        status=201 if created else 200)


# ── Rol ANS ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_rol_coberturas(request):
    """GET/POST /api/plano-saude/tuss/rol-ans/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProcedimentoTUSS, CoberturaRolANS, *_ = _get_tuss_models()

    if request.method == "GET":
        qs = CoberturaRolANS.objects.filter(empresa=empresa, ativa=True).select_related("procedimento")
        segmento_f = request.GET.get("segmento")
        cid_f      = request.GET.get("cid")
        q          = request.GET.get("q")

        if segmento_f:
            qs = qs.filter(procedimento__segmento=segmento_f)
        if cid_f:
            qs = qs.filter(cid10_indicacao__icontains=cid_f)
        if q:
            qs = qs.filter(
                Q(procedimento__descricao__icontains=q)
                | Q(procedimento__codigo_tuss__icontains=q)
                | Q(indicacao_clinica__icontains=q)
            )

        return JsonResponse({
            "total": qs.count(),
            "coberturas": [
                {
                    "id": c.id,
                    "procedimento_tuss": c.procedimento.codigo_tuss,
                    "procedimento_descricao": c.procedimento.descricao,
                    "segmento": c.procedimento.segmento,
                    "cid10_indicacao": c.cid10_indicacao,
                    "indicacao_clinica": c.indicacao_clinica,
                    "prazo_consulta_dias_uteis": c.prazo_consulta_dias_uteis,
                    "prazo_exame_dias_uteis": c.prazo_exame_dias_uteis,
                    "prazo_cirurgia_dias_corridos": c.prazo_cirurgia_dias_corridos,
                    "dut_disponivel": c.dut_disponivel,
                }
                for c in qs.order_by("procedimento__codigo_tuss")[:500]
            ],
        })

    data = json.loads(request.body)
    try:
        proc = ProcedimentoTUSS.objects.get(id=data["procedimento_id"], empresa=empresa)
    except ProcedimentoTUSS.DoesNotExist:
        return JsonResponse({"erro": "Procedimento TUSS não encontrado"}, status=404)

    with transaction.atomic():
        cob = CoberturaRolANS.objects.create(
            empresa=empresa,
            procedimento=proc,
            cid10_indicacao=data.get("cid10_indicacao", ""),
            indicacao_clinica=data.get("indicacao_clinica", ""),
            prazo_consulta_dias_uteis=data.get("prazo_consulta_dias_uteis"),
            prazo_exame_dias_uteis=data.get("prazo_exame_dias_uteis"),
            prazo_cirurgia_dias_corridos=data.get("prazo_cirurgia_dias_corridos"),
            dut_disponivel=data.get("dut_disponivel", False),
            vigencia_inicio=data.get("vigencia_inicio"),
            vigencia_fim=data.get("vigencia_fim"),
        )
    return JsonResponse({"id": cob.id}, status=201)


# ── Diretrizes de Utilização (DUT) ─────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_tuss_diretrizes(request):
    """GET/POST /api/plano-saude/tuss/diretrizes/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProcedimentoTUSS, _, DiretrizUtilizacao, *_ = _get_tuss_models()

    if request.method == "GET":
        qs = DiretrizUtilizacao.objects.filter(empresa=empresa, ativa=True).select_related("procedimento")
        q  = request.GET.get("q")

        if q:
            qs = qs.filter(
                Q(titulo__icontains=q)
                | Q(procedimento__codigo_tuss__icontains=q)
                | Q(criterios_acesso__icontains=q)
            )

        return JsonResponse({
            "total": qs.count(),
            "diretrizes": [
                {
                    "id": d.id,
                    "procedimento_tuss": d.procedimento.codigo_tuss,
                    "procedimento_descricao": d.procedimento.descricao,
                    "titulo": d.titulo,
                    "criterios_acesso": d.criterios_acesso,
                    "criterios_exclusao": d.criterios_exclusao,
                    "documentos_necessarios": d.documentos_necessarios,
                    "numero_resolucao": d.numero_resolucao,
                }
                for d in qs.order_by("titulo")
            ],
        })

    data = json.loads(request.body)
    try:
        proc = ProcedimentoTUSS.objects.get(id=data["procedimento_id"], empresa=empresa)
    except ProcedimentoTUSS.DoesNotExist:
        return JsonResponse({"erro": "Procedimento TUSS não encontrado"}, status=404)

    with transaction.atomic():
        dut = DiretrizUtilizacao.objects.create(
            empresa=empresa,
            procedimento=proc,
            titulo=data["titulo"],
            criterios_acesso=data["criterios_acesso"],
            criterios_exclusao=data.get("criterios_exclusao", ""),
            documentos_necessarios=data.get("documentos_necessarios", ""),
            numero_resolucao=data.get("numero_resolucao", ""),
            vigencia_inicio=data.get("vigencia_inicio"),
        )
    return JsonResponse({"id": dut.id}, status=201)


# ── Consulta de cobertura (beneficiário verifica se procedimento está coberto) ─

def api_tuss_verificar_cobertura(request):
    """GET /api/plano-saude/tuss/verificar/?codigo_tuss=X&cid=Y"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProcedimentoTUSS, CoberturaRolANS, DiretrizUtilizacao, *_ = _get_tuss_models()

    codigo_tuss = request.GET.get("codigo_tuss", "")
    cid         = request.GET.get("cid", "")

    try:
        proc = ProcedimentoTUSS.objects.get(empresa=empresa, codigo_tuss=codigo_tuss, ativo=True)
    except ProcedimentoTUSS.DoesNotExist:
        return JsonResponse({"coberto": False, "motivo": "Código TUSS não encontrado no catálogo"})

    # Verifica cobertura
    cob_qs = CoberturaRolANS.objects.filter(
        empresa=empresa, procedimento=proc, ativa=True
    )
    if cid:
        cob_qs = cob_qs.filter(Q(cid10_indicacao="") | Q(cid10_indicacao__startswith=cid[:3]))

    cobertura = cob_qs.first()

    # DUT disponível?
    dut = DiretrizUtilizacao.objects.filter(empresa=empresa, procedimento=proc, ativa=True).first()

    hoje = date.today()
    return JsonResponse({
        "codigo_tuss": codigo_tuss,
        "descricao": proc.descricao,
        "segmento": proc.segmento,
        "cobertura_obrigatoria": proc.cobertura_obrigatoria,
        "coberto": cobertura is not None or proc.cobertura_obrigatoria,
        "prazo_consulta_dias_uteis": cobertura.prazo_consulta_dias_uteis if cobertura else proc.prazo_atendimento,
        "data_prazo_maxima": (
            _calc_prazo_uteis_nip(cobertura.prazo_consulta_dias_uteis).isoformat()
            if cobertura and cobertura.prazo_consulta_dias_uteis else None
        ),
        "dut": {
            "titulo": dut.titulo,
            "criterios_acesso": dut.criterios_acesso,
            "documentos": dut.documentos_necessarios,
        } if dut else None,
    })


# ── NIP — Notificação Intermediária de Pendência ───────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_nip_lista(request):
    """GET/POST /api/plano-saude/nip/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, NotificacaoNIP, _ = _get_tuss_models()

    if request.method == "GET":
        qs = NotificacaoNIP.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        tipo_f   = request.GET.get("tipo")
        q        = request.GET.get("q")
        vencendo = request.GET.get("prazo_vencendo")

        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)
        if q:
            qs = qs.filter(
                Q(beneficiario_nome__icontains=q) | Q(cpf_beneficiario=q)
                | Q(numero_nip__icontains=q)
            )
        if vencendo == "true":
            limite = date.today() + timedelta(days=2)
            qs = qs.filter(prazo_resposta__lte=limite,
                           status__in=["aberta", "em_analise"])

        hoje = date.today()
        return JsonResponse({
            "total": qs.count(),
            "nips": [
                {
                    "id": n.id,
                    "numero_nip": n.numero_nip,
                    "beneficiario_nome": n.beneficiario_nome,
                    "cpf_beneficiario": n.cpf_beneficiario,
                    "tipo": n.tipo,
                    "tipo_display": n.get_tipo_display(),
                    "status": n.status,
                    "status_display": n.get_status_display(),
                    "data_abertura": n.data_abertura.isoformat(),
                    "prazo_resposta": n.prazo_resposta.isoformat() if n.prazo_resposta else None,
                    "prazo_vencido": bool(
                        n.prazo_resposta and n.prazo_resposta < hoje
                        and n.status in ("aberta", "em_analise")
                    ),
                }
                for n in qs.order_by("-data_abertura")[:200]
            ],
        })

    data = json.loads(request.body)

    # Protocolo sequencial
    total = NotificacaoNIP.objects.filter(empresa=empresa).count() + 1
    numero_nip = f"NIP-{empresa.id:06d}-{date.today().year}-{total:05d}"

    # Prazo: 5 dias úteis (RN 389/2015, art. 9º)
    prazo_resposta = _calc_prazo_uteis_nip(5)

    with transaction.atomic():
        nip = NotificacaoNIP.objects.create(
            empresa=empresa,
            numero_nip=numero_nip,
            beneficiario_nome=data["beneficiario_nome"],
            cpf_beneficiario=data.get("cpf_beneficiario", ""),
            carteirinha=data.get("carteirinha", ""),
            tipo=data["tipo"],
            descricao=data["descricao"],
            prazo_resposta=prazo_resposta,
            procedimento_id=data.get("procedimento_id"),
            obs_interna=data.get("obs_interna", ""),
        )

    return JsonResponse({
        "id": nip.id,
        "numero_nip": numero_nip,
        "prazo_resposta": prazo_resposta.isoformat(),
        "mensagem": f"NIP registrada. Prazo de resposta: {prazo_resposta.strftime('%d/%m/%Y')} (RN 389/2015)",
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_nip_detalhe(request, nip_id):
    """GET/PUT /api/plano-saude/nip/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, NotificacaoNIP, _ = _get_tuss_models()
    try:
        nip = NotificacaoNIP.objects.get(id=nip_id, empresa=empresa)
    except NotificacaoNIP.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        resposta = None
        if hasattr(nip, "resposta"):
            r = nip.resposta
            resposta = {
                "data_resposta": r.data_resposta.isoformat(),
                "respondido_por": r.respondido_por,
                "conteudo": r.conteudo,
                "aceite_beneficiario": r.aceite_beneficiario,
            }
        return JsonResponse({
            "id": nip.id,
            "numero_nip": nip.numero_nip,
            "beneficiario_nome": nip.beneficiario_nome,
            "cpf_beneficiario": nip.cpf_beneficiario,
            "carteirinha": nip.carteirinha,
            "tipo": nip.tipo,
            "tipo_display": nip.get_tipo_display(),
            "descricao": nip.descricao,
            "data_abertura": nip.data_abertura.isoformat(),
            "prazo_resposta": nip.prazo_resposta.isoformat() if nip.prazo_resposta else None,
            "status": nip.status,
            "status_display": nip.get_status_display(),
            "obs_interna": nip.obs_interna,
            "resposta": resposta,
        })

    data = json.loads(request.body)
    campos = ["status", "obs_interna"]
    for c in campos:
        if c in data:
            setattr(nip, c, data[c])
    nip.save()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def api_nip_responder(request, nip_id):
    """POST /api/plano-saude/nip/<id>/responder/ — registra resposta da operadora."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, _, NotificacaoNIP, RespostaNIP = _get_tuss_models()
    try:
        nip = NotificacaoNIP.objects.get(id=nip_id, empresa=empresa)
    except NotificacaoNIP.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if hasattr(nip, "resposta"):
        return JsonResponse({"erro": "NIP já respondida"}, status=400)

    data = json.loads(request.body)
    with transaction.atomic():
        resp = RespostaNIP.objects.create(
            empresa=empresa,
            nip=nip,
            data_resposta=data.get("data_resposta", date.today().isoformat()),
            respondido_por=data.get("respondido_por", ""),
            conteudo=data["conteudo"],
            aceite_beneficiario=data.get("aceite_beneficiario"),
            documento_comprobatorio=data.get("documento_comprobatorio", ""),
        )
        nip.status = "respondida"
        nip.save()

    no_prazo = nip.prazo_resposta and date.today() <= nip.prazo_resposta
    return JsonResponse({
        "id": resp.id,
        "respondida_no_prazo": no_prazo,
        "mensagem": "Resposta registrada no prazo ANS" if no_prazo else "⚠️ Resposta fora do prazo ANS (RN 389/2015)",
    }, status=201)


# ── KPIs ───────────────────────────────────────────────────────────────────────

def api_tuss_kpis(request):
    """GET /api/plano-saude/tuss/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProcedimentoTUSS, CoberturaRolANS, _, NotificacaoNIP, _ = _get_tuss_models()

    hoje = date.today()
    por_status = dict(
        NotificacaoNIP.objects.filter(empresa=empresa)
        .values_list("status").annotate(n=Count("id")).order_by()
    )
    vencidas = NotificacaoNIP.objects.filter(
        empresa=empresa,
        prazo_resposta__lt=hoje,
        status__in=["aberta", "em_analise"],
    ).count()
    por_tipo = dict(
        NotificacaoNIP.objects.filter(empresa=empresa)
        .values_list("tipo").annotate(n=Count("id")).order_by()
    )
    total_tuss   = ProcedimentoTUSS.objects.filter(empresa=empresa, ativo=True).count()
    cobertura_ob = CoberturaRolANS.objects.filter(empresa=empresa, ativa=True).count()

    return JsonResponse({
        "nip_por_status": por_status,
        "nip_prazo_vencido": vencidas,
        "nip_por_tipo": por_tipo,
        "procedimentos_tuss_ativos": total_tuss,
        "coberturas_rol_ans_ativas": cobertura_ob,
    })
