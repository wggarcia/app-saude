from .models import RegistroSintoma
from seu_app.utils.geolocalizacao import obter_regiao

def processar_registros_sem_regiao():
    registros = RegistroSintoma.objects.filter(cidade__isnull=True)

    for r in registros:
        regiao = obter_regiao(r.latitude, r.longitude)

        r.pais = regiao.get("pais")
        r.estado = regiao.get("estado")
        r.cidade = regiao.get("cidade")
        r.bairro = regiao.get("bairro")
        r.condado = regiao.get("condado")

        r.save()