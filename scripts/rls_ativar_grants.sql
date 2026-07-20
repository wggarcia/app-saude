-- ============================================================================
-- ATIVAÇÃO DA RLS — PASSO 1 de 3: GRANTS (100% seguro, apenas ADITIVO)
-- ============================================================================
-- Concede ao papel restrito `soluscrt` as permissões que ele precisa para
-- virar a conexão normal da aplicação (sujeita à RLS, pois NÃO é dono nem
-- superuser). Isto SOMENTE ADICIONA permissões — não remove nada e não pode
-- derrubar o app, que hoje roda como `soluscrt_app`.
--
-- IMPORTANTE: rode como o DONO das tabelas (`soluscrt_app`) ou como `postgres`,
-- pois só o dono/superuser pode conceder privilégios sobre as tabelas.
--
-- Exemplo (ajuste host/porta conforme seu .env; NÃO exponha senha no histórico):
--   psql "postgresql://postgres@localhost:5432/soluscrt_saude" -f scripts/rls_ativar_grants.sql
--   -- ou conectando como soluscrt_app (dono):
--   psql "postgresql://soluscrt_app@localhost:5432/soluscrt_saude" -f scripts/rls_ativar_grants.sql
-- ============================================================================

\echo '>>> Concedendo permissões ao papel restrito soluscrt...'

GRANT USAGE ON SCHEMA public TO soluscrt;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON ALL TABLES IN SCHEMA public TO soluscrt;

GRANT USAGE, SELECT, UPDATE
  ON ALL SEQUENCES IN SCHEMA public TO soluscrt;

-- Tabelas/sequences FUTURAS criadas pelo dono (migrations) já nascem acessíveis
-- ao papel restrito — evita "permission denied" após o próximo deploy.
ALTER DEFAULT PRIVILEGES FOR ROLE soluscrt_app IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO soluscrt;

ALTER DEFAULT PRIVILEGES FOR ROLE soluscrt_app IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO soluscrt;

\echo '>>> OK. Conferindo alguns grants concedidos:'
SELECT table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'soluscrt'
  AND table_schema = 'public'
  AND table_name IN ('api_registrosintoma','api_empresa','api_funcionariosst','api_planosaude')
ORDER BY table_name, privilege_type;

\echo '>>> Passo 1 concluído. Nada foi removido; o app continua rodando normalmente.'
