from django.contrib import admin
from django.urls import path, include
from django.http import FileResponse
from api.views import resumo_estados, resumo_municipios
import os

from api.views import (
    registrar_sintoma, listar_sintomas,
    alertas, tela_login, tela_pagamento,
    sucesso, erro, pendente,
    relatorio_regioes, relatorio_municipios,
    analisar_tosse,
    resumo_municipios, resumo_estados,
    detectar_surtos, prever_surtos,
    painel_geral,
    clusters, diagnostico_ia, registrar_sintoma_app, analisar_audio
)

from api.views_auth import registrar_empresa, login_empresa
from api.views_dashboard import dados_dashboard, dashboard, global_paises
from api.views_pagamento import criar_pagamento, webhook
from api.views import alertas
from api.views import resumo_doencas
from api.views import diagnostico_ia_avancado
from api.views import limpar_casos


def service_worker(request):
    return FileResponse(open(os.path.join(os.getcwd(), 'sw.js'), 'rb'))


urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/registrar', registrar_sintoma),
    path('api/sintomas', listar_sintomas),
    path('api/dashboard', dados_dashboard),

    path('dashboard/', dashboard),
    path('api/login', login_empresa),
    path('', tela_login),

    path('api/pagamento', criar_pagamento),
    path('pagamento/', tela_pagamento),
    path('sucesso/', sucesso),
    path('erro/', erro),
    path('pendente/', pendente),

    path("api/relatorio", relatorio_regioes),
    path('api/municipios', relatorio_municipios),

    path('api/alertas', alertas),
    path('api/clusters', clusters),

    path('api/registrar_empresa', registrar_empresa),
    path('api/global-paises', global_paises),

    path("api/analisar-tosse", analisar_tosse),
    path("api/webhook", webhook),

    path('api/resumo-municipios', resumo_municipios),
    path('api/resumo-estados', resumo_estados),

    path('api/surtos', detectar_surtos),
    path('api/previsao-surtos', prever_surtos),

    path("api/painel", painel_geral),

    path('sw.js', service_worker),

    path('api/', include('api.urls')),
    path('api/doencas', resumo_doencas),
    path('api/diagnostico', diagnostico_ia),
    path('api/ia-avancada', diagnostico_ia_avancado),
    path('api/registrar-app', registrar_sintoma_app),
    path('api/analisar-audio', analisar_audio),
    path('api/limpar-casos', limpar_casos),
]