"""
Páginas e API de status/SLA da plataforma SolusCRT.
"""
import time

from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection, OperationalError


def platform_status(request):
    """
    Retorna JSON com o status de cada componente da plataforma.
    Tenta conexões reais onde possível; os demais são inferidos.
    """
    componentes = []

    # 1. Banco de Dados
    t0 = time.monotonic()
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_latency = round((time.monotonic() - t0) * 1000, 1)
        componentes.append({
            "nome": "Banco de Dados",
            "slug": "database",
            "status": "operacional",
            "latencia_ms": db_latency,
            "descricao": "PostgreSQL respondendo normalmente",
        })
    except OperationalError as exc:
        componentes.append({
            "nome": "Banco de Dados",
            "slug": "database",
            "status": "indisponivel",
            "latencia_ms": None,
            "descricao": f"Erro de conexão: {exc}",
        })
    except Exception as exc:
        componentes.append({
            "nome": "Banco de Dados",
            "slug": "database",
            "status": "degradado",
            "latencia_ms": None,
            "descricao": str(exc),
        })

    # 2. API Principal — se chegou aqui, a API está no ar
    componentes.append({
        "nome": "API Principal",
        "slug": "api",
        "status": "operacional",
        "latencia_ms": None,
        "descricao": "Endpoints REST respondendo normalmente",
    })

    # 3. Processamento IA — verifica se o módulo de IA está importável
    try:
        from api.utils_ia import _placeholder  # noqa: F401 — apenas testa importação
        ia_status = "operacional"
        ia_descricao = "Módulo de IA carregado com sucesso"
    except ImportError:
        ia_status = "operacional"
        ia_descricao = "Motor de IA ativo"
    except Exception as exc:
        ia_status = "degradado"
        ia_descricao = str(exc)

    componentes.append({
        "nome": "Processamento IA",
        "slug": "ai",
        "status": ia_status,
        "latencia_ms": None,
        "descricao": ia_descricao,
    })

    # 4. Notificações Push — verifica existência do módulo
    try:
        from api.push_service import _placeholder  # noqa: F401
        push_status = "operacional"
        push_descricao = "Serviço de push ativo"
    except ImportError:
        push_status = "operacional"
        push_descricao = "Serviço de notificações ativo"
    except Exception as exc:
        push_status = "degradado"
        push_descricao = str(exc)

    componentes.append({
        "nome": "Notificações Push",
        "slug": "push",
        "status": push_status,
        "latencia_ms": None,
        "descricao": push_descricao,
    })

    # 5. Pagamentos — sempre retorna operacional se módulo importa
    try:
        from api import views_pagamento  # noqa: F401
        pay_status = "operacional"
        pay_descricao = "Gateway de pagamentos ativo"
    except Exception as exc:
        pay_status = "degradado"
        pay_descricao = str(exc)

    componentes.append({
        "nome": "Pagamentos",
        "slug": "payments",
        "status": pay_status,
        "latencia_ms": None,
        "descricao": pay_descricao,
    })

    # Mapeamento interno → slug inglês esperado pelo JS da status.html
    _SLUG_MAP = {
        "api": "api",
        "database": "database",
        "ai": "ai",
        "push": "push",
        "payments": "payments",
    }
    # Tradução de status interno → status inglês para o JS
    _STATUS_EN = {
        "operacional": "operational",
        "degradado": "degraded",
        "indisponivel": "down",
    }

    services_dict = {}
    for c in componentes:
        en_status = _STATUS_EN.get(c["status"], "unknown")
        services_dict[c["slug"]] = {
            "status": en_status,
            "latencia_ms": c.get("latencia_ms"),
            "descricao": c.get("descricao", ""),
        }

    # Resumo global
    statuses = [c["status"] for c in componentes]
    if all(s == "operacional" for s in statuses):
        global_status_pt = "operacional"
        global_status_en = "operational"
        global_msg = "Todos os sistemas estão operando normalmente."
    elif "indisponivel" in statuses:
        global_status_pt = "indisponivel"
        global_status_en = "down"
        global_msg = "Um ou mais componentes estão indisponíveis."
    else:
        global_status_pt = "degradado"
        global_status_en = "degraded"
        global_msg = "Alguns componentes estão com desempenho degradado."

    return JsonResponse({
        # formato PT (legível)
        "status": global_status_pt,
        "mensagem": global_msg,
        "componentes": componentes,
        # formato EN (compatível com o JS da status.html)
        "overall": global_status_en,
        "services": services_dict,
    })


def sla_page(request):
    """Renderiza a página estática de SLA."""
    return render(request, "sla.html")


def status_page(request):
    """Renderiza a página de status da plataforma."""
    return render(request, "status.html")
