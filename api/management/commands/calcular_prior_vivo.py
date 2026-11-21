"""Calcula o prior vivo: quanto cada doença está fora do SEU próprio normal, por UF.

Lê notificação oficial já importada (SINAN/DATASUS em FonteOficialAgregado) e,
para cada (doença, estado), compara o período recente com a linha de base
histórica DAQUELA MESMA doença naquele mesmo estado.

O que este comando NÃO faz, de propósito:
  • Não compara doenças entre si pelo volume de notificação. Dengue tem ~21 mil
    linhas na base e coqueluche ~880 — isso mede o esforço de coleta de cada
    sistema, não a prevalência real. Virar prior, criaria hierarquia inventada.
  • Não inventa sinal onde não há série: abaixo de MIN_AMOSTRAS, a doença
    simplesmente não ganha fator e segue com o prior fixo da literatura.
  • Não toca no panorama nem no classificador em tempo de execução — grava uma
    tabela que eles leem depois. Sem realimentação: a fonte é dado oficial, não
    a saída do próprio sistema.

Seguro por padrão: sem --aplicar, apenas simula.
"""
from django.core.management.base import BaseCommand

# Faixa estreita de propósito: o sinal AJUSTA o prior, nunca o substitui.
# Uma doença rara não vira comum porque teve um mês movimentado.
FATOR_MIN = 0.5
FATOR_MAX = 2.0

# Períodos recentes que formam o "agora"; o resto da série é a linha de base.
PERIODOS_RECENTES = 4
MIN_AMOSTRAS = 8  # abaixo disso não há série suficiente para afirmar nada

# O registro oficial e o classificador escrevem alguns nomes de formas
# diferentes (acento, nome completo). Sem isto, o fator cairia num nome que o
# prior não conhece e seria descartado silenciosamente.
_NOME_OFICIAL_PARA_CLASSIFICADOR = {
    "Gripe": "Gripe (Influenza)",
    "Doenca de Chagas": "Doença de Chagas",
    "Hanseniase": "Hanseníase",
    "Colera": "Cólera",
}


class Command(BaseCommand):
    help = "Calcula o fator de atividade (prior vivo) por doença e UF, a partir de dado oficial."

    def add_arguments(self, parser):
        parser.add_argument("--aplicar", action="store_true", help="Grava de verdade (sem isto, simula).")
        parser.add_argument("--doenca", type=str, default=None, help="Restringe a uma doença.")

    def handle(self, *args, **options):
        from collections import defaultdict

        from api.models import FonteOficialAgregado, PriorVivoEpidemiologico
        from api.epidemiologia_ml import DOENCAS_REGISTRADAS
        from api.classificador_doencas import _PRIOR_DEFAULT

        aplicar = options["aplicar"]
        filtro_doenca = options["doenca"]

        if not aplicar:
            self.stdout.write(self.style.WARNING("MODO SIMULAÇÃO — nada será gravado (use --aplicar)."))

        gravados = 0
        sem_serie = 0
        linhas = []

        for _fonte_id, indicador, doenca_oficial in DOENCAS_REGISTRADAS:
            doenca = _NOME_OFICIAL_PARA_CLASSIFICADOR.get(doenca_oficial, doenca_oficial)

            # Sem prior na literatura, não há o que ajustar.
            if doenca not in _PRIOR_DEFAULT:
                continue
            if filtro_doenca and filtro_doenca.lower() not in doenca.lower():
                continue

            # Série por (estado, período) — só o que tem UF identificada.
            registros = (
                FonteOficialAgregado.objects.using("owner")
                .filter(indicador=indicador)
                .exclude(estado__isnull=True)
                .exclude(estado="")
                .values("estado", "periodo", "valor")
            )

            serie_por_estado = defaultdict(dict)
            for r in registros.iterator(chunk_size=5000):
                periodo = r.get("periodo")
                valor = r.get("valor")
                if not periodo or valor is None:
                    continue
                uf = (r["estado"] or "").strip().upper()[:10]
                # Mesmo período pode vir em várias linhas (municípios): soma.
                serie_por_estado[uf][periodo] = serie_por_estado[uf].get(periodo, 0.0) + float(valor)

            for uf, por_periodo in serie_por_estado.items():
                if len(por_periodo) < MIN_AMOSTRAS:
                    sem_serie += 1
                    continue

                periodos = sorted(por_periodo)  # "2026-S21" ordena bem lexicograficamente
                recentes = [por_periodo[p] for p in periodos[-PERIODOS_RECENTES:]]
                base = [por_periodo[p] for p in periodos[:-PERIODOS_RECENTES]]
                if not base:
                    sem_serie += 1
                    continue

                media_recente = sum(recentes) / len(recentes)
                media_base = sum(base) / len(base)
                if media_base <= 0:
                    sem_serie += 1
                    continue

                fator = media_recente / media_base
                fator = max(FATOR_MIN, min(fator, FATOR_MAX))

                linhas.append((doenca, uf, fator, media_recente, media_base, len(base)))

                if aplicar:
                    PriorVivoEpidemiologico.objects.using("owner").update_or_create(
                        doenca=doenca, estado=uf,
                        defaults={
                            "fator": round(fator, 3),
                            "valor_recente": round(media_recente, 2),
                            "valor_base": round(media_base, 2),
                            "amostras": len(base),
                            "fonte_indicador": indicador[:80],
                        },
                    )
                gravados += 1

        # Mostra os maiores desvios — é onde o prior vivo realmente muda algo.
        linhas.sort(key=lambda x: abs(x[2] - 1.0), reverse=True)
        self.stdout.write("")
        self.stdout.write("Maiores desvios do próprio normal:")
        for doenca, uf, fator, rec, base, n in linhas[:15]:
            seta = "acima" if fator > 1 else "abaixo"
            self.stdout.write(
                f"  {doenca[:24]:<24} {uf:<3} fator {fator:5.2f} ({seta}) "
                f"| recente {rec:9.1f} vs base {base:9.1f} | n={n}"
            )

        self.stdout.write("")
        self.stdout.write(f"pares (doença, UF) com sinal: {gravados} | sem série suficiente: {sem_serie}")

        if aplicar:
            try:
                from api.classificador_doencas import limpar_cache_prior_vivo
                limpar_cache_prior_vivo()
                self.stdout.write("cache do prior vivo limpo")
            except Exception:
                pass
            self.stdout.write(self.style.SUCCESS("Prior vivo gravado."))
        else:
            self.stdout.write(self.style.WARNING("Nada gravado (simulação). Rode com --aplicar."))
