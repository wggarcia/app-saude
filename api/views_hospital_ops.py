import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import (
    DepartamentoHospital, LeitoHospital, PacienteHospital,
    TriagemHospital, InternacaoHospital, EvolucaoClinica,
)
from .views_dashboard import _empresa_autenticada
from .access_control import (
    api_requer_operacao_ou_gerencia,
    api_requer_setor,
    get_setor,
    principal_pode_operacao_setorial,
)


def _e(req):
    empresa = _empresa_autenticada(req)
    if empresa and get_setor(empresa) not in ('hospital',):
        return None  # Block non-hospital empresas
    if empresa and not principal_pode_operacao_setorial(req):
        return None
    return empresa


# ── Departamentos ──────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_departamentos_hospital(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = DepartamentoHospital.objects.filter(empresa=e)
        return JsonResponse({"departamentos": [
            {"id": d.id, "nome": d.nome, "tipo": d.tipo,
             "capacidade_leitos": d.capacidade_leitos,
             "responsavel": d.responsavel, "ativo": d.ativo}
            for d in qs
        ]})
    data = json.loads(request.body or "{}")
    d = DepartamentoHospital.objects.create(
        empresa=e,
        nome=data.get("nome", ""),
        tipo=data.get("tipo", ""),
        responsavel=data.get("responsavel", ""),
        capacidade_leitos=int(data.get("capacidade_leitos", 0)),
    )
    return JsonResponse({"id": d.id, "nome": d.nome}, status=201)


