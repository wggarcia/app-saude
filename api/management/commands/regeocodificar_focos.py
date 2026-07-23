"""
Reprocessa os campos cidade/bairro/estado de todos os RegistroSintoma
do app público que foram geocodificados errado (ex: Copacabana → "Centro").
Usa o fallback local aprimorado diretamente para não depender de Nominatim.
"""
from django.core.management.base import BaseCommand
from api.models import RegistroSintoma, Empresa
from api.utils_geo import _fallback_local
from api.epidemiologia import clear_panorama_cache


class Command(BaseCommand):
    help = "Re-geocodifica registros do app público usando o fallback local melhorado"

    def handle(self, *args, **options):
        try:
            emp = Empresa.objects.get(email="populacao@solocrt.com")
        except Empresa.DoesNotExist:
            self.stderr.write("Empresa populacao@solocrt.com não encontrada")
            return

        qs = RegistroSintoma.objects.filter(
            empresa=emp,
            latitude__isnull=False,
            longitude__isnull=False,
        )
        total = qs.count()
        self.stdout.write(f"Processando {total} registros...")

        atualizados = 0
        for r in qs:
            geo = _fallback_local(r.latitude, r.longitude)
            novo_bairro = geo["bairro"]
            nova_cidade = geo["cidade"]
            novo_estado = geo["estado"]

            if (r.bairro != novo_bairro or
                    r.cidade != nova_cidade or
                    r.estado != novo_estado):
                r.bairro = novo_bairro
                r.cidade = nova_cidade
                r.estado = novo_estado
                r.pais = geo.get("pais", "Brasil")
                r.save(update_fields=["bairro", "cidade", "estado", "pais"])
                atualizados += 1

        clear_panorama_cache()
        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Concluído: {atualizados}/{total} registros corrigidos. Cache limpo."
            )
        )
