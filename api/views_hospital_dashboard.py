"""
Hospital Dashboard — endpoints do módulo de gestão hospitalar.

Modelos: LeitoHospitalar, TriagemManchester, PacienteInternado, PrescricaoHospitalar
Pattern: @csrf_exempt + getattr(request, "empresa", None) + JsonResponse
"""

import json
from datetime import date

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    LeitoHospitalar,
    TriagemManchester,
    PacienteInternado,
    PrescricaoHospitalar,
)


def _get_empresa(request):
    """Retorna a empresa do JWT middleware ou None."""
    return getattr(request, "empresa", None)


# ── Dashboard / KPIs ─────────────────────────────────────────────────────────

@csrf_exempt
def api_hospital_dashboard(request):
    """GET — KPIs do módulo hospitalar para o dashboard Manchester."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    hoje = date.today()

    # Leitos
    total_leitos = LeitoHospitalar.objects.filter(empresa=empresa).count()
    leitos_ocupados = LeitoHospitalar.objects.filter(empresa=empresa, status="ocupado").count()
    leitos_livres = LeitoHospitalar.objects.filter(empresa=empresa, status="livre").count()
    taxa_ocupacao_pct = (
        round(leitos_ocupados / total_leitos * 100, 1) if total_leitos else 0.0
    )

    # Pacientes internados
    pacientes_internados = PacienteInternado.objects.filter(
        empresa=empresa, status="internado"
    ).count()

    # Triagens de hoje
    triagens_hoje_qs = TriagemManchester.objects.filter(
        empresa=empresa, data_hora__date=hoje
    )
    triagens_hoje = triagens_hoje_qs.count()

    # Contagem por nível Manchester
    niveis = ["vermelho", "laranja", "amarelo", "verde", "azul"]
    por_nivel_triagem = {}
    for nivel in niveis:
        por_nivel_triagem[nivel] = triagens_hoje_qs.filter(nivel=nivel).count()

    # Média de espera (triagens de hoje)
    espera_values = list(
        triagens_hoje_qs.values_list("tempo_espera_minutos", flat=True)
    )
    media_espera_minutos = (
        round(sum(espera_values) / len(espera_values), 1) if espera_values else 0.0
    )

    # Alertas
    alertas = []
    if taxa_ocupacao_pct > 85:
        alertas.append({
            "tipo": "leitos_criticos",
            "mensagem": f"Taxa de ocupação crítica: {taxa_ocupacao_pct}%",
        })

    triagens_vermelhas_pendentes = TriagemManchester.objects.filter(
        empresa=empresa,
        nivel="vermelho",
        status__in=["aguardando", "em_atendimento"],
    ).count()
    if triagens_vermelhas_pendentes > 0:
        alertas.append({
            "tipo": "triagens_vermelhas_pendentes",
            "mensagem": f"{triagens_vermelhas_pendentes} triagem(ns) vermelha(s) pendente(s)",
            "quantidade": triagens_vermelhas_pendentes,
        })

    return JsonResponse({
        "total_leitos": total_leitos,
        "leitos_ocupados": leitos_ocupados,
        "leitos_livres": leitos_livres,
        "taxa_ocupacao_pct": taxa_ocupacao_pct,
        "pacientes_internados": pacientes_internados,
        "triagens_hoje": triagens_hoje,
        "por_nivel_triagem": por_nivel_triagem,
        "media_espera_minutos": media_espera_minutos,
        "alertas": alertas,
    })


# ── Leitos ────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_hospital_leitos(request):
    """GET lista leitos | POST cria leito | PUT atualiza leito."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        status_f = request.GET.get("status")
        tipo_f = request.GET.get("tipo")
        qs = LeitoHospitalar.objects.filter(empresa=empresa)
        if status_f:
            qs = qs.filter(status=status_f)
        if tipo_f:
            qs = qs.filter(tipo=tipo_f)

        leitos = []
        for leito in qs:
            leitos.append({
                "id": leito.id,
                "numero": leito.numero,
                "ala": leito.ala,
                "tipo": leito.tipo,
                "status": leito.status,
                "paciente_nome": leito.paciente_nome,
                "paciente_id": str(leito.paciente_id) if leito.paciente_id else None,
                "data_internacao": leito.data_internacao.isoformat() if leito.data_internacao else None,
                "previsao_alta": leito.previsao_alta.isoformat() if leito.previsao_alta else None,
            })
        return JsonResponse({"leitos": leitos})

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        numero = data.get("numero", "").strip()
        if not numero:
            return JsonResponse({"erro": "numero é obrigatório"}, status=400)

        if LeitoHospitalar.objects.filter(empresa=empresa, numero=numero).exists():
            return JsonResponse({"erro": "Número de leito já cadastrado"}, status=409)

        leito = LeitoHospitalar.objects.create(
            empresa=empresa,
            numero=numero,
            ala=data.get("ala", ""),
            tipo=data.get("tipo", "enfermaria"),
            status=data.get("status", "livre"),
            paciente_nome=data.get("paciente_nome") or None,
            data_internacao=data.get("data_internacao") or None,
            previsao_alta=data.get("previsao_alta") or None,
        )
        return JsonResponse({"id": leito.id, "numero": leito.numero}, status=201)

    if request.method == "PUT":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        leito_id = data.get("id")
        if not leito_id:
            return JsonResponse({"erro": "id é obrigatório para PUT"}, status=400)

        try:
            leito = LeitoHospitalar.objects.get(pk=leito_id, empresa=empresa)
        except LeitoHospitalar.DoesNotExist:
            return JsonResponse({"erro": "Leito não encontrado"}, status=404)

        campos_simples = ["ala", "tipo", "status", "paciente_nome"]
        for campo in campos_simples:
            if campo in data:
                setattr(leito, campo, data[campo])

        if "paciente_id" in data:
            leito.paciente_id = data["paciente_id"] or None
        if "data_internacao" in data:
            leito.data_internacao = data["data_internacao"] or None
        if "previsao_alta" in data:
            leito.previsao_alta = data["previsao_alta"] or None

        leito.save()
        return JsonResponse({"ok": True, "id": leito.id})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Triagem Manchester ────────────────────────────────────────────────────────

