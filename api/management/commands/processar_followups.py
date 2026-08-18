"""
Management command: processar_followups

Roda diariamente (adicionar ao cron do VPS):
  0 8 * * * cd /opt/soluscrt && source venv/bin/activate && python manage.py processar_followups

Para cada lead com proximo_followup_em <= agora e status ativo:
  1. Determina o número da sequência (followup 2, 3 ou 4)
  2. Gera email com IA via email_ai.gerar_email()
  3. Envia via sendgrid_service.enviar_email()
  4. Atualiza status + proximo_followup_em do lead
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Envia follow-ups automáticos para leads que estão aguardando"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra quais emails seriam enviados sem realmente enviar",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=50,
            help="Máximo de emails para enviar nesta execução (padrão: 50)",
        )

    def handle(self, *args, **options):
        from api.models import LeadProspeccao, EmailProspeccao
        from api.email_ai import gerar_email
        from api.sendgrid_service import enviar_email

        dry_run = options["dry_run"]
        max_emails = options["max"]
        agora = timezone.now()

        # Leads com followup pendente
        leads_pendentes = LeadProspeccao.objects.filter(
            proximo_followup_em__isnull=False,
            proximo_followup_em__lte=agora,
            status__in=["email_enviado", "followup_1", "followup_2"],
        ).order_by("proximo_followup_em")[:max_emails]

        total = leads_pendentes.count()
        self.stdout.write(f"[processar_followups] {total} leads com followup pendente{' (DRY RUN)' if dry_run else ''}")

        # Mapeamento status → próxima sequência
        _seq_por_status = {
            "email_enviado": 2,
            "followup_1":    3,
            "followup_2":    4,
        }

        enviados = 0
        erros = 0

        for lead in leads_pendentes:
            seq = _seq_por_status.get(lead.status, 2)

            self.stdout.write(f"  → {lead.email} ({lead.get_segmento_display()}) seq={seq}")

            if dry_run:
                continue

            try:
                resultado = gerar_email(lead, seq)
            except Exception as exc:
                self.stderr.write(f"    ERRO ao gerar email: {exc}")
                erros += 1
                continue

            email_obj = EmailProspeccao.objects.create(
                lead=lead,
                numero_sequencia=seq,
                assunto=resultado["assunto"],
                corpo_html=resultado["corpo_html"],
                corpo_texto=resultado["corpo_texto"],
                status="rascunho",
            )

            sucesso = enviar_email(email_obj)

            if sucesso:
                # Atualizar status do lead
                mapa_status = {
                    2: ("followup_1",    7),
                    3: ("followup_2",   14),
                    4: ("followup_final", None),
                }
                novo_status, dias = mapa_status.get(seq, ("followup_final", None))
                lead.status = novo_status
                lead.ultimo_contato_em = agora
                lead.proximo_followup_em = agora + timedelta(days=dias) if dias else None
                lead.save(update_fields=["status", "ultimo_contato_em", "proximo_followup_em"])
                enviados += 1
                self.stdout.write(f"    ✓ Enviado (novo status: {lead.get_status_display()})")
            else:
                self.stderr.write(f"    ERRO ao enviar: {email_obj.erro}")
                erros += 1

        self.stdout.write(
            f"\n[processar_followups] Concluído: {enviados} enviados, {erros} erros"
            + (" (DRY RUN — nada enviado)" if dry_run else "")
        )
