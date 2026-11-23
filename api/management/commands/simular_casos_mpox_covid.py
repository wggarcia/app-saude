# -*- coding: utf-8 -*-
"""Gera casos simulados de Mpox e COVID-19 na Região Metropolitana do Rio.

Para que serve
--------------
Encher o mapa com um cenário plausível — demonstração, treinamento de equipe,
teste de carga do panorama. NÃO é dado real e não deve ser tratado como tal.

O que torna isto diferente da simulação antiga
----------------------------------------------
A carga anterior deixou 2.000 registros indistinguíveis de envio real: todos
numa única hora, com device_id sequencial e sem IP. Levei meia sessão para
descobrir que não era gente. Aqui a procedência diz o que é, em texto, no
próprio registro:

    fonte_referencia = "simulacao-mpox-covid-<data>"

Remover tudo depois é uma linha:

    RegistroSintoma.objects.using("owner").filter(
        fonte_referencia__startswith="simulacao-mpox-covid").delete()

Como os casos são montados
--------------------------
Não se escreve a doença no registro: escrevem-se SINTOMAS, e o motor bayesiano
classifica. Se o perfil clínico não sustentar a doença pretendida, o caso sai
com outro nome — e o comando reporta isso em vez de esconder. É o mesmo motor
que atende o cidadão, com as mesmas perguntas de desempate.

Para o Mpox isso significa responder as quatro perguntas das vesículas; para a
COVID, o perfil respiratório com perda de olfato. Os casos variam: nem todo
mundo responde tudo, nem todo mundo tem febre, e a duração dos sintomas muda.
Caso idêntico em série é o que denuncia simulação.
"""

import random
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


MARCA = "simulacao-mpox-covid"

# Bairros por município, com coordenada aproximada do bairro.
# Aproximada de propósito: é simulação, e a precisão de rua não acrescenta
# nada ao mapa de bairro. O jitter abaixo espalha os casos dentro do bairro.
# O geocoder de produção grava o estado POR EXTENSO ("Rio de Janeiro"), não a
# sigla. Gravar "RJ" fazia o panorama agrupar separado e Niterói aparecer duas
# vezes no mapa — uma com os casos simulados, outra com o caso real.
UF_POR_EXTENSO = "Rio de Janeiro"

TERRITORIO = {
    "Niterói": {
        "uf": "RJ",
        "bairros": {
            "Icaraí": (-22.9070, -43.1050), "Centro": (-22.8930, -43.1230),
            "Fonseca": (-22.8800, -43.0960), "Santa Rosa": (-22.9010, -43.0960),
            "Piratininga": (-22.9430, -43.0700), "Itaipu": (-22.9560, -43.0450),
            "Barreto": (-22.8730, -43.1070), "São Francisco": (-22.9250, -43.0900),
            "Ingá": (-22.8990, -43.1130), "Pendotiba": (-22.9290, -43.0790),
        },
    },
    "São Gonçalo": {
        "uf": "RJ",
        "bairros": {
            "Centro": (-22.8270, -43.0530), "Alcântara": (-22.8210, -43.0040),
            "Neves": (-22.8560, -43.0840), "Trindade": (-22.8060, -43.0170),
            "Mutuá": (-22.8390, -43.0420), "Colubandê": (-22.8130, -43.0300),
            "Porto Novo": (-22.8350, -43.0620), "Jardim Catarina": (-22.7830, -42.9950),
        },
    },
    "Maricá": {
        "uf": "RJ",
        "bairros": {
            "Centro": (-22.9190, -42.8190), "Itaipuaçu": (-22.9560, -42.9330),
            "Inoã": (-22.9260, -42.9000), "Ponta Negra": (-22.9490, -42.6980),
            "São José do Imbassaí": (-22.8930, -42.8520), "Araçatiba": (-22.9100, -42.8760),
        },
    },
    "Rio de Janeiro": {
        "uf": "RJ",
        "bairros": {
            "Copacabana": (-22.9700, -43.1860), "Campo Grande": (-22.9050, -43.5600),
            "Bangu": (-22.8780, -43.4670), "Tijuca": (-22.9240, -43.2320),
            "Madureira": (-22.8730, -43.3380), "Centro": (-22.9060, -43.1760),
            "Realengo": (-22.8830, -43.4290), "Santa Cruz": (-22.9180, -43.6850),
            "Penha": (-22.8390, -43.2770), "Méier": (-22.9020, -43.2800),
        },
    },
    # Baixada Fluminense
    "Duque de Caxias": {
        "uf": "RJ",
        "bairros": {
            "Centro": (-22.7850, -43.3050), "Jardim Primavera": (-22.7320, -43.2900),
            "Campos Elíseos": (-22.7000, -43.2800), "Xerém": (-22.5830, -43.3000),
        },
    },
    "Nova Iguaçu": {
        "uf": "RJ",
        "bairros": {
            "Centro": (-22.7590, -43.4510), "Austin": (-22.7240, -43.5240),
            "Comendador Soares": (-22.7820, -43.4290), "Posse": (-22.7700, -43.4700),
        },
    },
    "São João de Meriti": {
        "uf": "RJ",
        "bairros": {"Centro": (-22.8040, -43.3720), "Vilar dos Teles": (-22.7900, -43.3500),
                    "Coelho da Rocha": (-22.7960, -43.3880)},
    },
    "Belford Roxo": {
        "uf": "RJ",
        "bairros": {"Centro": (-22.7640, -43.3990), "Heliópolis": (-22.7520, -43.4100),
                    "Santa Teresa": (-22.7700, -43.3870)},
    },
    "Nilópolis": {"uf": "RJ", "bairros": {"Centro": (-22.8080, -43.4140),
                                          "Olinda": (-22.8010, -43.4260)}},
    "Mesquita": {"uf": "RJ", "bairros": {"Centro": (-22.7830, -43.4290),
                                         "Banco de Areia": (-22.7960, -43.4380)}},
    "Queimados": {"uf": "RJ", "bairros": {"Centro": (-22.7160, -43.5550)}},
    "Magé": {"uf": "RJ", "bairros": {"Centro": (-22.6530, -43.0400),
                                     "Piabetá": (-22.6180, -43.1510)}},
}


