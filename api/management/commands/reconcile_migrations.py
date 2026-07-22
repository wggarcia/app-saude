"""Reconcilia django_migrations quando o schema do banco está À FRENTE dos
registros de controle.

Cenário real em produção: o deploy bem-sucedido anterior aplicou as migrations
e criou todo o schema, mas os REGISTROS em django_migrations foram perdidos
(restore parcial dessa tabela, troca de banco, etc.). Nesse estado o
`migrate` normal falha com "column/relation ... already exists" ao tentar
recriar objetos que já existem.

Estratégia: aplicar as migrations pendentes UMA A UMA.
  - Se aplica limpo  -> migration genuinamente nova (roda de verdade).
  - Se falha porque o objeto já existe -> o schema já está no banco; marca
    a migration como aplicada (--fake) e segue.
  - Se falha por qualquer outro motivo -> propaga o erro (não mascara bugs).

Data migrations (RunPython) não disparam erro de "já existe"; portanto rodam
normalmente — backfills idempotentes continuam seguros.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.utils import IntegrityError, OperationalError, ProgrammingError

# Trechos que indicam "o objeto do schema já existe no banco" — Postgres.
_DUP_MARKERS = (
    "already exists",   # relation/column/index/constraint já existe
    "duplicate",        # duplicate_object / duplicate_column
)


class Command(BaseCommand):
    help = (
        "Aplica migrations pendentes uma a uma; marca como aplicada (--fake) "
        "qualquer migration cujo objeto de schema já exista no banco."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="default",
            help="Alias do banco (settings.DATABASES). Padrão: default.",
        )

    def handle(self, *args, **options):
        db_alias = options["database"]
        conn = connections[db_alias]

        executor = MigrationExecutor(conn)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)

        if not plan:
            self.stdout.write("[reconcile] Nenhuma migration pendente.")
            return

        self.stdout.write(
            f"[reconcile] {len(plan)} migration(s) pendente(s) — "
            "aplicando uma a uma com reconciliação de estado."
        )

        applied, faked = 0, 0
        for migration, _backwards in plan:
            app, name = migration.app_label, migration.name
            try:
                call_command(
                    "migrate", app, name,
                    database=db_alias, interactive=False, verbosity=1,
                )
                applied += 1
            except (ProgrammingError, OperationalError, IntegrityError) as exc:
                msg = str(exc).lower()
                # Transação abortada — reseta a conexão antes de continuar.
                conn.close()
                if any(marker in msg for marker in _DUP_MARKERS):
                    self.stdout.write(self.style.WARNING(
                        f"[reconcile] {app}.{name}: objeto já existe no banco "
                        f"— marcando como aplicada (--fake). Detalhe: {exc}"
                    ))
                    call_command(
                        "migrate", app, name,
                        database=db_alias, fake=True, interactive=False, verbosity=1,
                    )
                    faked += 1
                else:
                    self.stderr.write(self.style.ERROR(
                        f"[reconcile] {app}.{name}: erro não relacionado a "
                        "objeto duplicado — abortando sem mascarar."
                    ))
                    raise

        self.stdout.write(self.style.SUCCESS(
            f"[reconcile] Concluído: {applied} aplicada(s) de verdade, "
            f"{faked} reconciliada(s) via --fake."
        ))
