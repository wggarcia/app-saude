"""
Sistema de vínculo clínica-empresa: permite que uma clínica de exames ocupacionais
envie ASOs diretamente para a conta SolusCRT de uma empresa-cliente.

Fluxo:
  1. Clínica cria vínculo informando CNPJ + nome da empresa (POST /api/clinica/vinculos)
  2. Sistema gera token de convite e URL de aceitação
  3. Empresa acessa /clinica/aceitar/<token>/ e confirma o vínculo
  4. Clínica envia ASOs (POST /api/clinica/vinculos/<id>/enviar-aso/<aso_id>)
  5. Empresa vê ASOs recebidos (GET /api/empresa/asos-recebidos)
  6. Empresa importa ou rejeita cada ASO recebido
"""
import json
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    Empresa, ASOOcupacional, VinculoClinicaEmpresa, ASOEnviadoClinica, FuncionarioSST,
)
from .views_dashboard import _empresa_autenticada
from .access_control import get_setor


def _empresa_req(request):
    e = _empresa_autenticada(request)
    if not e:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(e) != "empresa":
        return None, JsonResponse({"erro": "Módulo SST não disponível para este plano."}, status=403)
    return e, None


def _vinculo_dict(v, incluir_token=False):
    d = {
        "id": v.id,
        "status": v.status,
        "status_label": v.get_status_display(),
        "empresa_cnpj": v.empresa_cnpj,
        "empresa_nome": v.empresa_nome or (v.empresa_contratante.nome if v.empresa_contratante else "—"),
        "empresa_tem_conta": v.empresa_contratante_id is not None,
        "criado_em": v.criado_em.isoformat(),
        "aceito_em": v.aceito_em.isoformat() if v.aceito_em else None,
        "total_asos_enviados": v.asos_enviados.count(),
    }
    if incluir_token:
        d["token_convite"] = v.token_convite
        host = "https://app-saude-p9n8.onrender.com"
        d["url_convite"] = f"{host}/clinica/aceitar/{v.token_convite}/"
    return d


def _aso_enviado_dict(e):
    aso = e.aso
    return {
        "id": e.id,
        "aso_id": aso.id,
        "funcionario_nome": aso.funcionario.nome,
        "funcionario_cpf": aso.funcionario.cpf,
        "tipo": aso.tipo,
        "tipo_label": aso.get_tipo_display(),
        "data_emissao": aso.data_emissao.strftime("%d/%m/%Y"),
        "data_validade": aso.data_validade.strftime("%d/%m/%Y") if aso.data_validade else None,
        "resultado": aso.resultado,
        "resultado_label": aso.get_resultado_display(),
        "medico": aso.medico_responsavel,
        "clinica_nome": e.vinculo.clinica.nome,
        "status": e.status,
        "status_label": e.get_status_display(),
        "enviado_em": e.enviado_em.isoformat(),
        "visualizado_em": e.visualizado_em.isoformat() if e.visualizado_em else None,
    }


# ── CLÍNICA: gerenciar vínculos ────────────────────────────────────────────────

