"""
Roda o modelo de dispersão (api/modelo_dispersao.py — 9º sistema de IA) sobre os
focos ativos e grava as projeções em ProjecaoDispersao.

De onde vêm as SEMENTES (focos): do REPORTE DA POPULAÇÃO — exatamente o mesmo
dado que o mapa do gestor mostra (build_panorama_payload → layer de municípios,
que agrega RegistroSintoma do app do cidadão). A doença dominante de cada
município e o nº de casos ativos viram a semente. Assim a projeção "para onde
vai" parte do que o cidadão reportou, não de tabela paralela.

Como fonte ADICIONAL, também incorpora SurtoEpidemiologico ativos (surtos que o
gestor registrou manualmente), se houver.

Fluxo:
  1. Agrega o panorama por município → (doença dominante, casos) acima do limiar.
  2. (+) Soma SurtoEpidemiologico ativos registrados manualmente.
  3. Resolve município (texto) → código IBGE.
  4. Carrega a matriz de mobilidade real (MatrizMobilidade); se não houver, usa
     o modelo gravitacional (pipeline_mobilidade.matriz_gravitacional).
  5. Para cada doença, projeta 7/14/30 dias com o SEIR metapopulacional e grava.

Uso:
    python manage.py projetar_dispersao_surtos
    python manage.py projetar_dispersao_surtos --min-casos 30   # foco só onde há >=30 casos reportados
    python manage.py projetar_dispersao_surtos --top 40
    python manage.py projetar_dispersao_surtos --dry-run

Roda como cron logo depois de coletar_mobilidade_aerea (opcional) e da chegada
de novos reportes do cidadão.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from api import modelo_dispersao as md
from api import pipeline_mobilidade as pm
from api.epidemiologia import build_panorama_payload, _estado_para_uf
from api.models import MatrizMobilidade, ProjecaoDispersao, SurtoEpidemiologico

# Panorama do tenant DEMO (estande) — inclui a simulação riw26-, que o panorama
# real exclui por integridade. É trabalho da demo do estande e pode não existir
# em todos os ambientes (ex.: Render); por isso o import é defensivo.
try:
    from api.epidemiologia import build_demo_panorama_payload
except ImportError:  # pragma: no cover
    build_demo_panorama_payload = None


class Command(BaseCommand):
    help = "Projeta a dispersão dos surtos ativos (SEIR + mobilidade) para ProjecaoDispersao."

    def add_arguments(self, parser):
        parser.add_argument("--top", type=int, default=50,
                            help="Máx. de municípios gravados por doença/horizonte (default 50).")
        parser.add_argument("--min-prob", type=float, default=0.01,
                            help="Ignora projeções com probabilidade abaixo disto (default 0.01).")
        parser.add_argument("--min-casos", type=int, default=15,
                            help="Nº mínimo de casos reportados num município p/ virar foco (default 15).")
        parser.add_argument("--demo", action="store_true",
                            help="Semeia do panorama do tenant DEMO (estande, simulação riw26-) "
                                 "em vez do reporte real. Use na feira, junto de simulacao_estande_riw.")
        parser.add_argument("--dry-run", action="store_true", help="Não grava, só reporta.")

    def _seeds_do_reporte(self, min_casos, demo=False):
        """Focos vindos do REPORTE (mesmo dado do mapa) — real ou, se demo=True,
        do tenant demo do estande.

        Agrega o panorama por município: a doença dominante + casos ativos de
        cada município acima de `min_casos` viram semente. Retorna
        ({doenca: {ibge: casos}}, [municipios_nao_resolvidos]).
        """
        seeds = defaultdict(dict)
        nao_resolvidos = []
        if demo:
            if build_demo_panorama_payload is None:
                self.stdout.write(self.style.ERROR(
                    "--demo indisponível: build_demo_panorama_payload não existe neste ambiente."
                ))
                return seeds, nao_resolvidos
            payload_fn = build_demo_panorama_payload
        else:
            payload_fn = build_panorama_payload
        try:
            payload = payload_fn()
        except Exception as exc:  # panorama indisponível não pode derrubar o cron
            self.stdout.write(self.style.WARNING(f"Panorama indisponível ({exc}); sem focos do reporte."))
            return seeds, nao_resolvidos

        for area in payload.get("layers", {}).get("municipios", []):
            casos = int(round(area.get("total_cases") or 0))
            doenca = (area.get("dominant_disease") or "").strip()
            if casos < min_casos or doenca in ("", "Indefinido", "Sem dados"):
                continue
            uf = _estado_para_uf(area.get("estado"))
            ibge = pm.resolver_ibge(area.get("cidade") or "", uf)
            if not ibge:
                nao_resolvidos.append(f"{area.get('cidade')}/{uf or '?'}")
                continue
            seeds[doenca][ibge] = seeds[doenca].get(ibge, 0) + casos
        return seeds, nao_resolvidos

    def _carregar_matriz_norm(self):
        """MatrizMobilidade (período mais recente) → {origem: {destino: peso}}."""
        ultimo = (MatrizMobilidade.objects
                  .filter(modo=MatrizMobilidade.MODO_AEREO)
                  .order_by("-periodo").values_list("periodo", flat=True).first())
        if not ultimo:
            return {}, None
        norm = defaultdict(dict)
        for reg in MatrizMobilidade.objects.filter(modo=MatrizMobilidade.MODO_AEREO, periodo=ultimo):
            norm[str(reg.origem_ibge)][str(reg.destino_ibge)] = reg.peso
        return dict(norm), ultimo

    def handle(self, *args, **opts):
        top = max(1, opts["top"])
        min_prob = opts["min_prob"]
        min_casos = opts["min_casos"]
        demo = opts["demo"]
        dry = opts["dry_run"]

        seeds_por_doenca: dict = defaultdict(dict)
        nao_resolvidos = []

        # 1) FONTE PRIMÁRIA — reporte (real ou, com --demo, do tenant demo do estande)
        seeds_reporte, nr_rep = self._seeds_do_reporte(min_casos, demo=demo)
        for doenca, mun in seeds_reporte.items():
            for ibge, casos in mun.items():
                seeds_por_doenca[doenca][ibge] = seeds_por_doenca[doenca].get(ibge, 0) + casos
        nao_resolvidos += nr_rep
        n_focos_reporte = sum(len(m) for m in seeds_reporte.values())
        if demo:
            self.stdout.write(self.style.WARNING("Modo --demo: semeando do panorama do tenant DEMO (estande)."))

        # 2) FONTE ADICIONAL — surtos registrados manualmente pelo gestor
        n_focos_manual = 0
        for s in SurtoEpidemiologico.objects.filter(status="ativo"):
            ibge = pm.resolver_ibge(s.municipio, s.uf)
            if not ibge:
                nao_resolvidos.append(f"{s.municipio}/{s.uf}")
                continue
            seeds_por_doenca[s.doenca][ibge] = seeds_por_doenca[s.doenca].get(ibge, 0) + (s.total_casos or 0)
            n_focos_manual += 1

        self.stdout.write(
            f"Focos: {n_focos_reporte} do reporte da população (>= {min_casos} casos) "
            f"+ {n_focos_manual} de surto manual."
        )
        if not seeds_por_doenca:
            self.stdout.write(self.style.WARNING(
                "Nenhum foco com município resolvível. Sem reporte suficiente do cidadão "
                "(rode simular_pandemia_brasil no ambiente de demo) nem surto manual ativo. Nada a projetar."
            ))
            if nao_resolvidos:
                self.stdout.write("Municípios não resolvidos: " + ", ".join(sorted(set(nao_resolvidos))))
            return

        # 3) matriz de mobilidade — prioriza voo real (MatrizMobilidade); se não
        #    houver, usa o modelo gravitacional (método principal, dado público
        #    IBGE, sem licença comercial — ver pipeline_mobilidade.matriz_gravitacional).
        matriz_norm, periodo_matriz = self._carregar_matriz_norm()
        if matriz_norm:
            fonte_mobilidade = "opensky"
        else:
            todas_seeds = {ibge for seeds in seeds_por_doenca.values() for ibge in seeds}
            matriz_norm = pm.matriz_gravitacional(todas_seeds)
            fonte_mobilidade = "gravitacional"
            periodo_matriz = None
            self.stdout.write(self.style.WARNING(
                "Sem voo real (MatrizMobilidade vazia) — usando modelo GRAVITACIONAL "
                f"(mobilidade estimada por população/distância). {len(matriz_norm)} focos com rota."
            ))

        # população conhecida dos hubs (para o SEIR); ausência vira default no modelo
        populacoes = {str(k): v for k, v in pm.POPULACAO_HUBS.items()}

        total_gravado = 0
        for doenca, seeds in seeds_por_doenca.items():
            params = md.parametros_para_doenca(doenca)
            proj = md.projetar_dispersao(seeds, populacoes=populacoes, matriz_norm=matriz_norm, params=params)

            self.stdout.write(f"\n== {doenca} (R0={params.r0}, focos={len(seeds)}) ==")
            registros_doenca = []
            for horizonte, linhas in proj.items():
                selecionadas = [l for l in linhas if l["probabilidade"] >= min_prob][:top]
                for l in selecionadas:
                    geo = pm.geo_municipio(l["ibge"]) or {}
                    origem_geo = pm.geo_municipio(l["origem_provavel_ibge"]) if l["origem_provavel_ibge"] else None
                    registros_doenca.append({
                        "doenca": doenca,
                        "municipio_ibge": l["ibge"],
                        "municipio_nome": geo.get("nome", ""),
                        "uf": geo.get("uf", ""),
                        "horizonte_dias": horizonte,
                        "probabilidade": l["probabilidade"],
                        "casos_projetados": l["casos_projetados"],
                        "origem_provavel_ibge": l["origem_provavel_ibge"],
                        "origem_provavel_nome": origem_geo["nome"] if origem_geo else "",
                        "metadados": {
                            "r0": params.r0, "rho": params.rho_mobilidade,
                            "fonte_mobilidade": fonte_mobilidade,
                            "periodo_matriz": periodo_matriz,
                        },
                    })
                if selecionadas:
                    exemplo = selecionadas[0]
                    ge = pm.geo_municipio(exemplo["ibge"]) or {}
                    self.stdout.write(
                        f"  {horizonte}d: {len(selecionadas)} municípios em risco. "
                        f"Maior: {ge.get('nome', exemplo['ibge'])} "
                        f"({exemplo['probabilidade']:.0%})"
                    )

            if dry:
                continue
            with transaction.atomic():
                # limpa projeções antigas desta doença e regrava
                ProjecaoDispersao.objects.filter(doenca=doenca).delete()
                for r in registros_doenca:
                    ProjecaoDispersao.objects.create(**r)
                total_gravado += len(registros_doenca)

        if dry:
            self.stdout.write(self.style.SUCCESS("\nDry-run: nada gravado."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nOK: {total_gravado} projeções gravadas em ProjecaoDispersao."))
        if nao_resolvidos:
            self.stdout.write("Municípios de surto não resolvidos p/ IBGE: " + ", ".join(sorted(set(nao_resolvidos))))