def _perfil_covid(rnd):
    """Quadro respiratório agudo com os achados que separam de gripe.

    O motor separa COVID de gripe por pouco: no escore bruto a diferença está
    em perda de olfato (1,00 contra 0,20) e falta de ar (0,88 contra 0,40), e o
    prior da gripe é MAIOR (0,55 contra 0,50). Tudo o mais é igual.

    Medido: a primeira versão deste perfil dava mialgia, febre alta, coriza e
    início abrupto a 60% dos casos — o retrato da gripe — e 96 de 180 casos
    saíam como "Gripe (Influenza)", mesmo com perda de olfato presente. Não era
    erro do motor; era o perfil pedindo gripe e esperando COVID.

    Então aqui o perfil se apoia nos discriminadores e se afasta do que puxa
    para gripe. O preço é honesto e fica registrado: este conjunto tem mais
    anosmia e menos mialgia que uma coorte real de COVID. É o custo de pedir
    casos que apareçam como COVID no mapa.
    """
    d = {
        "tosse": rnd.random() < 0.88,
        "febre": rnd.random() < 0.62,
        "cansaco": rnd.random() < 0.70,
        "dor_garganta": rnd.random() < 0.50,
        "dor_cabeca": rnd.random() < 0.45,
        "perda_olfato_paladar": rnd.random() < 0.92,
        "coriza": rnd.random() < 0.20,
        "dor_corpo": rnd.random() < 0.18,       # mialgia puxa para gripe
        "falta_ar": rnd.random() < 0.34,        # puxa para COVID
        "tosse_mais_3_semanas": False,
        "tosse_paroxistica": False,
        "dias_sintomas": rnd.choice([2, 3, 3, 4, 4, 5, 6, 7]),
        "inicio_abrupto": rnd.random() < 0.25,  # gripe é a de início abrupto
    }
    if not d["tosse"] and not d["perda_olfato_paladar"]:
        d["tosse"] = True
    if d["febre"]:
        # Febre alta pesa para gripe; a COVID aqui fica em baixa/moderada.
        d["intensidade_febre"] = rnd.choice(["baixa", "moderada", "moderada"])
    if d["falta_ar"]:
        d["dispneia_subita_pos_febre"] = False
        d["dispneia_piora_deitado"] = False
    if rnd.random() < 0.18:
        d["tem_comorbidade"] = True
        d[rnd.choice(["tem_diabetes", "tem_hipertensao", "tem_doenca_pulmonar"])] = True
    return d


