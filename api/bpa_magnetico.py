"""
bpa_magnetico.py
Geração do arquivo BPA-Magnético (SIA/SUS) — layout DATASUS.

Produz um arquivo texto de largura fixa com:
  - Registro 01  — Header (cabeçalho do lote)
  - Registro 02  — BPA-C (Boletim de Produção Ambulatorial Consolidado)
  - Registro 03  — BPA-I (Boletim de Produção Ambulatorial Individualizado)

Referência do layout: SIA/SUS — "BPA - Layout de Importação" (DATASUS).
Este módulo NÃO faz transmissão; apenas gera o arquivo para importação no
aplicativo BPA-Magnético / envio ao SIA. A transmissão eletrônica ao SISAB/
DATASUS permanece em views_governo_faturamento.py.

Campos que dependem de cadastro completo (quando ausentes, usam default seguro):
  - CNPJ do órgão gerador  → zeros (configurar em CredenciaisIntegracoes)
  - Código IBGE do município → zeros (preencher no cadastro da empresa)
  - CNS do profissional / paciente → brancos quando não cadastrados
Esses defaults não impedem a leitura do arquivo, mas devem ser preenchidos
para validação plena na importação do SIA.
"""
from datetime import date


# ── Helpers de formatação de campo ─────────────────────────────────────────────

def _txt(valor, tamanho):
    """Alfanumérico: alinhado à esquerda, preenchido com espaços à direita."""
    s = "" if valor is None else str(valor)
    s = _sem_acento(s).upper()
    return s[:tamanho].ljust(tamanho)


def _num(valor, tamanho):
    """Numérico: alinhado à direita, preenchido com zeros à esquerda."""
    try:
        s = str(int(valor))
    except (TypeError, ValueError):
        s = "0"
    return s[-tamanho:].rjust(tamanho, "0")


def _sem_acento(s):
    tabela = str.maketrans(
        "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇáàâãäéèêëíìîïóòôõöúùûüç",
        "AAAAAEEEEIIIIOOOOOUUUUCaaaaaeeeeiiiiooooouuuuc",
    )
    return s.translate(tabela)


def _campo_controle(qtd_linhas, qtd_folhas):
    """
    Campo de controle do header BPA (4 dígitos):
    ((total de linhas + total de folhas) módulo 1111) + 1111.
    """
    return _num(((qtd_linhas + qtd_folhas) % 1111) + 1111, 4)


def _idade(data_nascimento, data_ref):
    if not data_nascimento:
        return 0
    anos = data_ref.year - data_nascimento.year - (
        (data_ref.month, data_ref.day) < (data_nascimento.month, data_nascimento.day)
    )
    return max(0, min(anos, 130))


# ── Registros ───────────────────────────────────────────────────────────────

LINHAS_POR_FOLHA = 20  # padrão BPA


