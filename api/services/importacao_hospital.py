"""
Motor de importação de dados do segmento Hospital — genérico e reutilizável.

Cada "alvo" de importação (IMPORT_TARGETS) declara:
  - label, descrição, ícone
  - campos importáveis (chave, rótulo, tipo, obrigatório, ajuda)
  - chave natural para upsert (evita duplicar ao reimportar)
  - função de persistência de UMA linha já validada

O fluxo (upload → mapear → prévia → processar) vive nas views; aqui está a
regra de negócio de cada alvo e os conversores de tipo. Nada de HTML.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation

# ── conversores de tipo (retornam (valor, erro)) ────────────────────────────────

def _c_texto(v):
    return ("" if v is None else str(v).strip()), None


def _c_texto_maiusc(v):
    return ("" if v is None else str(v).strip().upper()), None


def _c_decimal(v):
    if v in (None, ""):
        return None, None
    s = str(v).strip().replace("R$", "").replace(" ", "")
    # Aceita tanto 1.234,56 (pt-BR) quanto 1234.56 (en).
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
        if d < 0:
            return None, "valor não pode ser negativo"
        return d, None
    except (InvalidOperation, ValueError):
        return None, f"'{v}' não é um número válido"


def _c_inteiro(v):
    if v in (None, ""):
        return None, None
    try:
        n = int(float(str(v).strip().replace(",", ".")))
        if n < 0:
            return None, "valor não pode ser negativo"
        return n, None
    except (TypeError, ValueError):
        return None, f"'{v}' não é um inteiro válido"


def _c_bool(v):
    if v in (None, ""):
        return None, None
    s = str(v).strip().lower()
    if s in ("1", "sim", "s", "true", "verdadeiro", "x", "yes", "y"):
        return True, None
    if s in ("0", "nao", "não", "n", "false", "falso", "no"):
        return False, None
    return None, f"'{v}' não é sim/não"


def _c_cnpj(v):
    if v in (None, ""):
        return "", None
    digitos = "".join(ch for ch in str(v) if ch.isdigit())
    if digitos and len(digitos) != 14:
        return None, f"CNPJ deve ter 14 dígitos (recebido {len(digitos)})"
    return digitos, None


def _c_data(v):
    if v in (None, ""):
        return None, None
    s = str(v).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date(), None
        except ValueError:
            continue
    return None, f"'{v}' não é uma data válida (use AAAA-MM-DD ou DD/MM/AAAA)"


def _c_tipo_opme(v):
    val, _ = _c_texto(v)
    mapa = {
        "protese": "protese", "prótese": "protese", "protése": "protese",
        "ortese": "ortese", "órtese": "ortese",
        "material": "material", "material especial": "material",
        "implante": "implante",
    }
    r = mapa.get(val.lower())
    if not r:
        return None, f"tipo inválido '{v}' (use: prótese, órtese, material ou implante)"
    return r, None


# ── persistência por alvo ───────────────────────────────────────────────────────

def _salvar_catalogo_opme(empresa, dados):
    from api.models import CatalogoOPME
    chave = {"empresa": empresa, "descricao": dados["descricao"]}
    defaults = {k: v for k, v in dados.items() if k != "descricao" and v is not None}
    obj, criado = CatalogoOPME.objects.update_or_create(**chave, defaults=defaults)
    return criado


def _salvar_fornecedor(empresa, dados):
    from api.models import FornecedorHospital
    cnpj = dados.get("cnpj") or ""
    if cnpj:
        chave = {"empresa": empresa, "cnpj": cnpj}
    else:
        chave = {"empresa": empresa, "razao_social": dados["razao_social"]}
    defaults = {k: v for k, v in dados.items() if v is not None}
    defaults.pop("cnpj", None) if cnpj else None
    obj, criado = FornecedorHospital.objects.update_or_create(**chave, defaults=defaults)
    return criado


def _salvar_procedimento_opme(empresa, dados):
    from api.models import OPMEProcedimento
    chave = {"empresa": empresa, "codigo_tuss": dados["codigo_tuss"]}
    defaults = {"descricao": dados.get("descricao", "")}
    obj, criado = OPMEProcedimento.objects.update_or_create(**chave, defaults=defaults)
    return criado


# ── registry ─────────────────────────────────────────────────────────────────────

IMPORT_TARGETS = {
    "catalogo_opme": {
        "label": "Catálogo de OPME (materiais)",
        "descricao": "Órteses, próteses e materiais especiais: descrição, códigos, "
                     "fabricante, preço e grupo de equivalência.",
        "icone": "📦",
        "chave_natural": "descricao",
        "salvar": _salvar_catalogo_opme,
        "campos": [
            {"chave": "descricao", "rotulo": "Descrição", "tipo": "texto",
             "obrigatorio": True, "conv": _c_texto,
             "ajuda": "Nome do material — é a chave: reimportar atualiza o existente."},
            {"chave": "tipo", "rotulo": "Tipo", "tipo": "texto", "obrigatorio": False,
             "conv": _c_tipo_opme, "ajuda": "prótese, órtese, material ou implante"},
            {"chave": "codigo_anvisa", "rotulo": "Código ANVISA", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "codigo_sigtap", "rotulo": "Código SIGTAP", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "codigo_operadora", "rotulo": "Código da Operadora", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "fabricante", "rotulo": "Fabricante", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "preco_maximo", "rotulo": "Preço máximo (R$)", "tipo": "decimal",
             "obrigatorio": False, "conv": _c_decimal},
            {"chave": "grupo_equivalencia", "rotulo": "Grupo de equivalência", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "homologado", "rotulo": "Homologado (sim/não)", "tipo": "bool",
             "obrigatorio": False, "conv": _c_bool},
            {"chave": "preferencial", "rotulo": "Preferencial (sim/não)", "tipo": "bool",
             "obrigatorio": False, "conv": _c_bool},
        ],
    },
    "fornecedor_hospital": {
        "label": "Fornecedores",
        "descricao": "Distribuidores e fabricantes. O CNPJ é conferido contra a base "
                     "de AFE da ANVISA após importar.",
        "icone": "🏭",
        "chave_natural": "cnpj",
        "salvar": _salvar_fornecedor,
        "campos": [
            {"chave": "razao_social", "rotulo": "Razão social", "tipo": "texto",
             "obrigatorio": True, "conv": _c_texto},
            {"chave": "nome_fantasia", "rotulo": "Nome fantasia", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "cnpj", "rotulo": "CNPJ", "tipo": "texto", "obrigatorio": False,
             "conv": _c_cnpj, "ajuda": "14 dígitos — usado para conferir AFE ANVISA."},
            {"chave": "contato", "rotulo": "Contato", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "telefone", "rotulo": "Telefone", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
            {"chave": "email", "rotulo": "E-mail", "tipo": "texto",
             "obrigatorio": False, "conv": _c_texto},
        ],
    },
    "procedimento_opme": {
        "label": "Procedimentos padronizados (TUSS)",
        "descricao": "Códigos de procedimento. Os materiais permitidos de cada um são "
                     "vinculados depois, na tela de Procedimentos.",
        "icone": "🧭",
        "chave_natural": "codigo_tuss",
        "salvar": _salvar_procedimento_opme,
        "campos": [
            {"chave": "codigo_tuss", "rotulo": "Código TUSS", "tipo": "texto",
             "obrigatorio": True, "conv": _c_texto},
            {"chave": "descricao", "rotulo": "Descrição", "tipo": "texto",
             "obrigatorio": True, "conv": _c_texto},
        ],
    },
}


def target_ou_none(chave):
    return IMPORT_TARGETS.get(chave)


def validar_linha(target, linha_bruta, mapeamento):
    """Aplica o mapeamento e os conversores a UMA linha do arquivo.
    Retorna (dados_validados: dict, erros: list[str])."""
    dados, erros = {}, []
    for campo in target["campos"]:
        col = mapeamento.get(campo["chave"])
        if not col:
            # Campo não mapeado: erro só se for obrigatório; senão ignora.
            if campo["obrigatorio"]:
                erros.append(f"{campo['rotulo']} é obrigatório")
            continue
        bruto = linha_bruta.get(col)
        valor, erro = campo["conv"](bruto)
        if erro:
            erros.append(f"{campo['rotulo']}: {erro}")
            continue
        if campo["obrigatorio"] and (valor is None or valor == ""):
            erros.append(f"{campo['rotulo']} é obrigatório")
            continue
        if valor is not None and valor != "":
            dados[campo["chave"]] = valor
    return dados, erros
