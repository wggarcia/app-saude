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
    site_principal, documento_publico
)

from api.views_auth import registrar_empresa, login_empresa, login_portal_empresa, login_portal_governo, logout_empresa, logout_governo, logout_operacao, login_dono_saas
from api.views_dashboard import dados_dashboard, dashboard, global_paises, dashboard_farmacia, dashboard_hospital, dashboard_governo, contrato_governo, licencas, seguranca, api_dispositivos, api_revogar_dispositivo, api_auditoria_seguranca, usuarios_empresa, api_usuarios_empresa, api_criar_usuario_empresa, api_desativar_usuario_empresa, login_operacao, console_operacional, api_dono_resumo, api_dono_atualizar_cliente, api_dono_financeiro_acao, api_dono_exportar, api_alertas_governo, api_criar_alerta_governo, api_toggle_alerta_governo, api_fluxo_alerta_governo
from api.epidemiologia import panorama_epidemiologico, exportar_briefing_governo
from api.fontes_oficiais_brasil import api_brasil_fontes_oficiais
from api.governanca import api_auditoria_institucional, api_matriz_decisao, api_metodologia_epidemiologica

# 🔥 IMPORT CORRETO (APENAS UM)
from api.views_pagamento import criar_pagamento, webhook, sucesso, erro, pendente, status_pagamento


def service_worker(request):
    return FileResponse(open(os.path.join(os.getcwd(), 'sw.js'), 'rb'))


urlpatterns = [
    path('admin/', admin.site.urls),

    # 🔐 LOGIN
    path('', site_principal),
    path('privacidade/', documento_publico, {"slug": "privacidade"}),
    path('termos/', documento_publico, {"slug": "termos"}),
    path('seguranca-lgpd/', documento_publico, {"slug": "seguranca-lgpd"}),
    path('metodologia/', documento_publico, {"slug": "metodologia"}),
    path('login-empresa/', tela_login_empresa),
    path('login-governo/', tela_login_governo),
    path('operacao-central/', login_operacao),
    path('api/login', login_empresa),
    path('api/login-empresa', login_portal_empresa),
    path('api/login-governo', login_portal_governo),
    path('api/operacao-central/login', login_dono_saas),
    path('logout/', logout_empresa),
    path('logout-governo/', logout_governo),
    path('logout-operacao/', logout_operacao),

    # 🧠 DASHBOARD
    path('dashboard/', dashboard),
    path('dashboard-farmacia/', dashboard_farmacia),
    path('dashboard-hospital/', dashboard_hospital),
    path('dashboard-governo/', dashboard_governo),
    path('contrato-governo/', contrato_governo),
    path('licencas/', licencas),
    path('seguranca/', seguranca),
    path('usuarios/', usuarios_empresa),
    path('console-operacional/', console_operacional),

    # 💰 PAGAMENTO
    path('pagamento/', tela_pagamento),

    # 📊 API PRINCIPAL
    path('api/registrar', registrar_sintoma),
    path('api/public/registrar', registrar_sintoma_publico),
    path('api/sintomas', listar_sintomas),
    path('api/dashboard', dados_dashboard),
    path('api/alertas', alertas),
    path('api/public/resumo', app_resumo_publico),
    path('api/public/radar-local', app_radar_local),
    path('api/public/mapa', app_mapa_publico),
    path('api/public/alertas', app_alertas_publicos),
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
    path('api/governo/alertas', api_alertas_governo),
    path('api/governo/alertas/criar', api_criar_alerta_governo),
    path('api/governo/alertas/toggle', api_toggle_alerta_governo),
    path('api/governo/alertas/fluxo', api_fluxo_alerta_governo),
    path('api/governanca/metodologia', api_metodologia_epidemiologica),
    path('api/governanca/matriz-decisao', api_matriz_decisao),
    path('api/governanca/auditoria', api_auditoria_institucional),

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
    
]
