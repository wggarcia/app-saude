"""
Autorização Clínica com ML Real — Hospital.

Mesmo padrão validado em views_ia_autorizacao_ml.py (Plano de Saúde), adaptado
aos campos de IAAutorizacaoClinica (urgente, tipo_solicitacao, sem TUSS):
  - RandomForestClassifier + GradientBoosting (ensemble)
  - Treino: usa historico de solicitacoes ja revisadas (decisao_final) como
    ground truth; bootstrap sintetico ate acumular 30 decisoes reais.
  - Persistencia: modelo salvo em disco com joblib.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from django.conf import settings

from .models import IAAutorizacaoClinica

# settings.MEDIA_ROOT ja resolve pro disco persistente em produção (Render,
# via MEDIA_ROOT_OVERRIDE) — usar o mesmo caminho evita que o modelo treinado
# seja apagado a cada deploy (BASE_DIR e efemero, recriado do zero no build).
MODELS_DIR = Path(settings.MEDIA_ROOT) / "ml_models" / "autorizacao_hospital"
try:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # build/preDeployCommand do Render roda sem o disco persistente montado
    # (so a instancia em execucao tem /var/data gravavel) — nao pode travar
    # a importacao do modulo so porque esse mkdir falhou nesse contexto.
    pass

# Isolamento por empresa (LGPD): cada tenant treina e usa o PROPRIO modelo,
# persistido em arquivos separados por empresa_id. Nunca ha um modelo clinico
# global compartilhado entre clientes — dado clinico de uma empresa jamais
# influencia a inferencia de outra.
def _paths(empresa_id):
    return (
        MODELS_DIR / f"autorizacao_hospital_model_{empresa_id}.joblib",
        MODELS_DIR / f"autorizacao_hospital_encoder_{empresa_id}.joblib",
        MODELS_DIR / f"autorizacao_hospital_meta_{empresa_id}.json",
    )

THRESHOLD_APROVAR = 0.82
THRESHOLD_NEGAR = 0.80
MIN_AMOSTRAS_TREINO = 30

CIDS_ALTA_COMPLEXIDADE = {
    "C", "D4", "D5", "D6", "D7", "D8",
    "F2", "F3",
    "G30", "G31",
    "I21", "I22",
    "J96",
    "K72",
    "N17", "N18",
}

KEYWORDS_NEGAR = [
    "experimental", "estético", "estetico", "estética", "estetica",
    "cosmético", "cosmetico", "cosmética", "cosmetica",
    "não padronizado", "nao padronizado", "off-label", "off label",
]

FEATURE_NAMES = [
    "alta_complexidade", "cid_preventivo", "urgente", "tipo_internacao",
    "tipo_cirurgia", "tipo_exame_complexidade", "tem_kw_negar", "cid_clinico",
    "historico", "fora_horario",
]


def _extrair_features(dados: dict) -> dict:
    cid = (dados.get("cid10") or "").upper().strip()
    proc = (dados.get("procedimento") or "").lower()
    tipo = (dados.get("tipo_solicitacao") or "").strip()
    urgente = bool(dados.get("urgente"))

    alta_complexidade = int(any(cid.startswith(p) for p in CIDS_ALTA_COMPLEXIDADE))
    cid_preventivo = int(cid.startswith("Z"))
    tem_kw_negar = int(any(k in proc for k in KEYWORDS_NEGAR))
    cid_clinico = int(bool(cid) and cid[0].isalpha() and cid[0] not in "ZVWXY")

    paciente_nome = dados.get("paciente_nome", "")
    empresa_id = dados.get("empresa_id")
    if paciente_nome and empresa_id:
        try:
            historico = int(
                IAAutorizacaoClinica.objects.filter(
                    empresa_id=empresa_id,
                    paciente_nome=paciente_nome,
                    decisao_final="aprovada",
                ).exists()
            )
        except Exception:
            historico = 0
    else:
        historico = 0

    hora_envio = datetime.now().hour
    fora_horario = int(hora_envio < 7 or hora_envio > 22)

    return {
        "alta_complexidade": alta_complexidade,
        "cid_preventivo": cid_preventivo,
        "urgente": int(urgente),
        "tipo_internacao": int(tipo == "internacao"),
        "tipo_cirurgia": int(tipo == "cirurgia"),
        "tipo_exame_complexidade": int(tipo == "exame_alta_complexidade"),
        "tem_kw_negar": tem_kw_negar,
        "cid_clinico": cid_clinico,
        "historico": historico,
        "fora_horario": fora_horario,
    }


def _gerar_dataset_sintetico():
    """Bootstrap baseado em padroes clinicos (urgencia = aprovar, experimental/estetico = negar,
    alta complexidade sem urgencia = revisao) — mesma logica do motor de regras anterior,
    usado so para inicializar o classificador antes de haver decisoes reais suficientes."""
    dados = []
    for cid, tipo in [
        ("Z00", "exame_alta_complexidade"), ("Z01", "procedimento"), ("J18", "internacao"),
        ("I10", "procedimento"), ("K35", "cirurgia"), ("N20", "cirurgia"),
        ("M54", "procedimento"), ("R10", "internacao"), ("K80", "cirurgia"),
    ]:
        dados.append({"cid10": cid, "procedimento": "procedimento clinico padrao", "tipo_solicitacao": tipo, "urgente": False, "paciente_nome": "paciente", "decisao_final": "aprovada"})

    for tipo in ["internacao", "cirurgia", "procedimento"]:
        dados.append({"cid10": "R69", "procedimento": "atendimento urgencia", "tipo_solicitacao": tipo, "urgente": True, "paciente_nome": "paciente", "decisao_final": "aprovada"})

    for cid in ["Z41", "L70", "Z71", "Z09", "M79"]:
        dados.append({"cid10": cid, "procedimento": "tratamento estético rejuvenescimento", "tipo_solicitacao": "procedimento", "urgente": False, "paciente_nome": "", "decisao_final": "negada"})

    for cid in ["C34", "F20", "G30", "I21", "N18"]:
        dados.append({"cid10": cid, "procedimento": "tratamento oncológico especializado de alta complexidade", "tipo_solicitacao": "internacao", "urgente": False, "paciente_nome": "paciente", "decisao_final": "revisao"})

    return dados


def treinar_modelo(empresa_id: int = None):
    # empresa_id e OBRIGATORIO: treinar sem filtro juntaria decisoes clinicas de
    # todas as empresas num unico modelo (pooling cross-tenant / violacao LGPD).
    if not empresa_id:
        raise ValueError(
            "treinar_modelo exige empresa_id: o modelo de autorizacao clinica e "
            "isolado por empresa (LGPD), nunca treinado sobre a base global."
        )

    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import cross_val_score

    qs = IAAutorizacaoClinica.objects.filter(
        decisao_final__isnull=False, empresa_id=empresa_id
    )

    solicitacoes = list(qs.values("cid10", "procedimento", "tipo_solicitacao", "urgente", "paciente_nome", "decisao_final"))

    dataset_sintetico = len(solicitacoes) < MIN_AMOSTRAS_TREINO
    if dataset_sintetico:
        solicitacoes = _gerar_dataset_sintetico()

    X_raw = [_extrair_features(s) for s in solicitacoes]
    X = np.array([[f[n] for n in FEATURE_NAMES] for f in X_raw])
    y_raw = [s["decisao_final"] for s in solicitacoes]

    le = LabelEncoder()
    y = le.fit_transform(y_raw)

    rf = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_split=5, class_weight="balanced", random_state=42, n_jobs=-1)
    gb = GradientBoostingClassifier(n_estimators=150, learning_rate=0.05, max_depth=4, subsample=0.8, random_state=42)
    ensemble = VotingClassifier(estimators=[("rf", rf), ("gb", gb)], voting="soft", weights=[2, 1])
    ensemble.fit(X, y)

    cv_scores = cross_val_score(ensemble, X, y, cv=min(5, len(solicitacoes) // 10 + 2), scoring="f1_weighted")

    model_path, encoder_path, meta_path = _paths(empresa_id)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(ensemble, model_path)
    joblib.dump(le, encoder_path)

    meta = {
        "treinado_em": datetime.now().isoformat(),
        "n_amostras": len(solicitacoes),
        "features": FEATURE_NAMES,
        "classes": le.classes_.tolist(),
        "cv_f1_media": float(cv_scores.mean()),
        "cv_f1_std": float(cv_scores.std()),
        "empresa_id": empresa_id,
        "dataset_sintetico": dataset_sintetico,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


def _carregar_modelo(empresa_id: int):
    # Carrega SEMPRE o modelo da propria empresa. Se ela ainda nao tem modelo,
    # treina um novo (com bootstrap sintetico) exclusivo dela — jamais reaproveita
    # o modelo de outro tenant.
    if not empresa_id:
        raise ValueError("_carregar_modelo exige empresa_id (isolamento por empresa / LGPD).")
    model_path, encoder_path, _ = _paths(empresa_id)
    if not model_path.exists() or not encoder_path.exists():
        treinar_modelo(empresa_id)
    return joblib.load(model_path), joblib.load(encoder_path)


def inferir_autorizacao_clinica(dados: dict) -> dict:
    # Sem empresa_id nao ha isolamento possivel: levanta erro para que o chamador
    # caia no fallback seguro (motor de regras / revisao manual), nunca usando o
    # modelo de outra empresa.
    empresa_id = dados.get("empresa_id")
    if not empresa_id:
        raise ValueError(
            "inferir_autorizacao_clinica exige empresa_id no payload para garantir "
            "isolamento por empresa (LGPD)."
        )
    model, le = _carregar_modelo(empresa_id)
    features = _extrair_features(dados)
    X = np.array([[features[n] for n in FEATURE_NAMES]])

    proba = model.predict_proba(X)[0]
    classes = le.classes_
    scores = {cls: float(p) for cls, p in zip(classes, proba)}
    decisao_idx = int(np.argmax(proba))
    decisao = classes[decisao_idx]
    confianca = float(proba[decisao_idx])

    if decisao == "aprovada" and confianca < THRESHOLD_APROVAR:
        decisao = "revisao"
    elif decisao == "negada" and confianca < THRESHOLD_NEGAR:
        decisao = "revisao"

    justificativa = _gerar_justificativa(features, decisao, scores, dados)

    return {
        "decisao": decisao,
        "score_confianca": round(confianca, 4),
        "scores_por_classe": {k: round(v, 4) for k, v in scores.items()},
        "justificativa_ia": justificativa,
        "features_utilizadas": features,
        "modelo": "Ensemble RF+GB SolusCRT v2",
    }


def _gerar_justificativa(features, decisao, scores, dados):
    motivos = []
    cid = (dados.get("cid10") or "").upper()

    if features["urgente"]:
        motivos.append("Solicitação classificada como urgente — sinal forte de aprovação imediata")
    if features["cid_preventivo"]:
        motivos.append(f"CID {cid} classifica procedimento preventivo (cobertura padrão)")
    if features["alta_complexidade"]:
        motivos.append(f"CID {cid} de alta complexidade clínica — análise criterial aplicada")
    if features["tem_kw_negar"]:
        motivos.append("Procedimento com características estéticas ou experimentais")
    if features["historico"]:
        motivos.append("Paciente com histórico de autorizações aprovadas nesta unidade")
    if features["fora_horario"]:
        motivos.append("Solicitação em horário de urgência/plantão")

    if not motivos:
        motivos.append(f"Análise ML baseada em {len(FEATURE_NAMES)} features clínicas")

    confianca_pct = round(scores.get(decisao, 0) * 100, 1)
    acao = {"aprovada": "Autorização recomendada", "negada": "Negativa recomendada", "revisao": "Encaminhado para revisão médica"}.get(decisao, decisao)
    return f"{acao} (confiança: {confianca_pct}%). " + " | ".join(motivos)
