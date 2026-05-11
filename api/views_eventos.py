"""
Event Backbone — Outbox Pattern, subscriptions, DLQ, processamento de eventos.
Endpoint: GET  /api/eventos/status
          GET  /api/eventos/dlq
          POST /api/eventos/publicar
          GET  /api/eventos/subscricoes
          POST /api/eventos/subscricoes
          POST /api/eventos/reprocessar/<uuid>
Page:     GET  /eventos/
"""
import hashlib
import hmac
import json
import re
from datetime import date, datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Count, Q
from .views_dashboard import _empresa_autenticada


def _evento_to_dict(e):
    return {
        "id": str(e.id),
        "tipo_evento": e.tipo_evento,
        "agregado_tipo": e.agregado_tipo,
        "agregado_id": e.agregado_id,
        "status": e.status,
        "tentativas": e.tentativas,
        "max_tentativas": e.max_tentativas,
        "erro_ultimo": e.erro_ultimo[:200] if e.erro_ultimo else "",
        "criado_em": e.criado_em.isoformat(),
        "criado_em_fmt": e.criado_em.strftime("%d/%m/%Y %H:%M:%S"),
        "processado_em": e.processado_em.isoformat() if e.processado_em else None,
    }


def api_eventos_status(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import OutboxEvento

        qs = OutboxEvento.objects.filter(empresa=empresa)
        agora = timezone.now()
        ultimas_24h = agora - timedelta(hours=24)
        ultimos_7d = agora - timedelta(days=7)

        por_status = dict(
            qs.values("status").annotate(total=Count("id")).values_list("status", "total")
        )
        por_tipo = list(
            qs.filter(criado_em__gte=ultimos_7d)
            .values("tipo_evento")
            .annotate(total=Count("id"))
            .order_by("-total")[:10]
        )
        taxa_sucesso_24h = 0
        total_24h = qs.filter(criado_em__gte=ultimas_24h).count()
        entregues_24h = qs.filter(criado_em__gte=ultimas_24h, status="entregue").count()
        if total_24h > 0:
            taxa_sucesso_24h = round(entregues_24h / total_24h * 100, 1)

        pendentes = list(qs.filter(status="pendente").order_by("criado_em")[:20])
        falhas = list(qs.filter(status__in=["falha", "dlq"]).order_by("-criado_em")[:10])

        return JsonResponse({
            "empresa": empresa.nome,
            "timestamp": agora.isoformat(),
            "resumo": {
                "total": qs.count(),
                "por_status": por_status,
                "taxa_sucesso_24h": taxa_sucesso_24h,
                "total_24h": total_24h,
                "entregues_24h": entregues_24h,
            },
            "por_tipo_7d": por_tipo,
            "pendentes": [_evento_to_dict(e) for e in pendentes],
            "falhas_recentes": [_evento_to_dict(e) for e in falhas],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_eventos_dlq(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import OutboxEvento
        dlq = list(OutboxEvento.objects.filter(empresa=empresa, status="dlq").order_by("-criado_em")[:50])
        return JsonResponse({
            "total_dlq": len(dlq),
            "eventos": [_evento_to_dict(e) for e in dlq],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
def api_eventos_publicar(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    tipo = body.get("tipo_evento", "").strip()
    if not tipo:
        return JsonResponse({"erro": "tipo_evento obrigatório"}, status=400)

    try:
        from .models import OutboxEvento
        evento = OutboxEvento.objects.create(
            empresa=empresa,
            tipo_evento=tipo,
            agregado_tipo=body.get("agregado_tipo", ""),
            agregado_id=str(body.get("agregado_id", "")),
            payload=body.get("payload", {}),
        )
        _processar_evento(evento)
        return JsonResponse({"id": str(evento.id), "status": evento.status}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def _processar_evento(evento):
    """Entrega síncrona via webhook para subscritores ativos."""
    try:
        from .models import SubscricaoEvento
        import urllib.request

        subs = SubscricaoEvento.objects.filter(empresa=evento.empresa, ativo=True)
        entregue = False
        for sub in subs:
            pattern = sub.tipo_evento_pattern.replace("*", ".*")
            if not re.match(f"^{pattern}$", evento.tipo_evento):
                continue
            payload_bytes = json.dumps({
                "id": str(evento.id),
                "tipo": evento.tipo_evento,
                "agregado": {"tipo": evento.agregado_tipo, "id": evento.agregado_id},
                "payload": evento.payload,
                "timestamp": evento.criado_em.isoformat(),
            }).encode()
            headers = {"Content-Type": "application/json"}
            if sub.secret_hmac:
                sig = hmac.new(sub.secret_hmac.encode(), payload_bytes, hashlib.sha256).hexdigest()
                headers["X-Signature-256"] = f"sha256={sig}"
            try:
                req = urllib.request.Request(sub.url_destino, data=payload_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=5):
                    entregue = True
            except Exception as err:
                evento.erro_ultimo = str(err)[:500]
                evento.tentativas += 1
                if evento.tentativas >= evento.max_tentativas:
                    evento.status = "dlq"
                else:
                    evento.status = "falha"
                    evento.proxima_tentativa = timezone.now() + timedelta(minutes=2 ** evento.tentativas)
                evento.save(update_fields=["status", "tentativas", "erro_ultimo", "proxima_tentativa"])
                return

        if entregue or not subs.exists():
            evento.status = "entregue"
            evento.processado_em = timezone.now()
            evento.save(update_fields=["status", "processado_em"])
    except Exception:
        pass


@csrf_exempt
def api_eventos_reprocessar(request, evento_id):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        from .models import OutboxEvento
        evt = OutboxEvento.objects.get(id=evento_id, empresa=empresa)
        evt.status = "pendente"
        evt.tentativas = 0
        evt.erro_ultimo = ""
        evt.proxima_tentativa = None
        evt.save()
        _processar_evento(evt)
        return JsonResponse({"id": str(evt.id), "status": evt.status})
    except OutboxEvento.DoesNotExist:
        return JsonResponse({"erro": "Evento não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_eventos_subscricoes(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
            from .models import SubscricaoEvento
            sub = SubscricaoEvento.objects.create(
                empresa=empresa,
                tipo_evento_pattern=body.get("tipo_evento_pattern", "*"),
                url_destino=body.get("url_destino", ""),
                secret_hmac=body.get("secret_hmac", ""),
                ativo=True,
            )
            return JsonResponse({"id": sub.id, "criado": True}, status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    try:
        from .models import SubscricaoEvento
        subs = SubscricaoEvento.objects.filter(empresa=empresa).order_by("-criado_em")
        return JsonResponse({
            "subscricoes": [
                {
                    "id": s.id,
                    "pattern": s.tipo_evento_pattern,
                    "url": s.url_destino[:80] + ("..." if len(s.url_destino) > 80 else ""),
                    "ativo": s.ativo,
                    "criado_em": s.criado_em.strftime("%d/%m/%Y"),
                }
                for s in subs
            ]
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def eventos_page(request):
    from django.shortcuts import render, redirect
    from .access_control import get_setor, _destino_correto
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return redirect("/login-empresa/")
    if get_setor(empresa) not in ("empresa", "hospital"):
        return redirect(_destino_correto(get_setor(empresa)))
    return render(request, "eventos.html")
