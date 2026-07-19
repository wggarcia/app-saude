"""
RHC — Registro Hospitalar do Câncer
Obrigação INCA para hospitais com UNACON/CACON (Portaria SAS/MS nº 741/2005).
Geração de arquivo no padrão RHCNET para envio ao INCA.
"""
import csv
import io
import json
import logging
from datetime import date

from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature, get_setor, requer_setor, requer_feature_pacote,
    requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)

# Modalidades de tratamento aceitas no RHCNET
_TRATAMENTOS_VALIDOS = frozenset(["quimio", "radio", "cirurgia", "hormonio", "imunoterapia"])


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _get_rhc_model():
    from .models import RegistroHospitalarCancer
    return RegistroHospitalarCancer


def _registro_to_dict(r, detalhe=False):
    d = {
        "id": r.id,
        "nome_paciente": r.nome_paciente,
        "data_nascimento": r.data_nascimento.isoformat(),
        "sexo": r.sexo,
        "sexo_display": r.get_sexo_display(),
        "cid_topografia": r.cid_topografia,
        "cid_morfologia": r.cid_morfologia,
        "estadiamento": r.estadiamento,
        "estadiamento_display": r.get_estadiamento_display(),
        "data_primeiro_atendimento": r.data_primeiro_atendimento.isoformat(),
        "data_diagnostico": r.data_diagnostico.isoformat() if r.data_diagnostico else None,
        "tratamentos_realizados": r.tratamentos_realizados,
        "status_paciente": r.status_paciente,
        "status_paciente_display": r.get_status_paciente_display(),
        "notificado_inca": r.notificado_inca,
        "numero_rhc": r.numero_rhc,
        "medico_responsavel": r.medico_responsavel,
        "criado_em": r.criado_em.isoformat(),
    }
    return d


# ── Página ─────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.oncologia", "RHC")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_rhc_page(request):
    return render(request, "hospital_rhc.html")


