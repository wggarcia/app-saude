"""
Ordem de Serviço de SST (NR-01) — SoloCRT SST.

Documento por função com riscos, medidas, EPIs e procedimentos; o trabalhador
dá ciência por link individual (assinatura). PDF da OS incluído. Aditivo.

Endpoints:
  GET  /api/sst/ordens-servico/kpis/                    — KPIs
  GET/POST /api/sst/ordens-servico/                     — lista / cria
  GET/PATCH/DELETE /api/sst/ordens-servico/<id>/        — detalhe
  GET  /api/sst/ordens-servico/<id>/pdf/                — PDF da OS
  GET/POST /api/sst/ordens-servico/<id>/ciencias/       — lista / gera ciências (links)
  GET  /sst/ordens-servico/                             — página gestão
  GET  /os/ciencia/<token>/                             — página pública de ciência
  GET/POST /api/os/ciencia/<token>/                     — dados / registra ciência
"""
import io
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

from .access_control import api_requer_feature, requer_feature_pacote, requer_permissao_modulo, principal_pode_operacao_setorial

logger = logging.getLogger(__name__)

TEAL = colors.HexColor("#00c9a7")
DARK = colors.HexColor("#071c28")
MUTED = colors.HexColor("#7a9fa0")


def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


def _client_ip(request):
    return (request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR", ""))[:64]


def _os_dict(o, completo=False):
    total = o.ciencias.count()
    assinadas = o.ciencias.filter(assinado=True).count()
    d = {
        "id": o.id, "titulo": o.titulo, "funcao": o.funcao, "setor": o.setor,
        "versao": o.versao, "status": o.status,
        "data_emissao": str(o.data_emissao) if o.data_emissao else None,
        "responsavel": o.responsavel,
        "ciencias_total": total, "ciencias_assinadas": assinadas,
    }
    if completo:
        d.update({
            "descricao_atividade": o.descricao_atividade, "riscos": o.riscos,
            "medidas_preventivas": o.medidas_preventivas, "epis_obrigatorios": o.epis_obrigatorios,
            "procedimentos_seguranca": o.procedimentos_seguranca, "condutas_proibidas": o.condutas_proibidas,
        })
    return d


@api_requer_feature("sst.ordem_servico")
def api_ordens_servico_kpis(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import OrdemServicoSST, OrdemServicoCiencia
    qs = OrdemServicoSST.objects.filter(empresa=empresa)
    ciencias = OrdemServicoCiencia.objects.filter(ordem__empresa=empresa)
    return JsonResponse({
        "total": qs.count(),
        "vigentes": qs.filter(status="vigente").count(),
        "ciencias_pendentes": ciencias.filter(assinado=False).count(),
        "ciencias_assinadas": ciencias.filter(assinado=True).count(),
    })


@api_requer_feature("sst.ordem_servico")
def api_ordens_servico(request):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import OrdemServicoSST

    if request.method == "GET":
        qs = OrdemServicoSST.objects.filter(empresa=empresa)
        if request.GET.get("status"):
            qs = qs.filter(status=request.GET["status"])
        return JsonResponse({"total": qs.count(), "ordens": [_os_dict(o) for o in qs[:100]]})

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        try:
            data = _json(request)
            if not data.get("titulo") or not data.get("funcao"):
                return JsonResponse({"erro": "titulo e funcao são obrigatórios"}, status=400)
            o = OrdemServicoSST.objects.create(
                empresa=empresa, titulo=data["titulo"], funcao=data["funcao"],
                setor=data.get("setor", ""), descricao_atividade=data.get("descricao_atividade", ""),
                riscos=data.get("riscos", ""), medidas_preventivas=data.get("medidas_preventivas", ""),
                epis_obrigatorios=data.get("epis_obrigatorios", ""),
                procedimentos_seguranca=data.get("procedimentos_seguranca", ""),
                condutas_proibidas=data.get("condutas_proibidas", ""),
                responsavel=data.get("responsavel", ""), data_emissao=data.get("data_emissao") or None,
            )
            return JsonResponse({"ok": True, "data": _os_dict(o, completo=True)}, status=201)
        except Exception:
            logger.exception("Erro ao criar OS")
            return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.ordem_servico")
def api_ordem_servico_detalhe(request, os_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import OrdemServicoSST
    try:
        o = OrdemServicoSST.objects.get(id=os_id, empresa=empresa)
    except OrdemServicoSST.DoesNotExist:
        return JsonResponse({"erro": "Ordem de Serviço não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_os_dict(o, completo=True))

    if request.method in ("PATCH", "PUT"):
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        for f in ("titulo", "funcao", "setor", "descricao_atividade", "riscos",
                  "medidas_preventivas", "epis_obrigatorios", "procedimentos_seguranca",
                  "condutas_proibidas", "responsavel", "status", "versao"):
            if f in data:
                setattr(o, f, data[f])
        if "data_emissao" in data:
            o.data_emissao = data["data_emissao"] or None
        o.save()
        return JsonResponse({"ok": True, "data": _os_dict(o, completo=True)})

    if request.method == "DELETE":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        o.delete()
        return JsonResponse({"ok": True, "msg": "Ordem de Serviço removida"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.ordem_servico")
def api_ordem_servico_ciencias(request, os_id):
    """GET lista ciências + links · POST gera ciências (para funcionarios ou todos)."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    import secrets
    from .models import OrdemServicoSST, OrdemServicoCiencia, FuncionarioSST
    try:
        o = OrdemServicoSST.objects.get(id=os_id, empresa=empresa)
    except OrdemServicoSST.DoesNotExist:
        return JsonResponse({"erro": "Ordem de Serviço não encontrada"}, status=404)

    if request.method == "GET":
        base = f"{request.scheme}://{request.get_host()}"
        cs = o.ciencias.select_related("funcionario")
        return JsonResponse({
            "total": cs.count(),
            "ciencias": [{
                "id": c.id, "funcionario_nome": c.funcionario.nome,
                "assinado": c.assinado,
                "data_ciencia": c.data_ciencia.isoformat() if c.data_ciencia else None,
                "link": f"{base}/os/ciencia/{c.token}/" if c.token else None,
            } for c in cs],
        })

    if request.method == "POST":
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({"erro": "Sem permissão"}, status=403)
        data = _json(request)
        if data.get("todos"):
            funcs = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
        else:
            ids = data.get("funcionario_ids") or []
            if not isinstance(ids, list) or not ids:
                return JsonResponse({"erro": "Informe funcionario_ids ou todos=true"}, status=400)
            funcs = FuncionarioSST.objects.filter(empresa=empresa, id__in=ids)
        criados = 0
        for f in funcs:
            c, novo = OrdemServicoCiencia.objects.get_or_create(ordem=o, funcionario=f)
            if not c.token:
                c.token = secrets.token_urlsafe(24)
                c.save(update_fields=["token"])
            if novo:
                criados += 1
        return JsonResponse({"ok": True, "criados": criados, "total": o.ciencias.count()})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@api_requer_feature("sst.ordem_servico")
def api_ordem_servico_pdf(request, os_id):
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    from .models import OrdemServicoSST
    try:
        o = OrdemServicoSST.objects.get(id=os_id, empresa=empresa)
    except OrdemServicoSST.DoesNotExist:
        return JsonResponse({"erro": "Ordem de Serviço não encontrada"}, status=404)
    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                                leftMargin=2 * cm, rightMargin=2 * cm)
        t = ParagraphStyle("t", fontSize=15, fontName="Helvetica-Bold", textColor=DARK, leading=19)
        h = ParagraphStyle("h", fontSize=10.5, fontName="Helvetica-Bold", textColor=DARK, leading=14, spaceBefore=9, spaceAfter=3)
        b = ParagraphStyle("b", fontSize=9.5, fontName="Helvetica", textColor=colors.black, leading=14)
        sub = ParagraphStyle("s", fontSize=9, fontName="Helvetica", textColor=MUTED, leading=13, spaceAfter=6)
        el = [Paragraph("Ordem de Serviço de SST", t),
              Paragraph(f"{empresa.nome} · NR-01 · Função: {o.funcao} · Versão {o.versao}", sub),
              HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=8)]
        for titulo, campo in [
            ("Setor", o.setor), ("Descrição das atividades", o.descricao_atividade),
            ("Riscos ocupacionais", o.riscos), ("Medidas de prevenção", o.medidas_preventivas),
            ("EPIs obrigatórios", o.epis_obrigatorios),
            ("Procedimentos seguros de trabalho", o.procedimentos_seguranca),
            ("Condutas proibidas", o.condutas_proibidas),
        ]:
            if campo:
                el.append(Paragraph(titulo, h))
                el.append(Paragraph(campo.replace("\n", "<br/>"), b))
        el.append(Spacer(1, 26))
        el.append(HRFlowable(width="60%", thickness=0.5, color=MUTED))
        el.append(Paragraph("Ciência do trabalhador: _________________________  Data: ___/___/______", sub))
        el.append(Paragraph(f"Responsável: {o.responsavel or '—'}", sub))
        doc.build(el)
        buf.seek(0)
        resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
        resp["Content-Disposition"] = f'inline; filename="os_{o.id}.pdf"'
        return resp
    except Exception:
        logger.exception("Erro ao gerar PDF da OS")
        return JsonResponse({"erro": "Erro interno ao processar a solicitação."}, status=500)


@requer_feature_pacote("sst.ordem_servico", "Ordem de Serviço NR-01")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_ordem_servico_page(request):
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_ordem_servico.html", {"empresa_nome": empresa.nome})


# ── Ciência pública (trabalhador assina por link) ────────────────────────────

def _ciencia_por_token(token):
    from .models import OrdemServicoCiencia
    if not token:
        return None
    return OrdemServicoCiencia.objects.select_related("ordem", "funcionario").filter(token=token).first()


def os_ciencia_page(request, token):
    from django.shortcuts import render
    c = _ciencia_por_token(token)
    if not c:
        return render(request, "os_ciencia.html", {"invalido": True, "token": ""})
    return render(request, "os_ciencia.html", {
        "invalido": False, "token": token,
        "funcionario": c.funcionario.nome, "os_titulo": c.ordem.titulo, "funcao": c.ordem.funcao,
    })


def api_os_ciencia_publico(request, token):
    c = _ciencia_por_token(token)
    if not c:
        return JsonResponse({"erro": "Link inválido"}, status=403)
    o = c.ordem

    if request.method == "GET":
        return JsonResponse({
            "funcionario": c.funcionario.nome, "ja_assinou": c.assinado,
            "os": {
                "titulo": o.titulo, "funcao": o.funcao, "setor": o.setor,
                "descricao_atividade": o.descricao_atividade, "riscos": o.riscos,
                "medidas_preventivas": o.medidas_preventivas, "epis_obrigatorios": o.epis_obrigatorios,
                "procedimentos_seguranca": o.procedimentos_seguranca, "condutas_proibidas": o.condutas_proibidas,
            },
        })

    if request.method == "POST":
        if c.assinado:
            return JsonResponse({"erro": "Você já deu ciência a esta Ordem de Serviço"}, status=409)
        data = _json(request)
        c.assinado = True
        c.assinatura_base64 = data.get("assinatura_base64", "")
        c.data_ciencia = timezone.now()
        c.ip = _client_ip(request)
        c.save(update_fields=["assinado", "assinatura_base64", "data_ciencia", "ip"])
        return JsonResponse({"ok": True, "msg": "Ciência registrada. Obrigado!"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)
