"""
ML treinado em dado oficial (DATASUS/SINAN) para a vigilância epidemiológica.

Substitui o limiar fixo usado em epidemiologia.py (ex.: media*1.35) por um
classificador treinado nas series reais de notificacao agregadas em
FonteOficialAgregado (api/pipeline_oficial.py), aprendendo o padrao de canal
endemico (sazonalidade + estado) em vez de aplicar um multiplicador unico
hardcoded para o Brasil inteiro.

Mesmo padrao de bootstrap/persistencia de views_ia_autorizacao_ml.py: cai no
calculo heuristico quando nao ha amostras oficiais suficientes para a
fonte/indicador/estado (ex.: estado sem dado oficial importado ainda).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings
from django.db.models import Sum

from .models import FonteOficialAgregado

MODELS_DIR = Path(getattr(settings, "BASE_DIR", "/tmp")) / "ml_models" / "epidemiologia"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = MODELS_DIR / "risco_oficial_model.joblib"
META_PATH = MODELS_DIR / "risco_oficial_meta.json"

MIN_AMOSTRAS_TREINO = 40  # minimo de observacoes (estado x semana) reais para treinar
JANELA_MEDIA_MOVEL = 4

FEATURE_NAMES = ["valor_atual", "media_movel", "desvio_movel", "razao_media", "semana_do_ano", "estado_idx"]

_MODELO_CACHE = {"bundle": None, "mtime": None}


def _parse_periodo(periodo: str):
    m = re.match(r"^(\d{4})-S(\d{2})$", periodo or "")
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _coletar_series(fonte_id: str, indicador: str):
    qs = (
        FonteOficialAgregado.objects.filter(fonte_id=fonte_id, indicador=indicador)
        .exclude(estado__isnull=True)
        .exclude(estado="")
        .values("estado", "periodo")
        .annotate(total=Sum("valor"))
    )
    por_estado = {}
    for row in qs:
        ano, semana = _parse_periodo(row["periodo"])
        if ano is None:
            continue
        por_estado.setdefault(row["estado"], []).append((ano, semana, float(row["total"] or 0)))
    for estado in por_estado:
        por_estado[estado].sort(key=lambda t: (t[0], t[1]))
    return por_estado


def _janela_stats(valores, fim_idx):
    janela = valores[max(0, fim_idx - JANELA_MEDIA_MOVEL):fim_idx]
    if not janela:
        return 0.0, 1.0
    media = float(np.mean(janela))
    desvio = float(np.std(janela)) or 1.0
    return media, desvio


def _construir_dataset(fonte_id: str, indicador: str):
    por_estado = _coletar_series(fonte_id, indicador)
    estados = sorted(por_estado.keys())
    estado_idx_map = {uf: i for i, uf in enumerate(estados)}

    X, y = [], []
    for estado, serie in por_estado.items():
        valores = [v for _, _, v in serie]
        for i in range(JANELA_MEDIA_MOVEL, len(serie)):
            ano, semana, valor_atual = serie[i]
            media, desvio = _janela_stats(valores, i)
            razao = valor_atual / media if media else 1.0
            label = int(valor_atual > media + 1.5 * desvio)
            X.append([valor_atual, media, desvio, razao, semana, estado_idx_map[estado]])
            y.append(label)

    return np.array(X, dtype=float), np.array(y), estados


def treinar_modelo_oficial(fonte_id="sinan_agravos", indicador="dengue_notificacoes_sinan"):
    """Treina (ou recusa treinar, de forma transparente) com dado real oficial."""
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, VotingClassifier
    from sklearn.model_selection import cross_val_score

    X, y = np.empty((0, len(FEATURE_NAMES))), np.empty((0,))
    estados = []
    try:
        X, y, estados = _construir_dataset(fonte_id, indicador)
    except Exception:
        pass

    if len(X) < MIN_AMOSTRAS_TREINO or len(set(y.tolist())) < 2:
        return {
            "treinado": False,
            "motivo": "amostras_oficiais_insuficientes",
            "fonte_id": fonte_id,
            "indicador": indicador,
            "n_amostras": int(len(X)),
            "minimo_necessario": MIN_AMOSTRAS_TREINO,
        }

    rf = RandomForestClassifier(
        n_estimators=150, max_depth=6, min_samples_split=4,
        class_weight="balanced", random_state=42, n_jobs=-1,
    )
    gb = GradientBoostingClassifier(n_estimators=100, learning_rate=0.05, max_depth=3, random_state=42)
    ensemble = VotingClassifier(estimators=[("rf", rf), ("gb", gb)], voting="soft", weights=[2, 1])
    ensemble.fit(X, y)

    cv_folds = min(5, len(X) // 20 + 2)
    cv_scores = cross_val_score(ensemble, X, y, cv=cv_folds, scoring="f1_weighted")

    joblib.dump({"model": ensemble, "estados": estados, "fonte_id": fonte_id, "indicador": indicador}, MODEL_PATH)

    meta = {
        "treinado": True,
        "treinado_em": datetime.now().isoformat(),
        "fonte_id": fonte_id,
        "indicador": indicador,
        "n_amostras": int(len(X)),
        "estados": estados,
        "cv_f1_media": float(cv_scores.mean()),
        "cv_f1_std": float(cv_scores.std()),
        "dataset_real_oficial": True,
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def _carregar_modelo():
    if not MODEL_PATH.exists():
        return None
    mtime = MODEL_PATH.stat().st_mtime
    if _MODELO_CACHE["bundle"] is not None and _MODELO_CACHE["mtime"] == mtime:
        return _MODELO_CACHE["bundle"]
    try:
        bundle = joblib.load(MODEL_PATH)
    except Exception:
        return None
    _MODELO_CACHE["bundle"] = bundle
    _MODELO_CACHE["mtime"] = mtime
    return bundle


def mapa_risco_oficial_por_estado(fonte_id="sinan_agravos", indicador="dengue_notificacoes_sinan"):
    """
    Retorna {estado: probabilidade_ml} usando a observacao oficial mais
    recente de cada estado coberto pelo modelo treinado. Dict vazio quando
    nao ha modelo treinado (chamador deve usar so a heuristica nesse caso).
    """
    bundle = _carregar_modelo()
    if bundle is None or bundle.get("fonte_id") != fonte_id or bundle.get("indicador") != indicador:
        return {}

    por_estado = _coletar_series(fonte_id, indicador)
    model = bundle["model"]
    estados_treino = bundle["estados"]
    resultado = {}

    for estado, serie in por_estado.items():
        if estado not in estados_treino or len(serie) <= JANELA_MEDIA_MOVEL:
            continue
        valores = [v for _, _, v in serie]
        ano, semana, valor_atual = serie[-1]
        media, desvio = _janela_stats(valores, len(serie) - 1)
        razao = valor_atual / media if media else 1.0
        estado_idx = estados_treino.index(estado)
        X = np.array([[valor_atual, media, desvio, razao, semana, estado_idx]], dtype=float)
        try:
            proba = model.predict_proba(X)[0]
            classes = list(model.classes_)
            resultado[estado] = float(proba[classes.index(1)]) if 1 in classes else 0.0
        except Exception:
            continue

    return resultado


def modelo_info(fonte_id="sinan_agravos", indicador="dengue_notificacoes_sinan"):
    if not META_PATH.exists():
        return {"modelo_treinado": False}
    with open(META_PATH) as f:
        meta = json.load(f)
    if meta.get("fonte_id") != fonte_id or meta.get("indicador") != indicador:
        return {"modelo_treinado": False, "meta_desatualizada_para_outra_fonte": True}
    meta["modelo_treinado"] = True
    return meta
