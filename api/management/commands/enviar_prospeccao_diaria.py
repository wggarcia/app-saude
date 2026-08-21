"""
enviar_prospeccao_diaria.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Envia o primeiro contato (sequência 1) pra leads novos, em LOTES por hora,
respeitando um teto diário e uma rampa de aquecimento de domínio.

Pensado pra rodar DE HORA EM HORA via cron (Render):
  manage.py enviar_prospeccao_diaria --por-execucao 100 --teto-dia 300 --rampa-auto

Cada execução manda até --por-execucao (padrão 100). O --teto-dia (máx 300, o
teto do Brevo grátis) impede que a soma do dia passe do limite — então rodando
de hora em hora, ele manda 100 na 1ª hora, 100 na 2ª, 100 na 3ª e para (300/dia).

--rampa-auto: nos primeiros dias o teto efetivo é menor (aquecimento de domínio
— remetente novo que dispara 300/dia de cara cai no spam). Sobe sozinho:
  dias 1-3: 100/dia · dias 4-7: 200/dia · dia 8+: 300/dia.
Pega os leads 'novo' mais antigos primeiro (FIFO); leads de buscas futuras
entram na fila automaticamente.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.brevo_service import enviar_email
from api.email_ai import gerar_email
from api.models import EmailProspeccao, LeadProspeccao

_BREVO_TETO_GRATIS = 300  # limite físico do plano grátis do Brevo


def _cap_do_dia(teto_dia: int, rampa_auto: bool) -> int:
    """Teto de envios de HOJE. Com --rampa-auto, cresce conforme os dias desde
    o 1º envio (aquecimento de domínio)."""
    teto_dia = min(teto_dia, _BREVO_TETO_GRATIS)
    if not rampa_auto:
        return teto_dia
    primeiro = (EmailProspeccao.objects
                .filter(status="enviado", enviado_em__isnull=False)
                .order_by("enviado_em").first())
    if not primeiro:
        dia = 1
    else:
        dia = (timezone.now().date() - primeiro.enviado_em.date()).days + 1
    if dia <= 3:
        base = 100
    elif dia <= 7:
        base = 200
    else:
        base = 300
    return min(base, teto_dia)


class Command(BaseCommand):
    help = "Envia 1º contato pra leads novos em lotes/hora, com teto diário e rampa de aquecimento."

    def add_arguments(self, parser):
        parser.add_argument("--por-execucao", type=int, default=100,
                            help="máximo de e-mails por execução/lote (padrão 100)")
        parser.add_argument("--teto-dia", type=int, default=300,
                            help="máximo de e-mails no dia somando todos os lotes (máx 300, Brevo grátis)")
        parser.add_argument("--rampa-auto", action="store_true",
                            help="aquecer o domínio: 100/dia (dias 1-3), 200 (4-7), 300 (8+)")

    def handle(self, *args, **options):
        por_execucao = options["por_execucao"]
        cap_dia = _cap_do_dia(options["teto_dia"], options["rampa_auto"])

        hoje = timezone.localdate()
        enviados_hoje = EmailProspeccao.objects.filter(
            status="enviado", enviado_em__date=hoje).count()
        restante_hoje = max(0, cap_dia - enviados_hoje)
        limite = min(por_execucao, restante_hoje)

        total_geral = EmailProspeccao.objects.filter(status="enviado").count()
        self.stdout.write(
            f"Teto do dia: {cap_dia} | já enviados hoje: {enviados_hoje} | "
            f"restam hoje: {restante_hoje} | ESTE LOTE: {limite} "
            f"(total geral entregue: {total_geral})"
        )
        if limite <= 0:
            self.stdout.write("Teto do dia já atingido — nada a enviar neste lote.")
            return

        leads = list(LeadProspeccao.objects.filter(status="novo").order_by("criado_em")[:limite])
        if not leads:
            self.stdout.write("Nenhum lead com status 'novo' na fila.")
            return

        enviados = erros = 0
        for lead in leads:
            try:
                resultado = gerar_email(lead, numero_sequencia=1)
            except Exception as exc:
                self.stdout.write(f"  ERRO ao gerar (lead={lead.id} {lead.email}): {exc}")
                erros += 1
                continue

            email_obj = EmailProspeccao.objects.create(
                lead=lead, numero_sequencia=1,
                assunto=resultado["assunto"], corpo_html=resultado["corpo_html"],
                corpo_texto=resultado["corpo_texto"], status="rascunho",
            )

            if enviar_email(email_obj):
                lead.status = "email_enviado"
                lead.ultimo_contato_em = timezone.now()
                lead.proximo_followup_em = timezone.now() + timedelta(days=3)
                lead.save(update_fields=["status", "ultimo_contato_em", "proximo_followup_em"])
                enviados += 1
                self.stdout.write(f"  OK: {lead.empresa} <{lead.email}>")
            else:
                erros += 1
                self.stdout.write(f"  ERRO ao enviar (lead={lead.id} {lead.email}): {email_obj.erro[:150]}")

            time.sleep(1.5)

        self.stdout.write(f"LOTE FINALIZADO — enviados: {enviados} | erros: {erros}")