@csrf_exempt
def api_hospital_triagem(request):
    """GET lista triagens (filtro: status, nivel) | POST registra nova triagem."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = TriagemManchester.objects.filter(empresa=empresa)

        status_f = request.GET.get("status")
        nivel_f = request.GET.get("nivel")
        data_f = request.GET.get("data")  # YYYY-MM-DD

        if status_f:
            qs = qs.filter(status=status_f)
        if nivel_f:
            qs = qs.filter(nivel=nivel_f)
        if data_f:
            qs = qs.filter(data_hora__date=data_f)

        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 50)), 200)
        offset = (page - 1) * limit
        total = qs.count()
        qs = qs[offset: offset + limit]

        triagens = []
        for t in qs:
            triagens.append({
                "id": t.id,
                "data_hora": t.data_hora.isoformat(),
                "paciente_nome": t.paciente_nome,
                "paciente_cpf": t.paciente_cpf,
                "queixa_principal": t.queixa_principal,
                "nivel": t.nivel,
                "tempo_espera_minutos": t.tempo_espera_minutos,
                "status": t.status,
                "medico_responsavel": t.medico_responsavel,
                "observacao": t.observacao,
            })
        return JsonResponse({"triagens": triagens, "total": total, "page": page})

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        paciente_nome = data.get("paciente_nome", "").strip()
        queixa = data.get("queixa_principal", "").strip()
        nivel = data.get("nivel", "").strip()

        if not paciente_nome:
            return JsonResponse({"erro": "paciente_nome é obrigatório"}, status=400)
        if not queixa:
            return JsonResponse({"erro": "queixa_principal é obrigatória"}, status=400)
        if not nivel:
            return JsonResponse({"erro": "nivel é obrigatório"}, status=400)

        niveis_validos = [c[0] for c in TriagemManchester.NIVEL_CHOICES]
        if nivel not in niveis_validos:
            return JsonResponse(
                {"erro": f"nivel inválido. Opções: {niveis_validos}"}, status=400
            )

        data_hora = data.get("data_hora")
        if data_hora:
            from django.utils.dateparse import parse_datetime
            data_hora = parse_datetime(data_hora) or timezone.now()
        else:
            data_hora = timezone.now()

        triagem = TriagemManchester.objects.create(
            empresa=empresa,
            data_hora=data_hora,
            paciente_nome=paciente_nome,
            paciente_cpf=data.get("paciente_cpf") or None,
            queixa_principal=queixa,
            nivel=nivel,
            tempo_espera_minutos=int(data.get("tempo_espera_minutos", 0)),
            status=data.get("status", "aguardando"),
            medico_responsavel=data.get("medico_responsavel", ""),
            observacao=data.get("observacao", ""),
        )
        return JsonResponse({"id": triagem.id, "nivel": triagem.nivel}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Pacientes Internados ──────────────────────────────────────────────────────

@csrf_exempt
def api_hospital_pacientes(request):
    """GET lista pacientes internados (paginado) | POST interna novo paciente."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        qs = PacienteInternado.objects.filter(empresa=empresa).select_related("leito")

        status_f = request.GET.get("status")
        q = request.GET.get("q", "")
        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(nome__icontains=q)

        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        offset = (page - 1) * limit
        total = qs.count()
        qs = qs[offset: offset + limit]

        pacientes = []
        for p in qs:
            pacientes.append({
                "id": p.id,
                "nome": p.nome,
                "cpf": p.cpf,
                "data_nascimento": p.data_nascimento.isoformat() if p.data_nascimento else None,
                "data_internacao": p.data_internacao.isoformat(),
                "leito_id": p.leito_id,
                "leito_numero": p.leito.numero if p.leito else None,
                "leito_ala": p.leito.ala if p.leito else None,
                "diagnostico_cid": p.diagnostico_cid,
                "medico_responsavel": p.medico_responsavel,
                "convenio": p.convenio,
                "status": p.status,
                "prescricao_atual": p.prescricao_atual,
                "evolucao": p.evolucao,
            })
        return JsonResponse({"pacientes": pacientes, "total": total, "page": page})

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = data.get("nome", "").strip()
        if not nome:
            return JsonResponse({"erro": "nome é obrigatório"}, status=400)

        data_internacao = data.get("data_internacao") or date.today().isoformat()

        leito = None
        leito_id = data.get("leito_id")
        if leito_id:
            try:
                leito = LeitoHospitalar.objects.get(pk=leito_id, empresa=empresa)
            except LeitoHospitalar.DoesNotExist:
                return JsonResponse({"erro": "Leito não encontrado"}, status=404)

        paciente = PacienteInternado.objects.create(
            empresa=empresa,
            nome=nome,
            cpf=data.get("cpf", ""),
            data_nascimento=data.get("data_nascimento") or None,
            data_internacao=data_internacao,
            leito=leito,
            diagnostico_cid=data.get("diagnostico_cid", ""),
            medico_responsavel=data.get("medico_responsavel", ""),
            convenio=data.get("convenio", ""),
            status=data.get("status", "internado"),
            prescricao_atual=data.get("prescricao_atual") or {},
            evolucao=data.get("evolucao") or [],
        )

        # Marcar leito como ocupado
        if leito:
            leito.status = "ocupado"
            leito.paciente_nome = nome
            leito.data_internacao = data_internacao
            leito.save()

        return JsonResponse({"id": paciente.id, "nome": paciente.nome}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Prescrições Hospitalares ──────────────────────────────────────────────────

@csrf_exempt
def api_hospital_prescricao(request):
    """GET lista prescrições do paciente | POST cria prescrição."""
    empresa = _get_empresa(request)
    if empresa is None:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "GET":
        paciente_id = request.GET.get("paciente_id")
        qs = PrescricaoHospitalar.objects.filter(empresa=empresa).select_related("paciente")

        if paciente_id:
            qs = qs.filter(paciente_id=paciente_id)

        status_f = request.GET.get("status")
        if status_f:
            qs = qs.filter(status=status_f)

        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 50)), 200)
        offset = (page - 1) * limit
        total = qs.count()
        qs = qs[offset: offset + limit]

        prescricoes = []
        for pr in qs:
            prescricoes.append({
                "id": pr.id,
                "paciente_id": pr.paciente_id,
                "paciente_nome": pr.paciente.nome,
                "data": pr.data.isoformat(),
                "medicamentos": pr.medicamentos,
                "validade_horas": pr.validade_horas,
                "medico_crm": pr.medico_crm,
                "medico_nome": pr.medico_nome,
                "status": pr.status,
                "criado_em": pr.criado_em.isoformat(),
            })
        return JsonResponse({"prescricoes": prescricoes, "total": total, "page": page})

    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        paciente_id = data.get("paciente_id")
        if not paciente_id:
            return JsonResponse({"erro": "paciente_id é obrigatório"}, status=400)

        try:
            paciente = PacienteInternado.objects.get(pk=paciente_id, empresa=empresa)
        except PacienteInternado.DoesNotExist:
            return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

        medicamentos = data.get("medicamentos", [])
        if not isinstance(medicamentos, list):
            return JsonResponse({"erro": "medicamentos deve ser uma lista"}, status=400)

        data_prescricao = data.get("data") or date.today().isoformat()

        prescricao = PrescricaoHospitalar.objects.create(
            empresa=empresa,
            paciente=paciente,
            data=data_prescricao,
            medicamentos=medicamentos,
            validade_horas=int(data.get("validade_horas", 24)),
            medico_crm=data.get("medico_crm", ""),
            medico_nome=data.get("medico_nome", ""),
            status=data.get("status", "ativa"),
        )

        # Atualiza prescricao_atual do paciente
        paciente.prescricao_atual = {
            "prescricao_id": prescricao.id,
            "data": data_prescricao,
            "medicamentos": medicamentos,
            "medico_nome": prescricao.medico_nome,
            "validade_horas": prescricao.validade_horas,
        }
        paciente.save(update_fields=["prescricao_atual", "atualizado_em"])

        return JsonResponse({"id": prescricao.id, "status": prescricao.status}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)
