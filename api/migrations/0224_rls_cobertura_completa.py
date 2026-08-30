"""
Fecha a cobertura de Row-Level Security (RLS).

A migration 0085 habilitou RLS + policy `tenant_isolation` em ~165 tabelas.
Desde então ~148 tabelas multi-tenant novas (com coluna `empresa_id`) ficaram
SEM RLS no banco — protegidas só pelo filtro na camada de aplicação. Esta
migration estende a MESMA policy da 0085 a toda tabela `api_*` que tenha uma
coluna `empresa_id` NOT NULL e ainda não tenha a policy.

Descoberta em runtime (information_schema) em vez de lista fixa: evita erro de
transcrição e é idempotente — reaplicar não quebra nada (DROP POLICY IF EXISTS).

Critérios de segurança:
  • Só PostgreSQL (no-op em SQLite/dev).
  • Só colunas `empresa_id` NOT NULL — tabelas com empresa_id anulável podem
    ter linhas compartilhadas (empresa_id NULL) que a policy tornaria invisíveis;
    essas ficam de fora e são tratadas caso a caso.
  • ENABLE (não FORCE) ROW LEVEL SECURITY — mantém o design da 0085 em que a
    conexão `owner` (usada no login pré-tenant) faz bypass de propósito. Forçar
    RLS quebraria o login. O isolamento real vem do papel restrito no
    APP_DATABASE_URL, como já documentado na 0085.
"""
from django.db import migrations


_POLICY_SQL = """
ALTER TABLE "{tabela}" ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON "{tabela}";
CREATE POLICY tenant_isolation ON "{tabela}"
AS PERMISSIVE FOR ALL TO PUBLIC
USING ("empresa_id" = NULLIF(current_setting('app.empresa_id', true), '')::bigint)
WITH CHECK ("empresa_id" = NULLIF(current_setting('app.empresa_id', true), '')::bigint);
"""

_DISABLE_SQL = """
DROP POLICY IF EXISTS tenant_isolation ON "{tabela}";
ALTER TABLE "{tabela}" DISABLE ROW LEVEL SECURITY;
"""

# Tabelas que a 0085 já cobriu — não mexer no reverse (deixar como a 0085 deixou).
# No forward, reaplicar nelas é idempotente e inofensivo.


def _tabelas_alvo(cursor):
    """Tabelas api_* com coluna empresa_id NOT NULL."""
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


def _aplicar(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return  # SQLite/dev: no-op
    with conn.cursor() as cur:
        tabelas = _tabelas_alvo(cur)
        for tabela in tabelas:
            cur.execute(_POLICY_SQL.format(tabela=tabela))


def _reverter(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return
    # Reverte apenas as tabelas que ganharam RLS AQUI não é distinguível de forma
    # barata das da 0085; por segurança, o reverse não desabilita RLS em massa
    # (evita reabrir isolamento por engano). Reversão manual, se necessária.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0223_cifra_certificados_pfx'),
    ]

    operations = [
        migrations.RunPython(_aplicar, _reverter),
    ]
