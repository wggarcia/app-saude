# api/inteligencia.py

from datetime import timedelta
from django.utils import timezone
from .models import RegistroSintoma

def casos_ultimas_24h():
    agora = timezone.now()
    ontem = agora - timedelta(hours=24)

    return RegistroSintoma.objects.filter(
        data_registro__gte=ontem
    ).count()


def casos_anteriores():
    agora = timezone.now()
    inicio = agora - timedelta(hours=48)
    fim = agora - timedelta(hours=24)

    return RegistroSintoma.objects.filter(
        data_registro__gte=inicio,
        data_registro__lt=fim
    ).count()


def nivel_risco():
    atual = casos_ultimas_24h()
    anterior = casos_anteriores()

    if anterior == 0:
        return "baixo"

    crescimento = atual / anterior

    if crescimento > 2:
        return "alto"
    elif crescimento > 1.2:
        return "medio"
    return "baixo"