@require_http_methods(["PUT", "DELETE"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_departamento_hospital_detalhe(request, dep_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        d = DepartamentoHospital.objects.get(pk=dep_id, empresa=e)
    except DepartamentoHospital.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "DELETE":
        d.delete()
        return JsonResponse({"ok": True})
    data = json.loads(request.body or "{}")
    for campo in ["nome", "tipo", "capacidade_leitos", "responsavel", "ativo"]:
        if campo in data:
            setattr(d, campo, data[campo])
    d.save()
    return JsonResponse({"ok": True})


# ── Leitos ─────────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_leitos_hospital(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        dep_id = request.GET.get("departamento_id")
        qs = LeitoHospital.objects.filter(empresa=e).select_related("departamento")
        if dep_id:
            qs = qs.filter(departamento_id=dep_id)
        # Enrich leitos with active internação data (paciente_nome, hora_entrada)
        leito_ids = [l.id for l in qs]
        internacoes_ativas = {
            i.leito_id: i
            for i in InternacaoHospital.objects.filter(
                leito_id__in=leito_ids, status="ativa"
            ).select_related("paciente")
        }
        return JsonResponse({"leitos": [
            {"id": l.id, "numero": l.numero, "tipo": l.tipo,
             "status": l.status, "departamento_id": l.departamento_id,
             "departamento_nome": l.departamento.nome,
             "paciente_nome": internacoes_ativas[l.id].paciente.nome if l.id in internacoes_ativas else None,
             "hora_entrada": internacoes_ativas[l.id].data_entrada.isoformat() if l.id in internacoes_ativas else None}
            for l in qs
        ]})
    data = json.loads(request.body or "{}")
    try:
        dep = DepartamentoHospital.objects.get(pk=data["departamento_id"], empresa=e)
    except (KeyError, DepartamentoHospital.DoesNotExist):
        return JsonResponse({"erro": "Departamento não encontrado"}, status=404)
    l = LeitoHospital.objects.create(
        empresa=e, departamento=dep,
        numero=data.get("numero", ""),
        tipo=data.get("tipo", ""),
    )
    return JsonResponse({"id": l.id, "numero": l.numero}, status=201)


@require_http_methods(["PUT"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_leito_status(request, leito_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        l = LeitoHospital.objects.get(pk=leito_id, empresa=e)
    except LeitoHospital.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    l.status = data.get("status", l.status)
    l.save()
    return JsonResponse({"ok": True})


# ── Pacientes ──────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_pacientes_hospital(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        q = request.GET.get("q", "")
        qs = PacienteHospital.objects.filter(empresa=e)
        if q:
            qs = qs.filter(nome__icontains=q)
        return JsonResponse({"pacientes": [
            {"id": p.id, "nome": p.nome, "cpf": p.cpf,
             "telefone": p.telefone,
             "data_nascimento": str(p.data_nascimento) if p.data_nascimento else "",
             "sexo": p.sexo, "tipo_sanguineo": p.tipo_sanguineo,
             "alergias": p.alergias}
            for p in qs[:100]
        ]})
    data = json.loads(request.body or "{}")
    p = PacienteHospital.objects.create(
        empresa=e,
        nome=data.get("nome", ""),
        cpf=data.get("cpf", ""),
        data_nascimento=data.get("data_nascimento") or None,
        sexo=data.get("sexo", ""),
        telefone=data.get("telefone", ""),
        endereco=data.get("endereco", ""),
        tipo_sanguineo=data.get("tipo_sanguineo", ""),
        alergias=data.get("alergias", ""),
    )
    return JsonResponse({"id": p.id, "nome": p.nome}, status=201)


# ── Triagem ────────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_triagens_hospital(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = TriagemHospital.objects.filter(empresa=e).select_related("paciente")[:100]
        return JsonResponse({"triagens": [
            {"id": t.id, "paciente_id": t.paciente_id,
             "paciente_nome": t.paciente.nome,
             "prioridade": t.prioridade,
             "queixa_principal": t.queixa_principal,
             "pressao_arterial": t.pressao_arterial,
             "temperatura": str(t.temperatura) if t.temperatura else "",
             "saturacao": t.saturacao,
             "frequencia_cardiaca": t.frequencia_cardiaca,
             "responsavel": t.responsavel,
             "triado_em": t.triado_em.isoformat()}
            for t in qs
        ]})
    data = json.loads(request.body or "{}")
    try:
        pac = PacienteHospital.objects.get(pk=data["paciente_id"], empresa=e)
    except (KeyError, PacienteHospital.DoesNotExist):
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)
    t = TriagemHospital.objects.create(
        empresa=e, paciente=pac,
        prioridade=data.get("prioridade", "verde"),
        queixa_principal=data.get("queixa_principal", ""),
        pressao_arterial=data.get("pressao_arterial", ""),
        temperatura=data.get("temperatura") or None,
        saturacao=data.get("saturacao") or None,
        frequencia_cardiaca=data.get("frequencia_cardiaca") or None,
        responsavel=data.get("responsavel", ""),
    )
    return JsonResponse({"id": t.id}, status=201)


# ── Internações ────────────────────────────────────────────────────────────────
@require_http_methods(["GET", "POST"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_internacoes_hospital(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if request.method == "GET":
        qs = InternacaoHospital.objects.filter(empresa=e).select_related(
            "paciente", "leito", "leito__departamento"
        )
        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({"internacoes": [
            {"id": i.id, "paciente_id": i.paciente_id,
             "paciente_nome": i.paciente.nome,
             "leito_id": i.leito_id,
             "leito_numero": i.leito.numero if i.leito else "",
             "departamento_nome": i.leito.departamento.nome if i.leito else "",
             "diagnostico": i.diagnostico,
             "medico_responsavel": i.medico_responsavel,
             "status": i.status,
             "data_entrada": i.data_entrada.isoformat(),
             "data_saida": i.data_saida.isoformat() if i.data_saida else ""}
            for i in qs
        ]})
    data = json.loads(request.body or "{}")
    try:
        pac = PacienteHospital.objects.get(pk=data["paciente_id"], empresa=e)
    except (KeyError, PacienteHospital.DoesNotExist):
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)
    leito = None
    if data.get("leito_id"):
        try:
            leito = LeitoHospital.objects.get(pk=data["leito_id"], empresa=e)
            leito.status = "ocupado"
            leito.save()
        except LeitoHospital.DoesNotExist:
            pass
    i = InternacaoHospital.objects.create(
        empresa=e, paciente=pac, leito=leito,
        diagnostico=data.get("diagnostico", ""),
        medico_responsavel=data.get("medico_responsavel", ""),
    )
    return JsonResponse({"id": i.id}, status=201)


@require_http_methods(["PUT"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_internacao_status(request, internacao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        i = InternacaoHospital.objects.get(pk=internacao_id, empresa=e)
    except InternacaoHospital.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    data = json.loads(request.body or "{}")
    i.status = data.get("status", i.status)
    if i.status in ("alta", "transferido", "obito") and not i.data_saida:
        i.data_saida = timezone.now()
        if i.leito:
            i.leito.status = "disponivel"
            i.leito.save()
    i.save()
    return JsonResponse({"ok": True})


@require_http_methods(["GET", "POST"])
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_evolucoes_internacao(request, internacao_id):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        internacao = InternacaoHospital.objects.get(pk=internacao_id, empresa=e)
    except InternacaoHospital.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    if request.method == "GET":
        return JsonResponse({"evolucoes": [
            {"id": ev.id, "descricao": ev.descricao,
             "responsavel": ev.responsavel,
             "registrado_em": ev.registrado_em.isoformat()}
            for ev in internacao.evolucoes.all()
        ]})
    data = json.loads(request.body or "{}")
    ev = EvolucaoClinica.objects.create(
        internacao=internacao,
        descricao=data.get("descricao", ""),
        responsavel=data.get("responsavel", ""),
    )
    return JsonResponse({"id": ev.id}, status=201)


# ── KPIs ───────────────────────────────────────────────────────────────────────
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_hospital_ops_kpis(request):
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    total_leitos = LeitoHospital.objects.filter(empresa=e).count()
    leitos_ocupados = LeitoHospital.objects.filter(empresa=e, status="ocupado").count()
    leitos_disponiveis = LeitoHospital.objects.filter(empresa=e, status="disponivel").count()
    internacoes_ativas = InternacaoHospital.objects.filter(empresa=e, status="ativa").count()
    triagens_hoje = TriagemHospital.objects.filter(
        empresa=e, triado_em__date=timezone.now().date()
    ).count()
    taxa_ocupacao = round(leitos_ocupados / total_leitos * 100, 1) if total_leitos else 0
    return JsonResponse({
        "total_leitos": total_leitos,
        "leitos_ocupados": leitos_ocupados,
        "leitos_disponiveis": leitos_disponiveis,
        "internacoes_ativas": internacoes_ativas,
        "triagens_hoje": triagens_hoje,
        "taxa_ocupacao": taxa_ocupacao,
    })


# ── PDFs ───────────────────────────────────────────────────────────────────────
@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_hospital_pdf_internacoes(request):
    from django.http import HttpResponse
    from .pdf_ops import gerar_pdf_internacoes_hospital
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    internacoes = list(InternacaoHospital.objects.filter(empresa=e).select_related(
        "paciente", "leito", "leito__departamento"
    ))
    buf = gerar_pdf_internacoes_hospital(e, internacoes)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="internacoes.pdf"'
    return resp


@api_requer_setor("hospital")
@api_requer_operacao_ou_gerencia
def api_hospital_pdf_ficha_internacao(request, internacao_id):
    from django.http import HttpResponse
    from .pdf_ops import gerar_pdf_ficha_internacao
    e = _e(request)
    if not e:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        internacao = InternacaoHospital.objects.select_related(
            "paciente", "leito", "leito__departamento"
        ).prefetch_related("evolucoes").get(pk=internacao_id, empresa=e)
    except InternacaoHospital.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)
    buf = gerar_pdf_ficha_internacao(e, internacao)
    resp = HttpResponse(buf.read(), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="internacao_{internacao_id}.pdf"'
    return resp
