from api.models import RegistroSintoma
from api.utils_geo import obter_endereco

for r in RegistroSintoma.objects.all():

    if not r.latitude or not r.longitude:
        continue

    geo = obter_endereco(r.latitude, r.longitude)

    print("ANTES:", r.bairro)
    print("DEPOIS:", geo)

    r.bairro = geo.get("bairro")
    r.cidade = geo.get("cidade")
    r.estado = geo.get("estado")
    r.pais = geo.get("pais")

    r.save()

print("OK FINAL")