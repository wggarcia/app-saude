"""Checagem de interação medicamentosa em oncologia.

ESCOPO, DITO NA CARA: isto é um **subconjunto curado** de interações relevantes
em oncologia — não é um checador completo de todas as interações possíveis.

A distinção não é modéstia, é desenho. Estudos brasileiros com pacientes
oncológicos encontraram 152 interações pelo Micromedex e 614 pelo Drugs.com nos
MESMOS pacientes. Uma base que dispara centenas de alertas produz fadiga de
alerta: a equipe passa a clicar "ignorar" em tudo, inclusive no que mata. Um
conjunto menor, com mecanismo e conduta em cada item, é mais seguro na prática
do que uma base completa que ninguém lê.

Quando o hospital licenciar uma base comercial (Micromedex, Lexicomp, DrugBank,
Memed), ela entra como provedor adicional — o motor aqui não precisa mudar.

Fontes dos pares: alertas regulatórios (bulas da ANVISA e do FDA, incluindo
advertências de caixa-preta) e literatura de oncologia clínica. Cada par carrega
a sua. Nenhum par entrou "por parecer razoável".
"""
import logging
import unicodedata

logger = logging.getLogger(__name__)


def normalizar(nome):
    """Minúsculo, sem acento, sem espaço nas pontas.

    A prescrição digita "Fluoruracila", "fluorouracil", "5-FU"... normalizar é o
    que permite casar sem depender de quem digitou.
    """
    if not nome:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(nome))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# Sinônimos e nomes comerciais frequentes. Sem isto, "Xeloda" não casa com
# "capecitabina" e o alerta de caixa-preta simplesmente não dispara.
SINONIMOS = {
    "5-fu": "fluoruracila",
    "5fu": "fluoruracila",
    "fluorouracil": "fluoruracila",
    "fluorouracila": "fluoruracila",
    "xeloda": "capecitabina",
    "mtx": "metotrexato",
    "methotrexate": "metotrexato",
    "adriamicina": "doxorrubicina",
    "doxorubicina": "doxorrubicina",
    "oncovin": "vincristina",
    "glivec": "imatinibe",
    "imatinib": "imatinibe",
    "tarceva": "erlotinibe",
    "erlotinib": "erlotinibe",
    "sprycel": "dasatinibe",
    "dasatinib": "dasatinibe",
    "nolvadex": "tamoxifeno",
    "tamoxifen": "tamoxifeno",
    "herceptin": "trastuzumabe",
    "trastuzumab": "trastuzumabe",
    "marevan": "varfarina",
    "warfarin": "varfarina",
    "warfarina": "varfarina",
    "coumadin": "varfarina",
    "bactrim": "sulfametoxazol-trimetoprima",
    "sulfametoxazol/trimetoprima": "sulfametoxazol-trimetoprima",
    "smz-tmp": "sulfametoxazol-trimetoprima",
    "omeprazol": "inibidor de bomba de protons",
    "pantoprazol": "inibidor de bomba de protons",
    "esomeprazol": "inibidor de bomba de protons",
    "lansoprazol": "inibidor de bomba de protons",
    "ibp": "inibidor de bomba de protons",
    "ibuprofeno": "anti-inflamatorio nao esteroidal",
    "naproxeno": "anti-inflamatorio nao esteroidal",
    "diclofenaco": "anti-inflamatorio nao esteroidal",
    "cetoprofeno": "anti-inflamatorio nao esteroidal",
    "aine": "anti-inflamatorio nao esteroidal",
    "aines": "anti-inflamatorio nao esteroidal",
    "gentamicina": "aminoglicosideo",
    "amicacina": "aminoglicosideo",
    "tobramicina": "aminoglicosideo",
    "cetoconazol": "inibidor forte de cyp3a4",
    "itraconazol": "inibidor forte de cyp3a4",
    "voriconazol": "inibidor forte de cyp3a4",
    "claritromicina": "inibidor forte de cyp3a4",
    "ritonavir": "inibidor forte de cyp3a4",
    "rifampicina": "indutor forte de cyp3a4",
    "carbamazepina": "indutor forte de cyp3a4",
    "fenobarbital": "indutor forte de cyp3a4",
    "erva-de-sao-joao": "indutor forte de cyp3a4",
    "hiperico": "indutor forte de cyp3a4",
    "fluoxetina": "inibidor forte de cyp2d6",
    "paroxetina": "inibidor forte de cyp2d6",
    "bupropiona": "inibidor forte de cyp2d6",
}


