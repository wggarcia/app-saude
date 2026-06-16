"""
utils_ia.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Interface principal da IA — usada por todos os ambientes do ecossistema.

• Delega classificação para classificador_doencas.py
• Cada setor vê APENAS o que é relevante para ele
• Sem mistura entre contextos de setores diferentes
• Ponto único para classificar registros individuais e populações
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

from .classificador_doencas import (
    DOENCAS_BRASIL,
    TODOS_SINTOMAS,
    CAMPOS_ANAMNESE,
    URGENCIA_ABSOLUTA,
    classificar,
    classificar_para_cidadao,
    analisar_populacao,
    calibrar_pesos_feedback,
    sintomas_do_registro,
    CONTEXTO_SETOR,
    SINDROME_CIDADAO,
)


# ──────────────────────────────────────────────────────────────────────────────
# API PÚBLICA — usada pelos ambientes do ecossistema
# ──────────────────────────────────────────────────────────────────────────────

def classificar_padrao(dados: dict, setor: str = "governo") -> dict:
    """
    Classifica um conjunto de sintomas no contexto de um setor específico.

    Substitui a versão anterior (3 campos → resultado simplista).
    Agora usa 19 campos de sintoma + diagnóstico diferencial completo.

    Parâmetros:
        dados:  dict com campos bool de sintomas (febre, tosse, dor_corpo, cansaco,
                falta_ar, dor_cabeca, dor_articular, exantema, conjuntivite,
                vomito_nausea, diarreia, dor_abdominal, rigidez_nuca, ictericia,
                manchas_hemorragicas, perda_olfato_paladar, dor_garganta, coriza,
                calafrios) + intensidade_febre + intensidade_articular
        setor:  'governo' | 'farmacia' | 'hospital' | 'plano_saude' | 'rede' | 'empresa' | 'sst'

    Retorna: resultado completo do classificador (dict)
    """
    return classificar(dados, setor=setor)


def classificar_registro(registro, setor: str = "governo") -> dict:
    """
    Classifica um objeto RegistroSintoma do Django diretamente.
    Extrai automaticamente todos os campos do modelo.
    """
    dados = sintomas_do_registro(registro)
    return classificar(dados, setor=setor)


def analisar_populacao_setor(registros_qs, setor: str = "governo") -> dict:
    """
    Analisa um QuerySet de RegistroSintoma e retorna perfil epidemiológico
    agregado para o setor informado.

    Cada setor recebe apenas o contexto relevante para ele.
    """
    return analisar_populacao(registros_qs, setor=setor)


def classificar_cidadao(dados: dict, estado: str | None = None) -> dict:
    """
    Classificação para exibição ao cidadão no app móvel.
    Retorna síndrome genérica (não nome de doença rara) + conduta.
    Usa prior geográfico bayesiano para evitar falsos alarmes como
    "Febre Amarela" em área sem prevalência.
    """
    return classificar_para_cidadao(dados, estado=estado)


def verificar_urgencias(dados: dict) -> list[dict]:
    """
    Verifica flags de urgência absoluta independentemente do score.
    Retorna lista de urgências presentes (pode estar vazia).
    """
    urgencias = []
    for campo, titulo, descricao in URGENCIA_ABSOLUTA:
        if dados.get(campo):
            urgencias.append({"campo": campo, "titulo": titulo, "descricao": descricao})
    return urgencias


def obter_contexto_setor(setor: str) -> dict:
    """Retorna o contexto/perfil do setor para orientar ações."""
    return CONTEXTO_SETOR.get(setor, CONTEXTO_SETOR["governo"])


def listar_doencas() -> list[dict]:
    """Lista todas as doenças modeladas com metadados básicos."""
    return [
        {
            "nome": nome,
            "grupo": info["grupo"],
            "cid10": info.get("cid10", ""),
            "vetor": info.get("vetor", ""),
            "descricao": info["descricao"],
        }
        for nome, info in DOENCAS_BRASIL.items()
    ]


def listar_sintomas() -> list[str]:
    """Retorna lista de todos os campos de sintoma disponíveis."""
    return list(TODOS_SINTOMAS)


def relatorio_calibracao(registros_confirmados_qs) -> dict:
    """
    Gera relatório de calibração da IA comparando previsões com diagnósticos confirmados.
    Retorna métricas de acurácia e pares de confusão mais frequentes.
    """
    return calibrar_pesos_feedback(registros_confirmados_qs)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS PARA TEMPLATES E SERIALIZERS
# ──────────────────────────────────────────────────────────────────────────────

def resumo_classificacao(dados: dict, setor: str = "governo") -> dict:
    """
    Versão compacta para uso em listas/tabelas (apenas campos essenciais).
    """
    resultado = classificar(dados, setor=setor)
    return {
        "primario": resultado["primario"],
        "grupo": resultado["grupo"],
        "confianca": resultado["confianca"],
        "confianca_label": _label_confianca(resultado["confianca"]),
        "red_flags": resultado["red_flags"],
        "urgencia": len(resultado["urgencia_absoluta"]) > 0,
        "sintomas_count": resultado["sintomas_count"],
    }


def _label_confianca(pct: int) -> str:
    if pct >= 80:
        return "Alta"
    if pct >= 60:
        return "Moderada"
    if pct >= 40:
        return "Baixa"
    return "Inconclusiva"