def _header(competencia, qtd_linhas, orgao_origem, sigla_origem, cnpj,
            orgao_destino, indicador_destino, versao):
    qtd_folhas = max(1, -(-qtd_linhas // LINHAS_POR_FOLHA))  # ceil
    return (
        "01"
        + "#BPA#"
        + _num(competencia, 6)
        + _num(qtd_linhas, 6)
        + _num(qtd_folhas, 6)
        + _campo_controle(qtd_linhas, qtd_folhas)
        + _txt(orgao_origem, 30)
        + _txt(sigla_origem, 6)
        + _num("".join(c for c in (cnpj or "") if c.isdigit()) or 0, 14)
        + _txt(orgao_destino, 40)
        + _txt(indicador_destino, 1)
        + _txt(versao, 10)
    )


def _linha_bpa_c(cnes, competencia, cbo, folha, seq, procedimento, idade, quantidade):
    return (
        "02"
        + _num(cnes, 7)
        + _num(competencia, 6)
        + _txt(cbo, 6)
        + _num(folha, 3)
        + _num(seq, 2)
        + _num(procedimento, 10)
        + _num(idade, 3)
        + _num(quantidade, 6)
        + _txt("EXT", 3)
    )


def _linha_bpa_i(cnes, competencia, cns_prof, cbo, data_atend, folha, seq,
                 procedimento, cns_pac, sexo, ibge, cid, idade, quantidade,
                 carater, autorizacao, nome_pac, data_nasc):
    return (
        "03"
        + _num(cnes, 7)
        + _num(competencia, 6)
        + _txt(cns_prof, 15)
        + _txt(cbo, 6)
        + _num(data_atend.strftime("%Y%m%d") if data_atend else 0, 8)
        + _num(folha, 3)
        + _num(seq, 2)
        + _num(procedimento, 10)
        + _txt(cns_pac, 15)
        + _txt(sexo or "M", 1)
        + _num(ibge, 6)
        + _txt(cid, 4)
        + _num(idade, 3)
        + _num(quantidade, 6)
        + _num(carater or 1, 2)
        + _txt(autorizacao, 13)
        + _txt("BPA", 3)
        + _txt(nome_pac, 30)
        + _num(data_nasc.strftime("%Y%m%d") if data_nasc else 0, 8)
    )


# ── Geração do arquivo ────────────────────────────────────────────────────────

def gerar_arquivo_bpa(*, competencia, cnes, atendimentos, orgao_origem,
                      sigla_origem="", cnpj="", orgao_destino="SECRETARIA MUNICIPAL DE SAUDE",
                      indicador_destino="M", codigo_ibge="", versao="SOLOCRT"):
    """
    Gera o conteúdo (str) do arquivo BPA-Magnético.

    Parâmetros:
      competencia   AAAAMM (str)
      cnes          CNES do estabelecimento (str/num)
      atendimentos  iterável de objetos AtendimentoUBS (com FK prontuario opcional)
      orgao_origem  nome da secretaria/prefeitura

    Retorna dict: {"conteudo": str, "linhas": int, "bpa_i": int, "bpa_c": int}
    """
    try:
        ano = int(competencia[:4])
        mes = int(competencia[4:6])
        data_ref = date(ano, mes, 1)
    except (ValueError, IndexError):
        data_ref = date.today()

    linhas_i = []
    consolidado = {}  # (cbo, procedimento, idade) -> quantidade

    folha = 1
    seq = 1
    for at in atendimentos:
        procedimento = (getattr(at, "procedimento_ab", "") or "").strip()
        if not procedimento:
            continue  # sem procedimento não entra no BPA

        pront = getattr(at, "prontuario", None)
        sexo = getattr(pront, "sexo", "") if pront else ""
        data_nasc = getattr(pront, "data_nascimento", None) if pront else None
        cns_pac = (getattr(at, "cns", "") or (getattr(pront, "cns", "") if pront else "")).strip()
        idade = _idade(data_nasc, data_ref)

        linhas_i.append(_linha_bpa_i(
            cnes=cnes, competencia=competencia,
            cns_prof="", cbo=getattr(at, "cbo", "") or "",
            data_atend=getattr(at, "data_atendimento", None),
            folha=folha, seq=seq, procedimento=procedimento,
            cns_pac=cns_pac, sexo=sexo, ibge=codigo_ibge,
            cid=(getattr(at, "cid10", "") or "").replace(".", ""),
            idade=idade, quantidade=1, carater=1, autorizacao="",
            nome_pac=getattr(at, "paciente_nome", "") or "",
            data_nasc=data_nasc,
        ))

        chave = (getattr(at, "cbo", "") or "", procedimento, idade)
        consolidado[chave] = consolidado.get(chave, 0) + 1

        seq += 1
        if seq > LINHAS_POR_FOLHA:
            seq = 1
            folha += 1

    # BPA-C consolidado
    linhas_c = []
    folha_c = 1
    seq_c = 1
    for (cbo, proc, idade), qtd in sorted(consolidado.items()):
        linhas_c.append(_linha_bpa_c(
            cnes=cnes, competencia=competencia, cbo=cbo,
            folha=folha_c, seq=seq_c, procedimento=proc, idade=idade, quantidade=qtd,
        ))
        seq_c += 1
        if seq_c > LINHAS_POR_FOLHA:
            seq_c = 1
            folha_c += 1

    total_linhas = len(linhas_i) + len(linhas_c)
    header = _header(
        competencia=competencia, qtd_linhas=total_linhas,
        orgao_origem=orgao_origem, sigla_origem=sigla_origem, cnpj=cnpj,
        orgao_destino=orgao_destino, indicador_destino=indicador_destino, versao=versao,
    )

    conteudo = "\r\n".join([header] + linhas_c + linhas_i) + "\r\n"
    return {
        "conteudo": conteudo,
        "linhas": total_linhas,
        "bpa_i": len(linhas_i),
        "bpa_c": len(linhas_c),
    }
