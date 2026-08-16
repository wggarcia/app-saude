"""
IA por Área — arquitetura de aprendizado dedicada por domínio clínico/operacional.

Cada ÁREA (opme, oncologia, …) tem o seu próprio modelo, treinado com as
DECISÕES REAIS daquela área e daquela empresa (isolamento por tenant / LGPD).
O mesmo motor (RandomForest + GradientBoosting em ensemble, mesma linha do
`views_hospital_ia_autorizacao_ml.py`) é reutilizado; o que muda por área é:
  - de onde vêm os exemplos rotulados (o dataset real);
  - quais features descrevem o caso;
  - o bootstrap sintético usado enquanto não há dados reais suficientes.

Registry extensível: registrar uma nova área = adicionar um dict em AREAS.
Nada aqui depende de rede externa; treino e inferência rodam offline.
"""
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings

MIN_AMOSTRAS_TREINO = 30

MODELS_DIR = Path(settings.MEDIA_ROOT) / "ml_models" / "ia_areas"
try:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def _paths(area, empresa_id):
    base = MODELS_DIR / area
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return (base / f"{area}_model_{empresa_id}.joblib",
            base / f"{area}_encoder_{empresa_id}.joblib")


# ═══════════════════════════════════════════════════════════════════════════
# ÁREA: OPME
# ═══════════════════════════════════════════════════════════════════════════

OPME_FEATURES = [
    "tem_fora_padrao", "nao_homologado", "acima_teto", "tem_alerta_fraude",
    "tem_procedimento_tuss", "tem_justificativa", "n_itens", "qtd_alertas",
]


def _opme_features_de_dict(d):
    """Extrai features de um caso OPME (dict). Tudo derivável do pedido + itens,
    sem consulta externa — treino e inferência rápidos."""
    return {
        "tem_fora_padrao":       int(bool(d.get("tem_fora_padrao"))),
        "nao_homologado":        int(bool(d.get("nao_homologado"))),
        "acima_teto":            int(bool(d.get("acima_teto"))),
        "tem_alerta_fraude":     int(bool(d.get("tem_alerta_fraude"))),
        "tem_procedimento_tuss": int(bool(d.get("tem_procedimento_tuss"))),
        "tem_justificativa":     int(bool(d.get("tem_justificativa"))),
        "n_itens":               int(d.get("n_itens") or 1),
        "qtd_alertas":           int(d.get("qtd_alertas") or 0),
    }


def _opme_dataset_real(empresa_id):
    """Exemplos rotulados a partir das autorizações OPME já DECIDIDAS da empresa.
    Ground truth = status resolvido (aprovada/parcial/negada)."""
    from api.models import AutorizacaoOPME
    exemplos = []
    qs = (AutorizacaoOPME.objects
          .filter(empresa_id=empresa_id, status__in=["aprovada", "parcial", "negada"])
          .prefetch_related("itens__opme"))
    for a in qs:
        itens = list(a.itens.all())
        acima = False
        nao_homol = False
        for it in itens:
            if it.opme and it.opme.homologado is False:
                nao_homol = True
            if (it.preco_solicitado is not None and it.opme
                    and it.opme.preco_maximo is not None
                    and float(it.preco_solicitado) > float(it.opme.preco_maximo)):
                acima = True
        exemplos.append({
            "tem_fora_padrao": any(it.fora_padrao for it in itens),
            "nao_homologado": nao_homol,
            "acima_teto": acima,
            "tem_alerta_fraude": a.tem_alerta_fraude,
            "tem_procedimento_tuss": bool(a.procedimento_tuss),
            "tem_justificativa": bool((a.justificativa or "").strip()),
            "n_itens": len(itens) or 1,
            "qtd_alertas": len(a.alertas_triagem or []),
            "label": "parcial" if a.status == "parcial" else a.status,
        })
    return exemplos


