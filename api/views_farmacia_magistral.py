"""
Farmácia Magistral — Manipulação
RDC 67/2007 ANVISA

GET/POST /api/farmacia/magistral/materias-primas
GET/POST /api/farmacia/magistral/lotes-mp
GET/POST /api/farmacia/magistral/formulas
GET/POST /api/farmacia/magistral/ordens
PATCH    /api/farmacia/magistral/ordens/<id>/status
GET/POST /api/farmacia/magistral/controle-qualidade
GET      /api/farmacia/magistral/kpis
"""
import json
import math
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .access_control import requer_setor, requer_operacao_page, requer_permissao_modulo, api_requer_feature, get_setor
from .utils import validar_cpf_cadastro

from .services.auth_session import empresa_autenticada_from_request


def _farm(request):
    emp = empresa_autenticada_from_request(request)
    if emp and get_setor(emp) == "farmacia":
        return emp
    return None


def _dec(value, default=Decimal("0")):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _consumir_materias_primas(empresa, om):
    """Baixa as matérias-primas da fórmula ao iniciar a manipulação (RDC 67/2007).

    DEVE rodar dentro de `transaction.atomic()`. Para cada item da composição da
    fórmula: trava e decrementa `MateriaPrimaFarmacia.estoque_atual` e consome dos
    `LoteMateriaPrima` aprovados por FEFO (validade mais próxima). As quantidades
    são escalonadas pela razão entre a quantidade da OM e a quantidade padrão da
    fórmula. Retorna a lista de consumos aplicados."""
    from .models import MateriaPrimaFarmacia, LoteMateriaPrima

    formula = om.formula
    composicao = formula.composicao if isinstance(formula.composicao, list) else []

    qtd_padrao = _dec(formula.quantidade_padrao)
    fator = (_dec(om.quantidade) / qtd_padrao) if qtd_padrao > 0 else Decimal("1")

    consumos = []
    for comp in composicao:
        mp_id = comp.get("materia_prima_id")
        if not mp_id:
            continue
        consumo = _dec(comp.get("quantidade")) * fator
        if consumo <= 0:
            continue

        mp = (MateriaPrimaFarmacia.objects.select_for_update()
              .filter(id=mp_id, empresa=empresa).first())
        if mp is None:
            continue

        mp.estoque_atual = max(_dec(mp.estoque_atual) - consumo, Decimal("0"))
        mp.save(update_fields=["estoque_atual", "atualizado_em"])

        # Consome dos lotes aprovados por FEFO.
        restante = consumo
        lotes = (LoteMateriaPrima.objects.select_for_update()
                 .filter(empresa=empresa, materia_prima=mp, status="aprovado",
                         quantidade_disponivel__gt=0)
                 .order_by("data_validade"))
        for lote in lotes:
            if restante <= 0:
                break
            disp = _dec(lote.quantidade_disponivel)
            usar = min(disp, restante)
            lote.quantidade_disponivel = disp - usar
            restante -= usar
            if lote.quantidade_disponivel <= 0:
                lote.status = "consumido"
            lote.save(update_fields=["quantidade_disponivel", "status"])

        consumos.append({"materia_prima_id": mp.id, "quantidade": float(consumo)})

    return consumos


@ensure_csrf_cookie
@requer_setor("farmacia")
@requer_operacao_page
@requer_permissao_modulo("farmacia.gestao")
def farmacia_magistral_page(request):
    return render(request, "farmacia_magistral.html")


