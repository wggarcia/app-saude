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
    limpar_casos, mapa_casos, simular_focos_epidemicos, regeocodificar_focos,
    insights_nacional,
    tela_cadastro, tela_login_empresa, tela_login_governo,
    registrar_sintoma_publico, app_resumo_publico, app_radar_local, app_mapa_publico, app_vigilancia_resumo, app_alertas_publicos, registrar_push_publico,
    site_principal, apresentacao_comercial, documento_publico
)

from api.views_auth import registrar_empresa, login_empresa, login_portal_empresa, login_portal_governo, logout_empresa, logout_governo, logout_operacao, login_dono_saas, ativar_sessao_aba, ativar_trial
from api.views_enterprise import api_enterprise_command_center, api_enterprise_premium_suite, api_enterprise_seed_operational_demo, api_enterprise_reset_demo
from api.views_dashboard import dados_dashboard, dashboard, global_paises, dashboard_farmacia, dashboard_hospital, dashboard_governo, dashboard_plano_saude, command_ai, api_command_ai, api_command_ai_feedback, contrato_governo, licencas, seguranca, api_dispositivos, api_revogar_dispositivo, api_auditoria_seguranca, usuarios_empresa, api_usuarios_empresa, api_criar_usuario_empresa, api_criar_credencial_ti, api_desativar_usuario_empresa, login_operacao, console_operacional, api_dono_resumo, api_dono_financeiro_real, api_dono_saude, api_dono_app_funcionario, api_dono_operadores, api_dono_operador_acao, api_dono_atualizar_cliente, api_dono_cortesia_plano, api_dono_financeiro_acao, api_dono_onboarding_acao, api_dono_exportar, api_dono_excluir_cliente, api_dono_reset_trial, api_dono_forcar_logout, api_dono_auditoria, api_alertas_governo, api_criar_alerta_governo, api_toggle_alerta_governo, api_fluxo_alerta_governo, farmacia_gestao_page, hospital_gestao_page, governo_gestao_page, governo_plataforma_page, rede_gestao_page, plano_saude_gestao_page, gerencia_executiva_page, portal_rh_page
from api.views_plano_saude import (
    api_ps_dashboard, api_ps_planos, api_ps_plano_detalhe,
    api_ps_beneficiarios, api_ps_beneficiario_detalhe,
    api_ps_prestadores, api_ps_prestador_detalhe, api_ps_portal_prestador,
    api_ps_fila_clinica, api_ps_fila_clinica_acao,
    api_ps_guias, api_ps_guia_detalhe,
    api_ps_sinistros, api_ps_sinistro_detalhe,
    api_ps_reembolsos, api_ps_reembolso_detalhe,
    api_ps_kpis,
    # Expansão — Glosas, Coparticipação, Faturamento, Programas, Sinistralidade IA
    api_ps_glosas, api_ps_glosa_detalhe,
    api_ps_coparticipacao, api_ps_coparticipacao_detalhe,
    api_ps_faturamento, api_ps_fatura_detalhe,
    api_ps_programas, api_ps_programa_detalhe,
    api_ps_inscricoes, api_ps_inscricao_detalhe,
    api_ps_sinistralidade_ia,
    # Enterprise modules
    api_ps_dashboard_exec,
    api_ps_sla,
    api_ps_auditoria,
    api_ps_contratos, api_ps_contrato_detalhe,
    api_ps_comunicacao, api_ps_comunicacao_thread,
    api_ps_telemedicina, api_ps_telemedicina_autorizar,
    api_ps_odontologia, api_ps_guia_odonto_detalhe,
    api_ps_regulatorio_gerar,
)
from api.views_ia import (
    api_ia_classificar,
    api_ia_doencas,
    api_ia_sintomas,
    api_ia_populacao,
    api_ia_calibracao,
    api_ia_urgencias,
)
from api.views_corporativo import (
    dashboard_empresa_corporativo,
    api_empresa_corporativo_resumo,
    api_empresa_corporativo_catalogo,
    app_colaborador_corporativo,
    api_colaborador_corporativo_config,
    api_corporativo_checkin_diario,
    api_corporativo_checkin_semanal,
    api_colaborador_trilhas,
    api_corporativo_rh_resumo,
    api_corporativo_rh_sincronizar,
)
from api.views_sst import (
    api_sst_dashboard,
    api_sst_contexto_integrado,
    api_funcionarios, api_funcionario_detalhe,
    api_asos,
    api_cats,
    api_sst_cids_ocupacionais,
    api_documentos_sst,
    api_afastamentos_sst, api_afastamento_retorno,
    api_exames,
    api_esocial_eventos as api_esocial_eventos_legacy,
    api_relatorios_sst,
    api_prontuario_funcionario,
    api_convidar_app_funcionario,
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
    api_sst_configuracoes, api_sst_mensagem_massa,
    sst_epis_page,
    api_epis_catalogo,
    api_epis_catalogo_lote,
    api_epis_catalogo_detail,
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
    sst_bem_estar_page,
)
from api.views_agendamento_sst import (
    api_agendamentos_sst,
    api_agendamento_sst_detalhe,
    api_agendamentos_sst_kpis,
)
from api.views_esocial_sst import (
    api_esocial_eventos as api_esocial_eventos_sst,
    api_esocial_gerar_xml,
    api_esocial_registrar_cat,
    api_esocial_registrar_aso,
    api_esocial_registrar_afastamento,
    api_esocial_marcar_transmitido,
    api_esocial_kpis,
    api_aso_compartilhamentos,
    api_aso_revogar_compartilhamento,
    portal_aso_publico,
    api_esocial_transmitir,
    api_esocial_aprovar,
    api_esocial_transmitir_pendentes,
    api_esocial_certificado,
    api_esocial_diagnostico,
)
from api.views_esocial_s2245 import (
    api_esocial_s2245_listar,
    api_esocial_s2245_gerar,
    api_esocial_s2245_transmitir,
    api_esocial_s2245_xml,
    api_esocial_s2245_lote,
)
from api.views_alertas import api_alertas, alertas_page
from api.views_executive import api_executive_dashboard, executive_dashboard_page
from api.views_rede import api_rede_kpis, dashboard_rede_page
from api.views_compliance import (
    api_compliance_resumo, api_compliance_trilha,
    api_compliance_dispositivos, api_compliance_exportar, compliance_page,
    api_soc2_controles, api_soc2_evidencias, api_rbac_permissoes, api_rbac_atribuir,
)
from api.views_hub import hub_view
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
    api_governanca_causal_impact, api_governanca_registrar_caixa,
    governanca_page,
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
from api.views_clinica import (
    api_clinica_vinculos,
    api_clinica_vinculo_detalhe,
    api_clinica_enviar_aso,
    pagina_aceitar_convite,
    api_aceitar_vinculo,
    api_empresa_asos_recebidos,
    api_empresa_aso_recebido_acao,
    api_empresa_vinculos_clinicas,
)
from api.views_postos_trabalho import (
    sst_postos_page,
    api_postos_trabalho,
    api_posto_detalhe,
    api_agentes_nocivos,
    api_agente_detalhe,
    api_posto_funcionarios,
    api_posto_xml_s2240,
)
from api.views_sst_rag import assistente_sst
# ── Módulos SST Expansão ──────────────────────────────────
from api.views_ppp import (
    api_ppp_lista, api_ppp_criar, api_ppp_detalhe,
    api_ppp_finalizar, api_ppp_pdf, api_ppp_kpis,
    api_ppp_preview, api_ppp_transmitir_esocial, api_ppp_status_esocial,
    sst_ppp_page,
)
from api.views_laudos_tecnicos import (
    api_laudos_lista, api_laudo_detalhe,
    api_laudo_assinar, api_laudo_pdf, api_laudos_kpis,
    sst_laudos_page,
)
from api.views_rede_credenciada import (
    api_rede_credenciada_busca, api_rede_credenciada_proximas,
    api_rede_credenciada_detalhe, api_rede_credenciar,
    api_rede_kpis_credenciada, api_rede_por_estado,
    sst_rede_credenciada_page,
)
from api.views_laboratorio import (
    api_laboratorios_lista, api_laboratorio_registrar,
    api_resultado_importar, api_resultado_lote_csv,
    api_resultados_empresa, api_resultados_funcionario,
    api_resultados_alertas, api_laboratorio_kpis,
    sst_laboratorio_page,
)
from api.views_financeiro_clinica import (
    api_faturas, api_fatura_detalhe, api_fatura_baixar,
    api_fatura_cancelar, api_fatura_pdf,
    api_despesas_clinica, api_glosas,
    api_financeiro_kpis_clinica, api_fluxo_caixa_clinica,
    sst_financeiro_clinica_page,
)
from api.views_fap import (
    api_fap_lista, api_fap_registrar, api_fap_detalhe,
    api_fap_simulacao, api_fap_contestacao,
    api_fap_historico, api_fap_kpis,
    sst_fap_page,
)
from api.views_pgr_pcmso import (
    api_pgr_gerar, api_pgr_pdf,
    api_pcmso_gerar, api_pcmso_pdf,
    sst_pgr_page,
)
from api.views_cipa import (
    api_cipa_comissoes, api_cipa_comissao_detalhe,
    api_cipa_membros, api_cipa_reunioes,
    api_cipa_reuniao_detalhe, api_cipa_ata_pdf,
    api_cipa_kpis,
    sst_cipa_page,
)
from api.views_biometria import (
    api_biometria_cadastrar, api_biometria_detalhe,
    api_biometria_confirmar_entrega, api_biometria_kpis,
    sst_biometria_page,
)
from api.views_biometria_facial import (
    api_biometria_cadastrar_facial,
    api_biometria_verificar_facial,
    api_biometria_confirmar_epi_facial,
    api_biometria_apagar_lgpd,
    api_biometria_status_facial,
)
from api.views_psicossocial import (
    api_psicossocial_avaliacoes, api_psicossocial_detalhe,
    api_psicossocial_ativar, api_psicossocial_questoes,
    api_psicossocial_responder_publico,
    api_psicossocial_resultados, api_psicossocial_pdf,
    api_psicossocial_kpis,
    sst_psicossocial_page,
)
from api.views_solicitacao_exame import (
    sst_solicitacoes_page,
    api_solicitacoes_exame,
    api_solicitacao_detalhe,
    api_clinicas_disponiveis,
    clinica_solicitacoes_page,
    api_clinica_solicitacoes,
    api_clinica_solicitacao_acao,
    api_link_resultado,
    clinica_resultado_page,
)
from api.views_gestao import (
    gestao_corporativa,
    gestao_plataforma,
    portal_ti_unificado,
    api_apoio_fila,
    api_apoio_atualizar,
    api_programas,
    api_programa_status,
    api_acoes,
    api_acao_status,
    api_gestao_resumo,
    api_trial_status,
    api_trial_ativar,
    api_onboarding_passo,
    api_integracoes,
    api_integracao_webhook,
    api_integracao_status,
    api_chaves,
    api_chave_revogar,
    api_uso_api,
    api_plataforma_webhooks,
    api_plataforma_seguranca,
    api_plataforma_logs,
    api_benchmark,
    api_dados_empresa,
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
    painel_grupos, api_criar_grupo, api_listar_salas_por_tipo, api_membros_grupo, api_editar_grupo,
)
from api.views_reuniao_sst import (
    sst_comunicacao_page, api_reunioes, api_reuniao_detalhe, api_funcionario_reunioes, api_reuniao_token,
)
from api.views_saude_ocupacional import (
    sst_saude_comunicacao_page,
    api_wellness_resumo, api_wellness_por_setor, api_wellness_alertas,
    api_conteudos_listar, api_conteudos_criar, api_conteudos_remover,
    api_conflitos_listar, api_conflito_atualizar, api_conflito_registrar,
    api_colab_conteudos, api_colab_conflito_registrar,
    api_colab_checkin_diario, api_colab_checkin_semanal,
)
from api.views_farmacia import api_farmacia_painel
from api.views_farmacia_gestao import (
    api_farmacia_dashboard,
    api_farmacia_estoque,
    api_farmacia_dispensacao,
    api_farmacia_fornecedores,
    api_farmacia_pedidos,
)
from api.views_farmacia_fase1 import (
    api_livro_controlado,
    api_lotes_bloqueio,
    api_farmacia_auditoria,
    api_farmacia_conformidade,
)
from api.views_farmacia_fase2 import (
    api_rede_farmacia_estoque,
    api_rede_farmacia_disponibilidade,
    api_rede_farmacia_transferencias,
    api_rede_farmacia_transferencia_acao,
    api_rede_farmacia_kpis,
)
from api.views_farmacia_fase3 import (
    api_verificar_interacoes,
    api_farmacia_previsao_demanda,
    api_farmacia_curva_abc,
    api_farmacia_ia_dashboard,
)
from api.views_hospital import api_hospital_painel
from api.views_hospital_dashboard import (
    api_hospital_dashboard,
    api_hospital_leitos,
    api_hospital_triagem,
    api_hospital_pacientes,
    api_hospital_prescricao,
)
from api.views_farmacia_ops import (
    api_fornecedores_farmacia, api_fornecedor_farmacia_detalhe,
    api_itens_farmacia, api_item_farmacia_detalhe,
    api_movimentos_estoque, api_dispensacoes_farmacia,
    api_pedidos_compra_farmacia, api_pedido_compra_status,
    api_farmacia_ops_kpis, api_farmacia_pdf_estoque, api_farmacia_pdf_dispensacoes,
)
from api.views_farmacia_pdv import (
    farmacia_pdv_page,
    api_pdv_sessao_atual,
    api_pdv_abrir_sessao,
    api_pdv_fechar_sessao,
    api_pdv_registrar_venda,
    api_pdv_historico,
)
from api.views_farmacia_pbm import (
    farmacia_pbm_page,
    api_pbm_convenios,
    api_pbm_convenio_detalhe,
    api_farmacia_popular_registros,
    api_farmacia_popular_kpis,
)
from api.views_farmacia_dre import (
    farmacia_financeiro_page,
    api_dre_lista,
    api_dre_salvar,
    api_dre_dashboard,
)
from api.views_farmacia_ecommerce import (
    farmacia_ecommerce_page,
    api_delivery_pedidos,
    api_delivery_novo,
    api_delivery_atualizar_status,
    api_delivery_kpis,
)
from api.views_farmacia_ifood import (
    api_ifood_config,
    api_ifood_webhook,
)
from api.views_farmacia_relatorio_ia import (
    api_farmacia_relatorio_ia,
)
from api.views_hospital_fase3 import (
    api_fatura_paciente,
    api_fatura_acao,
    api_itens_faturamento,
    api_item_faturamento_detalhe,
    api_faturamento_dashboard,
    api_hospital_analytics,
)
from api.views_hospital_fase2 import (
    api_pedidos_exame,
    api_pedido_exame_detalhe,
    api_resultados_exame,
    api_resultado_visualizar,
    api_resultado_arquivo,
    api_administracoes,
    api_exames_dashboard,
)
from api.views_hospital_fase1 import (
    api_evolucoes_paciente,
    api_monitoramento_uti,
    api_sumario_alta,
    api_centro_cirurgico,
    api_centro_cirurgico_detalhe,
    api_hospital_uti_dashboard,
    api_isolamento_paciente,
)
from api.views_hospital_multi import (
    api_avaliacoes_enfermagem,
    api_avaliacoes_fisioterapia,
    api_avaliacoes_nutricionais,
)
from api.views_hospital_visitantes import (
    api_visitantes_paciente,
    api_visitante_saida,
)
from api.views_hospital_obito import (
    api_declaracoes_obito,
)
from api.views_hospital_equipamentos import (
    api_equipamentos_medicos,
    api_manutencoes_equipamento,
    api_manutencao_concluir,
)
from api.views_hospital_dose_unitaria import (
    api_dose_unitaria_paciente,
    api_dose_unitaria_status,
)
from api.views_hospital_limpeza import (
    api_limpeza_leito,
    api_limpeza_status,
    api_rouparia,
)
from api.views_hospital_ops import (
    api_departamentos_hospital, api_departamento_hospital_detalhe,
    api_leitos_hospital, api_leito_status,
    api_pacientes_hospital, api_triagens_hospital,
    api_internacoes_hospital, api_internacao_status,
    api_evolucoes_internacao, api_hospital_ops_kpis, api_hospital_contexto_integrado,
    api_hospital_pdf_internacoes, api_hospital_pdf_ficha_internacao,
)
from api.views_hospital_prontuario import (
    hospital_prontuario_page,
    api_prontuario_hospitalar,
    api_prontuario_hospitalar_detalhe,
    api_prontuario_evolucoes,
    api_prontuario_prescricoes,
)
from api.views_hospital_cirurgia import (
    hospital_cirurgia_page,
    api_cirurgia,
    api_cirurgia_agenda,
    api_cirurgia_atualizar,
    api_cirurgia_kpis,
)
from api.views_hospital_farmacia import (
    hospital_farmacia_page,
    api_farmacia_hosp,
    api_farmacia_hosp_atualizar_estoque,
    api_farmacia_hosp_kpis,
)
from api.views_hospital_lis import (
    hospital_lis_page,
    api_lis,
    api_lis_resultado,
    api_lis_kpis,
)
from api.views_hospital_imagem import (
    hospital_imagem_page,
    api_ris,
    api_ris_laudar,
    api_ris_kpis,
    api_ris_dicom,
    api_ris_dicom_arquivo,
)
from api.views_hospital_tiss import (
    hospital_tiss_page,
    api_tiss,
    api_tiss_atualizar_status,
    api_tiss_kpis,
    api_tiss_gerar_xml,
)
from api.views_governo_ops import (
    api_programas_gov, api_programa_gov_detalhe,
    api_indicadores_gov, api_indicador_gov_detalhe,
    api_orcamentos_gov, api_planos_acao_gov, api_plano_acao_gov_detalhe,
    api_governo_ops_kpis, api_governo_pdf_relatorio,
)
from api.views_governo_fase2 import (
    api_unidades_saude, api_unidade_saude_detalhe, api_equipes_saude,
    api_notificacoes, api_surtos, api_surto_detalhe, api_vigilancia_dashboard,
    api_regulacao_leitos, api_regulacao_detalhe, api_regulacao_dashboard,
    api_producao_ambulatorial, api_producao_dashboard,
    api_metas_previne, api_previne_dashboard,
    api_contratos_gestao, api_contrato_detalhe,
    api_atendimentos_urgencia, api_urgencia_dashboard,
    api_governo_fase2_dashboard,
    api_governo_plataforma_integracoes, api_governo_plataforma_chaves,
    api_governo_plataforma_webhooks, api_governo_plataforma_seguranca,
    api_governo_plataforma_logs,
)
from api.views_governo_pec import (
    governo_pec_page,
    api_pec_kpis,
    api_pec_lista,
    api_pec_novo,
    api_pec_detalhe,
    api_pec_atendimentos,
)
from api.views_governo_farmacia_basica import (
    governo_farmacia_basica_page,
    api_farmacia_basica_kpis,
    api_farmacia_basica_itens,
    api_farmacia_basica_dispensar,
    api_farmacia_basica_dispensacoes,
)
from api.views_governo_regulacao import (
    governo_regulacao_page,
    api_regulacao_kpis,
    api_regulacao_lista,
    api_regulacao_nova,
    api_regulacao_atualizar,
)
from api.views_governo_faturamento import (
    governo_faturamento_sus_page,
    api_faturamento_sus_kpis,
    api_faturamento_sus_lotes,
    api_faturamento_sus_transmitir,
)
from api.views_governo_teleconsulta import (
    governo_teleconsulta_page,
    api_teleconsulta_kpis,
    api_teleconsulta_lista,
    api_teleconsulta_agendar,
    api_teleconsulta_atualizar,
)
from api.views_governo_rag import (
    governo_rag_page,
    api_rag_kpis,
    api_rag_lista,
    api_rag_criar,
    api_rag_atualizar,
)
from api.views_governo_esus import (
    governo_esus_page,
    api_esus_status,
    api_esus_logs,
    api_esus_enviar_fichas,
)
from api.views_governo_sigtap import (
    api_sigtap_buscar,
    api_sigtap_detalhe,
    api_sigtap_validar,
    api_sigtap_validar_bpa,
    api_sigtap_grupos,
    api_sigtap_kpis,
)
from api.views_governo_caps import (
    api_caps_unidades,
    api_caps_unidade_detalhe,
    api_caps_atendimentos,
    api_caps_encaminhamentos,
    api_caps_encaminhamento_acao,
    api_caps_kpis,
    api_caps_raas_exportar,
)
from api.views_hospital_rnds import (
    api_hospital_rnds_status,
    api_hospital_rnds_transmissoes,
    api_hospital_rnds_transmitir_alta,
    api_hospital_rnds_transmitir_rac,
    api_hospital_rnds_reprocessar,
    api_hospital_rnds_kpis,
)
from api.views_farmacia_magistral import (
    api_magistral_materias_primas,
    api_magistral_lotes_mp,
    api_magistral_lote_aprovar,
    api_magistral_formulas,
    api_magistral_ordens,
    api_magistral_ordem_status,
    api_magistral_controle_qualidade,
    api_magistral_kpis,
    farmacia_magistral_page,
)
from api.views_hospital_opme import (
    api_opme_catalogo,
    api_opme_catalogo_detalhe,
    api_opme_autorizacoes,
    api_opme_autorizacao_acao,
    api_opme_implantaveis,
    api_opme_kpis,
)
from api.views_governo_odontologia import (
    api_ceo_atendimentos,
    api_ceo_atendimento_detalhe,
    api_ceo_producao,
    api_ceo_fechar_producao,
    api_ceo_transmitir,
    api_ceo_bpa_download,
    api_ceo_procedimentos,
    api_ceo_kpis,
)
from api.views_hospital_ccih import (
    api_ccih_infeccoes,
    api_ccih_infeccao_detalhe,
    api_ccih_isolamentos,
    api_ccih_isolamento_encerrar,
    api_ccih_indicadores,
    api_ccih_kpis,
)
from api.views_governo_ceaf import (
    api_ceaf_medicamentos,
    api_ceaf_solicitacoes,
    api_ceaf_solicitacao_detalhe,
    api_ceaf_dispensar,
    api_ceaf_horus_enviar,
    api_ceaf_kpis,
)
from api.views_plano_portabilidade import (
    api_portabilidade_lista,
    api_portabilidade_detalhe,
    api_portabilidade_acao,
    api_portabilidade_declaracao,
    api_portabilidade_kpis,
)
from api.views_sst_ntep import (
    api_ntep_tabela,
    api_ntep_verificar,
    api_ntep_alertas,
    api_ntep_alerta_detalhe,
    api_ntep_scan_cats,
    api_ntep_kpis,
)
from api.views_hospital_obstetrico import (
    api_obstetrico_partogramas,
    api_obstetrico_partograma_detalhe,
    api_obstetrico_partos,
    api_obstetrico_parto_detalhe,
    api_obstetrico_dnv,
    api_obstetrico_kpis,
)
from api.views_governo_sipni import (
    api_sipni_status,
    api_sipni_historico,
    api_sipni_transmitir,
    api_sipni_reprocessar,
    api_sipni_kpis,
)
from api.views_hospital_assinatura import (
    api_assinatura_pendentes,
    api_assinatura_assinar,
    api_assinatura_assinar_lote,
    api_assinatura_verificar,
    api_assinatura_kpis,
)
from api.views_governo_cnes import (
    api_cnes_buscar,
    api_cnes_detalhe,
    api_cnes_sincronizar,
    api_cnes_sincronizar_todas,
    api_cnes_status,
    api_cnes_kpis,
)
from api.views_hospital_hemoterapia import (
    api_hemo_bolsas,
    api_hemo_bolsa_detalhe,
    api_hemo_solicitacoes,
    api_hemo_transfusoes,
    api_hemo_reacoes,
    api_hemo_notificar_anvisa,
    api_hemo_notivisa_download,
    api_hemo_kpis,
)
from api.views_hospital_oncologia import (
    api_onco_protocolos,
    api_onco_ciclos,
    api_onco_ciclo_detalhe,
    api_onco_toxicidade,
    api_onco_apacs,
    api_onco_apac_detalhe,
    api_onco_kpis,
)
from api.views_plano_tuss import (
    api_tuss_procedimentos,
    api_rol_coberturas,
    api_tuss_diretrizes,
    api_tuss_verificar_cobertura,
    api_nip_lista,
    api_nip_detalhe,
    api_nip_responder,
    api_tuss_kpis,
)
from api.views_governo_acs import (
    api_acs_lista,
    api_acs_detalhe,
    api_visitas_lista,
    api_visita_detalhe,
    api_visitas_transmitir_esus,
    api_visitas_exportar_cds,
    api_fichas_acompanhamento,
    api_ficha_detalhe,
    api_acs_kpis,
)
from api.views_governo_endemias import (
    api_endemias_visitas,
    api_endemias_indicadores,
)
from api.views_governo_vigilancia_sanitaria import (
    api_vigsan_estabelecimentos,
    api_vigsan_alvaras,
    api_vigsan_inspecoes,
)
from api.views_rede import (
    api_redes, api_rede_convidar, api_rede_entrar, api_rede_estoque, api_rede_item_disponibilidade,
    api_transferencias, api_transferencia_detalhe,
    api_mensagens_rede, api_mensagem_marcar_lida,
    api_planos_saude, api_plano_saude_detalhe,
    api_beneficiarios, api_beneficiario_detalhe,
    api_guias, api_guia_detalhe, api_plano_kpis,
    api_carencias, api_carencia_detalhe, api_portabilidade,
)
from api.views_plano_corretores import (
    plano_corretores_page,
    api_corretoras_lista,
    api_corretora_detalhe,
    api_corretora_comissoes,
    api_corretoras_kpis,
)
from api.views_plano_rede import (
    plano_rede_page,
    api_plano_rede_lista,
    api_plano_rede_novo,
    api_plano_rede_detalhe,
    api_plano_rede_kpis,
)
from api.views_plano_ans import (
    plano_ans_page,
    api_diops_lista,
    api_diops_detalhe,
    api_diops_gerar_xml,
    api_sib_lista,
    api_sib_detalhe,
    api_sib_transmitir,
    api_ans_kpis,
)
from api.views_diops_real import (
    api_diops_gerar_real,
    api_diops_download_xml,
    api_diops_transmitir_ans,
)
from api.views_plano_ia import (
    plano_ia_page,
    api_ia_autorizacoes,
    api_ia_analisar,
    api_ia_revisar,
    api_ia_kpis,
)
from api.views_ia_autorizacao_ml import (
    api_ia_analisar_ml,
    api_ia_retreinar,
    api_ia_modelo_info,
)
from api.views_sngpc_transmissao import (
    api_sngpc_gerar_xml,
    api_sngpc_transmitir,
    api_sngpc_download,
    farmacia_sngpc_page,
)
from api.views_credenciais import (
    api_credenciais_status,
    api_credenciais_sngpc_salvar,
    api_credenciais_testar_sngpc,
    api_credenciais_ans_salvar,
    api_credenciais_ans_testar,
    api_credenciais_sus_salvar,
    api_credenciais_sus_testar,
    api_credenciais_rnds_salvar,
    api_credenciais_rnds_testar,
    api_credenciais_nfe_salvar,
    api_credenciais_nfe_testar,
    api_credenciais_revogar,
)
from api.views_nfe import (
    api_nfe_status,
    api_nfe_lista,
    api_nfe_emitir,
    api_nfe_xml_download,
)
from api.views_plano_portal import (
    plano_portal_admin_page,
    api_portal_beneficiarios_lista,
    api_portal_token_gerar,
    plano_portal_beneficiario_page,
)
from api.epidemiologia import panorama_epidemiologico, exportar_briefing_governo
from api.fontes_oficiais_brasil import api_brasil_fontes_oficiais
from api.governanca import api_auditoria_institucional, api_matriz_decisao, api_metodologia_epidemiologica

