from django.urls import path
from .views import ativar_plano

urlpatterns = [
    path('ativar-plano/<int:empresa_id>/', ativar_plano),
]