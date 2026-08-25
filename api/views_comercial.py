"""
views_comercial.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agente Comercial Automatizado — SoloCRT Saúde

Auth: só o dono da plataforma (owner_token), igual ao GTM/Governança.
Exceção: os webhooks são públicos (validam secret próprio).

Endpoints:
  GET  /comercial/                     → dashboard (owner only)
  GET  /api/comercial/stats/           → estatísticas do pipeline
  GET  /api/comercial/leads/           → lista de leads (filtros)
  POST /api/comercial/leads/           → criar lead manual
  POST /api/comercial/leads/importar/  → importar CSV
  POST /api/comercial/leads/buscar-google/ → busca automática Google Places
  GET  /api/comercial/leads/<id>/      → detalhe do lead
  PUT  /api/comercial/leads/<id>/      → atualizar lead
  DELETE /api/comercial/leads/<id>/    → excluir lead
  POST /api/comercial/leads/<id>/gerar-email/ → gera email com IA
  POST /api/comercial/leads/<id>/enviar/      → envia email via Brevo
  PATCH /api/comercial/leads/<id>/status/     → muda status
  POST /api/comercial/webhook/eventos/        → webhook eventos Brevo (público)
  POST /api/comercial/webhook/inbound/        → respostas de leads (público)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import EmailProspeccao, LeadProspeccao, LicitacaoOportunidade
from .services.auth_session import dono_autenticado_from_request

logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _owner_required(view_fn):
    """Decorador: só o dono da plataforma (owner_token) acessa o agente comercial.

    Mesmo padrão do GTM/Governança — é uma ferramenta do operador do SaaS,
    não de um tenant. APIs devolvem 403 JSON; páginas HTML redirecionam.
    """
    from functools import wraps
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        dono = dono_autenticado_from_request(request)
        if not dono:
            if request.path.startswith("/api/"):
                return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
            return redirect("/operacao-central/")
        request.dono_saas = dono
        return view_fn(request, *args, **kwargs)
    return wrapper


def _json_body(request) -> dict:
    try:
        return json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return {}


def _lead_to_dict(lead: LeadProspeccao) -> dict:
    emails = list(lead.emails.values(
        "id", "numero_sequencia", "assunto", "status",
        "enviado_em", "aberto_em", "clicou_em", "respondeu_em", "criado_em"
    ))
    return {
        "id":                  lead.id,
        "segmento":            lead.segmento,
        "segmento_display":    lead.get_segmento_display(),
        "tipo":                lead.tipo,
        "tipo_display":        lead.get_tipo_display(),
        "nome":                lead.nome,
        "empresa":             lead.empresa,
        "cargo":               lead.cargo,
        "email":               lead.email,
        "telefone":            lead.telefone,
        "cidade":              lead.cidade,
        "estado":              lead.estado,
        "website":             lead.website,
        "linkedin_url":        lead.linkedin_url,
        "funcionarios_estimados": lead.funcionarios_estimados,
        "unidades_estimadas":     lead.unidades_estimadas,
        "pacote_sugerido":        lead.pacote_sugerido(),
        "status":              lead.status,
        "status_display":      lead.get_status_display(),
        "score":               lead.score,
        "notas":               lead.notas,
        "origem":              lead.origem,
        "ultimo_contato_em":   lead.ultimo_contato_em.isoformat() if lead.ultimo_contato_em else None,
        "proximo_followup_em": lead.proximo_followup_em.isoformat() if lead.proximo_followup_em else None,
        "criado_em":           lead.criado_em.isoformat(),
        "atualizado_em":       lead.atualizado_em.isoformat(),
        "emails":              emails,
        "num_emails":          len(emails),
    }


# ─── Dashboard HTML ───────────────────────────────────────────────────────────

@_owner_required
def comercial_dashboard(request):
    return render(request, "comercial_dashboard.html")


# ─── API: Estatísticas ────────────────────────────────────────────────────────

@_owner_required
def api_comercial_stats(request):
    qs = LeadProspeccao.objects.all()

    por_status = dict(qs.values_list("status").annotate(n=Count("id")))
    por_segmento = dict(qs.values_list("segmento").annotate(n=Count("id")))

    emails_qs = EmailProspeccao.objects.all()
    enviados   = emails_qs.filter(enviado_em__isnull=False).count()
    abertos    = emails_qs.filter(aberto_em__isnull=False).count()
    clicados   = emails_qs.filter(clicou_em__isnull=False).count()

    taxa_abertura = round(abertos / enviados * 100, 1) if enviados else 0
    taxa_clique   = round(clicados / enviados * 100, 1) if enviados else 0

    pendentes_followup = qs.filter(
        proximo_followup_em__isnull=False,
        proximo_followup_em__lte=timezone.now(),
        status__in=["email_enviado", "followup_1", "followup_2"],
    ).count()

    return JsonResponse({
        "totais": {
            "leads":        qs.count(),
            "novos":        por_status.get("novo", 0),
            "contatados":   por_status.get("email_enviado", 0) + por_status.get("followup_1", 0) + por_status.get("followup_2", 0) + por_status.get("followup_final", 0),
            "responderam":  por_status.get("respondeu", 0),
            "demo":         por_status.get("demo_agendada", 0),
            "trial":        por_status.get("trial", 0),
            "clientes":     por_status.get("cliente", 0),
        },
        "por_status":   por_status,
        "por_segmento": por_segmento,
        "emails": {
            "enviados":       enviados,
            "abertos":        abertos,
            "clicados":       clicados,
            "taxa_abertura":  taxa_abertura,
            "taxa_clique":    taxa_clique,
        },
        "pendentes_followup": pendentes_followup,
    })


# ─── API: Lista / Criar leads ─────────────────────────────────────────────────

@csrf_exempt
@_owner_required
def api_leads_lista(request):
    if request.method == "GET":
        qs = LeadProspeccao.objects.all()

        # Filtros
        status = request.GET.get("status")
        segmento = request.GET.get("segmento")
        q = request.GET.get("q", "").strip()

        if status:
            qs = qs.filter(status=status)
        if segmento:
            qs = qs.filter(segmento=segmento)
        if q:
            qs = qs.filter(
                Q(nome__icontains=q) | Q(empresa__icontains=q) |
                Q(email__icontains=q) | Q(cidade__icontains=q)
            )

        page = int(request.GET.get("pagina", 1))
        per_page = int(request.GET.get("por_pagina", 50))
        offset = (page - 1) * per_page

        total = qs.count()
        leads = [_lead_to_dict(l) for l in qs.prefetch_related("emails")[offset:offset + per_page]]

        return JsonResponse({
            "leads": leads,
            "total": total,
            "pagina": page,
            "por_pagina": per_page,
            "paginas": (total + per_page - 1) // per_page,
        })

    if request.method == "POST":
        data = _json_body(request)
        obrigatorios = ["nome", "empresa", "email", "cidade", "estado", "segmento", "tipo"]
        for campo in obrigatorios:
            if not data.get(campo):
                return JsonResponse({"erro": f"Campo obrigatório: {campo}"}, status=400)

        if LeadProspeccao.objects.filter(email=data["email"].lower()).exists():
            return JsonResponse({"erro": "Email já cadastrado."}, status=400)

        lead = LeadProspeccao.objects.create(
            nome=data["nome"],
            empresa=data["empresa"],
            cargo=data.get("cargo", ""),
            email=data["email"].lower().strip(),
            telefone=data.get("telefone", ""),
            cidade=data["cidade"],
            estado=data["estado"][:2].upper(),
            segmento=data["segmento"],
            tipo=data.get("tipo", "farmacia_dispensacao"),
            website=data.get("website", ""),
            linkedin_url=data.get("linkedin_url", ""),
            funcionarios_estimados=data.get("funcionarios_estimados") or None,
            unidades_estimadas=data.get("unidades_estimadas") or None,
            notas=data.get("notas", ""),
            score=data.get("score", 50),
            origem="manual",
        )
        return JsonResponse(_lead_to_dict(lead), status=201)

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── API: Detalhe / Atualizar / Excluir ──────────────────────────────────────

@csrf_exempt
@_owner_required
def api_lead_detalhe(request, lead_id: int):
    try:
        lead = LeadProspeccao.objects.prefetch_related("emails").get(pk=lead_id)
    except LeadProspeccao.DoesNotExist:
        return JsonResponse({"erro": "Lead não encontrado."}, status=404)

    if request.method == "GET":
        return JsonResponse(_lead_to_dict(lead))

    if request.method == "PUT":
        data = _json_body(request)
        campos_permitidos = [
            "nome", "empresa", "cargo", "email", "telefone", "cidade", "estado",
            "website", "linkedin_url", "notas", "score", "tipo", "segmento",
            "funcionarios_estimados", "unidades_estimadas",
        ]
        for campo in campos_permitidos:
            if campo in data:
                setattr(lead, campo, data[campo])
        lead.save()
        return JsonResponse(_lead_to_dict(lead))

    if request.method == "DELETE":
        lead.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Método não permitido"}, status=405)


# ─── API: Gerar email com IA ─────────────────────────────────────────────────

@csrf_exempt
@_owner_required
def api_lead_gerar_email(request, lead_id: int):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        lead = LeadProspeccao.objects.get(pk=lead_id)
    except LeadProspeccao.DoesNotExist:
        return JsonResponse({"erro": "Lead não encontrado."}, status=404)

    data = _json_body(request)
    numero_sequencia = int(data.get("numero_sequencia", 1))

    try:
        from .email_ai import gerar_email
        resultado = gerar_email(lead, numero_sequencia)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=503)
    except Exception as exc:
        logger.exception("gerar_email lead=%s", lead_id)
        return JsonResponse({"erro": f"Erro ao gerar email: {exc}"}, status=500)

    # Salvar como rascunho
    email_obj = EmailProspeccao.objects.create(
        lead=lead,
        numero_sequencia=numero_sequencia,
        assunto=resultado["assunto"],
        corpo_html=resultado["corpo_html"],
        corpo_texto=resultado["corpo_texto"],
        status="rascunho",
    )

    return JsonResponse({
        "email_id":      email_obj.id,
        "assunto":       email_obj.assunto,
        "corpo_html":    email_obj.corpo_html,
        "corpo_texto":   email_obj.corpo_texto,
        "numero_sequencia": email_obj.numero_sequencia,
    })


# ─── API: Enviar email ────────────────────────────────────────────────────────

@csrf_exempt
@_owner_required
def api_lead_enviar_email(request, lead_id: int):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        lead = LeadProspeccao.objects.get(pk=lead_id)
    except LeadProspeccao.DoesNotExist:
        return JsonResponse({"erro": "Lead não encontrado."}, status=404)

    data = _json_body(request)
    email_id = data.get("email_id")

    if email_id:
        try:
            email_obj = EmailProspeccao.objects.get(pk=email_id, lead=lead)
        except EmailProspeccao.DoesNotExist:
            return JsonResponse({"erro": "Email não encontrado."}, status=404)
    else:
        # Gera e envia na hora
        numero_sequencia = int(data.get("numero_sequencia", 1))
        try:
            from .email_ai import gerar_email
            resultado = gerar_email(lead, numero_sequencia)
        except ValueError as exc:
            return JsonResponse({"erro": str(exc)}, status=503)
        except Exception as exc:
            return JsonResponse({"erro": f"Erro ao gerar email: {exc}"}, status=500)

        email_obj = EmailProspeccao.objects.create(
            lead=lead,
            numero_sequencia=numero_sequencia,
            assunto=resultado["assunto"],
            corpo_html=resultado["corpo_html"],
            corpo_texto=resultado["corpo_texto"],
            status="rascunho",
        )

    # Enviar
    from .brevo_service import enviar_email
    sucesso = enviar_email(email_obj)

    if sucesso:
        # Atualizar status do lead
        _avancar_status_lead(lead, email_obj.numero_sequencia)
        return JsonResponse({
            "ok":        True,
            "email_id":  email_obj.id,
            "status":    email_obj.status,
            "enviado_em": email_obj.enviado_em.isoformat() if email_obj.enviado_em else None,
        })
    else:
        return JsonResponse({
            "ok":    False,
            "erro":  email_obj.erro,
        }, status=500)


def _avancar_status_lead(lead: LeadProspeccao, numero_sequencia: int):
    """Atualiza status e proximo_followup_em do lead após envio."""
    agora = timezone.now()

    mapa_status = {
        1: ("email_enviado", 3),   # seq 1 → followup em 3 dias
        2: ("followup_1",   7),    # seq 2 → followup em 7 dias
        3: ("followup_2",   14),   # seq 3 → followup em 14 dias
        4: ("followup_final", None),
    }
    novo_status, dias_proximo = mapa_status.get(numero_sequencia, ("email_enviado", 3))

    lead.status = novo_status
    lead.ultimo_contato_em = agora
    lead.proximo_followup_em = agora + timedelta(days=dias_proximo) if dias_proximo else None
    lead.save(update_fields=["status", "ultimo_contato_em", "proximo_followup_em"])


# ─── API: Atualizar status ────────────────────────────────────────────────────

@csrf_exempt
@_owner_required
def api_lead_status(request, lead_id: int):
    if request.method != "PATCH":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        lead = LeadProspeccao.objects.get(pk=lead_id)
    except LeadProspeccao.DoesNotExist:
        return JsonResponse({"erro": "Lead não encontrado."}, status=404)

    data = _json_body(request)
    novo_status = data.get("status")

    status_validos = [s[0] for s in LeadProspeccao.STATUS]
    if novo_status not in status_validos:
        return JsonResponse({"erro": f"Status inválido. Opções: {status_validos}"}, status=400)

    status_anterior = lead.status
    lead.status = novo_status
    if data.get("notas"):
        lead.notas = (lead.notas + "\n\n" + data["notas"]).strip()
    lead.save(update_fields=["status", "notas", "atualizado_em"])

    # Notifica no WhatsApp quando o lead esquenta (só na transição, não repete).
    if novo_status in ("respondeu", "demo_agendada") and status_anterior != novo_status:
        try:
            from .notificacao_comercial import notificar_resposta
            ctx = "pediu demo" if novo_status == "demo_agendada" else "respondeu"
            notificar_resposta(lead, ctx)
        except Exception:
            logger.exception("notificar_resposta falhou lead=%s", lead.id)

    return JsonResponse({"ok": True, "status": lead.status, "status_display": lead.get_status_display()})


# ─── API: Importar CSV ────────────────────────────────────────────────────────

@csrf_exempt
@_owner_required
def api_leads_importar_csv(request):
    if request.method == "GET":
        # Retorna template CSV para download
        from .lead_hunter import template_csv_exemplo
        csv_content = template_csv_exemplo()
        from django.http import HttpResponse
        resp = HttpResponse(csv_content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="template_leads.csv"'
        return resp

    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    # Aceita arquivo CSV ou corpo JSON com campo "csv_content"
    csv_content = ""
    if request.FILES.get("arquivo"):
        try:
            csv_content = request.FILES["arquivo"].read().decode("utf-8-sig")
        except UnicodeDecodeError:
            csv_content = request.FILES["arquivo"].read().decode("latin-1")
    else:
        data = _json_body(request)
        csv_content = data.get("csv_content", "")

    if not csv_content.strip():
        return JsonResponse({"erro": "Arquivo CSV vazio ou não enviado."}, status=400)

    from .lead_hunter import importar_csv
    resultado = importar_csv(csv_content)

    criados = 0
    duplicados = 0
    erros_db = []

    with transaction.atomic():
        for lead_dict in resultado["leads"]:
            try:
                LeadProspeccao.objects.create(**lead_dict)
                criados += 1
            except Exception as exc:
                if "unique" in str(exc).lower() or "UNIQUE" in str(exc):
                    duplicados += 1
                else:
                    erros_db.append(f"{lead_dict.get('email', '?')}: {exc}")

    return JsonResponse({
        "ok":        True,
        "criados":   criados,
        "duplicados": duplicados,
        "erros_parse": resultado["erros"],
        "erros_db":  erros_db,
        "total_csv": resultado["total"],
    })


# ─── API: Busca Google Places ─────────────────────────────────────────────────

@csrf_exempt
@_owner_required
def api_leads_buscar_google(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    data = _json_body(request)
    tipo    = data.get("tipo", "farmacia_dispensacao")
    cidade  = data.get("cidade", "")
    estado  = data.get("estado", "SP")
    max_r   = int(data.get("max_resultados", 20))

    if not cidade:
        return JsonResponse({"erro": "Campo 'cidade' obrigatório."}, status=400)

    try:
        from .lead_hunter import buscar_google_places
        resultados = buscar_google_places(tipo, cidade, estado, max_r)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=503)
    except Exception as exc:
        logger.exception("buscar_google_places cidade=%s tipo=%s", cidade, tipo)
        return JsonResponse({"erro": f"Erro na busca: {exc}"}, status=500)

    # Retorna candidatos para o usuário revisar antes de salvar
    return JsonResponse({
        "candidatos": resultados,
        "total":      len(resultados),
        "instrucao":  "Revise os candidatos e clique em 'Salvar selecionados' para importar.",
    })


# ─── Webhook Brevo ────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_brevo_webhook(request):
    """
    Recebe eventos do Brevo: opened, click, hard_bounce, spam, unsubscribed.
    Não exige autenticação (endpoint público, mas valida secret no header).
    """
    # Verificação simples de secret (configure EMAIL_WEBHOOK_SECRET no .env)
    from django.conf import settings
    webhook_secret = getattr(settings, "EMAIL_WEBHOOK_SECRET", "")
    if webhook_secret:
        token = request.headers.get("X-SoloCRT-Token", "")
        if token != webhook_secret:
            return JsonResponse({"erro": "Token inválido."}, status=401)

    try:
        payload = json.loads(request.body or "[]")
        if not isinstance(payload, list):
            payload = [payload]
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    from .brevo_service import processar_evento_webhook
    processados = processar_evento_webhook(payload)

    return JsonResponse({"ok": True, "processados": processados})


# ─── Webhook Brevo Inbound Parse (respostas de leads) ─────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_brevo_inbound(request):
    """
    Recebe respostas de leads via Brevo Inbound Parse.

    Quando um lead responde o email de prospecção, o Brevo faz POST em
    JSON com {"items": [{"From": "...", "Subject": "...",
    "ExtractedMarkdownMessage": "..."}]}. Identificamos o lead pelo
    remetente, marcamos status='respondeu' e disparamos WhatsApp.

    Configurar: domínio dedicado (ex. reply.solocrt.com) com MX apontando
    pra inbound1.sendinblue.com / inbound2.sendinblue.com, depois cadastrar
    esse domínio no painel Brevo → Inbound Parsing → esta URL.
    """
    import re

    try:
        payload = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"ok": False, "erro": "JSON inválido"}, status=200)

    itens = payload.get("items", [])
    if not itens:
        return JsonResponse({"ok": True, "processados": 0})

    processados = 0
    for item in itens:
        remetente = item.get("From", "")
        assunto = item.get("Subject", "")
        texto = item.get("ExtractedMarkdownMessage", "") or item.get("RawTextBody", "")

        # Extrai o email de dentro de "Nome <email@dominio>"
        m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", remetente)
        email_lead = m.group(0).lower() if m else ""
        if not email_lead:
            continue

        try:
            lead = LeadProspeccao.objects.get(email=email_lead)
        except LeadProspeccao.DoesNotExist:
            logger.info("inbound: resposta de %s não corresponde a nenhum lead", email_lead)
            continue

        status_anterior = lead.status
        if lead.status not in ("cliente", "trial", "demo_agendada"):
            lead.status = "respondeu"
        lead.notas = (
            lead.notas + f"\n\n[RESPOSTA {timezone.now():%d/%m %H:%M}] {assunto}\n{texto[:1000]}"
        ).strip()
        lead.ultimo_contato_em = timezone.now()
        lead.proximo_followup_em = None  # para os follow-ups automáticos
        lead.save(update_fields=["status", "notas", "ultimo_contato_em", "proximo_followup_em"])

        # Marca o último email como respondido
        ultimo_email = lead.emails.filter(enviado_em__isnull=False).order_by("-enviado_em").first()
        if ultimo_email and not ultimo_email.respondeu_em:
            ultimo_email.respondeu_em = timezone.now()
            ultimo_email.status = "respondeu"
            ultimo_email.save(update_fields=["respondeu_em", "status"])

        if status_anterior != "respondeu":
            try:
                from .notificacao_comercial import notificar_resposta
                notificar_resposta(lead, "respondeu")
            except Exception:
                logger.exception("notificar_resposta (inbound) falhou lead=%s", lead.id)

        processados += 1

    return JsonResponse({"ok": True, "processados": processados})


# ─── Imagens de post de rede social (públicas — a Meta precisa buscar) ────────

@require_http_methods(["GET"])
def api_social_imagem(request, nome_arquivo: str):
    """
    Serve imagens de post geradas por instagram_service.gerar_imagem_post().

    Pública de propósito (sem auth) — a Instagram Graph API busca a imagem
    diretamente dos servidores da Meta, sem enviar nenhum cookie/token nosso.
    NUNCA serve nada fora de settings.SOCIAL_MEDIA_CACHE_DIR (pasta dedicada,
    separada do MEDIA_ROOT clínico) — nome de arquivo é validado contra
    path traversal antes de tocar o disco.
    """
    import os
    from django.conf import settings
    from django.http import FileResponse, Http404

    nome_seguro = os.path.basename(nome_arquivo)
    if nome_seguro != nome_arquivo or not nome_seguro.endswith(".png"):
        raise Http404("Nome de arquivo inválido.")

    caminho = os.path.join(settings.SOCIAL_MEDIA_CACHE_DIR, nome_seguro)
    if not os.path.isfile(caminho):
        raise Http404("Imagem não encontrada.")

    return FileResponse(open(caminho, "rb"), content_type="image/png")


# ─── Descadastro de 1 clique (RFC 8058 List-Unsubscribe) ──────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_prospeccao_descadastro(request, lead_id: int, token: str):
    """
    Descadastro público, sem login — link vai direto no header List-Unsubscribe
    do email (e também aparece no rodapé visível). GET mostra a confirmação,
    POST (inclusive o clique automático "List-Unsubscribe=One-Click" de
    Outlook/Gmail) já efetiva o descadastro na hora.
    """
    from django.http import HttpResponse
    from .brevo_service import token_descadastro

    lead = LeadProspeccao.objects.filter(id=lead_id).first()
    if not lead or token_descadastro(lead.id, lead.email) != token:
        return HttpResponse(
            "<p style='font-family:sans-serif;padding:40px;text-align:center'>Link inválido.</p>",
            status=404,
        )

    if request.method == "POST" or request.GET.get("confirmar") == "1":
        lead.status = "unsubscribe"
        lead.proximo_followup_em = None
        lead.save(update_fields=["status", "proximo_followup_em"])
        return HttpResponse(
            "<p style='font-family:sans-serif;padding:40px;text-align:center'>"
            "Pronto — você não vai receber mais emails nossos. Sentimos muito o incômodo.</p>"
        )

    return HttpResponse(
        "<div style='font-family:sans-serif;max-width:420px;margin:60px auto;text-align:center'>"
        "<p>Confirma que você não quer mais receber emails da SoloCRT Saúde?</p>"
        f"<form method='post' action=''>"
        "<button style='padding:10px 20px;font-size:15px;cursor:pointer' type='submit'>"
        "Sim, descadastrar</button></form></div>"
    )


# ─── Monitor de Licitações (setor público: Governo/saúde + Assistência/SUAS) ──

def _licitacao_to_dict(lc: LicitacaoOportunidade) -> dict:
    return {
        "id":              lc.id,
        "objeto":          lc.objeto,
        "orgao":           lc.orgao,
        "municipio":       lc.municipio,
        "uf":              lc.uf,
        "modalidade":      lc.modalidade,
        "valor_estimado":  float(lc.valor_estimado) if lc.valor_estimado is not None else None,
        "data_publicacao": lc.data_publicacao.isoformat() if lc.data_publicacao else None,
        "data_abertura":   lc.data_abertura.isoformat() if lc.data_abertura else None,
        "link_origem":     lc.link_origem,
        "area":            lc.area,
        "area_display":    lc.get_area_display(),
        "palavras_match":  lc.palavras_match,
        "status":          lc.status,
        "status_display":  lc.get_status_display(),
        "notas":           lc.notas,
        "criado_em":       lc.criado_em.isoformat(),
    }


@_owner_required
def licitacoes_dashboard(request):
    return render(request, "licitacoes_dashboard.html")


@csrf_exempt
@_owner_required
def api_licitacoes_lista(request):
    qs = LicitacaoOportunidade.objects.all()
    area = request.GET.get("area")
    status = request.GET.get("status")
    uf = request.GET.get("uf")
    q = request.GET.get("q")
    if area:
        qs = qs.filter(area=area)
    if status:
        qs = qs.filter(status=status)
    if uf:
        qs = qs.filter(uf=uf.upper())
    if q:
        qs = qs.filter(objeto__icontains=q)

    from django.db.models import Count
    stats = {
        "total":        LicitacaoOportunidade.objects.count(),
        "novas":        LicitacaoOportunidade.objects.filter(status="nova").count(),
        "por_area":     dict(LicitacaoOportunidade.objects.values_list("area").annotate(n=Count("id"))),
        "por_status":   dict(LicitacaoOportunidade.objects.values_list("status").annotate(n=Count("id"))),
    }

    try:
        pagina = max(1, int(request.GET.get("pagina", 1)))
        por_pagina = min(100, max(1, int(request.GET.get("por_pagina", 50))))
    except (TypeError, ValueError):
        pagina, por_pagina = 1, 50
    ini = (pagina - 1) * por_pagina
    itens = [_licitacao_to_dict(lc) for lc in qs[ini:ini + por_pagina]]
    return JsonResponse({"licitacoes": itens, "total_filtrado": qs.count(), "stats": stats})


@csrf_exempt
@_owner_required
def api_licitacao_status(request, licitacao_id: int):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    try:
        lc = LicitacaoOportunidade.objects.get(pk=licitacao_id)
    except LicitacaoOportunidade.DoesNotExist:
        return JsonResponse({"erro": "Licitação não encontrada."}, status=404)
    data = _json_body(request)
    novo_status = data.get("status")
    validos = {c[0] for c in LicitacaoOportunidade.STATUS}
    if novo_status and novo_status in validos:
        lc.status = novo_status
    if "notas" in data:
        lc.notas = data["notas"]
    lc.save(update_fields=["status", "notas", "atualizado_em"])
    return JsonResponse(_licitacao_to_dict(lc))
