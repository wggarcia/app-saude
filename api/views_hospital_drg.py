"""
Integração com Valor Saúde Brasil / DRG Brasil (Sigquali).
"""
import json
import logging
import os
from datetime import date
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import get_setor, requer_setor, requer_feature_pacote, requer_operacao_page, requer_permissao_modulo

try:
    from .models import ClassificacaoDRG, PacienteInternado, CredenciaisIntegracoes
except ImportError:
    ClassificacaoDRG = PacienteInternado = CredenciaisIntegracoes = None

logger = logging.getLogger(__name__)

_SIGQUALI_URL = "https://api.sigquali.com.br/v1/episodes"


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── Page ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.financeiro", "DRG")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_drg_page(request):
    return render(request, "hospital_drg.html")


# ─── Status ──────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_drg_status(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    credencial_ok = False
    ultima_transmissao = None

    if CredenciaisIntegracoes:
        cred = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="drg").first()
        credencial_ok = bool(cred)

    if ClassificacaoDRG:
        ultimo = ClassificacaoDRG.objects.filter(
            empresa=emp, enviado_valor_saude=True
        ).order_by("-data_envio").first()
        if ultimo and ultimo.data_envio:
            ultima_transmissao = ultimo.data_envio.isoformat()

    return JsonResponse({
        "credencial_configurada": credencial_ok,
        "ultima_transmissao": ultima_transmissao,
        "endpoint": _SIGQUALI_URL,
    })