# ── Registros — lista / criação ────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
def api_rhc_registros(request):
    """
    GET  /api/hospital/rhc/registros — lista com filtros status_paciente / cid_topografia
    POST /api/hospital/rhc/registros — cria novo registro RHC
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    RegistroHospitalarCancer = _get_rhc_model()

    if request.method == "GET":
        qs = RegistroHospitalarCancer.objects.filter(empresa=empresa)

        status_f = request.GET.get("status_paciente")
        cid_f    = request.GET.get("cid_topografia")
        q        = request.GET.get("q")

        if status_f:
            qs = qs.filter(status_paciente=status_f)
        if cid_f:
            qs = qs.filter(cid_topografia__icontains=cid_f)
        if q:
            qs = qs.filter(
                Q(nome_paciente__icontains=q) |
                Q(cid_topografia__icontains=q) |
                Q(numero_rhc__icontains=q)
            )

        return JsonResponse({
            "total": qs.count(),
            "registros": [_registro_to_dict(r) for r in qs.order_by("-data_primeiro_atendimento")[:300]],
        })

    # POST — criação
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    campos_obrigatorios = [
        "nome_paciente", "data_nascimento", "sexo",
        "cid_topografia", "estadiamento",
        "data_primeiro_atendimento",
    ]
    faltando = [c for c in campos_obrigatorios if not data.get(c)]
    if faltando:
        return JsonResponse({"erro": f"Campos obrigatórios ausentes: {faltando}"}, status=400)

    try:
        registro = RegistroHospitalarCancer.objects.create(
            empresa=empresa,
            nome_paciente=data["nome_paciente"],
            data_nascimento=data["data_nascimento"],
            sexo=data["sexo"],
            cid_topografia=data["cid_topografia"],
            cid_morfologia=data.get("cid_morfologia", ""),
            estadiamento=data["estadiamento"],
            data_primeiro_atendimento=data["data_primeiro_atendimento"],
            data_diagnostico=data.get("data_diagnostico"),
            medico_responsavel=data.get("medico_responsavel", ""),
            tratamentos_realizados=data.get("tratamentos_realizados", []),
            status_paciente=data.get("status_paciente", "em_tratamento"),
            numero_rhc=data.get("numero_rhc", ""),
        )
    except RegistroHospitalarCancer.DoesNotExist:
        return JsonResponse({"erro": "Erro ao criar registro"}, status=500)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao criar RegistroHospitalarCancer: %s", exc)
        return JsonResponse({"erro": str(exc)}, status=400)

    return JsonResponse({"id": registro.id}, status=201)


# ── Registro — detalhe / atualização ──────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "PATCH"])
@api_requer_feature("hospital.oncologia")
def api_rhc_registro_detalhe(request, pk):
    """
    GET   /api/hospital/rhc/registros/<pk> — detalhe completo
    PATCH /api/hospital/rhc/registros/<pk> — atualiza tratamentos_realizados / status_paciente / estadiamento
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    RegistroHospitalarCancer = _get_rhc_model()

    try:
        registro = RegistroHospitalarCancer.objects.get(pk=pk, empresa=empresa)
    except RegistroHospitalarCancer.DoesNotExist:
        return JsonResponse({"erro": "Registro não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_registro_to_dict(registro, detalhe=True))

    # PATCH
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    campos_patch = ["tratamentos_realizados", "status_paciente", "estadiamento",
                    "medico_responsavel", "data_diagnostico", "numero_rhc", "notificado_inca"]
    for campo in campos_patch:
        if campo in data:
            setattr(registro, campo, data[campo])

    try:
        registro.save()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao atualizar RegistroHospitalarCancer pk=%s: %s", pk, exc)
        return JsonResponse({"erro": str(exc)}, status=400)

    return JsonResponse({"ok": True})


# ── Adicionar tratamento ───────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.oncologia")
def api_rhc_tratar(request, pk):
    """
    POST /api/hospital/rhc/registros/<pk>/tratar
    Body: {"tratamento": "quimio"}  — valores válidos: quimio/radio/cirurgia/hormonio/imunoterapia
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    RegistroHospitalarCancer = _get_rhc_model()

    try:
        registro = RegistroHospitalarCancer.objects.get(pk=pk, empresa=empresa)
    except RegistroHospitalarCancer.DoesNotExist:
        return JsonResponse({"erro": "Registro não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    tratamento = data.get("tratamento", "").lower().strip()
    if not tratamento:
        return JsonResponse({"erro": "Campo 'tratamento' obrigatório"}, status=400)
    if tratamento not in _TRATAMENTOS_VALIDOS:
        return JsonResponse(
            {"erro": f"Tratamento inválido. Valores aceitos: {sorted(_TRATAMENTOS_VALIDOS)}"},
            status=400,
        )

    try:
        lista_atual = list(registro.tratamentos_realizados or [])
        if tratamento not in lista_atual:
            lista_atual.append(tratamento)
            registro.tratamentos_realizados = lista_atual
            registro.save(update_fields=["tratamentos_realizados"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao adicionar tratamento em RHC pk=%s: %s", pk, exc)
        return JsonResponse({"erro": str(exc)}, status=400)

    return JsonResponse({
        "ok": True,
        "tratamentos_realizados": registro.tratamentos_realizados,
    })


# ── Exportação RHCNET ──────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.oncologia")
def api_rhc_exportar(request):
    """
    POST /api/hospital/rhc/exportar
    Body: {"formato": "json"|"csv", "apenas_pendentes": true}
    Gera arquivo no padrão INCA para upload no RHCNET.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    RegistroHospitalarCancer = _get_rhc_model()

    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    formato          = data.get("formato", "json").lower()
    apenas_pendentes = data.get("apenas_pendentes", True)

    try:
        qs = RegistroHospitalarCancer.objects.filter(empresa=empresa)
        if apenas_pendentes:
            qs = qs.filter(notificado_inca=False)

        registros = list(qs.order_by("data_primeiro_atendimento"))

        if formato == "csv":
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";")
            writer.writerow([
                "numero_rhc", "nome_paciente", "data_nascimento", "sexo",
                "cid_topografia", "cid_morfologia", "estadiamento",
                "data_primeiro_atendimento", "data_diagnostico",
                "tratamentos_realizados", "status_paciente",
                "medico_responsavel",
            ])
            for r in registros:
                writer.writerow([
                    r.numero_rhc,
                    r.nome_paciente,
                    r.data_nascimento.isoformat(),
                    r.sexo,
                    r.cid_topografia,
                    r.cid_morfologia,
                    r.estadiamento,
                    r.data_primeiro_atendimento.isoformat(),
                    r.data_diagnostico.isoformat() if r.data_diagnostico else "",
                    "|".join(r.tratamentos_realizados or []),
                    r.status_paciente,
                    r.medico_responsavel,
                ])
            payload = output.getvalue()
        else:
            # JSON no layout RHCNET
            payload = json.dumps({
                "versao_layout": "3.0",
                "hospital_cnes": getattr(empresa, "cnes", ""),
                "data_geracao": date.today().isoformat(),
                "registros": [_registro_to_dict(r) for r in registros],
            }, ensure_ascii=False, indent=2)

        # Marca como notificado
        qs.update(notificado_inca=True)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao exportar RHC: %s", exc)
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({
        "ok": True,
        "formato": formato,
        "total_exportado": len(registros),
        "conteudo": payload,
    })


# ── KPIs ───────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.oncologia")
def api_rhc_kpis(request):
    """GET /api/hospital/rhc/kpis"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    RegistroHospitalarCancer = _get_rhc_model()

    try:
        hoje    = date.today()
        mes_ini = hoje.replace(day=1)

        qs = RegistroHospitalarCancer.objects.filter(empresa=empresa)

        total_pacientes  = qs.count()
        em_tratamento    = qs.filter(status_paciente="em_tratamento").count()
        novos_mes        = qs.filter(data_primeiro_atendimento__gte=mes_ini).count()
        pendente_inca    = qs.filter(notificado_inca=False).count()

    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao calcular KPIs RHC: %s", exc)
        return JsonResponse({"erro": str(exc)}, status=500)

    return JsonResponse({
        "total_pacientes": total_pacientes,
        "em_tratamento":   em_tratamento,
        "novos_mes":       novos_mes,
        "pendente_inca":   pendente_inca,
    })
