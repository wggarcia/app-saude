from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import AlertaGovernamental, DispositivoAutorizado, DispositivoPushPublico, DonoSaaS, Empresa, EmpresaUsuario


def session_idle_timeout():
    return timedelta(minutes=15) if settings.DEBUG else timedelta(hours=8)


def collect_health_snapshot(now=None, revoked_alert_threshold_days=14, push_stale_days=45):
    now = now or timezone.now()
    session_threshold = now - session_idle_timeout()
    revoked_threshold = now - timedelta(days=revoked_alert_threshold_days)
    push_threshold = now - timedelta(days=push_stale_days)

    return {
        "generated_at": now.isoformat(),
        "thresholds": {
            "session_idle_hours": round(session_idle_timeout().total_seconds() / 3600, 2),
            "revoked_alert_days": revoked_alert_threshold_days,
            "push_stale_days": push_stale_days,
        },
        "devices": {
            "active_total": DispositivoAutorizado.objects.filter(ativo=True).count(),
            "stale_active": DispositivoAutorizado.objects.filter(
                ativo=True,
                ultimo_acesso__lt=session_threshold,
            ).count(),
            "inactive_total": DispositivoAutorizado.objects.filter(ativo=False).count(),
        },
        "sessions": {
            "empresa_stale": Empresa.objects.filter(
                sessao_ativa_chave__isnull=False,
                sessao_ativa_em__lt=session_threshold,
            ).exclude(sessao_ativa_chave="").count(),
            "usuario_stale": EmpresaUsuario.objects.filter(
                sessao_ativa_chave__isnull=False,
                sessao_ativa_em__lt=session_threshold,
            ).exclude(sessao_ativa_chave="").count(),
            "owner_stale": DonoSaaS.objects.filter(
                sessao_ativa_chave__isnull=False,
                sessao_ativa_em__lt=session_threshold,
            ).exclude(sessao_ativa_chave="").count(),
        },
        "push": {
            "active_total": DispositivoPushPublico.objects.filter(ativo=True).count(),
            "stale_active": DispositivoPushPublico.objects.filter(
                ativo=True,
                atualizado_em__lt=push_threshold,
            ).count(),
            "inactive_total": DispositivoPushPublico.objects.filter(ativo=False).count(),
        },
        "alerts": {
            "published_total": AlertaGovernamental.objects.filter(
                status=AlertaGovernamental.STATUS_PUBLICADO
            ).count(),
            "revoked_total": AlertaGovernamental.objects.filter(
                status=AlertaGovernamental.STATUS_REVOGADO
            ).count(),
            "revoked_old": AlertaGovernamental.objects.filter(
                status=AlertaGovernamental.STATUS_REVOGADO,
                revogado_em__lt=revoked_threshold,
            ).count(),
        },
    }


def apply_safe_cleanup(now=None, clear_cache=False, push_stale_days=45):
    now = now or timezone.now()
    session_threshold = now - session_idle_timeout()
    push_threshold = now - timedelta(days=push_stale_days)

    stale_devices = DispositivoAutorizado.objects.filter(
        ativo=True,
        ultimo_acesso__lt=session_threshold,
    )
    stale_empresa_sessions = Empresa.objects.filter(
        sessao_ativa_chave__isnull=False,
        sessao_ativa_em__lt=session_threshold,
    ).exclude(sessao_ativa_chave="")
    stale_user_sessions = EmpresaUsuario.objects.filter(
        sessao_ativa_chave__isnull=False,
        sessao_ativa_em__lt=session_threshold,
    ).exclude(sessao_ativa_chave="")
    stale_owner_sessions = DonoSaaS.objects.filter(
        sessao_ativa_chave__isnull=False,
        sessao_ativa_em__lt=session_threshold,
    ).exclude(sessao_ativa_chave="")
    stale_push_tokens = DispositivoPushPublico.objects.filter(
        ativo=True,
        atualizado_em__lt=push_threshold,
    )

    result = {
        "devices_deactivated": stale_devices.count(),
        "empresa_sessions_closed": stale_empresa_sessions.count(),
        "user_sessions_closed": stale_user_sessions.count(),
        "owner_sessions_closed": stale_owner_sessions.count(),
        "push_tokens_deactivated": stale_push_tokens.count(),
        "cache_cleared": bool(clear_cache),
    }

    stale_devices.update(ativo=False)
    stale_empresa_sessions.update(
        sessao_ativa_chave=None,
        sessao_ativa_device_id=None,
        sessao_ativa_em=None,
    )
    stale_user_sessions.update(
        sessao_ativa_chave=None,
        sessao_ativa_device_id=None,
        sessao_ativa_em=None,
    )
    stale_owner_sessions.update(
        sessao_ativa_chave=None,
        sessao_ativa_em=None,
    )
    stale_push_tokens.update(ativo=False)

    if clear_cache:
        cache.clear()

    return result


def maintenance_report(apply=False, clear_cache=False, now=None, revoked_alert_threshold_days=14, push_stale_days=45):
    before = collect_health_snapshot(
        now=now,
        revoked_alert_threshold_days=revoked_alert_threshold_days,
        push_stale_days=push_stale_days,
    )
    cleanup = None
    after = before
    if apply:
        cleanup = apply_safe_cleanup(now=now, clear_cache=clear_cache, push_stale_days=push_stale_days)
        after = collect_health_snapshot(
            now=now,
            revoked_alert_threshold_days=revoked_alert_threshold_days,
            push_stale_days=push_stale_days,
        )
    return {
        "mode": "apply" if apply else "dry_run",
        "before": before,
        "cleanup": cleanup,
        "after": after,
    }
