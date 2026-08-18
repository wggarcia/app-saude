"""
Management command: nutrir_trials

Roda diariamente (adicionar ao cron do VPS, depois do processar_followups):
  15 8 * * * cd /opt/soluscrt && source venv/bin/activate && python manage.py nutrir_trials

Para cada empresa SST/Farmácia com trial ativo, no dia exato de cada ponto
de contato (1, 4, 9, 13 — ver trial_nurture.PONTOS_DE_CONTATO), gera e envia
um email de acompanhamento via IA. Isso substitui a demonstração ao vivo:
guia a empresa pelo produto sozinho, e no dia 13 empurra pra ativação do plano.

Idempotente: cada empresa recebe no máximo 1 email por dia de trial, porque
o filtro por dia exato (não "<=") só bate uma vez por ponto de contato.
"""
from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)

_SEGMENTOS_COBERTOS = ("empresa_", "farmacia_")


class Command(BaseCommand):
    help = "Envia emails de acompanhamento automático (nurture) para empresas em trial SST/Farmácia"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria enviado sem enviar")

    def handle(self, *args, **options):
        from api.models import TrialEmpresa, OnboardingPasso
        from api.trial_nurture import gerar_nurture, PONTOS_DE_CONTATO
        from api.sendgrid_service import enviar_email_transacional

        dry_run = options["dry_run"]
        agora = timezone.now()

        trials_ativos = TrialEmpresa.objects.filter(
            convertido=False,
            expira_em__gt=agora,
        ).select_related("empresa")

        enviados = 0
        erros = 0

        for trial in trials_ativos:
            empresa = trial.empresa
            if not (empresa.pacote_codigo or "").startswith(_SEGMENTOS_COBERTOS):
                continue  # fora do escopo do agente (hospital/governo/plano de saúde)

            dias_de_trial = (agora.date() - trial.iniciado_em.date()).days
            tema = PONTOS_DE_CONTATO.get(dias_de_trial)
            if not tema:
                continue  # não é dia de contato

            passos = list(
                OnboardingPasso.objects.filter(empresa=empresa).values_list("passo", flat=True)
            )
            progresso = ", ".join(dict(OnboardingPasso.PASSOS)[p] for p in passos) if passos else "nada ainda"

            self.stdout.write(f"  → {empresa.email} (dia {dias_de_trial}, tema={tema}, progresso={progresso})")

            if dry_run:
                continue

            try:
                resultado = gerar_nurture(empresa, tema, progresso)
            except Exception as exc:
                self.stderr.write(f"    ERRO ao gerar: {exc}")
                erros += 1
                continue

            sucesso = enviar_email_transacional(
                empresa.email, empresa.nome, resultado["assunto"], resultado["corpo_html"]
            )
            if sucesso:
                enviados += 1
                self.stdout.write("    ✓ Enviado")
            else:
                erros += 1
                self.stderr.write("    ERRO ao enviar via SendGrid")

        self.stdout.write(
            f"\n[nutrir_trials] {enviados} enviados, {erros} erros"
            + (" (DRY RUN — nada enviado)" if dry_run else "")
        )
