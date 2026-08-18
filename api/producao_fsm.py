"""
producao_fsm.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Máquina de estados da Ordem de Produção Industrial.

Impõe a regra central do desafio: uma ordem só avança se a etapa atual está
COMPLETA, VÁLIDA e ASSINADA. Sem gate, o software original deixava o status
pular direto para o fim — aqui cada transição passa por uma guarda.

Dois níveis:
  1. Etapas da LINHA (etapa_atual): pesagem → granulação → … → embalagem.
     Cada etapa exige campos válidos + assinatura do papel definido no MBR.
  2. Status MACRO do lote: rascunho → em_produção → CQ → revisão GQ → liberado.

Não toca no banco: recebe os dados já carregados e devolve (permitido, motivo).
Quem persiste é a view, dentro de transaction.atomic().
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

from . import producao_validacao as val


# Transições de status macro permitidas.
TRANSICOES = {
    "rascunho":           ["em_producao", "cancelado"],
    "em_producao":        ["controle_qualidade", "rejeitado", "cancelado"],
    "controle_qualidade": ["revisao_qualidade", "rejeitado"],
    "revisao_qualidade":  ["liberado", "rejeitado"],
    "liberado":           [],
    "rejeitado":          [],
    "cancelado":          [],
}


def transicoes_permitidas(status: str) -> list:
    return TRANSICOES.get(status, [])


def _papel_da_etapa(especificacao, etapa_chave: str) -> str:
    for e in especificacao.lista_etapas():
        if str(e.get("chave")) == str(etapa_chave):
            return e.get("papel_assina") or "operador"
    return "operador"


def _proxima_etapa(especificacao, etapa_atual: str):
    etapas = especificacao.lista_etapas()
    chaves = [e.get("chave") for e in etapas]
    if not chaves:
        return None
    if not etapa_atual:
        return chaves[0]
    if etapa_atual in chaves:
        idx = chaves.index(etapa_atual)
        if idx + 1 < len(chaves):
            return chaves[idx + 1]
    return None  # já na última


def etapa_esta_pronta(especificacao, etapa_chave, registros_por_chave,
                      assinaturas_set) -> tuple[bool, list]:
    """
    Uma etapa está pronta para ser fechada quando:
      • todos os campos obrigatórios estão preenchidos e válidos; e
      • existe assinatura do papel exigido para a etapa.

    assinaturas_set: set de (etapa, papel) já assinados.
    Retorna (pronta: bool, motivos: [str]).
    """
    motivos = []
    check = val.validar_etapa(especificacao, registros_por_chave, etapa_chave)
    if check["faltando"]:
        motivos.append("Campos obrigatórios pendentes: " + ", ".join(check["faltando"]))
    if check["com_erro"]:
        motivos.extend(check["com_erro"])

    papel = _papel_da_etapa(especificacao, etapa_chave)
    if (etapa_chave, papel) not in assinaturas_set:
        motivos.append(f"Falta assinatura do responsável ({papel}) desta etapa.")

    return (len(motivos) == 0, motivos)


def pode_avancar_etapa(ordem, especificacao, registros_por_chave,
                       assinaturas_set) -> dict:
    """
    Avaliação para avançar da etapa_atual para a próxima etapa da linha.

    Retorna:
      {"permitido": bool, "motivos": [str], "proxima_etapa": str|None,
       "ultima": bool}   # ultima=True → não há próxima; pronto para ir ao CQ
    """
    etapa_atual = ordem.etapa_atual or (
        especificacao.lista_etapas()[0].get("chave")
        if especificacao.lista_etapas() else ""
    )
    pronta, motivos = etapa_esta_pronta(
        especificacao, etapa_atual, registros_por_chave, assinaturas_set)

    proxima = _proxima_etapa(especificacao, etapa_atual)
    return {
        "permitido": pronta,
        "motivos": motivos,
        "proxima_etapa": proxima,
        "ultima": proxima is None,
        "etapa_avaliada": etapa_atual,
    }


def pode_transicionar_status(ordem, especificacao, novo_status, contexto: dict) -> dict:
    """
    Guarda de transição de status macro.

    contexto pode conter:
      • registros_por_chave: {chave: valor} de toda a ordem
      • assinaturas_set: set de (etapa, papel)
      • tem_desvio_critico_aberto: bool
      • rendimento: resultado de validar_rendimento (para CQ→revisão)
      • assinou_qa: bool (para revisão→liberado)
      • motivo: str (para rejeitado)

    Retorna {"permitido": bool, "motivos": [str]}.
    """
    atual = ordem.status
    if novo_status not in transicoes_permitidas(atual):
        return {"permitido": False,
                "motivos": [f"Transição inválida: {atual} → {novo_status}."]}

    motivos = []

    # Rejeição e cancelamento são sempre permitidos (com motivo), a título de
    # segurança — nunca se deve travar a rejeição de um lote problemático.
    if novo_status in ("rejeitado", "cancelado"):
        if not contexto.get("motivo"):
            motivos.append("Informe o motivo da rejeição/cancelamento.")
        return {"permitido": not motivos, "motivos": motivos}

    if contexto.get("tem_desvio_critico_aberto") and novo_status != "rejeitado":
        motivos.append("Há desvio CRÍTICO em aberto — resolva antes de avançar.")

    # rascunho → em_producao
    if atual == "rascunho" and novo_status == "em_producao":
        if not especificacao.lista_etapas():
            motivos.append("A especificação não define etapas de produção.")
        if not ordem.numero_lote_fabricacao:
            motivos.append("Informe o lote de fabricação antes de iniciar.")
        if not ordem.tamanho_lote or float(ordem.tamanho_lote) <= 0:
            motivos.append("Informe o tamanho do lote antes de iniciar.")

    # em_producao → controle_qualidade: TODAS as etapas prontas
    elif atual == "em_producao" and novo_status == "controle_qualidade":
        registros = contexto.get("registros_por_chave", {})
        assinaturas = contexto.get("assinaturas_set", set())
        for e in especificacao.lista_etapas():
            chave = e.get("chave")
            pronta, ms = etapa_esta_pronta(especificacao, chave, registros, assinaturas)
            if not pronta:
                rotulo = e.get("rotulo") or chave
                motivos.append(f"Etapa '{rotulo}' não concluída: " + "; ".join(ms))

    # controle_qualidade → revisao_qualidade: rendimento e CQ ok
    elif atual == "controle_qualidade" and novo_status == "revisao_qualidade":
        rend = contexto.get("rendimento")
        if rend and rend.get("aplicavel") and not rend.get("dentro_faixa"):
            motivos.append(rend.get("mensagem", "Rendimento fora da faixa."))
        # Verifica o campo cq_aprovado diretamente na ordem (campo real, não contexto efêmero).
        if ordem.cq_aprovado is None:
            motivos.append("Registre as medições de CQ antes de avançar para revisão.")
        elif not ordem.cq_aprovado:
            motivos.append("CQ reprovado — registre desvio, resolva CAPA e reregistre o CQ.")

    # revisao_qualidade → liberado: assinatura da GQ
    elif atual == "revisao_qualidade" and novo_status == "liberado":
        if not contexto.get("assinou_qa"):
            motivos.append("A liberação exige assinatura do farmacêutico/GQ.")
        if contexto.get("tem_desvio_critico_aberto"):
            motivos.append("Não é possível liberar com desvio crítico em aberto.")

    return {"permitido": len(motivos) == 0, "motivos": motivos}
