"""
Views SST — Saúde e Segurança do Trabalho
Endpoints para o painel de saúde ocupacional da empresa.
"""
import csv
import io
import json
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .models import (
    AfastamentoSST,
    ASOOcupacional,
    CATOcupacional,
    DocumentoSST,
    Empresa,
    ExameOcupacional,
    FuncionarioSST,
    eSocialEventoSST,
)
from .views_dashboard import _empresa_autenticada


def _buscar_funcionario(empresa, data):
    """Resolve funcionário por ID ou por nome parcial (case-insensitive)."""
    fid = data.get("funcionario_id")
    if fid:
        return FuncionarioSST.objects.filter(id=fid, empresa=empresa, ativo=True).first()
    nome = (data.get("funcionario_nome") or "").strip()
    if not nome:
        return None
    return (
        FuncionarioSST.objects
        .filter(empresa=empresa, ativo=True, nome__icontains=nome)
        .order_by("nome")
        .first()
    )


def _empresa_sst_autenticada(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return None
    tipo = empresa.tipo_conta or ""
    if tipo not in ("empresa",):
        return None
    return empresa


def _sst_nao_autorizado():
    return JsonResponse({"erro": "nao autenticado ou sem acesso SST"}, status=401)


# ── Dashboard principal ──────────────────────────────────────────────────────

def api_sst_dashboard(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    em_30d = hoje + timedelta(days=30)
    em_60d = hoje + timedelta(days=60)
    inicio_ano = hoje.replace(month=1, day=1)

    func_qs = FuncionarioSST.objects.filter(empresa=empresa)
    func_ativos = func_qs.filter(ativo=True).count()

    # ASOs
    aso_qs = ASOOcupacional.objects.filter(empresa=empresa)
    asos_vencendo = list(
        aso_qs.filter(data_validade__gte=hoje, data_validade__lte=em_30d)
        .select_related("funcionario")
        .order_by("data_validade")[:10]
    )
    asos_vencidos = aso_qs.filter(data_validade__lt=hoje).count()
    asos_a_vencer_60d = aso_qs.filter(data_validade__gte=hoje, data_validade__lte=em_60d).count()

    # Exames
    exam_qs = ExameOcupacional.objects.filter(empresa=empresa)
    exames_atrasados = exam_qs.filter(status="vencido").count()
    exames_vencendo_30d = exam_qs.filter(
        status="pendente", data_validade__gte=hoje, data_validade__lte=em_30d
    ).count()

    # CATs
    cat_qs = CATOcupacional.objects.filter(empresa=empresa)
    cats_abertas = cat_qs.filter(status_esocial__in=("nao_enviado", "pendente")).count()
    cats_recentes = list(
        cat_qs.order_by("-data_acidente")[:5].select_related("funcionario")
    )

    # eSocial
    esocial_qs = eSocialEventoSST.objects.filter(empresa=empresa)
    esocial_pendentes = esocial_qs.filter(status__in=("pendente", "enviado")).count()
    esocial_erros = esocial_qs.filter(status="erro").count()
    esocial_transmitidos_mes = esocial_qs.filter(
        status="transmitido", data_envio__date__gte=hoje.replace(day=1)
    ).count()
    esocial_por_tipo = {}
    for tp in ("S-2210", "S-2220", "S-2240"):
        ultimo = esocial_qs.filter(tipo_evento=tp).order_by("-criado_em").first()
        esocial_por_tipo[tp] = {
            "label": dict(eSocialEventoSST.TIPO_EVENTO).get(tp, tp),
            "status": ultimo.status if ultimo else "nao_enviado",
            "data": ultimo.data_envio.strftime("%d/%m/%Y") if ultimo and ultimo.data_envio else None,
        }

    # Afastamentos
    afas_qs = AfastamentoSST.objects.filter(empresa=empresa)
    afastamentos_ativos = afas_qs.filter(status="ativo").count()
    afastamentos_ano = afas_qs.filter(data_inicio__gte=inicio_ano).count()

    # Absenteísmo
    absenteismo_pct = round((afastamentos_ativos / max(func_ativos, 1)) * 100, 1) if func_ativos else 0.0

    # Documentos SST
    docs_qs = DocumentoSST.objects.filter(empresa=empresa)
    docs_status = {}
    for tp in ("PGR", "PCMSO", "LTCAT", "laudo_insalubridade", "PPP", "CIPA"):
        doc = docs_qs.filter(tipo=tp).order_by("-data_emissao").first()
        if doc:
            vencido = doc.data_validade and doc.data_validade < hoje
            docs_status[tp] = {
                "status": "vencido" if vencido else doc.status,
                "validade": doc.data_validade.strftime("%d/%m/%Y") if doc.data_validade else None,
                "responsavel": doc.responsavel_tecnico,
            }
        else:
            docs_status[tp] = {"status": "nao_cadastrado", "validade": None, "responsavel": ""}

    # Alertas críticos
    alertas = []
    if asos_vencidos:
        alertas.append({"nivel": "critico", "mensagem": f"{asos_vencidos} ASO(s) vencido(s)"})
    if asos_vencendo:
        alertas.append({"nivel": "alto", "mensagem": f"{len(asos_vencendo)} ASO(s) vencem em 30 dias"})
    if exames_atrasados:
        alertas.append({"nivel": "critico", "mensagem": f"{exames_atrasados} exame(s) em atraso"})
    if esocial_erros:
        alertas.append({"nivel": "critico", "mensagem": f"{esocial_erros} evento(s) eSocial com erro"})
    if esocial_pendentes:
        alertas.append({"nivel": "alto", "mensagem": f"{esocial_pendentes} evento(s) eSocial pendentes"})
    if docs_status.get("PGR", {}).get("status") in ("vencido", "nao_cadastrado"):
        alertas.append({"nivel": "alto", "mensagem": "PGR não cadastrado ou vencido"})
    if docs_status.get("PCMSO", {}).get("status") in ("vencido", "nao_cadastrado"):
        alertas.append({"nivel": "alto", "mensagem": "PCMSO não cadastrado ou vencido"})

    return JsonResponse({
        "empresa_nome": empresa.nome,
        "funcionarios_ativos": func_ativos,
        "asos": {
            "vencendo_30d": [
                {
                    "funcionario": a.funcionario.nome,
                    "cargo": a.funcionario.cargo,
                    "tipo": dict(ASOOcupacional.TIPO).get(a.tipo, a.tipo),
                    "validade": a.data_validade.strftime("%d/%m/%Y") if a.data_validade else None,
                    "dias_restantes": (a.data_validade - hoje).days if a.data_validade else None,
                    "resultado": a.resultado,
                }
                for a in asos_vencendo
            ],
            "vencidos": asos_vencidos,
            "a_vencer_60d": asos_a_vencer_60d,
        },
        "exames": {
            "atrasados": exames_atrasados,
            "vencendo_30d": exames_vencendo_30d,
        },
        "cats": {
            "abertas": cats_abertas,
            "recentes": [
                {
                    "funcionario": c.funcionario.nome,
                    "tipo": dict(CATOcupacional.TIPO).get(c.tipo, c.tipo),
                    "gravidade": c.gravidade,
                    "data": c.data_acidente.strftime("%d/%m/%Y"),
                    "status_esocial": c.status_esocial,
                }
                for c in cats_recentes
            ],
        },
        "esocial": {
            "pendentes": esocial_pendentes,
            "erros": esocial_erros,
            "transmitidos_mes": esocial_transmitidos_mes,
            "por_tipo": esocial_por_tipo,
        },
        "afastamentos": {
            "ativos": afastamentos_ativos,
            "no_ano": afastamentos_ano,
            "absenteismo_pct": absenteismo_pct,
        },
        "documentos": docs_status,
        "alertas": alertas,
    })


# ── Funcionários ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_funcionarios(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).select_related("unidade")
        return JsonResponse({
            "funcionarios": [
                {
                    "id": f.id,
                    "nome": f.nome,
                    "cargo": f.cargo,
                    "unidade": f.unidade.nome if f.unidade else None,
                    "data_admissao": f.data_admissao.strftime("%d/%m/%Y") if f.data_admissao else None,
                    "classe_risco": f.classe_risco,
                }
                for f in qs
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = (data.get("nome") or "").strip()
        cargo = (data.get("cargo") or "").strip()
        if not nome or not cargo:
            return JsonResponse({"erro": "nome e cargo são obrigatórios"}, status=400)
        f = FuncionarioSST.objects.create(
            empresa=empresa,
            nome=nome,
            cpf=data.get("cpf", ""),
            matricula=data.get("matricula", ""),
            cargo=cargo,
            setor=data.get("setor", ""),
            classe_risco=data.get("classe_risco", "II"),
        )
        return JsonResponse({"id": f.id, "nome": f.nome}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── ASO ───────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_asos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = ASOOcupacional.objects.filter(empresa=empresa).select_related("funcionario")
        return JsonResponse({
            "asos": [
                {
                    "id": a.id,
                    "funcionario": a.funcionario.nome,
                    "tipo": a.get_tipo_display(),
                    "data_emissao": a.data_emissao.strftime("%d/%m/%Y"),
                    "data_validade": a.data_validade.strftime("%d/%m/%Y") if a.data_validade else None,
                    "resultado": a.get_resultado_display(),
                    "medico": a.medico_responsavel,
                }
                for a in qs[:50]
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado. Cadastre-o primeiro em Funcionários."}, status=404)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        aso = ASOOcupacional.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo=data.get("tipo", "periodico"),
            data_emissao=parse_date(data.get("data_emissao")) or date.today(),
            data_validade=parse_date(data.get("data_validade")),
            medico_responsavel=data.get("medico", ""),
            crm=data.get("crm", ""),
            resultado=data.get("resultado", "apto"),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": aso.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── CAT ───────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_cats(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = CATOcupacional.objects.filter(empresa=empresa).select_related("funcionario")
        return JsonResponse({
            "cats": [
                {
                    "id": c.id,
                    "funcionario": c.funcionario.nome,
                    "tipo": c.get_tipo_display(),
                    "gravidade": c.gravidade,
                    "data_acidente": c.data_acidente.strftime("%d/%m/%Y"),
                    "status_esocial": c.status_esocial,
                    "numero_cat": c.numero_cat,
                }
                for c in qs[:50]
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado. Cadastre-o primeiro em Funcionários."}, status=404)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        cat = CATOcupacional.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo=data.get("tipo", "tipico"),
            gravidade=data.get("gravidade", "leve"),
            data_acidente=parse_date(data.get("data_acidente")) or date.today(),
            descricao=data.get("descricao", ""),
            cid=data.get("cid", ""),
            houve_afastamento=bool(data.get("houve_afastamento")),
        )
        return JsonResponse({"id": cat.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Documentos SST ────────────────────────────────────────────────────────────

@csrf_exempt
def api_documentos_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = DocumentoSST.objects.filter(empresa=empresa)
        return JsonResponse({
            "documentos": [
                {
                    "id": d.id,
                    "tipo": d.tipo,
                    "titulo": d.titulo,
                    "status": d.status,
                    "validade": d.data_validade.strftime("%d/%m/%Y") if d.data_validade else None,
                    "responsavel": d.responsavel_tecnico,
                }
                for d in qs
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        doc = DocumentoSST.objects.create(
            empresa=empresa,
            tipo=data.get("tipo", "outro"),
            titulo=data.get("titulo", ""),
            status=data.get("status", "vigente"),
            responsavel_tecnico=data.get("responsavel", ""),
            registro_profissional=data.get("registro", ""),
            data_emissao=parse_date(data.get("data_emissao")),
            data_validade=parse_date(data.get("data_validade")),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": doc.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Afastamentos ──────────────────────────────────────────────────────────────

@csrf_exempt
def api_afastamentos_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = AfastamentoSST.objects.filter(empresa=empresa).select_related("funcionario")
        return JsonResponse({
            "afastamentos": [
                {
                    "id": a.id,
                    "funcionario": a.funcionario.nome,
                    "motivo": a.get_motivo_display(),
                    "cid": a.cid,
                    "data_inicio": a.data_inicio.strftime("%d/%m/%Y"),
                    "data_retorno": a.data_prevista_retorno.strftime("%d/%m/%Y") if a.data_prevista_retorno else None,
                    "status": a.status,
                }
                for a in qs[:50]
            ]
        })

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Páginas SST ───────────────────────────────────────────────────────────────

def _sst_redirect(request):
    return redirect("/login-empresa/")


def sst_home_redirect(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return redirect("/dashboard-empresa/")


def sst_configuracoes_redirect(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return redirect("/dashboard-empresa/#sst")


def sst_funcionarios_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_funcionarios.html")


def sst_asos_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_asos.html")


def sst_exames_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_exames.html")


def sst_afastamentos_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_afastamentos.html")


def sst_cats_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_cats.html")


def sst_documentos_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_documentos.html")


def sst_esocial_page(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return render(request, "sst_esocial.html")


# ── Exames (API) ──────────────────────────────────────────────────────────────

@csrf_exempt
def api_exames(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        status_filtro = request.GET.get("status", "")
        qs = ExameOcupacional.objects.filter(empresa=empresa).select_related("funcionario")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        return JsonResponse({
            "exames": [
                {
                    "id": e.id,
                    "funcionario_id": e.funcionario_id,
                    "funcionario": e.funcionario.nome,
                    "cargo": e.funcionario.cargo,
                    "tipo_exame": e.tipo_exame,
                    "tipo_exame_label": e.get_tipo_exame_display(),
                    "data_realizacao": e.data_realizacao.strftime("%Y-%m-%d") if e.data_realizacao else None,
                    "data_validade": e.data_validade.strftime("%Y-%m-%d") if e.data_validade else None,
                    "status": e.status,
                    "resultado": e.resultado,
                }
                for e in qs.order_by("data_realizacao")[:200]
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
        tipos_validos = {tipo for tipo, _label in ExameOcupacional.TIPO_EXAME}
        status_validos = {status for status, _label in ExameOcupacional.STATUS}
        tipo = data.get("tipo_exame", "outro")
        if tipo not in tipos_validos:
            return JsonResponse({"erro": "Tipo de exame inválido"}, status=400)
        status = data.get("status", "pendente")
        if status not in status_validos:
            return JsonResponse({"erro": "Status de exame inválido"}, status=400)
        try:
            dr_str = data.get("data_realizacao") or ""
            dr = date.fromisoformat(dr_str) if dr_str else date.today()
        except ValueError:
            dr = date.today()
        try:
            dv_str = data.get("data_validade") or ""
            dv = date.fromisoformat(dv_str) if dv_str else None
        except ValueError:
            dv = None
        exame = ExameOcupacional.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo_exame=tipo,
            data_realizacao=dr,
            data_validade=dv,
            resultado=data.get("resultado", ""),
            status=status,
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": exame.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── eSocial (API) ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_esocial_eventos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = eSocialEventoSST.objects.filter(empresa=empresa).order_by("-criado_em")
        return JsonResponse({
            "eventos": [
                {
                    "id": ev.id,
                    "tipo": ev.tipo_evento,
                    "label": dict(eSocialEventoSST.TIPO_EVENTO).get(ev.tipo_evento, ev.tipo_evento),
                    "status": ev.status,
                    "referencia": ev.referencia,
                    "protocolo": ev.protocolo,
                    "mensagem_erro": ev.mensagem_erro,
                    "data_envio": ev.data_envio.strftime("%d/%m/%Y %H:%M") if ev.data_envio else None,
                    "criado_em": ev.criado_em.strftime("%d/%m/%Y"),
                }
                for ev in qs[:100]
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        ev = eSocialEventoSST.objects.create(
            empresa=empresa,
            tipo_evento=data.get("tipo_evento", "S-2220"),
            referencia=data.get("referencia", ""),
            status="pendente",
        )
        return JsonResponse({"id": ev.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Páginas: Relatórios e Agendamento ────────────────────────────────────────

def sst_relatorios_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_relatorios.html", {"empresa_nome": empresa.nome})


def sst_agendamento_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_agendamento.html", {"empresa_nome": empresa.nome})


def sst_funcionarios_novo_redirect(request):
    return redirect("/sst/funcionarios/?modal=novo")


def sst_documentos_novo_redirect(request):
    return redirect("/sst/documentos/?modal=novo")


# ── API: Relatórios ──────────────────────────────────────────────────────────

def _mes_label(ano, mes):
    meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    return f"{meses[mes-1]}/{str(ano)[2:]}"


def api_relatorios_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    if hoje.month == 12:
        inicio_12m = date(hoje.year, 1, 1)
    else:
        inicio_12m = date(hoje.year - 1, hoje.month + 1, 1)

    # ── Série mensal de ASOs ──────────────────────────────────────────────────
    asos_qs = ASOOcupacional.objects.filter(empresa=empresa, data_emissao__gte=inicio_12m)
    asos_por_mes = defaultdict(int)
    for a in asos_qs.values("data_emissao"):
        d = a["data_emissao"]
        asos_por_mes[(d.year, d.month)] += 1

    # ── Série mensal de CATs ──────────────────────────────────────────────────
    cats_qs = CATOcupacional.objects.filter(empresa=empresa, data_acidente__gte=inicio_12m)
    cats_por_mes = defaultdict(int)
    for c in cats_qs.values("data_acidente"):
        d = c["data_acidente"]
        cats_por_mes[(d.year, d.month)] += 1

    # ── Série mensal de Afastamentos ─────────────────────────────────────────
    afas_qs = AfastamentoSST.objects.filter(empresa=empresa, data_inicio__gte=inicio_12m)
    afas_por_mes = defaultdict(int)
    dias_por_mes = defaultdict(int)
    for a in afas_qs.values("data_inicio", "data_retorno_real", "data_prevista_retorno"):
        d = a["data_inicio"]
        afas_por_mes[(d.year, d.month)] += 1
        fim = a["data_retorno_real"] or a["data_prevista_retorno"] or d
        dias_por_mes[(d.year, d.month)] += max(0, (fim - d).days)

    # ── Monta série ───────────────────────────────────────────────────────────
    serie = []
    m = inicio_12m
    while m <= hoje:
        k = (m.year, m.month)
        serie.append({
            "label": _mes_label(m.year, m.month),
            "ano": m.year,
            "mes": m.month,
            "asos": asos_por_mes.get(k, 0),
            "cats": cats_por_mes.get(k, 0),
            "afastamentos": afas_por_mes.get(k, 0),
            "dias_afastados": dias_por_mes.get(k, 0),
        })
        m = date(m.year + (1 if m.month == 12 else 0), (m.month % 12) + 1, 1)

    # ── Exames por tipo e status ──────────────────────────────────────────────
    exames_status = (
        ExameOcupacional.objects.filter(empresa=empresa)
        .values("tipo_exame", "status")
        .annotate(total=Count("id"))
    )
    exames_resumo = defaultdict(lambda: {"pendente": 0, "realizado": 0, "vencido": 0})
    for e in exames_status:
        exames_resumo[e["tipo_exame"]][e["status"]] = e["total"]

    tipo_labels = dict(ExameOcupacional.TIPO_EXAME)
    exames_out = [
        {
            "tipo": t,
            "label": tipo_labels.get(t, t),
            **cnts,
            "total": sum(cnts.values()),
        }
        for t, cnts in sorted(exames_resumo.items())
    ]

    # ── Documentos compliance ─────────────────────────────────────────────────
    docs_status = (
        DocumentoSST.objects.filter(empresa=empresa)
        .values("tipo", "status")
        .annotate(n=Count("id"))
    )
    docs_out = [{"tipo": d["tipo"], "status": d["status"], "total": d["n"]} for d in docs_status]

    # ── FAP inputs (referência) ───────────────────────────────────────────────
    total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
    total_cats_ano = CATOcupacional.objects.filter(empresa=empresa, data_acidente__year=hoje.year).count()
    total_afas_acidente = AfastamentoSST.objects.filter(
        empresa=empresa,
        data_inicio__year=hoje.year,
        motivo__in=["acidente_trabalho", "doenca_ocupacional"],
    ).count()
    freq_acidente = round((total_cats_ano / total_func * 1000), 2) if total_func > 0 else 0

    fap_inputs = {
        "total_funcionarios": total_func,
        "cats_ano": total_cats_ano,
        "afastamentos_acidente_ano": total_afas_acidente,
        "frequencia_acidente": freq_acidente,
        "referencia": f"Jan–{_mes_label(hoje.year, hoje.month)} {hoje.year}",
    }

    if request.GET.get("formato") == "csv":
        return _exportar_csv_relatorio(serie, empresa.nome)

    return JsonResponse({
        "serie_mensal": serie,
        "exames_por_tipo": exames_out,
        "documentos": docs_out,
        "fap_inputs": fap_inputs,
        "gerado_em": hoje.isoformat(),
    })


def _exportar_csv_relatorio(serie, empresa_nome):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Empresa", empresa_nome])
    w.writerow([])
    w.writerow(["Mês", "ASOs emitidos", "CATs registradas", "Afastamentos", "Dias afastados"])
    for s in serie:
        w.writerow([s["label"], s["asos"], s["cats"], s["afastamentos"], s["dias_afastados"]])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="sst_relatorio_{date.today()}.csv"'
    return resp


# ── Prontuário do Funcionário ─────────────────────────────────────────────────

def sst_prontuario_page(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return redirect("/sst/funcionarios/")
    return render(request, "sst_prontuario.html", {
        "empresa_nome": empresa.nome,
        "funcionario_id": funcionario_id,
        "funcionario_nome": func.nome,
    })


def api_prontuario_funcionario(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

    hoje = date.today()

    # ASOs
    asos = ASOOcupacional.objects.filter(empresa=empresa, funcionario=func).order_by("-data_emissao")
    asos_out = [
        {
            "id": a.id,
            "tipo": a.tipo,
            "tipo_label": a.get_tipo_display(),
            "data_emissao": a.data_emissao.strftime("%d/%m/%Y") if a.data_emissao else None,
            "data_validade": a.data_validade.strftime("%d/%m/%Y") if a.data_validade else None,
            "dias_restantes": (a.data_validade - hoje).days if a.data_validade else None,
            "medico": a.medico_responsavel,
            "resultado": a.resultado,
            "resultado_label": a.get_resultado_display(),
        }
        for a in asos
    ]

    # Exames
    exames = ExameOcupacional.objects.filter(empresa=empresa, funcionario=func).order_by("-data_realizacao")
    exames_out = [
        {
            "id": e.id,
            "tipo_exame": e.tipo_exame,
            "tipo_label": e.get_tipo_exame_display(),
            "data_realizacao": e.data_realizacao.strftime("%d/%m/%Y") if e.data_realizacao else None,
            "data_validade": e.data_validade.strftime("%d/%m/%Y") if e.data_validade else None,
            "dias_restantes": (e.data_validade - hoje).days if e.data_validade else None,
            "status": e.status,
            "resultado": e.resultado,
        }
        for e in exames
    ]

    # CATs
    cats = CATOcupacional.objects.filter(empresa=empresa, funcionario=func).order_by("-data_acidente")
    cats_out = [
        {
            "id": c.id,
            "tipo": c.tipo,
            "tipo_label": c.get_tipo_display(),
            "gravidade": c.gravidade,
            "gravidade_label": c.get_gravidade_display(),
            "data_acidente": c.data_acidente.strftime("%d/%m/%Y") if c.data_acidente else None,
            "cid": c.cid,
            "numero_cat": c.numero_cat,
            "status_esocial": c.status_esocial,
            "houve_afastamento": c.houve_afastamento,
        }
        for c in cats
    ]

    # Afastamentos
    afas = AfastamentoSST.objects.filter(empresa=empresa, funcionario=func).order_by("-data_inicio")
    afas_out = [
        {
            "id": a.id,
            "motivo": a.motivo,
            "motivo_label": a.get_motivo_display(),
            "cid": a.cid,
            "data_inicio": a.data_inicio.strftime("%d/%m/%Y") if a.data_inicio else None,
            "data_retorno": (a.data_retorno_real or a.data_prevista_retorno),
            "data_retorno_fmt": (a.data_retorno_real or a.data_prevista_retorno).strftime("%d/%m/%Y") if (a.data_retorno_real or a.data_prevista_retorno) else None,
            "dias": (a.data_retorno_real or a.data_prevista_retorno or hoje) and ((a.data_retorno_real or a.data_prevista_retorno or hoje) - a.data_inicio).days if a.data_inicio else None,
            "status": a.status,
            "status_label": a.get_status_display(),
        }
        for a in afas
    ]

    # Último ASO
    ultimo_aso = asos_out[0] if asos_out else None
    proximo_vencimento = None
    if ultimo_aso and ultimo_aso["dias_restantes"] is not None:
        proximo_vencimento = ultimo_aso["dias_restantes"]

    return JsonResponse({
        "funcionario": {
            "id": func.id,
            "nome": func.nome,
            "cpf": func.cpf,
            "matricula": func.matricula,
            "cargo": func.cargo,
            "setor": func.setor,
            "classe_risco": func.classe_risco,
            "classe_risco_label": func.get_classe_risco_display(),
            "data_admissao": func.data_admissao.strftime("%d/%m/%Y") if func.data_admissao else None,
            "ativo": func.ativo,
        },
        "resumo": {
            "total_asos": len(asos_out),
            "total_exames": len(exames_out),
            "total_cats": len(cats_out),
            "total_afastamentos": len(afas_out),
            "dias_ate_vencimento_aso": proximo_vencimento,
            "exames_vencidos": sum(1 for e in exames_out if e["status"] == "vencido"),
            "exames_pendentes": sum(1 for e in exames_out if e["status"] == "pendente"),
        },
        "asos": asos_out,
        "exames": exames_out,
        "cats": cats_out,
        "afastamentos": afas_out,
    })


# ── Treinamentos NR ───────────────────────────────────────────────────────────

from .models import TreinamentoNR


def sst_treinamentos_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_treinamentos.html", {"empresa_nome": empresa.nome})


@csrf_exempt
def api_treinamentos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        status_filtro = request.GET.get("status", "")
        nr_filtro = request.GET.get("nr", "")
        qs = TreinamentoNR.objects.filter(empresa=empresa).select_related("funcionario").order_by("data_validade")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        if nr_filtro:
            qs = qs.filter(nr=nr_filtro)
        hoje = date.today()
        return JsonResponse({
            "treinamentos": [
                {
                    "id": t.id,
                    "funcionario_id": t.funcionario_id,
                    "funcionario": t.funcionario.nome,
                    "cargo": t.funcionario.cargo,
                    "nr": t.nr,
                    "nr_label": t.get_nr_display(),
                    "titulo": t.titulo,
                    "instrutor": t.instrutor,
                    "carga_horaria": t.carga_horaria,
                    "data_realizacao": t.data_realizacao.strftime("%d/%m/%Y") if t.data_realizacao else None,
                    "data_validade": t.data_validade.strftime("%d/%m/%Y") if t.data_validade else None,
                    "dias_restantes": (t.data_validade - hoje).days if t.data_validade else None,
                    "status": t.status,
                    "certificado": t.certificado,
                }
                for t in qs[:200]
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
        nr = data.get("nr", "outro")
        try:
            dr = date.fromisoformat(data.get("data_realizacao") or "") if data.get("data_realizacao") else None
        except ValueError:
            dr = None
        try:
            dv = date.fromisoformat(data.get("data_validade") or "") if data.get("data_validade") else None
        except ValueError:
            dv = None
        # Status automático
        hoje = date.today()
        if dv and dv < hoje:
            status_auto = "vencido"
        elif dr and dr <= hoje:
            status_auto = "valido"
        elif dr and dr > hoje:
            status_auto = "agendado"
        else:
            status_auto = "pendente"
        t = TreinamentoNR.objects.create(
            empresa=empresa,
            funcionario=func,
            nr=nr,
            titulo=data.get("titulo", ""),
            instrutor=data.get("instrutor", ""),
            carga_horaria=int(data.get("carga_horaria") or 0),
            data_realizacao=dr,
            data_validade=dv,
            status=data.get("status") or status_auto,
            certificado=data.get("certificado", ""),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": t.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_treinamentos_resumo(request):
    """Resumo de treinamentos por NR e status — para dashboard."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    from django.db.models import Count
    hoje = date.today()
    vencendo_30 = TreinamentoNR.objects.filter(
        empresa=empresa, status="valido",
        data_validade__gte=hoje, data_validade__lte=hoje + timedelta(days=30),
    ).count()
    vencidos = TreinamentoNR.objects.filter(empresa=empresa, status="vencido").count()
    validos = TreinamentoNR.objects.filter(empresa=empresa, status="valido").count()
    pendentes = TreinamentoNR.objects.filter(empresa=empresa, status__in=["pendente","agendado"]).count()

    por_nr = (
        TreinamentoNR.objects.filter(empresa=empresa)
        .values("nr", "status")
        .annotate(total=Count("id"))
    )
    nr_map = {}
    nr_labels = dict(TreinamentoNR.NR_CHOICES)
    for row in por_nr:
        k = row["nr"]
        if k not in nr_map:
            nr_map[k] = {"nr": k, "label": nr_labels.get(k, k), "valido": 0, "vencido": 0, "pendente": 0, "agendado": 0}
        nr_map[k][row["status"]] = row["total"]

    return JsonResponse({
        "vencendo_30d": vencendo_30,
        "vencidos": vencidos,
        "validos": validos,
        "pendentes": pendentes,
        "por_nr": sorted(nr_map.values(), key=lambda x: x["nr"]),
    })


def sst_normas_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_normas.html", {
        "empresa_nome": empresa.nome,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  SST — Configurações
# ─────────────────────────────────────────────────────────────────────────────
from .models import ConfiguracaoSST, EPIItem, EntregaEPI

def sst_configuracoes_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    import json as _json
    config_json = "null"
    if config:
        config_json = _json.dumps({
            "nome_medico_coordenador": config.nome_medico_coordenador,
            "crm_medico": config.crm_medico,
            "especialidade_medico": config.especialidade_medico,
            "nome_engenheiro": config.nome_engenheiro,
            "crea_engenheiro": config.crea_engenheiro,
            "nome_tecnico": config.nome_tecnico,
            "registro_tecnico": config.registro_tecnico,
            "nome_enfermeiro": config.nome_enfermeiro,
            "coren_enfermeiro": config.coren_enfermeiro,
            "alerta_aso_dias": config.alerta_aso_dias,
            "alerta_exame_dias": config.alerta_exame_dias,
            "alerta_treinamento_dias": config.alerta_treinamento_dias,
            "email_alertas": config.email_alertas,
            "alertas_ativos": config.alertas_ativos,
            "cnpj": config.cnpj,
            "cnae_principal": config.cnae_principal,
            "grau_risco": config.grau_risco,
            "numero_funcionarios": config.numero_funcionarios,
            "endereco_completo": config.endereco_completo,
        })
    return render(request, "sst_configuracoes.html", {
        "empresa_nome": empresa.nome,
        "config_json": config_json,
    })


def api_sst_configuracoes(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
        if not config:
            return JsonResponse({"config": None})
        return JsonResponse({"config": {
            "nome_medico_coordenador": config.nome_medico_coordenador,
            "crm_medico": config.crm_medico,
            "especialidade_medico": config.especialidade_medico,
            "nome_engenheiro": config.nome_engenheiro,
            "crea_engenheiro": config.crea_engenheiro,
            "nome_tecnico": config.nome_tecnico,
            "registro_tecnico": config.registro_tecnico,
            "nome_enfermeiro": config.nome_enfermeiro,
            "coren_enfermeiro": config.coren_enfermeiro,
            "alerta_aso_dias": config.alerta_aso_dias,
            "alerta_exame_dias": config.alerta_exame_dias,
            "alerta_treinamento_dias": config.alerta_treinamento_dias,
            "email_alertas": config.email_alertas,
            "alertas_ativos": config.alertas_ativos,
            "cnpj": config.cnpj,
            "cnae_principal": config.cnae_principal,
            "grau_risco": config.grau_risco,
            "numero_funcionarios": config.numero_funcionarios,
            "endereco_completo": config.endereco_completo,
        }})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        config, _ = ConfiguracaoSST.objects.get_or_create(empresa=empresa)
        fields = [
            "nome_medico_coordenador","crm_medico","especialidade_medico",
            "nome_engenheiro","crea_engenheiro","nome_tecnico","registro_tecnico",
            "nome_enfermeiro","coren_enfermeiro","email_alertas",
            "cnpj","cnae_principal","grau_risco","endereco_completo",
        ]
        for f in fields:
            if f in data:
                setattr(config, f, data[f])
        int_fields = ["alerta_aso_dias","alerta_exame_dias","alerta_treinamento_dias","numero_funcionarios"]
        for f in int_fields:
            if f in data:
                try:
                    setattr(config, f, int(data[f]))
                except (ValueError, TypeError):
                    pass
        if "alertas_ativos" in data:
            config.alertas_ativos = bool(data["alertas_ativos"])
        config.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"erro": "método não permitido"}, status=405)


# ─────────────────────────────────────────────────────────────────────────────
#  SST — EPI / EPC
# ─────────────────────────────────────────────────────────────────────────────

def sst_epis_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_epis.html", {"empresa_nome": empresa.nome})


def api_epis_catalogo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        epis = EPIItem.objects.filter(empresa=empresa, ativo=True)
        hoje = date.today()
        return JsonResponse({"epis": [{
            "id": e.id,
            "nome": e.nome,
            "tipo": e.tipo,
            "tipo_label": e.get_tipo_display(),
            "ca_numero": e.ca_numero,
            "validade_ca": e.validade_ca.isoformat() if e.validade_ca else None,
            "dias_validade_ca": (e.validade_ca - hoje).days if e.validade_ca else None,
            "fornecedor": e.fornecedor,
            "descricao": e.descricao,
        } for e in epis]})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = data.get("nome","").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        epi = EPIItem.objects.create(
            empresa=empresa,
            nome=nome,
            tipo=data.get("tipo","outro"),
            ca_numero=data.get("ca_numero",""),
            validade_ca=data.get("validade_ca") or None,
            fornecedor=data.get("fornecedor",""),
            descricao=data.get("descricao",""),
        )
        return JsonResponse({"id": epi.id, "nome": epi.nome}, status=201)
    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_epis_entregas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        func_id = request.GET.get("funcionario_id")
        qs = EntregaEPI.objects.filter(empresa=empresa).select_related("funcionario","epi")
        if func_id:
            qs = qs.filter(funcionario_id=func_id)
        return JsonResponse({"entregas": [{
            "id": e.id,
            "funcionario_id": e.funcionario_id,
            "funcionario_nome": e.funcionario.nome,
            "epi_id": e.epi_id,
            "epi_nome": e.epi.nome,
            "epi_tipo": e.epi.get_tipo_display(),
            "ca_numero": e.epi.ca_numero,
            "data_entrega": e.data_entrega.isoformat(),
            "quantidade": e.quantidade,
            "data_devolucao": e.data_devolucao.isoformat() if e.data_devolucao else None,
            "observacoes": e.observacoes,
            "ativo": e.data_devolucao is None,
        } for e in qs]})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        from .models import FuncionarioSST
        func = FuncionarioSST.objects.filter(id=data.get("funcionario_id"), empresa=empresa).first()
        epi  = EPIItem.objects.filter(id=data.get("epi_id"), empresa=empresa).first()
        if not func or not epi:
            return JsonResponse({"erro": "funcionário ou EPI não encontrado"}, status=404)
        entrega = EntregaEPI.objects.create(
            empresa=empresa,
            funcionario=func,
            epi=epi,
            data_entrega=data.get("data_entrega") or date.today().isoformat(),
            quantidade=int(data.get("quantidade", 1)),
            observacoes=data.get("observacoes",""),
        )
        return JsonResponse({"id": entrega.id}, status=201)
    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_epis_devolver(request, entrega_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    entrega = EntregaEPI.objects.filter(id=entrega_id, empresa=empresa).first()
    if not entrega:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    entrega.data_devolucao = date.today()
    entrega.save(update_fields=["data_devolucao"])
    return JsonResponse({"ok": True})


def api_epis_pdf_ficha(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import FuncionarioSST
    from .pdf_sst import gerar_pdf_ficha_epi
    from django.http import HttpResponse
    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    entregas = EntregaEPI.objects.filter(empresa=empresa, funcionario=func).select_related("epi")
    pdf_bytes = gerar_pdf_ficha_epi(func, entregas, empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="ficha_epi_{func.matricula or func.id}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
#  SST — PDFs de ASO / CAT / Prontuário
# ─────────────────────────────────────────────────────────────────────────────

def api_aso_pdf(request, aso_id):
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_aso
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import ASOOcupacional, FuncionarioSST
    aso = ASOOcupacional.objects.filter(id=aso_id, funcionario__empresa=empresa).select_related("funcionario").first()
    if not aso:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    pdf_bytes = gerar_pdf_aso(aso, aso.funcionario, empresa.nome, config)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="aso_{aso.id}.pdf"'
    return resp


def api_cat_pdf(request, cat_id):
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_cat
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import CATOcupacional
    cat = CATOcupacional.objects.filter(id=cat_id, funcionario__empresa=empresa).select_related("funcionario").first()
    if not cat:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    pdf_bytes = gerar_pdf_cat(cat, cat.funcionario, empresa.nome, config)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="cat_{cat.id}.pdf"'
    return resp


def api_prontuario_pdf(request, funcionario_id):
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_prontuario
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import FuncionarioSST, ASOOcupacional, ExameOcupacional, CATOcupacional, AfastamentoSST
    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    asos        = ASOOcupacional.objects.filter(funcionario=func).order_by("-data_emissao")
    exames      = ExameOcupacional.objects.filter(funcionario=func).order_by("-data_realizacao")
    cats        = CATOcupacional.objects.filter(funcionario=func).order_by("-data_acidente")
    afastamentos = AfastamentoSST.objects.filter(funcionario=func).order_by("-data_inicio")
    pdf_bytes = gerar_pdf_prontuario(func, list(asos), list(exames), list(cats), list(afastamentos), empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="prontuario_{func.matricula or func.id}.pdf"'
    return resp


def api_epis_sem_epi(request):
    """GET → funcionários sem nenhuma entrega de EPI ativa"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import FuncionarioSST, EntregaEPI
    ativos = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
    # IDs que já têm pelo menos uma entrega sem devolução
    com_epi_ids = EntregaEPI.objects.filter(
        empresa=empresa, data_devolucao__isnull=True
    ).values_list("funcionario_id", flat=True)
    sem_epi = ativos.exclude(id__in=com_epi_ids)
    return JsonResponse({
        "funcionarios": [
            {"id": f.id, "nome": f.nome, "cargo": f.cargo or "—"}
            for f in sem_epi
        ],
        "total": sem_epi.count(),
    })


# ── Relatório de Conformidade SST ───────────────────────────────────────────────
def api_sst_conformidade(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    em_30d = hoje + timedelta(days=30)

    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).order_by("nome")
    from .models import EntregaEPI

    resultado = []
    for f in funcionarios:
        # ASO vigente
        aso = ASOOcupacional.objects.filter(funcionario=f, empresa=empresa).order_by("-data_exame").first()
        aso_ok = aso is not None and (aso.data_validade is None or aso.data_validade >= hoje)
        aso_alerta = aso is not None and aso.data_validade and hoje <= aso.data_validade <= em_30d

        # Exames OK
        exames_vencidos = ExameOcupacional.objects.filter(
            empresa=empresa, funcionario=f, status="vencido"
        ).count()
        exames_ok = exames_vencidos == 0

        # EPI entregue
        epi_ativo = EntregaEPI.objects.filter(
            empresa=empresa, funcionario=f, data_devolucao__isnull=True
        ).exists()

        # Treinamentos válidos
        from .models import TreinamentoNR
        trein = TreinamentoNR.objects.filter(empresa=empresa, funcionario=f).order_by("-data_realizacao").first()
        trein_ok = trein is not None and (trein.data_validade is None or trein.data_validade >= hoje)

        # Afastamento ativo
        afastado = AfastamentoSST.objects.filter(empresa=empresa, funcionario=f, status="ativo").exists()

        score = sum([aso_ok, exames_ok, epi_ativo, trein_ok])
        status = "conforme" if score == 4 else ("alerta" if score >= 2 else "critico")

        resultado.append({
            "id": f.id,
            "nome": f.nome,
            "cargo": f.cargo,
            "setor": f.setor,
            "aso_ok": aso_ok,
            "aso_alerta": aso_alerta,
            "aso_validade": str(aso.data_validade) if aso and aso.data_validade else None,
            "exames_ok": exames_ok,
            "exames_vencidos": exames_vencidos,
            "epi_ok": epi_ativo,
            "treinamento_ok": trein_ok,
            "afastado": afastado,
            "score": score,
            "status": status,
        })

    total = len(resultado)
    conformes = sum(1 for r in resultado if r["status"] == "conforme")
    alertas = sum(1 for r in resultado if r["status"] == "alerta")
    criticos = sum(1 for r in resultado if r["status"] == "critico")

    return JsonResponse({
        "resumo": {
            "total": total,
            "conformes": conformes,
            "alertas": alertas,
            "criticos": criticos,
            "indice_conformidade": round(conformes / max(total, 1) * 100, 1),
        },
        "funcionarios": resultado,
    })


def sst_conformidade_page(request):
    from django.shortcuts import render
    return render(request, "sst_conformidade.html")