# Tokens de posologia que vêm grudados no nome na prescrição real
# ("Varfarina 5mg", "Capecitabina 500 mg comprimido").
_UNIDADES = {"mg", "g", "mcg", "ml", "l", "ui", "u", "mg/m2", "mg/m²", "auc",
             "comprimido", "comprimidos", "capsula", "capsulas", "cp", "cps",
             "ampola", "ampolas", "frasco", "frascos", "sol", "solucao", "inj"}


def _sem_posologia(n):
    """Tira do nome os pedaços que são dose, não identidade do fármaco."""
    partes = [p for p in n.replace("/", " ").split()
              if not any(ch.isdigit() for ch in p) and p not in _UNIDADES]
    return " ".join(partes).strip()


def canonico(nome):
    """Normaliza, limpa posologia e resolve sinônimo para o termo da base.

    Na prescrição real o nome quase nunca vem limpo: "Varfarina 5mg",
    "Xeloda 500 mg comprimido". Se o casamento depender do nome exato, o
    alerta de caixa-preta simplesmente não dispara.
    """
    n = normalizar(nome)
    if not n:
        return ""
    if n in SINONIMOS:
        return SINONIMOS[n]
    limpo = _sem_posologia(n)
    if limpo and limpo in SINONIMOS:
        return SINONIMOS[limpo]
    # Marca comercial com complemento ("Glivec 400"): tenta a primeira palavra.
    primeira = limpo.split()[0] if limpo.split() else ""
    if primeira and primeira in SINONIMOS:
        return SINONIMOS[primeira]
    return limpo or n


