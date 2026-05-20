"""
Bem-estar do Funcionário — SST
Anônimo por padrão. A empresa só vê dados agregados.
Se o funcionário quiser contato, a empresa vê o nome.
"""
import json
from datetime import timedelta
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import CheckinBemEstar, FuncionarioSST
from .views_funcionario_portal import _autenticar_funcionario
from .views_dashboard import _empresa_autenticada
from .access_control import get_setor


# ── Funcionário: enviar check-in ────────────────────────────────────────────

@csrf_exempt
def api_funcionario_checkin(request):
    """
    POST /api/funcionario/bem-estar
    Body: {
        humor, saude_fisica, saude_mental, nivel_estresse, satisfacao_trabalho,
        mensagem (opcional),
        precisa_ajuda (bool), tipo_ajuda, quer_contato (bool)
    }
    GET /api/funcionario/bem-estar  → histórico próprio (últimos 30)
    """
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    if request.method == "GET":
        checkins = CheckinBemEstar.objects.filter(
            funcionario=func
        ).order_by("-criado_em")[:30]
        return JsonResponse({
            "checkins": [_checkin_proprio(c) for c in checkins]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        humor = data.get("humor", "")
        humores_validos = ["otimo", "bom", "regular", "ruim", "pessimo"]
        if humor not in humores_validos:
            return JsonResponse({"erro": "humor inválido"}, status=400)

        def _nota(campo, padrao=3):
            try:
                v = int(data.get(campo, padrao))
                return max(1, min(5, v))
            except (TypeError, ValueError):
                return padrao

        precisa_ajuda = bool(data.get("precisa_ajuda", False))
        quer_contato  = bool(data.get("quer_contato", False)) if precisa_ajuda else False

        checkin = CheckinBemEstar.objects.create(
            funcionario=func,
            empresa=func.empresa,
            humor=humor,
            saude_fisica=_nota("saude_fisica"),
            saude_mental=_nota("saude_mental"),
            nivel_estresse=_nota("nivel_estresse"),
            satisfacao_trabalho=_nota("satisfacao_trabalho"),
            mensagem=(data.get("mensagem") or "").strip()[:500],
            precisa_ajuda=precisa_ajuda,
            tipo_ajuda=data.get("tipo_ajuda", "") if precisa_ajuda else "",
            quer_contato=quer_contato,
        )
        return JsonResponse({"status": "ok", "id": checkin.id}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


def _checkin_proprio(c):
    """Serializa check-in para o próprio funcionário (vê tudo)."""
    return {
        "id": c.id,
        "humor": c.humor,
        "humor_label": c.get_humor_display(),
        "saude_fisica": c.saude_fisica,
        "saude_mental": c.saude_mental,
        "nivel_estresse": c.nivel_estresse,
        "satisfacao_trabalho": c.satisfacao_trabalho,
        "mensagem": c.mensagem,
        "precisa_ajuda": c.precisa_ajuda,
        "tipo_ajuda": c.tipo_ajuda,
        "tipo_ajuda_label": c.get_tipo_ajuda_display() if c.tipo_ajuda else "",
        "quer_contato": c.quer_contato,
        "criado_em": c.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ── Empresa: dashboard agregado ─────────────────────────────────────────────

def api_empresa_bem_estar_resumo(request):
    """
    GET /api/sst/bem-estar/resumo?dias=30
    Retorna dados agregados — NUNCA expõe nomes (exceto pedidos de contato).
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autorizado"}, status=401)
    if get_setor(empresa) != "empresa":
        return JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)

    dias = int(request.GET.get("dias", 30))
    desde = timezone.now() - timedelta(days=dias)
    qs = CheckinBemEstar.objects.filter(empresa=empresa, criado_em__gte=desde)

    total = qs.count()
    if total == 0:
        return JsonResponse({
            "total": 0,
            "medias": {},
            "humor_distribuicao": [],
            "pedidos_contato": [],
            "alertas": [],
        })

    medias = qs.aggregate(
        media_saude_fisica=Avg("saude_fisica"),
        media_saude_mental=Avg("saude_mental"),
        media_estresse=Avg("nivel_estresse"),
        media_satisfacao=Avg("satisfacao_trabalho"),
    )

    # distribuição de humor
    humor_dist = (
        qs.values("humor")
        .annotate(qtd=Count("id"))
        .order_by("humor")
    )
    humor_labels = dict(CheckinBemEstar.HUMOR)

    # alertas — funcionários em estado crítico nos últimos 7 dias
    # (dados anonimizados — apenas contagem por tipo)
    desde_7d = timezone.now() - timedelta(days=7)
    qs_7d = CheckinBemEstar.objects.filter(empresa=empresa, criado_em__gte=desde_7d)
    alertas = []
    criticos = qs_7d.filter(humor__in=["ruim", "pessimo"]).count()
    estresse_alto = qs_7d.filter(nivel_estresse__gte=4).count()
    saude_mental_baixa = qs_7d.filter(saude_mental__lte=2).count()
    if criticos:
        alertas.append({"tipo": "humor_critico", "qtd": criticos,
                        "mensagem": f"{criticos} check-in(s) com humor ruim/péssimo nos últimos 7 dias"})
    if estresse_alto:
        alertas.append({"tipo": "estresse_alto", "qtd": estresse_alto,
                        "mensagem": f"{estresse_alto} relato(s) de estresse alto nos últimos 7 dias"})
    if saude_mental_baixa:
        alertas.append({"tipo": "saude_mental", "qtd": saude_mental_baixa,
                        "mensagem": f"{saude_mental_baixa} relato(s) de saúde mental baixa nos últimos 7 dias"})

    # pedidos de contato — ÚNICO caso onde o nome aparece (consentimento explícito)
    pedidos = (
        CheckinBemEstar.objects
        .filter(empresa=empresa, quer_contato=True, contato_resolvido=False)
        .select_related("funcionario")
        .order_by("-criado_em")
    )
    pedidos_lista = [
        {
            "id": p.id,
            "nome": p.funcionario.nome,
            "cargo": p.funcionario.cargo,
            "tipo_ajuda": p.get_tipo_ajuda_display(),
            "mensagem": p.mensagem,
            "data": p.criado_em.strftime("%d/%m/%Y"),
        }
        for p in pedidos
    ]

    return JsonResponse({
        "total": total,
        "periodo_dias": dias,
        "medias": {
            "saude_fisica": round(medias["media_saude_fisica"] or 0, 1),
            "saude_mental": round(medias["media_saude_mental"] or 0, 1),
            "nivel_estresse": round(medias["media_estresse"] or 0, 1),
            "satisfacao_trabalho": round(medias["media_satisfacao"] or 0, 1),
        },
        "humor_distribuicao": [
            {"humor": h["humor"], "label": humor_labels.get(h["humor"], h["humor"]), "qtd": h["qtd"]}
            for h in humor_dist
        ],
        "alertas": alertas,
        "pedidos_contato": pedidos_lista,
    })


@csrf_exempt
def api_empresa_bem_estar_contato_resolvido(request, checkin_id):
    """PATCH /api/sst/bem-estar/<id>/resolvido — empresa marca contato como atendido."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autorizado"}, status=401)
    if get_setor(empresa) != "empresa":
        return JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)
    try:
        checkin = CheckinBemEstar.objects.get(id=checkin_id, empresa=empresa)
    except CheckinBemEstar.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    checkin.contato_resolvido = True
    checkin.save(update_fields=["contato_resolvido"])
    return JsonResponse({"status": "ok"})
