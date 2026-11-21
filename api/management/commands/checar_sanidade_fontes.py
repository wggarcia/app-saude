"""Avisa quando uma fonte oficial para de fazer sentido.

Por que existe: a importação do SINAN baixou o arquivo do ano errado por ~10
meses sem ninguém notar. Ela nunca deu erro — baixava, processava, não levantava
exceção. Só trazia dados que diziam 13 casos de dengue no Brasil inteiro numa
semana. Nenhum alarme tocou porque ninguém estava ouvindo.

Agora que a coleta é mensal e que o prior vivo usa esse dado para mexer no
diagnóstico, uma falha silenciosa é pior: ela não só esconde a realidade, como
passa a alterar a triagem com base em ficção.

Duas perguntas, as mesmas que denunciaram o problema original:

  1. A série parou? (último período muito antigo = coleta quebrada)
  2. A série desabou? (nível recente irrisório frente ao mesmo período do ano
     anterior = dado incompleto se passando por queda real)

A comparação é com o MESMO período do ano anterior, não com a média anual —
senão toda baixa estação viraria alarme falso.

Saída com código 1 quando encontra problema, para o cron poder reclamar.
"""
from django.core.management.base import BaseCommand

# Quantos períodos de atraso ainda são normais. O SINAN publica com semanas de
# defasagem; acima disto é a coleta que parou, não o Ministério que atrasou.
MAX_PERIODOS_ATRASO = 10

# Queda frente ao ano anterior que denuncia dado incompleto em vez de melhora
# epidemiológica. Dengue caindo 30% é notícia boa; caindo 97% é arquivo errado.
PISO_QUEDA_ANUAL = 0.15  # recente < 15% do ano passado = suspeito

# Abaixo deste volume no ano anterior a comparação não diz nada (doença rara).
VOLUME_MINIMO_COMPARAR = 5.0


class Command(BaseCommand):
    help = "Verifica se as fontes oficiais pararam ou desabaram; sai com erro se houver suspeita."

    def add_arguments(self, parser):
        parser.add_argument(
            "--indicador", type=str, default=None,
            help="Checa só um indicador (padrão: todos os registrados).",
        )

    def handle(self, *args, **options):
        from collections import defaultdict

        from api.models import FonteOficialAgregado
        from api.epidemiologia_ml import DOENCAS_REGISTRADAS

        filtro = options["indicador"]
        problemas = []
        checados = 0

        for _fonte, indicador, doenca in DOENCAS_REGISTRADAS:
            if filtro and filtro not in indicador:
                continue

            linhas = (
                FonteOficialAgregado.objects.using("owner")
                .filter(indicador=indicador)
                .values("periodo", "valor")
            )
            serie = defaultdict(float)
            for linha in linhas.iterator(chunk_size=5000):
                periodo = linha.get("periodo")
                if periodo and linha.get("valor") is not None:
                    serie[periodo] += float(linha["valor"])

            if not serie:
                continue

            checados += 1
            periodos = sorted(serie)
            ultimo = periodos[-1]

            # 1. A série parou de andar?
            # Compara pela posição na própria série: se os últimos períodos
            # publicados somem, o indicador congelou.
            recentes_reais = [p for p in periodos if p >= _periodo_menos(ultimo, MAX_PERIODOS_ATRASO)]
            if len(recentes_reais) < 2:
                problemas.append(f"{doenca} ({indicador}): série parada — último período {ultimo}")
                continue

            # 2. A série desabou frente ao mesmo período do ano anterior?
            janela = periodos[-4:]
            atual = sum(serie[p] for p in janela) / len(janela)

            anteriores = []
            for p in janela:
                try:
                    ano, resto = p.split("-", 1)
                    chave = f"{int(ano) - 1}-{resto}"
                except (ValueError, AttributeError):
                    continue
                if chave in serie:
                    anteriores.append(serie[chave])

            if len(anteriores) < 2:
                continue  # sem base de comparação, não acusa

            base = sum(anteriores) / len(anteriores)
            if base < VOLUME_MINIMO_COMPARAR:
                continue  # doença rara: variação não significa nada

            if atual < base * PISO_QUEDA_ANUAL:
                problemas.append(
                    f"{doenca} ({indicador}): desabou — {atual:.0f}/período agora "
                    f"contra {base:.0f} no mesmo período do ano passado "
                    f"({100 * atual / base:.0f}% do esperado)"
                )

        self.stdout.write(f"indicadores checados: {checados}")

        if not problemas:
            self.stdout.write(self.style.SUCCESS("Nenhuma fonte suspeita."))
            return

        self.stdout.write("")
        self.stdout.write(self.style.ERROR(f"{len(problemas)} fonte(s) suspeita(s):"))
        for p in problemas:
            self.stdout.write(self.style.ERROR(f"  • {p}"))
        self.stdout.write("")
        self.stdout.write(
            "Checar api/pipeline_oficial.py: URL com ano/data fixa é a causa conhecida "
            "(foi o que quebrou dengue/chikungunya/zika por ~10 meses em 2026)."
        )
        raise SystemExit(1)


def _periodo_menos(periodo: str, n: int) -> str:
    """Período aproximado n semanas antes. Serve só para comparação de corte —
    não precisa de calendário exato, precisa de uma régua estável."""
    try:
        ano, resto = periodo.split("-", 1)
        marcador = resto[0]  # 'S' de semana, 'M' de mês
        numero = int(resto[1:])
    except (ValueError, AttributeError, IndexError):
        return periodo

    numero -= n
    ano = int(ano)
    if numero < 1:
        ano -= 1
        numero += 52 if marcador == "S" else 12
    return f"{ano}-{marcador}{numero:02d}"
