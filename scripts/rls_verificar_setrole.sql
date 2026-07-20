-- ============================================================================
-- VERIFICAÇÃO DA RLS via SET ROLE — não usa senha (rodar como postgres)
-- ============================================================================
-- Conecta como superuser (peer auth, sem senha) e usa SET ROLE para assumir o
-- papel restrito `soluscrt` — que NÃO é dono das tabelas nem superuser, então a
-- RLS passa a valer para a sessão. Assim provamos o isolamento sem manipular
-- nenhuma credencial no shell.
--
--   sudo -u postgres psql -d soluscrt_saude < scripts/rls_verificar_setrole.sql
--
-- Esperado:
--   [B] sem empresa setada: 0 linhas               (RLS bloqueia por padrão)
--   [C] com empresa X: vazamento_de_outra_empresa=0 (só vê o próprio tenant)
--   Nenhum "permission denied"                      (grants OK)
-- ============================================================================

SET ROLE soluscrt;

\echo '=== [A] Papel efetivo e se sofre RLS (esperado: soluscrt, super=f, bypass=f) ==='
SELECT current_user,
       (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)     AS eh_superuser,
       (SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user) AS bypassa_rls;

\echo ''
\echo '=== [B] SEM empresa setada: deve ver 0 linhas ==='
SELECT set_config('app.empresa_id', '', false);
SELECT count(*) AS registrosintoma_sem_empresa FROM api_registrosintoma;

\echo ''
\echo '=== Empresas para o teste de isolamento (api_empresa nao esta sob RLS) ==='
SELECT id, nome FROM api_empresa ORDER BY id LIMIT 10;

SELECT id AS emp_a FROM api_empresa ORDER BY id LIMIT 1 \gset
SELECT id AS emp_b FROM api_empresa ORDER BY id DESC LIMIT 1 \gset

\echo ''
\echo '=== [C] Empresa A: registros visiveis (vazamento deve ser 0) ==='
\echo 'empresa A ='
\echo :emp_a
SELECT set_config('app.empresa_id', :'emp_a', false);
SELECT :emp_a AS empresa_id,
       count(*) AS registros_visiveis,
       count(*) FILTER (WHERE empresa_id <> :emp_a) AS vazamento_de_outra_empresa
FROM api_registrosintoma;

\echo ''
\echo '=== [C] Empresa B: registros visiveis (vazamento deve ser 0) ==='
\echo 'empresa B ='
\echo :emp_b
SELECT set_config('app.empresa_id', :'emp_b', false);
SELECT :emp_b AS empresa_id,
       count(*) AS registros_visiveis,
       count(*) FILTER (WHERE empresa_id <> :emp_b) AS vazamento_de_outra_empresa
FROM api_registrosintoma;

RESET ROLE;
\echo ''
\echo '>>> OK se vazamento_de_outra_empresa = 0 nas duas contagens e sem permission denied.'
