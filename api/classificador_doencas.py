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
            "exantema_vesicular":    -0.75,  # dengue é macular — bolhas aponta CONTRA
            "hemoptise":             -0.45,  # incomum no dengue
            "perda_peso":            -0.55,  # doença aguda, não causa emagrecimento
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
        "cid10": "U06.9",  # OMS/CID-10 pós-2016 (A92.8 era o código legado pré-Zika-específico)
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
            "exantema_vesicular":    -0.65,  # Zika é macular, não vesicular
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
            "exantema_vesicular":    -0.55,  # chikungunya é macular, não vesicular
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
            "hemoptise":              0.65,  # síndrome cardiopulmonar por hantavírus
            "exantema_vesicular":    -0.65,  # hantavirose não tem rash vesicular
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
            "exantema_vesicular":    -0.65,  # sarampo é maculopapular confluente, não vesicular
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

    # ── RESPIRATÓRIA CRÔNICA ─────────────────────────────────────────────────
    "Tuberculose": {
        "grupo": "Respiratória crônica / ILTB",
        "vetor": "Mycobacterium tuberculosis (aerossol)",
        "cid10": "A15",
        "descricao": "Tosse persistente (>3 semanas), sudorese noturna, febre baixa vespertina, fadiga progressiva; principal causa de morte infecciosa no Brasil",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "tosse":                  1.00,  # tosse crônica produtiva — obrigatória
            "sudorese":               0.85,  # suor noturno — muito característico
            "cansaco":                0.88,  # fadiga progressiva intensa
            "febre":                  0.65,  # febre BAIXA vespertina (<38°C típica)
            "falta_ar":               0.55,  # doença avançada ou TB miliar
            "dor_corpo":              0.50,  # mialgia leve/moderada
            "dor_cabeca":             0.30,
            "vomito_nausea":          0.20,  # TB abdominal ou efeito de medicação
            "perda_olfato_paladar":  -0.70,  # COVID, não TB
            "exantema":              -0.65,
            "dor_articular":         -0.35,
            "conjuntivite":          -0.55,
            "rigidez_nuca":          -0.25,
            "manchas_hemorragicas":  -0.75,
            "coriza":                -0.40,  # coriza diferencia de resfriado
            "dor_garganta":          -0.30,
            "calafrios":             -0.15,
            "diarreia":              -0.30,
            "hemoptise":              0.75,  # tosse com sangue — TB hemoptóica
            "exantema_vesicular":    -0.70,  # varicela, não TB
            "perda_peso":             0.82,  # emagrecimento é sintoma cardinal da TB
            "_intensidade_febre_baixa":  0.40,  # febre baixa é típica da TB
            "_intensidade_febre_alta":  -0.25,  # febre alta aponta contra TB pulmonar
        },
        "red_flags": ["falta_ar"],
        "diferencial_vs": {
            "Gripe (Influenza)": "gripe tem início abrupto e duração <2 semanas; TB evolui lentamente por semanas a meses",
            "COVID-19": "COVID tem perda de olfato/paladar; TB não tem",
            "Bronquite / DPOC Agudização": "TB tem sudorese noturna intensa; bronquite não",
        },
    },

    # ── EXANTEMÁTICA VIRAL ───────────────────────────────────────────────────
    "Varicela": {
        "grupo": "Viral exantemática",
        "vetor": "Varicella-zoster (aerossol + contato direto)",
        "cid10": "B01",
        "descricao": "Exantema vesicular pruriginoso em múltiplos estágios simultâneos (mácula→pápula→vesícula→crosta), febre baixa a moderada; altamente contagiosa",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "exantema":               1.00,  # vesículas pruriginosas — patognomônico
            "febre":                  0.72,  # febre moderada
            "cansaco":                0.68,
            "dor_corpo":              0.50,
            "dor_cabeca":             0.45,
            "calafrios":              0.35,
            "dor_garganta":           0.25,
            "tosse":                 -0.40,  # varicela tem pouca tosse — vs sarampo
            "coriza":                -0.50,
            "falta_ar":              -0.30,
            "perda_olfato_paladar":  -0.65,
            "ictericia":             -0.65,
            "manchas_hemorragicas":  -0.10,
            "rigidez_nuca":          -0.55,
            "dor_articular":         -0.30,
            "diarreia":              -0.35,
            "exantema_vesicular":     1.00,  # PATOGNOMÔNICO — vesículas com líquido em múltiplos estágios
            "hemoptise":             -0.85,  # varicela não causa tosse com sangue
            "_intensidade_febre_baixa":  0.25,
            "_intensidade_febre_alta":  -0.15,
        },
        "red_flags": ["falta_ar", "rigidez_nuca"],
        "diferencial_vs": {
            "Dengue": "varicela tem exantema vesicular pruriginoso; dengue tem exantema macular + dor intensa",
            "Sarampo": "sarampo tem tosse + coriza intensas e manchas de Koplik; varicela não",
            "Zika": "Zika tem conjuntivite e exantema macular; varicela tem vesículas em múltiplos estágios",
            "Mpox": "mpox tem lesões mais dolorosas que pruriginosas; começa no rosto/palmas; varicela tem estágios múltiplos simultâneos",
        },
    },

    "Mpox": {
        "grupo": "Viral exantemática / Poxvírus",
        "vetor": "Orthopoxvirus (contato direto pele-pele, secreções, fômites, gotículas)",
        "cid10": "B04",
        "descricao": "Febre ANTES do exantema + lesões vesiculopustulosas mais DOLOROSAS que pruriginosas; início no rosto com disseminação centrífuga; palmas e plantas frequentemente afetadas; linfonodomegalia característica",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "exantema_vesicular":     0.95,  # vesiculopustuloso — quase obrigatório
            "febre":                  0.92,  # precede o exantema (diferencial chave vs varicela)
            "dor_corpo":              0.88,  # mialgia intensa — mais que varicela
            "dor_cabeca":             0.80,
            "calafrios":              0.75,
            "cansaco":                0.72,
            "dor_articular":          0.55,  # artralgia presente, moderada
            "exantema":               0.80,  # exantema generalizado
            "vomito_nausea":          0.45,
            "dor_abdominal":          0.40,
            "tosse":                 -0.30,  # tosse incomum no mpox
            "coriza":                -0.45,
            "perda_olfato_paladar":  -0.70,
            "rigidez_nuca":          -0.50,
            "manchas_hemorragicas":  -0.55,
            "diarreia":              -0.30,
            "_intensidade_febre_alta":  0.30,  # febre alta antes do rash é característica
        },
        "red_flags": ["falta_ar", "exantema_vesicular"],
        "diferencial_vs": {
            "Varicela": "varicela é muito pruriginosa com estágios simultâneos; mpox é mais dolorosa, começa no rosto, afeta palmas/plantas",
            "Dengue": "dengue não tem vesículas; mpox tem lesões em estágio único disseminadas",
            "Sarampo": "sarampo é maculopapular sem vesículas; mpox tem pústulas dolorosas",
        },
    },

    # ── RIQUETSIOSE ──────────────────────────────────────────────────────────
    "Febre Maculosa": {
        "grupo": "Riquetsiose — URGÊNCIA",
        "vetor": "Amblyomma sculptum (carrapato-estrela)",
        "cid10": "A77.0",
        "descricao": "Febre alta abrupta + exantema maculopetequial iniciando em extremidades + mialgia intensa; mortalidade 20-40% sem tratamento nas primeiras 48h",
        "sazonalidade": [7, 8, 9, 10, 11, 12, 1, 2, 3, 4],  # primavera/verão SP/MG/RJ
        "sintomas": {
            "febre":                  1.00,  # febre alta abrupta — obrigatória
            "dor_cabeca":             0.95,  # cefaleia intensa
            "dor_corpo":              0.92,  # mialgia intensa generalizada
            "exantema":               0.88,  # máculas→petéquias — começa em pulsos/tornozelos
            "calafrios":              0.80,
            "manchas_hemorragicas":   0.72,  # petéquias/púrpura — gravidade
            "vomito_nausea":          0.65,
            "cansaco":                0.75,
            "sudorese":               0.55,
            "falta_ar":               0.30,  # forma grave
            "diarreia":               0.25,
            "tosse":                 -0.30,
            "coriza":                -0.55,
            "perda_olfato_paladar":  -0.70,
            "rigidez_nuca":          -0.20,
            "dor_articular":         -0.15,
            "hemoptise":              0.35,  # FM grave pode ter envolvimento pulmonar
            "exantema_vesicular":    -0.65,  # FM é macular→petequial, não vesicular
            "_intensidade_febre_alta": 0.35,  # febre alta abrupta é a marca da FM
        },
        "red_flags": ["febre", "exantema", "manchas_hemorragicas"],
        "diferencial_vs": {
            "Dengue": "FM tem exantema iniciando nas extremidades; zona rural e carrapato no contexto",
            "Meningite": "FM tem exantema antes da rigidez; meningite tem rigidez nuca proeminente",
            "Leptospirose": "FM tem exantema típico petequial; lepto tem exposição à água/lama",
        },
    },

    # ── BACTERIANA RESPIRATÓRIA ──────────────────────────────────────────────
    "Coqueluche": {
        "grupo": "Bacteriana respiratória",
        "vetor": "Bordetella pertussis (aerossol)",
        "cid10": "A37",
        "descricao": "Tosse paroxística em accessos com 'guincho' inspiratório, vômito pós-tosse; evolução catarral→paroxística→convalescença; grave em lactentes",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "tosse":                  1.00,  # tosse paroxística — obrigatória
            "vomito_nausea":          0.85,  # vômito pós-acesso de tosse — muito característico
            "falta_ar":               0.75,  # engasgos, cianose perioral pós-acesso
            "cansaco":                0.65,
            "coriza":                 0.55,  # fase catarral inicial
            "dor_cabeca":             0.30,
            "febre":                  0.30,  # baixa ou ausente
            "dor_corpo":              0.20,
            "exantema":              -0.72,
            "dor_articular":         -0.65,
            "ictericia":             -0.85,
            "rigidez_nuca":          -0.65,
            "manchas_hemorragicas":  -0.45,
            "dor_garganta":          -0.30,
            "sudorese":              -0.20,
            "perda_olfato_paladar":  -0.65,
            "_intensidade_febre_baixa":  0.20,
            "_intensidade_febre_alta":  -0.30,
        },
        "red_flags": ["falta_ar"],
        "diferencial_vs": {
            "Gripe (Influenza)": "coqueluche tem tosse paroxística com vômito; gripe tem febre alta e mialgia intensa",
            "COVID-19": "coqueluche não tem perda de olfato; tosse em accessos com vômito é patognomônica",
            "Resfriado Viral": "resfriado tem coriza dominante sem acessos de tosse; coqueluche tem acessos prolongados",
        },
    },

    # ── BACTERIANA SISTÊMICA / ENTÉRICA ─────────────────────────────────────
    "Febre Tifoide": {
        "grupo": "Bacteriana entérica",
        "vetor": "Salmonella Typhi (fecal-oral, água/alimento contaminado)",
        "cid10": "A01.0",
        "descricao": "Febre em platô progressiva (>39°C), dor abdominal difusa, cefaleia intensa; risco de perfuração intestinal; associada a saneamento básico precário",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "febre":                  1.00,  # febre em platô crescente — obrigatória
            "dor_abdominal":          0.88,
            "cansaco":                0.85,
            "dor_cabeca":             0.80,
            "vomito_nausea":          0.72,
            "diarreia":               0.65,  # pode alternar com constipação inicial
            "exantema":               0.50,  # manchas rosadas (rose spots) — 30-50% dos casos
            "dor_corpo":              0.65,
            "sudorese":               0.55,
            "calafrios":              0.60,
            "tosse":                 -0.50,
            "coriza":                -0.60,
            "perda_olfato_paladar":  -0.70,
            "rigidez_nuca":          -0.45,
            "manchas_hemorragicas":  -0.20,
            "conjuntivite":          -0.45,
            "dor_garganta":          -0.45,
            "_intensidade_febre_alta": 0.30,  # febre alta em platô é típica da tifoide
        },
        "red_flags": ["dor_abdominal", "manchas_hemorragicas"],
        "diferencial_vs": {
            "Dengue": "tifoide tem dor abdominal intensa e constante; dengue tem início mais abrupto e mialgia dominante",
            "Gastroenterite Viral": "GE é autolimitada em 72h; tifoide piora progressivamente",
            "Leptospirose": "lepto tem histórico de exposição à água/roedores; tifoide tem contexto de saneamento precário",
        },
    },

    # ── PARASITÁRIA / HELMINTÍASE ────────────────────────────────────────────
    "Esquistossomose": {
        "grupo": "Parasitária / Helmintíase",
        "vetor": "Schistosoma mansoni (água doce com caramujos Biomphalaria)",
        "cid10": "B65.1",
        "descricao": "Diarreia com sangue/muco, dor abdominal, hepatoesplenomegalia, anemia; endêmica no Nordeste e Minas Gerais; exposição a água doce (rios, açudes, irrigação)",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "diarreia":               0.90,  # diarreia mucossanguinolenta
            "dor_abdominal":          0.85,  # cólicas, hepatoesplenomegalia
            "cansaco":                0.82,  # anemia crônica
            "febre":                  0.62,  # fase aguda de Katayama
            "vomito_nausea":          0.60,
            "ictericia":              0.42,  # fase crônica avançada — fibrose hepática
            "dor_corpo":              0.42,
            "exantema":               0.35,  # dermatite cercarial inicial
            "calafrios":              0.45,  # fase aguda
            "dor_cabeca":             0.30,
            "tosse":                 -0.35,
            "coriza":                -0.55,
            "perda_olfato_paladar":  -0.70,
            "rigidez_nuca":          -0.65,
            "manchas_hemorragicas":  -0.25,
            "dor_articular":         -0.30,
            "falta_ar":              -0.20,
        },
        "red_flags": ["ictericia", "dor_abdominal"],
        "diferencial_vs": {
            "Hepatite A/B": "esquistossomose tem diarreia e histórico de contato com água doce; hepatite tem icterícia sem diarreia típica",
            "Gastroenterite Viral": "GE é autolimitada; esquistossomose persiste e tem contexto hídrico",
            "Febre Tifoide": "tifoide não tem hepatoesplenomegalia precoce; contexto hídrico diferencia",
        },
    },

    # ── DOENÇAS TROPICAIS NEGLIGENCIADAS — Phase 2 ────────────────────────────
    "Doença de Chagas": {
        "grupo": "Parasitária / Tripanossomíase",
        "vetor": "Triatoma infestans (barbeiro) — fezes contaminadas, transfusão, vertical",
        "cid10": "B57",
        "descricao": "Fase aguda: febre, mal-estar, sinal de Romaña (edema palpebral unilateral); fase crônica: cardiomiopatia, megaviscerais, emagrecimento; endêmica no Brasil Central/Nordeste",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "febre":                  0.75,  # fase aguda
            "cansaco":                0.88,  # fase aguda e crônica
            "dor_corpo":              0.65,
            "vomito_nausea":          0.55,  # fase aguda
            "dor_abdominal":          0.52,  # megacólon/megaesôfago
            "perda_peso":             0.78,  # emagrecimento — fase crônica cardinal
            "exantema":               0.42,  # lesão eritematosa no sítio de inoculação
            "diarreia":               0.30,  # megacólon
            "calafrios":              0.45,
            "sudorese":               0.40,
            "ictericia":             -0.55,
            "tosse":                 -0.45,
            "coriza":                -0.60,
            "rigidez_nuca":          -0.80,
            "manchas_hemorragicas":  -0.60,
            "perda_olfato_paladar":  -0.70,
            "exantema_vesicular":    -0.75,  # Chagas não causa vesículas
            "hemoptise":             -0.65,
            "mancha_anestesia":      -0.85,  # hanseníase, não Chagas
        },
        "red_flags": ["febre", "cansaco", "perda_peso"],
        "diferencial_vs": {
            "Tuberculose": "TB tem tosse crônica dominante; Chagas tem exposição ao barbeiro e sem tosse dominante",
            "Leishmaniose Visceral": "calazar tem esplenomegalia e febre mais prolongada; Chagas tem contato com triatomíneo",
        },
    },

    "Hanseníase": {
        "grupo": "Infectoparasitária / Micobacteriana",
        "vetor": "Mycobacterium leprae — aerossol (convívio domiciliar prolongado)",
        "cid10": "A30",
        "descricao": "Manchas hipocromáticas/eritematosas com PERDA DE SENSIBILIDADE; espessamento de nervos periféricos; evolução crônica e insidiosa; endêmica no Mato Grosso, Pará, Maranhão e Tocantins",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "mancha_anestesia":       1.00,  # PATOGNOMÔNICO — mancha insensível ao toque
            "exantema":               0.65,  # mácula/pápula eritematosa ou hipocromática
            "cansaco":                0.45,
            "dor_corpo":              0.42,  # neurite periférica
            "febre":                  0.20,  # reação hansênica tipo I/II
            "perda_peso":             0.35,  # formas avançadas
            "tosse":                 -0.65,
            "diarreia":              -0.70,
            "vomito_nausea":         -0.60,
            "dor_cabeca":            -0.40,
            "coriza":                -0.70,
            "manchas_hemorragicas":  -0.80,
            "rigidez_nuca":          -0.80,
            "perda_olfato_paladar":  -0.75,
            "hemoptise":             -0.80,
            "exantema_vesicular":    -0.75,  # hanseníase não tem vesículas
            "ulcera_cutanea":         0.40,  # reação tipo II (eritema nodoso) pode ulcerar
        },
        "red_flags": ["mancha_anestesia"],
        "diferencial_vs": {
            "Varicela": "varicela tem vesículas e febre aguda; hanseníase tem manchas insensíveis sem vesículas",
            "Febre Maculosa": "FM tem febre alta abrupta com manchas hemorrágicas; hanseníase é crônica e insidiosa",
        },
    },

    "Leishmaniose Visceral": {
        "grupo": "Parasitária / Leishmaniose",
        "vetor": "Lutzomyia longipalpis (mosquito palha) — reservatório canino",
        "cid10": "B55.0",
        "descricao": "Calazar: febre prolongada irregular, perda de peso acentuada, hepatoesplenomegalia, anemia grave; endêmica no Nordeste, Centro-Oeste e periurbano; alta letalidade sem tratamento",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "febre":                  0.90,  # prolongada (semanas a meses), irregular
            "perda_peso":             0.95,  # acentuada — sinal cardinal (caquexia)
            "cansaco":                0.88,
            "dor_abdominal":          0.72,  # esplenomegalia/hepatomegalia
            "vomito_nausea":          0.55,
            "ictericia":              0.50,  # hepatite/colestase
            "dor_corpo":              0.55,
            "calafrios":              0.55,
            "diarreia":               0.40,
            "exantema":               0.20,
            "tosse":                 -0.45,
            "coriza":                -0.65,
            "rigidez_nuca":          -0.70,
            "manchas_hemorragicas":  -0.50,
            "perda_olfato_paladar":  -0.80,
            "hemoptise":             -0.60,
            "exantema_vesicular":    -0.75,
            "mancha_anestesia":      -0.85,  # hanseníase, não calazar
        },
        "red_flags": ["febre", "perda_peso", "ictericia"],
        "diferencial_vs": {
            "Doença de Chagas": "calazar tem esplenomegalia e febre mais prolongada; Chagas tem contato com barbeiro",
            "Tuberculose": "TB tem tosse crônica e lesão pulmonar; calazar tem esplenomegalia e maior perda de peso",
            "Hepatite A/B": "hepatite tem icterícia precoce proeminente sem emagrecimento maciço",
        },
    },

    "Leishmaniose Tegumentar": {
        "grupo": "Parasitária / Leishmaniose",
        "vetor": "Lutzomyia spp. (mosquito palha) — reservatório silvestre",
        "cid10": "B55.1",
        "descricao": "Úlcera indolor de bordas elevadas e endurecidas em áreas expostas (úlcera de Bauru); pode comprometer mucosas (nariz, boca); transmitida em áreas florestais e periurbanas",
        "sazonalidade": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        "sintomas": {
            "ulcera_cutanea":         1.00,  # PATOGNOMÔNICO — úlcera indolor bordo elevado
            "exantema":               0.55,  # lesão papular inicial antes da úlcera
            "febre":                  0.35,  # febre baixa ocasional
            "cansaco":                0.30,
            "perda_peso":             0.30,  # formas mucosas extensas
            "tosse":                 -0.75,
            "diarreia":              -0.75,
            "vomito_nausea":         -0.60,
            "coriza":                -0.70,
            "rigidez_nuca":          -0.80,
            "manchas_hemorragicas":  -0.80,
            "hemoptise":             -0.75,
            "exantema_vesicular":    -0.70,  # úlcera ≠ vesícula
            "mancha_anestesia":      -0.70,  # hanseníase, não LT
        },
        "red_flags": ["ulcera_cutanea"],
        "diferencial_vs": {
            "Hanseníase": "hanseníase tem mancha insensível sem úlcera típica; LT tem úlcera indolor de bordas elevadas",
            "Febre Maculosa": "FM tem febre alta abrupta com petéquias; LT é crônica e localizada",
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
    # Novas doenças expandidas
    "Tuberculose":             0.08,  # 70 casos/100k no Brasil — alto no contexto global
    "Varicela":                0.12,  # endêmica no Brasil, pré-vacina universal
    "Febre Maculosa":          0.01,  # rara mas alta mortalidade; eleva com exposição
    "Coqueluche":              0.04,  # reemergente em adultos com waning immunity
    "Febre Tifoide":           0.03,  # incomum no Sudeste; maior no Norte/Nordeste
    "Esquistossomose":         0.05,  # endêmica Nordeste/MG — prior baixo no Sul/SP
    # Mpox — baixo prior nacional mas surtos urbanos são possíveis
    "Mpox":                    0.01,  # prior muito baixo; eleva com contato confirmado
    # Phase 2 — doenças tropicais negligenciadas
    "Doença de Chagas":        0.04,  # 1-2 milhões de infectados no Brasil; muitos sem diagnóstico
    "Hanseníase":              0.03,  # Brasil é 2º país em casos; endêmica no Centro-Norte
    "Leishmaniose Visceral":   0.02,  # calazar — fatal sem tratamento; reservatório canino
    "Leishmaniose Tegumentar": 0.02,  # úlcera de Bauru — zonas florestais e periurbanas
}

# UFs com priors específicos (apenas onde diferem significativamente do padrão)
PRIOR_GEOGRAFICO: dict[str, dict[str, float]] = {

    # ── Amazônia Legal — alto risco malária e febre amarela ──────────────────
    "AM": {**_PRIOR_DEFAULT, "Malaria": 0.55, "Febre Amarela": 0.12, "Dengue": 0.60, "Leptospirose": 0.12,
           "Leishmaniose Tegumentar": 0.06, "Leishmaniose Visceral": 0.04, "Hanseníase": 0.08},
    "PA": {**_PRIOR_DEFAULT, "Malaria": 0.45, "Febre Amarela": 0.10, "Dengue": 0.55, "Leptospirose": 0.10,
           "Leishmaniose Tegumentar": 0.05, "Leishmaniose Visceral": 0.05, "Hanseníase": 0.10},
    "AC": {**_PRIOR_DEFAULT, "Malaria": 0.50, "Febre Amarela": 0.12, "Dengue": 0.50,
           "Leishmaniose Tegumentar": 0.05},
    "RO": {**_PRIOR_DEFAULT, "Malaria": 0.40, "Febre Amarela": 0.10, "Dengue": 0.55,
           "Leishmaniose Tegumentar": 0.04},
    "RR": {**_PRIOR_DEFAULT, "Malaria": 0.45, "Febre Amarela": 0.10, "Dengue": 0.50},
    "AP": {**_PRIOR_DEFAULT, "Malaria": 0.35, "Febre Amarela": 0.08, "Dengue": 0.55},
    "TO": {**_PRIOR_DEFAULT, "Malaria": 0.15, "Febre Amarela": 0.08, "Dengue": 0.65,
           "Hanseníase": 0.10, "Doença de Chagas": 0.06, "Leishmaniose Visceral": 0.05},

    # ── Centro-Oeste — risco moderado febre amarela (área de transição) ──────
    "MT": {**_PRIOR_DEFAULT, "Malaria": 0.12, "Febre Amarela": 0.07, "Dengue": 0.70,
           "Hanseníase": 0.12, "Doença de Chagas": 0.07},
    "GO": {**_PRIOR_DEFAULT, "Febre Amarela": 0.05, "Dengue": 0.72, "Chikungunya": 0.25,
           "Doença de Chagas": 0.06, "Leishmaniose Visceral": 0.04},
    "MS": {**_PRIOR_DEFAULT, "Febre Amarela": 0.04, "Dengue": 0.65, "Leptospirose": 0.12,
           "Leishmaniose Visceral": 0.04},
    "DF": {**_PRIOR_DEFAULT, "Febre Amarela": 0.03, "Dengue": 0.68, "Chikungunya": 0.22},

    # ── Sudeste — urbano, dengue/chikungunya dominam; febre amarela mínima ───
    # Febre Maculosa SP/MG/RJ: maior incidência nacional (Ribeirão Preto, Campinas, Vale do Paraíba, Mata Atlântica)
    # Tuberculose SP/RJ: alta densidade urbana, populações vulneráveis, ILPI
    # Esquistossomose MG/ES: endêmica no Vale do Rio Doce e Zona da Mata
    "SP": {**_PRIOR_DEFAULT, "Dengue": 0.75, "Chikungunya": 0.30, "Febre Amarela": 0.015,
           "COVID-19": 0.55, "Gripe (Influenza)": 0.60,
           "Tuberculose": 0.14, "Febre Maculosa": 0.04, "Mpox": 0.02},
    "RJ": {**_PRIOR_DEFAULT, "Dengue": 0.80, "Chikungunya": 0.35, "Zika": 0.18,
           "Febre Amarela": 0.005, "Malaria": 0.001,
           "COVID-19": 0.55, "Gripe (Influenza)": 0.58,
           "Tuberculose": 0.16, "Febre Maculosa": 0.03, "Mpox": 0.02},
    "MG": {**_PRIOR_DEFAULT, "Dengue": 0.72, "Chikungunya": 0.28, "Febre Amarela": 0.04,
           "Leptospirose": 0.10,
           "Febre Maculosa": 0.05, "Esquistossomose": 0.15, "Tuberculose": 0.10,
           "Doença de Chagas": 0.06, "Leishmaniose Tegumentar": 0.04, "Leishmaniose Visceral": 0.03},
    "ES": {**_PRIOR_DEFAULT, "Dengue": 0.75, "Chikungunya": 0.30, "Febre Amarela": 0.02,
           "Leptospirose": 0.10,
           "Febre Maculosa": 0.03, "Esquistossomose": 0.12},

    # ── Nordeste — dengue altíssima, chikungunya elevada ────────────────────
    # Esquistossomose PE/AL/BA/SE: faixa endêmica histórica da esquistossomose
    # Febre Tifoide BA/MA: saneamento precário em áreas periurbanas
    # Tuberculose CE/PE: alta prevalência em população de rua, presídios
    "BA": {**_PRIOR_DEFAULT, "Dengue": 0.78, "Chikungunya": 0.40, "Febre Amarela": 0.03,
           "Esquistossomose": 0.18, "Febre Tifoide": 0.06, "Tuberculose": 0.10,
           "Doença de Chagas": 0.06, "Leishmaniose Visceral": 0.07, "Leishmaniose Tegumentar": 0.05, "Hanseníase": 0.05},
    "PE": {**_PRIOR_DEFAULT, "Dengue": 0.80, "Chikungunya": 0.45, "Zika": 0.25,
           "Febre Amarela": 0.01,
           "Esquistossomose": 0.20, "Febre Tifoide": 0.05, "Tuberculose": 0.12,
           "Leishmaniose Visceral": 0.05, "Doença de Chagas": 0.05},
    "CE": {**_PRIOR_DEFAULT, "Dengue": 0.78, "Chikungunya": 0.42, "Febre Amarela": 0.01,
           "Tuberculose": 0.12, "Febre Tifoide": 0.05,
           "Leishmaniose Visceral": 0.06, "Doença de Chagas": 0.05},
    "MA": {**_PRIOR_DEFAULT, "Dengue": 0.70, "Chikungunya": 0.35, "Febre Amarela": 0.03,
           "Malaria": 0.08, "Esquistossomose": 0.14, "Febre Tifoide": 0.06,
           "Hanseníase": 0.10, "Leishmaniose Visceral": 0.06, "Doença de Chagas": 0.05},
    "PI": {**_PRIOR_DEFAULT, "Dengue": 0.72, "Chikungunya": 0.35, "Febre Amarela": 0.03,
           "Esquistossomose": 0.10, "Febre Tifoide": 0.05,
           "Doença de Chagas": 0.07, "Leishmaniose Visceral": 0.06, "Hanseníase": 0.06},
    "RN": {**_PRIOR_DEFAULT, "Dengue": 0.75, "Chikungunya": 0.38, "Febre Amarela": 0.01,
           "Esquistossomose": 0.12},
    "PB": {**_PRIOR_DEFAULT, "Dengue": 0.73, "Chikungunya": 0.37, "Febre Amarela": 0.01,
           "Esquistossomose": 0.14},
    "AL": {**_PRIOR_DEFAULT, "Dengue": 0.72, "Chikungunya": 0.36, "Febre Amarela": 0.01,
           "Esquistossomose": 0.20},
    "SE": {**_PRIOR_DEFAULT, "Dengue": 0.70, "Chikungunya": 0.35, "Febre Amarela": 0.01,
           "Esquistossomose": 0.16},

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
    # Aliases: DISEASE_WEIGHTS usa nomes curtos; PRIOR_GEOGRAFICO usa nomes completos
    _alias = {
        "Gripe": "Gripe (Influenza)",
        "Bronquite": "Bronquite / DPOC Agudização",
    }
    doenca = _alias.get(doenca, doenca)
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
    "Malaria":        ["calafrios", "viagem_area_endemica"],         # calafrios cíclicos OU viagem endêmica
    "Meningite":      ["rigidez_nuca"],                              # sem rigidez nuca, não é meningite
    "Hantavirose":    ["falta_ar"],                                  # síndrome cardiopulmonar obrigatória
    "Sarampo":        ["exantema"],                                  # sem exantema, não é sarampo
    "Leptospirose":   ["ictericia", "dor_corpo", "calafrios"],       # precisa ≥1 dos 3
    "Hepatite A/B":   ["ictericia"],                                 # icterícia é essencial
    # Novas doenças expandidas
    "Bronquite / DPOC Agudização": ["tosse"],  # nome completo (bate com DOENCAS_BRASIL); sem tosse não é bronquite
    "Tuberculose":    ["tosse"],           # TB pulmonar sem tosse é rara no cidadão sintomático
    "Varicela":       ["exantema"],        # sem exantema, não é varicela
    "Mpox":           ["exantema_vesicular", "febre"],  # tríade: vesículas + febre + contato
    "Febre Maculosa": ["febre", "exantema"],  # tríade: febre+exantema+mialgia — precisa de ≥1
    "Coqueluche":     ["tosse"],           # tosse paroxística é obrigatória
    "Febre Tifoide":  ["febre"],           # febre em platô é essencial
    "Esquistossomose": ["diarreia", "dor_abdominal", "exposicao_agua_enchente"],  # ≥1 dos 3
    # Phase 2 — doenças tropicais negligenciadas
    "Doença de Chagas":        ["perda_peso", "exposicao_triatomideo"],   # ≥1 dos 2 obrigatório
    "Hanseníase":              ["mancha_anestesia"],                       # patognomônico obrigatório
    "Leishmaniose Visceral":   ["perda_peso", "febre"],                   # ambos (febre prolongada + emagrecimento)
    "Leishmaniose Tegumentar": ["ulcera_cutanea"],                        # patognomônico obrigatório
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
    "Tuberculose":          {"sindrome": "Síndrome Respiratória Crônica",   "cor": "laranja", "conduta": "Procure a UBS. Tosse por mais de 3 semanas com esses sintomas precisa de raio-X de tórax e exame de escarro."},
    "Varicela":             {"sindrome": "Síndrome Exantemática Viral",     "cor": "amarela", "conduta": "Isolamento domiciliar por 7 dias ou até as lesões secarem. Confirme na UBS. Não coçar — risco de infecção secundária."},
    "Mpox":                 {"sindrome": "Síndrome Exantemática Pustulosa", "cor": "laranja", "conduta": "Procure a UBS. Evite contato pele-pele com outras pessoas até avaliação médica. Mpox é notificação compulsória."},
    "Febre Maculosa":       {"sindrome": "Síndrome Febril com Manchas",     "cor": "vermelha","conduta": "URGÊNCIA — procure pronto-socorro imediatamente. Informe sobre exposição a carrapatos, mato ou área rural."},
    "Coqueluche":           {"sindrome": "Síndrome de Tosse Persistente",   "cor": "laranja", "conduta": "Procure a UBS. Tosse intensa em accessos com engasgos ou vômito é notificação compulsória."},
    "Febre Tifoide":        {"sindrome": "Síndrome Febril Entérica",        "cor": "laranja", "conduta": "Procure a UBS. Febre alta persistente com dor abdominal precisa de avaliação e exames de sangue."},
    "Esquistossomose":      {"sindrome": "Síndrome Diarreica com Histórico Hídrico", "cor": "amarela", "conduta": "Procure a UBS. Informe sobre contato com água de rio, lagoa ou irrigação."},
    # Phase 2 — doenças tropicais negligenciadas
    "Doença de Chagas":        {"sindrome": "Síndrome Febril com Histórico de Exposição",  "cor": "laranja", "conduta": "Procure a UBS. Se você teve contato com inseto barbeiro ou áreas rurais, relate ao médico."},
    "Hanseníase":              {"sindrome": "Síndrome de Mancha Cutânea",                  "cor": "laranja", "conduta": "Procure a UBS. Mancha na pele sem sensibilidade ao toque precisa de avaliação médica — é tratável."},
    "Leishmaniose Visceral":   {"sindrome": "Síndrome Febril Crônica com Emagrecimento",  "cor": "laranja", "conduta": "Procure a UBS. Febre prolongada com perda de peso em área endêmica precisa de exames de sangue."},
    "Leishmaniose Tegumentar": {"sindrome": "Síndrome de Úlcera Cutânea",                 "cor": "laranja", "conduta": "Procure a UBS. Úlcera indolor que não cicatriza em área de pele exposta precisa de avaliação médica."},
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
        "prioridade": ["Meningite", "Febre Amarela", "Febre Maculosa", "Sarampo", "Hantavirose", "Leptospirose", "Tuberculose", "Coqueluche"],
        "foco": "vigilância sanitária, notificação compulsória, resposta pública",
        "alerta_notificacao": ["Meningite", "Febre Amarela", "Febre Maculosa", "Sarampo", "Hantavirose",
                               "Dengue", "Malaria", "Leptospirose", "Tuberculose", "Coqueluche",
                               "Febre Tifoide", "Esquistossomose",
                               "Doença de Chagas", "Hanseníase", "Leishmaniose Visceral", "Leishmaniose Tegumentar",
                               "Mpox"],
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
        "prioridade": ["Meningite", "Febre Maculosa", "Hantavirose", "Febre Amarela", "Dengue", "COVID-19", "Leptospirose", "Tuberculose",
                       "Leishmaniose Visceral", "Doença de Chagas"],
        "foco": "triagem, leitos, insumos críticos, escala de pronto atendimento",
        "alerta_notificacao": ["Meningite", "Febre Amarela", "Febre Maculosa", "Hantavirose", "Sarampo",
                               "Tuberculose", "Coqueluche",
                               "Hanseníase", "Doença de Chagas", "Leishmaniose Visceral", "Leishmaniose Tegumentar",
                               "Mpox"],
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
    # Phase 2 — doenças tropicais negligenciadas + respiratórias crônicas
    "hemoptise", "exantema_vesicular", "perda_peso", "ulcera_cutanea", "mancha_anestesia",
]

# Campos de anamnese epidemiológica — contexto clínico que refina o prior
CAMPOS_ANAMNESE = [
    "dias_sintomas", "inicio_abrupto", "viagem_area_endemica",
    "exposicao_agua_enchente", "contato_roedores", "contato_caso_confirmado",
    "vacinado_febre_amarela", "tem_comorbidade",
    # Phase 2
    "exposicao_carrapato", "exposicao_triatomideo",
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
            # exantema pruriginoso + conjuntivite não-purulenta = tríade clássica de Zika
            # Prior de 0.40 era insuficiente para vencer Dengue (prior 0.80 em RJ)
            zika_prior = 0.55  # elevado: exantema+conjuntivite juntos são patognomônicos de Zika
            if str(dados.get("intensidade_febre", "")).lower() == "baixa":
                zika_prior = 0.70  # tríade completa: febre baixa + exantema + conjuntivite
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

    # Artralgia intensa é praticamente patognomônica de Chikungunya.
    # Dengue causa mialgia/artralgia leve; incapacitante (intensidade='intensa') aponta Chikungunya.
    # Sem este override, Dengue (prior 0.80 RJ) sempre vence Chikungunya (prior 0.35) no Sudeste.
    if str(dados.get("intensidade_articular", "")).lower() == "intensa":
        if doenca == "Chikungunya":
            return max(prior, 0.65)
        if doenca == "Dengue":
            return min(prior, 0.25)  # dengue raramente causa artralgia incapacitante

    # Tríade clássica de Sarampo: exantema + tosse + coriza.
    # Prior 0.01 (doença rara pós-vacinação) tornaria o Sarampo invisível mesmo com triade perfeita.
    # Override defensivo para garantir alerta ao profissional de saúde.
    if dados.get("exantema") and dados.get("tosse") and dados.get("coriza"):
        if doenca == "Sarampo":
            sarampo_prior = 0.40
            if dados.get("conjuntivite"):
                sarampo_prior = 0.55  # tétrade: exantema+tosse+coriza+conjuntivite
            return max(prior, sarampo_prior)

    # Comorbidade + início gradual → padrão de exacerbação de DPOC/Bronquite crónica.
    # Prior base 0.20 perde para COVID (prior 0.55 RJ) mesmo em apresentação atípica de COVID.
    if dados.get("tem_comorbidade") and dados.get("inicio_abrupto") is False:
        if doenca == "Bronquite / DPOC Agudização":
            return max(prior, 0.65)

    # ── Tuberculose ──────────────────────────────────────────────────────────
    # Contato com caso confirmado + tosse → prior mínimo defensivo (TB é altamente contagiosa)
    if dados.get("contato_caso_confirmado") and dados.get("tosse"):
        if doenca == "Tuberculose":
            return max(prior, 0.35)
    # Comorbidade imunossupressora (HIV, DM, IRC) eleva risco de TB ativa
    if dados.get("tem_comorbidade") and dados.get("tosse"):
        if doenca == "Tuberculose":
            return max(prior, 0.20)

    # ── Varicela ─────────────────────────────────────────────────────────────
    # Contato com caso confirmado + exantema → combinação altamente sugestiva
    if dados.get("contato_caso_confirmado") and dados.get("exantema"):
        if doenca == "Varicela":
            # exantema + contato direto é o padrão de transmissão por excelência da varicela
            return max(prior, 0.70)
        if doenca == "Sarampo":
            # varicela é mais provável que sarampo (erradicado) quando há contato
            return min(prior, 0.10)
        # Gripe raramente cursa com exantema proeminente sem tosse/coriza
        if doenca in ("Gripe (Influenza)",) and not dados.get("tosse") and not dados.get("coriza"):
            return min(prior, 0.20)
    # Exantema sem coriza/tosse aponta contra Sarampo/Gripe, favorece Varicela
    if dados.get("exantema") and not dados.get("tosse") and not dados.get("coriza"):
        if doenca == "Varicela":
            return max(prior, 0.45)

    # ── Febre Maculosa ───────────────────────────────────────────────────────
    # viagem_area_endemica (zona rural, mato, fazenda) + febre + exantema → FM é urgência
    if dados.get("viagem_area_endemica") and dados.get("febre") and dados.get("exantema"):
        if doenca == "Febre Maculosa":
            return max(prior, 0.50)
    # Febre + manchas petequiais + mialgia intensa → FM antes de tudo
    if dados.get("febre") and dados.get("manchas_hemorragicas") and dados.get("exantema"):
        if doenca == "Febre Maculosa":
            # petéquias + exantema + febre: Febre Maculosa é mais provável que dengue hemorrágico
            return max(prior, 0.55)

    # ── Coqueluche ───────────────────────────────────────────────────────────
    # Tosse + vômito pós-tosse + falta ar = tríade patognomônica de Coqueluche
    if dados.get("tosse") and dados.get("vomito_nausea") and dados.get("falta_ar"):
        if doenca == "Coqueluche":
            return max(prior, 0.45)
        # TB pulmonar raramente causa vômito diretamente relacionado à tosse
        if doenca == "Tuberculose":
            return min(prior, 0.10)
    if dados.get("contato_caso_confirmado") and dados.get("tosse") and dados.get("vomito_nausea"):
        if doenca == "Coqueluche":
            return max(prior, 0.50)

    # ── Febre Tifoide ─────────────────────────────────────────────────────────
    # Água contaminada + febre + dor abdominal = tríade clássica de tifoide
    if dados.get("exposicao_agua_enchente") and dados.get("febre") and dados.get("dor_abdominal"):
        if doenca == "Febre Tifoide":
            # febre+água+abdome é mais característico de tifoide do que de leptospirose
            return max(prior, 0.35)
    elif dados.get("exposicao_agua_enchente") and dados.get("febre"):
        if doenca == "Febre Tifoide":
            return max(prior, 0.15)

    # ── Esquistossomose ───────────────────────────────────────────────────────
    # Contato com água doce é a via de transmissão obrigatória
    if dados.get("exposicao_agua_enchente") and dados.get("diarreia") and dados.get("dor_abdominal"):
        if doenca == "Esquistossomose":
            # diarreia + dor abdominal + água doce é a tríade clínica clássica
            return max(prior, 0.50)
    elif dados.get("exposicao_agua_enchente") and (dados.get("diarreia") or dados.get("dor_abdominal")):
        if doenca == "Esquistossomose":
            return max(prior, 0.30)
    # Esquistossomose sem qualquer exposição hídrica → praticamente impossível
    if dados.get("exposicao_agua_enchente") is False:
        if doenca == "Esquistossomose":
            return min(prior, 0.01)

    # ── Febre Maculosa — exposição a carrapato é o vetor obrigatório ─────────
    if dados.get("exposicao_carrapato"):
        if doenca == "Febre Maculosa":
            # carrapato-estrela + febre = Febre Maculosa até prova em contrário
            return max(prior, 0.60 if dados.get("febre") else 0.40)
        # Dengue não é transmitida por carrapato
        if doenca == "Dengue":
            return min(prior, 0.25)
    if dados.get("exposicao_carrapato") is False:
        if doenca == "Febre Maculosa":
            return min(prior, 0.008)  # sem carrapato, FM é rara demais para o cidadão

    # ── Doença de Chagas — barbeiro é o vetor obrigatório ────────────────────
    if dados.get("exposicao_triatomideo"):
        if doenca == "Doença de Chagas":
            # contato com barbeiro é altamente específico para Chagas
            return max(prior, 0.55 if dados.get("febre") else 0.35)
    if dados.get("exposicao_triatomideo") is False:
        if doenca == "Doença de Chagas":
            return min(prior, 0.005)  # sem barbeiro, Chagas quase impossível no app

    # ── Leishmaniose Visceral — emagrecimento + febre prolongada ─────────────
    if dados.get("perda_peso") and dados.get("febre"):
        if doenca == "Leishmaniose Visceral":
            # calazar: febre prolongada + emagrecimento = combinação cardinal
            lv_prior = 0.50 if dados.get("dor_abdominal") else 0.35
            return max(prior, lv_prior)
        if doenca == "Tuberculose":
            return max(prior, 0.30)
        # Emagrecimento + febre prolongada é atípico de doenças agudas (dengue, gripe)
        if doenca in ("Dengue", "Chikungunya", "Gripe (Influenza)", "Zika"):
            return min(prior, 0.25)

    # ── Hanseníase — mancha insensível é patognomônica ────────────────────────
    if dados.get("mancha_anestesia"):
        if doenca == "Hanseníase":
            # mancha insensível → hanseníase até prova em contrário
            return max(prior, 0.75)
        # Praticamente todas as outras doenças ficam muito menos prováveis
        if doenca in ("Dengue", "Gripe (Influenza)", "COVID-19", "Resfriado Viral", "Gastroenterite Viral"):
            return min(prior, 0.05)

    # ── Leishmaniose Tegumentar — úlcera indolor é patognomônica ─────────────
    if dados.get("ulcera_cutanea"):
        if doenca == "Leishmaniose Tegumentar":
            return max(prior, 0.70)
        # Úlcera cutânea indolor é incompatível com doenças agudas febris / arboviroses
        if doenca in ("Dengue", "Gripe (Influenza)", "COVID-19", "Gastroenterite Viral",
                      "Febre Maculosa", "Chikungunya", "Zika", "Malaria"):
            return min(prior, 0.05)

    # ── Varicela / Mpox — exantema vesicular: diferenciação pela exposição ────
    if dados.get("exantema_vesicular"):
        if doenca == "Varicela":
            # Sem contato confirmado: Varicela domina (muito mais comum que Mpox)
            mpox_contato = dados.get("contato_caso_confirmado") and dados.get("febre")
            return max(prior, 0.50 if mpox_contato else 0.80)
        if doenca == "Mpox":
            # Vesículas + contato direto: Mpox considerado clinicamente
            if dados.get("contato_caso_confirmado") and dados.get("febre"):
                return max(prior, 0.55)
            elif dados.get("febre") and dados.get("dor_corpo"):
                return max(prior, 0.25)  # febre antes das vesículas aponta para Mpox
        # Vesículas com líquido tornam outras arboviroses muito menos prováveis
        if doenca in ("Dengue", "Chikungunya", "Zika"):
            return min(prior, 0.10)
        if doenca == "Febre Maculosa":
            return min(prior, 0.05)  # FM é macular/petequial, nunca vesicular

    # ── Tuberculose Phase 2 — hemoptise eleva probabilidade de TB ────────────
    if dados.get("hemoptise"):
        if doenca == "Tuberculose":
            return max(prior, 0.45)
        if doenca == "Hantavirose":
            return max(prior, 0.30)
        # Doenças gastrintestinais/arboviroses sem componente pulmonar
        if doenca in ("Gastroenterite Viral", "Dengue", "Resfriado Viral"):
            return min(prior, 0.05)

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
        if doenca in ("Malaria", "Febre Amarela", "Febre Maculosa"):
            mult *= 2.0  # FM é endêmica de zonas rurais com carrapato-estrela
        elif doenca in ("Dengue", "Chikungunya", "Zika", "Leptospirose"):
            mult *= 1.5
        elif doenca in ("Leishmaniose Tegumentar", "Leishmaniose Visceral"):
            mult *= 2.0  # leishmanioses são doenças de zonas endêmicas — viagem é fator chave

    # Exposição à água de enchente/lama
    if dados.get("exposicao_agua_enchente"):
        if doenca == "Hepatite A/B":
            mult *= 2.0
        # Leptospirose: prior_override JÁ eleva de 0.08→0.45; modifier é refinamento leve
        # (não aplicar 2.0 aqui — seria double-counting com o override de prior)

    # Contato com roedores — override de prior já eleva Lepto/Hanta para 0.55
    if dados.get("contato_roedores"):
        if doenca == "Hantavirose":
            mult *= 2.5  # mantém: Hantavirose é muito rara, precisa do boost forte

    # Leptospirose — lógica unificada de exposição epidemiológica:
    # - single exposure (uma via): refinamento leve (prior override já fez o trabalho pesado)
    # - double exposure (ambas as vias): boost justificado — risco real duplicado
    # - nenhuma via explicitamente negada: penalidade forte
    if doenca == "Leptospirose":
        agua = dados.get("exposicao_agua_enchente")
        ratos = dados.get("contato_roedores")
        if agua and ratos:
            mult *= 3.0   # ambas as vias confirmadas → situação de risco real elevado
        elif agua or ratos:
            mult *= 1.5   # single exposure: refinamento (não segundo boost completo)
        elif agua is False and ratos is False:
            mult *= 0.05  # ambas negadas explicitamente → praticamente excluída
        elif agua is False or ratos is False:
            mult *= 0.30  # uma via negada → ainda possível mas improvável

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
        elif doenca in ("Tuberculose", "Varicela", "Coqueluche"):
            mult *= 2.5  # altamente contagiosas por aerossol
        elif doenca == "Mpox":
            mult *= 3.0  # Mpox transmitida principalmente por contato direto
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
                      "Gastroenterite Viral", "Leptospirose", "Hantavirose",
                      "Febre Maculosa", "Febre Tifoide"):
            mult *= 1.5
        elif doenca in ("Resfriado Viral", "Bronquite / DPOC Agudização"):
            mult *= 0.4
        elif doenca == "Tuberculose":
            mult *= 0.3  # TB tem início insidioso — início abrupto praticamente descarta
    elif inicio is False:
        if doenca in ("Resfriado Viral", "COVID-19", "Bronquite / DPOC Agudização"):
            mult *= 1.4
        elif doenca in ("Dengue", "Gripe (Influenza)", "Malaria", "Febre Maculosa"):
            mult *= 0.5
        elif doenca == "Tuberculose":
            mult *= 1.6  # início gradual é característico da TB
        elif doenca == "Febre Tifoide":
            mult *= 1.3  # tifoide tem evolução gradual com piora progressiva

    # Comorbidade → aumenta risco de formas graves / padrão de DPOC crônica
    if dados.get("tem_comorbidade"):
        if doenca in ("COVID-19", "Gripe (Influenza)", "Dengue", "Leptospirose",
                      "Bronquite / DPOC Agudização"):
            mult *= 1.3
        elif doenca == "Tuberculose":
            mult *= 1.6  # HIV, DM, IRC são fatores de risco muito relevantes para TB ativa

    # Tosse + vômito pós-tosse → diferencial TB vs Coqueluche
    # Vômito diretamente relacionado à tosse é patognomônico de Coqueluche, não TB
    if dados.get("tosse") and dados.get("vomito_nausea"):
        if doenca == "Coqueluche":
            mult *= 2.0  # vômito pós-acesso de tosse é o diferencial clínico chave
        elif doenca == "Tuberculose":
            mult *= 0.4  # TB pulmonar raramente causa vômito relacionado à tosse

    # dias_sintomas — TB tem evolução crônica; Febre Tifoide piora por semanas
    dias = dados.get("dias_sintomas")
    if dias is not None:
        try:
            dias_int = int(dias)
        except (TypeError, ValueError):
            dias_int = 0

        if doenca == "Tuberculose" and dados.get("tosse"):
            if dias_int >= 21:
                mult *= 3.0  # tosse ≥3 semanas = critério diagnóstico de TB — peso máximo
            elif dias_int >= 14:
                mult *= 2.0  # 2 semanas já é suspeito
            elif dias_int < 7:
                mult *= 0.3  # TB não aparece em menos de 1 semana de doença aguda

        if doenca == "Febre Tifoide":
            if dias_int >= 14:
                mult *= 2.5  # piora progressiva por 2+ semanas é altamente sugestiva
            elif dias_int >= 7:
                mult *= 1.8  # febre persistente >7 dias é o padrão clássico da tifoide
            elif dias_int < 3:
                mult *= 0.5  # tifoide raramente se apresenta no início (incubação longa)

        if doenca == "Esquistossomose" and dias_int >= 14:
            mult *= 1.5  # fase aguda dura semanas; sintomas persistentes são típicos

        # Doenças com evolução crônica (semanas a meses)
        if doenca == "Hanseníase":
            if dias_int >= 30:
                mult *= 2.0  # evolução > 30 dias é muito característico de hanseníase
            elif dias_int < 7:
                mult *= 0.2  # hanseníase não se apresenta em menos de 1 semana

        if doenca == "Leishmaniose Visceral":
            if dias_int >= 14:
                mult *= 2.0  # febre prolongada por 2+ semanas é padrão do calazar
            elif dias_int < 7:
                mult *= 0.3  # calazar não se apresenta em menos de 1 semana

        if doenca == "Doença de Chagas":
            if dias_int >= 14:
                mult *= 1.8  # fase aguda dura 4-8 semanas; 2+ semanas é sugestivo
            elif dias_int < 5:
                mult *= 0.4  # fase aguda raramente cursa tão rapidamente

    # Chagas — contato com barbeiro eleva multiplicador fortemente
    if dados.get("exposicao_triatomideo"):
        if doenca == "Doença de Chagas":
            mult *= 3.0  # barbeiro é o vetor quase exclusivo — contato é definitivo
        if doenca in ("Dengue", "Gripe (Influenza)", "Resfriado Viral", "Gastroenterite Viral"):
            mult *= 0.5  # exposição a barbeiro não tem relação com essas doenças

    # Febre Maculosa — carrapato é o vetor
    if dados.get("exposicao_carrapato"):
        if doenca == "Febre Maculosa":
            mult *= 3.0
        if doenca in ("Dengue", "Gripe (Influenza)", "Resfriado Viral"):
            mult *= 0.5

    # Hanseníase sem mancha anestésica — quase impossível para cidadão sintomático
    if dados.get("mancha_anestesia") is False and doenca == "Hanseníase":
        mult *= 0.05

    # Leishmaniose Tegumentar sem úlcera → muito improvável para app cidadão
    if dados.get("ulcera_cutanea") is False and doenca == "Leishmaniose Tegumentar":
        mult *= 0.05

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

_SINTOMA_LABEL: dict[str, str] = {
    "febre":                "Febre",
    "tosse":                "Tosse",
    "dor_corpo":            "Dores no corpo",
    "cansaco":              "Cansaço intenso",
    "falta_ar":             "Falta de ar",
    "dor_cabeca":           "Dor de cabeça",
    "dor_articular":        "Dor nas articulações",
    "exantema":             "Manchas ou vermelhidão na pele",
    "conjuntivite":         "Olhos vermelhos",
    "vomito_nausea":        "Náusea ou vômito",
    "diarreia":             "Diarreia",
    "dor_abdominal":        "Dor abdominal",
    "rigidez_nuca":         "Rigidez de nuca",
    "ictericia":            "Pele ou olhos amarelados",
    "manchas_hemorragicas": "Manchas avermelhadas na pele",
    "perda_olfato_paladar": "Perda de olfato ou paladar",
    "dor_garganta":         "Dor de garganta",
    "coriza":               "Coriza / nariz escorrendo",
    "calafrios":            "Calafrios",
    "sudorese":             "Suor intenso",
    "hemoptise":            "Tosse com sangue",
    "exantema_vesicular":   "Bolhas com líquido na pele",
    "perda_peso":           "Perda de peso recente",
    "ulcera_cutanea":       "Ferida na pele que não cicatriza",
    "mancha_anestesia":     "Mancha insensível ao toque",
}


def _hipotese_texto(doenca: str, confianca: float, nominavel: bool) -> dict:
    if not nominavel or confianca < 45:
        return {
            "texto": "Seus sintomas indicam um quadro que requer avaliação médica para identificação precisa.",
            "doenca_nome": None,
            "nivel": "baixo",
        }
    if confianca >= 65:
        return {
            "texto": f"Com base no que você nos relatou, {doenca} é a hipótese mais compatível com seu quadro.",
            "doenca_nome": doenca,
            "nivel": "alto",
        }
    return {
        "texto": f"Seus sintomas têm mais de um padrão possível. {doenca} é o mais provável, mas não é possível determinar sem exame.",
        "doenca_nome": doenca,
        "nivel": "medio",
    }


def _mencionar_ao_medico(dados: dict) -> list[str]:
    items = []
    dias = dados.get("dias_sintomas")
    if dias:
        items.append(f"Sintomas há {dias} dia{'s' if int(dias) != 1 else ''}")
    if dados.get("inicio_abrupto") is True:
        items.append("Início abrupto dos sintomas")
    if dados.get("viagem_area_endemica") is True:
        items.append("Viagem recente para área de mata ou endêmica")
    if dados.get("exposicao_agua_enchente") is True:
        items.append("Contato com água de enchente ou esgoto")
    if dados.get("contato_roedores") is True:
        items.append("Contato com ratos ou animais silvestres")
    if dados.get("contato_caso_confirmado") is True:
        items.append("Contato próximo com caso confirmado de doença")
    if dados.get("vacinado_febre_amarela") is False:
        items.append("Não está vacinado para febre amarela")
    if dados.get("tem_comorbidade") is True:
        items.append("Tem condição de saúde pré-existente")
    if dados.get("exposicao_carrapato") is True:
        items.append("Contato recente com carrapatos")
    if dados.get("exposicao_triatomideo") is True:
        items.append("Contato com inseto barbeiro")
    return items


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
        # Novas — nomeáveis porque o cidadão precisa saber para buscar cuidado adequado
        "Varicela", "Tuberculose", "Coqueluche", "Febre Tifoide", "Esquistossomose", "Mpox",
        # Febre Maculosa é urgência (cor=vermelha) — nomeável para reforçar a busca por PS
        "Febre Maculosa",
        # Phase 2 — nomeáveis para orientar busca ao cuidado correto
        "Doença de Chagas", "Hanseníase", "Leishmaniose Visceral", "Leishmaniose Tegumentar",
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

    # Decide se a doença pode ser nomeada na hipótese ao cidadão.
    # Falso quando: confiança baixa, inconclusivo, febre guard, leptospirose sem exposição.
    _hipotese_nominavel = (
        doenca in DOENCAS_NOMINAVEIS
        and confianca >= 45
        and doenca != "Inconclusivo"
        and info_sindrome.get("sindrome") != "Sintomas em Acompanhamento"
        and not (
            doenca == "Leptospirose"
            and dados.get("exposicao_agua_enchente") is False
            and dados.get("contato_roedores") is False
        )
    )

    return {
        # O que o cidadão vê
        "sindrome": info_sindrome["sindrome"],
        "cor_alerta": info_sindrome["cor"],
        "conduta": info_sindrome["conduta"],
        "alerta_urgente": alerta_urgente,
        # Hipótese probabilística — texto seguro para exibir ao cidadão
        "hipotese": _hipotese_texto(doenca, confianca, _hipotese_nominavel),
        # Espelho dos sintomas relatados (labels em português)
        "sintomas_positivos": [
            _SINTOMA_LABEL[k]
            for k in _SINTOMA_LABEL
            if dados.get(k) is True
        ],
        # Pontos de anamnese relevantes para levar ao médico
        "mencionar_ao_medico": _mencionar_ao_medico(dados),
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
            "Resultado gerado por modelo estatístico de apoio — não constitui diagnóstico "
            "médico, prescrição, laudo ou parecer clínico. A hipótese é probabilística e "
            "pode estar incorreta. Não substitui avaliação por profissional de saúde "
            "habilitado. Em caso de sintomas graves ou agravamento, procure atendimento "
            "imediatamente. SolusCRT Sistemas Integrados LTDA não assume responsabilidade "
            "por decisões clínicas baseadas nesta triagem automática."
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
