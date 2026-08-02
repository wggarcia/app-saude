"""
Simulação ao vivo para o estande da RIW 2026.

Uso:
    python manage.py simulacao_estande_riw

    # Limpar registros sem rodar (cleanup pós-apresentação):
    python manage.py simulacao_estande_riw --limpar

    # Criar empresa demo sem rodar (setup inicial):
    python manage.py simulacao_estande_riw --setup

Fluxo padrão (~5 min):
  [0-2 min] Fase SURTO   — casos aparecem em todo o Brasil, mapa vai enchendo
  [2-3 min] Fase PICO    — nível máximo, alertas ligados
  [3-5 min] Fase CONTROLE — casos diminuem, mapa vai esvaziando

Doenças: usa o catálogo real do classificador (api/classificador_doencas.py).
Dengue é a endemia-manchete (~60% dos casos, espalhada pelo Brasil todo),
com doenças secundárias plausíveis por região (malária/febre amarela na
Amazônia, gripe/COVID no Sul mais frio, etc.). Os sintomas gerados batem
com o perfil real de cada doença, então o mapa e o dashboard classificam
e mostram o nome da doença certa — não só um "grupo" genérico.

Endpoint que alimenta o mapa da apresentação:
  /api/simulacao-nacional/riw2026-soluscrt-demo/panorama
"""

import random
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.classificador_doencas import DOENCAS_BRASIL
from api.epidemiologia import DEMO_APP_EMAIL, DEMO_ACCESS_TOKEN, clear_panorama_cache
from api.models import Empresa, RegistroSintoma

SOURCE_MARKER = "riw2026-ao-vivo"
DEVICE_PREFIX = "riw26-"

# Endemia-manchete da simulação — bate com a abertura do pitch
# ("Vocês têm 48 horas pra conter um surto de dengue").
DOENCA_PRINCIPAL = "Dengue"
PROB_DOENCA_PRINCIPAL = 0.60  # 60% dos registros são a endemia principal

# Doenças secundárias plausíveis por região — dá textura real ao mapa sem
# diluir a narrativa (a maioria dos casos continua sendo a endemia principal).
POOL_POR_REGIAO = {
    "amazonia":     ["Malaria", "Febre Amarela", "Zika"],
    "nordeste":     ["Chikungunya", "Zika", "Febre Amarela"],
    "centro_oeste": ["Chikungunya", "Leptospirose"],
    "sudeste":      ["Chikungunya", "Zika", "Leptospirose"],
    "sul":          ["Gripe (Influenza)", "COVID-19", "Resfriado Viral"],
}

