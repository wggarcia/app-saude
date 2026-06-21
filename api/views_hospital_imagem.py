"""
Hospital — RIS/PACS (Radiology Information System)
  • ExameRIS — modalidade, laudo, link PACS, workflow de status
  • InstanciaDicom — armazenamento real de arquivo DICOM + metadados (PACS)
"""
import json
from io import BytesIO

import pydicom
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_gerencia,
    get_setor,
    principal_pode_operacao_setorial,
    requer_setor,
    requer_operacao_page,
    requer_permissao_modulo,
)
from .models import ExameRIS, InstanciaDicom
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base, contexto_navegacao_setorial


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _empresa(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    if get_setor(empresa) != "hospital":
        return JsonResponse({"erro": "Módulo não disponível para este plano."}, status=403)
    if not principal_pode_operacao_setorial(request):
        return JsonResponse({"erro": "Acesso restrito à operação/gerência hospitalar."}, status=403)
    return empresa


# ─── Serializer ───────────────────────────────────────────────────────────────

def _ris_to_dict(e):
    return {
        "id": e.id,
        "paciente_nome": e.paciente_nome,
        "prontuario_id": e.prontuario_id,
        "modalidade": e.modalidade,
        "modalidade_label": dict(ExameRIS.MODALIDADES).get(e.modalidade, e.modalidade),
        "regiao_anatomica": e.regiao_anatomica,
        "solicitante": e.solicitante,
        "laudo": e.laudo,
        "imagem_url": e.imagem_url,
        "laudado": bool(e.laudo),
        "laudado_em": e.laudado_em.strftime("%d/%m/%Y %H:%M") if e.laudado_em else None,
        "solicitado_em": e.solicitado_em.strftime("%d/%m/%Y %H:%M"),
        "total_instancias_dicom": e.instancias_dicom.count(),
    }


def _instancia_to_dict(inst):
    return {
        "id": inst.id,
        "modalidade_dicom": inst.modalidade_dicom,
        "numero_instancia": inst.numero_instancia,
        "tamanho_bytes": inst.tamanho_bytes,
        "sop_instance_uid": inst.sop_instance_uid,
        "enviado_em": inst.enviado_em.strftime("%d/%m/%Y %H:%M"),
        "url_arquivo": f"/api/hospital/imagem/dicom/{inst.id}/arquivo/",
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_imagem_page(request):
    return render(request, "hospital_imagem.html", contexto_navegacao_setorial(request, "hospital"))


# ─── API: Lista exames RIS ────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_ris_exames(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    qs = ExameRIS.objects.filter(empresa=empresa)

    modalidade = request.GET.get("modalidade")
    if modalidade:
        qs = qs.filter(modalidade=modalidade)

    laudado = request.GET.get("laudado")
    if laudado == "1":
        qs = qs.exclude(laudo="")
    elif laudado == "0":
        qs = qs.filter(laudo="")

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(paciente_nome__icontains=q) |
            Q(regiao_anatomica__icontains=q) |
            Q(solicitante__icontains=q)
        )

    data_de = request.GET.get("data_de")
    data_ate = request.GET.get("data_ate")
    if data_de:
        qs = qs.filter(solicitado_em__date__gte=data_de)
    if data_ate:
        qs = qs.filter(solicitado_em__date__lte=data_ate)

    qs = qs.order_by("-solicitado_em")[:100]
    return JsonResponse({"exames": [_ris_to_dict(e) for e in qs]})


# ─── API: Solicitar exame RIS ─────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_ris_solicitar(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    paciente_nome = (data.get("paciente_nome") or "").strip()
    regiao_anatomica = (data.get("regiao_anatomica") or "").strip()
    solicitante = (data.get("solicitante") or "").strip()

    if not paciente_nome or not regiao_anatomica or not solicitante:
        return JsonResponse({"erro": "paciente_nome, regiao_anatomica e solicitante são obrigatórios"}, status=400)

    modalidades_validas = [m[0] for m in ExameRIS.MODALIDADES]
    modalidade = data.get("modalidade", "rx")
    if modalidade not in modalidades_validas:
        return JsonResponse({"erro": f"modalidade inválida. Opções: {modalidades_validas}"}, status=400)

    from .models import ProntuarioHospitalar
    prontuario_id = data.get("prontuario_id")
    prontuario = None
    if prontuario_id:
        try:
            prontuario = ProntuarioHospitalar.objects.get(pk=prontuario_id, empresa=empresa)
        except ProntuarioHospitalar.DoesNotExist:
            pass
    if prontuario is None:
        prontuario, _ = ProntuarioHospitalar.objects.get_or_create(
            empresa=empresa, paciente_nome=paciente_nome,
        )

    exame = ExameRIS.objects.create(
        empresa=empresa,
        prontuario=prontuario,
        paciente_nome=paciente_nome,
        modalidade=modalidade,
        regiao_anatomica=regiao_anatomica,
        solicitante=solicitante,
    )
    return JsonResponse({"ok": True, "exame": _ris_to_dict(exame)}, status=201)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ris(request):
    if request.method == "POST":
        return api_ris_solicitar(request)
    return api_ris_exames(request)


# ─── API: Laudar exame ────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_ris_laudar(request, exame_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        exame = ExameRIS.objects.get(pk=exame_id, empresa=empresa)
    except ExameRIS.DoesNotExist:
        return JsonResponse({"erro": "Exame não encontrado"}, status=404)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    laudo = (data.get("laudo") or "").strip()
    if not laudo:
        return JsonResponse({"erro": "laudo é obrigatório"}, status=400)

    exame.laudo = laudo
    if "imagem_url" in data:
        exame.imagem_url = data["imagem_url"]
    if not exame.laudado_em:
        exame.laudado_em = timezone.now()

    exame.save()
    return JsonResponse({"ok": True, "exame": _ris_to_dict(exame)})


# ─── API: KPIs por modalidade ─────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_ris_kpis(request):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    hoje = timezone.now().date()
    qs = ExameRIS.objects.filter(empresa=empresa)

    por_modalidade = list(
        qs.values("modalidade").annotate(n=Count("id")).order_by("-n")
    )
    # Add human-readable label
    modal_map = dict(ExameRIS.MODALIDADES)
    for row in por_modalidade:
        row["label"] = modal_map.get(row["modalidade"], row["modalidade"])

    solicitados_hoje = qs.filter(solicitado_em__date=hoje).count()
    pendentes_laudo = qs.filter(laudo="").count()
    laudados_hoje = qs.filter(laudado_em__date=hoje).count()
    total = qs.count()

    return JsonResponse({
        "total": total,
        "solicitados_hoje": solicitados_hoje,
        "pendentes_laudo": pendentes_laudo,
        "laudados_hoje": laudados_hoje,
        "por_modalidade": por_modalidade,
    })


# ─── API: Instâncias DICOM (upload + listagem) ────────────────────────────────

MAX_DICOM_UPLOAD_BYTES = 60 * 1024 * 1024  # 60MB por arquivo — exames de imagem são grandes


@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ris_dicom(request, exame_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        exame = ExameRIS.objects.get(pk=exame_id, empresa=empresa)
    except ExameRIS.DoesNotExist:
        return JsonResponse({"erro": "Exame não encontrado"}, status=404)

    if request.method == "GET":
        instancias = exame.instancias_dicom.all()
        return JsonResponse({"instancias": [_instancia_to_dict(i) for i in instancias]})

    arquivos = request.FILES.getlist("arquivos")
    if not arquivos:
        return JsonResponse({"erro": "Nenhum arquivo enviado. Use o campo 'arquivos'."}, status=400)

    ultima = exame.instancias_dicom.order_by("-numero_instancia").first()
    proximo_numero = (ultima.numero_instancia + 1) if ultima else 1

    criadas, erros = [], []
    for f in arquivos:
        if f.size > MAX_DICOM_UPLOAD_BYTES:
            erros.append(f"{f.name}: arquivo maior que {MAX_DICOM_UPLOAD_BYTES // (1024*1024)}MB")
            continue
        try:
            conteudo = f.read()
            ds = pydicom.dcmread(BytesIO(conteudo), force=True, stop_before_pixels=True)
        except Exception:
            erros.append(f"{f.name}: não é um arquivo DICOM válido")
            continue

        f.seek(0)
        inst = InstanciaDicom.objects.create(
            exame=exame,
            arquivo=f,
            sop_instance_uid=str(getattr(ds, "SOPInstanceUID", "")),
            series_instance_uid=str(getattr(ds, "SeriesInstanceUID", "")),
            study_instance_uid=str(getattr(ds, "StudyInstanceUID", "")),
            modalidade_dicom=str(getattr(ds, "Modality", "")),
            numero_instancia=proximo_numero,
            tamanho_bytes=len(conteudo),
        )
        proximo_numero += 1
        criadas.append(_instancia_to_dict(inst))

    status = 201 if criadas else 400
    return JsonResponse({"ok": bool(criadas), "criadas": criadas, "erros": erros}, status=status)


# ─── API: Download/visualização do arquivo DICOM (autenticado) ───────────────

@require_http_methods(["GET"])
def api_ris_dicom_arquivo(request, instancia_id):
    empresa = _empresa(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    try:
        inst = InstanciaDicom.objects.select_related("exame").get(
            pk=instancia_id, exame__empresa=empresa,
        )
    except InstanciaDicom.DoesNotExist:
        raise Http404

    nome_arquivo = f"{inst.sop_instance_uid or inst.id}.dcm"
    return FileResponse(
        inst.arquivo.open("rb"),
        content_type="application/dicom",
        filename=nome_arquivo,
    )
