"""
Endpoints de saúde para balanceador/monitoramento.

  GET /healthz  — liveness: o processo responde? (não toca em DB/cache)
  GET /readyz   — readiness: DB e cache respondem? (503 se algo falhar)

Diferente do healthcheck antigo, que batia numa view de negócio pesada e podia
reprovar sob carga do próprio banco.
"""
import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)


def healthz(request):
    """Liveness — 200 fixo se o processo está de pé."""
    return JsonResponse({"status": "ok"})


def readyz(request):
    """Readiness — verifica dependências críticas (DB + cache)."""
    componentes = {}
    ok = True

    # Banco
    try:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        componentes["db"] = "ok"
    except Exception as exc:
        componentes["db"] = f"erro: {str(exc)[:120]}"
        ok = False
        logger.error("readyz: falha no banco", exc_info=True)

    # Cache (Redis em produção)
    try:
        from django.core.cache import cache
        cache.set("_readyz", "1", 5)
        componentes["cache"] = "ok" if cache.get("_readyz") == "1" else "degradado"
    except Exception as exc:
        componentes["cache"] = f"erro: {str(exc)[:120]}"
        # cache é degradável (IGNORE_EXCEPTIONS), não derruba readiness sozinho
        logger.warning("readyz: falha no cache: %s", exc)

    return JsonResponse(
        {"status": "ok" if ok else "unavailable", "componentes": componentes},
        status=200 if ok else 503,
    )
