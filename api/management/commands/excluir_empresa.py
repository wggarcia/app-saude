"""
Exclui uma conta Empresa e todos os seus dados vinculados.

Uso:
    python manage.py excluir_empresa --email=populacao@soluscrt.com
    python manage.py excluir_empresa --id=33

Deleta objetos que fazem PROTECT sobre dados da empresa (cascata manual)
antes de chamar empresa.delete(), contornando o ProtectedError do Django ORM.
"""
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, IntegrityError
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

        # RLS do PostgreSQL filtra queries pelo empresa_id da sessão.
        # Sem setar o contexto, o cascade do Django não enxerga os registros
        # filhos e o banco rejeita o DELETE com ForeignKeyViolation.
        from api.middleware import _rls_set_empresa
        _rls_set_empresa(empresa.id)

        # Tenta até 20 vezes. A cada falha:
        # - ProtectedError (Django ORM): deleta os objetos bloqueadores via ORM
        # - IntegrityError  (FK violation no BD): deleta a tabela bloqueadora via SQL direto
        #   (acontece quando RLS impede o cascade do Django de enxergar os registros)
        for tentativa in range(1, 21):
            empresa = type(empresa).objects.filter(id=empresa.id).first()
            if not empresa:
                self.stdout.write(self.style.SUCCESS("\nConta excluída com sucesso."))
                return
            try:
                empresa.delete()
                self.stdout.write(self.style.SUCCESS(f"\nConta '{empresa.nome}' ({empresa.email}) excluída na tentativa {tentativa}."))
                return
            except ProtectedError as e:
                bloqueadores = list(e.protected_objects)
                self.stdout.write(f"  [{tentativa}] ProtectedError: {len(bloqueadores)} objeto(s) — removendo via ORM...")
                for obj in bloqueadores:
                    try:
                        obj.delete()
                        self.stdout.write(f"    ORM: {obj.__class__.__name__}(id={obj.pk})")
                    except Exception as ex:
                        self.stdout.write(self.style.WARNING(f"    Falha ORM: {obj.__class__.__name__}(id={obj.pk}): {ex}"))
            except IntegrityError as e:
                cause = str(getattr(e, '__cause__', e) or e)
                m = re.search(r'referenced from table "(\w+)"', cause)
                if m:
                    tbl = m.group(1)
                    self.stdout.write(f"  [{tentativa}] IntegrityError (RLS bloqueou cascade) — deletando {tbl} via SQL...")
                    with connection.cursor() as cur:
                        cur.execute(f"DELETE FROM {tbl} WHERE empresa_id = %s", [empresa.id])
                        self.stdout.write(f"    SQL: {cur.rowcount} linhas de {tbl} deletadas")
                else:
                    raise CommandError(f"IntegrityError sem tabela identificada: {cause}")

        raise CommandError("Não foi possível excluir após 20 tentativas.")
