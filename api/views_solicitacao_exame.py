"""
Solicitações de exames ocupacionais: empresa emite pedido → clínica recebe,
agenda e responde. Base para o fluxo ASO completo sem papel.
"""
import json
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    SolicitacaoExame, FuncionarioSST, VinculoClinicaEmpresa, Empresa,
)
from .views_dashboard import _empresa_autenticada
from .access_control import requer_setor


# Exames padrão SST disponíveis para seleção
EXAMES_PADRAO = [
    "Hemograma completo",
    "Glicemia em jejum",
    "Urina tipo 1 (EAS)",
    "Audiometria tonal (NHO-01)",
    "Acuidade visual (Snellen / Ishihara)",
    "Espirometria",
    "Raio-X de tórax PA",
    "Eletrocardiograma (ECG)",
    "Avaliação psicossocial",
    "Avaliação ergonômica",
    "Dosimetria de ruído",
    "Perfil lipídico (colesterol total, HDL, LDL, triglicerídeos)",
    "Função renal (ureia, creatinina)",
    "Função hepática (TGO, TGP, GGT)",
    "Colinesterase eritrocitária",
    "Chumbo no sangue (plumbemia)",
    "Benzeno urinário (ác. trans,trans-mucônico)",
    "Exame neurológico clínico",
    "Avaliação dermatológica",
    "Avaliação oftalmológica completa",
]


def _empresa(request):
    e = _empresa_autenticada(request)
    if not e:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return e, None


def _sol_dict(s, resumido=True):
    d = {
        "id": s.id,
        "funcionario_id": s.funcionario_id,
        "funcionario_nome": s.funcionario.nome,
        "funcionario_cargo": s.funcionario.cargo,
        "funcionario_cpf": s.funcionario.cpf,
        "clinica_id": s.clinica_id,
        "clinica_nome": s.clinica.nome if s.clinica else s.empresa.nome,
        "tipo_aso": s.tipo_aso,
        "tipo_aso_label": s.get_tipo_aso_display(),
        "exames": json.loads(s.exames) if s.exames else [],
        "urgente": s.urgente,
        "observacoes": s.observacoes,
        "status": s.status,
        "status_label": s.get_status_display(),
        "data_solicitacao": s.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
        "data_agendamento": s.data_agendamento.isoformat() if s.data_agendamento else None,
        "data_realizacao": s.data_realizacao.isoformat() if s.data_realizacao else None,
        "resposta_clinica": s.resposta_clinica,
    }
    return d


# ── Página empresa ─────────────────────────────────────────────────────────────

@requer_setor("empresa")
def sst_solicitacoes_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "sst_solicitacoes.html", {"empresa_nome": empresa.nome})


# ── API empresa: listar / criar solicitações ───────────────────────────────────

