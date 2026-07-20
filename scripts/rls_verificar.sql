-- ============================================================================
-- ATIVAÇÃO DA RLS — VERIFICAÇÃO: prova isolamento E acesso (somente leitura)
-- ============================================================================
-- Rode COMO O PAPEL RESTRITO (o mesmo que a app usará = APP_DATABASE_URL após
-- a troca). Não altera dados — só faz SET de uma variável de sessão e conta.
--
--   psql "$APP_DATABASE_URL" -f scripts/rls_verificar.sql
--
-- O que esperamos:
--   [A] papel NÃO é superuser/bypassrls  -> RLS se aplica a ele
--   [B] sem empresa setada: 0 linhas     -> RLS bloqueia por padrão (seguro)
--   [C] com empresa X setada: só linhas de X visíveis (nunca de outra empresa)
--   [D] nenhum "permission denied"        -> grants OK (app acessível)
-- ============================================================================

\echo '=== [A] Papel atual sofre RLS? (esperado: superuser=f, bypassa=f) ==='
SELECT current_user,
       (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)    AS eh_superuser,
       (SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user) AS bypassa_rls;

\echo ''
\echo '=== [B] SEM empresa setada: deve ver 0 linhas (RLS bloqueia) ==='
SELECT set_config('app.empresa_id', '', false);
SELECT count(*) AS registrosintoma_sem_empresa FROM api_registrosintoma;
SELECT count(*) AS funcionariosst_sem_empresa  FROM api_funcionariosst;

\echo ''
\echo '=== Empresas disponíveis para o teste de isolamento ==='
-- api_empresa NÃO está sob RLS (é preciso resolver o tenant antes de saber quem é)
SELECT id, nome, tipo_conta
FROM api_empresa
ORDER BY id
LIMIT 10;

-- Captura duas empresas quaisquer para o teste A×B
SELECT id AS emp_a FROM api_empresa ORDER BY id LIMIT 1 \gset
SELECT id AS emp_b FROM api_empresa ORDER BY id DESC LIMIT 1 \gset

\echo ''
\echo '=== [C] Com empresa A setada: conta linhas visíveis (só de A) ==='
\echo 'empresa A ='
\echo :emp_a
SELECT set_config('app.empresa_id', :'emp_a', false);
SELECT :emp_a AS empresa_id,
       count(*) AS registros_visiveis,
       count(*) FILTER (WHERE empresa_id <> :emp_a) AS vazamento_de_outra_empresa
FROM api_registrosintoma;

\echo ''
\echo '=== [C] Com empresa B setada: conta linhas visíveis (só de B) ==='
\echo 'empresa B ='
\echo :emp_b
SELECT set_config('app.empresa_id', :'emp_b', false);
SELECT :emp_b AS empresa_id,
       count(*) AS registros_visiveis,
       count(*) FILTER (WHERE empresa_id <> :emp_b) AS vazamento_de_outra_empresa
FROM api_registrosintoma;

\echo ''
\echo '>>> Isolamento OK se "vazamento_de_outra_empresa" = 0 nas duas contagens,'
\echo '>>> e acesso OK se nenhuma consulta acima deu "permission denied".'
