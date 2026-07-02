"""
CAPS / Saúde Mental — RAPS (Rede de Atenção Psicossocial)
GET/POST /api/governo/caps/unidades
GET/POST /api/governo/caps/atendimentos
GET/POST /api/governo/caps/encaminhamentos
GET      /api/governo/caps/kpis
GET      /api/governo/caps/raas-exportar   Exporta produção para RAAS/DATASUS
"""
import json
import math

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request


def _gov(request):
    emp = empresa_autenticada_from_request(request)
    if emp and emp.tipo_conta == "governo":
        return emp
    return None


# ── Unidades CAPS ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_caps_unidades(request):
    """GET lista | POST cria unidade CAPS."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import UnidadeCAPS

    if request.method == "GET":
        apenas_ativas = request.GET.get("ativas", "true").lower() == "true"
        qs = UnidadeCAPS.objects.filter(empresa=empresa)
        if apenas_ativas:
            qs = qs.filter(ativo=True)
        return JsonResponse({
            "total": qs.count(),
            "unidades": [_caps_dict(u) for u in qs],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        nome = (body.get("nome") or "").strip()
        tipo = body.get("tipo") or "caps_i"
        if not nome:
            return JsonResponse({"erro": "Campo 'nome' obrigatório"}, status=400)

        tipos_validos = [t[0] for t in UnidadeCAPS.TIPO_CAPS]
        if tipo not in tipos_validos:
            return JsonResponse({"erro": f"Tipo inválido. Opções: {tipos_validos}"}, status=400)

        unidade = UnidadeCAPS.objects.create(
            empresa    = empresa,
            nome       = nome,
            tipo       = tipo,
            cnes       = (body.get("cnes") or "").strip(),
            municipio  = (body.get("municipio") or "").strip(),
            uf         = (body.get("uf") or "").strip().upper()[:2],
            endereco   = (body.get("endereco") or "").strip(),
            telefone   = (body.get("telefone") or "").strip(),
        )
        return JsonResponse({"status": "criado", "id": unidade.id, "unidade": _caps_dict(unidade)}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
def api_caps_unidade_detalhe(request, caps_id):
    """GET detalhe | PATCH atualiza | DELETE desativa."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import UnidadeCAPS

    try:
        unidade = UnidadeCAPS.objects.get(id=caps_id, empresa=empresa)
    except UnidadeCAPS.DoesNotExist:
        return JsonResponse({"erro": "Unidade CAPS não encontrada"}, status=404)

    if request.method == "GET":
        from .models import AtendimentoSaudeMental
        total_atend = AtendimentoSaudeMental.objects.filter(caps=unidade).count()
        return JsonResponse({**_caps_dict(unidade), "total_atendimentos": total_atend})

    if request.method in ("PATCH", "PUT"):
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        for field in ("nome", "tipo", "cnes", "municipio", "uf", "endereco", "telefone"):
            if field in body:
                setattr(unidade, field, (body[field] or "").strip())
        if "ativo" in body:
            unidade.ativo = bool(body["ativo"])
        unidade.save()
        return JsonResponse({"status": "atualizado", "unidade": _caps_dict(unidade)})

    if request.method == "DELETE":
        unidade.ativo = False
        unidade.save(update_fields=["ativo"])
        return JsonResponse({"status": "desativado"})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Atendimentos ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_caps_atendimentos(request):
    """GET lista | POST registra atendimento."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import AtendimentoSaudeMental, UnidadeCAPS

    if request.method == "GET":
        caps_id      = request.GET.get("caps_id")
        competencia  = request.GET.get("competencia")
        enviado_raas = request.GET.get("enviado_raas")
        page         = max(1, int(request.GET.get("page") or 1))
        page_size    = 50

        qs = AtendimentoSaudeMental.objects.filter(empresa=empresa).select_related("caps")
        if caps_id:
            qs = qs.filter(caps_id=caps_id)
        if competencia:
            qs = qs.filter(competencia=competencia)
        if enviado_raas is not None:
            qs = qs.filter(enviado_raas=enviado_raas.lower() == "true")

        total  = qs.count()
        offset = (page - 1) * page_size
        items  = qs[offset: offset + page_size]

        return JsonResponse({
            "total":   total,
            "pagina":  page,
            "paginas": math.ceil(total / page_size) if total else 1,
            "atendimentos": [_atend_dict(a) for a in items],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        caps_id = body.get("caps_id")
        if not caps_id:
            return JsonResponse({"erro": "Campo 'caps_id' obrigatório"}, status=400)

        try:
            caps = UnidadeCAPS.objects.get(id=caps_id, empresa=empresa, ativo=True)
        except UnidadeCAPS.DoesNotExist:
            return JsonResponse({"erro": "Unidade CAPS não encontrada"}, status=404)

        paciente_nome = (body.get("paciente_nome") or "").strip()
        data_atendimento = body.get("data_atendimento")
        competencia      = body.get("competencia")

        if not paciente_nome:
            return JsonResponse({"erro": "Campo 'paciente_nome' obrigatório"}, status=400)
        if not data_atendimento:
            return JsonResponse({"erro": "Campo 'data_atendimento' obrigatório"}, status=400)
        if not competencia:
            # Deriva da data de atendimento automaticamente
            try:
                from datetime import datetime
                d = datetime.strptime(data_atendimento, "%Y-%m-%d")
                competencia = d.strftime("%Y%m")
            except ValueError:
                competencia = ""

        atend = AtendimentoSaudeMental.objects.create(
            caps              = caps,
            empresa           = empresa,
            paciente_nome     = paciente_nome,
            cns               = (body.get("cns") or "").strip(),
            cpf               = (body.get("cpf") or "").strip().replace(".", "").replace("-", ""),
            cid_principal     = (body.get("cid_principal") or "").strip().upper(),
            cid_secundario    = (body.get("cid_secundario") or "").strip().upper(),
            modalidade        = body.get("modalidade") or "individual",
            profissional      = (body.get("profissional") or "").strip(),
            cbo_profissional  = (body.get("cbo_profissional") or "").strip(),
            data_atendimento  = data_atendimento,
            competencia       = competencia,
            procedimento_sigtap = (body.get("procedimento_sigtap") or "").strip(),
            observacoes       = (body.get("observacoes") or "").strip(),
        )
        return JsonResponse({"status": "criado", "id": atend.id}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Encaminhamentos RAPS ──────────────────────────────────────────────────────

@csrf_exempt
def api_caps_encaminhamentos(request):
    """GET lista | POST cria encaminhamento RAPS."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import EncaminhamentoRAPS

    if request.method == "GET":
        status    = request.GET.get("status")
        page      = max(1, int(request.GET.get("page") or 1))
        page_size = 50

        qs = EncaminhamentoRAPS.objects.filter(empresa=empresa)
        if status:
            qs = qs.filter(status=status)

        total  = qs.count()
        offset = (page - 1) * page_size
        items  = qs[offset: offset + page_size]

        return JsonResponse({
            "total":   total,
            "pagina":  page,
            "paginas": math.ceil(total / page_size) if total else 1,
            "encaminhamentos": [_encam_dict(e) for e in items],
        })

    if request.method == "POST":
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        paciente_nome = (body.get("paciente_nome") or "").strip()
        origem        = (body.get("origem_descricao") or "").strip()
        destino_tipo  = body.get("destino_tipo") or "caps"
        destino_desc  = (body.get("destino_descricao") or "").strip()
        data_enc      = body.get("data_encaminhamento")

        if not paciente_nome or not data_enc:
            return JsonResponse({"erro": "Campos 'paciente_nome' e 'data_encaminhamento' obrigatórios"}, status=400)

        enc = EncaminhamentoRAPS.objects.create(
            empresa            = empresa,
            paciente_nome      = paciente_nome,
            cns                = (body.get("cns") or "").strip(),
            origem_descricao   = origem,
            destino_tipo       = destino_tipo,
            destino_descricao  = destino_desc,
            cid                = (body.get("cid") or "").strip().upper(),
            motivo             = (body.get("motivo") or "").strip(),
            data_encaminhamento = data_enc,
        )
        return JsonResponse({"status": "criado", "id": enc.id}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
def api_caps_encaminhamento_acao(request, enc_id):
    """PATCH /api/governo/caps/encaminhamentos/<id>/acao — atualiza status."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import EncaminhamentoRAPS

    try:
        enc = EncaminhamentoRAPS.objects.get(id=enc_id, empresa=empresa)
    except EncaminhamentoRAPS.DoesNotExist:
        return JsonResponse({"erro": "Encaminhamento não encontrado"}, status=404)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    status_validos = [s[0] for s in EncaminhamentoRAPS.STATUS]
    novo_status    = body.get("status")
    if novo_status and novo_status not in status_validos:
        return JsonResponse({"erro": f"Status inválido. Opções: {status_validos}"}, status=400)

    if novo_status:
        enc.status = novo_status
    if body.get("data_realizacao"):
        enc.data_realizacao = body["data_realizacao"]

    enc.save()
    return JsonResponse({"status": "atualizado", "encaminhamento": _encam_dict(enc)})


# ── KPIs ─────────────────────────────────────────────────────────────────────

def api_caps_kpis(request):
    """GET /api/governo/caps/kpis — indicadores CAPS por competência."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import UnidadeCAPS, AtendimentoSaudeMental, EncaminhamentoRAPS
    from django.db.models import Count, Q
    from datetime import date

    competencia = request.GET.get("competencia") or date.today().strftime("%Y%m")

    caps_total   = UnidadeCAPS.objects.filter(empresa=empresa, ativo=True).count()
    atend_comp   = AtendimentoSaudeMental.objects.filter(empresa=empresa, competencia=competencia)
    enc_pendentes = EncaminhamentoRAPS.objects.filter(empresa=empresa, status="pendente").count()

    por_modalidade = (
        atend_comp.values("modalidade").annotate(total=Count("id")).order_by("-total")
    )
    por_caps = (
        atend_comp.values("caps__nome").annotate(total=Count("id")).order_by("-total")
    )
    por_cid = (
        atend_comp.exclude(cid_principal="")
        .values("cid_principal").annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    return JsonResponse({
        "competencia":         competencia,
        "total_caps_ativos":   caps_total,
        "total_atendimentos":  atend_comp.count(),
        "pendentes_raas":      atend_comp.filter(enviado_raas=False).count(),
        "encaminhamentos_pendentes": enc_pendentes,
        "por_modalidade": list(por_modalidade),
        "por_caps":       [{"caps": p["caps__nome"], "total": p["total"]} for p in por_caps],
        "top_cids":       list(por_cid),
    })


def api_caps_raas_exportar(request):
    """
    GET /api/governo/caps/raas-exportar?competencia=AAAAMM
    Exporta os atendimentos em formato compatível com o RAAS/SIASUS.
    Retorna JSON estruturado; cliente converte para o layout DATASUS.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import AtendimentoSaudeMental
    from datetime import date

    competencia = request.GET.get("competencia") or date.today().strftime("%Y%m")

    atendimentos = AtendimentoSaudeMental.objects.filter(
        empresa=empresa, competencia=competencia
    ).select_related("caps")

    registros = []
    for a in atendimentos:
        registros.append({
            "co_municipio_gestor":  empresa.municipio_ibge if hasattr(empresa, "municipio_ibge") else "",
            "co_unidade_saude":     a.caps.cnes,
            "co_procedimento":      a.procedimento_sigtap or "0302060014",  # Atendimento p/ saúde mental default
            "co_cid_principal":     a.cid_principal,
            "no_paciente":          a.paciente_nome,
            "nu_cns_paciente":      a.cns,
            "nu_cpf_paciente":      a.cpf,
            "dt_atendimento":       a.data_atendimento.strftime("%Y%m%d") if a.data_atendimento else "",
            "co_modalidade":        a.modalidade,
            "co_profissional_cbo":  a.cbo_profissional,
            "competencia":          competencia,
        })

    # Marca como incluídos no RAAS apenas quando explicitamente confirmado
    if request.GET.get("confirmar") == "true":
        atendimentos.update(enviado_raas=True)

    return JsonResponse({
        "competencia":       competencia,
        "total_registros":   len(registros),
        "formato":           "RAAS-SM (Saúde Mental)",
        "registros":         registros,
        "aviso":             (
            "Converta para o layout fixo .txt do RAAS antes de submeter ao DATASUS. "
            "O layout completo está em: http://datasus.saude.gov.br/sistemas-e-aplicativos/"
        ),
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _caps_dict(u):
    return {
        "id":       u.id,
        "nome":     u.nome,
        "tipo":     u.tipo,
        "tipo_display": u.get_tipo_display(),
        "cnes":     u.cnes,
        "municipio": u.municipio,
        "uf":       u.uf,
        "endereco": u.endereco,
        "telefone": u.telefone,
        "ativo":    u.ativo,
    }


def _atend_dict(a):
    return {
        "id":               a.id,
        "caps_id":          a.caps_id,
        "caps_nome":        a.caps.nome if a.caps_id else "",
        "paciente_nome":    a.paciente_nome,
        "cns":              a.cns,
        "cid_principal":    a.cid_principal,
        "cid_secundario":   a.cid_secundario,
        "modalidade":       a.modalidade,
        "profissional":     a.profissional,
        "data_atendimento": a.data_atendimento.isoformat() if a.data_atendimento else None,
        "competencia":      a.competencia,
        "procedimento_sigtap": a.procedimento_sigtap,
        "enviado_raas":     a.enviado_raas,
    }


def _encam_dict(e):
    return {
        "id":                  e.id,
        "paciente_nome":       e.paciente_nome,
        "cns":                 e.cns,
        "origem_descricao":    e.origem_descricao,
        "destino_tipo":        e.destino_tipo,
        "destino_tipo_display": e.get_destino_tipo_display(),
        "destino_descricao":   e.destino_descricao,
        "cid":                 e.cid,
        "status":              e.status,
        "data_encaminhamento": e.data_encaminhamento.isoformat() if e.data_encaminhamento else None,
        "data_realizacao":     e.data_realizacao.isoformat() if e.data_realizacao else None,
    }