# ─── Enviar Internação ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_drg_enviar_internacao(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if PacienteInternado is None or ClassificacaoDRG is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    body = json.loads(request.body or "{}")
    paciente_id = body.get("paciente_internado_id")
    if not paciente_id:
        return JsonResponse({"erro": "paciente_internado_id obrigatório"}, status=400)

    try:
        paciente = PacienteInternado.objects.get(pk=paciente_id, empresa=emp)
    except PacienteInternado.DoesNotExist:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)

    comp = timezone.now().strftime("%Y-%m")
    drg = ClassificacaoDRG.objects.create(
        empresa=emp,
        paciente_internado=paciente,
        codigo_drg=body.get("codigo_drg", "000"),
        descricao_drg=body.get("descricao_drg", ""),
        peso_relativo=body.get("peso_relativo"),
        aih_numero=body.get("aih_numero", ""),
        competencia=comp,
    )

    # Verifica credencial Sigquali
    credencial = None
    if CredenciaisIntegracoes:
        credencial = CredenciaisIntegracoes.objects.filter(empresa=emp, tipo="drg").first()

    if not credencial:
        return JsonResponse({
            "status": "simulado",
            "mensagem": "Configure credenciais em /configuracoes/integracoes",
            "drg_id": drg.id,
        })

    # Envio real (placeholder)
    try:
        import urllib.request
        payload_json = json.dumps({
            "episodeId": str(drg.id),
            "drgCode": drg.codigo_drg,
            "admissionDate": paciente.data_internacao.isoformat() if hasattr(paciente, "data_internacao") and paciente.data_internacao else comp + "-01",
            "relativeWeight": str(drg.peso_relativo or 1),
        }).encode()
        req = urllib.request.Request(
            _SIGQUALI_URL,
            data=payload_json,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {getattr(credencial, 'token', '')}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resposta = json.loads(resp.read())
        drg.enviado_valor_saude = True
        drg.data_envio = timezone.now()
        drg.resposta_api = resposta
        drg.save()
        return JsonResponse({"status": "enviado", "protocolo": resposta.get("id", str(drg.id))})
    except Exception as exc:
        logger.warning("Erro ao enviar DRG ao Sigquali: %s", exc)
        return JsonResponse({"status": "erro", "mensagem": str(exc), "drg_id": drg.id}, status=502)


# ─── Histórico ────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_drg_historico(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if ClassificacaoDRG is None:
        return JsonResponse({"classificacoes": [], "total": 0})

    qs = ClassificacaoDRG.objects.filter(empresa=emp)
    enviado = request.GET.get("enviado")
    if enviado is not None:
        qs = qs.filter(enviado_valor_saude=(enviado.lower() == "true"))
    qs = qs.order_by("-criado_em")[:200]

    data = [
        {
            "id": d.id,
            "codigo_drg": d.codigo_drg,
            "descricao_drg": d.descricao_drg,
            "peso_relativo": float(d.peso_relativo) if d.peso_relativo else None,
            "aih_numero": d.aih_numero,
            "competencia": d.competencia,
            "enviado": d.enviado_valor_saude,
            "data_envio": d.data_envio.isoformat() if d.data_envio else None,
        }
        for d in qs
    ]
    return JsonResponse({"classificacoes": data, "total": len(data)})


# ─── Reenviar ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_drg_reenviar(request, pk):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    if ClassificacaoDRG is None:
        return JsonResponse({"erro": "Módulo indisponível"}, status=503)

    try:
        drg = ClassificacaoDRG.objects.get(pk=pk, empresa=emp)
    except ClassificacaoDRG.DoesNotExist:
        return JsonResponse({"erro": "Classificação não encontrada"}, status=404)

    sigquali_url = os.environ.get("SIGQUALI_API_URL")
    sigquali_token = os.environ.get("SIGQUALI_API_TOKEN")
    if not sigquali_url or not sigquali_token:
        return JsonResponse({
            "erro": "Integração Sigquali não configurada",
            "mensagem": "Configure as variáveis de ambiente SIGQUALI_API_URL e "
                        "SIGQUALI_API_TOKEN para habilitar o reenvio ao Valor Saúde Brasil.",
            "drg_id": drg.id,
        }, status=503)

    try:
        import requests
        resp = requests.post(
            sigquali_url,
            json={
                "episodeId": str(drg.id),
                "drgCode": drg.codigo_drg,
                "aihNumero": drg.aih_numero,
                "competencia": drg.competencia,
                "relativeWeight": float(drg.peso_relativo) if drg.peso_relativo else None,
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {sigquali_token}",
            },
            timeout=15,
        )
    except Exception as exc:
        logger.warning("Erro ao reenviar DRG %s ao Sigquali: %s", pk, exc)
        return JsonResponse({
            "erro": f"Falha na comunicação com Sigquali: {exc}",
            "drg_id": drg.id,
        }, status=502)

    if resp.status_code != 200:
        return JsonResponse({
            "erro": f"Sigquali retornou HTTP {resp.status_code}",
            "detalhe": resp.text[:300],
            "drg_id": drg.id,
        }, status=502)

    try:
        resposta_json = resp.json()
    except ValueError:
        resposta_json = {"raw": resp.text[:500]}

    protocolo = resposta_json.get("id") or resposta_json.get("protocolo") or str(drg.id)
    drg.enviado_valor_saude = True
    drg.data_envio = timezone.now()
    drg.resposta_api = resposta_json
    drg.save()
    return JsonResponse({"status": "reenviado", "protocolo": protocolo, "drg_id": drg.id})


# ─── KPIs ─────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_drg_kpis(request):
    emp = _hosp(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    enviados_mes = 0
    com_erro = 0
    peso_medio_mes = 0.0
    comp = timezone.now().strftime("%Y-%m")

    if ClassificacaoDRG:
        from django.db.models import Avg
        enviados_mes = ClassificacaoDRG.objects.filter(
            empresa=emp, competencia=comp, enviado_valor_saude=True
        ).count()
        com_erro = ClassificacaoDRG.objects.filter(
            empresa=emp, enviado_valor_saude=False
        ).count()
        avg = ClassificacaoDRG.objects.filter(
            empresa=emp, competencia=comp
        ).aggregate(avg=Avg("peso_relativo"))["avg"]
        peso_medio_mes = round(float(avg or 0), 4)

    return JsonResponse({
        "enviados_mes": enviados_mes,
        "com_erro": com_erro,
        "peso_medio_mes": peso_medio_mes,
        "competencia": comp,
    })