# ── Matérias-primas ───────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_materias_primas(request):
    """GET lista | POST cria matéria-prima."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import MateriaPrimaFarmacia

    if request.method == "GET":
        categoria        = request.GET.get("categoria")
        critico          = request.GET.get("critico")
        apenas_ativos    = request.GET.get("ativos", "true").lower() == "true"
        q                = (request.GET.get("q") or "").strip()

        qs = MateriaPrimaFarmacia.objects.filter(empresa=empresa)
        if apenas_ativos:
            qs = qs.filter(ativo=True)
        if categoria:
            qs = qs.filter(categoria=categoria)
        if q:
            qs = qs.filter(nome__icontains=q)

        items = list(qs)
        if critico == "true":
            items = [i for i in items if i.estoque_critico]

        return JsonResponse({
            "total":        len(items),
            "materias_primas": [_mp_dict(m) for m in items],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = (body.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Campo 'nome' obrigatório"}, status=400)

        if MateriaPrimaFarmacia.objects.filter(empresa=empresa, nome__iexact=nome).exists():
            return JsonResponse({"erro": f"Matéria-prima '{nome}' já cadastrada"}, status=409)

        mp = MateriaPrimaFarmacia.objects.create(
            empresa           = empresa,
            nome              = nome,
            sinonimos         = (body.get("sinonimos") or "").strip(),
            cas_numero        = (body.get("cas_numero") or "").strip(),
            categoria         = body.get("categoria") or "ativo",
            unidade_medida    = (body.get("unidade_medida") or "g").strip(),
            estoque_atual     = body.get("estoque_atual") or 0,
            estoque_minimo    = body.get("estoque_minimo") or 0,
            fornecedor        = (body.get("fornecedor") or "").strip(),
            controlado_anvisa = bool(body.get("controlado_anvisa", False)),
        )
        return JsonResponse({"status": "criado", "id": mp.id, "materia_prima": _mp_dict(mp)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Lotes de matéria-prima ────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_lotes_mp(request):
    """GET lista | POST registra lote."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import LoteMateriaPrima, MateriaPrimaFarmacia

    if request.method == "GET":
        mp_id   = request.GET.get("materia_prima_id")
        status  = request.GET.get("status")

        qs = LoteMateriaPrima.objects.filter(empresa=empresa).select_related("materia_prima")
        if mp_id:
            qs = qs.filter(materia_prima_id=mp_id)
        if status:
            qs = qs.filter(status=status)

        today = date.today()
        lotes = list(qs)
        # Auto-marca vencidos
        vencidos_ids = [l.id for l in lotes if l.data_validade < today and l.status not in ("vencido", "consumido")]
        if vencidos_ids:
            LoteMateriaPrima.objects.filter(id__in=vencidos_ids).update(status="vencido")
            for l in lotes:
                if l.id in vencidos_ids:
                    l.status = "vencido"

        return JsonResponse({
            "total":       len(lotes),
            "lotes":       [_lote_mp_dict(l) for l in lotes],
            "alertas":     {
                "vencidos":     sum(1 for l in lotes if l.status == "vencido"),
                "quarentena":   sum(1 for l in lotes if l.status == "quarentena"),
                "vencendo_30d": sum(1 for l in lotes if l.status == "aprovado" and (l.data_validade - today).days <= 30),
            },
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        mp_id       = body.get("materia_prima_id")
        numero_lote = (body.get("numero_lote") or "").strip()
        quantidade  = body.get("quantidade_inicial")
        validade    = body.get("data_validade")

        if not all([mp_id, numero_lote, quantidade, validade]):
            return JsonResponse({"erro": "Campos obrigatórios: materia_prima_id, numero_lote, quantidade_inicial, data_validade"}, status=400)

        try:
            mp = MateriaPrimaFarmacia.objects.get(id=mp_id, empresa=empresa)
        except MateriaPrimaFarmacia.DoesNotExist:
            return JsonResponse({"erro": "Matéria-prima não encontrada"}, status=404)

        lote = LoteMateriaPrima.objects.create(
            materia_prima         = mp,
            empresa               = empresa,
            numero_lote           = numero_lote,
            fornecedor            = (body.get("fornecedor") or "").strip(),
            nota_fiscal           = (body.get("nota_fiscal") or "").strip(),
            quantidade_inicial    = quantidade,
            quantidade_disponivel = quantidade,
            data_fabricacao       = body.get("data_fabricacao") or None,
            data_validade         = validade,
            data_entrada          = body.get("data_entrada") or date.today().isoformat(),
            laudo_coa             = (body.get("laudo_coa") or "").strip(),
        )
        # Atualiza estoque da matéria-prima
        mp.estoque_atual += float(quantidade)
        mp.save(update_fields=["estoque_atual"])

        return JsonResponse({"status": "criado", "id": lote.id}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_lote_aprovar(request, lote_id):
    """POST /api/farmacia/magistral/lotes-mp/<id>/aprovar — farmacêutico aprova lote."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import LoteMateriaPrima
    from django.utils import timezone

    try:
        lote = LoteMateriaPrima.objects.get(id=lote_id, empresa=empresa)
    except LoteMateriaPrima.DoesNotExist:
        return JsonResponse({"erro": "Lote não encontrado"}, status=404)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    resultado = body.get("resultado", "aprovado")
    if resultado not in ("aprovado", "rejeitado"):
        return JsonResponse({"erro": "resultado deve ser 'aprovado' ou 'rejeitado'"}, status=400)

    lote.status       = resultado
    lote.aprovado_por = (body.get("aprovado_por") or "").strip()
    lote.aprovado_em  = timezone.now()
    if body.get("laudo_coa"):
        lote.laudo_coa = body["laudo_coa"]
    lote.save()

    return JsonResponse({"status": resultado, "lote_id": lote.id})


# ── Fórmulas magistrais ───────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_formulas(request):
    """GET lista | POST cria fórmula."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import FormulaMagistral

    if request.method == "GET":
        forma   = request.GET.get("forma_farmaceutica")
        q       = (request.GET.get("q") or "").strip()
        ativos  = request.GET.get("ativos", "true").lower() == "true"

        qs = FormulaMagistral.objects.filter(empresa=empresa)
        if ativos:
            qs = qs.filter(ativo=True)
        if forma:
            qs = qs.filter(forma_farmaceutica=forma)
        if q:
            qs = qs.filter(nome__icontains=q)

        return JsonResponse({
            "total":    qs.count(),
            "formulas": [_formula_dict(f) for f in qs],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = (body.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Campo 'nome' obrigatório"}, status=400)

        formula = FormulaMagistral.objects.create(
            empresa              = empresa,
            nome                 = nome,
            forma_farmaceutica   = body.get("forma_farmaceutica") or "capsula",
            concentracao         = (body.get("concentracao") or "").strip(),
            quantidade_padrao    = body.get("quantidade_padrao") or 1,
            unidade_padrao       = (body.get("unidade_padrao") or "unid").strip(),
            prazo_validade_dias  = body.get("prazo_validade_dias") or 30,
            composicao           = body.get("composicao") or [],
            metodo_manipulacao   = (body.get("metodo_manipulacao") or "").strip(),
            controle_especial    = bool(body.get("controle_especial", False)),
        )
        return JsonResponse({"status": "criado", "id": formula.id, "formula": _formula_dict(formula)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Ordens de Manipulação ─────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_ordens(request):
    """GET lista | POST cria Ordem de Manipulação."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import OrdemManipulacao, FormulaMagistral

    if request.method == "GET":
        status    = request.GET.get("status")
        page      = max(1, int(request.GET.get("page") or 1))
        page_size = 50

        qs = OrdemManipulacao.objects.filter(empresa=empresa).select_related("formula")
        if status:
            qs = qs.filter(status=status)

        total  = qs.count()
        offset = (page - 1) * page_size
        items  = qs[offset: offset + page_size]

        return JsonResponse({
            "total":   total,
            "pagina":  page,
            "paginas": math.ceil(total / page_size) if total else 1,
            "ordens":  [_om_dict(o) for o in items],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        formula_id    = body.get("formula_id")
        paciente_nome = (body.get("paciente_nome") or "").strip()

        if not formula_id or not paciente_nome:
            return JsonResponse({"erro": "Campos 'formula_id' e 'paciente_nome' obrigatórios"}, status=400)

        try:
            formula = FormulaMagistral.objects.get(id=formula_id, empresa=empresa, ativo=True)
        except FormulaMagistral.DoesNotExist:
            return JsonResponse({"erro": "Fórmula não encontrada"}, status=404)

        # Gera número sequencial da OM
        ultimo = OrdemManipulacao.objects.filter(empresa=empresa).order_by("-id").first()
        seq    = (int(ultimo.numero_om.split("-")[-1]) + 1) if ultimo and "-" in ultimo.numero_om else 1
        numero_om = f"OM-{date.today().strftime('%Y%m')}-{seq:04d}"

        ok_cpf, erro_cpf = validar_cpf_cadastro(body.get("paciente_cpf", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)
        om = OrdemManipulacao.objects.create(
            empresa              = empresa,
            formula              = formula,
            numero_om            = numero_om,
            paciente_nome        = paciente_nome,
            paciente_cpf         = (body.get("paciente_cpf") or "").strip().replace(".", "").replace("-", ""),
            prescrito_por        = (body.get("prescrito_por") or "").strip(),
            crm_prescritor       = (body.get("crm_prescritor") or "").strip(),
            data_prescricao      = body.get("data_prescricao") or None,
            quantidade           = body.get("quantidade") or formula.quantidade_padrao,
            unidade              = body.get("unidade") or formula.unidade_padrao,
            observacoes          = (body.get("observacoes") or "").strip(),
        )
        return JsonResponse({"status": "criado", "id": om.id, "numero_om": numero_om}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_ordem_status(request, om_id):
    """PATCH /api/farmacia/magistral/ordens/<id>/status — avança o status da OM."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import OrdemManipulacao

    try:
        om = OrdemManipulacao.objects.get(id=om_id, empresa=empresa)
    except OrdemManipulacao.DoesNotExist:
        return JsonResponse({"erro": "Ordem de Manipulação não encontrada"}, status=404)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    status_validos = [s[0] for s in OrdemManipulacao.STATUS]
    novo_status    = body.get("status")
    if not novo_status or novo_status not in status_validos:
        return JsonResponse({"erro": f"Status inválido. Opções: {status_validos}"}, status=400)

    with transaction.atomic():
        # Trava a OM para evitar consumo duplicado de matéria-prima em chamadas
        # concorrentes de mudança de status.
        om = OrdemManipulacao.objects.select_for_update().get(id=om.id, empresa=empresa)

        # A baixa de matéria-prima ocorre uma única vez, na primeira entrada em
        # manipulação (guardada por data_manipulacao ainda não preenchida).
        consumir_mp = (novo_status == "em_manipulacao" and not om.data_manipulacao)

        om.status = novo_status
        if body.get("manipulado_por"):
            om.manipulado_por = body["manipulado_por"]
        if body.get("aprovado_por"):
            om.aprovado_por = body["aprovado_por"]
        if body.get("numero_lote_produto"):
            om.numero_lote_produto = body["numero_lote_produto"]
        if novo_status == "em_manipulacao" and not om.data_manipulacao:
            om.data_manipulacao = date.today()
        if novo_status in ("aprovado", "entregue") and not om.data_validade_produto:
            from datetime import timedelta
            om.data_validade_produto = date.today() + timedelta(days=om.formula.prazo_validade_dias)

        if consumir_mp:
            _consumir_materias_primas(empresa, om)

        om.save()

    return JsonResponse({"status": novo_status, "om_id": om.id, "numero_om": om.numero_om})


# ── Controle de Qualidade ─────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("farmacia.magistral")
def api_magistral_controle_qualidade(request):
    """GET lista | POST registra CQ de uma OM."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import ControleQualidadeMagistral, OrdemManipulacao

    if request.method == "GET":
        resultado = request.GET.get("resultado")
        page      = max(1, int(request.GET.get("page") or 1))
        page_size = 50

        qs = ControleQualidadeMagistral.objects.filter(empresa=empresa).select_related("ordem_manipulacao__formula")
        if resultado:
            qs = qs.filter(resultado=resultado)

        total  = qs.count()
        offset = (page - 1) * page_size
        items  = qs[offset: offset + page_size]

        return JsonResponse({
            "total":   total,
            "pagina":  page,
            "paginas": math.ceil(total / page_size) if total else 1,
            "controles": [_cq_dict(c) for c in items],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        om_id = body.get("ordem_manipulacao_id")
        if not om_id:
            return JsonResponse({"erro": "Campo 'ordem_manipulacao_id' obrigatório"}, status=400)

        try:
            om = OrdemManipulacao.objects.get(id=om_id, empresa=empresa)
        except OrdemManipulacao.DoesNotExist:
            return JsonResponse({"erro": "Ordem de Manipulação não encontrada"}, status=404)

        if ControleQualidadeMagistral.objects.filter(ordem_manipulacao=om).exists():
            return JsonResponse({"erro": "Esta OM já tem um registro de CQ"}, status=409)

        resultado = body.get("resultado") or "pendente"
        cq = ControleQualidadeMagistral.objects.create(
            ordem_manipulacao  = om,
            empresa            = empresa,
            aspecto_visual     = (body.get("aspecto_visual") or "").strip(),
            peso_medio         = body.get("peso_medio") or None,
            variacao_peso_pct  = body.get("variacao_peso_pct") or None,
            ph                 = body.get("ph") or None,
            resultado          = resultado,
            farmaceutico       = (body.get("farmaceutico") or "").strip(),
            crf_farmaceutico   = (body.get("crf_farmaceutico") or "").strip(),
            data_controle      = body.get("data_controle") or date.today().isoformat(),
            observacoes        = (body.get("observacoes") or "").strip(),
        )

        # Avança status da OM automaticamente
        if resultado == "aprovado":
            om.status      = "aprovado"
            om.aprovado_por = body.get("farmaceutico") or ""
            om.save(update_fields=["status", "aprovado_por"])
        elif resultado == "reprovado":
            om.status = "cancelado"
            om.save(update_fields=["status"])

        return JsonResponse({"status": "criado", "id": cq.id, "resultado": resultado}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── KPIs magistral ────────────────────────────────────────────────────────────

@api_requer_feature("farmacia.magistral")
def api_magistral_kpis(request):
    """GET /api/farmacia/magistral/kpis."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)

    from .models import (
        MateriaPrimaFarmacia, LoteMateriaPrima,
        FormulaMagistral, OrdemManipulacao, ControleQualidadeMagistral,
    )
    from django.db.models import Count, Q
    from datetime import timedelta

    hoje = date.today()

    mps      = MateriaPrimaFarmacia.objects.filter(empresa=empresa, ativo=True)
    lotes    = LoteMateriaPrima.objects.filter(empresa=empresa)
    formulas = FormulaMagistral.objects.filter(empresa=empresa, ativo=True)
    oms      = OrdemManipulacao.objects.filter(empresa=empresa)
    cqs      = ControleQualidadeMagistral.objects.filter(empresa=empresa)

    return JsonResponse({
        "materias_primas": {
            "total":   mps.count(),
            "criticos": sum(1 for m in mps if m.estoque_critico),
            "controlados_anvisa": mps.filter(controlado_anvisa=True).count(),
        },
        "lotes": {
            "total":          lotes.count(),
            "quarentena":     lotes.filter(status="quarentena").count(),
            "aprovados":      lotes.filter(status="aprovado").count(),
            "vencidos":       lotes.filter(status="vencido").count(),
            "vencendo_30d":   lotes.filter(status="aprovado", data_validade__lte=hoje + timedelta(days=30)).count(),
        },
        "formulas": {
            "total":            formulas.count(),
            "controle_especial": formulas.filter(controle_especial=True).count(),
        },
        "ordens_manipulacao": {
            "total":         oms.count(),
            "aguardando":    oms.filter(status="aguardando").count(),
            "em_manipulacao": oms.filter(status="em_manipulacao").count(),
            "em_controle":   oms.filter(status="controle").count(),
            "aprovadas":     oms.filter(status="aprovado").count(),
            "entregues":     oms.filter(status="entregue").count(),
        },
        "controle_qualidade": {
            "total":      cqs.count(),
            "aprovados":  cqs.filter(resultado="aprovado").count(),
            "reprovados": cqs.filter(resultado="reprovado").count(),
            "taxa_aprovacao_pct": round(
                cqs.filter(resultado="aprovado").count() / cqs.count() * 100, 1
            ) if cqs.count() > 0 else None,
        },
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mp_dict(m):
    return {
        "id":              m.id,
        "nome":            m.nome,
        "sinonimos":       m.sinonimos,
        "cas_numero":      m.cas_numero,
        "categoria":       m.categoria,
        "categoria_display": m.get_categoria_display(),
        "unidade_medida":  m.unidade_medida,
        "estoque_atual":   float(m.estoque_atual),
        "estoque_minimo":  float(m.estoque_minimo),
        "estoque_critico": m.estoque_critico,
        "fornecedor":      m.fornecedor,
        "controlado_anvisa": m.controlado_anvisa,
        "ativo":           m.ativo,
    }


def _lote_mp_dict(l):
    return {
        "id":                  l.id,
        "materia_prima_id":    l.materia_prima_id,
        "materia_prima_nome":  l.materia_prima.nome,
        "numero_lote":         l.numero_lote,
        "fornecedor":          l.fornecedor,
        "nota_fiscal":         l.nota_fiscal,
        "quantidade_inicial":  float(l.quantidade_inicial),
        "quantidade_disponivel": float(l.quantidade_disponivel),
        "data_fabricacao":     l.data_fabricacao.isoformat() if l.data_fabricacao else None,
        "data_validade":       l.data_validade.isoformat(),
        "data_entrada":        l.data_entrada.isoformat(),
        "status":              l.status,
        "aprovado_por":        l.aprovado_por,
        "vencido":             l.vencido,
    }


def _formula_dict(f):
    return {
        "id":                   f.id,
        "nome":                 f.nome,
        "forma_farmaceutica":   f.forma_farmaceutica,
        "forma_display":        f.get_forma_farmaceutica_display(),
        "concentracao":         f.concentracao,
        "quantidade_padrao":    float(f.quantidade_padrao),
        "unidade_padrao":       f.unidade_padrao,
        "prazo_validade_dias":  f.prazo_validade_dias,
        "composicao":           f.composicao,
        "metodo_manipulacao":   f.metodo_manipulacao,
        "controle_especial":    f.controle_especial,
        "versao":               f.versao,
        "ativo":                f.ativo,
    }


def _om_dict(o):
    return {
        "id":                  o.id,
        "numero_om":           o.numero_om,
        "formula_id":          o.formula_id,
        "formula_nome":        o.formula.nome if o.formula_id else "",
        "paciente_nome":       o.paciente_nome,
        "paciente_cpf":        o.paciente_cpf,
        "prescrito_por":       o.prescrito_por,
        "crm_prescritor":      o.crm_prescritor,
        "data_prescricao":     o.data_prescricao.isoformat() if o.data_prescricao else None,
        "quantidade":          float(o.quantidade),
        "unidade":             o.unidade,
        "status":              o.status,
        "data_manipulacao":    o.data_manipulacao.isoformat() if o.data_manipulacao else None,
        "data_validade_produto": o.data_validade_produto.isoformat() if o.data_validade_produto else None,
        "manipulado_por":      o.manipulado_por,
        "aprovado_por":        o.aprovado_por,
        "criado_em":           o.criado_em.isoformat(),
    }


def _cq_dict(c):
    return {
        "id":                c.id,
        "om_id":             c.ordem_manipulacao_id,
        "numero_om":         c.ordem_manipulacao.numero_om,
        "aspecto_visual":    c.aspecto_visual,
        "peso_medio":        float(c.peso_medio) if c.peso_medio else None,
        "variacao_peso_pct": float(c.variacao_peso_pct) if c.variacao_peso_pct else None,
        "ph":                float(c.ph) if c.ph else None,
        "resultado":         c.resultado,
        "farmaceutico":      c.farmaceutico,
        "crf_farmaceutico":  c.crf_farmaceutico,
        "data_controle":     c.data_controle.isoformat() if c.data_controle else None,
    }
