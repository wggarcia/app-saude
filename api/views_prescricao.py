"""
Views para prescrições médicas (Hospital) e Atos Normativos (Governo).
"""
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import PrescricaoMedica, InternacaoHospital, AtoNormativoGov
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base
from .access_control import get_setor


def _get_empresa_hospital(req):
    empresa = _empresa_autenticada_base(req)
    if empresa and get_setor(empresa) not in ('hospital',):
        return None
    return empresa


def _get_empresa_governo(req):
    empresa = _empresa_autenticada_base(req)
    if empresa and get_setor(empresa) not in ('governo',):
        return None
    return empresa


# ─── Prescrições Médicas ───────────────────────────────────────────────────────

def _prescricao_to_dict(p):
    return {
        "id": p.id,
        "internacao_id": p.internacao_id,
        "paciente_nome": p.internacao.paciente.nome if p.internacao.paciente else "—",
        "medicamento": p.medicamento,
        "dose": p.dose,
        "via": p.via,
        "via_label": p.get_via_display(),
        "frequencia": p.frequencia,
        "duracao_dias": p.duracao_dias,
        "status": p.status,
        "status_label": p.get_status_display(),
        "medico": p.medico,
        "observacoes": p.observacoes,
        "criado_em": p.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
def api_prescricoes_internacao(request, internacao_id):
    """GET prescriptions for an internação / POST new prescription."""
    empresa = _get_empresa_hospital(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        internacao = InternacaoHospital.objects.get(
            id=internacao_id,
            leito__departamento__empresa=empresa
        )
    except InternacaoHospital.DoesNotExist:
        return JsonResponse({"erro": "Internação não encontrada"}, status=404)

    if request.method == "GET":
        qs = internacao.prescricoes.all()
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({"prescricoes": [_prescricao_to_dict(p) for p in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        if not data.get("medicamento"):
            return JsonResponse({"erro": "medicamento obrigatório"}, status=400)

        p = PrescricaoMedica.objects.create(
            internacao=internacao,
            medicamento=data["medicamento"],
            dose=data.get("dose", ""),
            via=data.get("via", "oral"),
            frequencia=data.get("frequencia", ""),
            duracao_dias=data.get("duracao_dias") or None,
            status="ativa",
            medico=data.get("medico", ""),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"prescricao": _prescricao_to_dict(p)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_prescricao_status(request, prescricao_id):
    """PUT status of a prescription."""
    empresa = _get_empresa_hospital(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        p = PrescricaoMedica.objects.get(
            id=prescricao_id,
            internacao__leito__departamento__empresa=empresa
        )
    except PrescricaoMedica.DoesNotExist:
        return JsonResponse({"erro": "Prescrição não encontrada"}, status=404)

    data = json.loads(request.body)
    novo_status = data.get("status")
    validos = ["ativa", "suspensa", "concluida", "cancelada"]
    if novo_status not in validos:
        return JsonResponse({"erro": f"Status inválido. Use: {validos}"}, status=400)

    p.status = novo_status
    p.save()
    return JsonResponse({"prescricao": _prescricao_to_dict(p)})


# ─── Atos Normativos (Governo) ─────────────────────────────────────────────────

def _ato_to_dict(a):
    return {
        "id": a.id,
        "tipo": a.tipo,
        "tipo_label": a.get_tipo_display(),
        "numero": a.numero,
        "titulo": a.titulo,
        "ementa": a.ementa,
        "data_publicacao": str(a.data_publicacao) if a.data_publicacao else None,
        "data_vigencia": str(a.data_vigencia) if a.data_vigencia else None,
        "status": a.status,
        "status_label": a.get_status_display(),
        "orgao_emissor": a.orgao_emissor,
        "url_documento": a.url_documento,
        "programa_id": a.programa_id,
        "programa_nome": a.programa.nome if a.programa else None,
        "criado_em": a.criado_em.strftime("%d/%m/%Y"),
    }


@csrf_exempt
def api_atos_normativos(request):
    """GET list / POST create atos normativos governamentais."""
    empresa = _get_empresa_governo(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = AtoNormativoGov.objects.filter(empresa=empresa).select_related("programa")
        tipo_f   = request.GET.get("tipo")
        status_f = request.GET.get("status")
        if tipo_f:   qs = qs.filter(tipo=tipo_f)
        if status_f: qs = qs.filter(status=status_f)
        q = request.GET.get("q")
        if q:
            qs = qs.filter(titulo__icontains=q) | qs.filter(numero__icontains=q)
        return JsonResponse({"atos": [_ato_to_dict(a) for a in qs]})

    elif request.method == "POST":
        data = json.loads(request.body)
        if not data.get("titulo"):
            return JsonResponse({"erro": "titulo obrigatório"}, status=400)

        from .models import ProgramaSaudeGov
        programa = None
        if data.get("programa_id"):
            try:
                programa = ProgramaSaudeGov.objects.get(id=data["programa_id"], empresa=empresa)
            except ProgramaSaudeGov.DoesNotExist:
                pass

        ato = AtoNormativoGov.objects.create(
            empresa=empresa,
            tipo=data.get("tipo", "portaria"),
            numero=data.get("numero", ""),
            titulo=data["titulo"],
            ementa=data.get("ementa", ""),
            data_publicacao=data.get("data_publicacao") or None,
            data_vigencia=data.get("data_vigencia") or None,
            status=data.get("status", "vigente"),
            orgao_emissor=data.get("orgao_emissor", ""),
            url_documento=data.get("url_documento", ""),
            programa=programa,
        )
        return JsonResponse({"ato": _ato_to_dict(ato)}, status=201)

    return JsonResponse({"erro": "Método não suportado"}, status=405)


@csrf_exempt
def api_ato_normativo_detalhe(request, ato_id):
    """GET / PUT / DELETE ato normativo."""
    empresa = _get_empresa_governo(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        ato = AtoNormativoGov.objects.get(id=ato_id, empresa=empresa)
    except AtoNormativoGov.DoesNotExist:
        return JsonResponse({"erro": "Ato não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"ato": _ato_to_dict(ato)})

    elif request.method in ("PUT", "PATCH"):
        data = json.loads(request.body)
        for field in ("tipo", "numero", "titulo", "ementa", "status", "orgao_emissor", "url_documento"):
            if field in data:
                setattr(ato, field, data[field])
        for date_field in ("data_publicacao", "data_vigencia"):
            if date_field in data:
                setattr(ato, date_field, data[date_field] or None)
        if "programa_id" in data:
            from .models import ProgramaSaudeGov
            try:
                ato.programa = ProgramaSaudeGov.objects.get(id=data["programa_id"], empresa=empresa)
            except ProgramaSaudeGov.DoesNotExist:
                ato.programa = None
        ato.save()
        return JsonResponse({"ato": _ato_to_dict(ato)})

    elif request.method == "DELETE":
        ato.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não suportado"}, status=405)
