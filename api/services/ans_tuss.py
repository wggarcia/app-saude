"""
Cliente da API oficial da ANS — Terminologia Unificada da Saúde Suplementar (TUSS).

Fonte (dados abertos, sem autenticação), citada na página "Códigos da TUSS" do
gov.br/ans → serviço OpenConceptLab (OCL) da ANS:
  base: https://consulta-ocl.apps.sa-1a.mendixcloud.com/rest/oclservice/ANS
  - GET /source                          → lista as 63 tabelas TUSS
  - GET /concepts/{tabela}?page=N&q=termo → itens (25/página), com `extras`

Cada item vem como:
  {"id": "<código TUSS>", "display_name": "<descrição>", "source": "tuss-19",
   "extras": {"registro_anvisa": ..., "fabricante": ..., "classe_risco": ...,
              "inicio_vigencia": "YYYY-MM-DD", "fim_vigencia": "-"|"YYYY-MM-DD", ...}}

Nada aqui grava no banco — só fala com a API e devolve dicts normalizados. Quem
persiste é o command `sync_ans_tuss`. Assim a mesma camada serve tanto para a
busca ao vivo (fallback da tela) quanto para o sync mensal.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

BASE_URL = "https://consulta-ocl.apps.sa-1a.mendixcloud.com/rest/oclservice/ANS"
PAGE_SIZE = 25          # a API devolve 25 itens por página
TIMEOUT = 40

# Rótulos amigáveis das tabelas que o módulo Hospital usa de fato.
TABELAS_RELEVANTES = {
    "tuss-19": "Materiais, Órteses, Próteses e Materiais Especiais (OPME)",
    "tuss-22": "Procedimentos em saúde",
    "tuss-20": "Medicamentos",
    "tuss-18": "Diárias, taxas e gases medicinais",
    "tuss-64": "Forma de envio de procedimentos e itens à ANS",
}


def _sessao():
    import requests
    return requests.Session()


def _data(s):
    s = (s or "").strip()
    if not s or s == "-":
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _normalizar(item):
    """API OCL → dict achatado, no vocabulário do nosso modelo TerminologiaTuss."""
    extras = item.get("extras") or {}
    fim = _data(extras.get("fim_vigencia"))
    # `fabricante` (OPME) e `laboratorio` (medicamento) são o mesmo campo p/ nós.
    fabricante = (extras.get("fabricante") or extras.get("laboratorio") or "").strip()
    return {
        "tabela": (item.get("source") or "").strip(),
        "codigo": str(item.get("id") or "").strip(),
        "descricao": (item.get("display_name") or "").strip()[:400],
        "registro_anvisa": "".join(
            ch for ch in (extras.get("registro_anvisa") or "") if ch.isdigit())[:20],
        "fabricante": fabricante[:250],
        "classe_risco": (extras.get("classe_risco") or "").strip()[:8],
        "apresentacao": (extras.get("apresentacao") or "").strip()[:250],
        "modelo": (extras.get("modelo") or "").strip()[:250],
        "inicio_vigencia": _data(extras.get("inicio_vigencia")),
        "fim_vigencia": fim,
        "vigente": fim is None,
    }


def listar_tabelas():
    """GET /source — devolve [{codigo, descricao, total}] das tabelas TUSS."""
    sess = _sessao()
    resp = sess.get(f"{BASE_URL}/source", timeout=TIMEOUT)
    resp.raise_for_status()
    return [
        {"codigo": t.get("Codigo"), "descricao": t.get("Descricao"),
         "total": t.get("Total_sources")}
        for t in resp.json()
    ]


def buscar_pagina(tabela, termo="", page=1):
    """GET /concepts/{tabela}?page=N&q=termo — uma página normalizada."""
    sess = _sessao()
    params = {"page": page}
    if termo:
        params["q"] = termo
    resp = sess.get(f"{BASE_URL}/concepts/{tabela}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    dados = resp.json()
    if not isinstance(dados, list):
        return []
    return [_normalizar(x) for x in dados]


def buscar_ao_vivo(tabela, termo, limite=25):
    """Busca ao vivo na ANS (usada como fallback quando o item não está no espelho
    local). Devolve até `limite` itens já normalizados. Erros de rede são engolidos
    com log — o chamador trata lista vazia."""
    try:
        itens, page = [], 1
        while len(itens) < limite and page <= 4:
            pagina = buscar_pagina(tabela, termo, page)
            if not pagina:
                break
            itens.extend(pagina)
            if len(pagina) < PAGE_SIZE:
                break
            page += 1
        return itens[:limite]
    except Exception as e:  # rede/timeout/5xx — não derruba a tela
        logger.warning("ANS buscar_ao_vivo(%s, %r) falhou: %s", tabela, termo, e)
        return []


def iterar_tabela(tabela, termo="", max_paginas=0):
    """Gera itens normalizados paginando a tabela inteira (ou até `max_paginas`).
    Usado pelo sync. `max_paginas=0` = sem limite (cuidado com tuss-19: 1,4M)."""
    page = 1
    while True:
        if max_paginas and page > max_paginas:
            return
        pagina = buscar_pagina(tabela, termo, page)
        if not pagina:
            return
        for item in pagina:
            yield item
        if len(pagina) < PAGE_SIZE:
            return
        page += 1