# 🔥 IMPORT CORRETO (APENAS UM)
from api.views_pagamento import (
    api_billing_status,
    api_enterprise_readiness,
    criar_pagamento,
    webhook,
    sucesso,
    erro,
    pendente,
    status_pagamento,
    planos_publicos,
    api_plano_features,
)
from api.views_upgrade import api_upgrade_opcoes, api_upgrade_checkout
from api.views_white_label import api_marca, api_marca_publica
from api.views_whatsapp import api_whatsapp, api_whatsapp_testar, api_whatsapp_enviar, api_whatsapp_logs
from api.views_relatorios import (
    relatorio_pdf_funcionarios,
    relatorio_pdf_asos,
    relatorio_pdf_cats,
    relatorio_pdf_treinamentos,
)
from api.views_platform import platform_status, sla_page, status_page
from api.views_funcionario_portal import (
    funcionario_login, funcionario_registrar, funcionario_buscar_cpf, funcionario_dashboard,
    funcionario_meu_perfil, funcionario_meus_asos,
    funcionario_meus_treinamentos, funcionario_meus_epis, funcionario_minhas_solicitacoes,
    funcionario_notificacoes, funcionario_notificacao_lida,
    funcionario_notificacoes_limpar_lidas,
    funcionario_salvar_fcm_token,
    funcionario_comunicados, funcionario_comunicado_lido,
    funcionario_psicossocial_ativa, funcionario_epis_pendentes,
    funcionario_meus_afastamentos, funcionario_minha_biometria,
)

