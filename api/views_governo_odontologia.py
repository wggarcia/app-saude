"""
Odontologia CEO — Centro de Especialidades Odontológicas
Gestão de atendimentos, produção mensal e faturamento SIASUS/BPA odontológico.
Ministerio da Saúde — Portaria GM/MS 599/2006
"""
import base64
import json
import logging
from datetime import date, timedelta
from collections import defaultdict

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa

logger = logging.getLogger(__name__)

# Procedimentos odontológicos mais comuns (SIGTAP) por especialidade CEO
_PROCEDIMENTOS_CEO = {
    "periodontia": [
        ("0307010013", "Raspagem alisamento e polimento supragengivais"),
        ("0307010048", "Raspagem alisamento subgengival por sextante"),
    ],
    "endodontia": [
        ("0307020010", "Tratamento de canal radicular em dente com 1 canal"),
        ("0307020028", "Tratamento de canal radicular em dente com 2 canais"),
        ("0307020036", "Tratamento de canal radicular em dente com 3 canais"),
    ],
    "cirurgia": [
        ("0307030010", "Alveoloplastia por sextante"),
        ("0307030029", "Exodontia de dente incluso"),
        ("0307030037", "Frenectomia"),
    ],
    "diagnostico": [
        ("0201010585", "Biópsia de boca"),
        ("0201010550", "Citologia esfoliativa de mucosa oral"),
    ],
    "protese": [
        ("0307040010", "Adaptação de prótese dentária"),
    ],
}


def _get_ceo_models():
    from .models import AtendimentoCEO, ProducaoCEO
    return AtendimentoCEO, ProducaoCEO


# ── atendimentos ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ceo_atendimentos(request):
    """GET/POST /api/governo/ceo/atendimentos/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AtendimentoCEO, _ = _get_ceo_models()

    if request.method == "GET":
        qs = AtendimentoCEO.objects.filter(empresa=empresa)
        especialidade = request.GET.get("especialidade")
        status_f = request.GET.get("status")
        data_ini = request.GET.get("data_inicio")
        data_fim = request.GET.get("data_fim")
        q = request.GET.get("q")

        if especialidade:
            qs = qs.filter(especialidade=especialidade)
        if status_f:
            qs = qs.filter(status=status_f)
        if data_ini:
            qs = qs.filter(data_atendimento__gte=data_ini)
        if data_fim:
            qs = qs.filter(data_atendimento__lte=data_fim)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q)
                           | Q(cns_paciente__icontains=q))

        return JsonResponse({
            "total": qs.count(),
            "atendimentos": [
                {
                    "id": a.id,
                    "paciente_nome": a.paciente_nome,
                    "cpf_paciente": a.cpf_paciente,
                    "cns_paciente": a.cns_paciente,
                    "especialidade": a.especialidade,
                    "especialidade_display": a.get_especialidade_display(),
                    "codigo_sigtap": a.codigo_sigtap,
                    "descricao_procedimento": a.descricao_procedimento,
                    "cid10": a.cid10,
                    "dente": a.dente,
                    "face": a.face,
                    "profissional": a.profissional,
                    "cro": a.cro,
                    "data_atendimento": a.data_atendimento.isoformat(),
                    "status": a.status,
                    "status_display": a.get_status_display(),
                    "unidade_origem": a.unidade_origem,
                }
                for a in qs.order_by("-data_atendimento")[:200]
            ],
        })

    data = json.loads(request.body)
    with transaction.atomic():
        atend = AtendimentoCEO.objects.create(
            empresa=empresa,
            paciente_nome=data["paciente_nome"],
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            data_nascimento=data.get("data_nascimento"),
            especialidade=data["especialidade"],
            codigo_sigtap=data.get("codigo_sigtap", ""),
            descricao_procedimento=data.get("descricao_procedimento", ""),
            cid10=data.get("cid10", ""),
            dente=data.get("dente", ""),
            face=data.get("face", ""),
            profissional=data["profissional"],
            cro=data.get("cro", ""),
            data_atendimento=data.get("data_atendimento", date.today().isoformat()),
            status=data.get("status", "atendido"),
            observacoes=data.get("observacoes", ""),
            unidade_origem=data.get("unidade_origem", ""),
        )
    return JsonResponse({"id": atend.id}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
def api_ceo_atendimento_detalhe(request, atend_id):
    """GET/PUT /api/governo/ceo/atendimentos/<id>/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AtendimentoCEO, _ = _get_ceo_models()
    try:
        atend = AtendimentoCEO.objects.get(id=atend_id, empresa=empresa)
    except AtendimentoCEO.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": atend.id,
            "paciente_nome": atend.paciente_nome,
            "cpf_paciente": atend.cpf_paciente,
            "cns_paciente": atend.cns_paciente,
            "data_nascimento": atend.data_nascimento.isoformat() if atend.data_nascimento else None,
            "especialidade": atend.especialidade,
            "especialidade_display": atend.get_especialidade_display(),
            "codigo_sigtap": atend.codigo_sigtap,
            "descricao_procedimento": atend.descricao_procedimento,
            "cid10": atend.cid10,
            "dente": atend.dente,
            "face": atend.face,
            "profissional": atend.profissional,
            "cro": atend.cro,
            "data_atendimento": atend.data_atendimento.isoformat(),
            "status": atend.status,
            "observacoes": atend.observacoes,
            "unidade_origem": atend.unidade_origem,
        })

    data = json.loads(request.body)
    campos = ["status", "cid10", "codigo_sigtap", "descricao_procedimento",
              "dente", "face", "observacoes"]
    for c in campos:
        if c in data:
            setattr(atend, c, data[c])
    atend.save()
    return JsonResponse({"ok": True})


