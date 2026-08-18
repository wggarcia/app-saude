"""
prospeccao_funil.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fecha o ciclo entre o agente de prospecção (LeadProspeccao) e o produto
real (Empresa/TrialEmpresa/pagamento).

O lead frio recebe um email com link direto pro cadastro self-service.
Quando ele:
  1. ativa o trial de 15 dias  → LeadProspeccao.status = 'trial'
  2. tem um pagamento aprovado → LeadProspeccao.status = 'cliente' + WhatsApp

Casamento é por email (LeadProspeccao.email == Empresa.email). Se o
email não corresponder a nenhum lead prospectado (ex. cliente veio
orgânico, não veio do agente), as funções não fazem nada — o
signup/pagamento em si nunca depende deste módulo.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def marcar_trial_iniciado(email: str) -> None:
    """Chamado quando uma empresa ativa o trial self-service (views_auth.ativar_trial)."""
    from .models import LeadProspeccao

    if not email:
        return

    lead = LeadProspeccao.objects.filter(email__iexact=email).exclude(
        status__in=["cliente", "descartado", "unsubscribe"]
    ).first()
    if not lead:
        return

    lead.status = "trial"
    lead.proximo_followup_em = None  # entrou no produto — para os follow-ups frios
    lead.save(update_fields=["status", "proximo_followup_em"])
    logger.info("prospeccao_funil: lead %s ativou trial", email)


def marcar_cliente_fechado(email: str) -> None:
    """Chamado quando um pagamento é aprovado (views_pagamento._processar_pagamento_aprovado).

    Esse é o evento que mais importa pro dono do negócio: o agente fechou
    uma venda sozinho. Dispara notificação de WhatsApp.
    """
    from .models import LeadProspeccao

    if not email:
        return

    lead = LeadProspeccao.objects.filter(email__iexact=email).exclude(status="cliente").first()
    if not lead:
        return

    lead.status = "cliente"
    lead.save(update_fields=["status"])
    logger.info("prospeccao_funil: lead %s virou cliente pagante", email)

    try:
        from .notificacao_comercial import notificar_resposta
        notificar_resposta(lead, "🎉 FECHOU! Virou cliente pagante")
    except Exception:
        logger.exception("prospeccao_funil: falha ao notificar fechamento de %s", email)
