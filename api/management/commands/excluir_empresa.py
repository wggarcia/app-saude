"""
Exclui uma conta Empresa e todos os seus dados vinculados.

Uso:
    python manage.py excluir_empresa --email=populacao@soluscrt.com
    python manage.py excluir_empresa --id=33

Deleta objetos que fazem PROTECT sobre dados da empresa (cascata manual)
antes de chamar empresa.delete(), contornando o ProtectedError do Django ORM.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import ProtectedError


class Command(BaseCommand):
    help = "Exclui permanentemente uma conta Empresa e todos os seus dados."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--email", type=str, help="Email da empresa a excluir")
        group.add_argument("--id", type=int, help="ID da empresa a excluir")
        parser.add_argument("--confirmar", action="store_true", help="Confirma a exclusão sem prompt interativo")

    def handle(self, *args, **options):
        from api.models import Empresa

        email = options.get("email")
        empresa_id = options.get("id")

        if email:
            empresa = Empresa.objects.filter(email__iexact=email.strip()).first()
        else:
            empresa = Empresa.objects.filter(id=empresa_id).first()

        if not empresa:
            raise CommandError("Empresa não encontrada.")

        self.stdout.write(f"\nEmpresa encontrada:")
        self.stdout.write(f"  ID:    {empresa.id}")
        self.stdout.write(f"  Nome:  {empresa.nome}")
        self.stdout.write(f"  Email: {empresa.email}")
        self.stdout.write(f"  Setor: {empresa.pacote_codigo}")
        self.stdout.write(f"  Ativo: {empresa.ativo}\n")

        if not options["confirmar"]:
            resposta = input("Confirma a exclusão permanente? Digite 'sim' para continuar: ")
            if resposta.strip().lower() != "sim":
                self.stdout.write("Operação cancelada.")
                return

        self.stdout.write("Iniciando exclusão...")

        # Tenta empresa.delete() até 5 vezes, removendo a cada rodada os objetos
        # que fazem PROTECT sobre tabelas vinculadas à empresa.
        for tentativa in range(1, 6):
            try:
                empresa.delete()
                self.stdout.write(self.style.SUCCESS(f"\nConta '{empresa.nome}' ({empresa.email}) excluída com sucesso na tentativa {tentativa}."))
                return
            except ProtectedError as e:
                bloqueadores = list(e.protected_objects)
                self.stdout.write(f"  Tentativa {tentativa}: {len(bloqueadores)} objeto(s) bloqueando — removendo...")
                for obj in bloqueadores:
                    try:
                        obj.delete()
                        self.stdout.write(f"    Deletado: {obj.__class__.__name__}(id={obj.pk})")
                    except Exception as ex:
                        self.stdout.write(self.style.WARNING(f"    Falha ao deletar {obj.__class__.__name__}(id={obj.pk}): {ex}"))

        raise CommandError("Não foi possível excluir após 5 tentativas — verifique os dados vinculados manualmente.")