from api.views_bem_estar import (
    api_funcionario_checkin,
    api_empresa_bem_estar_resumo,
    api_empresa_bem_estar_contato_resolvido,
)
from api.views_assinatura_sst import (
    api_sst_assinaturas,
    api_sst_assinatura_detalhe,
    pagina_assinatura_sst,
    pagina_validar_assinatura,
    api_public_validar_assinatura_sst,
    api_public_assinar_sst,
)


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
    path('sla/', sla_page),
    path('status/', status_page),
    path('api/platform/status', platform_status),
    path('login-empresa/', tela_login_empresa),
    path('login-governo/', tela_login_governo),
    path('operacao-central/', login_operacao),
    path('api/login', login_empresa),
    path('api/login-empresa', login_portal_empresa),
    path('api/login-empresa-api', login_portal_empresa),  # alias for mobile app
    path('api/login-governo', login_portal_governo),
    path('api/sessao/aba', ativar_sessao_aba),
    path('api/trial/ativar', ativar_trial),
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
    path('dashboard-plano-saude/', dashboard_plano_saude),
    # Aliases com slug mais curto
    path('farmacia/', dashboard_farmacia),
    path('hospital/', dashboard_hospital),
    path('governo/', dashboard_governo),
    path('plano-saude/', dashboard_plano_saude),
    # Gestão operacional
    path('farmacia/gestao/', farmacia_gestao_page),
    path('farmacia/pdv/', farmacia_pdv_page),
    path('farmacia/pbm/', farmacia_pbm_page),
    path('farmacia/financeiro/', farmacia_financeiro_page),
    path('farmacia/delivery/', farmacia_ecommerce_page),
    path('farmacia/magistral/', farmacia_magistral_page),
    path('farmacia/sngpc/', farmacia_sngpc_page),
    path('hospital/gestao/', hospital_gestao_page),
    path('hospital/prontuario/', hospital_prontuario_page),
    path('hospital/cirurgia/', hospital_cirurgia_page),
    path('hospital/lis/', hospital_lis_page),
    path('hospital/imagem/', hospital_imagem_page),
    path('hospital/farmacia-hospitalar/', hospital_farmacia_page),
    path('hospital/faturamento-tiss/', hospital_tiss_page),
    path('governo/gestao/', governo_gestao_page),
    path('governo/pec/', governo_pec_page),
    path('governo/farmacia-basica/', governo_farmacia_basica_page),
    path('governo/regulacao/', governo_regulacao_page),
    path('governo/regulacao-assistencial/', governo_regulacao_page),
    path('governo/faturamento-sus/', governo_faturamento_sus_page),
    path('governo/teleconsulta/', governo_teleconsulta_page),
    path('governo/rag/', governo_rag_page),
    path('governo/esus/', governo_esus_page),
    path('governo/plataforma/', governo_plataforma_page),
    path('governo/ti/', governo_plataforma_page),
    path('governo/TI/', governo_plataforma_page),
    path('rede/gestao/', rede_gestao_page),
    path('plano-saude/gestao/', plano_saude_gestao_page),
    path('plano-saude/corretores/', plano_corretores_page),
    path('plano-saude/rede/', plano_rede_page),
    path('plano-saude/ans/', plano_ans_page),
    path('plano-saude/ia/', plano_ia_page),
    path('plano-saude/portal-admin/', plano_portal_admin_page),
    path('plano-saude/portal/<str:token>/', plano_portal_beneficiario_page),
    path('ti/', portal_ti_unificado),
    path('TI/', portal_ti_unificado),
    path('rh/', portal_rh_page),
    path('RH/', portal_rh_page),
    path('gerencia/', gerencia_executiva_page),
    path('sala-decisao-ia/', command_ai),
    path('command-ai/', command_ai),
    path('contrato-governo/', contrato_governo),
    path('licencas/', licencas),
    path('seguranca/', seguranca),
    path('usuarios/', usuarios_empresa),
    path('console-operacional/', console_operacional),
    path('centro-operacoes/', console_operacional),

    # 💬 COMUNICAÇÃO — Teams-like
    path('sst/saude-comunicacao/', sst_saude_comunicacao_page),
    path('api/sst/wellness/resumo/', api_wellness_resumo),
    path('api/sst/wellness/setores/', api_wellness_por_setor),
    path('api/sst/wellness/alertas/', api_wellness_alertas),
    path('api/sst/conteudos/', api_conteudos_listar),
    path('api/sst/conteudos/criar/', api_conteudos_criar),
    path('api/sst/conteudos/<int:conteudo_id>/remover/', api_conteudos_remover),
    path('api/sst/conflitos/', api_conflitos_listar),
    path('api/sst/conflitos/registrar/', api_conflito_registrar),
    path('api/sst/conflitos/<int:conflito_id>/atualizar/', api_conflito_atualizar),
    path('api/colab/<str:codigo>/conteudos/', api_colab_conteudos),
    path('api/colab/<str:codigo>/conflito/', api_colab_conflito_registrar),
    path('api/colab/<str:codigo>/checkin-diario/', api_colab_checkin_diario),
    path('api/colab/<str:codigo>/checkin-semanal/', api_colab_checkin_semanal),
    path('sst/comunicacao/', sst_comunicacao_page),
    path('sst/comunicacao/legado/', painel_comunicacao),
    path('sst/video/<int:sessao_id>/', sala_video_empresa),
    path('api/comunicacao/salas/', api_listar_salas_por_tipo),
    path('api/comunicacao/salas/criar/', api_criar_sala),
    path('api/comunicacao/colaboradores/', api_colaboradores_comunicacao),
    path('api/comunicacao/sala/<int:sala_id>/mensagens/', api_mensagens),
    path('api/comunicacao/sala/<int:sala_id>/enviar/', api_enviar_mensagem),
    path('api/comunicacao/sala/<int:sala_id>/lida/', api_marcar_lida),
    path('api/comunicacao/video/criar/', api_criar_video),
    path('api/comunicacao/video/<int:sessao_id>/encerrar/', api_encerrar_video),
    path('api/sst/reunioes/', api_reunioes),
    path('api/sst/reunioes/<int:reuniao_id>/', api_reuniao_detalhe),
    path('api/sst/reunioes/<int:reuniao_id>/token/', api_reuniao_token),
    path('api/funcionario/reunioes', api_funcionario_reunioes),
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
    path('gestao/plataforma/', gestao_plataforma),
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
    # SOC2 / ISO
    path('api/compliance/soc2/controles/', api_soc2_controles),
    path('api/compliance/soc2/controles', api_soc2_controles),
    path('api/compliance/soc2/controles/<int:controle_id>/evidencias/', api_soc2_evidencias),
    path('api/compliance/soc2/controles/<int:controle_id>/evidencias', api_soc2_evidencias),
    # RBAC
    path('api/rbac/permissoes/', api_rbac_permissoes),
    path('api/rbac/permissoes', api_rbac_permissoes),
    path('api/rbac/atribuir/', api_rbac_atribuir),
    path('api/rbac/atribuir', api_rbac_atribuir),
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
    path('sst/solicitacoes/', sst_solicitacoes_page),
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
    path('sst/bem-estar/', sst_bem_estar_page),
    path('sst/riscos/', sst_riscos_page),
    path('sst/postos/', sst_postos_page),
    path('sst/comunicacao/grupos/', painel_grupos),
    # 🏥 SST / Saúde Ocupacional — API
    path('api/sst/dashboard', api_sst_dashboard),
    path('api/sst/contexto-integrado', api_sst_contexto_integrado),
    path('api/sst/contexto-integrado/', api_sst_contexto_integrado),
    path('api/sst/funcionarios', api_funcionarios),
    path('api/sst/funcionarios/', api_funcionarios),
    path('api/sst/funcionarios/<int:funcionario_id>', api_funcionario_detalhe),
    path('api/sst/funcionarios/<int:funcionario_id>/', api_funcionario_detalhe),
    path('api/sst/asos', api_asos),
    path('api/sst/solicitacoes-exame', api_solicitacoes_exame),
    path('api/sst/solicitacoes-exame/', api_solicitacoes_exame),
    path('api/sst/solicitacoes-exame/<int:sol_id>', api_solicitacao_detalhe),
    path('api/sst/solicitacoes-exame/<int:sol_id>/', api_solicitacao_detalhe),
    path('api/sst/solicitacoes-exame/<int:sol_id>/link-resultado', api_link_resultado),
    path('api/sst/solicitacoes-exame/<int:sol_id>/link-resultado/', api_link_resultado),
    path('clinica/resultado/<int:sol_id>/<str:token>/', clinica_resultado_page),
    path('clinica/resultado/<int:sol_id>/<str:token>', clinica_resultado_page),
    path('api/sst/clinicas-disponiveis', api_clinicas_disponiveis),
    path('api/sst/clinicas-disponiveis/', api_clinicas_disponiveis),
    path('api/sst/cats', api_cats),
    path('api/sst/cids-ocupacionais', api_sst_cids_ocupacionais),
    path('api/sst/cids-ocupacionais/', api_sst_cids_ocupacionais),
    path('api/sst/documentos', api_documentos_sst),
    path('api/sst/afastamentos', api_afastamentos_sst),
    path('api/sst/afastamentos/<int:afastamento_id>/retorno', api_afastamento_retorno),
    path('api/sst/afastamentos/<int:afastamento_id>/retorno/', api_afastamento_retorno),
    path('api/sst/exames', api_exames),
    path('api/sst/esocial', api_esocial_eventos_legacy),
    path('api/sst/relatorios', api_relatorios_sst),
    path('api/sst/funcionarios/<int:funcionario_id>/prontuario', api_prontuario_funcionario),
    path('api/sst/funcionarios/<int:funcionario_id>/convidar-app', api_convidar_app_funcionario),
    path('api/sst/treinamentos', api_treinamentos),
    path('api/sst/treinamentos/resumo', api_treinamentos_resumo),
    path('api/sst/configuracoes', api_sst_configuracoes),
    path('api/sst/configuracoes/', api_sst_configuracoes),
    path('api/sst/mensagem-massa', api_sst_mensagem_massa),
    path('api/sst/mensagem-massa/', api_sst_mensagem_massa),
    path('api/sst/epis/catalogo', api_epis_catalogo),
    path('api/sst/epis/catalogo/', api_epis_catalogo),
    path('api/sst/epis/catalogo/lote', api_epis_catalogo_lote),
    path('api/sst/epis/catalogo/lote/', api_epis_catalogo_lote),
    path('api/sst/epis/catalogo/<int:epi_id>/', api_epis_catalogo_detail),
    path('api/sst/epis/catalogo/<int:epi_id>', api_epis_catalogo_detail),
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
    # Postos de Trabalho / S-2240
    path('api/sst/postos', api_postos_trabalho),
    path('api/sst/postos/', api_postos_trabalho),
    path('api/sst/postos/<int:posto_id>', api_posto_detalhe),
    path('api/sst/postos/<int:posto_id>/agentes', api_agentes_nocivos),
    path('api/sst/postos/<int:posto_id>/agentes/<int:agente_id>', api_agente_detalhe),
    path('api/sst/postos/<int:posto_id>/funcionarios', api_posto_funcionarios),
    path('api/sst/postos/<int:posto_id>/xml-s2240', api_posto_xml_s2240),
    # Riscos ocupacionais / PGR
    path('api/sst/bem-estar/resumo', api_empresa_bem_estar_resumo),
    path('api/sst/bem-estar/<int:checkin_id>/resolvido', api_empresa_bem_estar_contato_resolvido),
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
    # ── PPP ──────────────────────────────────────────────────
    path('api/sst/ppp/', api_ppp_lista),
    path('api/sst/ppp/kpis/', api_ppp_kpis),
    path('api/sst/ppp/preview/<int:funcionario_id>/', api_ppp_preview),
    path('api/sst/ppp/<int:ppp_id>/', api_ppp_detalhe),
    path('api/sst/ppp/<int:ppp_id>/finalizar/', api_ppp_finalizar),
    path('api/sst/ppp/<int:ppp_id>/pdf/', api_ppp_pdf),
    path('api/sst/ppp/<int:ppp_id>/transmitir-esocial/', api_ppp_transmitir_esocial),
    path('api/sst/ppp/<int:ppp_id>/status-esocial/', api_ppp_status_esocial),
    # ── Laudos Técnicos (LTCAT / LIP / PGR / PCMSO) ─────────
    path('api/sst/laudos/', api_laudos_lista),
    path('api/sst/laudos/kpis/', api_laudos_kpis),
    path('api/sst/laudos/<int:laudo_id>/', api_laudo_detalhe),
    path('api/sst/laudos/<int:laudo_id>/assinar/', api_laudo_assinar),
    path('api/sst/laudos/<int:laudo_id>/pdf/', api_laudo_pdf),
    # ── Rede Credenciada ──────────────────────────────────────
    path('api/sst/rede-credenciada/', api_rede_credenciada_busca),
    path('api/sst/rede-credenciada/kpis/', api_rede_kpis_credenciada),
    path('api/sst/rede-credenciada/proximas/', api_rede_credenciada_proximas),
    path('api/sst/rede-credenciada/por-estado/', api_rede_por_estado),
    path('api/sst/rede-credenciada/credenciar/', api_rede_credenciar),
    path('api/sst/rede-credenciada/<int:clinica_id>/', api_rede_credenciada_detalhe),
    # ── Laboratórios ─────────────────────────────────────────
    path('api/sst/laboratorios/', api_laboratorios_lista),
    path('api/sst/laboratorios/registrar/', api_laboratorio_registrar),
    path('api/sst/laboratorios/kpis/', api_laboratorio_kpis),
    path('api/sst/laboratorios/resultados/', api_resultados_empresa),
    path('api/sst/laboratorios/resultados/alertas/', api_resultados_alertas),
    path('api/sst/laboratorios/resultados/funcionario/<int:funcionario_id>/', api_resultados_funcionario),
    path('api/sst/laboratorios/resultado/', api_resultado_importar),
    path('api/sst/laboratorios/resultado/lote/', api_resultado_lote_csv),
    # ── Financeiro Clínica ────────────────────────────────────
    path('api/clinica/financeiro/faturas/', api_faturas),
    path('api/clinica/financeiro/faturas/<int:fatura_id>/', api_fatura_detalhe),
    path('api/clinica/financeiro/faturas/<int:fatura_id>/baixar/', api_fatura_baixar),
    path('api/clinica/financeiro/faturas/<int:fatura_id>/cancelar/', api_fatura_cancelar),
    path('api/clinica/financeiro/faturas/<int:fatura_id>/pdf/', api_fatura_pdf),
    path('api/clinica/financeiro/despesas/', api_despesas_clinica),
    path('api/clinica/financeiro/glosas/', api_glosas),
    path('api/clinica/financeiro/kpis/', api_financeiro_kpis_clinica),
    path('api/clinica/financeiro/fluxo-caixa/', api_fluxo_caixa_clinica),
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
    # (solicitacoes-exame registradas acima em bloco único, removidas duplicatas)
    path('api/clinica/solicitacoes/', api_clinica_solicitacoes),
    path('api/clinica/solicitacoes', api_clinica_solicitacoes),
    path('api/clinica/solicitacoes/<int:sol_id>/', api_clinica_solicitacao_acao),
    path('api/clinica/solicitacoes/<int:sol_id>', api_clinica_solicitacao_acao),
    # ── eSocial SST ──────────────────────────────────────────────────────────
    path('api/sst/esocial/eventos/', api_esocial_eventos_sst),
    path('api/sst/esocial/eventos', api_esocial_eventos_sst),
    path('api/sst/esocial/kpis/', api_esocial_kpis),
    path('api/sst/esocial/eventos/<int:evento_id>/xml/', api_esocial_gerar_xml),
    path('api/sst/esocial/eventos/<int:evento_id>/transmitir/', api_esocial_transmitir),
    path('api/sst/esocial/eventos/<int:evento_id>/aprovar/',    api_esocial_aprovar),
    path('api/sst/esocial/transmitir-pendentes/', api_esocial_transmitir_pendentes),
    path('api/sst/esocial/certificado/', api_esocial_certificado),
    path('api/sst/esocial/diagnostico/', api_esocial_diagnostico),
    path('api/sst/esocial/eventos/<int:evento_id>/transmitido/', api_esocial_marcar_transmitido),
    path('api/sst/cats/<int:cat_id>/esocial/', api_esocial_registrar_cat),
    path('api/sst/asos/<int:aso_id>/esocial/', api_esocial_registrar_aso),
    # ── eSocial S-2245 (Treinamentos NR) ─────────────────────────────────────
    path('api/sst/esocial/s2245/', api_esocial_s2245_listar),
    path('api/sst/esocial/s2245/lote/', api_esocial_s2245_lote),
    path('api/sst/esocial/s2245/<int:treinamento_id>/gerar/', api_esocial_s2245_gerar),
    path('api/sst/esocial/s2245/<int:evento_id>/transmitir/', api_esocial_s2245_transmitir),
    path('api/sst/esocial/s2245/<int:evento_id>/xml/', api_esocial_s2245_xml),
    path('api/sst/afastamentos/<int:afastamento_id>/esocial/', api_esocial_registrar_afastamento),
    # ── Compartilhamento de ASO ───────────────────────────────────────────────
    path('api/sst/asos/<int:aso_id>/compartilhar/', api_aso_compartilhamentos),
    path('api/sst/aso/compartilhamento/<str:token>/revogar/', api_aso_revogar_compartilhamento),
    path('sst/aso/portal/<str:token>/', portal_aso_publico),
    path('api/sst/asos/<int:aso_id>/pdf', api_aso_pdf),
    path('api/sst/cats/<int:cat_id>/pdf', api_cat_pdf),
    path('api/sst/funcionarios/<int:funcionario_id>/prontuario/pdf', api_prontuario_pdf),
    path('api/clinica/solicitacoes-exame', api_clinica_solicitacoes),
    path('api/clinica/solicitacoes-exame/', api_clinica_solicitacoes),
    path('api/clinica/solicitacoes-exame/<int:sol_id>/acao', api_clinica_solicitacao_acao),
    path('api/clinica/solicitacoes-exame/<int:sol_id>/acao/', api_clinica_solicitacao_acao),
    # grupos de chat
    path('api/comunicacao/grupos/', api_criar_grupo),
    path('api/comunicacao/grupos/criar/', api_criar_grupo),
    path('api/comunicacao/salas/filtro/', api_listar_salas_por_tipo),
    path('api/comunicacao/grupos/<int:sala_id>/membros/', api_membros_grupo),
    path('api/comunicacao/grupos/<int:sala_id>/', api_editar_grupo),
    path('api/comunicacao/grupos/<int:sala_id>', api_editar_grupo),

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
    path('api/corporativo/rh/resumo/', api_corporativo_rh_resumo),
    path('api/corporativo/rh/sincronizar/', api_corporativo_rh_sincronizar),
    path('api/public/resumo', app_resumo_publico),
    path('api/public/radar-local', app_radar_local),
    path('api/public/mapa', app_mapa_publico),
    path('api/public/vigilancia-resumo', app_vigilancia_resumo),
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
    path('api/usuarios/credencial-ti', api_criar_credencial_ti),
    path('api/usuarios/desativar', api_desativar_usuario_empresa),
    path('api/operacao-central/resumo', api_dono_resumo),
    path('api/operacao-central/financeiro-real', api_dono_financeiro_real),
    path('api/operacao-central/saude', api_dono_saude),
    path('api/operacao-central/app-funcionario', api_dono_app_funcionario),
    path('api/operacao-central/operadores', api_dono_operadores),
    path('api/operacao-central/operador/acao', api_dono_operador_acao),
    path('api/operacao-central/cliente/atualizar', api_dono_atualizar_cliente),
    path('api/operacao-central/cliente/cortesia', api_dono_cortesia_plano),
    path('api/operacao-central/cliente/excluir', api_dono_excluir_cliente),
    path('api/operacao-central/cliente/reset-trial', api_dono_reset_trial),
    path('api/operacao-central/cliente/forcar-logout', api_dono_forcar_logout),
    path('api/operacao-central/financeiro/acao', api_dono_financeiro_acao),
    path('api/operacao-central/onboarding/acao', api_dono_onboarding_acao),
    path('api/operacao-central/exportar', api_dono_exportar),
    path('api/operacao-central/auditoria', api_dono_auditoria),
    path('api/farmacia/painel', api_farmacia_painel),
    # ── Farmácia Gestão (módulo completo) ────────────────────────
    path('api/farmacia/dashboard', api_farmacia_dashboard),
    path('api/farmacia/dashboard/', api_farmacia_dashboard),
    path('api/farmacia/estoque', api_farmacia_estoque),
    path('api/farmacia/estoque/', api_farmacia_estoque),
    path('api/farmacia/dispensacao', api_farmacia_dispensacao),
    path('api/farmacia/dispensacao/', api_farmacia_dispensacao),
    path('api/farmacia/fornecedores-gestao', api_farmacia_fornecedores),
    path('api/farmacia/fornecedores-gestao/', api_farmacia_fornecedores),
    path('api/farmacia/pedidos-gestao', api_farmacia_pedidos),
    path('api/farmacia/pedidos-gestao/', api_farmacia_pedidos),
    # ── Farmácia PDV / Caixa ──────────────────────────────────
    path('api/farmacia/pdv/sessao-atual', api_pdv_sessao_atual),
    path('api/farmacia/pdv/abrir-sessao', api_pdv_abrir_sessao),
    path('api/farmacia/pdv/fechar-sessao/<int:sessao_id>', api_pdv_fechar_sessao),
    path('api/farmacia/pdv/venda/<int:sessao_id>', api_pdv_registrar_venda),
    path('api/farmacia/pdv/historico', api_pdv_historico),
    # ── Farmácia PBM / Convênios ──────────────────────────────────
    path('api/farmacia/pbm/convenios', api_pbm_convenios),
    path('api/farmacia/pbm/convenios/<int:conv_id>', api_pbm_convenio_detalhe),
    path('api/farmacia/pbm/farmacia-popular', api_farmacia_popular_registros),
    path('api/farmacia/pbm/kpis', api_farmacia_popular_kpis),
    # ── Farmácia DRE / Financeiro ──────────────────────────────────
    path('api/farmacia/dre/lista', api_dre_lista),
    path('api/farmacia/dre/salvar', api_dre_salvar),
    path('api/farmacia/dre/dashboard', api_dre_dashboard),
    # ── Farmácia Delivery / E-commerce ──────────────────────────────────
    path('api/farmacia/delivery/pedidos', api_delivery_pedidos),
    path('api/farmacia/delivery/novo', api_delivery_novo),
    path('api/farmacia/delivery/<int:pedido_id>/status', api_delivery_atualizar_status),
    path('api/farmacia/delivery/kpis', api_delivery_kpis),
    path('api/farmacia/ifood/config', api_ifood_config),
    path('api/farmacia/ifood/config/', api_ifood_config),
    path('api/farmacia/ifood/webhook/', api_ifood_webhook),
    path('api/farmacia/relatorio-ia/', api_farmacia_relatorio_ia),
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
    # ── Fase 1: Conformidade & Segurança ─────────────────────────
    path('api/farmacia/livro-controlado/', api_livro_controlado),
    path('api/farmacia/lotes/bloqueio/', api_lotes_bloqueio),
    path('api/farmacia/auditoria/', api_farmacia_auditoria),
    path('api/farmacia/conformidade/', api_farmacia_conformidade),
    # ── Fase 3: IA & Analytics ───────────────────────────────────
    path('api/farmacia/ia/dashboard/', api_farmacia_ia_dashboard),
    path('api/farmacia/ia/previsao-demanda/', api_farmacia_previsao_demanda),
    path('api/farmacia/ia/curva-abc/', api_farmacia_curva_abc),
    path('api/farmacia/ia/interacoes/', api_verificar_interacoes),
    # ── Fase 2: Multi-unidade & Rede ─────────────────────────────
    path('api/farmacia/rede/estoque/', api_rede_farmacia_estoque),
    path('api/farmacia/rede/disponibilidade/<str:nome_med>/', api_rede_farmacia_disponibilidade),
    path('api/farmacia/rede/transferencias/', api_rede_farmacia_transferencias),
    path('api/farmacia/rede/transferencias/<int:transf_id>/acao/', api_rede_farmacia_transferencia_acao),
    path('api/farmacia/rede/kpis/', api_rede_farmacia_kpis),
    path('api/hospital/painel', api_hospital_painel),
    # ── Hospital Gestão (Manchester / KPIs) ─────────────────
    path('api/hospital/dashboard', api_hospital_dashboard),
    path('api/hospital/leitos', api_hospital_leitos),
    path('api/hospital/triagem', api_hospital_triagem),
    path('api/hospital/pacientes', api_hospital_pacientes),
    path('api/hospital/prescricao', api_hospital_prescricao),
    # ── Hospital Operacional ─────────────────────────────────
    path('api/hospital/ops/kpis/', api_hospital_ops_kpis),
    path('api/hospital/contexto-integrado/', api_hospital_contexto_integrado),
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
    # ── Hospital Fase 1: Alta, UTI, Centro Cirúrgico, Isolamento ────────────
    path('api/hospital/pacientes/<int:pac_id>/evolucoes/', api_evolucoes_paciente),
    path('api/hospital/pacientes/<int:pac_id>/monitoramento-uti/', api_monitoramento_uti),
    path('api/hospital/pacientes/<int:pac_id>/avaliacoes-enfermagem/', api_avaliacoes_enfermagem),
    path('api/hospital/pacientes/<int:pac_id>/avaliacoes-fisioterapia/', api_avaliacoes_fisioterapia),
    path('api/hospital/pacientes/<int:pac_id>/avaliacoes-nutricionais/', api_avaliacoes_nutricionais),
    path('api/hospital/pacientes/<int:pac_id>/visitantes/', api_visitantes_paciente),
    path('api/hospital/visitantes/<int:visitante_id>/saida/', api_visitante_saida),
    path('api/hospital/pacientes/<int:pac_id>/declaracoes-obito/', api_declaracoes_obito),
    path('api/hospital/equipamentos/', api_equipamentos_medicos),
    path('api/hospital/equipamentos/<int:equip_id>/manutencoes/', api_manutencoes_equipamento),
    path('api/hospital/equipamentos/manutencoes/<int:os_id>/concluir/', api_manutencao_concluir),
    path('api/hospital/pacientes/<int:pac_id>/dose-unitaria/', api_dose_unitaria_paciente),
    path('api/hospital/dose-unitaria/<int:dose_id>/status/', api_dose_unitaria_status),
    path('api/hospital/leitos/<int:leito_id>/limpeza/', api_limpeza_leito),
    path('api/hospital/limpeza/<int:registro_id>/status/', api_limpeza_status),
    path('api/hospital/rouparia/', api_rouparia),
    path('api/hospital/pacientes/<int:pac_id>/sumario-alta/', api_sumario_alta),
    path('api/hospital/pacientes/<int:pac_id>/isolamento/', api_isolamento_paciente),
    path('api/hospital/centro-cirurgico/', api_centro_cirurgico),
    path('api/hospital/centro-cirurgico/<int:cc_id>/', api_centro_cirurgico_detalhe),
    path('api/hospital/uti/dashboard/', api_hospital_uti_dashboard),
    # ── Hospital Fase 2: Exames + Resultados + Administração ────────────────
    path('api/hospital/exames/dashboard/', api_exames_dashboard),
    path('api/hospital/exames/', api_pedidos_exame),
    path('api/hospital/exames/<int:pedido_id>/', api_pedido_exame_detalhe),
    path('api/hospital/exames/<int:pedido_id>/resultados/', api_resultados_exame),
    path('api/hospital/exames/resultados/<int:resultado_id>/visualizar/', api_resultado_visualizar),
    path('api/hospital/exames/resultados/<int:resultado_id>/arquivo/', api_resultado_arquivo),
    path('api/hospital/prescricoes/<int:presc_id>/administracoes/', api_administracoes),
    # ── Hospital Fase 3: Faturamento + Analytics ─────────────────
    path('api/hospital/analytics/', api_hospital_analytics),
    path('api/hospital/faturamento/dashboard/', api_faturamento_dashboard),
    path('api/hospital/pacientes/<int:pac_id>/fatura/', api_fatura_paciente),
    path('api/hospital/pacientes/<int:pac_id>/fatura/acao/', api_fatura_acao),
    path('api/hospital/pacientes/<int:pac_id>/fatura/itens/', api_itens_faturamento),
    path('api/hospital/faturamento/itens/<int:item_id>/', api_item_faturamento_detalhe),
    # ── Hospital Paridade Competitiva: EMR, cirurgia, LIS, RIS/PACS, farmácia e TISS ──
    path('api/hospital/prontuario/', api_prontuario_hospitalar),
    path('api/hospital/prontuario/<int:pront_id>/', api_prontuario_hospitalar_detalhe),
    path('api/hospital/prontuario/<int:pront_id>/evolucoes/', api_prontuario_evolucoes),
    path('api/hospital/prontuario/<int:pront_id>/prescricoes/', api_prontuario_prescricoes),
    path('api/hospital/cirurgia/', api_cirurgia),
    path('api/hospital/cirurgia/agenda/', api_cirurgia_agenda),
    path('api/hospital/cirurgia/kpis/', api_cirurgia_kpis),
    path('api/hospital/cirurgia/<int:cir_id>/', api_cirurgia_atualizar),
    path('api/hospital/farmacia/', api_farmacia_hosp),
    path('api/hospital/farmacia/kpis/', api_farmacia_hosp_kpis),
    path('api/hospital/farmacia/<int:item_id>/estoque/', api_farmacia_hosp_atualizar_estoque),
    path('api/hospital/lis/', api_lis),
    path('api/hospital/lis/kpis/', api_lis_kpis),
    path('api/hospital/lis/<int:exame_id>/resultado/', api_lis_resultado),
    path('api/hospital/imagem/', api_ris),
    path('api/hospital/imagem/kpis/', api_ris_kpis),
    path('api/hospital/imagem/<int:exame_id>/laudo/', api_ris_laudar),
    path('api/hospital/imagem/<int:exame_id>/dicom/', api_ris_dicom),
    path('api/hospital/imagem/dicom/<int:instancia_id>/arquivo/', api_ris_dicom_arquivo),
    path('api/hospital/tiss/', api_tiss),
    path('api/hospital/tiss/kpis/', api_tiss_kpis),
    path('api/hospital/tiss/<int:guia_id>/status/', api_tiss_atualizar_status),
    path('api/hospital/tiss/<int:guia_id>/xml/', api_tiss_gerar_xml),
    # ── Rede / Network ───────────────────────────────────────────
    path('api/rede/', api_redes),
    path('api/rede/convidar/', api_rede_convidar),
    path('api/rede/entrar/', api_rede_entrar),
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
    path('api/plano-saude/carencias/', api_carencias),
    path('api/plano-saude/carencias/<int:carencia_id>/', api_carencia_detalhe),
    path('api/plano-saude/portabilidade/', api_portabilidade),
    # ── Plano de Saúde Paridade Competitiva: corretores, rede, DIOPS/SIB, IA e portal ──
    path('api/plano-saude/corretoras/kpis', api_corretoras_kpis),
    path('api/plano-saude/corretoras', api_corretoras_lista),
    path('api/plano-saude/corretoras/<int:cor_id>', api_corretora_detalhe),
    path('api/plano-saude/corretoras/<int:cor_id>/comissoes', api_corretora_comissoes),
    path('api/plano-saude/rede/kpis', api_plano_rede_kpis),
    path('api/plano-saude/rede', api_plano_rede_lista),
    path('api/plano-saude/rede/novo', api_plano_rede_novo),
    path('api/plano-saude/rede/<int:rede_id>', api_plano_rede_detalhe),
    path('api/plano-saude/ans/kpis', api_ans_kpis),
    path('api/plano-saude/ans/diops', api_diops_lista),
    path('api/plano-saude/ans/diops/<int:decl_id>', api_diops_detalhe),
    path('api/plano-saude/ans/diops/<int:decl_id>/xml', api_diops_gerar_xml),
    # ── DIOPS 3.0 Real ────────────────────────────────────────────────────────
    path('api/plano-saude/ans/diops/<int:declaracao_id>/gerar-real/', api_diops_gerar_real),
    path('api/plano-saude/ans/diops/<int:declaracao_id>/download/', api_diops_download_xml),
    path('api/plano-saude/ans/diops/<int:declaracao_id>/transmitir/', api_diops_transmitir_ans),
    path('api/plano-saude/ans/sib', api_sib_lista),
    path('api/plano-saude/ans/sib/<int:sib_id>', api_sib_detalhe),
    path('api/plano-saude/ans/sib/<int:sib_id>/transmitir/', api_sib_transmitir),
    path('api/plano-saude/ia/kpis', api_ia_kpis),
    path('api/plano-saude/ia/autorizacoes', api_ia_autorizacoes),
    path('api/plano-saude/ia/analisar', api_ia_analisar),
    # ── IA ML Real ────────────────────────────────────────────────────────────
    path('api/plano-saude/ia/analisar-ml/', api_ia_analisar_ml),
    path('api/plano-saude/ia/retreinar/', api_ia_retreinar),
    path('api/plano-saude/ia/modelo-info/', api_ia_modelo_info),
    path('api/plano-saude/ia/<int:ia_id>/revisar', api_ia_revisar),
    # ── SNGPC Transmissão ANVISA Real ─────────────────────────────────────────
    path('api/farmacia/sngpc/gerar/', api_sngpc_gerar_xml),
    path('api/farmacia/sngpc/transmitir/', api_sngpc_transmitir),
    path('api/farmacia/sngpc/download/', api_sngpc_download),
    # ── Credenciais de Integrações (por empresa/tenant) ───────────────────────
    path('api/integracoes/credenciais/', api_credenciais_status),
    path('api/integracoes/credenciais/sngpc/', api_credenciais_sngpc_salvar),
    path('api/integracoes/credenciais/sngpc/testar/', api_credenciais_testar_sngpc),
    path('api/integracoes/credenciais/ans/', api_credenciais_ans_salvar),
    path('api/integracoes/credenciais/ans/testar/', api_credenciais_ans_testar),
    path('api/integracoes/credenciais/sus/', api_credenciais_sus_salvar),
    path('api/integracoes/credenciais/sus/testar/', api_credenciais_sus_testar),
    path('api/integracoes/credenciais/rnds/', api_credenciais_rnds_salvar),
    path('api/integracoes/credenciais/rnds/testar/', api_credenciais_rnds_testar),
    path('api/integracoes/credenciais/nfe/', api_credenciais_nfe_salvar),
    path('api/integracoes/credenciais/nfe/testar/', api_credenciais_nfe_testar),
    path('api/integracoes/credenciais/revogar/', api_credenciais_revogar),
    # NF-e / SEFAZ
    path('api/nfe/', api_nfe_lista),
    path('api/nfe/status/', api_nfe_status),
    path('api/nfe/emitir/', api_nfe_emitir),
    path('api/nfe/<int:nfe_id>/xml/', api_nfe_xml_download),
    path('api/plano-saude/portal/beneficiarios', api_portal_beneficiarios_lista),
    path('api/plano-saude/portal/token/<int:benef_id>', api_portal_token_gerar),
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

    # ── Governo Fase 2 ───────────────────────────────────────────
    path('api/governo/dashboard/fase2/', api_governo_fase2_dashboard),
    # Rede de Saúde
    path('api/governo/unidades/', api_unidades_saude),
    path('api/governo/unidades/<int:unidade_id>/', api_unidade_saude_detalhe),
    path('api/governo/unidades/<int:unidade_id>/equipes/', api_equipes_saude),
    # Vigilância Epidemiológica
    path('api/governo/vigilancia/notificacoes/', api_notificacoes),
    path('api/governo/vigilancia/surtos/', api_surtos),
    path('api/governo/vigilancia/surtos/<int:surto_id>/', api_surto_detalhe),
    path('api/governo/vigilancia/dashboard/', api_vigilancia_dashboard),
    # Regulação de Leitos
    path('api/governo/regulacao/', api_regulacao_leitos),
    path('api/governo/regulacao/<int:regulacao_id>/', api_regulacao_detalhe),
    path('api/governo/regulacao/dashboard/', api_regulacao_dashboard),
    # Produção Ambulatorial
    path('api/governo/producao/', api_producao_ambulatorial),
    path('api/governo/producao/dashboard/', api_producao_dashboard),
    # Previne Brasil
    path('api/governo/previne/', api_metas_previne),
    path('api/governo/previne/dashboard/', api_previne_dashboard),
    # Contratos de Gestão
    path('api/governo/contratos/', api_contratos_gestao),
    path('api/governo/contratos/<int:contrato_id>/', api_contrato_detalhe),
    # Urgência e Emergência
    path('api/governo/urgencia/', api_atendimentos_urgencia),
    path('api/governo/urgencia/dashboard/', api_urgencia_dashboard),
    # Plataforma TI Governamental
    path('api/governo/plataforma/integracoes/', api_governo_plataforma_integracoes),
    path('api/governo/plataforma/chaves/', api_governo_plataforma_chaves),
    path('api/governo/plataforma/webhooks/', api_governo_plataforma_webhooks),
    path('api/governo/plataforma/seguranca/', api_governo_plataforma_seguranca),
    path('api/governo/plataforma/logs/', api_governo_plataforma_logs),
    # ── Governo Paridade Competitiva: PEC, UBS, SISREG, SUS, teleconsulta, RAG/RDQA, e-SUS ──
    path('api/governo/pec/kpis/', api_pec_kpis),
    path('api/governo/pec/', api_pec_lista),
    path('api/governo/pec/novo/', api_pec_novo),
    path('api/governo/pec/<int:pac_id>/', api_pec_detalhe),
    path('api/governo/pec/<int:pac_id>/atendimentos/', api_pec_atendimentos),
    path('api/governo/farmacia-basica/kpis/', api_farmacia_basica_kpis),
    path('api/governo/farmacia-basica/itens/', api_farmacia_basica_itens),
    path('api/governo/farmacia-basica/dispensar/', api_farmacia_basica_dispensar),
    path('api/governo/farmacia-basica/dispensacoes/', api_farmacia_basica_dispensacoes),
    path('api/governo/regulacao-assistencial/kpis/', api_regulacao_kpis),
    path('api/governo/regulacao-assistencial/', api_regulacao_lista),
    path('api/governo/regulacao-assistencial/nova/', api_regulacao_nova),
    path('api/governo/regulacao-assistencial/<int:reg_id>/atualizar/', api_regulacao_atualizar),
    path('api/governo/faturamento-sus/kpis/', api_faturamento_sus_kpis),
    path('api/governo/faturamento-sus/lotes/', api_faturamento_sus_lotes),
    path('api/governo/faturamento-sus/<int:lote_id>/transmitir/', api_faturamento_sus_transmitir),
    path('api/governo/teleconsulta/kpis/', api_teleconsulta_kpis),
    path('api/governo/teleconsulta/', api_teleconsulta_lista),
    path('api/governo/teleconsulta/agendar/', api_teleconsulta_agendar),
    path('api/governo/teleconsulta/<int:tc_id>/atualizar/', api_teleconsulta_atualizar),
    path('api/governo/rag/kpis/', api_rag_kpis),
    path('api/governo/rag/', api_rag_lista),
    path('api/governo/rag/criar/', api_rag_criar),
    path('api/governo/rag/<int:rag_id>/atualizar/', api_rag_atualizar),
    path('api/governo/esus/status/', api_esus_status),
    path('api/governo/esus/logs/', api_esus_logs),
    path('api/governo/esus/enviar/', api_esus_enviar_fichas),

    # ── SIGTAP — Tabela de Procedimentos SUS ─────────────────────────────────
    path('api/governo/sigtap/buscar',         api_sigtap_buscar),
    path('api/governo/sigtap/buscar/',        api_sigtap_buscar),
    path('api/governo/sigtap/validar',        api_sigtap_validar),
    path('api/governo/sigtap/validar/',       api_sigtap_validar),
    path('api/governo/sigtap/validar-bpa',    api_sigtap_validar_bpa),
    path('api/governo/sigtap/validar-bpa/',   api_sigtap_validar_bpa),
    path('api/governo/sigtap/grupos',         api_sigtap_grupos),
    path('api/governo/sigtap/grupos/',        api_sigtap_grupos),
    path('api/governo/sigtap/kpis',           api_sigtap_kpis),
    path('api/governo/sigtap/kpis/',          api_sigtap_kpis),
    path('api/governo/sigtap/<str:codigo>',   api_sigtap_detalhe),
    path('api/governo/sigtap/<str:codigo>/',  api_sigtap_detalhe),

    # ── CAPS / Saúde Mental / RAPS ────────────────────────────────────────────
    path('api/governo/caps/unidades',                               api_caps_unidades),
    path('api/governo/caps/unidades/',                              api_caps_unidades),
    path('api/governo/caps/unidades/<int:caps_id>',                 api_caps_unidade_detalhe),
    path('api/governo/caps/unidades/<int:caps_id>/',                api_caps_unidade_detalhe),
    path('api/governo/caps/atendimentos',                           api_caps_atendimentos),
    path('api/governo/caps/atendimentos/',                          api_caps_atendimentos),
    path('api/governo/caps/encaminhamentos',                        api_caps_encaminhamentos),
    path('api/governo/caps/encaminhamentos/',                       api_caps_encaminhamentos),
    path('api/governo/caps/encaminhamentos/<int:enc_id>/acao',      api_caps_encaminhamento_acao),
    path('api/governo/caps/encaminhamentos/<int:enc_id>/acao/',     api_caps_encaminhamento_acao),
    path('api/governo/caps/kpis',                                   api_caps_kpis),
    path('api/governo/caps/kpis/',                                  api_caps_kpis),
    path('api/governo/caps/raas-exportar',                          api_caps_raas_exportar),
    path('api/governo/caps/raas-exportar/',                         api_caps_raas_exportar),

    # ── RNDS Hospital ─────────────────────────────────────────────────────────
    path('api/hospital/rnds/status',                                      api_hospital_rnds_status),
    path('api/hospital/rnds/status/',                                     api_hospital_rnds_status),
    path('api/hospital/rnds/transmissoes',                                api_hospital_rnds_transmissoes),
    path('api/hospital/rnds/transmissoes/',                               api_hospital_rnds_transmissoes),
    path('api/hospital/rnds/transmitir-alta/<int:internacao_id>',         api_hospital_rnds_transmitir_alta),
    path('api/hospital/rnds/transmitir-alta/<int:internacao_id>/',        api_hospital_rnds_transmitir_alta),
    path('api/hospital/rnds/transmitir-rac/<int:prontuario_id>',          api_hospital_rnds_transmitir_rac),
    path('api/hospital/rnds/transmitir-rac/<int:prontuario_id>/',         api_hospital_rnds_transmitir_rac),
    path('api/hospital/rnds/reprocessar/<int:tx_id>',                     api_hospital_rnds_reprocessar),
    path('api/hospital/rnds/reprocessar/<int:tx_id>/',                    api_hospital_rnds_reprocessar),
    path('api/hospital/rnds/kpis',                                        api_hospital_rnds_kpis),
    path('api/hospital/rnds/kpis/',                                       api_hospital_rnds_kpis),

    # ── Farmácia Magistral / Manipulação ──────────────────────────────────────
    path('api/farmacia/magistral/materias-primas',                        api_magistral_materias_primas),
    path('api/farmacia/magistral/materias-primas/',                       api_magistral_materias_primas),
    path('api/farmacia/magistral/lotes-mp',                               api_magistral_lotes_mp),
    path('api/farmacia/magistral/lotes-mp/',                              api_magistral_lotes_mp),
    path('api/farmacia/magistral/lotes-mp/<int:lote_id>/aprovar',         api_magistral_lote_aprovar),
    path('api/farmacia/magistral/lotes-mp/<int:lote_id>/aprovar/',        api_magistral_lote_aprovar),
    path('api/farmacia/magistral/formulas',                               api_magistral_formulas),
    path('api/farmacia/magistral/formulas/',                              api_magistral_formulas),
    path('api/farmacia/magistral/ordens',                                 api_magistral_ordens),
    path('api/farmacia/magistral/ordens/',                                api_magistral_ordens),
    path('api/farmacia/magistral/ordens/<int:om_id>/status',              api_magistral_ordem_status),
    path('api/farmacia/magistral/ordens/<int:om_id>/status/',             api_magistral_ordem_status),
    path('api/farmacia/magistral/controle-qualidade',                     api_magistral_controle_qualidade),
    path('api/farmacia/magistral/controle-qualidade/',                    api_magistral_controle_qualidade),
    path('api/farmacia/magistral/kpis',                                   api_magistral_kpis),
    path('api/farmacia/magistral/kpis/',                                  api_magistral_kpis),
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
    path('api/simular-focos', simular_focos_epidemicos),
    path('api/regeocodificar-focos', regeocodificar_focos),

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
    path('api/billing/status', api_billing_status),
    path('api/operacao/readiness', api_enterprise_readiness),
    path('api/planos-publicos', planos_publicos),
    path('api/plano/features', api_plano_features),   # features + limites do plano ativo
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
    path('api/governanca/caixa',         api_governanca_registrar_caixa),
    path('api/governanca/caixa/',        api_governanca_registrar_caixa),

    # Hub Enterprise — filtrado por setor, isolamento total entre ambientes
    path('hub/', hub_view),
    path('plataforma/', hub_view),
    path('api/enterprise/command-center', api_enterprise_command_center),
    path('api/enterprise/command-center/', api_enterprise_command_center),
    path('api/enterprise/premium-suite', api_enterprise_premium_suite),
    path('api/enterprise/premium-suite/', api_enterprise_premium_suite),
    path('api/enterprise/seed-operational-demo', api_enterprise_seed_operational_demo),
    path('api/enterprise/seed-operational-demo/', api_enterprise_seed_operational_demo),
    path('api/enterprise/reset-demo', api_enterprise_reset_demo),
    path('api/enterprise/reset-demo/', api_enterprise_reset_demo),

    # API Infra (versioning, rate limit, circuit breaker)
    path('api/infra/circuit-breaker', api_circuit_breaker_status),
    path('api/infra/circuit-breaker/', api_circuit_breaker_status),
    path('api/infra/rate-limit', api_rate_limit_status),
    path('api/infra/rate-limit/', api_rate_limit_status),

    # ── API v1 — stable surface (tenant-scoped) ──────────────────────────────
    path('api/v1/compliance/resumo', api_compliance_resumo),
    path('api/v1/compliance/trilha', api_compliance_trilha),
    path('api/v1/compliance/soc2/controles', api_soc2_controles),
    path('api/v1/rbac/permissoes', api_rbac_permissoes),
    path('api/v1/mlops/modelos', api_mlops_modelos),
    path('api/v1/mlops/monitoramento/snapshot', api_mlops_snapshot),
    path('api/v1/feature-store/features', api_feature_store_features),
    path('api/v1/feature-store/dicionario', api_feature_store_dicionario),
    path('api/v1/eventos/status', api_eventos_status),
    path('api/v1/schema/contratos', api_schema_contratos),
    path('api/v1/slo/status', api_slo_status),
    path('api/v1/saude', api_health),

    # ── API v2 — envelope padronizado + rate-limit headers ───────────────────
    path('api/v2/compliance/resumo', api_compliance_resumo),
    path('api/v2/compliance/trilha', api_compliance_trilha),
    path('api/v2/compliance/soc2/controles', api_soc2_controles),
    path('api/v2/rbac/permissoes', api_rbac_permissoes),
    path('api/v2/mlops/modelos', api_mlops_modelos),
    path('api/v2/mlops/monitoramento/snapshot', api_mlops_snapshot),
    path('api/v2/feature-store/features', api_feature_store_features),
    path('api/v2/eventos/status', api_eventos_status),
    path('api/v2/schema/contratos', api_schema_contratos),
    path('api/v2/slo/status', api_slo_status),
    path('api/v2/saude', api_health),

    # ── Relatórios PDF SST ────────────────────────────────────────────────────
    path('api/sst/relatorio/funcionarios.pdf', relatorio_pdf_funcionarios),
    path('api/sst/relatorio/asos.pdf', relatorio_pdf_asos),
    path('api/sst/relatorio/cats.pdf', relatorio_pdf_cats),
    path('api/sst/relatorio/treinamentos.pdf', relatorio_pdf_treinamentos),

    # ── Portal do Funcionário (app mobile trabalhador SST) ────────────────────
    path('api/funcionario/buscar-cpf', funcionario_buscar_cpf),
    path('api/funcionario/registrar', funcionario_registrar),
    path('api/funcionario/login', funcionario_login),
    path('api/funcionario/fcm-token', funcionario_salvar_fcm_token),
    path('api/funcionario/bem-estar', api_funcionario_checkin),
    path('api/funcionario/notificacoes', funcionario_notificacoes),
    path('api/funcionario/notificacoes/limpar-lidas', funcionario_notificacoes_limpar_lidas),
    path('api/funcionario/notificacoes/<int:notificacao_id>/lida', funcionario_notificacao_lida),
    path('api/funcionario/dashboard', funcionario_dashboard),
    path('api/funcionario/meu-perfil', funcionario_meu_perfil),
    path('api/funcionario/meus-asos', funcionario_meus_asos),
    path('api/funcionario/meus-treinamentos', funcionario_meus_treinamentos),
    path('api/funcionario/meus-epis', funcionario_meus_epis),
    path('api/funcionario/epis/pendentes-entrega', funcionario_epis_pendentes),
    path('api/funcionario/minhas-solicitacoes', funcionario_minhas_solicitacoes),
    path('api/funcionario/meus-afastamentos', funcionario_meus_afastamentos),
    path('api/funcionario/minha-biometria', funcionario_minha_biometria),
    path('api/funcionario/comunicados', funcionario_comunicados),
    path('api/funcionario/comunicados/<int:comunicado_id>/lido', funcionario_comunicado_lido),
    path('api/funcionario/psicossocial/ativa/', funcionario_psicossocial_ativa),

    # ── Upgrade self-service ──────────────────────────────────────────────────
    path('api/plano/upgrade/opcoes', api_upgrade_opcoes),
    path('api/plano/upgrade/checkout', api_upgrade_checkout),

    # ── White Label (Marca Branca) ────────────────────────────────────────────
    path('api/gestao/marca/', api_marca),
    path('api/gestao/marca/publica/', api_marca_publica),

    # ── WhatsApp Notifications ────────────────────────────────────────────────
    path('api/gestao/whatsapp/', api_whatsapp),
    path('api/gestao/whatsapp/testar/', api_whatsapp_testar),
    path('api/gestao/whatsapp/enviar/', api_whatsapp_enviar),
    path('api/gestao/whatsapp/logs/', api_whatsapp_logs),

    # ── Trial / Self-service Onboarding ──────────────────────────────────────
    path('api/gestao/trial', api_trial_status),
    path('api/gestao/trial/ativar', api_trial_ativar),
    path('api/gestao/onboarding/<str:passo>', api_onboarding_passo),

    # ── Integrações RH (TOTVS, ADP, Senior, SAP) ─────────────────────────────
    path('api/gestao/integracoes', api_integracoes),
    path('api/gestao/integracoes/', api_integracoes),
    path('api/gestao/integracoes/<int:integracao_id>/status', api_integracao_status),
    path('api/gestao/integracoes/webhook/<str:sistema>', api_integracao_webhook),

    # ── API Keys (acesso programático / BI) ───────────────────────────────────
    path('api/gestao/chaves', api_chaves),
    path('api/gestao/chaves/', api_chaves),
    path('api/gestao/chaves/<int:chave_id>/revogar', api_chave_revogar),
    path('api/gestao/uso-api', api_uso_api),
    path('api/gestao/plataforma/webhooks/', api_plataforma_webhooks),
    path('api/gestao/plataforma/seguranca/', api_plataforma_seguranca),
    path('api/gestao/plataforma/logs/', api_plataforma_logs),

    # ── Benchmark setorial ────────────────────────────────────────────────────
    path('api/gestao/benchmark', api_benchmark),

    # ── Dados via API Key (BI / ERP externo) ─────────────────────────────────
    path('api/v1/dados', api_dados_empresa),

    # ── Assinatura Digital SST ────────────────────────────────────────────────
    path('api/sst/assinaturas', api_sst_assinaturas),
    path('api/sst/assinaturas/', api_sst_assinaturas),
    path('api/sst/assinaturas/<str:token>', api_sst_assinatura_detalhe),
    path('assinatura/sst/<str:token>/', pagina_assinatura_sst),
    path('validar-assinatura/<str:token>/', pagina_validar_assinatura),
    path('api/public/sst/validar/<str:token>', api_public_validar_assinatura_sst),
    path('api/public/sst/assinar/<str:token>', api_public_assinar_sst),
    path('api/public/sst/assinaturas/<str:token>/assinar/', api_public_assinar_sst),

    # ── Plano de Saúde ────────────────────────────────────────────────────────
    path('api/plano-saude/dashboard', api_ps_dashboard),
    path('api/plano-saude/kpis', api_ps_kpis),
    path('api/plano-saude/planos', api_ps_planos),
    path('api/plano-saude/planos/<int:plano_id>', api_ps_plano_detalhe),
    path('api/plano-saude/beneficiarios', api_ps_beneficiarios),
    path('api/plano-saude/beneficiarios/<int:ben_id>', api_ps_beneficiario_detalhe),
    path('api/plano-saude/prestadores', api_ps_prestadores),
    path('api/plano-saude/prestadores/<int:prestador_id>', api_ps_prestador_detalhe),
    path('api/plano-saude/portal-prestador', api_ps_portal_prestador),
    path('api/plano-saude/guias', api_ps_guias),
    path('api/plano-saude/guias/<int:guia_id>', api_ps_guia_detalhe),
    path('api/plano-saude/fila-clinica', api_ps_fila_clinica),
    path('api/plano-saude/fila-clinica/<int:guia_id>/acao', api_ps_fila_clinica_acao),
    path('api/plano-saude/sinistros', api_ps_sinistros),
    path('api/plano-saude/sinistros/<int:sinistro_id>', api_ps_sinistro_detalhe),
    path('api/plano-saude/reembolsos', api_ps_reembolsos),
    path('api/plano-saude/reembolsos/<int:reembolso_id>', api_ps_reembolso_detalhe),
    # Glosas
    path('api/plano-saude/glosas', api_ps_glosas),
    path('api/plano-saude/glosas/<int:glosa_id>', api_ps_glosa_detalhe),
    # Coparticipação
    path('api/plano-saude/coparticipacao', api_ps_coparticipacao),
    path('api/plano-saude/coparticipacao/<int:regra_id>', api_ps_coparticipacao_detalhe),
    # Faturamento
    path('api/plano-saude/faturamento', api_ps_faturamento),
    path('api/plano-saude/faturamento/<int:fatura_id>', api_ps_fatura_detalhe),
    # Programas de Saúde
    path('api/plano-saude/programas', api_ps_programas),
    path('api/plano-saude/programas/<int:programa_id>', api_ps_programa_detalhe),
    # Inscrições em Programas
    path('api/plano-saude/inscricoes', api_ps_inscricoes),
    path('api/plano-saude/inscricoes/<int:inscricao_id>', api_ps_inscricao_detalhe),
    # Sinistralidade + IA
    path('api/plano-saude/sinistralidade-ia', api_ps_sinistralidade_ia),
    # ── Enterprise modules ──────────────────────────────────────────────────
    path('api/plano-saude/dashboard-exec/', api_ps_dashboard_exec),
    path('api/plano-saude/sla/', api_ps_sla),
    path('api/plano-saude/auditoria/', api_ps_auditoria),
    path('api/plano-saude/contratos/', api_ps_contratos),
    path('api/plano-saude/contratos/<int:contrato_id>/', api_ps_contrato_detalhe),
    path('api/plano-saude/comunicacao/', api_ps_comunicacao),
    path('api/plano-saude/comunicacao/<int:destinatario_id>/thread/', api_ps_comunicacao_thread),
    path('api/plano-saude/telemedicina/', api_ps_telemedicina),
    path('api/plano-saude/telemedicina/<int:tele_id>/autorizar/', api_ps_telemedicina_autorizar),
    path('api/plano-saude/odontologia/', api_ps_odontologia),
    path('api/plano-saude/odontologia/guias/<int:guia_id>/', api_ps_guia_odonto_detalhe),
    path('api/plano-saude/regulatorio/gerar/', api_ps_regulatorio_gerar),
    # ── Páginas SST Expansão ─────────────────────────────────────────────────
    path('sst/ppp/', sst_ppp_page),
    path('sst/laudos/', sst_laudos_page),
    path('sst/fap/', sst_fap_page),
    path('sst/laboratorios/', sst_laboratorio_page),
    path('sst/rede-credenciada/', sst_rede_credenciada_page),
    path('clinica/financeiro/', sst_financeiro_clinica_page),

    # ── Gestão FAP (Fator Acidentário de Prevenção) ─────────────────────────
    path('api/sst/fap/', api_fap_lista),
    path('api/sst/fap/registrar/', api_fap_registrar),
    path('api/sst/fap/simulacao/', api_fap_simulacao),
    path('api/sst/fap/contestacao/', api_fap_contestacao),
    path('api/sst/fap/historico/', api_fap_historico),
    path('api/sst/fap/kpis/', api_fap_kpis),
    path('api/sst/fap/<int:fap_id>/', api_fap_detalhe),

    # ── Motor de IA epidemiológica (todos os setores)
    path('api/ia/classificar', api_ia_classificar),
    path('api/ia/doencas', api_ia_doencas),
    path('api/ia/sintomas', api_ia_sintomas),
    path('api/ia/populacao', api_ia_populacao),
    path('api/ia/calibracao', api_ia_calibracao),
    path('api/ia/urgencias', api_ia_urgencias),

    # ── PGR / PCMSO Automático ────────────────────────────────────────────────
    path('sst/pgr/', sst_pgr_page),
    path('api/sst/pgr/gerar/', api_pgr_gerar),
    path('api/sst/pgr/<int:doc_id>/pdf/', api_pgr_pdf),
    path('api/sst/pcmso/gerar/', api_pcmso_gerar),
    path('api/sst/pcmso/<int:doc_id>/pdf/', api_pcmso_pdf),

    # ── CIPA — NR-5 ──────────────────────────────────────────────────────────
    path('sst/cipa/', sst_cipa_page),
    path('api/sst/cipa/kpis/', api_cipa_kpis),
    path('api/sst/cipa/comissoes/', api_cipa_comissoes),
    path('api/sst/cipa/comissoes/<int:comissao_id>/', api_cipa_comissao_detalhe),
    path('api/sst/cipa/comissoes/<int:comissao_id>/membros/', api_cipa_membros),
    path('api/sst/cipa/comissoes/<int:comissao_id>/reunioes/', api_cipa_reunioes),
    path('api/sst/cipa/reunioes/<int:reuniao_id>/', api_cipa_reuniao_detalhe),
    path('api/sst/cipa/reunioes/<int:reuniao_id>/ata/pdf/', api_cipa_ata_pdf),

    # ── Biometria Foto-confirmação (legado) ───────────────────────────────────
    path('sst/biometria/', sst_biometria_page),
    path('api/sst/biometria/kpis/', api_biometria_kpis),
    path('api/sst/biometria/cadastrar/', api_biometria_cadastrar),
    path('api/sst/biometria/<int:funcionario_id>/', api_biometria_detalhe),
    path('api/sst/biometria/entregas/<int:entrega_id>/confirmar/', api_biometria_confirmar_entrega),
    # ── Biometria Facial REAL (ArcFace DeepFace) ─────────────────────────────
    path('api/sst/biometria/facial/status/', api_biometria_status_facial),
    path('api/sst/biometria/<int:funcionario_id>/cadastrar-facial/', api_biometria_cadastrar_facial),
    path('api/sst/biometria/<int:funcionario_id>/verificar/', api_biometria_verificar_facial),
    path('api/sst/biometria/<int:funcionario_id>/apagar-lgpd/', api_biometria_apagar_lgpd),
    path('api/sst/epi/entregas/<int:entrega_id>/confirmar-facial/', api_biometria_confirmar_epi_facial),

    # ── Psicossocial NR-01 ────────────────────────────────────────────────────
    path('sst/psicossocial/', sst_psicossocial_page),
    path('api/sst/psicossocial/kpis/', api_psicossocial_kpis),
    path('api/sst/psicossocial/', api_psicossocial_avaliacoes),
    path('api/sst/psicossocial/<int:av_id>/', api_psicossocial_detalhe),
    path('api/sst/psicossocial/<int:av_id>/ativar/', api_psicossocial_ativar),
    path('api/sst/psicossocial/<int:av_id>/questoes/', api_psicossocial_questoes),
    path('api/sst/psicossocial/<int:av_id>/resultados/', api_psicossocial_resultados),
    path('api/sst/psicossocial/<int:av_id>/pdf/', api_psicossocial_pdf),
    path('api/sst/psicossocial/responder/<str:token>/', api_psicossocial_responder_publico),

    # ── OPME — Órteses, Próteses e Materiais Especiais ───────────────────────
    path('api/hospital/opme/kpis',                               api_opme_kpis),
    path('api/hospital/opme/kpis/',                              api_opme_kpis),
    path('api/hospital/opme/catalogo',                           api_opme_catalogo),
    path('api/hospital/opme/catalogo/',                          api_opme_catalogo),
    path('api/hospital/opme/catalogo/<int:item_id>',             api_opme_catalogo_detalhe),
    path('api/hospital/opme/catalogo/<int:item_id>/',            api_opme_catalogo_detalhe),
    path('api/hospital/opme/autorizacoes',                       api_opme_autorizacoes),
    path('api/hospital/opme/autorizacoes/',                      api_opme_autorizacoes),
    path('api/hospital/opme/autorizacoes/<int:aut_id>/acao',     api_opme_autorizacao_acao),
    path('api/hospital/opme/autorizacoes/<int:aut_id>/acao/',    api_opme_autorizacao_acao),
    path('api/hospital/opme/implantaveis',                       api_opme_implantaveis),
    path('api/hospital/opme/implantaveis/',                      api_opme_implantaveis),

    # ── Odontologia CEO (Centro de Especialidades Odontológicas) ─────────────
    path('api/governo/ceo/kpis',                                 api_ceo_kpis),
    path('api/governo/ceo/kpis/',                                api_ceo_kpis),
    path('api/governo/ceo/procedimentos',                        api_ceo_procedimentos),
    path('api/governo/ceo/procedimentos/',                       api_ceo_procedimentos),
    path('api/governo/ceo/atendimentos',                         api_ceo_atendimentos),
    path('api/governo/ceo/atendimentos/',                        api_ceo_atendimentos),
    path('api/governo/ceo/atendimentos/<int:atend_id>',          api_ceo_atendimento_detalhe),
    path('api/governo/ceo/atendimentos/<int:atend_id>/',         api_ceo_atendimento_detalhe),
    path('api/governo/ceo/producao',                             api_ceo_producao),
    path('api/governo/ceo/producao/',                            api_ceo_producao),
    path('api/governo/ceo/producao/<int:prod_id>/fechar',        api_ceo_fechar_producao),
    path('api/governo/ceo/producao/<int:prod_id>/fechar/',       api_ceo_fechar_producao),
    path('api/governo/ceo/producao/<int:prod_id>/transmitir',    api_ceo_transmitir),
    path('api/governo/ceo/producao/<int:prod_id>/transmitir/',   api_ceo_transmitir),
    path('api/governo/ceo/producao/<int:prod_id>/bpa-download',  api_ceo_bpa_download),
    path('api/governo/ceo/producao/<int:prod_id>/bpa-download/', api_ceo_bpa_download),

    # ── CCIH — Controle de Infecção Hospitalar (ANVISA RDC 36/2008) ──────────
    path('api/hospital/ccih/kpis',                               api_ccih_kpis),
    path('api/hospital/ccih/kpis/',                              api_ccih_kpis),
    path('api/hospital/ccih/infeccoes',                          api_ccih_infeccoes),
    path('api/hospital/ccih/infeccoes/',                         api_ccih_infeccoes),
    path('api/hospital/ccih/infeccoes/<int:ih_id>',              api_ccih_infeccao_detalhe),
    path('api/hospital/ccih/infeccoes/<int:ih_id>/',             api_ccih_infeccao_detalhe),
    path('api/hospital/ccih/isolamentos',                        api_ccih_isolamentos),
    path('api/hospital/ccih/isolamentos/',                       api_ccih_isolamentos),
    path('api/hospital/ccih/isolamentos/<int:iso_id>/encerrar',  api_ccih_isolamento_encerrar),
    path('api/hospital/ccih/isolamentos/<int:iso_id>/encerrar/', api_ccih_isolamento_encerrar),
    path('api/hospital/ccih/indicadores',                        api_ccih_indicadores),
    path('api/hospital/ccih/indicadores/',                       api_ccih_indicadores),

    # ── CEAF — Componente Especializado da Assistência Farmacêutica ──────────
    path('api/governo/ceaf/kpis',                                api_ceaf_kpis),
    path('api/governo/ceaf/kpis/',                               api_ceaf_kpis),
    path('api/governo/ceaf/medicamentos',                        api_ceaf_medicamentos),
    path('api/governo/ceaf/medicamentos/',                       api_ceaf_medicamentos),
    path('api/governo/ceaf/solicitacoes',                        api_ceaf_solicitacoes),
    path('api/governo/ceaf/solicitacoes/',                       api_ceaf_solicitacoes),
    path('api/governo/ceaf/solicitacoes/<int:sol_id>',           api_ceaf_solicitacao_detalhe),
    path('api/governo/ceaf/solicitacoes/<int:sol_id>/',          api_ceaf_solicitacao_detalhe),
    path('api/governo/ceaf/solicitacoes/<int:sol_id>/dispensar', api_ceaf_dispensar),
    path('api/governo/ceaf/solicitacoes/<int:sol_id>/dispensar/',api_ceaf_dispensar),
    path('api/governo/ceaf/dispensacoes/<int:disp_id>/horus',    api_ceaf_horus_enviar),
    path('api/governo/ceaf/dispensacoes/<int:disp_id>/horus/',   api_ceaf_horus_enviar),

    # ── Portabilidade ANS Formal (RN 438/2018) ───────────────────────────────
    path('api/plano-saude/portabilidade-ans/kpis',                           api_portabilidade_kpis),
    path('api/plano-saude/portabilidade-ans/kpis/',                          api_portabilidade_kpis),
    path('api/plano-saude/portabilidade-ans',                                api_portabilidade_lista),
    path('api/plano-saude/portabilidade-ans/',                               api_portabilidade_lista),
    path('api/plano-saude/portabilidade-ans/<int:sol_id>',                   api_portabilidade_detalhe),
    path('api/plano-saude/portabilidade-ans/<int:sol_id>/',                  api_portabilidade_detalhe),
    path('api/plano-saude/portabilidade-ans/<int:sol_id>/acao',              api_portabilidade_acao),
    path('api/plano-saude/portabilidade-ans/<int:sol_id>/acao/',             api_portabilidade_acao),
    path('api/plano-saude/portabilidade-ans/<int:sol_id>/declaracao',        api_portabilidade_declaracao),
    path('api/plano-saude/portabilidade-ans/<int:sol_id>/declaracao/',       api_portabilidade_declaracao),

    # ── NTEP — Nexo Técnico Epidemiológico (SST / Decreto 6.042/2007) ────────
    path('api/sst/ntep/kpis',                                    api_ntep_kpis),
    path('api/sst/ntep/kpis/',                                   api_ntep_kpis),
    path('api/sst/ntep/tabela',                                  api_ntep_tabela),
    path('api/sst/ntep/tabela/',                                 api_ntep_tabela),
    path('api/sst/ntep/verificar',                               api_ntep_verificar),
    path('api/sst/ntep/verificar/',                              api_ntep_verificar),
    path('api/sst/ntep/alertas',                                 api_ntep_alertas),
    path('api/sst/ntep/alertas/',                                api_ntep_alertas),
    path('api/sst/ntep/alertas/<int:alerta_id>',                 api_ntep_alerta_detalhe),
    path('api/sst/ntep/alertas/<int:alerta_id>/',                api_ntep_alerta_detalhe),
    path('api/sst/ntep/scan-cats',                               api_ntep_scan_cats),
    path('api/sst/ntep/scan-cats/',                              api_ntep_scan_cats),
    # ── Assistente IA SST (RAG via Claude Tool Use) ───────────────────────────
    path('api/sst/assistente',                                   assistente_sst),
    path('api/sst/assistente/',                                  assistente_sst),

    # ── Centro Obstétrico / Maternidade ──────────────────────────────────────
    path('api/hospital/obstetrico/kpis',                                      api_obstetrico_kpis),
    path('api/hospital/obstetrico/kpis/',                                     api_obstetrico_kpis),
    path('api/hospital/obstetrico/partogramas',                               api_obstetrico_partogramas),
    path('api/hospital/obstetrico/partogramas/',                              api_obstetrico_partogramas),
    path('api/hospital/obstetrico/partogramas/<int:pt_id>',                   api_obstetrico_partograma_detalhe),
    path('api/hospital/obstetrico/partogramas/<int:pt_id>/',                  api_obstetrico_partograma_detalhe),
    path('api/hospital/obstetrico/partos',                                    api_obstetrico_partos),
    path('api/hospital/obstetrico/partos/',                                   api_obstetrico_partos),
    path('api/hospital/obstetrico/partos/<int:parto_id>',                     api_obstetrico_parto_detalhe),
    path('api/hospital/obstetrico/partos/<int:parto_id>/',                    api_obstetrico_parto_detalhe),
    path('api/hospital/obstetrico/partos/<int:parto_id>/dnv',                 api_obstetrico_dnv),
    path('api/hospital/obstetrico/partos/<int:parto_id>/dnv/',                api_obstetrico_dnv),

    # ── SIPNI — Imunizações via RNDS ─────────────────────────────────────────
    path('api/governo/sipni/status',                            api_sipni_status),
    path('api/governo/sipni/status/',                           api_sipni_status),
    path('api/governo/sipni/historico',                         api_sipni_historico),
    path('api/governo/sipni/historico/',                        api_sipni_historico),
    path('api/governo/sipni/transmitir',                        api_sipni_transmitir),
    path('api/governo/sipni/transmitir/',                       api_sipni_transmitir),
    path('api/governo/sipni/reprocessar/<int:tx_id>',           api_sipni_reprocessar),
    path('api/governo/sipni/reprocessar/<int:tx_id>/',          api_sipni_reprocessar),
    path('api/governo/sipni/kpis',                              api_sipni_kpis),
    path('api/governo/sipni/kpis/',                             api_sipni_kpis),

    # ── Assinatura Digital de Prontuário (CFM Res. 2.299/2021) ───────────────
    path('api/hospital/assinatura/kpis',                        api_assinatura_kpis),
    path('api/hospital/assinatura/kpis/',                       api_assinatura_kpis),
    path('api/hospital/assinatura/pendentes',                   api_assinatura_pendentes),
    path('api/hospital/assinatura/pendentes/',                  api_assinatura_pendentes),
    path('api/hospital/assinatura/assinar-lote',                api_assinatura_assinar_lote),
    path('api/hospital/assinatura/assinar-lote/',               api_assinatura_assinar_lote),
    path('api/hospital/assinatura/assinar/<int:evolucao_id>',   api_assinatura_assinar),
    path('api/hospital/assinatura/assinar/<int:evolucao_id>/',  api_assinatura_assinar),
    path('api/hospital/assinatura/verificar/<int:evolucao_id>', api_assinatura_verificar),
    path('api/hospital/assinatura/verificar/<int:evolucao_id>/', api_assinatura_verificar),

    # ── CNES — Sincronização com DATASUS ─────────────────────────────────────
    path('api/governo/cnes/buscar',                             api_cnes_buscar),
    path('api/governo/cnes/buscar/',                            api_cnes_buscar),
    path('api/governo/cnes/sincronizar',                        api_cnes_sincronizar),
    path('api/governo/cnes/sincronizar/',                       api_cnes_sincronizar),
    path('api/governo/cnes/sincronizar-todas',                  api_cnes_sincronizar_todas),
    path('api/governo/cnes/sincronizar-todas/',                 api_cnes_sincronizar_todas),
    path('api/governo/cnes/status',                             api_cnes_status),
    path('api/governo/cnes/status/',                            api_cnes_status),
    path('api/governo/cnes/kpis',                               api_cnes_kpis),
    path('api/governo/cnes/kpis/',                              api_cnes_kpis),
    path('api/governo/cnes/<str:codigo_cnes>',                  api_cnes_detalhe),
    path('api/governo/cnes/<str:codigo_cnes>/',                 api_cnes_detalhe),

    # ── Hemoterapia (Banco de Sangue — ANVISA RDC 34/2014) ────────────────────
    path('api/hospital/hemoterapia/bolsas',                     api_hemo_bolsas),
    path('api/hospital/hemoterapia/bolsas/',                    api_hemo_bolsas),
    path('api/hospital/hemoterapia/bolsas/<int:bolsa_id>',      api_hemo_bolsa_detalhe),
    path('api/hospital/hemoterapia/bolsas/<int:bolsa_id>/',     api_hemo_bolsa_detalhe),
    path('api/hospital/hemoterapia/solicitacoes',               api_hemo_solicitacoes),
    path('api/hospital/hemoterapia/solicitacoes/',              api_hemo_solicitacoes),
    path('api/hospital/hemoterapia/transfusoes',                api_hemo_transfusoes),
    path('api/hospital/hemoterapia/transfusoes/',               api_hemo_transfusoes),
    path('api/hospital/hemoterapia/reacoes',                    api_hemo_reacoes),
    path('api/hospital/hemoterapia/reacoes/',                   api_hemo_reacoes),
    path('api/hospital/hemoterapia/reacoes/<int:reacao_id>/notificar-anvisa',          api_hemo_notificar_anvisa),
    path('api/hospital/hemoterapia/reacoes/<int:reacao_id>/notificar-anvisa/',         api_hemo_notificar_anvisa),
    path('api/hospital/hemoterapia/reacoes/<int:reacao_id>/notificar-anvisa/download', api_hemo_notivisa_download),
    path('api/hospital/hemoterapia/reacoes/<int:reacao_id>/notificar-anvisa/download/',api_hemo_notivisa_download),
    path('api/hospital/hemoterapia/kpis',                       api_hemo_kpis),
    path('api/hospital/hemoterapia/kpis/',                      api_hemo_kpis),

    # ── Oncologia (Alta Complexidade / APAC SUS) ──────────────────────────────
    path('api/hospital/oncologia/protocolos',                   api_onco_protocolos),
    path('api/hospital/oncologia/protocolos/',                  api_onco_protocolos),
    path('api/hospital/oncologia/ciclos',                       api_onco_ciclos),
    path('api/hospital/oncologia/ciclos/',                      api_onco_ciclos),
    path('api/hospital/oncologia/ciclos/<int:ciclo_id>',        api_onco_ciclo_detalhe),
    path('api/hospital/oncologia/ciclos/<int:ciclo_id>/',       api_onco_ciclo_detalhe),
    path('api/hospital/oncologia/ciclos/<int:ciclo_id>/toxicidade',  api_onco_toxicidade),
    path('api/hospital/oncologia/ciclos/<int:ciclo_id>/toxicidade/', api_onco_toxicidade),
    path('api/hospital/oncologia/apacs',                        api_onco_apacs),
    path('api/hospital/oncologia/apacs/',                       api_onco_apacs),
    path('api/hospital/oncologia/apacs/<int:apac_id>',          api_onco_apac_detalhe),
    path('api/hospital/oncologia/apacs/<int:apac_id>/',         api_onco_apac_detalhe),
    path('api/hospital/oncologia/kpis',                         api_onco_kpis),
    path('api/hospital/oncologia/kpis/',                        api_onco_kpis),

    # ── TUSS + Rol ANS + NIP (Plano de Saúde) ────────────────────────────────
    path('api/plano-saude/tuss/procedimentos',                  api_tuss_procedimentos),
    path('api/plano-saude/tuss/procedimentos/',                 api_tuss_procedimentos),
    path('api/plano-saude/tuss/rol-ans',                        api_rol_coberturas),
    path('api/plano-saude/tuss/rol-ans/',                       api_rol_coberturas),
    path('api/plano-saude/tuss/diretrizes',                     api_tuss_diretrizes),
    path('api/plano-saude/tuss/diretrizes/',                    api_tuss_diretrizes),
    path('api/plano-saude/tuss/verificar',                      api_tuss_verificar_cobertura),
    path('api/plano-saude/tuss/verificar/',                     api_tuss_verificar_cobertura),
    path('api/plano-saude/tuss/kpis',                           api_tuss_kpis),
    path('api/plano-saude/tuss/kpis/',                          api_tuss_kpis),
    path('api/plano-saude/nip',                                 api_nip_lista),
    path('api/plano-saude/nip/',                                api_nip_lista),
    path('api/plano-saude/nip/<int:nip_id>',                    api_nip_detalhe),
    path('api/plano-saude/nip/<int:nip_id>/',                   api_nip_detalhe),
    path('api/plano-saude/nip/<int:nip_id>/responder',          api_nip_responder),
    path('api/plano-saude/nip/<int:nip_id>/responder/',         api_nip_responder),

    # ── ACS + Visitas Domiciliares + Fichas (Governo / Atenção Básica) ────────
    path('api/governo/acs',                                     api_acs_lista),
    path('api/governo/acs/',                                    api_acs_lista),
    path('api/governo/endemias/visitas/',                       api_endemias_visitas),
    path('api/governo/endemias/indicadores/',                   api_endemias_indicadores),
    path('api/governo/vigilancia-sanitaria/estabelecimentos/',  api_vigsan_estabelecimentos),
    path('api/governo/vigilancia-sanitaria/estabelecimentos/<int:estab_id>/alvaras/',   api_vigsan_alvaras),
    path('api/governo/vigilancia-sanitaria/estabelecimentos/<int:estab_id>/inspecoes/', api_vigsan_inspecoes),
    path('api/governo/acs/kpis',                                api_acs_kpis),
    path('api/governo/acs/kpis/',                               api_acs_kpis),
    path('api/governo/acs/<int:acs_id>',                        api_acs_detalhe),
    path('api/governo/acs/<int:acs_id>/',                       api_acs_detalhe),
    path('api/governo/acs/visitas',                             api_visitas_lista),
    path('api/governo/acs/visitas/',                            api_visitas_lista),
    path('api/governo/acs/visitas/transmitir-esus',             api_visitas_transmitir_esus),
    path('api/governo/acs/visitas/transmitir-esus/',            api_visitas_transmitir_esus),
    path('api/governo/acs/visitas/exportar-cds',                api_visitas_exportar_cds),
    path('api/governo/acs/visitas/exportar-cds/',               api_visitas_exportar_cds),
    path('api/governo/acs/visitas/<int:visita_id>',             api_visita_detalhe),
    path('api/governo/acs/visitas/<int:visita_id>/',            api_visita_detalhe),
    path('api/governo/acs/fichas',                              api_fichas_acompanhamento),
    path('api/governo/acs/fichas/',                             api_fichas_acompanhamento),
    path('api/governo/acs/fichas/<int:ficha_id>',               api_ficha_detalhe),
    path('api/governo/acs/fichas/<int:ficha_id>/',              api_ficha_detalhe),
]
