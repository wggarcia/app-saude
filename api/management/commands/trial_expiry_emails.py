"""
python manage.py trial_expiry_emails

Envia emails automáticos para empresas em trial prestes a expirar ou que já expiraram.
Configurar como Render Cron Job: roda diariamente às 09:00 BRT (12:00 UTC).

Emails disparados:
- Aviso 7 dias antes do vencimento (se ainda não enviado)
- Aviso 1 dia antes do vencimento (se ainda não enviado)
- Notificação de expiração no dia do vencimento
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.email_service import enviar_email_trial_expirado, enviar_email_trial_expirando
from api.models import Empresa, TrialEmpresa


class Command(BaseCommand):
    help = "Envia emails de aviso/expiração de trial para empresas SolusCRT"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista os emails que seriam enviados sem enviá-los",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        hoje = timezone.now().date()
        enviados = 0
        ignorados = 0

        trials_ativos = TrialEmpresa.objects.filter(
            convertido=False,
        ).select_related("empresa")

        for trial in trials_ativos:
            empresa = trial.empresa
            if not empresa.ativo and trial.expira_em.date() < hoje:
                # Já expirou e a empresa está inativa — skip
                ignorados += 1
                continue

            expira = trial.expira_em.date()
            dias_restantes = (expira - hoje).days

            if dias_restantes == 7:
                if dry_run:
                    self.stdout.write(f"  [DRY] Aviso 7 dias → {empresa.email}")
                else:
                    enviar_email_trial_expirando(empresa, 7)
                    self.stdout.write(f"  ✉  Aviso 7 dias → {empresa.email}")
                enviados += 1

            elif dias_restantes == 1:
                if dry_run:
                    self.stdout.write(f"  [DRY] Aviso último dia → {empresa.email}")
                else:
                    enviar_email_trial_expirando(empresa, 1)
                    self.stdout.write(f"  ✉  Aviso último dia → {empresa.email}")
                enviados += 1

            elif dias_restantes == 0:
                # Expirou hoje — desativar e notificar
                if empresa.ativo:
                    empresa.ativo = False
                    empresa.save(update_fields=["ativo"])
                if dry_run:
                    self.stdout.write(f"  [DRY] Trial expirado → {empresa.email}")
                else:
                    enviar_email_trial_expirado(empresa)
                    self.stdout.write(f"  ✉  Trial expirado → {empresa.email}")
                enviados += 1

            else:
                ignorados += 1

        prefixo = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixo}trial_expiry_emails concluído — {enviados} emails, {ignorados} ignorados"
            )
        )
