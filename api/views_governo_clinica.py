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

    if cns:
        prontuario = ProntuarioCidadao.objects.filter(empresa=e, cns=cns).first()
        historico = list(
            TeleconsultaGoverno.objects.filter(empresa=e, cns=cns).order_by('-data_hora')[:10]
        )

    ctx = contexto_navegacao_setorial(request, 'governo')
    ctx['prontuario'] = prontuario
    ctx['historico'] = historico
    ctx['cns'] = cns
    return render(request, 'governo_prontuario_tc.html', ctx)
