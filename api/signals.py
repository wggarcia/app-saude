"""
Signals da api — dispara push FCM quando uma NotificacaoFuncionario é criada.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='api.NotificacaoFuncionario')
def notificacao_funcionario_post_save(sender, instance, created, **kwargs):
    """Envia push FCM toda vez que uma nova notificação é criada."""
    if not created:
        return
    try:
        from .push_service import enviar_push_funcionario
        enviar_push_funcionario(instance)
    except Exception:
        # Push nunca deve quebrar o fluxo principal
        pass
