-- ============================================================================
-- DIAGNÓSTICO DE RLS (Row Level Security) — SOMENTE LEITURA
-- ============================================================================
-- Este script NÃO altera nada. Ele apenas inspeciona o estado atual do banco
-- para decidirmos com segurança se/como ativar a RLS multi-tenant.
--
-- Como rodar no VPS:
--   cd /opt/soluscrt && set -a && . ./.env && set +a
--   psql "$DATABASE_URL" -f scripts/rls_diagnostico.sql
--
-- (Se o psql não aceitar a URL diretamente, use os parâmetros -h -U -d -p
--  correspondentes ao DATABASE_URL. NÃO imprima a senha no terminal.)
-- ============================================================================

\echo '=== [1] Qual papel a aplicação usa e ele é superuser/owner? ==='
SELECT current_user            AS papel_conectado,
       session_user,
       (SELECT rolsuper  FROM pg_roles WHERE rolname = current_user) AS eh_superuser,
       (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user) AS bypassa_rls;

\echo ''
\echo '=== [2] Todos os papéis existentes (procuramos soluscrt_app) ==='
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin
FROM pg_roles
ORDER BY rolname;

\echo ''
\echo '=== [3] Quem é o DONO das tabelas de tenant (amostra)? ==='
-- Se o dono == papel da app, a RLS é bypassada mesmo com ENABLE (sem FORCE).
SELECT tableowner, count(*) AS qtd_tabelas
FROM pg_tables
WHERE schemaname = 'public' AND tablename LIKE 'api_%'
GROUP BY tableowner
ORDER BY qtd_tabelas DESC;

\echo ''
\echo '=== [4] RLS está habilitada e/ou forçada nas tabelas de tenant? ==='
SELECT c.relname                         AS tabela,
       c.relrowsecurity                  AS rls_habilitada,
       c.relforcerowsecurity             AS rls_forcada
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND c.relname IN ('api_registrosintoma','api_funcionariosst','api_asoocupacional',
                    'api_planosaude','api_guiatiss','api_pacientehospital')
ORDER BY c.relname;

\echo ''
\echo '=== [5] A policy tenant_isolation existe? (amostra) ==='
SELECT tablename, policyname, cmd, roles
FROM pg_policies
WHERE schemaname = 'public'
  AND policyname = 'tenant_isolation'
  AND tablename IN ('api_registrosintoma','api_funcionariosst','api_planosaude')
ORDER BY tablename;

\echo ''
\echo '=== [6] O papel atual consegue LER as tabelas críticas? (grants) ==='
SELECT table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = current_user
  AND table_schema = 'public'
  AND table_name IN ('api_registrosintoma','api_empresa','api_funcionariosst')
ORDER BY table_name, privilege_type;

\echo ''
\echo '=== [7] Teste prático: o filtro RLS depende de app.empresa_id ==='
-- current_setting com o 2º arg true = não dá erro se a variável não existir.
SELECT current_setting('app.empresa_id', true) AS empresa_id_atual;
-- Contagem SEM setar empresa (simula um endpoint que esqueceu o middleware):
SELECT count(*) AS registros_visiveis_sem_empresa FROM api_registrosintoma;

\echo ''
\echo '=== FIM DO DIAGNÓSTICO (nada foi alterado) ==='
