from django.contrib import admin
from django.urls import path, include
from django.http import FileResponse
import os
from api.views_dashboard import dashboard
from api.views import casos_por_regiao
from api.views import mapa_risco
from api import views



from api.views import (
    registrar_sintoma, listar_sintomas,
    alertas, tela_login, tela_pagamento,
    relatorio_regioes, relatorio_municipios,
    analisar_tosse,
    resumo_municipios, resumo_estados,
    detectar_surtos, prever_surtos,
    painel,
    diagnostico_ia, analisar_audio,
    resumo_doencas, diagnostico_ia_avancado,
    limpar_casos, mapa_casos,
    insights_nacional,
    tela_cadastro, tela_login_empresa, tela_login_governo,
    registrar_sintoma_publico, app_resumo_publico, app_radar_local, app_mapa_publico, app_alertas_publicos, registrar_push_publico,
    site_principal, apresentacao_comercial, documento_publico
)

from api.views_auth import registrar_empresa, login_empresa, login_portal_empresa, login_portal_governo, logout_empresa, logout_governo, logout_operacao, login_dono_saas, ativar_sessao_aba
from api.views_dashboard import dados_dashboard, dashboard, global_paises, dashboard_farmacia, dashboard_hospital, dashboard_governo, command_ai, api_command_ai, api_command_ai_feedback, contrato_governo, licencas, seguranca, api_dispositivos, api_revogar_dispositivo, api_auditoria_seguranca, usuarios_empresa, api_usuarios_empresa, api_criar_usuario_empresa, api_desativar_usuario_empresa, login_operacao, console_operacional, api_dono_resumo, api_dono_atualizar_cliente, api_dono_financeiro_acao, api_dono_exportar, api_alertas_governo, api_criar_alerta_governo, api_toggle_alerta_governo, api_fluxo_alerta_governo, farmacia_gestao_page, hospital_gestao_page, governo_gestao_page, rede_gestao_page, plano_saude_gestao_page
from api.views_corporativo import (
    dashboard_empresa_corporativo,
    api_empresa_corporativo_resumo,
    api_empresa_corporativo_catalogo,
    app_colaborador_corporativo,
    api_colaborador_corporativo_config,
    api_corporativo_checkin_diario,
    api_corporativo_checkin_semanal,
    api_colaborador_trilhas,
)
from api.views_sst import (
    api_sst_dashboard,
    api_funcionarios,
    api_asos,
    api_cats,
    api_documentos_sst,
    api_afastamentos_sst,
    api_exames,
    api_esocial_eventos,
    api_relatorios_sst,
    api_prontuario_funcionario,
    api_treinamentos,
    api_treinamentos_resumo,
    sst_home_redirect,
    sst_configuracoes_redirect,
    sst_funcionarios_page,
    sst_asos_page,
    sst_exames_page,
    sst_afastamentos_page,
    sst_cats_page,
    sst_documentos_page,
    sst_esocial_page,
    sst_relatorios_page,
    sst_agendamento_page,
    sst_funcionarios_novo_redirect,
    sst_documentos_novo_redirect,
    sst_prontuario_page,
    sst_treinamentos_page,
    sst_normas_page,
    # new
    sst_configuracoes_page,
    api_sst_configuracoes,
    sst_epis_page,
    api_epis_catalogo,
    api_epis_entregas,
    api_epis_devolver,
    api_epis_pdf_ficha,
    api_epis_sem_epi,
    api_aso_pdf,
    api_cat_pdf,
    api_prontuario_pdf,
    api_sst_conformidade,
    api_sst_conformidade_pdf,
    api_sst_relatorio_consolidado_pdf,
    sst_conformidade_page,
)
from api.views_agendamento_sst import (
    api_agendamentos_sst,
    api_agendamento_sst_detalhe,
    api_agendamentos_sst_kpis,
)
from api.views_esocial_sst import (
    api_esocial_eventos,
    api_esocial_gerar_xml,
    api_esocial_registrar_cat,
    api_esocial_registrar_aso,
    api_esocial_registrar_afastamento,
    api_esocial_marcar_transmitido,
    api_esocial_kpis,
    api_aso_compartilhamentos,
    api_aso_revogar_compartilhamento,
    portal_aso_publico,
)
from api.views_alertas import api_alertas, alertas_page
from api.views_executive import api_executive_dashboard, executive_dashboard_page
from api.views_rede import api_rede_kpis, dashboard_rede_page
from api.views_compliance import (
    api_compliance_resumo, api_compliance_trilha,
    api_compliance_dispositivos, api_compliance_exportar, compliance_page,
)
from api.views_relatorio import api_relatorio_executivo, relatorio_page
from api.views_financeiro import api_financeiro_metricas, api_financeiro_cohorts, financeiro_page
from api.views_observabilidade import api_health, api_slo_status, api_slo_incidentes, observabilidade_page
from api.views_gtm import api_gtm_funil, api_gtm_pipeline, api_gtm_expansao, gtm_page
from api.views_eventos import (
    api_eventos_status, api_eventos_dlq, api_eventos_publicar,
    api_eventos_reprocessar, api_eventos_subscricoes, eventos_page,
)
from api.views_schema import (
    api_schema_contratos, api_schema_contrato_detalhe,
    api_schema_versoes, api_schema_validar, api_schema_seed, schema_registry_page,
)
from api.views_mlops import (
    api_mlops_modelos, api_mlops_modelo_detalhe, api_mlops_run,
    api_mlops_snapshot, api_mlops_drift_alertas, api_mlops_seed, mlops_page,
)
from api.views_feature_store import (
    api_feature_store_features, api_feature_store_dicionario,
    api_feature_store_qualidade, feature_store_page,
)
from api.views_governanca import (
    api_governanca_semanal, api_governanca_burn_multiple,
    api_governanca_pricing_valor, api_governanca_ml_fairness,
    api_governanca_causal_impact, governanca_page,
)
from api.views_api_versioning import api_circuit_breaker_status, api_rate_limit_status
from api.views_contratos import (
    api_beneficiario_excluir,
    api_beneficiarios_contrato,
    api_contrato_saude_detalhe,
    api_contratos_kpis,
    api_contratos_saude,
    contratos_page,
)
from api.views_series_epi import (
    api_ponto_serie_detalhe,
    api_pontos_serie,
    api_serie_epidemiologica_detalhe,
    api_series_dashboard,
    api_series_epidemiologicas,
    series_epi_page,
)
from api.views_lotes_farmacia import (
    api_lotes_farmacia,
    api_lote_farmacia_detalhe,
    api_lotes_farmacia_kpis,
)
from api.views_farmacia_avancado import (
    api_pacientes_farmacia, api_paciente_farmacia_detalhe,
    api_receitas_farmacia, api_receita_farmacia_detalhe,
    api_inventarios_farmacia, api_inventario_farmacia_detalhe,
    api_descartes_farmacia,
    api_farmacia_kpis_avancados,
    api_farmacia_relatorio_curva_abc,
    api_farmacia_relatorio_cmm,
    api_farmacia_relatorio_giro,
)
from api.views_riscos_sst import (
    api_planos_acao_sst,
    api_plano_acao_sst_detalhe,
    api_risco_detalhe,
    api_riscos_kpis,
    api_riscos_ocupacionais,
    sst_riscos_page,
)
from api.views_vacinacao import (
    api_campanha_detalhe,
    api_campanhas_vacinacao,
    api_registro_vacinacao_detalhe,
    api_registros_vacinacao,
    api_vacinacao_kpis,
)
from api.views_prescricao import (
    api_prescricoes_internacao,
    api_prescricao_status,
    api_atos_normativos,
    api_ato_normativo_detalhe,
)
from api.views_gestao import (
    gestao_corporativa,
    api_apoio_fila,
    api_apoio_atualizar,
    api_programas,
    api_programa_status,
    api_acoes,
    api_acao_status,
    api_gestao_resumo,
)
from api.views_competencia import (
    competencia_corporativa,
    api_cargos,
    api_funcoes_criticas,
    api_equipamentos,
    api_trilhas,
    api_itens,
    api_evidencias,
    api_evidencia_colaborador,
    api_validar,
    api_prontidao,
)
from api.views_escalas import (
    escalas_corporativa,
    api_escalas,
    api_escala_detalhe,
    api_escala_ciclo,
    api_escala_atribuicoes,
    api_escalas_resumo,
)
from api.views_lider import painel_lider, api_unidade_dados
from api.views_reset_senha import solicitar_reset_senha, redefinir_senha, reset_senha_sucesso
from api.views_comunicacao import (
    painel_comunicacao, sala_video_empresa,
    api_listar_salas, api_criar_sala, api_mensagens, api_enviar_mensagem,
    api_marcar_lida, api_criar_video, api_encerrar_video,
    api_colaboradores_comunicacao,
    colaborador_chat, colaborador_video,
    api_colab_mensagens, api_colab_enviar, api_colab_video_ativa,
    painel_grupos, api_criar_grupo, api_listar_salas_por_tipo, api_membros_grupo,
)
from api.views_farmacia import api_farmacia_painel
from api.views_hospital import api_hospital_painel
from api.views_farmacia_ops import (
    api_fornecedores_farmacia, api_fornecedor_farmacia_detalhe,
    api_itens_farmacia, api_item_farmacia_detalhe,
    api_movimentos_estoque, api_dispensacoes_farmacia,
    api_pedidos_compra_farmacia, api_pedido_compra_status,
    api_farmacia_ops_kpis, api_farmacia_pdf_estoque, api_farmacia_pdf_dispensacoes,
)
from api.views_hospital_ops import (
    api_departamentos_hospital, api_departamento_hospital_detalhe,
    api_leitos_hospital, api_leito_status,
    api_pacientes_hospital, api_triagens_hospital,
    api_internacoes_hospital, api_internacao_status,
    api_evolucoes_internacao, api_hospital_ops_kpis,
    api_hospital_pdf_internacoes, api_hospital_pdf_ficha_internacao,
)
from api.views_governo_ops import (
    api_programas_gov, api_programa_gov_detalhe,
    api_indicadores_gov, api_indicador_gov_detalhe,
    api_orcamentos_gov, api_planos_acao_gov, api_plano_acao_gov_detalhe,
    api_governo_ops_kpis, api_governo_pdf_relatorio,
)
from api.views_rede import (
    api_redes, api_rede_convidar, api_rede_estoque, api_rede_item_disponibilidade,
    api_transferencias, api_transferencia_detalhe,
    api_mensagens_rede, api_mensagem_marcar_lida,
    api_planos_saude, api_plano_saude_detalhe,
    api_beneficiarios, api_beneficiario_detalhe,
    api_guias, api_guia_detalhe, api_plano_kpis,
)
from api.epidemiologia import panorama_epidemiologico, exportar_briefing_governo
from api.fontes_oficiais_brasil import api_brasil_fontes_oficiais
from api.governanca import api_auditoria_institucional, api_matriz_decisao, api_metodologia_epidemiologica

