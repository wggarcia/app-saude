"""
Ordem de Produção Industrial — Motor Anti-Erro (Farmácia / Indústria)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Previne erro no preenchimento de ordens de produção antes que avancem de etapa.

GET/POST  /api/producao/especificacoes            lista | cria MBR
GET/PATCH /api/producao/especificacoes/<id>       detalhe | edita | inativa
GET/POST  /api/producao/ordens                     lista | abre ordem
GET       /api/producao/ordens/<id>                detalhe completo (etapas, campos, desvios)
POST      /api/producao/ordens/<id>/campo          preenche 1 campo com validação em tempo real
GET       /api/producao/ordens/<id>/validar        valida a ordem inteira
PATCH     /api/producao/ordens/<id>/avancar        avança etapa/status (guarda FSM)
POST      /api/producao/ordens/<id>/assinar        assina uma etapa (ICP-Brasil)
GET/PATCH /api/producao/ordens/<id>/desvios        lista | resolve desvio
GET       /api/producao/kpis                        painel RFT / desvios

Isolado no setor farmácia (LGPD). Toda alteração grava FarmaciaAuditLog.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from .access_control import (requer_setor, requer_operacao_page,
                             requer_permissao_modulo, get_setor)
from .services.auth_session import empresa_autenticada_from_request
from . import producao_validacao as val
from . import producao_fsm as fsm
from . import producao_ia as pia


# ── Helpers ───────────────────────────────────────────────────────────────────

def _farm(request):
    emp = empresa_autenticada_from_request(request)
    if emp and get_setor(emp) == "farmacia":
        return emp
    return None


def _get_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")


def _usuario(request):
    s = getattr(request, "session", None)
    if s:
        for k in ("principal_nome", "usuario_nome", "nome_principal"):
            v = s.get(k)
            if v:
                return str(v)[:160]
    return ""


def _audit(empresa, acao, modelo, objeto_id, descricao, request=None,
           dados_antes=None, dados_depois=None):
    from .models import FarmaciaAuditLog
    FarmaciaAuditLog.objects.create(
        empresa=empresa, acao=acao, modelo=modelo, objeto_id=objeto_id,
        descricao=descricao[:5000], dados_antes=dados_antes, dados_depois=dados_depois,
        usuario=_usuario(request) if request else "",
        ip=_get_ip(request) if request else None,
    )


def _body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _dec(value, default=None):
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return default


# ── Página ────────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("farmacia")
@requer_operacao_page
@requer_permissao_modulo("farmacia.gestao")
def producao_industrial_page(request):
    return render(request, "producao_industrial.html")


# ── Especificações (MBR) ──────────────────────────────────────────────────────

@csrf_exempt
def api_producao_especificacoes(request):
    """GET lista | POST cria especificação-mestre."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import EspecificacaoProducao

    if request.method == "GET":
        inclui_inativas = request.GET.get("todas") == "1"
        qs = EspecificacaoProducao.objects.filter(empresa=empresa)
        if not inclui_inativas:
            qs = qs.filter(ativo=True)
        dados = [{
            "id": e.id, "codigo_produto": e.codigo_produto, "nome": e.nome,
            "forma_farmaceutica": e.forma_farmaceutica, "concentracao": e.concentracao,
            "versao": e.versao, "ativo": e.ativo,
            "n_etapas": len(e.lista_etapas()),
            "n_campos": len(e.campos if isinstance(e.campos, list) else []),
        } for e in qs]
        return JsonResponse({"especificacoes": dados})

    if request.method == "POST":
        d = _body(request)
        codigo = (d.get("codigo_produto") or "").strip()
        nome = (d.get("nome") or "").strip()
        if not codigo or not nome:
            return JsonResponse({"erro": "Informe código do produto e nome."}, status=400)

        etapas = d.get("etapas") if isinstance(d.get("etapas"), list) else []
        campos = d.get("campos") if isinstance(d.get("campos"), list) else []
        if not etapas:
            return JsonResponse({"erro": "Defina ao menos uma etapa de produção."}, status=400)

        versao = int(d.get("versao") or 1)
        if EspecificacaoProducao.objects.filter(
                empresa=empresa, codigo_produto=codigo, versao=versao).exists():
            return JsonResponse({"erro": f"Já existe versão {versao} para {codigo}."}, status=409)

        esp = EspecificacaoProducao.objects.create(
            empresa=empresa, codigo_produto=codigo, nome=nome,
            forma_farmaceutica=d.get("forma_farmaceutica") or "comprimido",
            concentracao=d.get("concentracao") or "", versao=versao,
            unidade_rendimento=d.get("unidade_rendimento") or "unid",
            tamanho_lote_padrao=_dec(d.get("tamanho_lote_padrao"), Decimal("1")),
            rendimento_teorico=_dec(d.get("rendimento_teorico"), Decimal("0")),
            faixa_rendimento_min=_dec(d.get("faixa_rendimento_min"), Decimal("98")),
            faixa_rendimento_max=_dec(d.get("faixa_rendimento_max"), Decimal("102")),
            etapas=etapas, campos=campos,
        )
        _audit(empresa, "criar", "EspecificacaoProducao", esp.id,
               f"MBR criado: {codigo} v{versao} — {nome}", request,
               dados_depois={"codigo": codigo, "versao": versao})
        return JsonResponse({"ok": True, "id": esp.id}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


@csrf_exempt
def api_producao_especificacao_detail(request, esp_id):
    """GET detalhe | PATCH edita (gera nova versão em mudança de campos) | inativa."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import EspecificacaoProducao

    esp = EspecificacaoProducao.objects.filter(empresa=empresa, id=esp_id).first()
    if not esp:
        return JsonResponse({"erro": "Especificação não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": esp.id, "codigo_produto": esp.codigo_produto, "nome": esp.nome,
            "forma_farmaceutica": esp.forma_farmaceutica, "concentracao": esp.concentracao,
            "versao": esp.versao, "ativo": esp.ativo,
            "unidade_rendimento": esp.unidade_rendimento,
            "tamanho_lote_padrao": str(esp.tamanho_lote_padrao),
            "rendimento_teorico": str(esp.rendimento_teorico),
            "faixa_rendimento_min": str(esp.faixa_rendimento_min),
            "faixa_rendimento_max": str(esp.faixa_rendimento_max),
            "etapas": esp.etapas, "campos": esp.campos,
        })

    if request.method == "PATCH":
        d = _body(request)
        if d.get("inativar"):
            esp.ativo = False
            esp.save(update_fields=["ativo", "atualizado_em"])
            _audit(empresa, "editar", "EspecificacaoProducao", esp.id,
                   f"MBR inativado: {esp.codigo_produto} v{esp.versao}", request)
            return JsonResponse({"ok": True, "ativo": False})

        for campo_attr in ("nome", "concentracao", "forma_farmaceutica", "unidade_rendimento"):
            if campo_attr in d:
                setattr(esp, campo_attr, d[campo_attr])
        for dec_attr in ("tamanho_lote_padrao", "rendimento_teorico",
                         "faixa_rendimento_min", "faixa_rendimento_max"):
            if dec_attr in d:
                setattr(esp, dec_attr, _dec(d[dec_attr], getattr(esp, dec_attr)))
        if isinstance(d.get("etapas"), list):
            esp.etapas = d["etapas"]
        if isinstance(d.get("campos"), list):
            esp.campos = d["campos"]
        esp.save()
        _audit(empresa, "editar", "EspecificacaoProducao", esp.id,
               f"MBR editado: {esp.codigo_produto} v{esp.versao}", request)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── Ordens de produção ────────────────────────────────────────────────────────

@csrf_exempt
def api_producao_ordens(request):
    """GET lista | POST abre nova ordem."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import EspecificacaoProducao, OrdemProducaoIndustrial

    if request.method == "GET":
        qs = OrdemProducaoIndustrial.objects.filter(empresa=empresa).select_related("especificacao")
        status_filtro = request.GET.get("status")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        dados = [{
            "id": o.id, "numero_op": o.numero_op,
            "produto": o.especificacao.nome, "codigo_produto": o.especificacao.codigo_produto,
            "numero_lote_fabricacao": o.numero_lote_fabricacao,
            "status": o.status, "status_label": o.get_status_display(),
            "etapa_atual": o.etapa_atual,
            "rendimento_pct": str(o.rendimento_pct) if o.rendimento_pct is not None else None,
            "bloqueada": o.bloqueada,
            "tem_desvio_aberto": o.tem_desvio_aberto,
            "criado_em": o.criado_em.isoformat(),
        } for o in qs[:300]]
        return JsonResponse({"ordens": dados})

    if request.method == "POST":
        d = _body(request)
        esp = EspecificacaoProducao.objects.filter(
            empresa=empresa, id=d.get("especificacao_id"), ativo=True).first()
        if not esp:
            return JsonResponse({"erro": "Especificação inválida ou inativa."}, status=400)
        numero_op = (d.get("numero_op") or "").strip()
        if not numero_op:
            return JsonResponse({"erro": "Informe o número da ordem de produção."}, status=400)
        if OrdemProducaoIndustrial.objects.filter(empresa=empresa, numero_op=numero_op).exists():
            return JsonResponse({"erro": f"Já existe a OP {numero_op}."}, status=409)

        primeira_etapa = ""
        if esp.lista_etapas():
            primeira_etapa = esp.lista_etapas()[0].get("chave", "")

        ordem = OrdemProducaoIndustrial.objects.create(
            empresa=empresa, especificacao=esp, numero_op=numero_op,
            numero_lote_fabricacao=d.get("numero_lote_fabricacao") or "",
            tamanho_lote=_dec(d.get("tamanho_lote"), Decimal("0")),
            unidade=d.get("unidade") or esp.unidade_rendimento,
            responsavel=d.get("responsavel") or "", criado_por=_usuario(request),
            etapa_atual=primeira_etapa, status="rascunho",
        )
        _audit(empresa, "criar", "OrdemProducaoIndustrial", ordem.id,
               f"OP aberta: {numero_op} — {esp.nome}", request)
        return JsonResponse({"ok": True, "id": ordem.id}, status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


def _serializar_ordem(ordem):
    esp = ordem.especificacao
    registros = {r.chave_campo: r for r in ordem.registros.all()}
    etapas_out = []
    for e in esp.lista_etapas():
        chave = e.get("chave")
        campos_etapa = []
        for c in esp.campos_da_etapa(chave):
            reg = registros.get(c.get("chave"))
            campos_etapa.append({
                "chave": c.get("chave"), "rotulo": c.get("rotulo"),
                "tipo": c.get("tipo", "numero"), "unidade": c.get("unidade", ""),
                "obrigatorio": bool(c.get("obrigatorio")),
                "min": c.get("min"), "max": c.get("max"),
                "opcoes": c.get("opcoes"), "ajuda": c.get("ajuda", ""),
                "valor": reg.valor if reg else "",
                "status_validacao": reg.status_validacao if reg else "pendente",
                "mensagem_validacao": reg.mensagem_validacao if reg else "",
            })
        assinada_por = list(ordem.assinaturas.filter(etapa=chave)
                            .values("papel", "assinante_nome", "metodo", "assinado_em"))
        etapas_out.append({
            "chave": chave, "rotulo": e.get("rotulo") or chave,
            "papel_assina": e.get("papel_assina") or "operador",
            "campos": campos_etapa, "assinaturas": [
                {"papel": a["papel"], "assinante": a["assinante_nome"],
                 "metodo": a["metodo"], "em": a["assinado_em"].isoformat()}
                for a in assinada_por
            ],
            "atual": chave == ordem.etapa_atual,
        })

    desvios = [{
        "id": dv.id, "tipo": dv.tipo, "severidade": dv.severidade, "etapa": dv.etapa,
        "campo": dv.campo, "descricao": dv.descricao, "resolvido": dv.resolvido,
        "detectado_por": dv.detectado_por, "criado_em": dv.criado_em.isoformat(),
    } for dv in ordem.desvios.all()]

    return {
        "id": ordem.id, "numero_op": ordem.numero_op,
        "produto": esp.nome, "codigo_produto": esp.codigo_produto,
        "concentracao": esp.concentracao,
        "numero_lote_fabricacao": ordem.numero_lote_fabricacao,
        "tamanho_lote": str(ordem.tamanho_lote), "unidade": ordem.unidade,
        "status": ordem.status, "status_label": ordem.get_status_display(),
        "etapa_atual": ordem.etapa_atual,
        "rendimento_real": str(ordem.rendimento_real) if ordem.rendimento_real is not None else "",
        "rendimento_pct": str(ordem.rendimento_pct) if ordem.rendimento_pct is not None else None,
        "bloqueada": ordem.bloqueada, "motivo_bloqueio": ordem.motivo_bloqueio,
        "responsavel": ordem.responsavel,
        "faixa_rendimento": [str(esp.faixa_rendimento_min), str(esp.faixa_rendimento_max)],
        "transicoes_permitidas": fsm.transicoes_permitidas(ordem.status),
        "etapas": etapas_out, "desvios": desvios,
    }


@csrf_exempt
def api_producao_ordem_detail(request, op_id):
    """GET detalhe completo da ordem (etapas, campos com status, desvios)."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import OrdemProducaoIndustrial

    ordem = (OrdemProducaoIndustrial.objects
             .filter(empresa=empresa, id=op_id)
             .select_related("especificacao").first())
    if not ordem:
        return JsonResponse({"erro": "Ordem não encontrada"}, status=404)
    return JsonResponse(_serializar_ordem(ordem))


# ── Preenchimento de campo com validação em tempo real ────────────────────────

@csrf_exempt
def api_producao_preencher_campo(request, op_id):
    """
    POST {chave_campo, valor}. Valida contra a faixa da especificação NA HORA,
    salva o registro, roda a IA de anomalia e — se fora da faixa — abre desvio.
    É este endpoint que o tablet chama a cada campo preenchido.
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import OrdemProducaoIndustrial, RegistroCampoProducao, DesvioProducao

    ordem = (OrdemProducaoIndustrial.objects
             .filter(empresa=empresa, id=op_id).select_related("especificacao").first())
    if not ordem:
        return JsonResponse({"erro": "Ordem não encontrada"}, status=404)
    if ordem.status in ("liberado", "rejeitado", "cancelado"):
        return JsonResponse({"erro": "Ordem finalizada — não aceita edição."}, status=409)

    d = _body(request)
    chave = (d.get("chave_campo") or "").strip()
    valor = d.get("valor")
    if not chave:
        return JsonResponse({"erro": "Informe a chave do campo."}, status=400)

    esp = ordem.especificacao
    campo_spec = next((c for c in (esp.campos if isinstance(esp.campos, list) else [])
                       if c.get("chave") == chave), None)
    if not campo_spec:
        return JsonResponse({"erro": "Campo não pertence à especificação."}, status=400)

    # 1) Validação de faixa/tipo.
    resultado = val.validar_valor_campo(campo_spec, valor)

    # 2) IA de anomalia (só quando a faixa passou — pega o "plausível mas errado").
    anomalia = {"anomalia": False, "mensagem": ""}
    if resultado["status"] in (val.OK, val.ALERTA):
        anomalia = pia.detectar_anomalia(empresa, esp, chave, valor)
        if anomalia.get("anomalia"):
            if resultado["status"] == val.OK:
                resultado["status"] = val.ALERTA
            resultado["mensagem"] = (resultado["mensagem"] + " " + anomalia["mensagem"]).strip()

    with transaction.atomic():
        reg, _criado = RegistroCampoProducao.objects.update_or_create(
            ordem=ordem, chave_campo=chave,
            defaults={
                "empresa": empresa,
                "rotulo": campo_spec.get("rotulo") or chave,
                "etapa": campo_spec.get("etapa") or "",
                "tipo": campo_spec.get("tipo") or "numero",
                "valor": "" if valor is None else str(valor),
                "unidade": campo_spec.get("unidade") or "",
                "status_validacao": resultado["status"],
                "fora_faixa": resultado["fora_faixa"],
                "mensagem_validacao": resultado["mensagem"][:300],
                "valor_min_esperado": resultado["min"][:40],
                "valor_max_esperado": resultado["max"][:40],
                "preenchido_por": _usuario(request),
            },
        )

        # 3) Abre/limpa desvio conforme o resultado.
        desvio_existente = DesvioProducao.objects.filter(
            ordem=ordem, campo=chave, resolvido=False,
            tipo__in=["faixa", "anomalia_ia"]).first()

        if resultado["status"] == val.ERRO:
            if not desvio_existente:
                DesvioProducao.objects.create(
                    ordem=ordem, empresa=empresa, tipo="faixa",
                    severidade="alta", etapa=campo_spec.get("etapa") or "",
                    campo=chave, valor_encontrado=str(valor)[:120],
                    valor_esperado=f"{resultado['min']}–{resultado['max']}",
                    descricao=resultado["mensagem"], detectado_por="sistema",
                )
        elif anomalia.get("anomalia"):
            if not desvio_existente:
                DesvioProducao.objects.create(
                    ordem=ordem, empresa=empresa, tipo="anomalia_ia",
                    severidade="media", etapa=campo_spec.get("etapa") or "",
                    campo=chave, valor_encontrado=str(valor)[:120],
                    valor_esperado=(str(anomalia.get("sugestao")) if anomalia.get("sugestao") else ""),
                    descricao=anomalia["mensagem"], detectado_por="ia",
                )
        else:
            # Valor corrigido para dentro da faixa/padrão → resolve o desvio automático.
            if desvio_existente:
                desvio_existente.resolvido = True
                desvio_existente.resolucao = "Valor corrigido para dentro do padrão."
                desvio_existente.resolvido_por = _usuario(request)
                desvio_existente.resolvido_em = timezone.now()
                desvio_existente.save(update_fields=["resolvido", "resolucao",
                                                     "resolvido_por", "resolvido_em"])

        if resultado["status"] == val.OK:
            pia.registrar_aprendizado(empresa, 1)

    return JsonResponse({
        "ok": True,
        "status": resultado["status"],
        "fora_faixa": resultado["fora_faixa"],
        "mensagem": resultado["mensagem"],
        "faixa": {"min": resultado["min"], "max": resultado["max"]},
        "ia": {"anomalia": anomalia.get("anomalia", False),
               "sugestao": anomalia.get("sugestao"),
               "n": anomalia.get("n", 0)},
    })


# ── Validação da ordem inteira ────────────────────────────────────────────────

@csrf_exempt
def api_producao_validar(request, op_id):
    """GET valida a ordem inteira e devolve o que impede o avanço."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import OrdemProducaoIndustrial

    ordem = (OrdemProducaoIndustrial.objects
             .filter(empresa=empresa, id=op_id).select_related("especificacao").first())
    if not ordem:
        return JsonResponse({"erro": "Ordem não encontrada"}, status=404)

    esp = ordem.especificacao
    registros = {r.chave_campo: r.valor for r in ordem.registros.all()}
    etapas_status = []
    tudo_ok = True
    for e in esp.lista_etapas():
        chave = e.get("chave")
        check = val.validar_etapa(esp, registros, chave)
        if not check["completa"]:
            tudo_ok = False
        etapas_status.append({
            "etapa": chave, "rotulo": e.get("rotulo") or chave,
            "completa": check["completa"], "faltando": check["faltando"],
            "com_erro": check["com_erro"], "ok": check["ok"],
            "total": check["total_campos"],
        })

    rendimento = val.validar_rendimento(esp, ordem.tamanho_lote, ordem.rendimento_real)
    return JsonResponse({
        "ordem": ordem.numero_op, "status": ordem.status,
        "tudo_ok": tudo_ok, "etapas": etapas_status,
        "rendimento": {
            "aplicavel": rendimento["aplicavel"],
            "pct": str(rendimento["pct"]) if rendimento["pct"] is not None else None,
            "dentro_faixa": rendimento["dentro_faixa"],
            "mensagem": rendimento["mensagem"],
        },
        "desvios_abertos": ordem.desvios.filter(resolvido=False).count(),
    })


# ── Avanço de etapa / status (guarda FSM) ─────────────────────────────────────

@csrf_exempt
def api_producao_avancar(request, op_id):
    """
    PATCH. Dois modos:
      {"acao":"proxima_etapa"}          avança para a próxima etapa da linha
      {"acao":"status","novo":"..."}    transição de status macro (CQ, liberar, rejeitar)
    Sempre passa pela guarda: nada avança incompleto/inválido/sem assinatura.
    """
    if request.method != "PATCH":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import OrdemProducaoIndustrial

    ordem = (OrdemProducaoIndustrial.objects
             .filter(empresa=empresa, id=op_id).select_related("especificacao").first())
    if not ordem:
        return JsonResponse({"erro": "Ordem não encontrada"}, status=404)

    esp = ordem.especificacao
    d = _body(request)
    acao = d.get("acao")

    registros = {r.chave_campo: r.valor for r in ordem.registros.all()}
    assinaturas_set = set((a.etapa, a.papel) for a in ordem.assinaturas.all())

    if acao == "proxima_etapa":
        aval = fsm.pode_avancar_etapa(ordem, esp, registros, assinaturas_set)
        if not aval["permitido"]:
            _registrar_desvio_sequencia(empresa, ordem, aval["motivos"])
            return JsonResponse({"ok": False, "motivos": aval["motivos"]}, status=422)

        with transaction.atomic():
            if aval["ultima"]:
                # Última etapa concluída → move o status macro para CQ.
                guarda = fsm.pode_transicionar_status(
                    ordem, esp, "controle_qualidade",
                    {"registros_por_chave": registros, "assinaturas_set": assinaturas_set,
                     "tem_desvio_critico_aberto": ordem.tem_desvio_critico_aberto})
                if not guarda["permitido"]:
                    return JsonResponse({"ok": False, "motivos": guarda["motivos"]}, status=422)
                ordem.status = "controle_qualidade"
                ordem.save(update_fields=["status", "atualizado_em"])
                _audit(empresa, "editar", "OrdemProducaoIndustrial", ordem.id,
                       f"OP {ordem.numero_op}: produção concluída → controle de qualidade", request)
                return JsonResponse({"ok": True, "status": ordem.status,
                                     "mensagem": "Produção concluída. Ordem enviada ao CQ."})
            ordem.etapa_atual = aval["proxima_etapa"]
            ordem.save(update_fields=["etapa_atual", "atualizado_em"])
            _audit(empresa, "editar", "OrdemProducaoIndustrial", ordem.id,
                   f"OP {ordem.numero_op}: avançou para etapa {aval['proxima_etapa']}", request)
        return JsonResponse({"ok": True, "etapa_atual": ordem.etapa_atual})

    if acao == "status":
        novo = d.get("novo")
        contexto = {
            "registros_por_chave": registros, "assinaturas_set": assinaturas_set,
            "tem_desvio_critico_aberto": ordem.tem_desvio_critico_aberto,
            "motivo": d.get("motivo"),
            "assinou_qa": ordem.assinaturas.filter(papel="farmaceutico_qa").exists(),
        }
        # Contexto extra por transição.
        if ordem.status == "rascunho" and novo == "em_producao":
            if not ordem.etapa_atual and esp.lista_etapas():
                ordem.etapa_atual = esp.lista_etapas()[0].get("chave", "")
        if ordem.status == "controle_qualidade" and novo == "revisao_qualidade":
            # rendimento real pode vir no corpo
            if d.get("rendimento_real") is not None:
                ordem.rendimento_real = _dec(d.get("rendimento_real"), ordem.rendimento_real)
            contexto["rendimento"] = val.validar_rendimento(
                esp, ordem.tamanho_lote, ordem.rendimento_real)

        guarda = fsm.pode_transicionar_status(ordem, esp, novo, contexto)
        if not guarda["permitido"]:
            return JsonResponse({"ok": False, "motivos": guarda["motivos"]}, status=422)

        with transaction.atomic():
            anterior = ordem.status
            ordem.status = novo
            campos_update = ["status", "atualizado_em"]
            if novo == "em_producao" and not ordem.data_inicio:
                ordem.data_inicio = timezone.now()
                campos_update.append("data_inicio")
            if novo == "em_producao":
                campos_update.append("etapa_atual")
            if novo == "revisao_qualidade" and ordem.rendimento_real is not None:
                rend = contexto.get("rendimento") or val.validar_rendimento(
                    esp, ordem.tamanho_lote, ordem.rendimento_real)
                if rend.get("pct") is not None:
                    ordem.rendimento_pct = rend["pct"]
                    campos_update += ["rendimento_real", "rendimento_pct"]
            if novo in ("liberado", "rejeitado", "cancelado"):
                ordem.data_conclusao = timezone.now()
                campos_update.append("data_conclusao")
            if novo in ("rejeitado", "cancelado") and d.get("motivo"):
                ordem.motivo_bloqueio = str(d.get("motivo"))[:300]
                campos_update.append("motivo_bloqueio")
            ordem.save(update_fields=list(set(campos_update)))
            _audit(empresa, "editar", "OrdemProducaoIndustrial", ordem.id,
                   f"OP {ordem.numero_op}: {anterior} → {novo}. {d.get('motivo','')}".strip(),
                   request, dados_antes={"status": anterior}, dados_depois={"status": novo})
        return JsonResponse({"ok": True, "status": ordem.status})

    return JsonResponse({"erro": "Ação inválida."}, status=400)


def _registrar_desvio_sequencia(empresa, ordem, motivos):
    from .models import DesvioProducao
    if DesvioProducao.objects.filter(ordem=ordem, tipo="sequencia", resolvido=False).exists():
        return
    DesvioProducao.objects.create(
        ordem=ordem, empresa=empresa, tipo="sequencia", severidade="media",
        etapa=ordem.etapa_atual, descricao="Avanço bloqueado: " + " | ".join(motivos)[:400],
        detectado_por="sistema",
    )


# ── Assinatura de etapa (ICP-Brasil) ──────────────────────────────────────────

@csrf_exempt
def api_producao_assinar(request, op_id):
    """
    POST {etapa, papel, assinante_nome, assinante_registro, senha?}.
    Assina o snapshot da etapa com o motor ICP-Brasil (fallback SHA-256).
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import (OrdemProducaoIndustrial, AssinaturaEtapaProducao,
                         CredenciaisIntegracoes)
    from .assinatura_digital import assinar_conteudo

    ordem = (OrdemProducaoIndustrial.objects
             .filter(empresa=empresa, id=op_id).select_related("especificacao").first())
    if not ordem:
        return JsonResponse({"erro": "Ordem não encontrada"}, status=404)

    d = _body(request)
    etapa = (d.get("etapa") or "").strip()
    papel = (d.get("papel") or "operador").strip()
    nome = (d.get("assinante_nome") or "").strip()
    if not etapa or not nome:
        return JsonResponse({"erro": "Informe etapa e nome do assinante."}, status=400)

    esp = ordem.especificacao
    if etapa not in [e.get("chave") for e in esp.lista_etapas()]:
        return JsonResponse({"erro": "Etapa não pertence à especificação."}, status=400)

    # Só assina o que está completo e válido — assinatura não legitima erro.
    registros = {r.chave_campo: r.valor for r in ordem.registros.all()}
    check = val.validar_etapa(esp, registros, etapa)
    if not check["completa"]:
        return JsonResponse({
            "ok": False,
            "erro": "Etapa incompleta ou com erro — corrija antes de assinar.",
            "faltando": check["faltando"], "com_erro": check["com_erro"],
        }, status=422)

    # Snapshot canônico do que está sendo assinado.
    campos_snapshot = {c.get("chave"): registros.get(c.get("chave"), "")
                       for c in esp.campos_da_etapa(etapa)}
    conteudo = json.dumps({
        "op": ordem.numero_op, "lote": ordem.numero_lote_fabricacao,
        "etapa": etapa, "papel": papel, "assinante": nome,
        "campos": campos_snapshot,
    }, sort_keys=True, ensure_ascii=False)

    cred, _ = CredenciaisIntegracoes.objects.get_or_create(empresa=empresa)
    ok, assinatura_b64, hash_hex, metodo, erro = assinar_conteudo(
        conteudo, cred, identificador=f"{nome} {d.get('assinante_registro','')}".strip(),
        senha_override=d.get("senha", ""))
    if not ok:
        return JsonResponse({"ok": False, "erro": f"Falha ao assinar: {erro}"}, status=500)

    with transaction.atomic():
        AssinaturaEtapaProducao.objects.update_or_create(
            ordem=ordem, etapa=etapa, papel=papel,
            defaults={
                "empresa": empresa, "assinante_nome": nome,
                "assinante_registro": d.get("assinante_registro") or "",
                "conteudo_assinado": conteudo, "assinatura_b64": assinatura_b64,
                "hash_documento": hash_hex, "metodo": metodo,
            },
        )
        _audit(empresa, "editar", "OrdemProducaoIndustrial", ordem.id,
               f"OP {ordem.numero_op}: etapa {etapa} assinada por {nome} ({papel}) [{metodo}]",
               request)
    return JsonResponse({"ok": True, "metodo": metodo, "hash": hash_hex})


# ── Desvios ───────────────────────────────────────────────────────────────────

@csrf_exempt
def api_producao_desvios(request, op_id):
    """GET lista desvios | PATCH resolve um desvio {desvio_id, resolucao}."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import OrdemProducaoIndustrial, DesvioProducao

    ordem = OrdemProducaoIndustrial.objects.filter(empresa=empresa, id=op_id).first()
    if not ordem:
        return JsonResponse({"erro": "Ordem não encontrada"}, status=404)

    if request.method == "GET":
        dados = [{
            "id": dv.id, "tipo": dv.tipo, "tipo_label": dv.get_tipo_display(),
            "severidade": dv.severidade, "etapa": dv.etapa, "campo": dv.campo,
            "valor_encontrado": dv.valor_encontrado, "valor_esperado": dv.valor_esperado,
            "descricao": dv.descricao, "detectado_por": dv.detectado_por,
            "resolvido": dv.resolvido, "resolucao": dv.resolucao,
            "criado_em": dv.criado_em.isoformat(),
        } for dv in ordem.desvios.all()]
        return JsonResponse({"desvios": dados})

    if request.method == "PATCH":
        d = _body(request)
        dv = DesvioProducao.objects.filter(ordem=ordem, id=d.get("desvio_id")).first()
        if not dv:
            return JsonResponse({"erro": "Desvio não encontrado"}, status=404)
        resolucao = (d.get("resolucao") or "").strip()
        if not resolucao:
            return JsonResponse({"erro": "Descreva a resolução/justificativa (BPF)."}, status=400)
        dv.resolvido = True
        dv.resolucao = resolucao
        dv.resolvido_por = _usuario(request)
        dv.resolvido_em = timezone.now()
        dv.save(update_fields=["resolvido", "resolucao", "resolvido_por", "resolvido_em"])
        _audit(empresa, "editar", "DesvioProducao", dv.id,
               f"OP {ordem.numero_op}: desvio {dv.tipo} resolvido — {resolucao}", request)
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ── KPIs / RFT ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_producao_kpis(request):
    """GET painel: RFT (Right First Time), desvios por tipo, ordens por status."""
    empresa = _farm(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Farmácia"}, status=403)
    from .models import OrdemProducaoIndustrial, DesvioProducao, ModeloIAArea
    from django.db.models import Count

    ordens = OrdemProducaoIndustrial.objects.filter(empresa=empresa)
    total = ordens.count()
    finalizadas = ordens.filter(status__in=["liberado", "rejeitado"])
    n_final = finalizadas.count()

    # RFT: ordens liberadas SEM nenhum desvio registrado / total finalizadas.
    ids_com_desvio = set(DesvioProducao.objects.filter(empresa=empresa)
                         .values_list("ordem_id", flat=True))
    liberadas = finalizadas.filter(status="liberado")
    rft_ok = sum(1 for o in liberadas if o.id not in ids_com_desvio)
    rft_pct = round((rft_ok / n_final) * 100, 1) if n_final else None

    por_status = dict(ordens.values_list("status").annotate(n=Count("id")))
    desvios_qs = DesvioProducao.objects.filter(empresa=empresa)
    por_tipo = dict(desvios_qs.values_list("tipo").annotate(n=Count("id")))

    modelo_ia = ModeloIAArea.objects.filter(empresa=empresa, area="producao_industrial").first()

    return JsonResponse({
        "total_ordens": total,
        "finalizadas": n_final,
        "rft_pct": rft_pct,
        "rft_descricao": "Ordens liberadas sem nenhum desvio / ordens finalizadas",
        "desvios_abertos": desvios_qs.filter(resolvido=False).count(),
        "desvios_por_tipo": por_tipo,
        "ordens_por_status": por_status,
        "ia": {
            "amostras": modelo_ia.n_amostras if modelo_ia else 0,
            "em_bootstrap": modelo_ia.dataset_sintetico if modelo_ia else True,
        },
    })