# ── produção / BPA CEO ─────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_ceo_producao(request):
    """GET/POST /api/governo/ceo/producao/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, ProducaoCEO = _get_ceo_models()

    if request.method == "GET":
        qs = ProducaoCEO.objects.filter(empresa=empresa).order_by("-competencia")
        return JsonResponse({
            "producoes": [
                {
                    "id": p.id,
                    "competencia": p.competencia,
                    "cnes": p.cnes,
                    "total_atendimentos": p.total_atendimentos,
                    "total_procedimentos": p.total_procedimentos,
                    "valor_total": float(p.valor_total),
                    "protocolo_datasus": p.protocolo_datasus,
                    "status": p.status,
                    "status_display": p.get_status_display(),
                    "transmitido_em": p.transmitido_em.isoformat() if p.transmitido_em else None,
                }
                for p in qs
            ],
        })

    data = json.loads(request.body)
    competencia = data.get("competencia", date.today().strftime("%Y%m"))
    cnes = data.get("cnes", "")

    prod, created = ProducaoCEO.objects.get_or_create(
        empresa=empresa,
        competencia=competencia,
        cnes=cnes,
        defaults={"status": "aberto"},
    )
    return JsonResponse({"id": prod.id, "criado": created}, status=201 if created else 200)


@csrf_exempt
@require_http_methods(["POST"])
def api_ceo_fechar_producao(request, prod_id):
    """POST /api/governo/ceo/producao/<id>/fechar/ — consolida e gera BPA."""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AtendimentoCEO, ProducaoCEO = _get_ceo_models()
    try:
        prod = ProducaoCEO.objects.get(id=prod_id, empresa=empresa)
    except ProducaoCEO.DoesNotExist:
        return JsonResponse({"erro": "Produção não encontrada"}, status=404)

    if prod.status != "aberto":
        return JsonResponse({"erro": f"Produção já está '{prod.status}'"}, status=400)

    # Busca atendimentos do período
    ano = prod.competencia[:4]
    mes = prod.competencia[4:6]
    qs = AtendimentoCEO.objects.filter(
        empresa=empresa,
        data_atendimento__year=int(ano),
        data_atendimento__month=int(mes),
        status="atendido",
    )

    # Gera BPA-I CEO (formato simplificado — cabeçalho + linhas por procedimento)
    linhas_bpa = []
    for a in qs:
        if a.codigo_sigtap:
            linhas_bpa.append(
                f"02|{prod.cnes or '0000000'}|{prod.competencia}|"
                f"{a.cns_paciente or '000000000000000'}|"
                f"{a.codigo_sigtap}|{a.cid10 or 'Z00'}|1|"
                f"{a.profissional}|{a.data_atendimento.strftime('%Y%m%d')}"
            )

    arquivo_bpa = "\n".join(linhas_bpa)

    with transaction.atomic():
        prod.total_atendimentos = qs.count()
        prod.total_procedimentos = qs.filter(codigo_sigtap__gt="").count()
        prod.arquivo_bpa = arquivo_bpa
        prod.status = "fechado"
        prod.save()

    return JsonResponse({
        "ok": True,
        "total_atendimentos": prod.total_atendimentos,
        "total_procedimentos": prod.total_procedimentos,
        "linhas_bpa": len(linhas_bpa),
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_ceo_transmitir(request, prod_id):
    """
    POST /api/governo/ceo/producao/<id>/transmitir/

    CEO — Centro de Especialidades Odontológicas — fatura pelo SIASUS/SIA-SUS
    (Sistema de Informações Ambulatoriais do SUS), NÃO pelo SISAB.
    O SISAB é exclusivo para Atenção Básica (UBS/ESF); CEO é Atenção Especializada.

    O DATASUS/SIA-SUS NÃO possui API REST pública para envio de BPA.
    O fluxo correto é:
      1. Exportar o arquivo BPA-I (.txt) via este endpoint (formato SIASUS)
      2. Acessar o Posto de Transmissão da Secretaria Municipal/Estadual de Saúde
      3. Transmitir o arquivo pelo programa Transmissor SIA ou pelo portal SCNS:
         https://scns.saude.gov.br/

    Este endpoint gera o arquivo e retorna instruções para a equipe executar
    manualmente no Posto de Transmissão — exatamente como acontece na prática.
    """
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, ProducaoCEO = _get_ceo_models()
    try:
        prod = ProducaoCEO.objects.get(id=prod_id, empresa=empresa)
    except ProducaoCEO.DoesNotExist:
        return JsonResponse({"erro": "Produção não encontrada"}, status=404)

    if prod.status not in ("fechado", "erro"):
        return JsonResponse({"erro": f"Status atual '{prod.status}' não permite transmissão"}, status=400)

    if not prod.arquivo_bpa:
        return JsonResponse({"erro": "Arquivo BPA não gerado — feche a produção primeiro"}, status=400)

    # Codifica arquivo BPA em base64 para transporte via JSON
    arquivo_bytes = prod.arquivo_bpa.encode("latin-1")
    arquivo_b64 = base64.b64encode(arquivo_bytes).decode("ascii")
    nome_arquivo = f"BPA_CEO_{prod.cnes or 'CNES'}_{prod.competencia}.txt"

    with transaction.atomic():
        # Marca como "aguardando_transmissao" — confirmação manual após upload SCNS
        prod.protocolo_datasus = f"BPA-CEO-{prod.competencia}-{prod.pk}-PENDENTE"
        prod.status = "transmitido"      # operador confirma após transmissão real
        prod.transmitido_em = timezone.now()
        prod.save()

    logger.info(
        "BPA CEO gerado empresa=%s prod=%s competencia=%s linhas=%d",
        empresa.id, prod_id, prod.competencia,
        prod.arquivo_bpa.count("\n") + 1,
    )

    return JsonResponse({
        "ok": True,
        "arquivo_bpa_b64": arquivo_b64,
        "nome_arquivo": nome_arquivo,
        "tamanho_bytes": len(arquivo_bytes),
        "linhas_bpa": prod.arquivo_bpa.count("\n") + 1,
        "competencia": prod.competencia,
        "cnes": prod.cnes,
        "protocolo_local": prod.protocolo_datasus,
        "instrucoes": [
            "1. Baixe o arquivo BPA pelo endpoint GET /api/governo/ceo/producao/{id}/bpa-download/",
            "2. Acesse o Posto de Transmissão da sua Secretaria Municipal/Estadual de Saúde",
            "3. Use o programa Transmissor SIA ou o portal SCNS (https://scns.saude.gov.br/)",
            "4. Transmita o arquivo BPA-I no formato SIASUS (Atenção Especializada — CEO)",
            "5. Anote o protocolo retornado pelo DATASUS e registre-o neste sistema",
        ],
        "portal_scns": "https://scns.saude.gov.br/",
        "sistema": "SIASUS/SIA-SUS — Atenção Especializada Odontológica (CEO)",
        "nota": (
            "CEO fatura pelo SIA-SUS (Atenção Especializada), não pelo SISAB. "
            "O DATASUS não disponibiliza API REST para envio de BPA — "
            "a transmissão é realizada pelo Posto de Transmissão da Secretaria de Saúde."
        ),
    })


@require_http_methods(["GET"])
def api_ceo_bpa_download(request, prod_id):
    """
    GET /api/governo/ceo/producao/<id>/bpa-download/
    Retorna o arquivo BPA-I como download (.txt, encoding latin-1).
    """
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, ProducaoCEO = _get_ceo_models()
    try:
        prod = ProducaoCEO.objects.get(id=prod_id, empresa=empresa)
    except ProducaoCEO.DoesNotExist:
        return JsonResponse({"erro": "Produção não encontrada"}, status=404)

    if not prod.arquivo_bpa:
        return JsonResponse({"erro": "Arquivo BPA não gerado — feche a produção primeiro"}, status=400)

    nome = f"BPA_CEO_{prod.cnes or 'CNES'}_{prod.competencia}.txt"
    response = HttpResponse(
        prod.arquivo_bpa.encode("latin-1"),
        content_type="text/plain; charset=latin-1",
    )
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    return response


# ── catálogo de procedimentos por especialidade ────────────────────────────────

def api_ceo_procedimentos(request):
    """GET /api/governo/ceo/procedimentos/?especialidade=endodontia"""
    especialidade = request.GET.get("especialidade")
    if especialidade and especialidade in _PROCEDIMENTOS_CEO:
        procs = [{"codigo": c, "descricao": d} for c, d in _PROCEDIMENTOS_CEO[especialidade]]
    else:
        procs = [
            {"especialidade": esp, "codigo": c, "descricao": d}
            for esp, plist in _PROCEDIMENTOS_CEO.items()
            for c, d in plist
        ]
    return JsonResponse({"procedimentos": procs})


# ── KPIs ───────────────────────────────────────────────────────────────────────

def api_ceo_kpis(request):
    """GET /api/governo/ceo/kpis/"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AtendimentoCEO, ProducaoCEO = _get_ceo_models()

    hoje = date.today()
    mes_ini = hoje.replace(day=1)

    qs_mes = AtendimentoCEO.objects.filter(empresa=empresa, data_atendimento__gte=mes_ini)
    por_esp = dict(
        qs_mes.values_list("especialidade").annotate(n=Count("id")).order_by()
    )
    por_status = dict(
        AtendimentoCEO.objects.filter(empresa=empresa)
        .values_list("status").annotate(n=Count("id")).order_by()
    )
    producoes_pendentes = ProducaoCEO.objects.filter(
        empresa=empresa, status__in=["aberto", "fechado"]
    ).count()

    return JsonResponse({
        "atendimentos_mes": qs_mes.count(),
        "por_especialidade_mes": por_esp,
        "por_status_total": por_status,
        "producoes_pendentes": producoes_pendentes,
        "especialidades_ativas": list(_PROCEDIMENTOS_CEO.keys()),
    })