# ── Base curada ───────────────────────────────────────────────────────────────
# (farmaco_a, farmaco_b, gravidade, mecanismo, conduta, fonte)
# Pares em termos canônicos. Classes ("inibidor forte de cyp3a4") entram como
# um termo só, porque o que importa clinicamente é a classe, não a molécula.
BASE_CURADA = [
    # ── Antagonistas da vitamina K com fluoropirimidinas ──────────────────
    ("capecitabina", "varfarina", "grave",
     "A capecitabina inibe o metabolismo da varfarina e potencializa o efeito "
     "anticoagulante; o RNI (Razão Normalizada Internacional) sobe de forma "
     "imprevisível, com risco de sangramento grave.",
     "Advertência de caixa-preta. Se a anticoagulação for indispensável, "
     "preferir heparina de baixo peso molecular. Mantendo a varfarina, "
     "monitorar RNI com frequência e ajustar a dose.",
     "Advertência de caixa-preta da bula de capecitabina (FDA/ANVISA)"),
    ("fluoruracila", "varfarina", "grave",
     "Mesmo mecanismo da capecitabina: inibição do metabolismo da varfarina, "
     "com elevação imprevisível do RNI.",
     "Preferir heparina de baixo peso molecular. Se mantiver a varfarina, "
     "monitorar RNI de perto.",
     "Bula de fluoruracila; advertência de classe"),
    ("tamoxifeno", "varfarina", "grave",
     "O tamoxifeno potencializa o efeito anticoagulante da varfarina.",
     "Monitorar RNI e ajustar a dose do anticoagulante.",
     "Bula de tamoxifeno"),

    # ── Metotrexato ───────────────────────────────────────────────────────
    ("metotrexato", "anti-inflamatorio nao esteroidal", "grave",
     "Os anti-inflamatórios reduzem a depuração renal do metotrexato e "
     "aumentam a fração livre, elevando a concentração a níveis tóxicos — "
     "mielossupressão e nefrotoxicidade.",
     "Evitar. Se for inevitável, suspender o anti-inflamatório ao redor da "
     "infusão, hidratar, alcalinizar a urina e monitorar o nível sérico de "
     "metotrexato e a função renal.",
     "Bula de metotrexato; literatura de oncologia clínica"),
    ("metotrexato", "sulfametoxazol-trimetoprima", "grave",
     "Efeito antifolato aditivo somado à redução da depuração renal do "
     "metotrexato: risco de mielossupressão grave e pancitopenia.",
     "Evitar a associação. Usar outro antimicrobiano; se não houver "
     "alternativa, monitorar hemograma de perto e considerar resgate com "
     "ácido folínico.",
     "Bula de metotrexato; alerta de classe antifolato"),
    ("metotrexato", "inibidor de bomba de protons", "moderada",
     "Os inibidores de bomba de prótons retardam a eliminação renal do "
     "metotrexato, prolongando a exposição.",
     "Em altas doses de metotrexato, suspender o inibidor alguns dias antes e "
     "trocar por bloqueador H2. Monitorar o nível sérico.",
     "Bula de metotrexato"),
    ("metotrexato", "probenecida", "grave",
     "A probenecida bloqueia a secreção tubular renal do metotrexato e eleva "
     "muito a sua concentração.",
     "Evitar a associação.",
     "Bula de metotrexato"),
    ("metotrexato", "penicilina", "moderada",
     "As penicilinas competem pela secreção tubular e reduzem a depuração do "
     "metotrexato.",
     "Monitorar nível sérico e hemograma; considerar antimicrobiano "
     "alternativo em altas doses.",
     "Bula de metotrexato"),

    # ── Tamoxifeno e CYP2D6 ───────────────────────────────────────────────
    ("tamoxifeno", "inibidor forte de cyp2d6", "grave",
     "O tamoxifeno é pró-fármaco: precisa da CYP2D6 para virar endoxifeno, a "
     "forma ativa. Inibidores fortes (fluoxetina, paroxetina, bupropiona) "
     "derrubam o endoxifeno e podem anular o efeito antitumoral.",
     "Trocar o antidepressivo por um que não iniba a CYP2D6 (venlafaxina, "
     "citalopram ou escitalopram). A interação reduz EFICÁCIA, não causa "
     "toxicidade — por isso passa despercebida.",
     "Bula de tamoxifeno; diretrizes de oncologia mamária"),

    # ── Platinas ──────────────────────────────────────────────────────────
    ("cisplatina", "aminoglicosideo", "grave",
     "Nefrotoxicidade e ototoxicidade aditivas: as duas classes lesam túbulo "
     "renal e células ciliadas.",
     "Evitar a associação. Se inevitável, monitorar creatinina e audiometria, "
     "hidratar vigorosamente e espaçar as administrações.",
     "Bula de cisplatina"),
    ("carboplatina", "aminoglicosideo", "moderada",
     "Toxicidade renal e auditiva aditivas, menor que com cisplatina mas "
     "presente.",
     "Monitorar função renal; ajustar a dose pela fórmula de Calvert com "
     "clearance atualizado.",
     "Bula de carboplatina"),
    ("cisplatina", "furosemida", "moderada",
     "Ototoxicidade aditiva e risco de depleção de volume agravando a "
     "nefrotoxicidade.",
     "Preferir hidratação a diurético. Se precisar, usar com volume "
     "reposto e monitorar audição.",
     "Bula de cisplatina"),

    # ── Inibidores de tirosina quinase e pH gástrico ──────────────────────
    ("erlotinibe", "inibidor de bomba de protons", "grave",
     "A absorção do erlotinibe depende de meio ácido. Inibidores de bomba "
     "elevam o pH gástrico e reduzem a exposição ao fármaco de forma "
     "relevante — perda de eficácia.",
     "Evitar inibidor de bomba de prótons. Se precisar de antiácido, usar "
     "antiácido simples espaçado algumas horas do erlotinibe.",
     "Bula de erlotinibe"),
    ("dasatinibe", "inibidor de bomba de protons", "grave",
     "Mesmo mecanismo: pH elevado reduz a dissolução e a absorção do "
     "dasatinibe.",
     "Evitar. Usar antiácido simples, espaçado pelo menos 2 horas.",
     "Bula de dasatinibe"),
    ("pazopanibe", "inibidor de bomba de protons", "moderada",
     "Redução da exposição ao pazopanibe por elevação do pH gástrico.",
     "Espaçar a administração; considerar bloqueador H2 como alternativa.",
     "Bula de pazopanibe"),

    # ── CYP3A4 ────────────────────────────────────────────────────────────
    ("irinotecano", "inibidor forte de cyp3a4", "grave",
     "Inibição do metabolismo eleva a exposição ao SN-38, metabólito ativo do "
     "irinotecano: diarreia grave e neutropenia.",
     "Suspender o inibidor, se possível, uma semana antes. Caso contrário, "
     "reduzir a dose do irinotecano e vigiar toxicidade.",
     "Bula de irinotecano"),
    ("irinotecano", "indutor forte de cyp3a4", "grave",
     "Indução acelera o metabolismo e derruba a exposição ao irinotecano — "
     "perda de eficácia do tratamento.",
     "Trocar o indutor por alternativa sem efeito em CYP3A4 (ex.: trocar "
     "fenitoína por levetiracetam) ao menos 2 semanas antes.",
     "Bula de irinotecano"),
    ("vincristina", "inibidor forte de cyp3a4", "grave",
     "Inibição do metabolismo da vincristina aumenta muito o risco de "
     "neuropatia periférica grave e íleo paralítico.",
     "Evitar azólicos durante o tratamento; preferir profilaxia antifúngica "
     "sem efeito em CYP3A4.",
     "Bula de vincristina; literatura de neurotoxicidade"),
    ("imatinibe", "inibidor forte de cyp3a4", "moderada",
     "Aumento da exposição ao imatinibe, com mais edema, citopenia e "
     "hepatotoxicidade.",
     "Monitorar toxicidade; considerar redução de dose.",
     "Bula de imatinibe"),
    ("imatinibe", "varfarina", "grave",
     "O imatinibe inibe a CYP2C9 e altera o metabolismo da varfarina, com "
     "RNI imprevisível.",
     "Substituir por heparina de baixo peso molecular.",
     "Bula de imatinibe"),
    ("everolimo", "inibidor forte de cyp3a4", "grave",
     "Elevação acentuada da exposição ao everolimo: estomatite, pneumonite e "
     "mielossupressão.",
     "Evitar. Se indispensável, reduzir a dose conforme a bula e monitorar.",
     "Bula de everolimo"),
    ("sorafenibe", "indutor forte de cyp3a4", "grave",
     "Indução reduz a exposição ao sorafenibe e compromete a eficácia.",
     "Evitar indutores fortes; trocar por alternativa.",
     "Bula de sorafenibe"),
    ("sunitinibe", "indutor forte de cyp3a4", "grave",
     "Mesmo mecanismo: perda de exposição e de eficácia.",
     "Evitar indutores fortes; trocar por alternativa.",
     "Bula de sunitinibe"),
    ("paclitaxel", "inibidor forte de cyp3a4", "moderada",
     "Redução do metabolismo do paclitaxel, com mais mielossupressão e "
     "neuropatia.",
     "Monitorar hemograma e sintomas neurológicos; considerar ajuste de dose.",
     "Bula de paclitaxel"),
    ("etoposideo", "varfarina", "moderada",
     "O etoposídeo pode potencializar o efeito anticoagulante.",
     "Monitorar RNI.",
     "Bula de etoposídeo"),

    # ── Cardiotoxicidade ──────────────────────────────────────────────────
    ("doxorrubicina", "trastuzumabe", "grave",
     "Cardiotoxicidade aditiva: a antraciclina lesa o miócito e o trastuzumabe "
     "impede o reparo, elevando muito o risco de insuficiência cardíaca.",
     "Não administrar de forma concomitante. Separar as fases do tratamento e "
     "monitorar a fração de ejeção antes e durante.",
     "Bula de trastuzumabe; diretrizes de cardio-oncologia"),

    # ── Suporte e antieméticos ────────────────────────────────────────────
    ("ondansetrona", "apomorfina", "grave",
     "Hipotensão profunda e perda de consciência relatadas com a associação.",
     "Contraindicado. Usar outro antiemético.",
     "Bula de ondansetrona — contraindicação"),
    ("ciclofosfamida", "alopurinol", "moderada",
     "O alopurinol aumenta a mielossupressão induzida pela ciclofosfamida.",
     "Monitorar hemograma; considerar suspender o alopurinol se não for "
     "essencial.",
     "Bula de ciclofosfamida"),
    ("capecitabina", "alopurinol", "moderada",
     "O alopurinol pode reduzir a eficácia da capecitabina.",
     "Evitar a associação durante o tratamento.",
     "Bula de capecitabina"),
    ("capecitabina", "fenitoina", "moderada",
     "A capecitabina eleva a concentração de fenitoína, com risco de "
     "toxicidade (ataxia, nistagmo, sedação).",
     "Monitorar o nível sérico de fenitoína e ajustar a dose.",
     "Bula de capecitabina"),
    ("bleomicina", "oxigenio suplementar", "grave",
     "Oxigênio em alta concentração potencializa a toxicidade pulmonar da "
     "bleomicina, podendo precipitar fibrose.",
     "Usar a menor fração inspirada de oxigênio possível, inclusive em "
     "anestesia. Avisar a equipe cirúrgica sobre o uso prévio de bleomicina.",
     "Bula de bleomicina; literatura de toxicidade pulmonar"),
    ("vincristina", "fenitoina", "moderada",
     "A vincristina pode reduzir a absorção e o nível sérico da fenitoína.",
     "Monitorar nível sérico e ajustar.",
     "Bula de vincristina"),
]


