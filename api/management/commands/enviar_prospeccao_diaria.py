"""
enviar_prospeccao_diaria.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Envia o primeiro contato (sequência 1) pra leads novos, todo dia, respeitando
uma rampa de aquecimento de domínio — comercial@solocrt.com é remetente novo,
mandar tudo de uma vez faz a Microsoft/Gmail jogar pra spam. A cada dia o
limite sobe conforme o volume total já entregue com sucesso cresce.

Pensado pra rodar 1x/dia via cron (Render) — pega os leads mais antigos com
status='novo' primeiro (FIFO), então leads novos de buscas futuras entram
na fila automaticamente sem precisar de intervenção manual.
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

# (volume total já enviado com sucesso, limite de novos contatos nesse dia)
# Cresce em degraus — o número da esquerda é o "quando você já mandou pelo
# menos X emails que a Microsoft/Gmail confirmaram entregues, seu limite de
# hoje sobe pra Y". Nunca passa de 300 (teto real do Brevo no plano grátis).
_RAMPA_AQUECIMENTO = [
    (0, 25),
    (25, 35),
    (60, 50),
    (110, 70),
    (180, 90),
    (270, 120),
    (400, 160),
    (600, 220),
]


def _limite_do_dia() -> int:
    total_enviado = EmailProspeccao.objects.filter(status="enviado").count()
    limite = _RAMPA_AQUECIMENTO[0][1]
    for piso, valor in _RAMPA_AQUECIMENTO:
        if total_enviado >= piso:
            limite = valor
    return limite


class Command(BaseCommand):
    help = "Envia primeiro contato pra leads novos, respeitando rampa de aquecimento de domínio."

    def handle(self, *args, **options):
        limite = _limite_do_dia()
        leads = list(LeadProspeccao.objects.filter(status="novo").order_by("criado_em")[:limite])
        total_ja_enviado = EmailProspeccao.objects.filter(status="enviado").count()
        self.stdout.write(
            f"Volume total já entregue: {total_ja_enviado} | Limite de hoje: {limite} | "
            f"Leads selecionados: {len(leads)}"
        )

        enviados = 0
        erros = 0
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

        self.stdout.write(f"TOTAL enviados: {enviados}")
        self.stdout.write(f"TOTAL erros: {erros}")
