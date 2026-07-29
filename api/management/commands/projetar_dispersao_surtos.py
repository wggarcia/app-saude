"""
Roda o modelo de dispersão (api/modelo_dispersao.py — 9º sistema de IA) sobre
os surtos ativos e grava as projeções em ProjecaoDispersao.

Fluxo:
  1. Lê SurtoEpidemiologico ativos (seed = município + casos + doença).
  2. Resolve município (texto) → código IBGE.
  3. Carrega a matriz de mobilidade mais recente (MatrizMobilidade).
  4. Para cada doença, projeta 7/14/30 dias com o SEIR metapopulacional.
  5. Grava as projeções (probabilidade de chegada + casos + rota provável).

Uso:
    python manage.py projetar_dispersao_surtos
    python manage.py projetar_dispersao_surtos --top 40   # grava só os 40 municípios de maior risco por doença/horizonte
    python manage.py projetar_dispersao_surtos --dry-run

Roda como cron logo depois de coletar_mobilidade_aerea e de detectar surtos.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from api import modelo_dispersao as md
from api import pipeline_mobilidade as pm
from api.models import MatrizMobilidade, ProjecaoDispersao, SurtoEpidemiologico


class Command(BaseCommand):
    help = "Projeta a dispersão dos surtos ativos (SEIR + mobilidade) para ProjecaoDispersao."

    def add_arguments(self, parser):
        parser.add_argument("--top", type=int, default=50,
                            help="Máx. de municípios gravados por doença/horizonte (default 50).")
        parser.add_argument("--min-prob", type=float, default=0.01,
                            help="Ignora projeções com probabilidade abaixo disto (default 0.01).")
        parser.add_argument("--dry-run", action="store_true", help="Não grava, só reporta.")

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
        dry = opts["dry_run"]

        # 1+2) seeds por doença
        seeds_por_doenca: dict = defaultdict(dict)
        nao_resolvidos = []
        for s in SurtoEpidemiologico.objects.filter(status="ativo"):
            ibge = pm.resolver_ibge(s.municipio, s.uf)
            if not ibge:
                nao_resolvidos.append(f"{s.municipio}/{s.uf}")
                continue
            # acumula casos se houver mais de um surto no mesmo município/doença
            seeds_por_doenca[s.doenca][ibge] = seeds_por_doenca[s.doenca].get(ibge, 0) + (s.total_casos or 0)

        if not seeds_por_doenca:
            self.stdout.write(self.style.WARNING("Nenhum surto ativo com município resolvível. Nada a projetar."))
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
