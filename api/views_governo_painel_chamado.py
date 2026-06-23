"""
views_governo_painel_chamado.py
Painel Eletrônico de Chamado — fila de senhas para UBS/UPA (Governo).
"""
import json

from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    get_setor, principal_pode_operacao_setorial,
    requer_setor, requer_operacao_page, requer_permissao_modulo,
    api_requer_permissao_modulo,
)
from .models import SenhaAtendimento, EmpresaUnidade
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


def _e(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa or get_setor(empresa) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


def _hoje_local():
    """Data do dia operacional, no horário local (settings.TIME_ZONE) — não em UTC,
    para a virada da fila de senhas bater com a meia-noite real da unidade."""
    return timezone.localtime(timezone.now()).date()


# ── Page view ─────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("governo")
@requer_operacao_page
@requer_permissao_modulo("governo.atencao_clinica")
def governo_painel_chamado_page(request):
    return render(request, "governo_painel_chamado.html", contexto_navegacao_setorial(request, "governo"))


# ── Geração de senha ──────────────────────────────────────────────────────────

@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_painel_gerar_senha(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    tipo = data.get("tipo", "normal")
    if tipo not in ("normal", "prioritario"):
        return JsonResponse({"erro": "tipo inválido"}, status=400)
    unidade_id = data.get("unidade_id")
    unidade = None
    if unidade_id:
        unidade = EmpresaUnidade.objects.filter(pk=unidade_id, empresa=e).first()

    hoje = _hoje_local()
    prefixo = "P" if tipo == "prioritario" else "N"
    ultimo = SenhaAtendimento.objects.filter(
        empresa=e, unidade=unidade, prefixo=prefixo, criado_em__date=hoje
    ).aggregate(Max("numero"))["numero__max"] or 0

    senha = SenhaAtendimento.objects.create(
        empresa=e, unidade=unidade, numero=ultimo + 1, prefixo=prefixo, tipo=tipo,
        paciente_nome=data.get("paciente_nome", ""),
    )
    return JsonResponse({"id": senha.id, "senha": f"{senha.prefixo}{senha.numero:03d}"}, status=201)


# ── Chamar próxima ────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_painel_chamar_proxima(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    data = json.loads(request.body or "{}")
    guiche = data.get("guiche", "")
    unidade_id = data.get("unidade_id")

    hoje = _hoje_local()
    qs = SenhaAtendimento.objects.filter(empresa=e, criado_em__date=hoje, status="aguardando")
    if unidade_id:
        qs = qs.filter(unidade_id=unidade_id)
    # prioritário primeiro, depois ordem de chegada
    proxima = qs.order_by("-tipo", "criado_em").first()
    if not proxima:
        return JsonResponse({"erro": "Nenhuma senha aguardando"}, status=404)

    proxima.status = "chamado"
    proxima.guiche = guiche
    proxima.chamado_em = timezone.now()
    proxima.save(update_fields=["status", "guiche", "chamado_em"])
    return JsonResponse(_senha_dict(proxima))


@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_painel_finalizar_senha(request, senha_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        senha = SenhaAtendimento.objects.get(pk=senha_id, empresa=e)
    except SenhaAtendimento.DoesNotExist:
        return JsonResponse({"erro": "Senha não encontrada"}, status=404)
    senha.status = "atendido"
    senha.atendido_em = timezone.now()
    senha.save(update_fields=["status", "atendido_em"])
    return JsonResponse(_senha_dict(senha))


# ── Status / painel ───────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_permissao_modulo("governo.atencao_clinica")
def api_painel_status(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    hoje = _hoje_local()
    qs = SenhaAtendimento.objects.filter(empresa=e, criado_em__date=hoje)
    unidade_id = request.GET.get("unidade_id")
    if unidade_id:
        qs = qs.filter(unidade_id=unidade_id)

    chamada_atual = qs.filter(status="chamado").order_by("-chamado_em").first()
    aguardando = qs.filter(status="aguardando").order_by("-tipo", "criado_em")
    ultimas_chamadas = qs.filter(status__in=["chamado", "atendido"]).order_by("-chamado_em")[:5]

    return JsonResponse({
        "chamada_atual": _senha_dict(chamada_atual) if chamada_atual else None,
        "total_aguardando": aguardando.count(),
        "fila": [_senha_dict(s) for s in aguardando[:20]],
        "ultimas_chamadas": [_senha_dict(s) for s in ultimas_chamadas],
    })


def _senha_dict(s):
    return {
        "id": s.id,
        "senha": f"{s.prefixo}{s.numero:03d}",
        "tipo": s.tipo,
        "status": s.status,
        "guiche": s.guiche,
        "paciente_nome": s.paciente_nome,
        "criado_em": s.criado_em.isoformat(),
        "chamado_em": s.chamado_em.isoformat() if s.chamado_em else None,
    }
