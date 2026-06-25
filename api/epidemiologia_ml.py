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

Suporta multiplas doencas (uma fonte/indicador por doenca, ver
DOENCAS_REGISTRADAS) — cada uma treina e persiste seu proprio modelo,
nomeado pelo indicador, para nao misturar series de doencas diferentes.
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

MIN_AMOSTRAS_TREINO = 40  # minimo de observacoes (estado x semana) reais para treinar
JANELA_MEDIA_MOVEL = 4

FEATURE_NAMES = ["valor_atual", "media_movel", "desvio_movel", "razao_media", "semana_do_ano", "estado_idx"]

# Doencas com fonte oficial real verificada e wireada em pipeline_oficial.py.
# Cada entrada e (fonte_id, indicador, nome_da_doenca_em_DISEASE_WEIGHTS).
# Doencas que nao tem dataset oficial confirmado (ex.: Resfriado Viral,
# Bronquite, Gastroenterite Viral, Virose — nao sao de notificacao
# compulsoria no Brasil) ficam de fora de proposito: nao ha fonte real para
# treinar, e nao vamos simular uma.
DOENCAS_REGISTRADAS = [
    ("sinan_agravos", "dengue_notificacoes_sinan", "Dengue"),
    ("sinan_chikungunya", "chikungunya_notificacoes_sinan", "Chikungunya"),
    ("sinan_zika", "zika_notificacoes_sinan", "Zika"),
]

_MODELO_CACHE = {}  # indicador -> {"bundle": ..., "mtime": ...}


def _slug(indicador: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (indicador or "").lower()).strip("_") or "default"


def _model_path(indicador: str) -> Path:
    return MODELS_DIR / f"risco_oficial_{_slug(indicador)}_model.joblib"


def _meta_path(indicador: str) -> Path:
    return MODELS_DIR / f"risco_oficial_{_slug(indicador)}_meta.json"


# Compatibilidade com versao anterior (1 doenca so) e com os testes existentes,
# que continuam podendo sobrescrever esses dois caminhos via patch.object.
MODEL_PATH = _model_path("dengue_notificacoes_sinan")
META_PATH = _meta_path("dengue_notificacoes_sinan")


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

    model_path = MODEL_PATH if indicador == "dengue_notificacoes_sinan" else _model_path(indicador)
    meta_path = META_PATH if indicador == "dengue_notificacoes_sinan" else _meta_path(indicador)

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

    joblib.dump({"model": ensemble, "estados": estados, "fonte_id": fonte_id, "indicador": indicador}, model_path)

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
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def treinar_todas_doencas_registradas():
    """Treina (ou recusa, de forma transparente) o modelo de cada doenca em
    DOENCAS_REGISTRADAS. Retorna {nome_doenca: meta}."""
    resultados = {}
    for fonte_id, indicador, nome_doenca in DOENCAS_REGISTRADAS:
        resultados[nome_doenca] = treinar_modelo_oficial(fonte_id=fonte_id, indicador=indicador)
    return resultados


def _carregar_modelo(indicador="dengue_notificacoes_sinan"):
    model_path = MODEL_PATH if indicador == "dengue_notificacoes_sinan" else _model_path(indicador)
    if not model_path.exists():
        return None
    mtime = model_path.stat().st_mtime
    cache_key = str(model_path)
    cached = _MODELO_CACHE.get(cache_key)
    if cached is not None and cached["mtime"] == mtime:
        return cached["bundle"]
    try:
        bundle = joblib.load(model_path)
    except Exception:
        return None
    _MODELO_CACHE[cache_key] = {"bundle": bundle, "mtime": mtime}
    return bundle


def mapa_risco_oficial_por_estado(fonte_id="sinan_agravos", indicador="dengue_notificacoes_sinan"):
    """
    Retorna {estado: probabilidade_ml} usando a observacao oficial mais
    recente de cada estado coberto pelo modelo treinado. Dict vazio quando
    nao ha modelo treinado (chamador deve usar so a heuristica nesse caso).
    """
    bundle = _carregar_modelo(indicador)
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


def mapa_risco_oficial_por_doenca():
    """
    Retorna {nome_doenca: {estado: probabilidade_ml}} para todas as doencas em
    DOENCAS_REGISTRADAS que tem modelo treinado. Doencas sem modelo treinado
    (poucas amostras oficiais ainda) simplesmente nao aparecem no dict — o
    chamador deve usar a heuristica de sintomas para essas.
    """
    resultado = {}
    for fonte_id, indicador, nome_doenca in DOENCAS_REGISTRADAS:
        mapa = mapa_risco_oficial_por_estado(fonte_id=fonte_id, indicador=indicador)
        if mapa:
            resultado[nome_doenca] = mapa
    return resultado


def modelo_info(fonte_id="sinan_agravos", indicador="dengue_notificacoes_sinan"):
    meta_path = META_PATH if indicador == "dengue_notificacoes_sinan" else _meta_path(indicador)
    if not meta_path.exists():
        return {"modelo_treinado": False}
    with open(meta_path) as f:
        meta = json.load(f)
    if meta.get("fonte_id") != fonte_id or meta.get("indicador") != indicador:
        return {"modelo_treinado": False, "meta_desatualizada_para_outra_fonte": True}
    meta["modelo_treinado"] = True
    return meta