def seed_interacoes(empresa, modelo=None):
    """Semeia a base curada no tenant. Idempotente."""
    from api.models import InteracaoMedicamentosa
    modelo = modelo or InteracaoMedicamentosa
    criadas = 0
    for a, b, gravidade, mecanismo, conduta, fonte in BASE_CURADA:
        _, novo = modelo.objects.get_or_create(
            empresa=empresa, farmaco_a=a, farmaco_b=b,
            defaults={"gravidade": gravidade, "mecanismo": mecanismo,
                      "conduta": conduta, "fonte": fonte, "origem": "curada",
                      "ativo": True})
        criadas += 1 if novo else 0
    return criadas


def checar(empresa, medicamentos):
    """Procura interações entre os medicamentos informados.

    Devolve dict com os achados e, sempre, o aviso de escopo — para que nenhuma
    tela possa apresentar "0 interações" como se fosse "seguro".
    """
    from api.models import InteracaoMedicamentosa

    # Mantém o nome como foi digitado para mostrar ao usuário, mas casa pelo
    # termo canônico.
    originais = {}
    for m in (medicamentos or []):
        c = canonico(m)
        if c:
            originais.setdefault(c, str(m).strip())

    termos = set(originais)
    achados = []
    if len(termos) >= 2:
        candidatas = InteracaoMedicamentosa.objects.filter(
            empresa=empresa, ativo=True, farmaco_a__in=termos,
            farmaco_b__in=termos)
        for i in candidatas:
            achados.append({
                "id": i.id,
                "farmaco_a": originais.get(i.farmaco_a, i.farmaco_a),
                "farmaco_b": originais.get(i.farmaco_b, i.farmaco_b),
                "termo_a": i.farmaco_a,
                "termo_b": i.farmaco_b,
                "gravidade": i.gravidade,
                "gravidade_display": i.get_gravidade_display(),
                "mecanismo": i.mecanismo,
                "conduta": i.conduta,
                "fonte": i.fonte,
                "origem": i.origem,
            })

    ordem = {"grave": 0, "moderada": 1, "leve": 2}
    achados.sort(key=lambda x: ordem.get(x["gravidade"], 9))
    graves = [a for a in achados if a["gravidade"] == "grave"]
    base_vazia = not InteracaoMedicamentosa.objects.filter(
        empresa=empresa, ativo=True).exists()

    return {
        "medicamentos_analisados": sorted(originais.values()),
        "total": len(achados),
        "graves": len(graves),
        "interacoes": achados,
        "base_vazia": base_vazia,
        # Nunca deixar a tela sugerir que "nenhuma encontrada" = "seguro".
        "escopo": (
            "Subconjunto curado de interações relevantes em oncologia — não "
            "substitui a avaliação do farmacêutico clínico nem uma base "
            "completa licenciada. Ausência de alerta não significa ausência "
            "de interação."
        ),
    }


def medicamentos_do_ciclo(ciclo):
    """Todos os fármacos que o paciente recebe naquele ciclo.

    Inclui a pré-medicação: é comum a interação estar entre o antiemético e o
    quimioterápico, e não entre dois quimioterápicos.
    """
    nomes = []
    for d in (ciclo.doses_calculadas or []):
        if d.get("droga"):
            nomes.append(d["droga"])
    if not nomes:
        for d in (ciclo.protocolo.drogas or []):
            if d.get("droga"):
                nomes.append(d["droga"])
    for m in (ciclo.protocolo.drogas_suporte or []):
        if m.get("droga"):
            nomes.append(m["droga"])
    return nomes
