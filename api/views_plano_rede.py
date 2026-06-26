"""
Plano de Saúde — Rede Credenciada (Gestão).
CRUD de prestadores credenciados: hospital, clínica, laboratório, imagem, odonto.
"""
import json
from datetime import date, timedelta

from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Count

from .access_control import api_requer_gerencia, contexto_navegacao_setorial, requer_setor, requer_operacao_page, requer_permissao_modulo
from .models import RedeCredenciadaPlano
from .views_dashboard import _empresa_autenticada
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie


# ── helpers ──────────────────────────────────────────────────────────────────

def _ps_auth(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return empresa, None


def _rede_dict(r):
    return {
        "id": r.id,
        "nome": r.nome,
        "tipo": r.tipo,
        "tipo_label": dict(RedeCredenciadaPlano.TIPO_CHOICES).get(r.tipo, r.tipo),
        "cnpj": r.cnpj,
        "cnes": r.cnes,
        "cidade": r.cidade,
        "uf": r.uf,
        "especialidades": r.especialidades,
        "tabela_preco": r.tabela_preco,
        "ativo": r.ativo,
        "contrato_vigente_ate": r.contrato_vigente_ate.strftime("%Y-%m-%d") if r.contrato_vigente_ate else None,
        "vencimento_proximo": (
            r.contrato_vigente_ate is not None and
            r.contrato_vigente_ate <= date.today() + timedelta(days=30)
        ),
        "criado_em": r.criado_em.strftime("%d/%m/%Y"),
    }


# ── page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.rede_credenciada")
def plano_rede_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        from django.shortcuts import redirect
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_rede_credenciada_gestao.html", ctx)


# ── API: rede lista ───────────────────────────────────────────────────────────

@csrf_exempt
def api_plano_rede_lista(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "GET":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    qs = RedeCredenciadaPlano.objects.filter(empresa=empresa)

    tipo = request.GET.get("tipo")
    if tipo:
        qs = qs.filter(tipo=tipo)

    uf = request.GET.get("uf")
    if uf:
        qs = qs.filter(uf__iexact=uf)

    ativo = request.GET.get("ativo")
    if ativo is not None and ativo != "":
        qs = qs.filter(ativo=(ativo in ("1", "true", "True")))

    busca = request.GET.get("q", "").strip()
    if busca:
        qs = qs.filter(nome__icontains=busca)

    try:
        limit = min(max(int(request.GET.get("limit", 50)), 1), 500)
        offset = max(int(request.GET.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 50, 0

    total = qs.count()
    return JsonResponse({
        "rede": [_rede_dict(r) for r in qs.order_by("nome")[offset: offset + limit]],
        "total": total, "limit": limit, "offset": offset,
        "has_more": (offset + limit) < total,
    })


@csrf_exempt
def api_plano_rede_novo(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    if request.method != "POST":
        return JsonResponse({"erro": "Método não suportado"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    nome = (data.get("nome") or "").strip()
    if not nome:
        return JsonResponse({"erro": "nome obrigatório"}, status=400)

    contrato_ate = None
    raw_contrato = data.get("contrato_vigente_ate")
    if raw_contrato:
        try:
            from datetime import datetime
            contrato_ate = datetime.strptime(raw_contrato, "%Y-%m-%d").date()
        except ValueError:
            pass

    especialidades = data.get("especialidades", [])
    if isinstance(especialidades, str):
        especialidades = [e.strip() for e in especialidades.split(",") if e.strip()]

    r = RedeCredenciadaPlano.objects.create(
        empresa=empresa,
        nome=nome,
        tipo=data.get("tipo", "clinica"),
        cnpj=data.get("cnpj", ""),
        cnes=data.get("cnes", ""),
        cidade=data.get("cidade", ""),
        uf=(data.get("uf") or "").upper()[:2],
        especialidades=especialidades,
        tabela_preco=data.get("tabela_preco", ""),
        ativo=bool(data.get("ativo", True)),
        contrato_vigente_ate=contrato_ate,
    )
    return JsonResponse({"rede": _rede_dict(r)}, status=201)


# ── API: rede detalhe ─────────────────────────────────────────────────────────

@csrf_exempt
def api_plano_rede_detalhe(request, rede_id):
    empresa, err = _ps_auth(request)
    if err:
        return err

    try:
        r = RedeCredenciadaPlano.objects.get(id=rede_id, empresa=empresa)
    except RedeCredenciadaPlano.DoesNotExist:
        return JsonResponse({"erro": "Credenciado não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"rede": _rede_dict(r)})

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for field in ("nome", "tipo", "cnpj", "cnes", "cidade", "tabela_preco"):
            if field in data:
                setattr(r, field, data[field])
        if "uf" in data:
            r.uf = (data["uf"] or "").upper()[:2]
        if "ativo" in data:
            r.ativo = bool(data["ativo"])
        if "especialidades" in data:
            esp = data["especialidades"]
            if isinstance(esp, str):
                esp = [e.strip() for e in esp.split(",") if e.strip()]
            r.especialidades = esp
        if "contrato_vigente_ate" in data and data["contrato_vigente_ate"]:
            try:
                from datetime import datetime
                r.contrato_vigente_ate = datetime.strptime(data["contrato_vigente_ate"], "%Y-%m-%d").date()
            except ValueError:
                pass
        r.save()
        return JsonResponse({"rede": _rede_dict(r)})

    if request.method == "DELETE":
        r.delete()
        return JsonResponse({"status": "ok"})

    return JsonResponse({"erro": "Método não suportado"}, status=405)


# ── API: KPIs ─────────────────────────────────────────────────────────────────

def api_plano_rede_kpis(request):
    empresa, err = _ps_auth(request)
    if err:
        return err

    qs = RedeCredenciadaPlano.objects.filter(empresa=empresa)
    total = qs.count()
    ativos = qs.filter(ativo=True).count()

    # Por tipo
    por_tipo = {}
    for tipo, label in RedeCredenciadaPlano.TIPO_CHOICES:
        por_tipo[tipo] = {"label": label, "total": qs.filter(tipo=tipo).count()}

    # Contratos vencendo em 30 dias
    hoje = date.today()
    limite = hoje + timedelta(days=30)
    vencendo = qs.filter(
        ativo=True,
        contrato_vigente_ate__lte=limite,
        contrato_vigente_ate__gte=hoje,
    ).count()
    vencidos = qs.filter(
        ativo=True,
        contrato_vigente_ate__lt=hoje,
    ).count()

    return JsonResponse({
        "total_credenciados": total,
        "ativos": ativos,
        "por_tipo": por_tipo,
        "contratos_vencendo_30d": vencendo,
        "contratos_vencidos": vencidos,
    })
