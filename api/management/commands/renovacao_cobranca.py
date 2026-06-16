"""
python manage.py renovacao_cobranca

Régua de renovação/dunning para clientes PAGANTES (não-trial).
Configurar como Render Cron Job diário.

Ações (aditivas, não alteram checkout nem webhook):
- 7 dias antes do vencimento: e-mail de aviso de renovação
- 1 dia antes: e-mail de aviso (urgente)
- No/após vencimento: registra evento de inadimplência (uma única vez por ciclo)
  e envia e-mail de contrato vencido. NÃO desativa a conta — o acesso já é
  bloqueado pelo middleware quando o plano expira; aqui só notificamos e
  alimentamos o painel financeiro.

Idempotência: a inadimplência só é registrada/enviada uma vez por ciclo de
vencimento (verifica se já existe evento após a data de expiração atual).
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.email_service import (
    enviar_email_renovacao_proxima,
    enviar_email_contrato_vencido,
)
from api.models import Empresa, FinanceiroEventoSaaS, TrialEmpresa


class Command(BaseCommand):
    help = "Avisos de renovação e dunning para clientes pagantes SolusCRT"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Lista o que seria feito sem enviar e-mails nem gravar eventos",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        agora = timezone.now()
        hoje = agora.date()
        avisos = 0
        inadimplencias = 0
        ignorados = 0

        # Empresas com contrato em trial não-convertido são tratadas pelo
        # comando trial_expiry_emails — excluímos para não duplicar.
        ids_trial = set(
            TrialEmpresa.objects.filter(convertido=False).values_list("empresa_id", flat=True)
        )

        pagantes = (
            Empresa.objects.filter(data_expiracao__isnull=False)
            .exclude(id__in=ids_trial)
        )

        for empresa in pagantes:
            exp = empresa.data_expiracao
            exp_date = exp.date() if hasattr(exp, "date") else exp
            dias = (exp_date - hoje).days

            if dias == 7 or dias == 1:
                if dry:
                    self.stdout.write(f"  [DRY] Renovação {dias}d → {empresa.email}")
                else:
                    enviar_email_renovacao_proxima(empresa, dias)
                    self.stdout.write(f"  ✉  Renovação {dias}d → {empresa.email}")
                avisos += 1

            elif dias <= 0:
                # Vencido — registra inadimplência só uma vez por ciclo
                ja_registrado = FinanceiroEventoSaaS.objects.filter(
                    empresa=empresa,
                    tipo_evento="inadimplencia",
                    criado_em__gte=exp,
                ).exists()
                if ja_registrado:
                    ignorados += 1
                    continue
                if dry:
                    self.stdout.write(f"  [DRY] Inadimplência → {empresa.email} (venceu {exp_date})")
                else:
                    FinanceiroEventoSaaS.objects.create(
                        empresa=empresa,
                        tipo_evento="inadimplencia",
                        pacote_codigo=empresa.pacote_codigo,
                        ciclo=empresa.plano,
                        valor=0,
                        status="vencido",
                        observacao=f"Contrato vencido em {exp_date} — dunning automático.",
                    )
                    enviar_email_contrato_vencido(empresa)
                    self.stdout.write(f"  🔴 Inadimplência → {empresa.email}")
                inadimplencias += 1
            else:
                ignorados += 1

        # Limpa cache do painel para refletir as novas inadimplências
        if not dry:
            try:
                from api.epidemiologia import clear_panorama_cache
                clear_panorama_cache()
            except Exception:
                pass

        prefixo = "[DRY RUN] " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefixo}renovacao_cobranca concluído — {avisos} avisos, "
            f"{inadimplencias} inadimplências, {ignorados} ignorados"
        ))