# 🔥 IMPORT CORRETO (APENAS UM)
from api.views_pagamento import criar_pagamento, webhook, sucesso, erro, pendente, status_pagamento, planos_publicos


def service_worker(request):
    return FileResponse(open(os.path.join(os.getcwd(), 'sw.js'), 'rb'))


urlpatterns = [
    path('admin/', admin.site.urls),

    # 🔐 LOGIN
    path('', site_principal),
    path('apresentacao/', apresentacao_comercial),
    path('privacidade/', documento_publico, {"slug": "privacidade"}),
    path('termos/', documento_publico, {"slug": "termos"}),
    path('seguranca-lgpd/', documento_publico, {"slug": "seguranca-lgpd"}),
    path('metodologia/', documento_publico, {"slug": "metodologia"}),
    path('suporte/', documento_publico, {"slug": "suporte"}),
    path('login-empresa/', tela_login_empresa),
    path('login-governo/', tela_login_governo),
    path('operacao-central/', login_operacao),
    path('api/login', login_empresa),
    path('api/login-empresa', login_portal_empresa),
    path('api/login-governo', login_portal_governo),
    path('api/sessao/aba', ativar_sessao_aba),
    path('api/operacao-central/login', login_dono_saas),
    path('logout/', logout_empresa),
    path('sair/', logout_empresa),          # alias amigável
    path('logout-governo/', logout_governo),
    path('sair-governo/', logout_governo),  # alias amigável
    path('logout-operacao/', logout_operacao),
    path('solicitar-reset-senha/', solicitar_reset_senha),
    path('redefinir-senha/<str:token_str>/', redefinir_senha),
    path('reset-senha-sucesso/', reset_senha_sucesso),

    # 🧠 DASHBOARD
    path('dashboard/', dashboard),
    path('dashboard-empresa/', dashboard_empresa_corporativo),
    path('dashboard-farmacia/', dashboard_farmacia),
    path('dashboard-hospital/', dashboard_hospital),
    path('dashboard-governo/', dashboard_governo),
    # Aliases com slug mais curto
    path('farmacia/', dashboard_farmacia),
    path('hospital/', dashboard_hospital),
    path('governo/', dashboard_governo),
    # Gestão operacional
    path('farmacia/gestao/', farmacia_gestao_page),
    path('hospital/gestao/', hospital_gestao_page),
    path('governo/gestao/', governo_gestao_page),
    path('rede/gestao/', rede_gestao_page),
    path('plano-saude/gestao/', plano_saude_gestao_page),
    path('sala-decisao-ia/', command_ai),
    path('command-ai/', command_ai),
    path('contrato-governo/', contrato_governo),
    path('licencas/', licencas),
    path('seguranca/', seguranca),
    path('usuarios/', usuarios_empresa),
    path('console-operacional/', console_operacional),

    # 💬 COMUNICAÇÃO — Teams-like
    path('sst/comunicacao/', painel_comunicacao),
    path('sst/video/<int:sessao_id>/', sala_video_empresa),
    path('api/comunicacao/salas/', api_listar_salas_por_tipo),
    path('api/comunicacao/salas/criar/', api_criar_sala),
    path('api/comunicacao/colaboradores/', api_colaboradores_comunicacao),
    path('api/comunicacao/sala/<int:sala_id>/mensagens/', api_mensagens),
    path('api/comunicacao/sala/<int:sala_id>/enviar/', api_enviar_mensagem),
    path('api/comunicacao/sala/<int:sala_id>/lida/', api_marcar_lida),
    path('api/comunicacao/video/criar/', api_criar_video),
    path('api/comunicacao/video/<int:sessao_id>/encerrar/', api_encerrar_video),
    # colaborador side
    path('colaborador/c/<str:codigo>/chat/', colaborador_chat),
    path('colaborador/c/<str:codigo>/video/<str:sala>/', colaborador_video),
    path('api/corporativo/<str:codigo>/chat/mensagens/', api_colab_mensagens),
    path('api/corporativo/<str:codigo>/chat/enviar/', api_colab_enviar),
    path('api/corporativo/<str:codigo>/video/ativa/', api_colab_video_ativa),

    # 💰 PAGAMENTO
    path('pagamento/', tela_pagamento),
    path('colaborador/c/<str:codigo>/', app_colaborador_corporativo),
    path('mobile/c/<str:codigo>/', app_colaborador_corporativo),
    path('colaborador-mobile/c/<str:codigo>/', app_colaborador_corporativo),
    path('competencia/', competencia_corporativa),
    path('gestao/', gestao_corporativa),
    path('api/gestao/resumo', api_gestao_resumo),
    path('api/gestao/apoio', api_apoio_fila),
    path('api/gestao/apoio/<int:pedido_id>', api_apoio_atualizar),
    path('api/gestao/programas', api_programas),
    path('api/gestao/programas/<int:programa_id>/status', api_programa_status),
    path('api/gestao/acoes', api_acoes),
    path('api/gestao/acoes/<int:acao_id>/status', api_acao_status),
    path('escalas/', escalas_corporativa),
    path('api/escalas', api_escalas),
    path('api/escalas/resumo', api_escalas_resumo),
    path('api/escalas/<int:escala_id>', api_escala_detalhe),
    path('api/escalas/<int:escala_id>/ciclo', api_escala_ciclo),
    path('api/escalas/<int:escala_id>/atribuicoes', api_escala_atribuicoes),
    path('painel-lider/', painel_lider),
    path('api/lider/unidade/<int:unidade_id>/dados', api_unidade_dados),

    # 🚨 Alertas inteligentes
    path('alertas/', alertas_page),
    path('api/alertas/', api_alertas),
    path('api/alertas', api_alertas),
    # 📊 Dashboard Executivo
    path('executive/', executive_dashboard_page),
    path('api/executive/dashboard/', api_executive_dashboard),
    path('api/executive/dashboard', api_executive_dashboard),
    # 🌐 Dashboard Executivo de Rede
    path('dashboard-rede/', dashboard_rede_page),
    path('api/rede/kpis/', api_rede_kpis),
    path('api/rede/kpis', api_rede_kpis),
    # 🔒 Compliance & Auditoria
    path('compliance/', compliance_page),
    path('api/compliance/resumo/', api_compliance_resumo),
    path('api/compliance/resumo', api_compliance_resumo),
    path('api/compliance/trilha/', api_compliance_trilha),
    path('api/compliance/trilha', api_compliance_trilha),
    path('api/compliance/dispositivos/', api_compliance_dispositivos),
    path('api/compliance/dispositivos', api_compliance_dispositivos),
    path('api/compliance/exportar/', api_compliance_exportar),
    path('api/compliance/exportar', api_compliance_exportar),
    # 📄 Relatório Executivo
    path('relatorio-executivo/', relatorio_page),
    path('api/relatorio/executivo/', api_relatorio_executivo),
    path('api/relatorio/executivo', api_relatorio_executivo),
    # Contratos de saúde e séries epidemiológicas
    path('contratos/', contratos_page),
    path('series-epidemiologicas/', series_epi_page),

    # 🏥 SST / Saúde Ocupacional — páginas
    path('sst/', sst_home_redirect),
    path('sst/funcionarios/', sst_funcionarios_page),
    path('sst/funcionarios/novo/', sst_funcionarios_novo_redirect),
    path('sst/asos/', sst_asos_page),
    path('sst/exames/', sst_exames_page),
    path('sst/exames/agendar/', sst_agendamento_page),
    path('sst/afastamentos/', sst_afastamentos_page),
    path('sst/cats/', sst_cats_page),
    path('sst/documentos/', sst_documentos_page),
    path('sst/documentos/novo/', sst_documentos_novo_redirect),
    path('sst/esocial/', sst_esocial_page),
    path('sst/relatorios/', sst_relatorios_page),
    path('sst/treinamentos/', sst_treinamentos_page),
    path('sst/normas/', sst_normas_page),
    path('sst/funcionarios/<int:funcionario_id>/', sst_prontuario_page),
    path('sst/configuracoes/', sst_configuracoes_page),
    path('sst/epis/', sst_epis_page),
    path('sst/conformidade/', sst_conformidade_page),
    path('sst/riscos/', sst_riscos_page),
    path('sst/comunicacao/grupos/', painel_grupos),
    # 🏥 SST / Saúde Ocupacional — API
    path('api/sst/dashboard', api_sst_dashboard),
    path('api/sst/funcionarios', api_funcionarios),
    path('api/sst/funcionarios/', api_funcionarios),
    path('api/sst/asos', api_asos),
    path('api/sst/cats', api_cats),
    path('api/sst/documentos', api_documentos_sst),
    path('api/sst/afastamentos', api_afastamentos_sst),
    path('api/sst/exames', api_exames),
    path('api/sst/esocial', api_esocial_eventos),
    path('api/sst/relatorios', api_relatorios_sst),
    path('api/sst/funcionarios/<int:funcionario_id>/prontuario', api_prontuario_funcionario),
    path('api/sst/treinamentos', api_treinamentos),
    path('api/sst/treinamentos/resumo', api_treinamentos_resumo),
    path('api/sst/configuracoes', api_sst_configuracoes),
    path('api/sst/configuracoes/', api_sst_configuracoes),
    path('api/sst/epis/catalogo', api_epis_catalogo),
    path('api/sst/epis/catalogo/', api_epis_catalogo),
    path('api/sst/epis/entregas', api_epis_entregas),
    path('api/sst/epis/entregas/', api_epis_entregas),
    path('api/sst/epis/entregas/<int:entrega_id>/devolver', api_epis_devolver),
    path('api/sst/epis/entregas/<int:entrega_id>/devolver/', api_epis_devolver),
    path('api/sst/epis/ficha/<int:funcionario_id>/pdf', api_epis_pdf_ficha),
    path('api/sst/epis/sem-epi/', api_epis_sem_epi),
    path('api/sst/epis/sem-epi', api_epis_sem_epi),
    path('api/sst/conformidade/', api_sst_conformidade),
    path('api/sst/conformidade', api_sst_conformidade),
    path('api/sst/conformidade/pdf', api_sst_conformidade_pdf),
    path('api/sst/conformidade/pdf/', api_sst_conformidade_pdf),
    path('api/sst/relatorio/consolidado/pdf', api_sst_relatorio_consolidado_pdf),
    path('api/sst/relatorio/consolidado/pdf/', api_sst_relatorio_consolidado_pdf),
    # Riscos ocupacionais / PGR
    path('api/sst/riscos/', api_riscos_ocupacionais),
    path('api/sst/riscos/kpis/', api_riscos_kpis),
    path('api/sst/riscos/<int:risco_id>/', api_risco_detalhe),
    path('api/sst/planos-acao/', api_planos_acao_sst),
    path('api/sst/planos-acao/<int:plano_id>/', api_plano_acao_sst_detalhe),
    # Vacinação ocupacional
    path('api/sst/vacinacao/kpis/', api_vacinacao_kpis),
    path('api/sst/vacinacao/campanhas/', api_campanhas_vacinacao),
    path('api/sst/vacinacao/campanhas/<int:campanha_id>/', api_campanha_detalhe),
    path('api/sst/vacinacao/campanhas/<int:campanha_id>/registros/', api_registros_vacinacao),
    path('api/sst/vacinacao/registros/<int:reg_id>/', api_registro_vacinacao_detalhe),
    # Contratos de saúde / convênios
    path('api/contratos/', api_contratos_saude),
    path('api/contratos/kpis/', api_contratos_kpis),
    path('api/contratos/<int:contrato_id>/', api_contrato_saude_detalhe),
    path('api/contratos/<int:contrato_id>/beneficiarios/', api_beneficiarios_contrato),
    path('api/contratos/beneficiarios/<int:beneficiario_id>/', api_beneficiario_excluir),
    # Séries epidemiológicas
    path('api/series-epi/', api_series_epidemiologicas),
    path('api/series-epi/dashboard/', api_series_dashboard),
    path('api/series-epi/<int:serie_id>/', api_serie_epidemiologica_detalhe),
    path('api/series-epi/<int:serie_id>/pontos/', api_pontos_serie),
    path('api/series-epi/pontos/<int:ponto_id>/', api_ponto_serie_detalhe),
    # Agendamento SST
    path('api/sst/agendamentos/', api_agendamentos_sst),
    path('api/sst/agendamentos', api_agendamentos_sst),
    path('api/sst/agendamentos/kpis/', api_agendamentos_sst_kpis),
    path('api/sst/agendamentos/kpis', api_agendamentos_sst_kpis),
    path('api/sst/agendamentos/<int:ag_id>/', api_agendamento_sst_detalhe),
    path('api/sst/agendamentos/<int:ag_id>', api_agendamento_sst_detalhe),
    # ── eSocial SST ──────────────────────────────────────────────────────────
    path('api/sst/esocial/eventos/', api_esocial_eventos),
    path('api/sst/esocial/kpis/', api_esocial_kpis),
    path('api/sst/esocial/eventos/<int:evento_id>/xml/', api_esocial_gerar_xml),
    path('api/sst/esocial/eventos/<int:evento_id>/transmitido/', api_esocial_marcar_transmitido),
    path('api/sst/cats/<int:cat_id>/esocial/', api_esocial_registrar_cat),
    path('api/sst/asos/<int:aso_id>/esocial/', api_esocial_registrar_aso),
    path('api/sst/afastamentos/<int:afastamento_id>/esocial/', api_esocial_registrar_afastamento),
    # ── Compartilhamento de ASO ───────────────────────────────────────────────
    path('api/sst/asos/<int:aso_id>/compartilhar/', api_aso_compartilhamentos),
    path('api/sst/aso/compartilhamento/<str:token>/revogar/', api_aso_revogar_compartilhamento),
    path('sst/aso/portal/<str:token>/', portal_aso_publico),
    path('api/sst/asos/<int:aso_id>/pdf', api_aso_pdf),
    path('api/sst/cats/<int:cat_id>/pdf', api_cat_pdf),
    path('api/sst/funcionarios/<int:funcionario_id>/prontuario/pdf', api_prontuario_pdf),
    # grupos de chat
    path('api/comunicacao/grupos/', api_criar_grupo),
    path('api/comunicacao/grupos/criar/', api_criar_grupo),
    path('api/comunicacao/salas/filtro/', api_listar_salas_por_tipo),
    path('api/comunicacao/grupos/<int:sala_id>/membros/', api_membros_grupo),

    # 📊 API PRINCIPAL
    path('api/registrar', registrar_sintoma),
    path('api/public/registrar', registrar_sintoma_publico),
    path('api/sintomas', listar_sintomas),
    path('api/dashboard', dados_dashboard),
    path('api/empresa/resumo', api_empresa_corporativo_resumo),
    path('api/empresa/catalogo', api_empresa_corporativo_catalogo),
    path('api/corporativo/<str:codigo>/config', api_colaborador_corporativo_config),
    path('api/corporativo/<str:codigo>/checkin-diario', api_corporativo_checkin_diario),
    path('api/corporativo/<str:codigo>/checkin-semanal', api_corporativo_checkin_semanal),
    path('api/corporativo/<str:codigo>/evidencia', api_evidencia_colaborador),
    path('api/corporativo/cargos', api_cargos),
    path('api/corporativo/funcoes-criticas', api_funcoes_criticas),
    path('api/corporativo/equipamentos', api_equipamentos),
    path('api/corporativo/trilhas', api_trilhas),
    path('api/corporativo/trilhas/<int:trilha_id>/itens', api_itens),
    path('api/corporativo/evidencias', api_evidencias),
    path('api/corporativo/evidencias/<int:evidencia_id>/validar', api_validar),
    path('api/corporativo/prontidao', api_prontidao),
    path('api/corporativo/mobile/<str:codigo>/config', api_colaborador_corporativo_config),
    path('api/corporativo/mobile/<str:codigo>/checkin-diario', api_corporativo_checkin_diario),
    path('api/corporativo/mobile/<str:codigo>/checkin-semanal', api_corporativo_checkin_semanal),
    path('api/colaborador-mobile/<str:codigo>/config', api_colaborador_corporativo_config),
    path('api/colaborador-mobile/<str:codigo>/checkin-diario', api_corporativo_checkin_diario),
    path('api/colaborador-mobile/<str:codigo>/checkin-semanal', api_corporativo_checkin_semanal),
    path('api/colaborador-mobile/<str:codigo>/trilhas', api_colaborador_trilhas),
    path('api/alertas', alertas),
    path('api/public/resumo', app_resumo_publico),
    path('api/public/radar-local', app_radar_local),
    path('api/public/mapa', app_mapa_publico),
    path('api/public/alertas', app_alertas_publicos),
    path('api/public/legal-consent', views.registrar_aceite_legal_publico),
    path('api/public/push-token', registrar_push_publico),

    path('api/registrar_empresa', registrar_empresa),
    path('api/global-paises', global_paises),
    path('api/dispositivos', api_dispositivos),
    path('api/dispositivos/revogar', api_revogar_dispositivo),
    path('api/seguranca/auditoria', api_auditoria_seguranca),
    path('api/usuarios', api_usuarios_empresa),
    path('api/usuarios/criar', api_criar_usuario_empresa),
    path('api/usuarios/desativar', api_desativar_usuario_empresa),
    path('api/operacao-central/resumo', api_dono_resumo),
    path('api/operacao-central/cliente/atualizar', api_dono_atualizar_cliente),
    path('api/operacao-central/financeiro/acao', api_dono_financeiro_acao),
    path('api/operacao-central/exportar', api_dono_exportar),
    path('api/farmacia/painel', api_farmacia_painel),
    # ── Farmácia Operacional ──────────────────────────────────
    path('api/farmacia/ops/kpis/', api_farmacia_ops_kpis),
    path('api/farmacia/fornecedores/', api_fornecedores_farmacia),
    path('api/farmacia/fornecedores/<int:fornecedor_id>/', api_fornecedor_farmacia_detalhe),
    path('api/farmacia/itens/', api_itens_farmacia),
    path('api/farmacia/itens/<int:item_id>/', api_item_farmacia_detalhe),
    path('api/farmacia/movimentos/', api_movimentos_estoque),
    path('api/farmacia/dispensacoes/', api_dispensacoes_farmacia),
    path('api/farmacia/pedidos/', api_pedidos_compra_farmacia),
    path('api/farmacia/pedidos/<int:pedido_id>/status/', api_pedido_compra_status),
    path('api/farmacia/pdf/estoque/', api_farmacia_pdf_estoque),
    path('api/farmacia/pdf/dispensacoes/', api_farmacia_pdf_dispensacoes),
    # ── Lotes / Rastreabilidade ──────────────────────────────────
    path('api/farmacia/lotes/', api_lotes_farmacia),
    path('api/farmacia/lotes/kpis/', api_lotes_farmacia_kpis),
    path('api/farmacia/lotes/<int:lote_id>/', api_lote_farmacia_detalhe),
    # ── Farmácia Avançado ─────────────────────────────────────────
    path('api/farmacia/pacientes/', api_pacientes_farmacia),
    path('api/farmacia/pacientes/<int:paciente_id>/', api_paciente_farmacia_detalhe),
    path('api/farmacia/receitas/', api_receitas_farmacia),
    path('api/farmacia/receitas/<int:receita_id>/', api_receita_farmacia_detalhe),
    path('api/farmacia/inventarios/', api_inventarios_farmacia),
    path('api/farmacia/inventarios/<int:inventario_id>/', api_inventario_farmacia_detalhe),
    path('api/farmacia/descartes/', api_descartes_farmacia),
    path('api/farmacia/kpis/avancados/', api_farmacia_kpis_avancados),
    path('api/farmacia/relatorios/curva-abc/', api_farmacia_relatorio_curva_abc),
    path('api/farmacia/relatorios/cmm/', api_farmacia_relatorio_cmm),
    path('api/farmacia/relatorios/giro/', api_farmacia_relatorio_giro),
    path('api/hospital/painel', api_hospital_painel),
    # ── Hospital Operacional ─────────────────────────────────
    path('api/hospital/ops/kpis/', api_hospital_ops_kpis),
    path('api/hospital/departamentos/', api_departamentos_hospital),
    path('api/hospital/departamentos/<int:dep_id>/', api_departamento_hospital_detalhe),
    path('api/hospital/leitos/', api_leitos_hospital),
    path('api/hospital/leitos/<int:leito_id>/status/', api_leito_status),
    path('api/hospital/pacientes/', api_pacientes_hospital),
    path('api/hospital/triagens/', api_triagens_hospital),
    path('api/hospital/internacoes/', api_internacoes_hospital),
    path('api/hospital/internacoes/<int:internacao_id>/status/', api_internacao_status),
    path('api/hospital/internacoes/<int:internacao_id>/evolucoes/', api_evolucoes_internacao),
    path('api/hospital/internacoes/<int:internacao_id>/prescricoes/', api_prescricoes_internacao),
    path('api/hospital/prescricoes/<int:prescricao_id>/status/', api_prescricao_status),
    path('api/hospital/pdf/internacoes/', api_hospital_pdf_internacoes),
    path('api/hospital/pdf/internacao/<int:internacao_id>/', api_hospital_pdf_ficha_internacao),
    # ── Rede / Network ───────────────────────────────────────────
    path('api/rede/', api_redes),
    path('api/rede/convidar/', api_rede_convidar),
    path('api/rede/estoque/', api_rede_estoque),
    path('api/rede/disponibilidade/<str:nome_item>/', api_rede_item_disponibilidade),
    path('api/rede/transferencias/', api_transferencias),
    path('api/rede/transferencias/<int:transferencia_id>/', api_transferencia_detalhe),
    path('api/rede/mensagens/', api_mensagens_rede),
    path('api/rede/mensagens/<int:msg_id>/lida/', api_mensagem_marcar_lida),
    # ── Plano de Saúde ───────────────────────────────────────────
    path('api/planos-saude/', api_planos_saude),
    path('api/planos-saude/<int:plano_id>/', api_plano_saude_detalhe),
    path('api/planos-saude/<int:plano_id>/kpis/', api_plano_kpis),
    path('api/planos-saude/<int:plano_id>/beneficiarios/', api_beneficiarios),
    path('api/planos-saude/<int:plano_id>/beneficiarios/<int:ben_id>/', api_beneficiario_detalhe),
    path('api/planos-saude/<int:plano_id>/guias/', api_guias),
    path('api/planos-saude/<int:plano_id>/guias/<int:guia_id>/', api_guia_detalhe),
    path('api/governo/alertas', api_alertas_governo),
    # ── Governo Gestão ───────────────────────────────────────
    path('api/governo/ops/kpis/', api_governo_ops_kpis),
    path('api/governo/programas/', api_programas_gov),
    path('api/governo/programas/<int:programa_id>/', api_programa_gov_detalhe),
    path('api/governo/indicadores/', api_indicadores_gov),
    path('api/governo/indicadores/<int:indicador_id>/', api_indicador_gov_detalhe),
    path('api/governo/orcamentos/', api_orcamentos_gov),
    path('api/governo/planos-acao/', api_planos_acao_gov),
    path('api/governo/planos-acao/<int:plano_id>/', api_plano_acao_gov_detalhe),
    path('api/governo/pdf/relatorio/', api_governo_pdf_relatorio),
    # ── Atos Normativos ──────────────────────────────────────────
    path('api/governo/atos-normativos/', api_atos_normativos),
    path('api/governo/atos-normativos/<int:ato_id>/', api_ato_normativo_detalhe),
    path('api/governo/alertas/criar', api_criar_alerta_governo),
    path('api/governo/alertas/toggle', api_toggle_alerta_governo),
    path('api/governo/alertas/fluxo', api_fluxo_alerta_governo),
    path('api/governanca/metodologia', api_metodologia_epidemiologica),
    path('api/governanca/matriz-decisao', api_matriz_decisao),
    path('api/governanca/auditoria', api_auditoria_institucional),
    path('api/command-ai', api_command_ai),
    path('api/command-ai/feedback', api_command_ai_feedback),

    path("api/analisar-tosse", analisar_tosse),

    path('api/resumo-municipios', resumo_municipios),
    path('api/resumo-estados', resumo_estados),

    path('api/surtos', detectar_surtos),
    path('api/previsao-surtos', prever_surtos),

    path("api/painel", painel),

    path('api/doencas', resumo_doencas),
    path('api/diagnostico', diagnostico_ia),
    path('api/ia-avancada', diagnostico_ia_avancado),

    path('api/analisar-audio', analisar_audio),

    path('api/limpar-casos', limpar_casos),
    path('api/mapa-casos', mapa_casos),

    # 🔥 INSIGHTS
    path('api/insights-nacional', insights_nacional),
    path('api/epidemiologia', panorama_epidemiologico),
    path('api/epidemiologia/briefing', exportar_briefing_governo),
    path('api/brasil/fontes-oficiais', api_brasil_fontes_oficiais),

    # 🔐 API CENTRALIZADA
    path('api/', include('api.urls')),

    # 🧾 CADASTRO
    path('cadastro/', tela_cadastro),

    # 💳 PAGAMENTO (FUNCIONAL)
    path('api/assinatura/<int:empresa_id>/', criar_pagamento),
    path('api/planos-publicos', planos_publicos),
    path('api/webhook', webhook),
    

    # 🔁 RETORNOS DO PAGAMENTO
    path('sucesso/', sucesso),
    path('erro/', erro),
    path('pendente/', pendente),
    path('api/status-pagamento', status_pagamento),
    path("regioes", casos_por_regiao),
    path("api/sintoma/", registrar_sintoma),
    path("api/mapa-risco", mapa_risco),
    path("api/bairros", views.bairros_por_cidade),

    # Financial OS
    path('financeiro/', financeiro_page),
    path('api/financeiro/metricas', api_financeiro_metricas),
    path('api/financeiro/metricas/', api_financeiro_metricas),
    path('api/financeiro/cohorts', api_financeiro_cohorts),
    path('api/financeiro/cohorts/', api_financeiro_cohorts),

    # Observabilidade & SLO
    path('observabilidade/', observabilidade_page),
    path('api/saude', api_health),
    path('api/saude/', api_health),
    path('api/slo/status', api_slo_status),
    path('api/slo/status/', api_slo_status),
    path('api/slo/incidentes', api_slo_incidentes),
    path('api/slo/incidentes/', api_slo_incidentes),

    # GTM Analytics
    path('gtm/', gtm_page),
    path('api/gtm/funil', api_gtm_funil),
    path('api/gtm/funil/', api_gtm_funil),
    path('api/gtm/pipeline', api_gtm_pipeline),
    path('api/gtm/pipeline/', api_gtm_pipeline),
    path('api/gtm/expansao', api_gtm_expansao),
    path('api/gtm/expansao/', api_gtm_expansao),

    # Event Backbone / Outbox
    path('eventos/', eventos_page),
    path('api/eventos/status', api_eventos_status),
    path('api/eventos/status/', api_eventos_status),
    path('api/eventos/dlq', api_eventos_dlq),
    path('api/eventos/dlq/', api_eventos_dlq),
    path('api/eventos/publicar', api_eventos_publicar),
    path('api/eventos/publicar/', api_eventos_publicar),
    path('api/eventos/subscricoes', api_eventos_subscricoes),
    path('api/eventos/subscricoes/', api_eventos_subscricoes),
    path('api/eventos/reprocessar/<uuid:evento_id>/', api_eventos_reprocessar),

    # Schema Registry
    path('schema-registry/', schema_registry_page),
    path('api/schema/contratos', api_schema_contratos),
    path('api/schema/contratos/', api_schema_contratos),
    path('api/schema/contratos/<int:contrato_id>/', api_schema_contrato_detalhe),
    path('api/schema/contratos/<int:contrato_id>/versoes/', api_schema_versoes),
    path('api/schema/validar', api_schema_validar),
    path('api/schema/validar/', api_schema_validar),
    path('api/schema/seed', api_schema_seed),
    path('api/schema/seed/', api_schema_seed),

    # MLOps Pipeline
    path('mlops/', mlops_page),
    path('api/mlops/modelos', api_mlops_modelos),
    path('api/mlops/modelos/', api_mlops_modelos),
    path('api/mlops/modelos/<slug:slug>/', api_mlops_modelo_detalhe),
    path('api/mlops/modelos/<slug:slug>/run/', api_mlops_run),
    path('api/mlops/monitoramento/snapshot', api_mlops_snapshot),
    path('api/mlops/monitoramento/snapshot/', api_mlops_snapshot),
    path('api/mlops/drift/alertas', api_mlops_drift_alertas),
    path('api/mlops/drift/alertas/', api_mlops_drift_alertas),
    path('api/mlops/seed', api_mlops_seed),
    path('api/mlops/seed/', api_mlops_seed),

    # Feature Store & Data Dictionary
    path('feature-store/', feature_store_page),
    path('api/feature-store/features', api_feature_store_features),
    path('api/feature-store/features/', api_feature_store_features),
    path('api/feature-store/dicionario', api_feature_store_dicionario),
    path('api/feature-store/dicionario/', api_feature_store_dicionario),
    path('api/feature-store/qualidade', api_feature_store_qualidade),
    path('api/feature-store/qualidade/', api_feature_store_qualidade),

    # Governança Executiva
    path('governanca/', governanca_page),
    path('api/governanca/semanal', api_governanca_semanal),
    path('api/governanca/semanal/', api_governanca_semanal),
    path('api/governanca/burn-multiple', api_governanca_burn_multiple),
    path('api/governanca/burn-multiple/', api_governanca_burn_multiple),
    path('api/governanca/pricing-valor', api_governanca_pricing_valor),
    path('api/governanca/pricing-valor/', api_governanca_pricing_valor),
    path('api/governanca/ml-fairness', api_governanca_ml_fairness),
    path('api/governanca/ml-fairness/', api_governanca_ml_fairness),
    path('api/governanca/causal-impact', api_governanca_causal_impact),
    path('api/governanca/causal-impact/', api_governanca_causal_impact),

    # Hub Enterprise
    path('hub/', lambda req: __import__('django.shortcuts', fromlist=['render']).render(req, 'hub_enterprise.html')),
    path('plataforma/', lambda req: __import__('django.shortcuts', fromlist=['render']).render(req, 'hub_enterprise.html')),

    # API Infra (versioning, rate limit, circuit breaker)
    path('api/infra/circuit-breaker', api_circuit_breaker_status),
    path('api/infra/circuit-breaker/', api_circuit_breaker_status),
    path('api/infra/rate-limit', api_rate_limit_status),
    path('api/infra/rate-limit/', api_rate_limit_status),
]
