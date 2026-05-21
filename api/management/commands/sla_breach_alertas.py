"""
python manage.py sla_breach_alertas

Detecta guias com SLA ANS violado (RN 395/452) e envia alerta por email
para a operadora. Registrar como Render Cron Job — roda 2x/dia.

Configurar no render.yaml:
  schedule: "0 8,14 * * *"  (08h e 14h BRT = 11h e 17h UTC)
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.email_service import enviar_email_sla_breach_critico
from api.models import Empresa, GuiaAutorizacao

# Prazos ANS em horas corridas por tipo de guia (RN 395/452 simplificado)
SLA_MAP = {
    "urgencia":   4,
    "urgência":   4,
    "consulta":   168,   # 7 dias úteis ≈ 168h
    "exame":      240,   # 10 dias úteis ≈ 240h
    "internacao": 504,   # 21 dias úteis ≈ 504h
    "internação": 504,
    "cirurgia":   504,
    "quimio":     240,
    "radio":      240,
    "home":       240,
}
DEFAULT_PRAZO_H = 168  # fallback: 7 dias


def _prazo_horas(tipo: str) -> int:
    tipo_lower = (tipo or "").lower()
    for key, horas in SLA_MAP.items():
        if key in tipo_lower:
            return horas
    return DEFAULT_PRAZO_H


class Command(BaseCommand):
    help = "Detecta breaches de SLA ANS e envia alerta por email para as operadoras"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Lista os alertas que seriam enviados sem enviar emails",
        )
        parser.add_argument(
            "--empresa-id",
            type=int,
            default=None,
            help="Processar apenas uma empresa específica (para testes)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        empresa_id = options.get("empresa_id")
        agora = timezone.now()

        empresas_qs = Empresa.objects.filter(
            pacote_codigo__in=["plano_saude_operadora", "plano_saude_enterprise"],
            ativo=True,
        )
        if empresa_id:
            empresas_qs = empresas_qs.filter(pk=empresa_id)

        total_emails = 0
        total_breaches = 0

        for empresa in empresas_qs:
            guias_pendentes = GuiaAutorizacao.objects.filter(
                plano__empresa=empresa,
                status__in=["solicitada", "em_analise"],
            ).select_related("beneficiario", "prestador")

            breaches = []
            for guia in guias_pendentes:
                prazo_h = _prazo_horas(guia.tipo)
                horas_abertas = (agora - guia.solicitada_em).total_seconds() / 3600
                if horas_abertas > prazo_h:
                    breaches.append({
                        "id": f"GUI-{guia.pk}",
                        "beneficiario": guia.beneficiario.nome if guia.beneficiario_id else "—",
                        "tipo": guia.tipo or "Guia",
                        "prazo": f"{prazo_h}h",
                        "aberto_ha": (
                            f"{int(horas_abertas)}h"
                            if horas_abertas < 48
                            else f"{int(horas_abertas / 24)}d"
                        ),
                        "prestador": (
                            guia.prestador.nome_fantasia
                            if guia.prestador_id
                            else "—"
                        ),
                    })

            if not breaches:
                continue

            total_breaches += len(breaches)

            if dry_run:
                self.stdout.write(
                    f"  [DRY] {empresa.nome}: {len(breaches)} breach(es) → {empresa.email}"
                )
                for b in breaches[:5]:
                    self.stdout.write(f"    • {b['id']} {b['beneficiario']} — {b['aberto_ha']}")
            else:
                enviar_email_sla_breach_critico(empresa, breaches)
                self.stdout.write(
                    f"  ✉  {empresa.nome}: {len(breaches)} breach(es) → {empresa.email}"
                )
                total_emails += 1

        prefixo = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefixo}sla_breach_alertas concluído — "
                f"{total_breaches} breach(es), {total_emails} email(s) enviado(s)"
            )
        )
