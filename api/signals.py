"""
Signals da api — dispara push FCM quando uma NotificacaoFuncionario é criada.
"""
import threading

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='api.NotificacaoFuncionario')
def notificacao_funcionario_post_save(sender, instance, created, **kwargs):
    """Envia push FCM em background — não bloqueia o request HTTP."""
    if not created:
        return

    notificacao_id = instance.pk

    def _enviar():
        try:
            from django.db import connection
            from .push_service import enviar_push_funcionario
            from .models import NotificacaoFuncionario
            notificacao = NotificacaoFuncionario.objects.get(pk=notificacao_id)
            enviar_push_funcionario(notificacao)
        except Exception:
            pass
        finally:
            try:
                from django.db import connection
                connection.close()
            except Exception:
                pass

    thread = threading.Thread(target=_enviar, daemon=True)
    thread.start()