def _opme_dataset_sintetico():
    """Bootstrap com o conhecimento clínico/regulatório: pedido em conformidade
    → aprovar; fora do padrão + fraude → negar; fora do padrão com justificativa
    → revisão parcial. Só inicializa o classificador antes de haver dados reais."""
    ex = []
    # conformes → aprovada
    for _ in range(8):
        ex.append({"tem_fora_padrao": 0, "nao_homologado": 0, "acima_teto": 0,
                   "tem_alerta_fraude": 0, "tem_procedimento_tuss": 1,
                   "tem_justificativa": 1, "n_itens": 1, "qtd_alertas": 0,
                   "label": "aprovada"})
    # fora do padrão + fraude → negada
    for _ in range(6):
        ex.append({"tem_fora_padrao": 1, "nao_homologado": 1, "acima_teto": 1,
                   "tem_alerta_fraude": 1, "tem_procedimento_tuss": 0,
                   "tem_justificativa": 0, "n_itens": 2, "qtd_alertas": 3,
                   "label": "negada"})
    # fora do padrão COM justificativa → parcial (revisão que aprova em parte)
    for _ in range(6):
        ex.append({"tem_fora_padrao": 1, "nao_homologado": 0, "acima_teto": 1,
                   "tem_alerta_fraude": 0, "tem_procedimento_tuss": 1,
                   "tem_justificativa": 1, "n_itens": 1, "qtd_alertas": 1,
                   "label": "parcial"})
    return ex


def _opme_justificativa(features, decisao):
    m = []
    if features["tem_fora_padrao"]: m.append("material fora do padrão homologado")
    if features["nao_homologado"]: m.append("item não homologado")
    if features["acima_teto"]: m.append("preço acima do teto")
    if features["tem_alerta_fraude"]: m.append("padrão atípico do solicitante")
    if features["tem_procedimento_tuss"] and not features["tem_fora_padrao"]:
        m.append("dentro do procedimento padronizado")
    if not m:
        m.append("pedido em conformidade com o padrão")
    acao = {"aprovada": "Aprovação recomendada", "negada": "Negativa recomendada",
            "parcial": "Aprovação parcial / revisão"}.get(decisao, decisao)
    return f"{acao} — " + "; ".join(m) + "."


# ═══════════════════════════════════════════════════════════════════════════
# Registry de áreas
# ═══════════════════════════════════════════════════════════════════════════

AREAS = {
    "opme": {
        "label": "OPME — Autorização de materiais",
        "features": OPME_FEATURES,
        "extrair": _opme_features_de_dict,
        "dataset_real": _opme_dataset_real,
        "dataset_sintetico": _opme_dataset_sintetico,
        "justificativa": _opme_justificativa,
    },
}


def areas_disponiveis():
    return list(AREAS.keys())


# ═══════════════════════════════════════════════════════════════════════════
# Treino e inferência genéricos (mesmo motor para todas as áreas)
# ═══════════════════════════════════════════════════════════════════════════

