"""
Painel de BI / Indicadores SST — SoloCRT SST.

Dashboard executivo que consolida indicadores de todos os módulos de SST numa
única visão. Somente leitura (agrega dados já existentes). Cada bloco é isolado
em try/except para que a ausência de um módulo não derrube o painel. Aditivo.

Endpoints:
  GET  /api/sst/bi/indicadores/   — todos os indicadores consolidados
  GET  /sst/bi/                    — página
"""
import logging
from datetime import timedelta

from django.http import JsonResponse
from django.utils import timezone

from .access_control import api_requer_feature, requer_feature_pacote, requer_permissao_modulo

logger = logging.getLogger(__name__)


def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _safe(fn, default=0):
    try:
        return fn()
    except Exception:
        return default


@api_requer_feature("sst.bi")
def api_bi_indicadores(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    hoje = timezone.now().date()
    em30 = hoje + timedelta(days=30)
    from . import models as M

    # ── Pessoas / documentos base ──────────────────────────────────────────
    funcionarios = _safe(lambda: M.FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count())
    asos_vencidos = _safe(lambda: M.ASOOcupacional.objects.filter(empresa=empresa, data_validade__lt=hoje).count())
    asos_vencendo = _safe(lambda: M.ASOOcupacional.objects.filter(empresa=empresa, data_validade__gte=hoje, data_validade__lte=em30).count())
    exames_vencidos = _safe(lambda: M.ExameOcupacional.objects.filter(empresa=empresa, data_validade__lt=hoje).exclude(status="realizado").count())

    # ── Saúde auditiva / respiratória ──────────────────────────────────────
    audio_pair = _safe(lambda: M.Audiometria.objects.filter(empresa=empresa, sugestivo_pair=True).count())
    audio_retestes = _safe(lambda: M.Audiometria.objects.filter(empresa=empresa, reteste_indicado=True).count())
    espiro_alteradas = _safe(lambda: M.Espirometria.objects.filter(empresa=empresa).exclude(padrao__in=["normal", "indeterminado"]).count())

    # ── Acidentes / investigação ───────────────────────────────────────────
    cats_ano = _safe(lambda: M.CATOcupacional.objects.filter(empresa=empresa, data_acidente__year=hoje.year).count())
    invest_abertas = _safe(lambda: M.InvestigacaoAcidente.objects.filter(empresa=empresa).exclude(status="concluida").count())
    acoes_pendentes = _safe(lambda: M.AcaoCorretivaAcidente.objects.filter(investigacao__empresa=empresa).exclude(status="concluida").count())

    # ── Inspeções / conformidade ───────────────────────────────────────────
    inspecoes_total = _safe(lambda: M.InspecaoSeguranca.objects.filter(empresa=empresa).count())
    ncs = _safe(lambda: M.ItemInspecao.objects.filter(inspecao__empresa=empresa, conforme="nao_conforme").count())

    def _conformidade_media():
        vals = [i.indice_conformidade for i in M.InspecaoSeguranca.objects.filter(empresa=empresa)]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 1) if vals else None
    conformidade_media = _safe(_conformidade_media, None)

    # ── Conformidade documental / treinamentos ─────────────────────────────
    treinamentos_vencidos = _safe(lambda: M.TreinamentoNR.objects.filter(empresa=empresa, data_validade__lt=hoje).count())
    os_ciencias_pendentes = _safe(lambda: M.OrdemServicoCiencia.objects.filter(ordem__empresa=empresa, assinado=False).count())

    # ── CIPA / psicossocial ────────────────────────────────────────────────
    cipa_ativa = _safe(lambda: M.ComissaoCIPA.objects.filter(empresa=empresa, status="ativa").exists())
    psico_ativas = _safe(lambda: M.AvaliacaoPsicossocial.objects.filter(empresa=empresa).exclude(status="encerrada").count())

    # ── Série: acidentes (CAT) por mês, últimos 6 meses ────────────────────
    def _serie_cats():
        serie = []
        for k in range(5, -1, -1):
            ref = (hoje.replace(day=1) - timedelta(days=1))
            # calcula o mês alvo
            y, m = hoje.year, hoje.month - k
            while m <= 0:
                m += 12
                y -= 1
            n = M.CATOcupacional.objects.filter(empresa=empresa, data_acidente__year=y, data_acidente__month=m).count()
            serie.append({"mes": f"{m:02d}/{y}", "valor": n})
        return serie
    serie_cats = _safe(_serie_cats, [])

    return JsonResponse({
        "gerado_em": hoje.isoformat(),
        "pessoas": {
            "funcionarios_ativos": funcionarios,
            "asos_vencidos": asos_vencidos,
            "asos_vencendo_30d": asos_vencendo,
            "exames_vencidos": exames_vencidos,
        },
        "saude": {
            "audiometria_pair": audio_pair,
            "audiometria_retestes": audio_retestes,
            "espirometria_alteradas": espiro_alteradas,
        },
        "acidentes": {
            "cats_ano": cats_ano,
            "investigacoes_abertas": invest_abertas,
            "acoes_pendentes": acoes_pendentes,
            "serie_mensal": serie_cats,
        },
        "conformidade": {
            "inspecoes_total": inspecoes_total,
            "nao_conformidades": ncs,
            "conformidade_media": conformidade_media,
            "treinamentos_vencidos": treinamentos_vencidos,
            "os_ciencias_pendentes": os_ciencias_pendentes,
        },
        "gestao": {
            "cipa_ativa": cipa_ativa,
            "psicossocial_ativas": psico_ativas,
        },
    })


@requer_feature_pacote("sst.bi", "BI / Indicadores SST")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_bi_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_bi.html", {"empresa_nome": empresa.nome})
