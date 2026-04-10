from django.contrib import admin
from django.urls import path, include
from django.http import FileResponse
import os

from api.views import (
    registrar_sintoma, listar_sintomas,
    alertas, tela_login, tela_pagamento,
    relatorio_regioes, relatorio_municipios,
    analisar_tosse,
    resumo_municipios, resumo_estados,
    detectar_surtos, prever_surtos,
    painel_geral,
    diagnostico_ia, registrar_sintoma_app, analisar_audio,
    resumo_doencas, diagnostico_ia_avancado,
    limpar_casos, mapa_casos,
    insights_nacional,
    tela_cadastro
)

from api.views_auth import registrar_empresa, login_empresa
from api.views_dashboard import dados_dashboard, dashboard, global_paises, dashboard_farmacia

# 🔥 IMPORT CORRETO (APENAS UM)
from api.views_pagamento import criar_pagamento, webhook, sucesso, erro, pendente, status_pagamento


def service_worker(request):
    return FileResponse(open(os.path.join(os.getcwd(), 'sw.js'), 'rb'))


urlpatterns = [
    path('admin/', admin.site.urls),

    # 🔐 LOGIN
    path('', tela_login),
    path('api/login', login_empresa),

    # 🧠 DASHBOARD
    path('dashboard/', dashboard),
    path('dashboard-farmacia/', dashboard_farmacia),

    # 💰 PAGAMENTO
    path('pagamento/', tela_pagamento),

    # 📊 API PRINCIPAL
    path('api/registrar', registrar_sintoma),
    path('api/sintomas', listar_sintomas),
    path('api/dashboard', dados_dashboard),
    path('api/alertas', alertas),

    path('api/registrar_empresa', registrar_empresa),
    path('api/global-paises', global_paises),

    path("api/analisar-tosse", analisar_tosse),

    path('api/resumo-municipios', resumo_municipios),
    path('api/resumo-estados', resumo_estados),

    path('api/surtos', detectar_surtos),
    path('api/previsao-surtos', prever_surtos),

    path("api/painel", painel_geral),

    path('api/doencas', resumo_doencas),
    path('api/diagnostico', diagnostico_ia),
    path('api/ia-avancada', diagnostico_ia_avancado),

    path('api/registrar-app', registrar_sintoma_app),
    path('api/analisar-audio', analisar_audio),

    path('api/limpar-casos', limpar_casos),
    path('api/mapa-casos', mapa_casos),

    # 🔥 INSIGHTS
    path('api/insights-nacional', insights_nacional),

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
]