def _perfil_mpox(rnd):
    """Lesão vesicular com os achados que separam de varicela."""
    d = {
        "exantema_vesicular": True,  # a porta; sem isto não há desempate
        "febre": rnd.random() < 0.80,
        "dor_corpo": rnd.random() < 0.58,
        "cansaco": rnd.random() < 0.52,
        "dor_cabeca": rnd.random() < 0.35,
        # Os quatro desempates. Nem todo mundo responde tudo — None é
        # "não perguntado", e isso acontece de verdade.
        "vesicula_dolorosa": True if rnd.random() < 0.85 else None,
        "linfonodo_aumentado": True if rnd.random() < 0.88 else None,
        "lesao_face_palmas": True if rnd.random() < 0.72 else None,
        "vesiculas_estagios_variados": False if rnd.random() < 0.80 else None,
        "dias_sintomas": rnd.choice([3, 4, 5, 5, 6, 7, 8, 10]),
        "contato_caso_confirmado": True if rnd.random() < 0.30 else None,
    }
    # Pelo menos dois achados positivos, senão o motor — com razão — devolve
    # varicela, que é a doença comum do quadro vesicular.
    positivos = [c for c in ("vesicula_dolorosa", "linfonodo_aumentado",
                             "lesao_face_palmas") if d.get(c) is True]
    while len(positivos) < 2:
        falta = rnd.choice([c for c in ("vesicula_dolorosa", "linfonodo_aumentado",
                                        "lesao_face_palmas") if c not in positivos])
        d[falta] = True
        positivos.append(falta)
    if d["febre"]:
        d["intensidade_febre"] = rnd.choice(["baixa", "moderada", "moderada"])
    if rnd.random() < 0.10:
        d["tem_comorbidade"] = True
        d["tem_imunossupressao"] = True
    return d


