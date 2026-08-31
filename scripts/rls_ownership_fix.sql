-- ═══════════════════════════════════════════════════════════════════════════
-- RLS OWNERSHIP FIX — fecha o último gap sistêmico de isolamento por tenant
-- ═══════════════════════════════════════════════════════════════════════════
--
-- PROBLEMA:
--   O papel do app (soluscrt) é DONO de 43 tabelas que têm empresa_id. No
--   PostgreSQL, o dono da tabela CONTORNA a RLS por padrão (a menos que FORCE
--   esteja ligado). Ou seja: nessas 43 tabelas a policy tenant_isolation existe
--   e o RLS está ENABLE, mas NÃO é enforçado para o app — se algum caminho de
--   código esquecer o filtro .filter(empresa=...), há risco de vazamento
--   cross-tenant. Inclui tabelas ULTRASSENSÍVEIS de todos os segmentos.
--
--   Nas outras ~352 tabelas o dono é soluscrt_app (≠ papel do app), então a RLS
--   JÁ é enforçada e o site funciona — prova de que os caminhos autenticados
--   setam app.empresa_id corretamente.
--
-- FIX (este script): transferir a propriedade das 43 para soluscrt_app. Depois
--   disso o papel do app (soluscrt) deixa de ser dono e a RLS passa a enforçar.
--
-- COMO RODAR (exige SUPERUSER — nem soluscrt nem soluscrt_app são superuser):
--   sudo -u postgres psql -d <DB> -f scripts/rls_ownership_fix.sql
--
-- ⚠️  ANTES DE RODAR EM PROD:
--   1. BACKUP (scripts/backup_postgres.sh).
--   2. Idealmente validar em HOMOLOGAÇÃO primeiro. Risco: se algum caminho
--      NÃO-autenticado (login/2FA, kiosk/totem, job de fundo, endpoint público)
--      tocar uma dessas tabelas SEM app.empresa_id setado, a RLS vai ESCONDER
--      as linhas (retorna vazio). Tabelas de auth incluídas aqui e que merecem
--      atenção redobrada: api_twofactortotp, api_totemdispositivo,
--      api_totemcheckinlog, api_portalfacialoperadora.
--   3. Logo após, VALIDAR: site 200, /readyz ok, login normal, login 2FA,
--      check-in de totem, e os dados demo aparecendo. Logs sem erro.
--   4. ROLLBACK (se algo sumir): reverter o dono para soluscrt (ver fim do
--      arquivo) e investigar o caminho que não seta app.empresa_id.
--
-- Momento ideal: SEM clientes reais ainda → blast radius = contas demo. É a
-- melhor janela para fechar isso.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE public.api_assinaturaetapaproducao      OWNER TO soluscrt_app;
ALTER TABLE public.api_auditoriaclinica             OWNER TO soluscrt_app;
ALTER TABLE public.api_avaliacaonps                 OWNER TO soluscrt_app;
ALTER TABLE public.api_buscaativasocial             OWNER TO soluscrt_app;  -- SUAS
ALTER TABLE public.api_campanhacomunicacaoplano     OWNER TO soluscrt_app;
ALTER TABLE public.api_casoeticomedico              OWNER TO soluscrt_app;  -- ética médica
ALTER TABLE public.api_chegadaps                    OWNER TO soluscrt_app;
ALTER TABLE public.api_clientefidelidade            OWNER TO soluscrt_app;
ALTER TABLE public.api_conselheirosaude             OWNER TO soluscrt_app;
ALTER TABLE public.api_deliberacaoconselhosaude     OWNER TO soluscrt_app;
ALTER TABLE public.api_desvioproducao               OWNER TO soluscrt_app;
ALTER TABLE public.api_encaminhamentoconselhotutelar OWNER TO soluscrt_app; -- ECA (criança)
ALTER TABLE public.api_escalaprofissionalrede       OWNER TO soluscrt_app;
ALTER TABLE public.api_especificacaoproducao        OWNER TO soluscrt_app;
ALTER TABLE public.api_fornecedorhospital           OWNER TO soluscrt_app;
ALTER TABLE public.api_guiaintercambio              OWNER TO soluscrt_app;
ALTER TABLE public.api_guiaoncologica               OWNER TO soluscrt_app;  -- oncologia
ALTER TABLE public.api_identidadepaciente           OWNER TO soluscrt_app;  -- MPI paciente
ALTER TABLE public.api_importacaodados              OWNER TO soluscrt_app;
ALTER TABLE public.api_inconsistenciacadastral      OWNER TO soluscrt_app;
ALTER TABLE public.api_itempedidodelivery           OWNER TO soluscrt_app;
ALTER TABLE public.api_juntamedicaopme              OWNER TO soluscrt_app;  -- OPME
ALTER TABLE public.api_logmensagemwhatsapp          OWNER TO soluscrt_app;
ALTER TABLE public.api_manifestacaoouvidoria        OWNER TO soluscrt_app;
ALTER TABLE public.api_membrocomissaoetica          OWNER TO soluscrt_app;
ALTER TABLE public.api_modeloiaarea                 OWNER TO soluscrt_app;
ALTER TABLE public.api_opmeprocedimento             OWNER TO soluscrt_app;  -- OPME
ALTER TABLE public.api_ordemproducaoindustrial      OWNER TO soluscrt_app;
ALTER TABLE public.api_pedidoexamevita              OWNER TO soluscrt_app;  -- VITA
ALTER TABLE public.api_portalfacialoperadora        OWNER TO soluscrt_app;  -- ⚠ auth facial
ALTER TABLE public.api_prontuariosocialpaif         OWNER TO soluscrt_app;  -- SUAS (violência)
ALTER TABLE public.api_redeapoiosst                 OWNER TO soluscrt_app;
ALTER TABLE public.api_registrocampoproducao        OWNER TO soluscrt_app;
ALTER TABLE public.api_registroobitomunicipal       OWNER TO soluscrt_app;  -- óbitos (Governo)
ALTER TABLE public.api_ressarcimentosus             OWNER TO soluscrt_app;
ALTER TABLE public.api_reuniaoconselhosaude         OWNER TO soluscrt_app;
ALTER TABLE public.api_solicitacaovidarh            OWNER TO soluscrt_app;
ALTER TABLE public.api_territoriovigilanciasocial   OWNER TO soluscrt_app;  -- SUAS
ALTER TABLE public.api_totemcheckinlog              OWNER TO soluscrt_app;  -- ⚠ kiosk
ALTER TABLE public.api_totemdispositivo             OWNER TO soluscrt_app;  -- ⚠ kiosk
ALTER TABLE public.api_transacaofidelidade          OWNER TO soluscrt_app;
ALTER TABLE public.api_triagemmanchesterps          OWNER TO soluscrt_app;  -- triagem (Hospital)
ALTER TABLE public.api_twofactortotp                OWNER TO soluscrt_app;  -- ⚠ 2FA (login)

COMMIT;

-- ── VALIDAÇÃO (rodar como o papel do APP, ex.: SET ROLE soluscrt) ────────────
-- Deve retornar 0 linhas SEM app.empresa_id setado (RLS escondendo):
--   SET ROLE soluscrt;
--   SELECT count(*) FROM api_prontuariosocialpaif;                    -- espera 0
--   SET app.empresa_id = '45';
--   SELECT count(*) FROM api_prontuariosocialpaif;                    -- espera >0 (do tenant 45)
--   RESET ROLE;

-- ── ROLLBACK (se algum caminho quebrar) ─────────────────────────────────────
-- BEGIN;
--   ALTER TABLE public.api_twofactortotp OWNER TO soluscrt;
--   -- ... (reverter as tabelas que causaram problema, ou todas)
-- COMMIT;
