"""
0064 - Extend subscription for expired accounts + ASO notification infra.
- Reactivates empresas with ativo=False where data_expiracao was the cause
- Extends wfggarcia@hotmail.com subscription by 1 year from today
"""
from django.db import migrations
from django.utils import timezone
from datetime import timedelta


def extend_subscription(apps, schema_editor):
    Empresa = apps.get_model("api", "Empresa")
    now = timezone.now()

    # Extend all empresas whose subscription just expired (within last 30 days)
    expired = Empresa.objects.filter(
        ativo=False,
        data_expiracao__gte=now - timedelta(days=30),
        data_expiracao__lt=now,
    )
    for e in expired:
        e.ativo = True
        e.data_expiracao = now + timedelta(days=365)
        e.save(update_fields=["ativo", "data_expiracao"])

    # Also ensure the main dev account is always active
    dev = Empresa.objects.filter(email="wfggarcia@hotmail.com").first()
    if dev:
        dev.ativo = True
        dev.data_expiracao = now + timedelta(days=365)
        dev.save(update_fields=["ativo", "data_expiracao"])

    demo = Empresa.objects.filter(email="empresa.demo@soluscrt.com").first()
    if demo:
        demo.ativo = True
        demo.data_expiracao = now + timedelta(days=365)
        demo.save(update_fields=["ativo", "data_expiracao"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0063_credencial_app_notificacao_funcionario"),
    ]

    operations = [
        migrations.RunPython(extend_subscription, noop),
    ]