@csrf_exempt
def api_solicitacoes_exame(request):
    empresa, err = _empresa(request)
    if err:
        return err

    if request.method == "GET":
        status_f = request.GET.get("status", "")
        qs = SolicitacaoExame.objects.filter(empresa=empresa).select_related(
            "funcionario", "clinica"
        )
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({
            "solicitacoes": [_sol_dict(s) for s in qs],
            "exames_padrao": EXAMES_PADRAO,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        func_id = data.get("funcionario_id")
        if not func_id:
            return JsonResponse({"erro": "funcionario_id é obrigatório"}, status=400)
        func = FuncionarioSST.objects.filter(id=func_id, empresa=empresa).first()
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

        tipo = data.get("tipo_aso", "periodico")
        if tipo not in dict(SolicitacaoExame.TIPO_ASO):
            return JsonResponse({"erro": "Tipo de ASO inválido"}, status=400)

        clinica_id = data.get("clinica_id")
        vinculo = None
        clinica = None
        if clinica_id:
            vinculo = VinculoClinicaEmpresa.objects.filter(
                empresa_contratante=empresa, clinica_id=clinica_id, status="ativo"
            ).first()
            clinica = Empresa.objects.filter(id=clinica_id).first()
            if not clinica:
                return JsonResponse({"erro": "Clínica não encontrada"}, status=404)

        exames = data.get("exames", [])
        sol = SolicitacaoExame.objects.create(
            empresa=empresa,
            funcionario=func,
            clinica=clinica,
            vinculo=vinculo,
            tipo_aso=tipo,
            exames=json.dumps(exames, ensure_ascii=False),
            urgente=bool(data.get("urgente", False)),
            observacoes=data.get("observacoes", "").strip(),
        )
        return JsonResponse(_sol_dict(sol), status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_solicitacao_detalhe(request, sol_id):
    empresa, err = _empresa(request)
    if err:
        return err

    sol = SolicitacaoExame.objects.filter(id=sol_id, empresa=empresa).select_related(
        "funcionario", "clinica"
    ).first()
    if not sol:
        return JsonResponse({"erro": "Solicitação não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_sol_dict(sol))

    if request.method == "DELETE":
        if sol.status != "pendente":
            return JsonResponse({"erro": "Só é possível cancelar solicitações pendentes"}, status=400)
        sol.status = "cancelado"
        sol.save()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_clinicas_disponiveis(request):
    """Lista as clínicas vinculadas à empresa para seleção na solicitação."""
    empresa, err = _empresa(request)
    if err:
        return err

    vinculos = VinculoClinicaEmpresa.objects.filter(
        empresa_contratante=empresa, status="ativo"
    ).select_related("clinica")

    return JsonResponse({
        "clinicas": [
            {
                "id": v.clinica_id,
                "nome": v.clinica.nome,
                "vinculo_id": v.id,
            }
            for v in vinculos
        ]
    })


# ── Página clínica ─────────────────────────────────────────────────────────────

@requer_setor("clinica")
def clinica_solicitacoes_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "clinica_solicitacoes.html", {"empresa_nome": empresa.nome})


# ── API clínica: ver e responder solicitações ──────────────────────────────────

@csrf_exempt
def api_clinica_solicitacoes(request):
    clinica, err = _empresa(request)
    if err:
        return err

    if request.method == "GET":
        status_f = request.GET.get("status", "")
        qs = SolicitacaoExame.objects.filter(clinica=clinica).select_related(
            "funcionario", "empresa"
        )
        if status_f:
            qs = qs.filter(status=status_f)

        def _sol_clinica(s):
            d = _sol_dict(s)
            d["empresa_solicitante"] = s.empresa.nome
            d["empresa_cnpj"] = s.empresa.cnpj if hasattr(s.empresa, "cnpj") else ""
            return d

        return JsonResponse({"solicitacoes": [_sol_clinica(s) for s in qs]})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_clinica_solicitacao_acao(request, sol_id):
    clinica, err = _empresa(request)
    if err:
        return err

    sol = SolicitacaoExame.objects.filter(id=sol_id, clinica=clinica).select_related(
        "funcionario", "empresa"
    ).first()
    if not sol:
        return JsonResponse({"erro": "Solicitação não encontrada"}, status=404)

    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao")

    if acao == "agendar":
        data_ag = data.get("data_agendamento")
        if not data_ag:
            return JsonResponse({"erro": "data_agendamento é obrigatória"}, status=400)
        from datetime import datetime
        try:
            sol.data_agendamento = datetime.strptime(data_ag, "%Y-%m-%d").date()
        except Exception:
            return JsonResponse({"erro": "Data inválida"}, status=400)
        sol.status = "agendado"
        sol.resposta_clinica = data.get("resposta_clinica", sol.resposta_clinica)
        sol.save()
        return JsonResponse({"ok": True, "status": sol.status})

    if acao == "realizar":
        data_real = data.get("data_realizacao")
        from datetime import date, datetime
        try:
            sol.data_realizacao = datetime.strptime(data_real, "%Y-%m-%d").date() if data_real else date.today()
        except Exception:
            sol.data_realizacao = date.today()
        sol.status = "realizado"
        sol.resposta_clinica = data.get("resposta_clinica", sol.resposta_clinica)
        sol.save()
        return JsonResponse({"ok": True, "status": sol.status})

    if acao == "cancelar":
        sol.status = "cancelado"
        sol.resposta_clinica = data.get("resposta_clinica", "")
        sol.save()
        return JsonResponse({"ok": True, "status": sol.status})

    return JsonResponse({"erro": f"Ação inválida: {acao}"}, status=400)