def treinar_area(area, empresa_id):
    """Treina o modelo de UMA área para UMA empresa. Retorna metadados e grava
    o registro em ModeloIAArea. Exige empresa_id (isolamento/LGPD)."""
    if area not in AREAS:
        raise ValueError(f"Área desconhecida: {area}")
    if not empresa_id:
        raise ValueError("treinar_area exige empresa_id (isolamento por empresa / LGPD).")

    from sklearn.ensemble import (RandomForestClassifier, GradientBoostingClassifier,
                                  VotingClassifier)
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import cross_val_score
    from api.models import ModeloIAArea

    spec = AREAS[area]
    exemplos = spec["dataset_real"](empresa_id)
    sintetico = len(exemplos) < MIN_AMOSTRAS_TREINO
    if sintetico:
        # combina o pouco real que houver com o bootstrap, pra já capturar o
        # padrão da empresa sem quebrar por falta de volume.
        exemplos = exemplos + spec["dataset_sintetico"]()

    feats = spec["features"]
    X = np.array([[spec["extrair"](e)[n] for n in feats] for e in exemplos])
    y_raw = [e["label"] for e in exemplos]

    le = LabelEncoder()
    y = le.fit_transform(y_raw)

    # se só houver 1 classe (dados pobres), não há o que classificar — aborta
    # honesto em vez de treinar um modelo degenerado.
    if len(set(y)) < 2:
        raise ValueError(f"Área {area}: dados insuficientes (só uma classe de decisão).")

    rf = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_split=5,
                                class_weight="balanced", random_state=42, n_jobs=-1)
    gb = GradientBoostingClassifier(n_estimators=150, learning_rate=0.05, max_depth=4,
                                    subsample=0.8, random_state=42)
    ensemble = VotingClassifier(estimators=[("rf", rf), ("gb", gb)],
                                voting="soft", weights=[2, 1])
    ensemble.fit(X, y)

    try:
        cv = cross_val_score(ensemble, X, y, cv=min(5, max(2, len(exemplos) // 10)),
                             scoring="f1_weighted")
        f1 = float(cv.mean())
    except Exception:
        f1 = None

    model_path, encoder_path = _paths(area, empresa_id)
    joblib.dump(ensemble, model_path)
    joblib.dump(le, encoder_path)

    n_reais = len(spec["dataset_real"](empresa_id))
    reg, _ = ModeloIAArea.objects.update_or_create(
        empresa_id=empresa_id, area=area,
        defaults={
            "n_amostras": n_reais,
            "acuracia_f1": f1,
            "dataset_sintetico": sintetico,
            "classes": le.classes_.tolist(),
            "arquivo": str(model_path.name),
        })
    ModeloIAArea.objects.filter(pk=reg.pk).update(versao=reg.versao + 1)
    return {
        "area": area, "empresa_id": empresa_id, "n_amostras_reais": n_reais,
        "n_treino": len(exemplos), "dataset_sintetico": sintetico,
        "cv_f1": f1, "classes": le.classes_.tolist(),
    }


def _carregar(area, empresa_id):
    from api.models import ModeloIAArea
    model_path, encoder_path = _paths(area, empresa_id)
    # Re-treina se faltar o ARQUIVO ou o REGISTRO no banco — os dois precisam
    # estar em sincronia. Sem checar o banco, um arquivo antigo (de outra
    # execução / após reset de banco) seria carregado sem registro de status.
    tem_registro = ModeloIAArea.objects.filter(empresa_id=empresa_id, area=area).exists()
    if not model_path.exists() or not encoder_path.exists() or not tem_registro:
        treinar_area(area, empresa_id)
    return joblib.load(model_path), joblib.load(encoder_path)


def inferir(area, empresa_id, dados):
    """Inferência de uma área. Retorna dict {decisao, score, justificativa,...}.
    Levanta se a área não existe ou sem empresa_id — o chamador cai no fallback."""
    if area not in AREAS:
        raise ValueError(f"Área desconhecida: {area}")
    if not empresa_id:
        raise ValueError("inferir exige empresa_id (isolamento por empresa / LGPD).")
    spec = AREAS[area]
    model, le = _carregar(area, empresa_id)
    feats = spec["extrair"](dados)
    X = np.array([[feats[n] for n in spec["features"]]])
    proba = model.predict_proba(X)[0]
    classes = le.classes_
    idx = int(np.argmax(proba))
    decisao = classes[idx]
    conf = float(proba[idx])
    return {
        "decisao": decisao,
        "score_confianca": round(conf, 4),
        "scores_por_classe": {c: round(float(p), 4) for c, p in zip(classes, proba)},
        "justificativa_ia": spec["justificativa"](feats, decisao),
        "features_utilizadas": feats,
        "modelo": f"IA-área {area} · Ensemble RF+GB SoloCRT",
    }