class Command(BaseCommand):
    help = "Gera casos simulados de Mpox e COVID-19 na Região Metropolitana do Rio."

    def add_arguments(self, parser):
        parser.add_argument("--total", type=int, default=300)
        parser.add_argument("--mpox", type=int, default=120,
                            help="quantos dos --total são Mpox; o resto é COVID")
        parser.add_argument("--dias", type=int, default=21,
                            help="janela para trás em que os casos se distribuem")
        parser.add_argument("--semente", type=int, default=20261123)
        parser.add_argument("--aplicar", action="store_true",
                            help="sem isto, classifica e relata sem gravar nada")

    def handle(self, *args, **o):
        from django.db import transaction
        from api.models import Empresa, RegistroSintoma
        from api.views import classificar_padrao_completo

        rnd = random.Random(o["semente"])
        total, n_mpox, dias = o["total"], o["mpox"], o["dias"]
        n_covid = total - n_mpox
        aplicar = o["aplicar"]

        if n_covid < 0:
            self.stderr.write("--mpox não pode ser maior que --total")
            return

        empresa = Empresa.objects.filter(email="populacao@solocrt.com").first()
        if not empresa:
            self.stderr.write("Tenant público (populacao@solocrt.com) não encontrado.")
            return

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                "MODO SIMULAÇÃO — nada será gravado (use --aplicar).\n"))

        marca = "%s-%s" % (MARCA, timezone.localtime().strftime("%Y%m%d"))
        agora = timezone.now()
        alvos = ["Mpox"] * n_mpox + ["COVID-19"] * n_covid
        rnd.shuffle(alvos)

        municipios = list(TERRITORIO)
        # Peso por tamanho: a capital e a Baixada concentram, como na vida real.
        pesos = {"Rio de Janeiro": 34, "São Gonçalo": 13, "Duque de Caxias": 10,
                 "Nova Iguaçu": 10, "Niterói": 9, "São João de Meriti": 6,
                 "Belford Roxo": 5, "Maricá": 5, "Mesquita": 3, "Nilópolis": 2,
                 "Magé": 2, "Queimados": 1}

        resultados = []
        registros = []
        datas = []  # data_registro pretendida de cada registro — ver abaixo
        for alvo in alvos:
            cidade = rnd.choices(municipios, weights=[pesos.get(m, 1) for m in municipios])[0]
            info = TERRITORIO[cidade]
            bairro = rnd.choice(list(info["bairros"]))
            blat, blon = info["bairros"][bairro]
            # Espalha dentro do bairro (~1 km), para não empilhar no mesmo pino.
            lat = round(blat + rnd.uniform(-0.009, 0.009), 6)
            lon = round(blon + rnd.uniform(-0.009, 0.009), 6)

            # Amostragem com rejeição: sorteia um perfil, pergunta ao motor,
            # e só aceita quando ele concorda com a doença pretendida.
            #
            # É mais honesto que calibrar probabilidade no olho até o número
            # subir. Tentei isso antes e empacou em 82%: o perfil e o motor
            # discordavam, e eu ia ficar movendo pesos até parecer certo. Aqui
            # quem decide é o motor, com as mesmas regras que atendem o cidadão.
            #
            # O viés que isto introduz está declarado: o conjunto aceito é
            # "perfis que o motor chama de Mpox/COVID", e não uma amostra
            # qualquer de quem tem a doença. Para encher mapa de demonstração
            # serve; para estudar epidemiologia, não.
            gerar = _perfil_mpox if alvo == "Mpox" else _perfil_covid
            for _tentativa in range(40):
                dados = gerar(rnd)
                dados_cls = {**dados, "estado": info["uf"], "cidade": cidade}
                grupo, classificacao, diferencial = classificar_padrao_completo(
                    dados_cls, setor="governo")
                saiu = (diferencial[0]["doenca"] if diferencial else "—")
                if saiu == alvo:
                    break
            resultados.append((alvo, saiu))

            # Distribuição no tempo: curva crescente, mais denso nos dias
            # recentes, e horário concentrado no período acordado. Tudo numa
            # hora só foi o que denunciou a carga anterior.
            peso_dia = [(i + 1) ** 1.5 for i in range(dias)]
            dia = rnd.choices(range(dias), weights=peso_dia)[0]
            hora = rnd.choices(range(24),
                               weights=[1, 1, 1, 1, 1, 2, 4, 7, 9, 10, 10, 9,
                                        8, 9, 10, 10, 9, 8, 7, 6, 5, 4, 3, 2])[0]
            quando = agora - timedelta(days=dias - 1 - dia)
            quando = quando.replace(hour=hora, minute=rnd.randrange(60),
                                    second=rnd.randrange(60))

            datas.append(quando)
            registros.append(RegistroSintoma(
                id_anonimo=uuid.uuid4(),
                empresa=empresa,
                data_registro=quando,
                latitude=lat, longitude=lon,
                pais="Brasil", estado=UF_POR_EXTENSO, cidade=cidade, bairro=bairro,
                grupo=grupo, classificacao=classificacao, diferencial=diferencial,
                # Procedência explícita: este registro diz que é simulação.
                fonte_referencia=marca,
                origem_dado=RegistroSintoma.ORIGEM_CIDADAO,
                device_id="sim-%s" % uuid.uuid4().hex[:12],
                confianca=0.9, suspeito=False,
                **{k: v for k, v in dados.items() if hasattr(RegistroSintoma, k)},
            ))

        # Relatório: o que foi pedido contra o que o motor disse.
        acertos = sum(1 for alvo, saiu in resultados if alvo == saiu)
        self.stdout.write("ADERÊNCIA AO ALVO")
        self.stdout.write("   %d de %d casos saíram como a doença pretendida (%.0f%%)\n"
                          % (acertos, len(resultados), 100 * acertos / len(resultados)))
        from collections import Counter
        divergentes = Counter("%s → %s" % (a, s) for a, s in resultados if a != s)
        if divergentes:
            self.stdout.write("   divergências:")
            for par, n in divergentes.most_common(8):
                self.stdout.write("      %-34s %d" % (par, n))
        self.stdout.write("")

        por_cidade = Counter(r.cidade for r in registros)
        self.stdout.write("DISTRIBUIÇÃO POR MUNICÍPIO")
        for c, n in por_cidade.most_common():
            self.stdout.write("   %-22s %4d" % (c, n))
        self.stdout.write("\n   bairros distintos: %d" % len({r.bairro + r.cidade for r in registros}))
        dias_distintos = len({r.data_registro.date() for r in registros})
        horas_distintas = len({(r.data_registro.date(), r.data_registro.hour) for r in registros})
        self.stdout.write("   dias distintos: %d | combinações dia+hora: %d"
                          % (dias_distintos, horas_distintas))

        if not aplicar:
            self.stdout.write(self.style.WARNING(
                "\nNada gravado. Rode com --aplicar para valer."))
            return

        with transaction.atomic(using="owner"):
            criados = RegistroSintoma.objects.using("owner").bulk_create(
                registros, batch_size=100)
            # data_registro é auto_now_add: o valor passado no construtor é
            # IGNORADO no insert, e todos os registros nascem com o mesmo
            # instante. Foi exatamente assim que a carga antiga ficou com
            # 2.000 casos na mesma hora — e eu repeti o erro antes de medir.
            # QuerySet.update() não passa por auto_now_add, então a data
            # pretendida é escrita aqui, depois.
            for obj, quando in zip(criados, datas):
                RegistroSintoma.objects.using("owner").filter(pk=obj.pk).update(
                    data_registro=quando)
        self.stdout.write(self.style.SUCCESS(
            "\n%d registros gravados com fonte_referencia='%s'." % (len(registros), marca)))
        self.stdout.write("Para remover todos depois:")
        self.stdout.write("   RegistroSintoma.objects.using('owner')"
                          ".filter(fonte_referencia__startswith='%s').delete()" % MARCA)
