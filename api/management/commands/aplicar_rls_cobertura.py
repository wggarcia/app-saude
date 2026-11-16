"""
Aplica Row-Level Security (RLS) a TODAS as tabelas api_* multi-tenant e mantém
a policy tenant_isolation igual em todas elas. Roda em todo deploy.

Idempotente e seguro:
  • Só PostgreSQL (no-op em SQLite/dev).
  • Alvo: toda tabela api_* com empresa_id NOT NULL, mais as tabelas de
    empresa_id anulável listadas em TABELAS_ANULAVEIS_ISOLADAS (decisão caso a
    caso — ver abaixo). Linha com empresa_id NULL nessas tabelas só é vista e
    gravada pelo console do dono ou pela conexão owner.
  • ENABLE (não FORCE) ROW LEVEL SECURITY — a conexão owner (login pré-tenant,
    crons) faz bypass de propósito. FORCE quebraria o login.
  • A policy aceita app.rls_bypass = 'dono', ligado só pelo EmpresaMiddleware
    depois de validar o owner_token do console operacional.
  • --dry-run lista o que faria sem tocar no banco.
"""
from django.core.management.base import BaseCommand
from django.db import connection

# empresa_id anulável, mas o dado é do cliente: isolar igual às demais.
TABELAS_ANULAVEIS_ISOLADAS = (
    "api_auditoriainstitucional",  # NULL = evento de plataforma; não pode vazar a clientes
    "api_donoauditoriaacao",       # trilha do console do dono
    "api_passwordresettoken",      # todo token nasce com empresa (inclusive de sub-usuário)
    "api_planosaude",              # dado de negócio da operadora
    "api_outboxevento",
    "api_schemacontrato",
    "api_modeloml",
)
# api_dispositivopushpublico fica SEM RLS de propósito: aparelhos anônimos do app
# do cidadão, sem cliente dono (empresa só inferida por geolocalização).

_TENANT = "NULLIF(current_setting('app.empresa_id', true), '')::bigint"
_REGRA = f"(\"empresa_id\" = {_TENANT} OR current_setting('app.rls_bypass', true) = 'dono')"

_POLICY_SQL = f"""
ALTER TABLE "{{tabela}}" ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON "{{tabela}}";
CREATE POLICY tenant_isolation ON "{{tabela}}"
AS PERMISSIVE FOR ALL TO PUBLIC
USING {_REGRA}
WITH CHECK {_REGRA};
"""


def _tabelas_alvo(cursor):
    cursor.execute("""
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_name = c.table_name AND t.table_schema = c.table_schema
        WHERE c.table_schema = 'public'
          AND c.column_name = 'empresa_id'
          AND t.table_type = 'BASE TABLE'
          AND c.table_name LIKE 'api_%%'
          AND (c.is_nullable = 'NO' OR c.table_name = ANY(%s))
        ORDER BY c.table_name
    """, [list(TABELAS_ANULAVEIS_ISOLADAS)])
    return [r[0] for r in cursor.fetchall()]


def _ja_tem_policy(cursor, tabela):
    cursor.execute(
        "SELECT 1 FROM pg_policies WHERE tablename = %s AND policyname = 'tenant_isolation'",
        [tabela],
    )
    return cursor.fetchone() is not None


class Command(BaseCommand):
    help = "Aplica a policy tenant_isolation (RLS) às tabelas api_* multi-tenant."

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
            self.stdout.write(f"Tabelas api_* multi-tenant: {len(tabelas)}")
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
