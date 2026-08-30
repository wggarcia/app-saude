"""
Aplica Row-Level Security (RLS) a TODAS as tabelas api_* multi-tenant que ainda
não têm a policy — fechando a cobertura que a migration 0085 deixou parcial.

Idempotente e seguro:
  • Só PostgreSQL (no-op em SQLite/dev).
  • Só colunas empresa_id NOT NULL (evita esconder linhas compartilhadas de
    tabelas com empresa_id anulável).
  • ENABLE (não FORCE) ROW LEVEL SECURITY — mantém o design da 0085: a conexão
    owner (login pré-tenant) faz bypass de propósito. FORCE quebraria o login.
  • --dry-run lista o que faria sem tocar no banco.

Rodar em produção só APÓS validar num Postgres de homologação (checar que
nenhuma tela legítima perde linhas e que o isolamento cross-tenant funciona).
"""
from django.core.management.base import BaseCommand
from django.db import connection


_POLICY_SQL = """
ALTER TABLE "{tabela}" ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON "{tabela}";
CREATE POLICY tenant_isolation ON "{tabela}"
AS PERMISSIVE FOR ALL TO PUBLIC
USING ("empresa_id" = NULLIF(current_setting('app.empresa_id', true), '')::bigint)
WITH CHECK ("empresa_id" = NULLIF(current_setting('app.empresa_id', true), '')::bigint);
"""


def _tabelas_alvo(cursor):
    cursor.execute("""
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_name = c.table_name AND t.table_schema = c.table_schema
        WHERE c.table_schema = 'public'
          AND c.column_name = 'empresa_id'
          AND c.is_nullable = 'NO'
          AND t.table_type = 'BASE TABLE'
          AND c.table_name LIKE 'api_%'
        ORDER BY c.table_name
    """)
    return [r[0] for r in cursor.fetchall()]


def _ja_tem_policy(cursor, tabela):
    cursor.execute(
        "SELECT 1 FROM pg_policies WHERE tablename = %s AND policyname = 'tenant_isolation'",
        [tabela],
    )
    return cursor.fetchone() is not None


class Command(BaseCommand):
    help = "Aplica a policy tenant_isolation (RLS) a todas as tabelas api_* com empresa_id NOT NULL."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Lista as tabelas que ganhariam/atualizariam a policy, sem aplicar.")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING(
                f"Banco é {connection.vendor} — RLS é específico de PostgreSQL. Nada a fazer."))
            return

        with connection.cursor() as cur:
            tabelas = _tabelas_alvo(cur)
            novas = [t for t in tabelas if not _ja_tem_policy(cur, t)]
            self.stdout.write(f"Tabelas api_* com empresa_id NOT NULL: {len(tabelas)}")
            self.stdout.write(f"Sem a policy tenant_isolation hoje: {len(novas)}")

            if opts["dry_run"]:
                for t in novas:
                    self.stdout.write(f"  [dry-run] aplicaria RLS em {t}")
                self.stdout.write(self.style.WARNING("Dry-run — nada foi alterado."))
                return

            aplicadas = 0
            for t in tabelas:  # reaplicar nas já cobertas é idempotente
                cur.execute(_POLICY_SQL.format(tabela=t))
                aplicadas += 1
            self.stdout.write(self.style.SUCCESS(
                f"RLS (re)aplicada em {aplicadas} tabelas — {len(novas)} eram novas."))