# 32 pontos cobrindo todos os estados + DF
REGIOES = [
    ("Acre",                "Rio Branco",       "Centro",           -9.9750, -67.8243, "amazonia"),
    ("Amapá",               "Macapá",           "Centro",           0.0349,  -51.0694, "amazonia"),
    ("Amazonas",            "Manaus",            "Centro",          -3.1190, -60.0217, "amazonia"),
    ("Pará",                "Belém",             "Campina",         -1.4558, -48.4902, "amazonia"),
    ("Rondônia",            "Porto Velho",       "Centro",          -8.7612, -63.9004, "amazonia"),
    ("Roraima",             "Boa Vista",         "Centro",           2.8235, -60.6758, "amazonia"),
    ("Tocantins",           "Palmas",            "Plano Diretor",  -10.1840, -48.3336, "centro_oeste"),
    ("Alagoas",             "Maceió",            "Ponta Verde",     -9.6498, -35.7089, "nordeste"),
    ("Bahia",               "Salvador",          "Centro",         -12.9777, -38.5016, "nordeste"),
    ("Ceará",               "Fortaleza",         "Centro",          -3.7319, -38.5267, "nordeste"),
    ("Maranhão",            "São Luís",          "Centro",          -2.5307, -44.3068, "nordeste"),
    ("Paraíba",             "João Pessoa",       "Centro",          -7.1195, -34.8450, "nordeste"),
    ("Pernambuco",          "Recife",            "Boa Vista",       -8.0476, -34.8770, "nordeste"),
    ("Piauí",               "Teresina",          "Centro",          -5.0892, -42.8019, "nordeste"),
    ("Rio Grande do Norte", "Natal",             "Petrópolis",      -5.7793, -35.2009, "nordeste"),
    ("Sergipe",             "Aracaju",           "Centro",         -10.9472, -37.0731, "nordeste"),
    ("Distrito Federal",    "Brasília",          "Plano Piloto",   -15.7939, -47.8828, "centro_oeste"),
    ("Goiás",               "Goiânia",           "Setor Central",  -16.6869, -49.2648, "centro_oeste"),
    ("Mato Grosso",         "Cuiabá",            "Centro",         -15.6014, -56.0979, "centro_oeste"),
    ("Mato Grosso do Sul",  "Campo Grande",      "Centro",         -20.4697, -54.6201, "centro_oeste"),
    ("Espírito Santo",      "Vitória",           "Centro",         -20.3155, -40.3128, "sudeste"),
    ("Minas Gerais",        "Belo Horizonte",    "Centro",         -19.9167, -43.9345, "sudeste"),
    ("Rio de Janeiro",      "Rio de Janeiro",    "Centro",         -22.9068, -43.1729, "sudeste"),
    ("Rio de Janeiro",      "Niterói",           "Icaraí",         -22.8897, -43.1286, "sudeste"),
    ("São Paulo",           "São Paulo",         "Pinheiros",      -23.5614, -46.7016, "sudeste"),
    ("São Paulo",           "Campinas",          "Centro",         -22.9056, -47.0608, "sudeste"),
    ("São Paulo",           "Guarulhos",         "Centro",         -23.4543, -46.5332, "sudeste"),
    ("Paraná",              "Curitiba",          "Centro",         -25.4284, -49.2733, "sul"),
    ("Rio Grande do Sul",   "Porto Alegre",      "Centro Histórico",-30.0346,-51.2177, "sul"),
    ("Santa Catarina",      "Florianópolis",     "Centro",         -27.5949, -48.5482, "sul"),
    ("Mato Grosso",         "Sinop",             "Centro",         -11.8619, -55.5139, "centro_oeste"),
    ("Bahia",               "Feira de Santana",  "Centro",         -12.2597, -38.9601, "nordeste"),
]

# Campos de RegistroSintoma que recebem os sintomas (o resto das chaves em
# DOENCAS_BRASIL[doenca]["sintomas"] começa com "_" — são bônus de score
# internos do classificador, não sintomas reais do formulário).
_CAMPOS_INTENSIDADE = {"_intensidade_febre_alta", "_intensidade_febre_baixa",
                       "_intensidade_articular_leve", "_intensidade_articular_intensa"}


def _escolher_doenca(perfil_regiao):
    if random.random() < PROB_DOENCA_PRINCIPAL:
        return DOENCA_PRINCIPAL
    pool = POOL_POR_REGIAO.get(perfil_regiao, [DOENCA_PRINCIPAL])
    return random.choice(pool)


def _sintomas_para_doenca(doenca):
    """Gera sintomas booleanos batendo com o perfil real da doença
    (usa os pesos positivos de DOENCAS_BRASIL como probabilidade de presença)."""
    info = DOENCAS_BRASIL.get(doenca, DOENCAS_BRASIL[DOENCA_PRINCIPAL])
    pesos = info["sintomas"]
    sintomas = {}
    for campo, peso in pesos.items():
        if campo in _CAMPOS_INTENSIDADE:
            continue
        prob = max(0.0, peso)  # pesos negativos = "contra" no classificador, não presença real
        sintomas[campo] = random.random() < prob

    if not any(sintomas.values()):
        sintomas["febre"] = True  # garante ao menos um sintoma sempre presente

    intensidade_febre = ""
    if pesos.get("_intensidade_febre_alta", 0) > 0:
        intensidade_febre = "alta"
    elif pesos.get("_intensidade_febre_baixa", 0) > 0:
        intensidade_febre = "baixa"
    elif sintomas.get("febre"):
        intensidade_febre = "moderada"

    intensidade_articular = ""
    if pesos.get("_intensidade_articular_intensa", 0) > 0:
        intensidade_articular = "intensa"
    elif pesos.get("_intensidade_articular_leve", 0) > 0:
        intensidade_articular = "leve"
    elif sintomas.get("dor_articular"):
        intensidade_articular = "moderada"

    return sintomas, intensidade_febre, intensidade_articular


