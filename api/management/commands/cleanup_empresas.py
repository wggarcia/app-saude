"""
Limpa o banco de dados removendo todas as Empresas que NÃO são contas demo.

Uso seguro (só lista o que seria deletado):
    python manage.py cleanup_empresas

Execução real (deleta de verdade):
    python manage.py cleanup_empresas --confirmar
"""
from django.core.management.base import BaseCommand
from api.models import Empresa

DEMO_EMAILS = {
    "demo.sst@soluscrt.com",
    "demo.farmacia@soluscrt.com",
    "demo.hospital@soluscrt.com",
    "demo.governo@soluscrt.com",
    "demo.plano@soluscrt.com",
}


class Command(BaseCommand):
    help = "Remove todas as Empresas que não são contas demo (mantém as 5 demos)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmar",
            action="store_true",
            default=False,
            help="Executa a deleção de verdade. Sem esta flag, apenas lista o que seria removido.",
        )

    def handle(self, *args, **options):
        confirmar = options["confirmar"]

        para_deletar = Empresa.objects.exclude(email__in=DEMO_EMAILS)
        total = para_deletar.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("✅ Nenhuma empresa para remover. Banco já está limpo."))
            return

        self.stdout.write(f"\n{'[SIMULAÇÃO]' if not confirmar else '[EXECUÇÃO]'} {total} empresa(s) serão removidas:\n")
        for emp in para_deletar.order_by("email"):
            status = "✅ ativo" if emp.ativo else "❌ inativo"
            self.stdout.write(f"  • {emp.email} — {emp.nome or '(sem nome)'} [{emp.pacote_codigo}] {status}")

        demos_restantes = Empresa.objects.filter(email__in=DEMO_EMAILS)
        self.stdout.write(f"\n📌 Contas demo que serão mantidas ({demos_restantes.count()}):")
        for emp in demos_restantes.order_by("email"):
            self.stdout.write(f"  ✓ {emp.email} — {emp.nome or '(sem nome)'}")

        if not confirmar:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠️  Simulação apenas. Para deletar de verdade, rode:\n"
                    "   python manage.py cleanup_empresas --confirmar\n"
                )
            )
            return

        self.stdout.write(self.style.WARNING(f"\n🗑️  Deletando {total} empresa(s)..."))
        deletados, detalhes = para_deletar.delete()
        self.stdout.write(self.style.SUCCESS(
            f"✅ Removidos: {deletados} registros no total.\n"
            + "\n".join(f"   {k}: {v}" for k, v in detalhes.items())
        ))
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Console operacional agora mostra apenas as {demos_restantes.count()} contas demo.\n"
        ))
