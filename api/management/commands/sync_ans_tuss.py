"""
sync_ans_tuss — Sincroniza a Terminologia TUSS da ANS para o espelho local.

Fonte: API oficial OpenConceptLab da ANS (ver api/services/ans_tuss.py).

Estratégia por tamanho de tabela:
  - tuss-22 (Procedimentos ~6 mil), tuss-18 (~3,6 mil), tuss-20 (Medicamentos):
    dá para sincronizar por completo — é o default de `--todas`.
  - tuss-19 (OPME) tem ~1,4 MILHÃO de itens: NÃO se baixa inteira. Aqui ela é
    sincronizada de forma dirigida:
      * `--busca "stent"` traz só o que casa com o termo, ou
      * `--revalidar-catalogo` revalida apenas os códigos TUSS já usados no
        catálogo OPME das empresas (atualiza registro ANVISA e vigência).
    A busca ao vivo da tela cobre o resto sob demanda.

Uso:
  python manage.py sync_ans_tuss --todas
  python manage.py sync_ans_tuss --tabela tuss-22
  python manage.py sync_ans_tuss --tabela tuss-19 --busca stent --limite 20
  python manage.py sync_ans_tuss --revalidar-catalogo
  python manage.py sync_ans_tuss --tabela tuss-22 --dry-run
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from api.services import ans_tuss

logger = logging.getLogger(__name__)

# Tabelas sincronizadas por inteiro no --todas (pequenas o bastante).
TABELAS_COMPLETAS = ["tuss-22", "tuss-18", "tuss-20"]


class Command(BaseCommand):
    help = "Sincroniza a Terminologia TUSS da ANS (procedimentos, materiais, medicamentos)."

    def add_arguments(self, parser):
        parser.add_argument("--tabela", help="Uma tabela específica, ex.: tuss-22")
        parser.add_argument("--busca", default="", help="Filtra por termo (obrigatório p/ tuss-19)")
        parser.add_argument("--limite", type=int, default=0,
                            help="Máximo de PÁGINAS (25 itens cada). 0 = sem limite")
        parser.add_argument("--todas", action="store_true",
                            help=f"Sincroniza as tabelas completas: {', '.join(TABELAS_COMPLETAS)}")
        parser.add_argument("--revalidar-catalogo", action="store_true",
                            help="Revalida na ANS só os códigos já usados no catálogo OPME")
        parser.add_argument("--dry-run", action="store_true", help="Não grava — só conta")

    # ── gravação em lote de uma leva de itens normalizados ──────────────────────
    def _gravar(self, itens, dry):
        from api.models import TerminologiaTuss
        if dry:
            return len(itens), 0
        criados = atualizados = 0
        nomes = ans_tuss.TABELAS_RELEVANTES
        with transaction.atomic():
            for d in itens:
                if not d["tabela"] or not d["codigo"]:
                    continue
                d = dict(d, tabela_nome=nomes.get(d["tabela"], ""))
                _, created = TerminologiaTuss.objects.update_or_create(
                    tabela=d["tabela"], codigo=d["codigo"],
                    defaults={k: v for k, v in d.items()
                              if k not in ("tabela", "codigo")})
                criados += int(created)
                atualizados += int(not created)
        return criados, atualizados

    def _sync_tabela(self, tabela, termo, max_paginas, dry):
        self.stdout.write(f"→ {tabela}"
                          + (f" (busca: {termo!r})" if termo else "")
                          + (f" [máx {max_paginas} págs]" if max_paginas else ""))
        buffer, criados, atualizados, total = [], 0, 0, 0
        try:
            for item in ans_tuss.iterar_tabela(tabela, termo, max_paginas):
                buffer.append(item)
                total += 1
                if len(buffer) >= 500:
                    c, a = self._gravar(buffer, dry)
                    criados += c; atualizados += a; buffer = []
            if buffer:
                c, a = self._gravar(buffer, dry)
                criados += c; atualizados += a
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"  falha em {tabela}: {e}"))
            logger.exception("sync_ans_tuss falhou em %s", tabela)
            return 0, 0, total
        pfx = "[dry-run] " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"  {pfx}{total} itens · {criados} novos, {atualizados} atualizados"))
        return criados, atualizados, total

    def _revalidar_catalogo(self, dry):
        """tuss-19 dirigido: para cada registro ANVISA já no catálogo OPME das
        empresas, busca o material correspondente na tabela 19 da ANS e atualiza o
        espelho local (traz o código TUSS oficial, fabricante e vigência). Fecha o
        laço que o usuário faz hoje à mão entre ANVISA ↔ TUSS ↔ catálogo."""
        from api.models import CatalogoOPME
        registros = sorted({
            "".join(ch for ch in (c or "") if ch.isdigit())
            for c in CatalogoOPME.objects
            .exclude(codigo_anvisa="").values_list("codigo_anvisa", flat=True)
        } - {""})
        if not registros:
            self.stdout.write("Nenhum registro ANVISA no catálogo OPME para revalidar.")
            return
        self.stdout.write(f"Revalidando {len(registros)} registro(s) ANVISA do catálogo na ANS…")
        achados = []
        for reg in registros:
            # busca o registro na tabela 19 e mantém quem casa pelo registro ANVISA
            for item in ans_tuss.buscar_ao_vivo("tuss-19", reg, limite=25):
                if item["registro_anvisa"] == reg:
                    achados.append(item)
        criados, atualizados = self._gravar(achados, dry)
        pfx = "[dry-run] " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"  {pfx}{len(achados)}/{len(registros)} encontrados · "
            f"{criados} novos, {atualizados} atualizados"))

    def handle(self, *args, **opts):
        dry = opts.get("dry_run")
        termo = (opts.get("busca") or "").strip()
        max_paginas = opts.get("limite") or 0

        if opts.get("revalidar_catalogo"):
            self._revalidar_catalogo(dry)

        alvos = []
        if opts.get("tabela"):
            alvos = [opts["tabela"]]
        elif opts.get("todas"):
            alvos = TABELAS_COMPLETAS

        if not alvos and not opts.get("revalidar_catalogo"):
            self.stdout.write(self.style.WARNING(
                "Nada a fazer. Use --todas, --tabela <cod> ou --revalidar-catalogo."))
            return

        # tuss-19 sem termo e sem limite seria baixar 1,4M — barra por segurança.
        for tabela in alvos:
            if tabela == "tuss-19" and not termo and not max_paginas:
                self.stderr.write(self.style.WARNING(
                    "tuss-19 é gigante (~1,4M). Use --busca <termo> ou "
                    "--revalidar-catalogo, ou --limite <páginas>. Pulando."))
                continue
            self._sync_tabela(tabela, termo, max_paginas, dry)
