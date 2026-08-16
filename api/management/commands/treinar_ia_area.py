"""
treinar_ia_area — Treina os modelos de IA POR ÁREA e POR EMPRESA.

Cada área (opme, …) tem o próprio modelo, treinado com as decisões reais
daquela área e daquela empresa (isolamento/LGPD). Roda mensal no cron.

Uso:
  python manage.py treinar_ia_area --todas               # todas as áreas, todas as empresas hospital
  python manage.py treinar_ia_area --area opme           # área específica, todas as empresas
  python manage.py treinar_ia_area --area opme --empresa 44
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Treina modelos de IA por área/empresa (OPME etc.) com dados reais."

    def add_arguments(self, parser):
        parser.add_argument("--area", help="Área específica (ex.: opme). Sem isto, treina todas.")
        parser.add_argument("--empresa", type=int, help="Empresa específica. Sem isto, todas do setor hospital.")
        parser.add_argument("--todas", action="store_true", help="Todas as áreas e empresas.")

    def handle(self, *args, **opts):
        from api.services.ia_areas import AREAS, treinar_area
        from api.models import Empresa
        from api.access_control import get_setor

        areas = [opts["area"]] if opts.get("area") else list(AREAS.keys())
        for a in areas:
            if a not in AREAS:
                self.stderr.write(self.style.ERROR(f"Área desconhecida: {a}"))
                return

        if opts.get("empresa"):
            empresas = Empresa.objects.filter(id=opts["empresa"])
        else:
            # empresas do setor hospital (as que têm OPME/áreas clínicas)
            empresas = [e for e in Empresa.objects.filter(ativo=True)
                        if _seguro_setor(e) == "hospital"]

        total_ok = total_falha = 0
        for area in areas:
            for emp in empresas:
                try:
                    meta = treinar_area(area, emp.id)
                    total_ok += 1
                    tag = "bootstrap" if meta["dataset_sintetico"] else "dados reais"
                    f1 = f"{meta['cv_f1']:.3f}" if meta["cv_f1"] is not None else "—"
                    self.stdout.write(
                        f"[{area}] empresa {emp.id}: {meta['n_amostras_reais']} reais "
                        f"({tag}), F1={f1}")
                except Exception as e:
                    total_falha += 1
                    self.stdout.write(self.style.WARNING(
                        f"[{area}] empresa {emp.id}: pulado — {e}"))
        self.stdout.write(self.style.SUCCESS(
            f"Concluído: {total_ok} modelo(s) treinado(s), {total_falha} pulado(s)."))


def _seguro_setor(empresa):
    from api.access_control import get_setor
    try:
        return get_setor(empresa)
    except Exception:
        return None
