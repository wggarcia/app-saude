"""Re-geocodifica os registros de sintoma do app público com o mapa de
referência aprimorado (100+ pontos do Brasil).

Por quê?
--------
Registros antigos foram rotulados genericamente como "Centro, Rio de Janeiro"
porque o fallback de geocodificação anterior tinha apenas 12 pontos para o
Brasil inteiro (e o Nominatim sofria timeout de 2,5s em produção). Como o
lat/lng real desses registros era de Copacabana, Tijuca, Botafogo, Niterói,
Nova Iguaçu etc., a MÉDIA das coordenadas sob um único rótulo "Centro" caía
dentro da Baía de Guanabara — o "foco na ilha/água" que aparecia no mapa.

O `utils_geo.py` agora tem 100+ pontos precisos (15+ bairros do RJ, capitais
e municípios principais). Esta migração reprocessa cidade/bairro/estado de
cada registro usando esse mapa, fazendo o foco agregado se dividir em pontos
territorialmente corretos.

Roda no banco de produção via `manage.py migrate` (parte do preDeploy),
com acesso total (bypassa RLS) e sem depender de sessão/login. É idempotente
e nunca levanta exceção — não pode quebrar o deploy.
"""
from django.db import migrations


PUBLIC_APP_EMAIL = "populacao@soluscrt.com"


def _regeocodifica(apps, schema_editor):
    from api.utils_geo import _fallback_local

    Empresa = apps.get_model("api", "Empresa")
    RegistroSintoma = apps.get_model("api", "RegistroSintoma")

    empresa = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
    if not empresa:
        return

    qs = RegistroSintoma.objects.filter(
        empresa=empresa,
        latitude__isnull=False,
        longitude__isnull=False,
    )

    atualizados = 0
    for r in qs.iterator():
        try:
            g = _fallback_local(r.latitude, r.longitude)
            if (r.bairro != g["bairro"] or r.cidade != g["cidade"]
                    or r.estado != g["estado"]):
                r.bairro = g["bairro"]
                r.cidade = g["cidade"]
                r.estado = g["estado"]
                r.pais = g.get("pais", "Brasil")
                r.save(update_fields=["bairro", "cidade", "estado", "pais"])
                atualizados += 1
        except Exception:  # noqa: BLE001 — nunca quebrar o deploy
            continue

    # Limpa o cache do panorama para refletir imediatamente
    try:
        from api.epidemiologia import clear_panorama_cache
        clear_panorama_cache()
    except Exception:  # noqa: BLE001
        pass


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0092_provisiona_credenciais_app_demo"),
    ]

    operations = [
        migrations.RunPython(_regeocodifica, _noop),
    ]