def _criar_registro(empresa, estado, cidade, bairro, lat, lon, perfil_regiao, device_id):
    doenca = _escolher_doenca(perfil_regiao)
    sintomas, intensidade_febre, intensidade_articular = _sintomas_para_doenca(doenca)
    grupo = DOENCAS_BRASIL.get(doenca, {}).get("grupo", "")

    campos = {
        "empresa": empresa,
        "device_id": device_id,
        "latitude": lat + random.uniform(-0.04, 0.04),
        "longitude": lon + random.uniform(-0.04, 0.04),
        "estado": estado,
        "cidade": cidade,
        "bairro": bairro,
        "doenca": doenca,
        "grupo": grupo,
        "intensidade_febre": intensidade_febre,
        "intensidade_articular": intensidade_articular,
        "fonte_referencia": SOURCE_MARKER,
        "suspeito": False,
        "confianca": round(random.uniform(0.72, 0.99), 2),
        "data_registro": timezone.now(),
    }
    campos.update(sintomas)
    return RegistroSintoma(**campos)


def _injetar_lote(empresa, regioes, n_por_regiao, device_counter):
    objs = []
    for estado, cidade, bairro, lat, lon, perfil_regiao in regioes:
        for _ in range(n_por_regiao):
            did = f"{DEVICE_PREFIX}{device_counter[0]:06d}"
            device_counter[0] += 1
            objs.append(_criar_registro(empresa, estado, cidade, bairro, lat, lon, perfil_regiao, did))
    RegistroSintoma.objects.bulk_create(objs, ignore_conflicts=True)
    clear_panorama_cache()
    return len(objs)


def _remover_lote(empresa, n):
    ids = list(
        RegistroSintoma.objects
        .filter(empresa=empresa, fonte_referencia=SOURCE_MARKER)
        .order_by("data_registro")
        .values_list("id", flat=True)[:n]
    )
    if ids:
        RegistroSintoma.objects.filter(id__in=ids).delete()
        clear_panorama_cache()
    return len(ids)


