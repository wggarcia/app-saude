"""
Fila de tarefas assíncronas (RQ) com FALLBACK SÍNCRONO.

Objetivo: tirar operações lentas fire-and-forget (envio de e-mail/push, IA de
lote, PDFs pesados) de dentro da request HTTP, para o worker não ficar preso.

Segurança / rollout gradual:
  - Controlado por settings.TASK_QUEUE_ENABLED (env TASK_QUEUE_ENABLED, default OFF).
  - Com a flag OFF, ou se o Redis/RQ estiver indisponível, `run_async` executa a
    função INLINE (comportamento idêntico ao de hoje). Ou seja: ligar/desligar a
    fila nunca quebra nada — no pior caso volta a rodar dentro da request.
  - `run_async` é fire-and-forget: NUNCA propaga exceção pro chamador (a operação
    é acessória à request; falha de e-mail não pode derrubar a ação principal).

Uso (passe SEMPRE identificadores serializáveis, não objetos ORM pesados):
    from api.tasks import run_async
    run_async("api.tasks.enviar_email_contrato_task", contrato_id)
"""
import logging

logger = logging.getLogger("api")


def _fila():
    """Retorna a fila RQ 'default' se habilitada e disponível; senão None."""
    from django.conf import settings
    if not getattr(settings, "TASK_QUEUE_ENABLED", False):
        return None
    try:
        import django_rq
        return django_rq.get_queue("default")
    except Exception as exc:  # rq ausente, Redis fora, etc. → fallback inline
        logger.warning("Fila RQ indisponível, rodando inline: %s", exc)
        return None


def _resolver(func):
    """Aceita callable ou string 'modulo.func' e retorna o callable."""
    if callable(func):
        return func
    modulo, _, nome = func.rpartition(".")
    import importlib
    return getattr(importlib.import_module(modulo), nome)


def run_async(func, *args, **kwargs):
    """Enfileira `func(*args, **kwargs)` no worker; se a fila estiver off/indisponível,
    roda inline. Fire-and-forget: engole exceções (loga), nunca derruba a request.

    `func` pode ser um callable ou uma string 'modulo.funcao' (preferível p/ RQ,
    que serializa por referência).
    """
    fila = _fila()
    if fila is not None:
        try:
            fila.enqueue(func, *args, **kwargs)
            return
        except Exception as exc:
            logger.warning("Falha ao enfileirar %s, rodando inline: %s", func, exc)
    # Fallback inline (comportamento atual) — protegido, fire-and-forget.
    try:
        _resolver(func)(*args, **kwargs)
    except Exception:
        logger.exception("Tarefa assíncrona (inline) falhou: %s", func)

# NOTA: para tarefas fire-and-forget de e-mail passamos a própria função +
# objeto (o RQ serializa a função por referência e faz pickle do arg). Para
# tarefas MAIS pesadas/críticas, prefira uma função de topo de módulo que receba
# um ID e recarregue do banco (evita pickle de objeto grande / dado stale).
