"""
Gerenciamento de features liberadas para contas de demo/trial.

Uso:
  python manage.py liberar_features_demo --email demo.sst@solocrt.com --pacote empresa_profissional_25
  python manage.py liberar_features_demo --email demo.sst@solocrt.com  # usa empresa_nacional_1000
  python manage.py liberar_features_demo --todos-demos                   # alinha todos os demos
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.hashers import make_password


DEMOS_PADRAO = {
    "demo.sst@solocrt.com":          "empresa_nacional_1000",
    "demo.farmacia@solocrt.com":     "farmacia_rede_1000",
    "demo.hospital@solocrt.com":     "hospital_grande_1000",
    "demo.governo@solocrt.com":      "governo_estado",
    "demo.plano@solocrt.com":        "plano_saude_enterprise",
}


class Command(BaseCommand):
    help = "Alinha o pacote_codigo de contas demo para garantir que todas as features estejam liberadas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            help="E-mail da empresa demo a atualizar (ex: demo.sst@solocrt.com)",
        )
        parser.add_argument(
            "--pacote",
            type=str,
            default=None,
            help="Pacote a atribuir (default: usa o mapeamento padrão para o e-mail)",
        )
        parser.add_argument(
            "--todos-demos",
            action="store_true",
            default=False,
            help="Alinha todos os demos do mapeamento padrão",
        )

    def handle(self, *args, **options):
        from api.models import Empresa
        from api.planos import detalhes_pacote, PACOTES_SAAS

        def _alinhar(email, pacote_codigo):
            if pacote_codigo not in PACOTES_SAAS:
                raise CommandError(
                    f"Pacote '{pacote_codigo}' não existe. "
                    f"Pacotes disponíveis: {', '.join(PACOTES_SAAS.keys())}"
                )
            try:
                empresa = Empresa.objects.get(email=email)
            except Empresa.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"  ⚠  Conta não encontrada: {email} — pulando")
                )
                return

            det = detalhes_pacote(pacote_codigo)
            pacote_anterior = empresa.pacote_codigo
            features_novas = det.get("features", [])

            empresa.pacote_codigo = pacote_codigo
            empresa.max_dispositivos = det.get("dispositivos", empresa.max_dispositivos)
            empresa.max_usuarios = det.get("usuarios", empresa.max_usuarios)
            empresa.save(update_fields=["pacote_codigo", "max_dispositivos", "max_usuarios"])

            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✅  {email}\n"
                    f"      {pacote_anterior}  →  {pacote_codigo}\n"
                    f"      Features liberadas: {len(features_novas)}"
                )
            )
            if "sst.biometria" in features_novas:
                self.stdout.write(self.style.SUCCESS("      🔓  sst.biometria ✔"))

        self.stdout.write(self.style.HTTP_INFO("SoloCRT · Liberação de features demo"))
        self.stdout.write("─" * 52)

        if options["todos_demos"]:
            for email, pacote in DEMOS_PADRAO.items():
                _alinhar(email, pacote)
        elif options["email"]:
            email = options["email"]
            pacote = options["pacote"] or DEMOS_PADRAO.get(email)
            if not pacote:
                raise CommandError(
                    f"Nenhum pacote padrão para '{email}'. "
                    f"Use --pacote <codigo> para especificar."
                )
            _alinhar(email, pacote)
        else:
            raise CommandError(
                "Informe --email <email> ou --todos-demos.\n"
                f"Demos conhecidos: {', '.join(DEMOS_PADRAO.keys())}"
            )

        self.stdout.write("─" * 52)
        self.stdout.write(self.style.SUCCESS("Concluído."))
