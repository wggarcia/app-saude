from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import AlertaGovernamental, DispositivoAutorizado, Empresa, RegistroSintoma
from api.services.public_integrity import (
    SYNTHETIC_DEVICE_PREFIXES,
    q_alerta_governamental_sintetico,
    q_registro_sintoma_sintetico,
)
from api.utils import EMAILS_CONTAS_DEMO as DEMO_EMAILS
def _q_dispositivo_sintetico():
    from django.db.models import Q

    query = Q()
    for prefix in SYNTHETIC_DEVICE_PREFIXES:
        query |= Q(device_id__istartswith=prefix)
    return query


class Command(BaseCommand):
    help = "Remove contas demo e residuos sintéticos explícitos da produção."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Executa a limpeza de verdade. Sem esta flag, apenas mostra o preview.",
        )

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        if self._is_production() and not apply:
            raise CommandError("Em producao use --apply para executar a limpeza.")

        preview = self._collect_preview()

        self.stdout.write("\n=== Sanear Produção ===\n")
        self.stdout.write(f"Contas demo encontradas: {preview['empresas_demo']}")
        self.stdout.write(f"Alertas sintéticos encontrados: {preview['alertas_sinteticos']}")
        self.stdout.write(f"Registros sintéticos encontrados: {preview['registros_sinteticos']}")
        self.stdout.write(f"Dispositivos sintéticos encontrados: {preview['dispositivos_sinteticos']}")

        if not apply:
            self.stdout.write(self.style.WARNING("\nPreview apenas. Use --apply para executar a limpeza."))
            return

        with transaction.atomic(using="owner"):
            # Deletar a empresa demo via cascade bate em FKs PROTECT indiretas
            # (ex.: Empresa→CatalogoOPME[cascade] ← ItemAutorizacaoOPME[PROTECT];
            # Empresa→ACS[cascade] ← VisitaDomiciliar[PROTECT]) e levanta
            # ProtectedError. Antes de deletar a empresa, limpamos genericamente
            # todos os modelos com FK PROTECT que pertencem às empresas demo.
            demo_ids = list(
                Empresa.objects.using("owner").filter(email__in=DEMO_EMAILS).values_list("id", flat=True)
            )
            if demo_ids:
                self._limpar_protect_das_empresas(demo_ids)
            removidos_empresas = Empresa.objects.using("owner").filter(email__in=DEMO_EMAILS).delete()[0]
            removidos_alertas = AlertaGovernamental.objects.using("owner").filter(q_alerta_governamental_sintetico()).delete()[0]
            removidos_registros = RegistroSintoma.objects.using("owner").filter(q_registro_sintoma_sintetico()).delete()[0]
            removidos_dispositivos = DispositivoAutorizado.objects.using("owner").filter(_q_dispositivo_sintetico()).delete()[0]
        self.stdout.write(self.style.SUCCESS("\nLimpeza concluída."))
        self.stdout.write(f"Empresas removidas: {removidos_empresas}")
        self.stdout.write(f"Alertas removidos: {removidos_alertas}")
        self.stdout.write(f"Registros removidos: {removidos_registros}")
        self.stdout.write(f"Dispositivos removidos: {removidos_dispositivos}")

    def _limpar_protect_das_empresas(self, demo_ids):
        """Apaga, das empresas demo, todos os modelos com FK PROTECT — em várias
        passadas, pois um PROTECT-filho pode bloquear outro. Descobre o vínculo
        com Empresa por FK direta (→Empresa) ou 1 hop (→modelo que tem empresa).
        Assim o delete da empresa cascateia o resto sem ProtectedError."""
        from django.apps import apps
        from django.db.models import ForeignKey, Q
        from django.db.models.deletion import PROTECT

        modelos_protect = []
        for m in apps.get_app_config("api").get_models():
            if any(isinstance(f, ForeignKey) and f.remote_field.on_delete is PROTECT
                   for f in m._meta.get_fields()):
                modelos_protect.append(m)

        def _filtro(model):
            q = Q()
            achou = False
            for f in model._meta.get_fields():
                if not isinstance(f, ForeignKey):
                    continue
                alvo = f.remote_field.model
                if alvo.__name__ == "Empresa":
                    q |= Q(**{f"{f.name}_id__in": demo_ids}); achou = True
                elif any(getattr(ff, "name", None) == "empresa" for ff in alvo._meta.get_fields()):
                    q |= Q(**{f"{f.name}__empresa_id__in": demo_ids}); achou = True
            return q if achou else None

        for _ in range(6):  # passadas suficientes p/ cadeias PROTECT aninhadas
            apagou_algo = False
            for model in modelos_protect:
                filtro = _filtro(model)
                if filtro is None:
                    continue
                try:
                    n = model.objects.using("owner").filter(filtro).delete()[0]
                    if n:
                        apagou_algo = True
                except Exception:
                    # PROTECT ainda bloqueando este nível — próxima passada resolve
                    pass
            if not apagou_algo:
                break

    def _is_production(self) -> bool:
        from django.conf import settings

        return bool(getattr(settings, "IS_PRODUCTION", False))

    def _collect_preview(self):
        return {
            "empresas_demo": Empresa.objects.using("owner").filter(email__in=DEMO_EMAILS).count(),
            "alertas_sinteticos": AlertaGovernamental.objects.using("owner").filter(q_alerta_governamental_sintetico()).count(),
            "registros_sinteticos": RegistroSintoma.objects.using("owner").filter(q_registro_sintoma_sintetico()).count(),
            "dispositivos_sinteticos": DispositivoAutorizado.objects.using("owner").filter(_q_dispositivo_sintetico()).count(),
        }

