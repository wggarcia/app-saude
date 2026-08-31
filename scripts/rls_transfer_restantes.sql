-- ═══════════════════════════════════════════════════════════════════════════
-- Transferir as 10 tabelas restantes do papel `soluscrt` para `soluscrt_app`
-- ═══════════════════════════════════════════════════════════════════════════
--
-- CONTEXTO: depois do rls_enforce_fix.sql, sobraram 10 tabelas api_* ainda
-- pertencentes ao papel `soluscrt`. NENHUMA tem empresa_id (são referência/
-- filhas: terminologia TUSS, registro ANVISA, prospecção, itens OPME/totem),
-- então RLS não se aplica a elas — transferir é NEUTRO para segurança.
--
-- POR QUE FAZER: robustez de migração. Migrações rodam como `soluscrt_app`
-- (via APP_DATABASE_URL= vazio, ver hostinger_deploy.sh). Se uma migração
-- futura tocar UMA destas 10 (dono soluscrt) junto com tabelas do soluscrt_app,
-- ela falha com "must be owner". Transferindo tudo pro soluscrt_app, migrações
-- sempre funcionam. (Foi exatamente o que causou a falha da migr 0231 em 31/08.)
--
-- É SEGURO e OPCIONAL. `soluscrt` mantém grant DML explícito (405/405) e USAGE
-- nas sequences — não perde acesso. Rodar como superuser postgres.
--
--   sudo -u postgres psql -d soluscrt_saude -f /opt/soluscrt/scripts/rls_transfer_restantes.sql
--
-- Depois: nada a validar de segurança (sem empresa_id). Confirme só que o app
-- segue 200 (readyz) e que uma migração de teste roda.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE public.api_biometriatotempaciente     OWNER TO soluscrt_app;
ALTER TABLE public.api_conveniopacientetotem       OWNER TO soluscrt_app;
ALTER TABLE public.api_emailprospeccao             OWNER TO soluscrt_app;
ALTER TABLE public.api_empresaafeanvisa            OWNER TO soluscrt_app;
ALTER TABLE public.api_etapahistoricoopme          OWNER TO soluscrt_app;
ALTER TABLE public.api_leadprospeccao              OWNER TO soluscrt_app;
ALTER TABLE public.api_opmeprocedimentoitem        OWNER TO soluscrt_app;
ALTER TABLE public.api_portalrhtoken               OWNER TO soluscrt_app;
ALTER TABLE public.api_registroanvisaprodutosaude  OWNER TO soluscrt_app;
ALTER TABLE public.api_terminologiatuss            OWNER TO soluscrt_app;

-- garante acesso do papel do app (idempotente)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO soluscrt;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO soluscrt;

COMMIT;

-- Verificação (deve retornar 0):
--   SELECT count(*) FROM pg_tables WHERE schemaname='public'
--     AND tablename LIKE 'api_%' AND tableowner='soluscrt';
