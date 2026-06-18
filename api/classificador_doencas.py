"""
classificador_doencas.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Motor de classificação probabilística de doenças para o Brasil.

Princípios:
  • Diagnóstico DIFERENCIAL — distingue doenças com sintomas similares
    (dengue ≠ Zika ≠ Chikungunya mesmo com febre/dor compartilhadas)
  • Pesos específicos por sintoma por doença (positivos e negativos)
  • Flags de urgência absoluta (rigidez_nuca, manchas_hemorragicas, etc.)
  • Sazonalidade brasileira (dengue no verão, gripe no inverno…)
  • Retorna ranking com score, confiança, diagnóstico diferencial,
    red flags e contexto por setor do ecossistema
  • Isolamento por setor — cada ambiente recebe apenas o que é relevante
  • Sem mistura entre setores — cada um vê sua própria lente
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# BASE DE CONHECIMENTO EPIDEMIOLÓGICO BRASIL
# Cada doença tem:
#   peso positivo  → sintoma aponta para ela
#   peso negativo  → sintoma aponta CONTRA ela (reduz probabilidade)
#   peso zero/omit → neutro
# Escala de 0 a 1.0 (positivo) e -1.0 a 0 (negativo)
# ──────────────────────────────────────────────────────────────────────────────

DOENCAS_BRASIL: dict[str, dict] = {

    # ── ARBOVIROSES (Aedes aegypti) ───────────────────────────────────────────
    "Dengue": {
        "grupo": "Arbovirose",
        "vetor": "Aedes aegypti",
        "cid10": "A90",
        "descricao": "Febre alta abrupta, dor retroorbitária, mialgia intensa, possível rash e plaquetopenia",
        "sazonalidade": [10, 11, 12, 1, 2, 3, 4, 5],  # meses de maior risco no Brasil
        "sintomas": {
            "febre":                  1.00,  # febre ALTA >39°C, característica
            "dor_corpo":              0.95,  # mialgia intensa
            "dor_cabeca":             0.90,  # cefaleia + dor retroorbitária
            "cansaco":                0.80,
            "vomito_nausea":          0.72,  # sinal de alarme
            "exantema":               0.68,  # rash maculopapular em ~50%
            "dor_abdominal":          0.65,  # sinal de alarme dengue
            "manchas_hemorragicas":   0.55,  # petéquias, dengue grave
            "diarreia":               0.35,
            "sudorese":               0.30,
            "dor_articular":          0.30,  # artralgia LEVE — presente mas nunca incapacitante
            "calafrios":              0.40,
            "tosse":                 -0.40,  # raro na dengue — aponta CONTRA
            "falta_ar":              -0.35,  # raro — aponta CONTRA
            "coriza":                -0.45,  # raro — aponta CONTRA
            "perda_olfato_paladar":  -0.60,  # COVID, não dengue
            "rigidez_nuca":          -0.50,  # forte contra-indicador — meningite, não dengue
            "ictericia":             -0.50,  # icterícia é RARA no dengue típico — aponta forte para hepatite/lepto/FA
            "conjuntivite":          -0.30,  # Zika, não dengue
            "dor_garganta":          -0.35,  # gripe/resfriado, não dengue
            # intensidades importantíssimas para diferencial:
            "_intensidade_febre_alta":       0.30,   # bônus se febre alta
            "_intensidade_articular_leve":   0.15,   # dengue tem artralgia leve
            "_intensidade_articular_intensa":-0.40,  # artralgia INTENSA aponta CONTRA dengue → chikungunya
        },
        "red_flags": ["manchas_hemorragicas", "dor_abdominal", "vomito_nausea"],
        "diferencial_vs": {
            "Chikungunya": "artralgia muito menos intensa na dengue; chikungunya é incapacitante",
            "Zika": "febre alta na dengue; Zika tem febre baixa e conjuntivite",
            "Gripe": "dengue NÃO tem coriza nem dor de garganta significativa",
        },
    },

    "Zika": {
        "grupo": "Arbovirose",
        "vetor": "Aedes aegypti",
        "cid10": "A928",
        "descricao": "Febre baixa, exantema pruriginoso, conjuntivite não-purulenta; risco de microcefalia e Guillan-Barré",
        "sazonalidade": [10, 11, 12, 1, 2, 3, 4, 5],
        "sintomas": {
            "febre":                  0.68,  # febre BAIXA — diferenciador chave
            "exantema":               0.98,  # exantema pruriginoso quase sempre presente
            "conjuntivite":           0.95,  # PATOGNOMÔNICO — diferenciador principal
            "dor_articular":          0.72,  # artralgia LEVE (vs chikungunya)
            "dor_corpo":              0.52,
            "cansaco":                0.48,
            "dor_cabeca":             0.55,
            "sudorese":               0.20,
            "tosse":                 -0.25,
            "falta_ar":              -0.20,
            "coriza":                -0.25,
            "manchas_hemorragicas":  -0.30,  # não é dengue hemorrágico
            "dor_abdominal":         -0.10,
            "vomito_nausea":         -0.15,
            "perda_olfato_paladar":  -0.60,
            "rigidez_nuca":          -0.50,
            "ictericia":             -0.40,
            "_intensidade_febre_baixa":    0.40,   # bônus se febre BAIXA
            "_intensidade_articular_leve": 0.30,   # artralgia leve vs chikungunya
        },
        "red_flags": [],
        "diferencial_vs": {
            "Dengue": "Zika tem febre baixa, exantema pruriginoso e CONJUNTIVITE — dengue não",
            "Chikungunya": "Zika tem conjuntivite e exantema; artralgia é leve; chikungunya é incapacitante",
        },
    },

    "Chikungunya": {
        "grupo": "Arbovirose",
        "vetor": "Aedes aegypti",
        "cid10": "A920",
        "descricao": "Febre alta abrupta + artralgia INCAPACITANTE bilateral; pode cronicizar por meses",
        "sazonalidade": [10, 11, 12, 1, 2, 3, 4, 5],
        "sintomas": {
            "dor_articular":          1.00,  # ARTRALGIA INTENSA — diferenciador absoluto
            "febre":                  0.92,  # febre alta
            "exantema":               0.75,
            "dor_corpo":              0.85,
            "cansaco":                0.80,
            "dor_cabeca":             0.72,
            "sudorese":               0.35,
            "vomito_nausea":          0.40,
            "tosse":                 -0.35,
            "falta_ar":              -0.30,
            "coriza":                -0.40,
            "perda_olfato_paladar":  -0.60,
            "rigidez_nuca":          -0.40,
            "ictericia":             -0.50,
            "conjuntivite":           0.35,  # pode ocorrer mas não patognomônico
            "manchas_hemorragicas":  -0.20,
            "_intensidade_febre_alta":        0.25,
            "_intensidade_articular_intensa": 0.80,  # bônus decisivo — artralgia intensa é o diferenciador chikungunya
        },
        "red_flags": [],
        "diferencial_vs": {
            "Dengue": "artralgia é muito mais intensa na chikungunya — incapacitante, bilateral",
            "Zika": "artralgia mais severa; conjuntivite menos proeminente; sem exantema pruriginoso típico",
            "Febre Reumática": "cronificação pode confundir mas contexto epidemiológico diferente",
        },
    },

    "Febre Amarela": {
        "grupo": "Arbovirose",
        "vetor": "Aedes/Haemagogus",
        "cid10": "A95",
        "descricao": "Febre bifásica, icterícia, hepatite, hemorragia — alta mortalidade; prevenível por vacina",
        "sazonalidade": [12, 1, 2, 3, 4, 5],
        "sintomas": {
            "febre":                  0.95,
            "ictericia":              0.90,  # diferenciador forte
            "vomito_nausea":          0.85,
            "dor_corpo":              0.80,
            "cansaco":                0.82,
            "manchas_hemorragicas":   0.70,
            "dor_abdominal":          0.75,
            "dor_cabeca":             0.72,
            "calafrios":              0.65,
            "sudorese":               0.45,
            "tosse":                 -0.20,
            "falta_ar":              -0.15,
            "coriza":                -0.50,
            "perda_olfato_paladar":  -0.70,
            "exantema":               0.20,
            "dor_articular":          0.15,
            "rigidez_nuca":          -0.15,
            "dor_garganta":          -0.40,
        },
        "red_flags": ["ictericia", "manchas_hemorragicas", "vomito_nausea"],
        "diferencial_vs": {
            "Dengue": "icterícia e hemorragia mais proeminentes; dengue não tem icterícia típica",
            "Leptospirose": "sobreposição grande — contexto ambiental e vacinação ajudam",
        },
    },

    "Malaria": {
        "grupo": "Parasitária",
        "vetor": "Anopheles",
        "cid10": "B54",
        "descricao": "Febre cíclica (terçã/quartã), calafrios, sudorese; endêmica na Amazônia",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # todo ano na Amazônia
        "sintomas": {
            "febre":                  0.95,  # febre cíclica — muito característica
            "calafrios":              0.95,  # tremores — muito característico
            "sudorese":               0.90,  # CICLO febre→calafrios→SUDORESE — tríade patognomônica
            "cansaco":                0.88,
            "dor_corpo":              0.72,
            "dor_cabeca":             0.78,
            "vomito_nausea":          0.68,
            "diarreia":               0.35,
            "tosse":                 -0.20,
            "falta_ar":              -0.10,
            "coriza":                -0.50,
            "exantema":              -0.25,
            "conjuntivite":          -0.40,
            "dor_garganta":          -0.40,
            "perda_olfato_paladar":  -0.70,
            "rigidez_nuca":          -0.30,
            "ictericia":              0.35,  # malária pode causar icterícia leve
        },
        "red_flags": ["ictericia", "falta_ar"],
        "diferencial_vs": {
            "Dengue": "malária tem calafrios cíclicos característicos; dengue não tem padrão cíclico tão marcado",
            "Leptospirose": "histórico de área endêmica e calafrios cíclicos diferem",
        },
    },

    # ── ZOONOSES ──────────────────────────────────────────────────────────────
    "Leptospirose": {
        "grupo": "Zoonose",
        "vetor": "Roedores/água contaminada",
        "cid10": "A27",
        "descricao": "Febre + mialgia + exposição à água enchente/lama + evolução para síndrome de Weil (icterícia, insuficiência renal)",
        "sazonalidade": [1, 2, 3, 4, 11, 12],  # chuvas no Brasil
        "sintomas": {
            "febre":                  0.90,
            "dor_corpo":              0.92,  # mialgia intensa, especialmente panturrilhas
            "cansaco":                0.80,
            "dor_cabeca":             0.82,
            "vomito_nausea":          0.75,
            "ictericia":              0.78,  # síndrome de Weil
            "dor_abdominal":          0.72,
            "calafrios":              0.70,
            "sudorese":               0.60,
            "manchas_hemorragicas":   0.45,
            "diarreia":               0.40,
            "tosse":                 -0.10,
            "falta_ar":              -0.05,
            "coriza":                -0.45,
            "exantema":              -0.20,
            "conjuntivite":          -0.10,
            "perda_olfato_paladar":  -0.70,
            "dor_garganta":          -0.40,
        },
        "red_flags": ["ictericia", "manchas_hemorragicas", "dor_abdominal"],
        "diferencial_vs": {
            "Dengue": "leptospirose tem histórico de exposição à água/lama; icterícia mais intensa",
            "Febre Amarela": "contexto ambiental (inundação, ratos) diferencia",
        },
    },

    "Hantavirose": {
        "grupo": "Zoonose",
        "vetor": "Roedores silvestres (aerossol)",
        "cid10": "B33.4",
        "descricao": "Febre + falta de ar progressiva rápida; síndrome cardiopulmonar com alta mortalidade",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "falta_ar":               1.00,  # cardiopulmonar — insuficiência respiratória
            "febre":                  0.92,
            "cansaco":                0.88,
            "dor_corpo":              0.75,
            "dor_cabeca":             0.68,
            "vomito_nausea":          0.58,
            "tosse":                  0.72,
            "calafrios":              0.62,
            "sudorese":               0.45,
            "coriza":                -0.20,
            "exantema":              -0.30,
            "conjuntivite":          -0.35,
            "dor_garganta":          -0.30,
            "perda_olfato_paladar":  -0.60,
            "ictericia":             -0.20,
            "rigidez_nuca":          -0.40,
        },
        "red_flags": ["falta_ar", "cansaco", "febre"],
        "diferencial_vs": {
            "COVID": "hantavirose tem piora respiratória MUITO mais rápida; sem perda de olfato",
            "Gripe": "falta de ar dominante desde o início distingue da gripe comum",
        },
    },

    # ── EXANTEMÁTICAS ────────────────────────────────────────────────────────
    "Sarampo": {
        "grupo": "Viral exantemática",
        "vetor": "Aerossol (altamente contagioso)",
        "cid10": "B05",
        "descricao": "Febre alta + exantema maculopapular céfalo-caudal + manchas de Koplik; prevenível por vacina",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "febre":                  0.95,
            "exantema":               1.00,  # exantema maculopapular progressivo — essencial
            "conjuntivite":           0.88,  # fotofobia + hiperemia
            "tosse":                  0.85,  # tosse intensa
            "coriza":                 0.80,
            "dor_corpo":              0.55,
            "cansaco":                0.65,
            "dor_cabeca":             0.60,
            "falta_ar":               0.20,
            "dor_garganta":           0.50,
            "sudorese":               0.30,
            "perda_olfato_paladar":  -0.60,
            "ictericia":             -0.50,
            "manchas_hemorragicas":  -0.20,
            "rigidez_nuca":          -0.25,
            "dor_articular":         -0.15,
            "calafrios":              0.30,
        },
        "red_flags": ["falta_ar", "rigidez_nuca"],
        "diferencial_vs": {
            "Rubéola": "sarampo tem tosse, coriza e manchas de Koplik — rubéola não tem",
            "Dengue": "exantema pruriginoso na dengue não é céfalo-caudal como no sarampo",
        },
    },

    # ── MENINGITES ────────────────────────────────────────────────────────────
    "Meningite": {
        "grupo": "Neurológica — URGÊNCIA",
        "vetor": "Neisseria/Streptococcus/Viral",
        "cid10": "G03",
        "descricao": "URGÊNCIA MÉDICA: tríade febre + rigidez nuca + cefaleia intensa; manchas petequiais na meningocócica",
        "sazonalidade": [5, 6, 7, 8, 9],  # inverno — meningocócica
        "sintomas": {
            "rigidez_nuca":           1.00,  # SINAL CLÍNICO PATOGNOMÔNICO
            "febre":                  0.92,
            "dor_cabeca":             0.95,  # cefaleia intensa — "pior dor da vida"
            "manchas_hemorragicas":   0.88,  # petéquias/púrpura — meningocócica
            "vomito_nausea":          0.78,
            "cansaco":                0.72,
            "falta_ar":               0.25,
            "sudorese":               0.45,
            "tosse":                 -0.15,
            "coriza":                -0.30,
            "exantema":               0.35,  # purpura
            "dor_articular":          0.20,
            "dor_corpo":              0.55,
            "perda_olfato_paladar":  -0.70,
            "ictericia":             -0.30,
        },
        "red_flags": ["rigidez_nuca", "manchas_hemorragicas", "dor_cabeca"],
        "diferencial_vs": {
            "Dengue": "rigidez nuca AUSENTE na dengue — presença é alarme de meningite",
            "Gripe": "cefaleia da meningite é mais intensa; sem coriza",
        },
    },

    # ── RESPIRATÓRIAS ────────────────────────────────────────────────────────
    "COVID-19": {
        "grupo": "Viral respiratória",
        "vetor": "SARS-CoV-2 (aerossol)",
        "cid10": "U07.1",
        "descricao": "Tosse, febre, falta de ar; perda de olfato/paladar quase patognomônica; amplo espectro de gravidade",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "perda_olfato_paladar":   1.00,  # QUASE PATOGNOMÔNICO para COVID
            "tosse":                  0.90,
            "falta_ar":               0.88,
            "febre":                  0.82,
            "cansaco":                0.85,
            "dor_corpo":              0.70,
            "dor_cabeca":             0.72,
            "dor_garganta":           0.65,
            "vomito_nausea":          0.45,
            "diarreia":               0.40,
            "coriza":                 0.40,
            "exantema":               0.20,
            "dor_articular":          0.35,
            "calafrios":              0.50,
            "sudorese":               0.25,
            "rigidez_nuca":          -0.60,
            "ictericia":             -0.50,
            "conjuntivite":          -0.20,
            "manchas_hemorragicas":  -0.40,
        },
        "red_flags": ["falta_ar", "perda_olfato_paladar"],
        "diferencial_vs": {
            "Gripe": "perda de olfato é muito mais comum no COVID; gripe tem dor muscular mais intensa",
            "Resfriado Viral": "resfriado não causa falta de ar ou perda de olfato significativa",
            "Dengue": "COVID tem tosse e perda de olfato; dengue não",
        },
    },

    "Gripe (Influenza)": {
        "grupo": "Viral respiratória",
        "vetor": "Influenza A/B (aerossol)",
        "cid10": "J11",
        "descricao": "Início súbito, febre alta, mialgia intensa, tosse seca, cefaleia; evolução rápida",
        "sazonalidade": [4, 5, 6, 7, 8, 9],  # inverno sul do Brasil
        "sintomas": {
            "febre":                  0.92,  # febre alta de início ABRUPTO
            "tosse":                  0.90,
            "dor_corpo":              0.88,  # mialgia intensa — diferenciador da gripe
            "dor_cabeca":             0.85,
            "cansaco":                0.82,
            "dor_garganta":           0.70,
            "calafrios":              0.72,
            "sudorese":               0.40,
            "coriza":                 0.60,
            "falta_ar":               0.40,
            "vomito_nausea":          0.35,
            "perda_olfato_paladar":   0.20,  # pode ocorrer mas menos que COVID
            "exantema":              -0.35,
            "conjuntivite":          -0.20,
            "ictericia":             -0.70,
            "rigidez_nuca":          -0.50,
            "manchas_hemorragicas":  -0.60,
            "_intensidade_febre_alta":  0.20,
        },
        "red_flags": ["falta_ar"],
        "diferencial_vs": {
            "COVID-19": "gripe tem mialgia mais intensa; COVID tem perda de olfato mais frequente",
            "Dengue": "gripe tem coriza e dor de garganta; dengue não tem coriza",
            "Resfriado Viral": "gripe tem início mais abrupto e febre mais alta",
        },
    },

    "Resfriado Viral": {
        "grupo": "Viral respiratória leve",
        "vetor": "Rhinovirus/Coronavirus sazonal",
        "cid10": "J00",
        "descricao": "Coriza, dor de garganta, tosse leve; sem febre alta; autolimitado em 7-10 dias",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "coriza":                 1.00,  # coriza — presente quase sempre
            "dor_garganta":           0.90,
            "tosse":                  0.78,
            "cansaco":                0.55,
            "dor_cabeca":             0.45,
            "febre":                  0.20,  # febre BAIXA ou ausente
            "dor_corpo":              0.25,
            "sudorese":              -0.20,  # sudorese intensa incomum em resfriado
            "falta_ar":              -0.50,
            "perda_olfato_paladar":  -0.30,
            "exantema":              -0.70,
            "vomito_nausea":         -0.40,
            "ictericia":             -0.90,
            "rigidez_nuca":          -0.90,
            "manchas_hemorragicas":  -0.90,
            "_intensidade_febre_baixa": 0.25,
        },
        "red_flags": [],
        "diferencial_vs": {
            "Gripe": "resfriado tem coriza dominante, febre baixa; gripe tem febre alta e mialgia intensa",
            "COVID-19": "resfriado não tem falta de ar ou perda de olfato significativa",
        },
    },

    "Bronquite / DPOC Agudização": {
        "grupo": "Respiratória obstrutiva",
        "vetor": "Bacteriana/Viral/Poluição",
        "cid10": "J40",
        "descricao": "Tosse crônica com expectoração, falta de ar progressiva; geralmente sem febre alta",
        "sazonalidade": [4, 5, 6, 7, 8, 9],  # inverno
        "sintomas": {
            "tosse":                  1.00,  # tosse produtiva
            "falta_ar":               0.92,
            "cansaco":                0.60,
            "febre":                 -0.15,  # bronquite não costuma ter febre
            "dor_corpo":              0.20,
            "coriza":                 0.30,
            "sudorese":              -0.10,
            "perda_olfato_paladar":  -0.50,
            "exantema":              -0.80,
            "ictericia":             -0.80,
            "rigidez_nuca":          -0.90,
            "manchas_hemorragicas":  -0.90,
            "dor_articular":         -0.30,
        },
        "red_flags": ["falta_ar"],
        "diferencial_vs": {
            "COVID-19": "bronquite raramente tem perda de olfato; febre baixa ou ausente",
            "Hantavirose": "piora na hantavirose é muito mais rápida; contexto de exposição a roedores",
        },
    },

    # ── GASTROINTESTINAIS ────────────────────────────────────────────────────
    "Gastroenterite Viral": {
        "grupo": "Gastrointestinal",
        "vetor": "Norovírus/Rotavírus/Alimento contaminado",
        "cid10": "A08",
        "descricao": "Vômito + diarreia + cólicas; febre baixa ou ausente; autolimitada em 24-72h; risco de desidratação",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "vomito_nausea":          1.00,  # principal apresentação
            "diarreia":               0.95,  # muito frequente — quase patognomônico junto ao vômito
            "dor_abdominal":          0.88,  # cólicas abdominais — muito comuns
            "cansaco":                0.60,
            "dor_cabeca":             0.35,
            "febre":                  0.30,  # febre BAIXA é comum; alta febre aponta CONTRA GE viral
            "dor_corpo":              0.10,  # mialgia incomum em GE pura; sugere dengue/gripe
            "sudorese":              -0.15,
            "calafrios":             -0.35,  # calafrios sugere dengue, malária ou leptospirose — NÃO GE
            "tosse":                 -0.50,
            "falta_ar":              -0.60,
            "coriza":                -0.40,
            "exantema":              -0.50,
            "ictericia":             -0.35,  # icterícia = Hepatite A, não GE — forte contra-indicador
            "rigidez_nuca":          -0.70,
            "perda_olfato_paladar":  -0.70,
            "_intensidade_febre_alta": -0.25,  # alta febre sugere dengue ou processo bacteriano, não GE viral
        },
        "red_flags": ["febre", "dor_abdominal"],
        "diferencial_vs": {
            "Dengue": "dengue tem febre ALTA abrupta + dor retroorbitária + mialgia intensa — GE raramente tem todos esses; febre com dor abdominal = sinal de alarme dengue",
            "Hepatite A": "hepatite tem icterícia (pele/olhos amarelados) + fadiga intensa; GE não tem icterícia",
            "Leptospirose": "leptospirose tem histórico de contato com água/lama + mialgia intensa em panturrilhas + calafrios",
        },
    },

    "Hepatite A/B": {
        "grupo": "Viral hepática",
        "vetor": "Fecal-oral (A) / Sangue (B)",
        "cid10": "B15/B16",
        "descricao": "Icterícia + urina escura + náuseas + fadiga; hepatite A autolimitada, B pode cronificar",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "ictericia":              1.00,  # icterícia — essencial para hepatite
            "vomito_nausea":          0.85,
            "cansaco":                0.88,
            "dor_abdominal":          0.82,
            "febre":                  0.65,
            "dor_corpo":              0.55,
            "dor_cabeca":             0.45,
            "sudorese":               0.30,
            "diarreia":               0.40,
            "tosse":                 -0.60,
            "falta_ar":              -0.60,
            "coriza":                -0.60,
            "exantema":              -0.30,
            "rigidez_nuca":          -0.60,
            "perda_olfato_paladar":  -0.70,
            "manchas_hemorragicas":  -0.30,
        },
        "red_flags": ["ictericia"],
        "diferencial_vs": {
            "Leptospirose": "leptospirose tem contexto de exposição à água/ratos; hepatite tem contato fecal-oral",
            "Febre Amarela": "febre amarela tem hemorragia mais intensa; área endêmica e falta de vacinação",
        },
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# TODAS AS DOENÇAS → GRUPO EPIDEMIOLÓGICO (para RegistroSintoma.grupo)
# ──────────────────────────────────────────────────────────────────────────────
GRUPO_POR_DOENCA: dict[str, str] = {d: info["grupo"] for d, info in DOENCAS_BRASIL.items()}

# ──────────────────────────────────────────────────────────────────────────────
# PRIOR GEOGRÁFICO POR UF — P(doença | localização)
#
# Representa a probabilidade BASE de cada doença na região, INDEPENDENTE dos
# sintomas. O score final = score_sintomas × prior_geografico.
#
# Isso implementa o teorema de Bayes:
#   P(doença | sintomas, local) ∝ P(sintomas | doença) × P(doença | local)
#
# Fontes: SVS/MS, SINAN, boletins epidemiológicos regionais 2023-2024.
# Valores são RELATIVOS entre doenças por UF (não probabilidades absolutas).
# ──────────────────────────────────────────────────────────────────────────────

# Prior padrão para UFs não mapeadas (conservador)
_PRIOR_DEFAULT: dict[str, float] = {
    "Dengue":                  0.45,
    "Chikungunya":             0.20,
    "Zika":                    0.10,
    "Febre Amarela":           0.02,   # raro fora de áreas endêmicas
    "Malaria":                 0.01,   # raro fora da Amazônia
    "Leptospirose":            0.08,
    "Hantavirose":             0.02,
    "Sarampo":                 0.01,
    "Meningite":               0.05,
    "COVID-19":                0.50,
    "Gripe (Influenza)":       0.55,
    "Resfriado Viral":         0.70,
    "Bronquite / DPOC Agudização": 0.20,
    "Gastroenterite Viral":    0.55,  # GE é extremamente comum — segunda causa de atendimento em UBS
    "Hepatite A/B":            0.05,
}

# UFs com priors específicos (apenas onde diferem significativamente do padrão)
PRIOR_GEOGRAFICO: dict[str, dict[str, float]] = {

    # ── Amazônia Legal — alto risco malária e febre amarela ──────────────────
    "AM": {**_PRIOR_DEFAULT, "Malaria": 0.55, "Febre Amarela": 0.12, "Dengue": 0.60, "Leptospirose": 0.12},
    "PA": {**_PRIOR_DEFAULT, "Malaria": 0.45, "Febre Amarela": 0.10, "Dengue": 0.55, "Leptospirose": 0.10},
    "AC": {**_PRIOR_DEFAULT, "Malaria": 0.50, "Febre Amarela": 0.12, "Dengue": 0.50},
    "RO": {**_PRIOR_DEFAULT, "Malaria": 0.40, "Febre Amarela": 0.10, "Dengue": 0.55},
    "RR": {**_PRIOR_DEFAULT, "Malaria": 0.45, "Febre Amarela": 0.10, "Dengue": 0.50},
    "AP": {**_PRIOR_DEFAULT, "Malaria": 0.35, "Febre Amarela": 0.08, "Dengue": 0.55},
    "TO": {**_PRIOR_DEFAULT, "Malaria": 0.15, "Febre Amarela": 0.08, "Dengue": 0.65},

    # ── Centro-Oeste — risco moderado febre amarela (área de transição) ──────
    "MT": {**_PRIOR_DEFAULT, "Malaria": 0.12, "Febre Amarela": 0.07, "Dengue": 0.70},
    "GO": {**_PRIOR_DEFAULT, "Febre Amarela": 0.05, "Dengue": 0.72, "Chikungunya": 0.25},
    "MS": {**_PRIOR_DEFAULT, "Febre Amarela": 0.04, "Dengue": 0.65, "Leptospirose": 0.12},
    "DF": {**_PRIOR_DEFAULT, "Febre Amarela": 0.03, "Dengue": 0.68, "Chikungunya": 0.22},

    # ── Sudeste — urbano, dengue/chikungunya dominam; febre amarela mínima ───
    "SP": {**_PRIOR_DEFAULT, "Dengue": 0.75, "Chikungunya": 0.30, "Febre Amarela": 0.015,
           "COVID-19": 0.55, "Gripe (Influenza)": 0.60},
    "RJ": {**_PRIOR_DEFAULT, "Dengue": 0.80, "Chikungunya": 0.35, "Zika": 0.18,
           "Febre Amarela": 0.005,   # praticamente ausente em RJ urbano
           "Malaria": 0.001,         # quase impossível em RJ
           "COVID-19": 0.55, "Gripe (Influenza)": 0.58},
    "MG": {**_PRIOR_DEFAULT, "Dengue": 0.72, "Chikungunya": 0.28, "Febre Amarela": 0.04,
           "Leptospirose": 0.10},
    "ES": {**_PRIOR_DEFAULT, "Dengue": 0.75, "Chikungunya": 0.30, "Febre Amarela": 0.02,
           "Leptospirose": 0.10},

    # ── Nordeste — dengue altíssima, chikungunya elevada ────────────────────
    "BA": {**_PRIOR_DEFAULT, "Dengue": 0.78, "Chikungunya": 0.40, "Febre Amarela": 0.03},
    "PE": {**_PRIOR_DEFAULT, "Dengue": 0.80, "Chikungunya": 0.45, "Zika": 0.25,
           "Febre Amarela": 0.01},
    "CE": {**_PRIOR_DEFAULT, "Dengue": 0.78, "Chikungunya": 0.42, "Febre Amarela": 0.01},
    "MA": {**_PRIOR_DEFAULT, "Dengue": 0.70, "Chikungunya": 0.35, "Febre Amarela": 0.03,
           "Malaria": 0.08},
    "PI": {**_PRIOR_DEFAULT, "Dengue": 0.72, "Chikungunya": 0.35, "Febre Amarela": 0.03},
    "RN": {**_PRIOR_DEFAULT, "Dengue": 0.75, "Chikungunya": 0.38, "Febre Amarela": 0.01},
    "PB": {**_PRIOR_DEFAULT, "Dengue": 0.73, "Chikungunya": 0.37, "Febre Amarela": 0.01},
    "AL": {**_PRIOR_DEFAULT, "Dengue": 0.72, "Chikungunya": 0.36, "Febre Amarela": 0.01},
    "SE": {**_PRIOR_DEFAULT, "Dengue": 0.70, "Chikungunya": 0.35, "Febre Amarela": 0.01},

    # ── Sul — dengue crescente, gripe/covid prevalentes no inverno ───────────
    "PR": {**_PRIOR_DEFAULT, "Dengue": 0.65, "Chikungunya": 0.20, "Febre Amarela": 0.02,
           "Gripe (Influenza)": 0.65, "COVID-19": 0.55},
    "SC": {**_PRIOR_DEFAULT, "Dengue": 0.40, "Chikungunya": 0.12, "Febre Amarela": 0.01,
           "Gripe (Influenza)": 0.70, "COVID-19": 0.58, "Resfriado Viral": 0.75},
    "RS": {**_PRIOR_DEFAULT, "Dengue": 0.38, "Chikungunya": 0.10, "Febre Amarela": 0.01,
           "Gripe (Influenza)": 0.70, "COVID-19": 0.58, "Leptospirose": 0.15},
}


def _prior_geografico(doenca: str, estado: str | None) -> float:
    """
    Retorna o prior geográfico da doença para o estado informado.
    Se estado não mapeado, usa default conservador.
    Prior é multiplicador (0.001 a 1.0).
    """
    uf = (estado or "").strip().upper()
    # Aceitar nome completo mapeando para sigla
    _nome_para_sigla = {
        "RIO DE JANEIRO": "RJ", "SÃO PAULO": "SP", "MINAS GERAIS": "MG",
        "BAHIA": "BA", "PERNAMBUCO": "PE", "CEARÁ": "CE", "AMAZONAS": "AM",
        "PARÁ": "PA", "GOIÁS": "GO", "MATO GROSSO": "MT",
        "MATO GROSSO DO SUL": "MS", "PARANÁ": "PR", "SANTA CATARINA": "SC",
        "RIO GRANDE DO SUL": "RS", "MARANHÃO": "MA", "PIAUÍ": "PI",
        "RIO GRANDE DO NORTE": "RN", "PARAÍBA": "PB", "ALAGOAS": "AL",
        "SERGIPE": "SE", "ESPÍRITO SANTO": "ES", "RONDÔNIA": "RO",
        "ACRE": "AC", "RORAIMA": "RR", "AMAPÁ": "AP", "TOCANTINS": "TO",
        "DISTRITO FEDERAL": "DF",
    }
    if len(uf) > 2:
        uf = _nome_para_sigla.get(uf, "")
    priors_uf = PRIOR_GEOGRAFICO.get(uf, _PRIOR_DEFAULT)
    return priors_uf.get(doenca, _PRIOR_DEFAULT.get(doenca, 0.05))


# ──────────────────────────────────────────────────────────────────────────────
# SINTOMA MÍNIMO OBRIGATÓRIO para doenças raras
# Para aparecer no ranking, doenças raras exigem ao menos 1 sintoma "chave"
# presente. Sem ele, o score é zerado antes mesmo de chegar ao usuário.
# Isso evita que febre simples gere suspeita de febre amarela.
# ──────────────────────────────────────────────────────────────────────────────
SINTOMA_CHAVE_OBRIGATORIO: dict[str, list[str]] = {
    # Arboviroses: são doenças febris por definição — sem febre reportada,
    # não classificar como arbovirose (evita "Síndrome Febril" quando não há febre).
    "Dengue":         ["febre"],
    "Zika":           ["febre"],
    "Chikungunya":    ["febre"],
    "Febre Amarela":  ["ictericia", "manchas_hemorragicas"],       # sem icterícia ou hemorragia, não é FA
    "Malaria":        ["calafrios"],                                 # sem calafrios cíclicos, não é malária
    "Meningite":      ["rigidez_nuca"],                              # sem rigidez nuca, não é meningite
    "Hantavirose":    ["falta_ar"],                                  # síndrome cardiopulmonar obrigatória
    "Sarampo":        ["exantema"],                                  # sem exantema, não é sarampo
    "Leptospirose":   ["ictericia", "dor_corpo", "calafrios"],       # precisa ≥1 dos 3
    "Hepatite A/B":   ["ictericia"],                                 # icterícia é essencial
}

# ──────────────────────────────────────────────────────────────────────────────
# SAÍDA PARA CIDADÃO — syndromes genéricas sem nomear doença rara
# O cidadão NÃO deve ver "Febre Amarela" — isso gera pânico.
# Vê apenas a síndrome clínica + orientação de conduta.
# ──────────────────────────────────────────────────────────────────────────────
SINDROME_CIDADAO: dict[str, dict] = {
    "Dengue":               {"sindrome": "Síndrome Febril com Dores",       "cor": "amarela", "conduta": "Hidratação e repouso. Procure UBS se piorar em 48h. Não tome AAS ou ibuprofeno."},
    "Zika":                 {"sindrome": "Síndrome Febril com Manchas",     "cor": "amarela", "conduta": "Repouso e hidratação. Gestantes: consulta médica urgente."},
    "Chikungunya":          {"sindrome": "Síndrome Febril com Dores Articulares", "cor": "amarela", "conduta": "Repouso, hidratação e analgésico. Procure UBS se as dores forem intensas."},
    "Febre Amarela":        {"sindrome": "Síndrome Febril com Alteração Hepática", "cor": "vermelha", "conduta": "Procure pronto-socorro imediatamente. Informe sobre vacinação para febre amarela."},
    "Malaria":              {"sindrome": "Síndrome Febril com Calafrios",   "cor": "laranja", "conduta": "Procure UBS — é necessário exame de gota espessa para diagnóstico."},
    "Leptospirose":         {"sindrome": "Síndrome Febril com Dores Musculares", "cor": "laranja", "conduta": "Informe ao médico sobre exposição à água de enchente ou animais. Procure UBS."},
    "Hantavirose":          {"sindrome": "Síndrome Respiratória Aguda",     "cor": "vermelha", "conduta": "URGÊNCIA — procure pronto-socorro agora. Informe sobre contato com roedores."},
    "Sarampo":              {"sindrome": "Síndrome Exantemática Febril",    "cor": "laranja", "conduta": "Isolamento domiciliar e procure UBS. Confirme situação vacinal."},
    "Meningite":            {"sindrome": "Síndrome Neurológica Febril",     "cor": "vermelha", "conduta": "EMERGÊNCIA — vá ao pronto-socorro agora."},
    "COVID-19":             {"sindrome": "Síndrome Respiratória Viral",     "cor": "amarela", "conduta": "Isolamento por 5 dias. Procure UBS se falta de ar ou saturação < 95%."},
    "Gripe (Influenza)":    {"sindrome": "Síndrome Gripal",                 "cor": "verde",   "conduta": "Repouso, hidratação, analgésico. Procure UBS se piorar em 48h."},
    "Resfriado Viral":      {"sindrome": "Resfriado Comum",                 "cor": "verde",   "conduta": "Repouso e hidratação. Autolimitado em 7-10 dias."},
    "Bronquite / DPOC Agudização": {"sindrome": "Síndrome Respiratória Obstrutiva", "cor": "amarela", "conduta": "Procure médico para avaliação. Evite exposição a fumaça ou poeira."},
    "Gastroenterite Viral": {
        "sindrome": "Síndrome Diarreica",
        "cor": "verde",
        "conduta": (
            "Hidrate-se bastante: água, soro caseiro (1L água + 1 colher sopa açúcar + 1 colher chá sal) "
            "ou soro de reidratação oral da farmácia. Repouso e dieta leve (arroz, banana, torrada). "
            "PROCURE UBS SE: febre acima de 38,5°C por mais de 24h, sangue nas fezes, "
            "dor abdominal intensa e persistente, incapacidade de manter líquidos, "
            "criança muito sonolenta ou adulto com tontura ao levantar."
        ),
    },
    "Hepatite A/B":         {"sindrome": "Síndrome Hepática Febril",        "cor": "laranja", "conduta": "Procure UBS para exames. Evite álcool e medicamentos sem orientação médica."},
    "Inconclusivo":         {"sindrome": "Sintomas em Acompanhamento",      "cor": "cinza",   "conduta": "Continue monitorando seus sintomas. Se piorar, procure uma unidade de saúde."},
}

# ──────────────────────────────────────────────────────────────────────────────
# FLAGS ABSOLUTOS DE URGÊNCIA — independente do score, alertar imediatamente
# ──────────────────────────────────────────────────────────────────────────────
URGENCIA_ABSOLUTA: list[tuple[str, str, str]] = [
    ("rigidez_nuca",          "MENINGITE POSSÍVEL — evacuação imediata",
     "Rigidez de nuca é sinal de meningite até prova em contrário. Encaminhar para PS agora."),
    ("manchas_hemorragicas",  "SANGRAMENTO — avaliação urgente",
     "Petéquias/púrpura podem indicar dengue hemorrágico ou meningococcemia. Não aguardar."),
    ("ictericia",             "ICTERÍCIA — disfunção hepática",
     "Icterícia com febre indica febre amarela, leptospirose ou hepatite grave. Avaliar imediatamente."),
    ("falta_ar",              "DISPNEIA — verificar saturação",
     "Falta de ar com febre pode indicar COVID grave, hantavirose ou pneumonia. Monitorar SpO2."),
    ("perda_olfato_paladar",  "PERDA OLFATO/PALADAR — protocolo COVID",
     "Fortemente sugestivo de COVID-19. Aplicar protocolo de isolamento e testagem."),
]

# ──────────────────────────────────────────────────────────────────────────────
# CONTEXTO POR SETOR — o que cada ambiente quer saber (isolado por setor)
# ──────────────────────────────────────────────────────────────────────────────
CONTEXTO_SETOR: dict[str, dict] = {
    "governo": {
        "prioridade": ["Meningite", "Febre Amarela", "Sarampo", "Hantavirose", "Leptospirose"],
        "foco": "vigilância sanitária, notificação compulsória, resposta pública",
        "alerta_notificacao": ["Meningite", "Febre Amarela", "Sarampo", "Hantavirose", "Dengue", "Malaria", "Leptospirose"],
        "filtro_grupo": None,  # vê tudo
        "mensagem_acao": "Acionar vigilância epidemiológica e preparar notificação compulsória.",
    },
    "farmacia": {
        "prioridade": ["Dengue", "Gripe (Influenza)", "COVID-19", "Resfriado Viral", "Gastroenterite Viral"],
        "foco": "demanda de balcão, itens em falta, orientação responsável",
        "alerta_notificacao": [],
        "filtro_grupo": None,
        "mensagem_acao": "Verificar estoque de itens associados ao padrão dominante.",
    },
    "hospital": {
        "prioridade": ["Meningite", "Hantavirose", "Febre Amarela", "Dengue", "COVID-19", "Leptospirose"],
        "foco": "triagem, leitos, insumos críticos, escala de pronto atendimento",
        "alerta_notificacao": ["Meningite", "Febre Amarela", "Hantavirose", "Sarampo"],
        "filtro_grupo": None,
        "mensagem_acao": "Revisar fluxo de triagem e disponibilidade de leitos.",
    },
    "plano_saude": {
        "prioridade": ["Dengue", "COVID-19", "Gripe (Influenza)", "Chikungunya", "Zika", "Leptospirose"],
        "foco": "sinistralidade, autorização de guias, programas de saúde gerenciada, risco populacional",
        "alerta_notificacao": [],
        "filtro_grupo": None,
        "mensagem_acao": "Avaliar impacto em sinistralidade e acionar programas de prevenção.",
    },
    "rede": {
        "prioridade": ["Dengue", "Gripe (Influenza)", "COVID-19", "Resfriado Viral"],
        "foco": "demanda de consultas na rede credenciada, triagem, encaminhamento",
        "alerta_notificacao": [],
        "filtro_grupo": None,
        "mensagem_acao": "Sinalizar aumento de demanda para unidades próximas à área de risco.",
    },
    "empresa": {
        "prioridade": ["Gripe (Influenza)", "COVID-19", "Resfriado Viral", "Dengue"],
        "foco": "absenteísmo, saúde ocupacional, continuidade operacional",
        "alerta_notificacao": [],
        "filtro_grupo": None,
        "mensagem_acao": "Orientar equipes e acionar SESMT para prevenção e acompanhamento.",
    },
    "sst": {
        "prioridade": ["Gripe (Influenza)", "COVID-19", "Leptospirose", "Hantavirose"],
        "foco": "saúde do trabalhador, NRs, afastamentos, exposição ocupacional",
        "alerta_notificacao": ["Leptospirose", "Hantavirose"],
        "filtro_grupo": None,
        "mensagem_acao": "Verificar exposição ocupacional e acionar protocolo de afastamento se necessário.",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# NORMALIZAR CAMPOS DE SINTOMA DO RegistroSintoma → dict para classificar
# ──────────────────────────────────────────────────────────────────────────────
TODOS_SINTOMAS = [
    "febre", "tosse", "dor_corpo", "cansaco", "falta_ar",
    "dor_cabeca", "dor_articular", "exantema", "conjuntivite",
    "vomito_nausea", "diarreia", "dor_abdominal", "rigidez_nuca",
    "ictericia", "manchas_hemorragicas", "perda_olfato_paladar",
    "dor_garganta", "coriza", "calafrios", "sudorese",
]

# Campos de anamnese epidemiológica — contexto clínico que refina o prior
CAMPOS_ANAMNESE = [
    "dias_sintomas", "inicio_abrupto", "viagem_area_endemica",
    "exposicao_agua_enchente", "contato_roedores", "contato_caso_confirmado",
    "vacinado_febre_amarela", "tem_comorbidade",
]


def sintomas_do_registro(registro) -> dict[str, Any]:
    """Extrai todos os campos de sintoma e anamnese de um RegistroSintoma para dict classificável."""
    dados: dict[str, Any] = {}
    for campo in TODOS_SINTOMAS:
        dados[campo] = bool(getattr(registro, campo, False))
    dados["intensidade_febre"] = getattr(registro, "intensidade_febre", "") or ""
    dados["intensidade_articular"] = getattr(registro, "intensidade_articular", "") or ""
    # Dados geográficos — essenciais para o prior bayesiano
    dados["estado"] = getattr(registro, "estado", None) or ""
    dados["cidade"] = getattr(registro, "cidade", None) or ""
    # Dados de anamnese epidemiológica
    for campo in CAMPOS_ANAMNESE:
        dados[campo] = getattr(registro, campo, None)
    return dados


# ──────────────────────────────────────────────────────────────────────────────
# MOTOR DE CLASSIFICAÇÃO PROBABILÍSTICA
# ──────────────────────────────────────────────────────────────────────────────

def _bônus_sazonalidade(doenca: str, mes: int) -> float:
    """Bônus de score se o mês atual está na sazonalidade da doença."""
    meses = DOENCAS_BRASIL[doenca].get("sazonalidade", [])
    return 0.08 if mes in meses else 0.0


def _calcular_score_doenca(doenca: str, dados: dict[str, Any], mes: int) -> float:
    """
    Calcula score bruto para uma doença dado o conjunto de sintomas.
    Lógica: soma ponderada de sintomas presentes (positivos) + penalidades de ausentes (negativos).
    """
    pesos = DOENCAS_BRASIL[doenca]["sintomas"]
    score = 0.0
    sintomas_presentes = 0

    for sintoma, peso in pesos.items():
        # Campos de intensidade especiais
        if sintoma.startswith("_intensidade_"):
            parts = sintoma.split("_")[2:]
            campo_base = parts[0]
            nivel_esperado = parts[1]
            campo_real = f"intensidade_{campo_base}"
            valor = str(dados.get(campo_real, "")).lower()
            if valor == nivel_esperado:
                score += peso
            continue

        valor = dados.get(sintoma, False)
        if isinstance(valor, bool):
            if valor:
                if peso > 0:
                    score += peso
                    sintomas_presentes += 1
                elif peso < 0:
                    score += peso
            # sintoma AUSENTE com peso negativo = não penaliza
            # sintoma AUSENTE com peso positivo = não adiciona

    # Bônus sazonalidade
    score += _bônus_sazonalidade(doenca, mes)

    # Normalizar: score nunca negativo para ranking
    return max(score, 0.0)


def _sintoma_chave_presente(doenca: str, dados: dict[str, Any]) -> bool:
    """
    Para doenças raras com SINTOMA_CHAVE_OBRIGATORIO: verifica se ao menos
    1 dos sintomas-chave está presente. Se não estiver, zera o score.
    Isso impede que "febre + cansaço" gere suspeita de Febre Amarela.
    """
    chaves = SINTOMA_CHAVE_OBRIGATORIO.get(doenca)
    if not chaves:
        return True   # sem restrição
    return any(dados.get(s) for s in chaves)


def _prior_anamnese_override(prior: float, doenca: str, dados: dict[str, Any]) -> float:
    """
    Para exposições patognomônicas, garante um prior mínimo que reflete o risco real.
    Exemplo: contato com roedores + Hantavirose → prior mínimo 0.40, não 0.02.
    Isso evita que o prior geográfico (base na população geral) subestime doenças
    raras quando o fator de exposição específico está presente.
    """
    if dados.get("contato_roedores"):
        if doenca == "Hantavirose":
            # Roedores = vetor específico — prior base de 0.02 é irrelevante com exposição direta
            return max(prior, 0.55)
        if doenca == "Leptospirose":
            # Transmissão pelo contato com urina de roedor — risco ocupacional alto
            return max(prior, 0.55)

    if dados.get("exposicao_agua_enchente"):
        if doenca == "Leptospirose":
            return max(prior, 0.45)
        if doenca == "Hepatite A/B":
            return max(prior, 0.15)

    # Reduzir prior de Leptospirose quando AMBAS as vias de transmissão são negadas
    if dados.get("exposicao_agua_enchente") is False and dados.get("contato_roedores") is False:
        if doenca == "Leptospirose":
            return min(prior, 0.01)   # praticamente impossível sem exposição confirmada

    # Reduzir prior de Malária quando viagem endêmica é negada
    if dados.get("viagem_area_endemica") is False and doenca == "Malaria":
        return min(prior, 0.005)  # sem viagem à Amazônia/pantanal, malária urbana é rarissima

    # Reduzir prior de Hantavirose quando contato com roedores é negado
    if dados.get("contato_roedores") is False and doenca == "Hantavirose":
        return min(prior, 0.005)

    if dados.get("viagem_area_endemica"):
        if doenca == "Malaria":
            # Tríade febril em retornante da Amazônia — prior geográfico de SP (0.01) é irrelevante
            return max(prior, 0.55)
        if doenca == "Febre Amarela":
            fa_prior = 0.25  # viajante sem info vacinal — risco aumentado
            if dados.get("vacinado_febre_amarela") is False:
                # Não vacinado + viagem à área endêmica = risco muito alto
                fa_prior = 0.65
            return max(prior, fa_prior)
        if doenca in ("Dengue", "Chikungunya", "Zika"):
            return max(prior, 0.50)

    # Sintomas patognomônicos — sobrepõem o prior geográfico independentemente do local
    if dados.get("rigidez_nuca"):
        if doenca == "Meningite":
            return max(prior, 0.60)

    # Tríade de Zika: exantema pruriginoso + conjuntivite + (opcional febre baixa)
    # Prior geográfico de Zika (0.10-0.18) é muito baixo vs COVID (0.50) — sem override, Zika nunca vence.
    if dados.get("exantema") and dados.get("conjuntivite"):
        if doenca == "Zika":
            zika_prior = 0.40  # exantema + conjuntivite = padrão de Zika
            if str(dados.get("intensidade_febre", "")).lower() == "baixa":
                zika_prior = 0.55  # tríade completa: febre baixa + exantema + conjuntivite
            return max(prior, zika_prior)

    # icterícia é sinal patognomônico de disfunção hepática — forte evidência contra Dengue típica.
    # Prior de Hepatite A/B (0.05) destruiria o sinal contra Dengue (0.75) sem este override.
    # Febre Amarela e Leptospirose também têm icterícia — dar prior mínimo defensivo a ambas.
    if dados.get("ictericia"):
        if doenca == "Hepatite A/B":
            # Paciente com icterícia tem prob. muito alta de hepatite, independente do estado.
            # 0.65 garante que Hepatite A/B vença Dengue mesmo em RJ (prior 0.80).
            return max(prior, 0.65)
        if doenca == "Febre Amarela":
            return max(prior, 0.20)
        if doenca == "Leptospirose":
            return max(prior, 0.20)

    return prior


def _modificadores_anamnese(dados: dict[str, Any], doenca: str) -> float:
    """
    Retorna um multiplicador fino baseado no histórico epidemiológico.
    O override de prior já garante que doenças raras entrem no ranking;
    este multiplicador refina a posição no ranking dentro da doença.
    """
    mult = 1.0

    # Viagem para área endêmica — boost adicional após override de prior
    if dados.get("viagem_area_endemica"):
        if doenca in ("Malaria", "Febre Amarela"):
            mult *= 2.0
        elif doenca in ("Dengue", "Chikungunya", "Zika", "Leptospirose"):
            mult *= 1.5

    # Exposição à água de enchente/lama
    if dados.get("exposicao_agua_enchente"):
        if doenca == "Leptospirose":
            mult *= 2.0
        elif doenca == "Hepatite A/B":
            mult *= 2.0

    # Contato com roedores — override de prior já garante piso; modifier amplifica a vantagem
    if dados.get("contato_roedores"):
        if doenca == "Hantavirose":
            mult *= 2.5
        elif doenca == "Leptospirose":
            mult *= 2.0

    # Leptospirose sem vias de transmissão: penalidade forte quando AMBAS são explicitamente negadas.
    # Transmissão da leptospirose é quase exclusivamente via exposição a água contaminada
    # ou contato com urina de roedor. Sem as duas, é epidemiologicamente improvável.
    if doenca == "Leptospirose":
        agua = dados.get("exposicao_agua_enchente")
        ratos = dados.get("contato_roedores")
        if agua is False and ratos is False:
            mult *= 0.05   # ambas as vias negadas → praticamente excluída
        elif agua is False or ratos is False:
            mult *= 0.30   # uma via negada → ainda possível mas improvável

    # Hantavirose sem contato com roedores → quase impossível (transmissão é aerossol de roedor)
    if doenca == "Hantavirose" and dados.get("contato_roedores") is False:
        mult *= 0.05

    # Malária sem viagem para área endêmica → praticamente impossível no Brasil urbano
    if doenca == "Malaria" and dados.get("viagem_area_endemica") is False:
        mult *= 0.05

    # Contato com caso confirmado — doenças de transmissão pessoa-a-pessoa
    if dados.get("contato_caso_confirmado"):
        if doenca in ("COVID-19", "Gripe (Influenza)", "Sarampo", "Meningite"):
            mult *= 3.0
        elif doenca == "Resfriado Viral":
            mult *= 2.0
        elif doenca in ("Dengue", "Chikungunya", "Zika"):
            mult *= 1.1  # transmissão vetorial, não por contato direto

    # Vacinado para febre amarela → elimina FA quase completamente
    if dados.get("vacinado_febre_amarela") is True and doenca == "Febre Amarela":
        mult *= 0.02

    # Início abrupto vs gradual — diferencia dengue/gripe de resfriado
    # BUG FIX: Gastroenterite viral e Leptospirose também têm início abrupto típico.
    # Sem incluí-las, inicio_abrupto=True favorecia Dengue sobre GE indevidamente.
    inicio = dados.get("inicio_abrupto")
    if inicio is True:
        if doenca in ("Dengue", "Gripe (Influenza)", "Chikungunya", "Meningite", "Malaria",
                      "Gastroenterite Viral", "Leptospirose", "Hantavirose"):
            mult *= 1.5
        elif doenca in ("Resfriado Viral", "Bronquite / DPOC Agudização"):
            mult *= 0.4
    elif inicio is False:
        if doenca in ("Resfriado Viral", "COVID-19", "Bronquite / DPOC Agudização"):
            mult *= 1.4
        elif doenca in ("Dengue", "Gripe (Influenza)", "Malaria"):
            mult *= 0.5

    # Comorbidade → aumenta risco de formas graves
    if dados.get("tem_comorbidade"):
        if doenca in ("COVID-19", "Gripe (Influenza)", "Dengue", "Leptospirose"):
            mult *= 1.3

    return mult


def _score_bayesiano(score_sintomas: float, doenca: str, estado: str | None,
                     dados: dict[str, Any] | None = None) -> float:
    """
    Aplica prior geográfico + override anamnese + modificadores ao score de sintomas.

    score = P(sintomas|doença) × P(doença|local) × P(doença|exposição) × ajuste_fino

    Para exposições patognomônicas (contato_roedores, exposicao_agua_enchente,
    viagem_area_endemica), o prior é elevado ao mínimo necessário antes de
    aplicar o multiplicador, garantindo que doenças raras sejam visíveis no ranking
    quando o contexto clínico é específico.
    """
    prior = _prior_geografico(doenca, estado)
    if dados:
        prior = _prior_anamnese_override(prior, doenca, dados)
    score = score_sintomas * prior
    if dados:
        score *= _modificadores_anamnese(dados, doenca)
    return score


def _confianca(score_doenca: float, score_total: float, sintomas_presentes: int) -> int:
    """
    Confiança em % da classificação (35-95).
    Quanto maior o score relativo e mais sintomas, maior a confiança.
    """
    if score_total <= 0:
        return 35
    ratio = score_doenca / score_total
    base = 35 + (ratio * 45)
    bonus_sintomas = min(sintomas_presentes * 2, 15)
    return int(min(max(round(base + bonus_sintomas), 35), 95))


def classificar(dados: dict[str, Any], setor: str = "governo", estado: str | None = None) -> dict:
    """
    Motor principal de classificação probabilística.

    Parâmetros:
        dados: dict com campos bool de sintomas + intensidade_febre + intensidade_articular
        setor: contexto do ambiente ('farmacia', 'hospital', 'governo', 'plano_saude', etc.)

    Retorna:
        {
          "primario": str,           # doença mais provável
          "score": float,
          "grupo": str,              # grupo epidemiológico
          "confianca": int,          # 35-95%
          "ranking": [...],          # top 5 doenças com scores
          "red_flags": [...],        # alertas de urgência encontrados
          "urgencia_absoluta": [...],# flags críticas independentes de score
          "diagnostico_diferencial": str, # texto explicando a diferenciação
          "contexto_setor": {...},   # o que este setor deve fazer
          "sintomas_ativos": [...],  # sintomas positivos reportados
          "sintomas_count": int,
          "aprender": {...},         # para sistema de feedback/aprendizado
        }
    """
    mes_atual = date.today().month
    sintomas_ativos = [s for s in TODOS_SINTOMAS if dados.get(s)]
    sintomas_count = len(sintomas_ativos)

    # Estado do registro (pode vir em dados ou no parâmetro direto)
    uf = estado or dados.get("estado") or ""

    # ── Verificar urgência absoluta (independente de score) ────────────────
    urgencias = []
    for campo, titulo, descricao in URGENCIA_ABSOLUTA:
        if dados.get(campo):
            urgencias.append({"campo": campo, "titulo": titulo, "descricao": descricao})

    # ── Calcular scores bayesianos para todas as doenças ──────────────────
    # score = P(sintomas|doença) × P(doença|local)  [Bayes simplificado]
    scores: dict[str, float] = {}
    for doenca in DOENCAS_BRASIL:
        score_bruto = _calcular_score_doenca(doenca, dados, mes_atual)

        # Zerar doenças raras sem sintoma-chave presente
        if not _sintoma_chave_presente(doenca, dados):
            score_bruto = 0.0

        # Aplicar prior geográfico + modificadores de anamnese
        scores[doenca] = _score_bayesiano(score_bruto, doenca, uf, dados)

    # ── Sem sintomas suficientes ──────────────────────────────────────────
    if sintomas_count == 0:
        return {
            "primario": "Inconclusivo",
            "score": 0.0,
            "grupo": "Indefinido",
            "confianca": 0,
            "ranking": [],
            "red_flags": [],
            "urgencia_absoluta": urgencias,
            "diagnostico_diferencial": "Nenhum sintoma informado. Coletando dados.",
            "contexto_setor": CONTEXTO_SETOR.get(setor, CONTEXTO_SETOR["governo"]),
            "sintomas_ativos": sintomas_ativos,
            "sintomas_count": 0,
            "aprender": {"feedback_esperado": True, "confirmacao_pendente": True},
        }

    score_total = sum(scores.values())

    # ── Ranking top 5 ──────────────────────────────────────────────────────
    ranking_completo = sorted(scores.items(), key=lambda x: -x[1])
    top5 = [
        {
            "doenca": d,
            "score": round(s, 3),
            "grupo": DOENCAS_BRASIL[d]["grupo"],
            "cid10": DOENCAS_BRASIL[d].get("cid10", ""),
            "confianca": _confianca(s, score_total, sintomas_count),
            "descricao": DOENCAS_BRASIL[d]["descricao"],
            "diferencial_vs": DOENCAS_BRASIL[d].get("diferencial_vs", {}),
        }
        for d, s in ranking_completo[:5]
        if s > 0
    ]

    primario = top5[0] if top5 else None
    doenca_principal = primario["doenca"] if primario else "Inconclusivo"
    score_principal = primario["score"] if primario else 0.0
    confianca_principal = primario["confianca"] if primario else 0

    # ── Red flags da doença principal ─────────────────────────────────────
    red_flags_doenca = []
    if primario:
        flags = DOENCAS_BRASIL[doenca_principal].get("red_flags", [])
        for flag in flags:
            if dados.get(flag):
                red_flags_doenca.append(flag)

    # ── Diagnóstico diferencial em texto ──────────────────────────────────
    diferencial_txt = ""
    if primario and len(top5) > 1:
        segundo = top5[1]["doenca"]
        diff_dict = DOENCAS_BRASIL[doenca_principal].get("diferencial_vs", {})
        if segundo in diff_dict:
            diferencial_txt = f"vs {segundo}: {diff_dict[segundo]}"
        else:
            ratio = top5[1]["score"] / max(score_principal, 0.001)
            if ratio > 0.7:
                diferencial_txt = (
                    f"Padrão próximo a {segundo} (score {round(ratio*100)}% do principal). "
                    f"Considerar diagnóstico diferencial clínico."
                )

    # ── Contexto para o setor ─────────────────────────────────────────────
    ctx_setor = CONTEXTO_SETOR.get(setor, CONTEXTO_SETOR["governo"]).copy()
    ctx_setor["relevante_para_setor"] = doenca_principal in ctx_setor.get("prioridade", [])
    ctx_setor["requer_notificacao"] = doenca_principal in ctx_setor.get("alerta_notificacao", [])

    # ── Bloco de aprendizado ──────────────────────────────────────────────
    aprender = {
        "feedback_esperado": True,
        "confirmacao_pendente": True,
        "campo_confirmacao": "doenca_confirmada",
        "instrucao": (
            "Quando a doença for confirmada por exame, registrar em doenca_confirmada "
            "para calibrar o motor de classificação."
        ),
        "calibracao_ativa": True,
    }

    return {
        "primario": doenca_principal,
        "score": round(score_principal, 3),
        "grupo": DOENCAS_BRASIL.get(doenca_principal, {}).get("grupo", "Indefinido"),
        "cid10": DOENCAS_BRASIL.get(doenca_principal, {}).get("cid10", ""),
        "confianca": confianca_principal,
        "ranking": top5,
        "red_flags": red_flags_doenca,
        "urgencia_absoluta": urgencias,
        "diagnostico_diferencial": diferencial_txt,
        "contexto_setor": ctx_setor,
        "sintomas_ativos": sintomas_ativos,
        "sintomas_count": sintomas_count,
        "aprender": aprender,
        "safeguard": (
            "Classificação de apoio. Não substitui diagnóstico médico, exames laboratoriais "
            "ou avaliação clínica presencial. Sempre validar com profissional de saúde."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# SAÍDA PARA CIDADÃO — retorna síndrome genérica, não nome da doença rara
# Uso: app mobile, tela de resultado para o usuário final
# ──────────────────────────────────────────────────────────────────────────────

def classificar_para_cidadao(dados: dict[str, Any], estado: str | None = None) -> dict:
    """
    Versão cidadão do classificador — retorna síndrome clínica genérica
    em vez do nome da doença. Previne pânico por falsos diagnósticos raros.

    Regras:
      • Urgências absolutas (rigidez nuca, manchas, icterícia, falta ar) →
        sempre mostrar alerta direto de "ir ao PS" sem nomear a doença rara
      • Doenças comuns (dengue, gripe, resfriado, COVID, gastro) → pode nomear
      • Doenças raras (febre amarela, malária, meningite, hantavirose) →
        mostrar apenas a síndrome genérica
      • Confiança < 50% → "Sintomas em acompanhamento" independente da doença
    """
    resultado = classificar(dados, setor="governo", estado=estado)

    doenca = resultado["primario"]
    confianca = resultado["confianca"]
    urgencias = resultado["urgencia_absoluta"]

    # Doenças que podem ser nomeadas ao cidadão (comuns, baixo pânico)
    DOENCAS_NOMINAVEIS = {
        "Dengue", "Chikungunya", "Zika", "COVID-19",
        "Gripe (Influenza)", "Resfriado Viral",
        "Bronquite / DPOC Agudização", "Gastroenterite Viral",
    }

    # Se confiança muito baixa → inconclusivo para o cidadão
    if confianca < 45 or doenca == "Inconclusivo":
        info_sindrome = SINDROME_CIDADAO["Inconclusivo"]
    else:
        info_sindrome = SINDROME_CIDADAO.get(doenca, SINDROME_CIDADAO["Inconclusivo"])

    # Guarda: se a síndrome contém "Febril" mas o cidadão NÃO reportou febre,
    # rebaixar para síndrome genérica — evita "Síndrome Febril com Dores" quando
    # nenhuma febre foi marcada (o prior geográfico pode ter inflado Dengue/arbovírus).
    if not dados.get("febre") and "Febril" in info_sindrome.get("sindrome", ""):
        info_sindrome = SINDROME_CIDADAO["Inconclusivo"]

    # Guarda: se Leptospirose é primária mas ambas as vias de exposição foram negadas,
    # não mencionar "enchente/animais" na conduta — seria clinicamente enganoso.
    if doenca == "Leptospirose":
        agua = dados.get("exposicao_agua_enchente")
        ratos = dados.get("contato_roedores")
        if agua is False and ratos is False:
            # Reclassificar como síndrome febril genérica — sem menção a leptospirose
            info_sindrome = {
                "sindrome": "Síndrome Febril com Dores Musculares",
                "cor": "amarela",
                "conduta": "Repouso e hidratação. Procure UBS se a febre persistir por mais de 48h ou se surgirem manchas, icterícia ou piora do estado geral.",
            }

    # Gastroenterite com febre + dor abdominal → escalação para amarela.
    # Esses dois sinais juntos são sinal de alarme para dengue — não podemos orientar
    # o cidadão a ficar em casa se a GE pode ser dengue mal diferenciado ou outra causa grave.
    if doenca == "Gastroenterite Viral" and confianca >= 45:
        if dados.get("febre") and dados.get("dor_abdominal"):
            info_sindrome = {
                "sindrome": "Síndrome Diarreica com Alerta",
                "cor": "amarela",
                "conduta": (
                    "Hidrate-se bem (soro oral ou caseiro). Repouso e dieta leve. "
                    "ATENÇÃO: febre com dor abdominal pode ter causas mais sérias além de gastroenterite, "
                    "inclusive dengue (onde dor abdominal com febre é sinal de alarme). "
                    "Procure uma UBS HOJE se a febre persistir, a dor abdominal piorar "
                    "ou aparecer qualquer sangramento, manchas na pele ou piora do estado geral."
                ),
            }

    # Urgências absolutas → sempre alerta direto, independente da síndrome
    alerta_urgente = None
    if urgencias:
        alerta_urgente = {
            "titulo": urgencias[0]["titulo"],
            "acao": "Dirija-se imediatamente ao pronto-socorro mais próximo.",
            "cor": "vermelha",
        }

    return {
        # O que o cidadão vê
        "sindrome": info_sindrome["sindrome"],
        "cor_alerta": info_sindrome["cor"],
        "conduta": info_sindrome["conduta"],
        "alerta_urgente": alerta_urgente,
        # Metadados seguros para mostrar
        "sintomas_reportados": resultado["sintomas_count"],
        "acompanhamento_recomendado": confianca >= 45 and doenca not in DOENCAS_NOMINAVEIS,
        # Para gestores/saúde (não exibir ao cidadão diretamente)
        "_gestor": {
            "doenca_provavel": doenca,
            "confianca": confianca,
            "estado": estado or dados.get("estado", ""),
            "red_flags": resultado["red_flags"],
            "ranking_top3": resultado["ranking"][:3],
        },
        "safeguard": (
            "Este resultado é apenas orientativo. "
            "Não substitui avaliação médica presencial."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# ANÁLISE EPIDEMIOLÓGICA AGREGADA (para dashboards e command_ai)
# ──────────────────────────────────────────────────────────────────────────────

def analisar_populacao(registros_qs, setor: str = "governo") -> dict:
    """
    Analisa um QuerySet de RegistroSintoma e retorna perfil epidemiológico
    com distribuição de doenças, red flags, e tendência.

    Retorna payload formatado para uso nos dashboards de todos os setores.
    """
    total = registros_qs.count()
    if total == 0:
        return {
            "total": 0,
            "doenca_dominante": "Sem dados",
            "grupo_dominante": "Sem dados",
            "distribuicao_doencas": [],
            "red_flags_populacao": [],
            "urgencias_absolutas": [],
            "pressao_nivel": "controlada",
            "pressao_label": "Sem sinais",
            "contexto_setor": CONTEXTO_SETOR.get(setor, CONTEXTO_SETOR["governo"]),
        }

    mes_atual = date.today().month
    contagem_doencas: dict[str, int] = {}
    contagem_red_flags: dict[str, int] = {}
    contagem_urgencias: dict[str, int] = {}

    for reg in registros_qs.iterator():
        dados = sintomas_do_registro(reg)
        resultado = classificar(dados, setor)
        doenca = resultado["primario"]
        if doenca != "Inconclusivo":
            contagem_doencas[doenca] = contagem_doencas.get(doenca, 0) + 1
        for rf in resultado["red_flags"]:
            contagem_red_flags[rf] = contagem_red_flags.get(rf, 0) + 1
        for urg in resultado["urgencia_absoluta"]:
            key = urg["campo"]
            contagem_urgencias[key] = contagem_urgencias.get(key, 0) + 1

    doenca_dominante = max(contagem_doencas, key=lambda x: contagem_doencas[x]) if contagem_doencas else "Indefinido"
    grupo_dominante = DOENCAS_BRASIL.get(doenca_dominante, {}).get("grupo", "Indefinido")

    distribuicao = sorted(
        [{"doenca": d, "casos": c, "pct": round(c/total*100, 1)} for d, c in contagem_doencas.items()],
        key=lambda x: -x["casos"]
    )[:8]

    red_flags_pop = sorted(
        [{"sintoma": s, "casos": c} for s, c in contagem_red_flags.items()],
        key=lambda x: -x["casos"]
    )

    urgencias_pop = sorted(
        [{"sintoma": s, "casos": c} for s, c in contagem_urgencias.items()],
        key=lambda x: -x["casos"]
    )

    # Nível de pressão
    casos_dominante = contagem_doencas.get(doenca_dominante, 0)
    pct_dominante = casos_dominante / total if total > 0 else 0
    if pct_dominante >= 0.6 or len(urgencias_pop) > 0:
        pressao_nivel = "alta"
        pressao_label = "Pressão alta — ação imediata"
    elif pct_dominante >= 0.35:
        pressao_nivel = "moderada"
        pressao_label = "Pressão moderada — monitoramento ativo"
    elif pct_dominante >= 0.15:
        pressao_nivel = "monitoramento"
        pressao_label = "Monitoramento ativo"
    else:
        pressao_nivel = "controlada"
        pressao_label = "Situação controlada"

    ctx_setor = CONTEXTO_SETOR.get(setor, CONTEXTO_SETOR["governo"]).copy()
    ctx_setor["relevante_para_setor"] = doenca_dominante in ctx_setor.get("prioridade", [])
    ctx_setor["requer_notificacao"] = doenca_dominante in ctx_setor.get("alerta_notificacao", [])

    return {
        "total": total,
        "doenca_dominante": doenca_dominante,
        "grupo_dominante": grupo_dominante,
        "cid10_dominante": DOENCAS_BRASIL.get(doenca_dominante, {}).get("cid10", ""),
        "distribuicao_doencas": distribuicao,
        "red_flags_populacao": red_flags_pop,
        "urgencias_absolutas": urgencias_pop,
        "pressao_nivel": pressao_nivel,
        "pressao_label": pressao_label,
        "contexto_setor": ctx_setor,
        "safeguard": "Análise agregada anônima. Não expõe dado individual.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# SISTEMA DE APRENDIZADO — calibração a partir de confirmações
# ──────────────────────────────────────────────────────────────────────────────

def calibrar_pesos_feedback(registros_confirmados_qs) -> dict:
    """
    Analisa registros que tiveram doenca_confirmada preenchida e compara
    com o que o classificador teria dito. Retorna métricas de acurácia
    e sugere onde a IA precisa aprender mais.

    Não modifica os pesos automaticamente (requer revisão humana).
    Gera um relatório de calibração para o operador.
    """
    total = registros_confirmados_qs.filter(doenca_confirmada__isnull=False).exclude(doenca_confirmada="").count()
    if total == 0:
        return {"status": "sem_dados", "total_confirmados": 0, "acuracia": None}

    acertos = 0
    erros: dict[str, dict] = {}

    for reg in registros_confirmados_qs.filter(doenca_confirmada__isnull=False).exclude(doenca_confirmada="").iterator():
        dados = sintomas_do_registro(reg)
        resultado = classificar(dados)
        previsto = resultado["primario"]
        confirmado = reg.doenca_confirmada

        if previsto == confirmado:
            acertos += 1
        else:
            chave = f"{previsto}→{confirmado}"
            erros[chave] = erros.get(chave, 0) + 1

    acuracia = round(acertos / total * 100, 1)
    top_erros = sorted([{"confusao": k, "casos": v} for k, v in erros.items()], key=lambda x: -x["casos"])[:5]

    return {
        "status": "calibrado",
        "total_confirmados": total,
        "acertos": acertos,
        "acuracia": acuracia,
        "top_confusoes": top_erros,
        "instrucao": (
            "Os pares de confusão indicam onde os pesos de sintomas precisam de ajuste. "
            "Revisar com epidemiologista antes de alterar o motor."
        ),
    }