@csrf_exempt
def api_clinica_vinculos(request):
    """GET: lista empresas vinculadas. POST: cria novo vínculo (convite)."""
    clinica, err = _empresa_req(request)
    if err:
        return err

    if request.method == "GET":
        qs = VinculoClinicaEmpresa.objects.filter(clinica=clinica).select_related("empresa_contratante")
        return JsonResponse({
            "vinculos": [_vinculo_dict(v, incluir_token=True) for v in qs],
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        cnpj = (data.get("empresa_cnpj") or "").strip()
        nome = (data.get("empresa_nome") or "").strip()
        email = (data.get("empresa_email") or "").strip()

        if not cnpj and not nome:
            return JsonResponse({"erro": "Informe CNPJ ou nome da empresa"}, status=400)

        # Verifica se empresa já tem conta no SolusCRT pelo CNPJ (busca no email ou nome)
        empresa_conta = None
        if email:
            empresa_conta = Empresa.objects.filter(email=email, ativo=True).first()

        # Evita duplicar vínculo ativo
        if empresa_conta:
            existente = VinculoClinicaEmpresa.objects.filter(
                clinica=clinica, empresa_contratante=empresa_conta,
            ).exclude(status="recusado").first()
            if existente:
                return JsonResponse({"erro": "Já existe um vínculo com esta empresa", "vinculo_id": existente.id}, status=409)

        vinculo = VinculoClinicaEmpresa.objects.create(
            clinica=clinica,
            empresa_contratante=empresa_conta,
            empresa_cnpj=cnpj,
            empresa_nome=nome,
            empresa_email_convite=email,
        )
        return JsonResponse(_vinculo_dict(vinculo, incluir_token=True), status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_clinica_vinculo_detalhe(request, vinculo_id):
    """GET: detalhes. DELETE: remove/suspende vínculo."""
    clinica, err = _empresa_req(request)
    if err:
        return err

    vinculo = VinculoClinicaEmpresa.objects.filter(id=vinculo_id, clinica=clinica).first()
    if not vinculo:
        return JsonResponse({"erro": "Vínculo não encontrado"}, status=404)

    if request.method == "GET":
        d = _vinculo_dict(vinculo, incluir_token=True)
        d["asos"] = [_aso_enviado_dict(e) for e in vinculo.asos_enviados.select_related("aso__funcionario").order_by("-enviado_em")[:20]]
        return JsonResponse(d)

    if request.method == "DELETE":
        vinculo.status = "suspenso"
        vinculo.save(update_fields=["status"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_clinica_enviar_aso(request, vinculo_id, aso_id):
    """POST: clínica envia um ASO para a empresa vinculada."""
    clinica, err = _empresa_req(request)
    if err:
        return err

    vinculo = VinculoClinicaEmpresa.objects.filter(id=vinculo_id, clinica=clinica, status="ativo").first()
    if not vinculo:
        return JsonResponse({"erro": "Vínculo não encontrado ou não está ativo"}, status=404)

    aso = ASOOcupacional.objects.filter(id=aso_id, empresa=clinica).select_related("funcionario").first()
    if not aso:
        return JsonResponse({"erro": "ASO não encontrado"}, status=404)

    # Evita envio duplicado
    if ASOEnviadoClinica.objects.filter(vinculo=vinculo, aso=aso).exists():
        return JsonResponse({"erro": "Este ASO já foi enviado para esta empresa"}, status=409)

    envio = ASOEnviadoClinica.objects.create(vinculo=vinculo, aso=aso)
    return JsonResponse({"id": envio.id, "ok": True, "mensagem": "ASO enviado para a empresa"}, status=201)


# ── EMPRESA: aceitar convite e ver ASOs recebidos ──────────────────────────────

def pagina_aceitar_convite(request, token):
    """Página pública onde empresa aceita o vínculo com a clínica."""
    vinculo = get_object_or_404(VinculoClinicaEmpresa, token_convite=token)
    empresa = _empresa_autenticada(request)

    if request.method == "POST":
        acao = request.POST.get("acao") or (json.loads(request.body or "{}").get("acao") if request.content_type == "application/json" else None)

        if acao == "aceitar":
            if not empresa:
                return JsonResponse({"erro": "Faça login para aceitar o convite"}, status=401)
            vinculo.empresa_contratante = empresa
            vinculo.status = "ativo"
            vinculo.aceito_em = timezone.now()
            vinculo.save(update_fields=["empresa_contratante", "status", "aceito_em"])
            return JsonResponse({"ok": True, "mensagem": f"Vínculo com {vinculo.clinica.nome} ativado com sucesso!"})

        if acao == "recusar":
            vinculo.status = "recusado"
            vinculo.save(update_fields=["status"])
            return JsonResponse({"ok": True, "mensagem": "Convite recusado"})

        return JsonResponse({"erro": "ação inválida"}, status=400)

    return render(request, "clinica_aceitar_convite.html", {
        "vinculo": vinculo,
        "clinica_nome": vinculo.clinica.nome,
        "empresa_logada": empresa,
        "ja_respondido": vinculo.status in ("ativo", "recusado", "suspenso"),
    })


@csrf_exempt
def api_aceitar_vinculo(request, token):
    """API JSON para aceitar/recusar convite (usado pelo frontend sem reload)."""
    empresa, err = _empresa_req(request)
    if err:
        return err

    vinculo = VinculoClinicaEmpresa.objects.filter(token_convite=token).first()
    if not vinculo:
        return JsonResponse({"erro": "Convite não encontrado ou expirado"}, status=404)
    if vinculo.status != "pendente":
        return JsonResponse({"erro": f"Convite já foi {vinculo.get_status_display().lower()}"}, status=409)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao")
    if acao == "aceitar":
        vinculo.empresa_contratante = empresa
        vinculo.status = "ativo"
        vinculo.aceito_em = timezone.now()
        vinculo.save(update_fields=["empresa_contratante", "status", "aceito_em"])
        return JsonResponse({"ok": True, "clinica_nome": vinculo.clinica.nome})

    if acao == "recusar":
        vinculo.status = "recusado"
        vinculo.save(update_fields=["status"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "ação inválida (aceitar ou recusar)"}, status=400)


def api_empresa_asos_recebidos(request):
    """GET: lista ASOs recebidos de clínicas vinculadas."""
    empresa, err = _empresa_req(request)
    if err:
        return err

    qs = ASOEnviadoClinica.objects.filter(
        vinculo__empresa_contratante=empresa,
    ).select_related("aso__funcionario", "vinculo__clinica").order_by("-enviado_em")

    # Marca como visualizado
    nao_vistos = qs.filter(status="enviado")
    agora = timezone.now()
    nao_vistos.update(status="visualizado", visualizado_em=agora)

    return JsonResponse({
        "total": qs.count(),
        "asos_recebidos": [_aso_enviado_dict(e) for e in qs[:50]],
    })


@csrf_exempt
def api_empresa_aso_recebido_acao(request, envio_id):
    """POST: empresa importa ou rejeita ASO recebido."""
    empresa, err = _empresa_req(request)
    if err:
        return err

    envio = ASOEnviadoClinica.objects.filter(
        id=envio_id, vinculo__empresa_contratante=empresa
    ).select_related("aso__funcionario").first()
    if not envio:
        return JsonResponse({"erro": "Registro não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao")
    if acao == "importar":
        # Cria cópia do ASO na conta da empresa se o funcionário existir
        aso_orig = envio.aso
        func = FuncionarioSST.objects.filter(
            empresa=empresa, cpf=aso_orig.funcionario.cpf
        ).first()
        if not func:
            return JsonResponse({
                "erro": f"Funcionário com CPF {aso_orig.funcionario.cpf} não encontrado na sua empresa. Cadastre-o primeiro.",
            }, status=404)

        ASOOcupacional.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            tipo=aso_orig.tipo,
            data_emissao=aso_orig.data_emissao,
            defaults={
                "data_validade": aso_orig.data_validade,
                "medico_responsavel": aso_orig.medico_responsavel,
                "crm": aso_orig.crm,
                "resultado": aso_orig.resultado,
                "cid_inapto": aso_orig.cid_inapto,
                "riscos_ocupacionais": aso_orig.riscos_ocupacionais,
                "restricoes": aso_orig.restricoes,
                "observacoes": f"Importado de {envio.vinculo.clinica.nome}. {aso_orig.observacoes}".strip(),
            },
        )
        envio.status = "importado"
        envio.importado_em = timezone.now()
        envio.save(update_fields=["status", "importado_em"])
        return JsonResponse({"ok": True, "mensagem": "ASO importado ao prontuário do funcionário"})

    if acao == "rejeitar":
        obs = data.get("observacao", "")
        envio.status = "rejeitado"
        envio.observacao_empresa = obs
        envio.save(update_fields=["status", "observacao_empresa"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "ação inválida (importar ou rejeitar)"}, status=400)


def api_empresa_vinculos_clinicas(request):
    """GET: lista clínicas vinculadas à empresa (vínculos aceitos)."""
    empresa, err = _empresa_req(request)
    if err:
        return err

    qs = VinculoClinicaEmpresa.objects.filter(
        empresa_contratante=empresa, status="ativo"
    ).select_related("clinica")

    return JsonResponse({
        "clinicas": [
            {
                "id": v.id,
                "clinica_nome": v.clinica.nome,
                "aceito_em": v.aceito_em.strftime("%d/%m/%Y") if v.aceito_em else None,
                "total_asos": v.asos_enviados.count(),
                "pendentes": v.asos_enviados.filter(status="enviado").count(),
            }
            for v in qs
        ]
    })
