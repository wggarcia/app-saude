"""
views_governo_clinica.py
Documentos clínicos da teleconsulta governo: receita, atestado, solicitação de exame e prontuário.
"""
import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .access_control import api_requer_permissao_modulo
from .models import DocumentoClinicoGov, ProntuarioCidadao, TeleconsultaGoverno
from .views_dashboard import contexto_navegacao_setorial
from .views_governo_teleconsulta import _e

logger = logging.getLogger(__name__)


# ── Receita Médica ────────────────────────────────────────────────────────────

def governo_prescricao_nova(request):
    e = _e(request)
    if e is None:
        return redirect('/governo/teleconsulta/')

    tc = None
    tc_id = request.GET.get('tc')
    if tc_id:
        tc = get_object_or_404(TeleconsultaGoverno, pk=tc_id, empresa=e)

    ctx = contexto_navegacao_setorial(request, 'governo')
    ctx['tc'] = tc
    return render(request, 'governo_prescricao.html', ctx)


@csrf_exempt
@require_http_methods(['POST'])
@api_requer_permissao_modulo('governo.atencao_clinica')
def api_governo_prescricao_salvar(request):
    e = _e(request)
    if e is None:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    tc = None
    tc_id = body.get('teleconsulta_id')
    if tc_id:
        try:
            tc = TeleconsultaGoverno.objects.get(pk=tc_id, empresa=e)
        except TeleconsultaGoverno.DoesNotExist:
            pass

    doc = DocumentoClinicoGov.objects.create(
        empresa=e,
        teleconsulta=tc,
        tipo='receita',
        paciente_nome=body.get('paciente_nome', ''),
        cns=body.get('cns', ''),
        profissional=body.get('profissional', ''),
        dados=body,
    )
    return JsonResponse({'id': doc.id, 'ok': True})


# ── Atestado Médico ───────────────────────────────────────────────────────────

def governo_atestado_novo(request):
    e = _e(request)
    if e is None:
        return redirect('/governo/teleconsulta/')

    tc = None
    tc_id = request.GET.get('tc')
    if tc_id:
        tc = get_object_or_404(TeleconsultaGoverno, pk=tc_id, empresa=e)

    ctx = contexto_navegacao_setorial(request, 'governo')
    ctx['tc'] = tc
    return render(request, 'governo_atestado.html', ctx)


@csrf_exempt
@require_http_methods(['POST'])
@api_requer_permissao_modulo('governo.atencao_clinica')
def api_governo_atestado_salvar(request):
    e = _e(request)
    if e is None:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    tc = None
    tc_id = body.get('teleconsulta_id')
    if tc_id:
        try:
            tc = TeleconsultaGoverno.objects.get(pk=tc_id, empresa=e)
        except TeleconsultaGoverno.DoesNotExist:
            pass

    doc = DocumentoClinicoGov.objects.create(
        empresa=e,
        teleconsulta=tc,
        tipo='atestado',
        paciente_nome=body.get('paciente_nome', ''),
        cns=body.get('cns', ''),
        profissional=body.get('profissional', ''),
        dados=body,
    )
    return JsonResponse({'id': doc.id, 'ok': True})


# ── Solicitação de Exame ──────────────────────────────────────────────────────

def governo_exame_novo(request):
    e = _e(request)
    if e is None:
        return redirect('/governo/teleconsulta/')

    tc = None
    tc_id = request.GET.get('tc')
    if tc_id:
        tc = get_object_or_404(TeleconsultaGoverno, pk=tc_id, empresa=e)

    ctx = contexto_navegacao_setorial(request, 'governo')
    ctx['tc'] = tc
    return render(request, 'governo_exame.html', ctx)


@csrf_exempt
@require_http_methods(['POST'])
@api_requer_permissao_modulo('governo.atencao_clinica')
def api_governo_exame_salvar(request):
    e = _e(request)
    if e is None:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    tc = None
    tc_id = body.get('teleconsulta_id')
    if tc_id:
        try:
            tc = TeleconsultaGoverno.objects.get(pk=tc_id, empresa=e)
        except TeleconsultaGoverno.DoesNotExist:
            pass

    doc = DocumentoClinicoGov.objects.create(
        empresa=e,
        teleconsulta=tc,
        tipo='exame',
        paciente_nome=body.get('paciente_nome', ''),
        cns=body.get('cns', ''),
        profissional=body.get('profissional', ''),
        dados=body,
    )
    return JsonResponse({'id': doc.id, 'ok': True})


# ── Prontuário ────────────────────────────────────────────────────────────────

def governo_prontuario_page(request):
    e = _e(request)
    if e is None:
        return redirect('/governo/teleconsulta/')

    cns = request.GET.get('cns', '').strip()
    prontuario = None
    historico = []
    evolucoes = []

    if cns:
        prontuario = ProntuarioCidadao.objects.filter(empresa=e, cns=cns).first()
        historico = list(
            TeleconsultaGoverno.objects.filter(empresa=e, cns=cns).order_by('-data_hora')[:10]
        )
        evolucoes = list(
            DocumentoClinicoGov.objects.filter(empresa=e, cns=cns, tipo='evolucao').order_by('-criado_em')[:20]
        )

    ctx = contexto_navegacao_setorial(request, 'governo')
    ctx['prontuario'] = prontuario
    ctx['historico'] = historico
    ctx['evolucoes'] = evolucoes
    ctx['cns'] = cns
    return render(request, 'governo_prontuario_tc.html', ctx)


@csrf_exempt
@require_http_methods(['POST'])
@api_requer_permissao_modulo('governo.atencao_clinica')
def api_governo_evolucao_salvar(request):
    """Persiste uma anotação/evolução clínica no prontuário do cidadão (governo)."""
    e = _e(request)
    if e is None:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    texto = (body.get('texto') or '').strip()
    cns = (body.get('cns') or '').strip()
    if not texto:
        return JsonResponse({'erro': 'Texto obrigatório'}, status=400)

    paciente_nome = ''
    if cns:
        pront = ProntuarioCidadao.objects.filter(empresa=e, cns=cns).first()
        if pront:
            paciente_nome = pront.nome_completo

    profissional = (body.get('profissional') or '').strip()
    if not profissional:
        principal = getattr(request, 'principal', None)
        if principal is not None:
            profissional = getattr(principal, 'nome', '') or ''

    doc = DocumentoClinicoGov.objects.create(
        empresa=e,
        tipo='evolucao',
        paciente_nome=paciente_nome,
        cns=cns,
        profissional=profissional,
        dados={'texto': texto},
    )
    return JsonResponse({
        'id': doc.id,
        'ok': True,
        'criado_em': doc.criado_em.strftime('%d/%m/%Y %H:%M'),
        'profissional': profissional,
        'texto': texto,
    })