class Command(BaseCommand):
    help = "Simulação ao vivo para o estande da RIW 2026 — mapa enche e esvazia em ~5 min."

    def add_arguments(self, parser):
        parser.add_argument(
            "--setup",
            action="store_true",
            help="Apenas cria a empresa demo e sai (rode uma vez antes da apresentação).",
        )
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Remove todos os registros demo e sai.",
        )
        parser.add_argument(
            "--duracao",
            type=int,
            default=300,
            help="Duração total em segundos (padrão: 300 = 5 min).",
        )
        parser.add_argument(
            "--pico",
            type=int,
            default=20,
            help="Registros por região no pico máximo (padrão: 20).",
        )

    def handle(self, *args, **options):
        empresa = self._obter_ou_criar_empresa()
        if empresa is None:
            self.stderr.write(self.style.ERROR("Falha ao obter empresa demo. Abortando."))
            return

        if options["setup"]:
            self.stdout.write(self.style.SUCCESS(
                f"\nEmpresa demo pronta: {DEMO_APP_EMAIL}\n"
                f"Token de acesso: {DEMO_ACCESS_TOKEN}\n"
                f"Endpoint: /api/simulacao-nacional/{DEMO_ACCESS_TOKEN}/panorama\n"
            ))
            return

        if options["limpar"]:
            n = RegistroSintoma.objects.filter(empresa=empresa, fonte_referencia=SOURCE_MARKER).count()
            RegistroSintoma.objects.filter(empresa=empresa, fonte_referencia=SOURCE_MARKER).delete()
            clear_panorama_cache()
            self.stdout.write(self.style.SUCCESS(f"{n} registros demo removidos."))
            return

        self._rodar_simulacao(empresa, options["duracao"], options["pico"])

    def _obter_ou_criar_empresa(self):
        try:
            empresa = Empresa.objects.filter(email=DEMO_APP_EMAIL).first()
            if empresa:
                return empresa
            empresa = Empresa.objects.create(
                email=DEMO_APP_EMAIL,
                senha="",
                nome="Demo Estande RIW 2026",
                tipo_conta=Empresa.TIPO_GOVERNO,
                pacote_codigo="governo_municipio_pequeno",
                ativo=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Empresa demo criada: {empresa.pk}"))
            return empresa
        except Exception as e:
            self.stderr.write(f"Erro ao criar empresa demo: {e}")
            return None

    def _rodar_simulacao(self, empresa, duracao_total, pico_por_regiao):
        # Limpar registros antigos antes de começar
        RegistroSintoma.objects.filter(empresa=empresa, fonte_referencia=SOURCE_MARKER).delete()
        clear_panorama_cache()

        duracao_surto   = int(duracao_total * 0.40)  # 40% do tempo subindo
        duracao_pico    = int(duracao_total * 0.20)  # 20% no pico
        duracao_queda   = duracao_total - duracao_surto - duracao_pico  # 40% descendo

        # Quantas ondas de injeção na fase de surto
        n_ondas_surto = 8
        intervalo_surto = duracao_surto / n_ondas_surto
        # Registros por região por onda (sobe gradualmente)
        doses_surto = [max(1, round(pico_por_regiao * (i + 1) / n_ondas_surto))
                       for i in range(n_ondas_surto)]

        n_ondas_queda = 10
        intervalo_queda = duracao_queda / n_ondas_queda

        device_counter = [1]
        total_injetados = 0

        doencas_da_rodada = sorted({DOENCA_PRINCIPAL, *[d for pool in POOL_POR_REGIAO.values() for d in pool]})
        self.stdout.write(self.style.WARNING(
            f"\n{'='*60}\n"
            f"  SIMULAÇÃO ESTANDE RIW 2026 — SolusCRT\n"
            f"  Endemia principal: {DOENCA_PRINCIPAL} (~{int(PROB_DOENCA_PRINCIPAL*100)}% dos casos)\n"
            f"  Doenças em jogo: {', '.join(doencas_da_rodada)}\n"
            f"  Duração: {duracao_total}s | Pico: {pico_por_regiao} reg/região\n"
            f"  Endpoint: /api/simulacao-nacional/{DEMO_ACCESS_TOKEN}/panorama\n"
            f"{'='*60}\n"
        ))

        # ── FASE 1: SURTO ─────────────────────────────────────────────
        self.stdout.write(self.style.ERROR(f"▲ FASE SURTO — {DOENCA_PRINCIPAL} se espalhando por todo o Brasil"))
        for onda in range(n_ondas_surto):
            dose = doses_surto[onda]
            regioes_onda = random.sample(REGIOES, min(len(REGIOES), len(REGIOES)))
            n = _injetar_lote(empresa, regioes_onda, dose, device_counter)
            total_injetados += n
            self.stdout.write(
                f"  Onda {onda+1}/{n_ondas_surto}: +{n} registros "
                f"(total: {total_injetados}) [{len(regioes_onda)} estados]"
            )
            time.sleep(intervalo_surto)

        # ── FASE 2: PICO ──────────────────────────────────────────────
        self.stdout.write(self.style.ERROR(
            f"\n⚠  FASE PICO — {total_injetados} casos ativos em todo o Brasil"
        ))
        tick = 5
        for _ in range(duracao_pico // tick):
            time.sleep(tick)
            self.stdout.write(f"  [pico] {total_injetados} casos | {timezone.now().strftime('%H:%M:%S')}")

        # ── FASE 3: CONTROLE ──────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n▼ FASE CONTROLE — sistema identifica, alertas disparam, casos diminuem"))
        por_onda = total_injetados // n_ondas_queda
        restantes = total_injetados
        for onda in range(n_ondas_queda):
            n_remover = por_onda if onda < n_ondas_queda - 1 else restantes
            removidos = _remover_lote(empresa, n_remover)
            restantes -= removidos
            self.stdout.write(
                f"  Onda {onda+1}/{n_ondas_queda}: -{removidos} registros "
                f"(restantes: {restantes})"
            )
            time.sleep(intervalo_queda)

        # Garante que não sobrou nada
        sobrou = RegistroSintoma.objects.filter(empresa=empresa, fonte_referencia=SOURCE_MARKER).count()
        if sobrou:
            RegistroSintoma.objects.filter(empresa=empresa, fonte_referencia=SOURCE_MARKER).delete()
            clear_panorama_cache()

        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*60}\n"
            f"  Simulação concluída! Mapa limpo.\n"
            f"  Para repetir: python manage.py simulacao_estande_riw\n"
            f"{'='*60}\n"
        ))
