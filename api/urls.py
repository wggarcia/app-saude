from django.urls import path
from .views import insights_farmacia
from api.views import tela_cadastro
from .views_pagamento import pagar_direto
from .views import casos_por_regiao



urlpatterns = [
    path('insights-farmacia/', insights_farmacia),
    path('cadastro/', tela_cadastro),
    path('pagar-direto/', pagar_direto),
    path("regioes", casos_por_regiao),
    path("api/regioes", casos_por_regiao),

]

