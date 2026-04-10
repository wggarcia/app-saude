from django.urls import path
from .views import insights_farmacia
from api.views import tela_cadastro
from .views_pagamento import pagar_direto


urlpatterns = [
    path('insights-farmacia/', insights_farmacia),
    path('cadastro/', tela_cadastro),
    path('pagar-direto/', pagar_direto),

]

