# Generated migration — PostgreSQL Row-Level Security (RLS)
# Ativa isolamento de tenant no banco para 165 tabelas com FK direta para Empresa.
#
# ⚠️  IMPORTANTE — leia antes de rodar em produção:
#
#   PostgreSQL aplica RLS apenas a usuários que NÃO são superuser / table-owner.
#   O usuário típico do Render (DATABASE_URL padrão) é o dono da base, então
#   as políticas existem mas são bypassadas por padrão.
#
#   Para ativação completa, crie um usuário restrito no console do Render Postgres
#   e aponte o DATABASE_URL para ele — veja o README de segurança.
#
#   Em dev local (SQLite) a migration é silenciosa (skip automático).

from django.db import migrations

# (tabela, coluna FK para Empresa)
_TABELAS = [
    ("api_acaocorporativa",              "empresa_id"),
    ("api_afastamentosst",               "empresa_id"),
    ("api_agendamentosst",               "empresa_id"),
    ("api_alertagovernamental",          "empresa_id"),
    ("api_apikeyempresa",                "empresa_id"),
    ("api_asocompartilhamento",          "empresa_origem_id"),   # FK com nome diferente
    ("api_asoocupacional",               "empresa_id"),
    ("api_assinaturadocumentosst",       "empresa_id"),
    ("api_atendimentoubs",               "empresa_id"),
    ("api_atendimentourgencia",          "empresa_id"),
    ("api_atonormativogov",              "empresa_id"),
    ("api_auditoriainstitucional",       "empresa_id"),
    ("api_avaliacaopsicossocial",        "empresa_id"),
    ("api_beneficiarioodonto",           "empresa_id"),
    ("api_blococirurgico",               "empresa_id"),
    ("api_campanhavacinacao",            "empresa_id"),
    ("api_carenciabeneficiario",         "empresa_id"),
    ("api_catocupacional",               "empresa_id"),
    ("api_centrocirurgico",              "empresa_id"),
    ("api_checkinbemestar",              "empresa_id"),
    ("api_checkindiariocorporativo",     "empresa_id"),
    ("api_checkinsemanalcorporativo",    "empresa_id"),
    ("api_colaboradoraliascorporativo",  "empresa_id"),
    ("api_colaboradorescalacorporativa", "empresa_id"),
    ("api_comissaocipa",                 "empresa_id"),
    ("api_competenciaitemcorporativo",   "empresa_id"),
    ("api_configuracaomarca",            "empresa_id"),
    ("api_configuracaosst",              "empresa_id"),
    ("api_conteudosstpublicado",         "empresa_id"),
    ("api_contratogestao",               "empresa_id"),
    ("api_contratogrupo",                "empresa_operadora_id"), # FK com nome diferente
    ("api_contratosaude",                "empresa_id"),
    ("api_corretoraplano",               "empresa_id"),
    ("api_credenciaisintegracoes",       "empresa_id"),
    ("api_departamentohospital",         "empresa_id"),
    ("api_descarteitemfarmacia",         "empresa_id"),
    ("api_despesaclinica",               "clinica_id"),           # clinica IS Empresa
    ("api_diopsdeclaracao",              "empresa_id"),
    ("api_dispensacao",                  "empresa_id"),
    ("api_dispensacaofarmaciabasica",    "empresa_id"),
    ("api_dispensacaomedicamento",       "empresa_id"),
    ("api_dispositivoautorizado",        "empresa_id"),
    ("api_documentosst",                 "empresa_id"),
    ("api_donoauditoriaacao",            "empresa_id"),
    ("api_drefarmacia",                  "empresa_id"),
    ("api_empresacargocorporativo",      "empresa_id"),
    ("api_empresasetor",                 "empresa_id"),
    ("api_empresaturno",                 "empresa_id"),
    ("api_empresaunidade",               "empresa_id"),
    ("api_empresausuario",               "empresa_id"),
    ("api_entregaepi",                   "empresa_id"),
    ("api_epiitem",                      "empresa_id"),
    ("api_equipamentocorporativo",       "empresa_id"),
    ("api_equipesaude",                  "empresa_id"),
    ("api_escalacorporativa",            "empresa_id"),
    ("api_esocialeventosst",             "empresa_id"),
    ("api_estoquemovimento",             "empresa_id"),
    ("api_evidenciacompetenciacorporativa", "empresa_id"),
    ("api_examelis",                     "empresa_id"),
    ("api_exameocupacional",             "empresa_id"),
    ("api_exameris",                     "empresa_id"),
    ("api_expansaocontrato",             "empresa_id"),
    ("api_fapempresa",                   "empresa_id"),
    ("api_farmaciaauditlog",             "empresa_id"),
    ("api_farmaciabasicaitem",           "empresa_id"),
    ("api_farmaciahospitalaritem",       "empresa_id"),
    ("api_farmaciapopularregistro",      "empresa_id"),
    ("api_faturaclinica",                "clinica_id"),           # clinica IS Empresa
    ("api_faturahospitalar",             "empresa_id"),
    ("api_faturamentobeneficiario",      "empresa_id"),
    ("api_faturamentosuslote",           "empresa_id"),
    ("api_financeiroeventosaas",         "empresa_id"),
    ("api_fornecedorfarmacia",           "empresa_id"),
    ("api_fornecedorfarmaciagestao",     "empresa_id"),
    ("api_funcaocriticacorporativa",     "empresa_id"),
    ("api_funcionariosst",               "empresa_id"),
    ("api_guiaodonto",                   "empresa_id"),
    ("api_guiatiss",                     "empresa_id"),
    ("api_iaautorizacaoguia",            "empresa_id"),
    ("api_indicadorsaudegov",            "empresa_id"),
    ("api_integracaorh",                 "empresa_id"),
    ("api_integracaowhatsapp",           "empresa_id"),
    ("api_internacaohospital",           "empresa_id"),
    ("api_inventariofarmacia",           "empresa_id"),
    ("api_itemfarmacia",                 "empresa_id"),
    ("api_itemfaturamento",              "empresa_id"),
    ("api_laudotecnicosst",              "empresa_id"),
    ("api_leitohospital",                "empresa_id"),
    ("api_leitohospitalar",              "empresa_id"),
    ("api_livroregistrocontrolado",      "empresa_id"),
    ("api_logesus",                      "empresa_id"),
    ("api_logwhatsapp",                  "empresa_id"),
    ("api_lotemedicamento",              "empresa_id"),
    ("api_medicamentofarmacia",          "empresa_id"),
    ("api_mensagemchat",                 "empresa_id"),
    ("api_mensagemplano",                "empresa_id"),
    ("api_metaprevine",                  "empresa_id"),
    ("api_modeloml",                     "empresa_id"),
    ("api_movimentoestoque",             "empresa_id"),
    ("api_notafiscaleletronica",         "empresa_id"),
    ("api_notificacaocompulsoria",       "empresa_id"),
    ("api_notificacaofuncionario",       "empresa_id"),
    ("api_onboardingpasso",              "empresa_id"),
    ("api_orcamentosaudegov",            "empresa_id"),
    ("api_outboxevento",                 "empresa_id"),
    ("api_pacientefarmacia",             "empresa_id"),
    ("api_pacientehospital",             "empresa_id"),
    ("api_pacienteinternado",            "empresa_id"),
    ("api_passwordresettoken",           "empresa_id"),
    ("api_pbmconvenio",                  "empresa_id"),
    ("api_pdvsessao",                    "empresa_id"),
    ("api_pdvvenda",                     "empresa_id"),
    ("api_pedidoapoiocorporativo",       "empresa_id"),
    ("api_pedidocomprafarmacia",         "empresa_id"),
    ("api_pedidodelivery",               "empresa_id"),
    ("api_pedidoexame",                  "empresa_id"),
    ("api_pedidofarmacia",               "empresa_id"),
    ("api_planoacaogov",                 "empresa_id"),
    ("api_planoacaosst",                 "empresa_id"),
    ("api_planosaude",                   "empresa_id"),
    ("api_postotrabalho",                "empresa_id"),
    ("api_pppfuncionario",               "empresa_id"),
    ("api_prescricaohospitalar",         "empresa_id"),
    ("api_prestadorplanosaude",          "empresa_id"),
    ("api_producaoambulatorial",         "empresa_id"),
    ("api_programacorporativo",          "empresa_id"),
    ("api_programasaude",                "empresa_id"),
    ("api_programasaudegov",             "empresa_id"),
    ("api_prontuariocidadao",            "empresa_id"),
    ("api_prontuariohospitalar",         "empresa_id"),
    ("api_rbacatribuicao",               "empresa_id"),
    ("api_receitamedica",                "empresa_id"),
    ("api_redecredenciadaplano",         "empresa_id"),
    ("api_reembolso",                    "empresa_id"),
    ("api_registroconflitocultural",     "empresa_id"),
    ("api_registrosintoma",              "empresa_id"),
    ("api_regulacaoassistencial",        "empresa_id"),
    ("api_regulacaoleito",               "empresa_id"),
    ("api_relatoriorag",                 "empresa_id"),
    ("api_resultadoexamelaboratorio",    "empresa_id"),
    ("api_reuniaosst",                   "empresa_id"),
    ("api_riscoocupacional",             "empresa_id"),
    ("api_salachat",                     "empresa_id"),
    ("api_schemacontrato",               "empresa_id"),
    ("api_serieepidemiologica",          "empresa_id"),
    ("api_sessaovideo",                  "empresa_id"),
    ("api_sibregistro",                  "empresa_id"),
    ("api_sinistro",                     "empresa_id"),
    ("api_soc2controle",                 "empresa_id"),
    ("api_solicitacaoexame",             "empresa_id"),
    ("api_subscricaoevento",             "empresa_id"),
    ("api_surtoepidemiologico",          "empresa_id"),
    ("api_teleconsultaautorizacao",      "empresa_id"),
    ("api_teleconsultagoverno",          "empresa_id"),
    ("api_transferenciafarmaciamed",     "empresa_solicitante_id"), # FK com nome diferente
    ("api_treinamentonr",                "empresa_id"),
    ("api_triagemhospital",              "empresa_id"),
    ("api_triagemmanchester",            "empresa_id"),
    ("api_trialempresa",                 "empresa_id"),
    ("api_trilhacompetenciacorporativa", "empresa_id"),
    ("api_unidaderede",                  "empresa_id"),
    ("api_unidadesaude",                 "empresa_id"),
    ("api_usoapiempresa",                "empresa_id"),
    ("api_validacaocompetenciacorporativa", "empresa_id"),
    ("api_vinculoclinicaempresa",        "clinica_id"),            # clinica IS Empresa
]


def _enable_rls(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return  # SQLite em dev — sem RLS

    with conn.cursor() as cur:
        for table, col in _TABELAS:
            # Ativa RLS na tabela
            cur.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')

            # Remove política anterior (idempotente)
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')

            # Cria política:
            #   USING  → filtra SELECT / UPDATE / DELETE (linhas visíveis)
            #   WITH CHECK → bloqueia INSERT / UPDATE de linhas de outro tenant
            #
            # NULLIF(..., '') converte '' (variável não definida) para NULL,
            # fazendo a condição FALSE → nenhuma linha visível se empresa não definida.
            cur.execute(f"""
                CREATE POLICY tenant_isolation ON "{table}"
                AS PERMISSIVE FOR ALL TO PUBLIC
                USING (
                    "{col}" = NULLIF(current_setting('app.empresa_id', true), '')::bigint
                )
                WITH CHECK (
                    "{col}" = NULLIF(current_setting('app.empresa_id', true), '')::bigint
                )
            """)


def _disable_rls(apps, schema_editor):
    conn = schema_editor.connection
    if conn.vendor != "postgresql":
        return

    with conn.cursor() as cur:
        for table, _col in _TABELAS:
            cur.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cur.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0084_nfe_sefaz_model"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
