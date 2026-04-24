import json

from django.core.management.base import BaseCommand

from api.maintenance import maintenance_report


class Command(BaseCommand):
    help = "Monitora e executa manutencao segura do SolusCRT sem tocar em dados operacionais sensiveis."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply-safe-cleanup",
            action="store_true",
            help="Aplica apenas limpezas seguras: sessoes expiradas, dispositivos ociosos, tokens push antigos e cache.",
        )
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            help="Limpa o cache Django junto com a manutencao segura.",
        )
        parser.add_argument(
            "--push-stale-days",
            type=int,
            default=45,
            help="Dias sem atualizacao para considerar token push como antigo.",
        )
        parser.add_argument(
            "--revoked-alert-threshold-days",
            type=int,
            default=14,
            help="Dias para destacar alertas revogados antigos no relatorio.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Formato da saida.",
        )

    def handle(self, *args, **options):
        report = maintenance_report(
            apply=options["apply_safe_cleanup"],
            clear_cache=options["clear_cache"],
            revoked_alert_threshold_days=options["revoked_alert_threshold_days"],
            push_stale_days=options["push_stale_days"],
        )

        if options["format"] == "json":
            self.stdout.write(json.dumps(report, ensure_ascii=True, indent=2))
            return

        before = report["before"]
        self.stdout.write(self.style.MIGRATE_HEADING("SolusCRT Maintenance Report"))
        self.stdout.write(f"Modo: {report['mode']}")
        self.stdout.write(
            "Sessao ociosa limite: "
            f"{before['thresholds']['session_idle_hours']}h | "
            f"Push antigo: {before['thresholds']['push_stale_days']}d | "
            f"Alerta revogado antigo: {before['thresholds']['revoked_alert_days']}d"
        )
        self.stdout.write("")
        self.stdout.write(
            f"Dispositivos ativos: {before['devices']['active_total']} | "
            f"ativos ociosos: {before['devices']['stale_active']} | "
            f"inativos: {before['devices']['inactive_total']}"
        )
        self.stdout.write(
            f"Sessoes expiradas: empresa {before['sessions']['empresa_stale']} | "
            f"usuarios {before['sessions']['usuario_stale']} | "
            f"operacao {before['sessions']['owner_stale']}"
        )
        self.stdout.write(
            f"Push ativos: {before['push']['active_total']} | "
            f"push antigos: {before['push']['stale_active']} | "
            f"push inativos: {before['push']['inactive_total']}"
        )
        self.stdout.write(
            f"Alertas publicados: {before['alerts']['published_total']} | "
            f"revogados: {before['alerts']['revoked_total']} | "
            f"revogados antigos: {before['alerts']['revoked_old']}"
        )

        if report["cleanup"]:
            cleanup = report["cleanup"]
            after = report["after"]
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Limpeza segura aplicada"))
            self.stdout.write(
                f"Dispositivos desativados: {cleanup['devices_deactivated']} | "
                f"sessoes empresa encerradas: {cleanup['empresa_sessions_closed']} | "
                f"sessoes usuario encerradas: {cleanup['user_sessions_closed']} | "
                f"sessoes operacao encerradas: {cleanup['owner_sessions_closed']} | "
                f"push desativados: {cleanup['push_tokens_deactivated']} | "
                f"cache limpo: {'sim' if cleanup['cache_cleared'] else 'nao'}"
            )
            self.stdout.write(
                f"Pos-limpeza -> dispositivos ativos: {after['devices']['active_total']} | "
                f"sessoes expiradas restantes: "
                f"{after['sessions']['empresa_stale'] + after['sessions']['usuario_stale'] + after['sessions']['owner_stale']} | "
                f"push antigos restantes: {after['push']['stale_active']}"
            )
        else:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Nenhuma alteracao aplicada. Use --apply-safe-cleanup para executar a limpeza segura."))
