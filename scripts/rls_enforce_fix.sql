-- ═══════════════════════════════════════════════════════════════════════════
-- RLS ENFORCE FIX — faz a RLS realmente enforçar para o papel do app
-- ═══════════════════════════════════════════════════════════════════════════
--
-- DIAGNÓSTICO (31/08/2026, confirmado ao vivo no VPS):
--   A RLS está ENABLE + com policy tenant_isolation em ~301 tabelas, MAS está
--   INERTE para o papel do app (soluscrt). Prova empírica: conectado como
--   soluscrt, `SELECT count(*) FROM api_funcionariosst` retorna TODAS as 14
--   linhas com qualquer app.empresa_id ('42'→14, '999'→14, ''→14) — deveria
--   ser 12, 0, 0. O isolamento real hoje vem 100% do `.filter(empresa=)` do
--   Django (camada de app), NÃO da RLS.
--
--   CAUSA (dois mecanismos de bypass de dono):
--   (a) soluscrt é MEMBRO de soluscrt_app (com INHERIT). soluscrt_app é dono de
--       ~352 tabelas. O PostgreSQL pula a RLS quando o papel atual tem os
--       privilégios do DONO (has_privs_of_role) → soluscrt herda o bypass.
--   (b) soluscrt é DONO DIRETO de 43 tabelas com empresa_id → dono bypassa RLS.
--
-- FIX (fecha os dois):
--   (a) REVOKE soluscrt_app FROM soluscrt   → para de herdar o bypass nas 352.
--   (b) ALTER ... OWNER TO soluscrt_app     → nas 43, soluscrt deixa de ser dono.
--   Depois disso soluscrt não é dono nem herda dono em NENHUMA → RLS enforça.
--   Acesso é preservado: soluscrt já tem grant EXPLÍCITO SELECT/INSERT/UPDATE/
--   DELETE nas 405 tabelas + USAGE em 413 sequences (verificado). A conexão
--   "owner" (soluscrt_app, usada no login/pré-tenant) segue bypassando (é dona).
--
-- COMO RODAR (precisa superuser postgres):
--   sudo -u postgres psql -d soluscrt_saude -f /opt/soluscrt/scripts/rls_enforce_fix.sql
--
-- ⚠️  ANTES:
--   1. BACKUP: sudo -u postgres pg_dump soluscrt_saude | gzip > /root/pre_rls_$(date +%F).sql.gz
--   2. Ideal: validar em HOMOLOGAÇÃO. RISCO: caminhos que usam a conexão
--      DEFAULT (soluscrt) SEM setar app.empresa_id passam a ver 0 linhas.
--      Suspeitos a testar: endpoints públicos (/api/public/*), o registrar de
--      sintomas do app da população, e cron jobs (notícias, agente comercial).
--      O login usa a conexão "owner" (soluscrt_app) e não é afetado.
--   3. Momento ideal: SEM clientes reais → blast radius = demos + coleta de dados.
--
-- ── VALIDAÇÃO PÓS-EXECUÇÃO (rodar TODAS) ────────────────────────────────────
--   A) RLS enforça? (deve dar 12, 0, 0)
--      sudo -u postgres psql -d soluscrt_saude -c "SET ROLE soluscrt;
--        SET app.empresa_id='42'; SELECT count(*) FROM api_funcionariosst;
--        SET app.empresa_id='999'; SELECT count(*) FROM api_funcionariosst;
--        SET app.empresa_id=''; SELECT count(*) FROM api_funcionariosst; RESET ROLE;"
--   B) systemctl restart soluscrt.service   (dropa conexões do pool)
--   C) curl -s -o /dev/null -w '%{http_code}\n' https://empresa.solocrt.com.br/readyz   → 200
--   D) Login normal + login-governo funcionam (usa owner). Dashboards mostram dados.
--   E) App da população: enviar sintoma (/api/public/registrar) — DEVE gravar.
--      Mapa /api/epidemiologia — DEVE responder (usa .using("owner")).
--   F) Logs sem erro de "permission denied" nem páginas vazias:
--      journalctl -u soluscrt.service -n 100 --no-pager | grep -i 'denied\|rls\|empresa_id'
--
-- ── ROLLBACK (se QUALQUER item acima falhar) ────────────────────────────────
--   sudo -u postgres psql -d soluscrt_saude -c "GRANT soluscrt_app TO soluscrt;"
--   -- (opcional) reverter donos das 43 de volta p/ soluscrt — ver rls_ownership_fix.sql rollback
--   systemctl restart soluscrt.service
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- (a) parar de herdar o bypass de dono nas ~352 tabelas do soluscrt_app
REVOKE soluscrt_app FROM soluscrt;

-- (b) transferir as 43 tabelas que soluscrt possui direto (senão continua dono→bypass)
ALTER TABLE public.api_assinaturaetapaproducao      OWNER TO soluscrt_app;
ALTER TABLE public.api_auditoriaclinica             OWNER TO soluscrt_app;
ALTER TABLE public.api_avaliacaonps                 OWNER TO soluscrt_app;
ALTER TABLE public.api_buscaativasocial             OWNER TO soluscrt_app;
ALTER TABLE public.api_campanhacomunicacaoplano     OWNER TO soluscrt_app;
ALTER TABLE public.api_casoeticomedico              OWNER TO soluscrt_app;
ALTER TABLE public.api_chegadaps                    OWNER TO soluscrt_app;
ALTER TABLE public.api_clientefidelidade            OWNER TO soluscrt_app;
ALTER TABLE public.api_conselheirosaude             OWNER TO soluscrt_app;
ALTER TABLE public.api_deliberacaoconselhosaude     OWNER TO soluscrt_app;
ALTER TABLE public.api_desvioproducao               OWNER TO soluscrt_app;
ALTER TABLE public.api_encaminhamentoconselhotutelar OWNER TO soluscrt_app;
ALTER TABLE public.api_escalaprofissionalrede       OWNER TO soluscrt_app;
ALTER TABLE public.api_especificacaoproducao        OWNER TO soluscrt_app;
ALTER TABLE public.api_fornecedorhospital           OWNER TO soluscrt_app;
ALTER TABLE public.api_guiaintercambio              OWNER TO soluscrt_app;
ALTER TABLE public.api_guiaoncologica               OWNER TO soluscrt_app;
ALTER TABLE public.api_identidadepaciente           OWNER TO soluscrt_app;
ALTER TABLE public.api_importacaodados              OWNER TO soluscrt_app;
ALTER TABLE public.api_inconsistenciacadastral      OWNER TO soluscrt_app;
ALTER TABLE public.api_itempedidodelivery           OWNER TO soluscrt_app;
ALTER TABLE public.api_juntamedicaopme              OWNER TO soluscrt_app;
ALTER TABLE public.api_logmensagemwhatsapp          OWNER TO soluscrt_app;
ALTER TABLE public.api_manifestacaoouvidoria        OWNER TO soluscrt_app;
ALTER TABLE public.api_membrocomissaoetica          OWNER TO soluscrt_app;
ALTER TABLE public.api_modeloiaarea                 OWNER TO soluscrt_app;
ALTER TABLE public.api_opmeprocedimento             OWNER TO soluscrt_app;
ALTER TABLE public.api_ordemproducaoindustrial      OWNER TO soluscrt_app;
ALTER TABLE public.api_pedidoexamevita              OWNER TO soluscrt_app;
ALTER TABLE public.api_portalfacialoperadora        OWNER TO soluscrt_app;
ALTER TABLE public.api_prontuariosocialpaif         OWNER TO soluscrt_app;
ALTER TABLE public.api_redeapoiosst                 OWNER TO soluscrt_app;
ALTER TABLE public.api_registrocampoproducao        OWNER TO soluscrt_app;
ALTER TABLE public.api_registroobitomunicipal       OWNER TO soluscrt_app;
ALTER TABLE public.api_ressarcimentosus             OWNER TO soluscrt_app;
ALTER TABLE public.api_reuniaoconselhosaude         OWNER TO soluscrt_app;
ALTER TABLE public.api_solicitacaovidarh            OWNER TO soluscrt_app;
ALTER TABLE public.api_territoriovigilanciasocial   OWNER TO soluscrt_app;
ALTER TABLE public.api_totemcheckinlog              OWNER TO soluscrt_app;
ALTER TABLE public.api_totemdispositivo             OWNER TO soluscrt_app;
ALTER TABLE public.api_transacaofidelidade          OWNER TO soluscrt_app;
ALTER TABLE public.api_triagemmanchesterps          OWNER TO soluscrt_app;
ALTER TABLE public.api_twofactortotp                OWNER TO soluscrt_app;

-- garante grants (idempotente; já existem, mas belt-and-suspenders após troca de dono)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO soluscrt;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO soluscrt;

COMMIT;
