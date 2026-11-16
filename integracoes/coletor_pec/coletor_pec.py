#!/usr/bin/env python3
"""
Coletor PEC → SoloCRT: lê as visitas domiciliares do banco do PEC (e-SUS APS)
em modo somente leitura e envia em lotes para a API de ingestão do SoloCRT.

Roda na rede da prefeitura, ao lado do PEC. Ver README.md desta pasta.

ATENÇÃO: os nomes de tabela/coluna do PEC abaixo NÃO foram validados num PEC
real — variam por versão. Rode --diagnostico antes da primeira coleta.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime

TABELA_FATO = "tb_fat_visita_domiciliar"

# Campo lógico → (tabela, colunas candidatas em ordem de preferência).
# Fato: tb_fat_visita_domiciliar. Dimensões ligadas por FK co_dim_*.
CANDIDATOS = {
    "pk":           (TABELA_FATO, ["co_seq_fat_visita_domiciliar", "co_seq_fat_visita_domic"]),
    "uuid":         (TABELA_FATO, ["nu_uuid_ficha", "uuid_ficha", "nu_uuid_dado_transp"]),
    "fk_prof":      (TABELA_FATO, ["co_dim_profissional"]),
    "fk_unidade":   (TABELA_FATO, ["co_dim_unidade_saude"]),
    "fk_equipe":    (TABELA_FATO, ["co_dim_equipe"]),
    "fk_tempo":     (TABELA_FATO, ["co_dim_tempo"]),
    "turno":        (TABELA_FATO, ["co_dim_turno", "co_turno"]),
    "desfecho":     (TABELA_FATO, ["co_dim_desfecho_visita", "co_desfecho_visita", "co_desfecho"]),
    "motivos":      (TABELA_FATO, ["ds_filtro_motivo_visita", "ds_motivo_visita"]),
    "microarea":    (TABELA_FATO, ["nu_micro_area", "nu_microarea"]),
    "cns_cidadao":  (TABELA_FATO, ["nu_cns", "nu_cns_cidadao"]),
    "cpf_cidadao":  (TABELA_FATO, ["nu_cpf_cidadao", "nu_cpf"]),
    "peso":         (TABELA_FATO, ["nu_peso"]),
    "data_direta":  (TABELA_FATO, ["dt_visita", "dt_registro"]),
    "prof_pk":      ("tb_dim_profissional", ["co_seq_dim_profissional"]),
    "prof_cns":     ("tb_dim_profissional", ["nu_cns"]),
    "prof_nome":    ("tb_dim_profissional", ["no_profissional"]),
    "unidade_pk":   ("tb_dim_unidade_saude", ["co_seq_dim_unidade_saude"]),
    "unidade_cnes": ("tb_dim_unidade_saude", ["nu_cnes"]),
    "equipe_pk":    ("tb_dim_equipe", ["co_seq_dim_equipe"]),
    "equipe_ine":   ("tb_dim_equipe", ["nu_ine"]),
    "tempo_pk":     ("tb_dim_tempo", ["co_seq_dim_tempo"]),
    "tempo_data":   ("tb_dim_tempo", ["dt_registro"]),
}

_IDENT = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def mapear_colunas(colunas_por_tabela):
    """Recebe {tabela: {colunas}} do information_schema e devolve
    (mapa {campo: (tabela, coluna)}, faltando [campos obrigatórios ausentes])."""
    mapa = {}
    for campo, (tabela, candidatas) in CANDIDATOS.items():
        existentes = colunas_por_tabela.get(tabela, set())
        achada = next((c for c in candidatas if c in existentes and _IDENT.match(c)), None)
        if achada:
            mapa[campo] = (tabela, achada)

    faltando = [c for c in ("pk", "fk_prof", "prof_pk", "prof_cns") if c not in mapa]
    tem_data = "data_direta" in mapa or all(k in mapa for k in ("fk_tempo", "tempo_pk", "tempo_data"))
    if not tem_data:
        faltando.append("data da visita (dt_visita ou co_dim_tempo + tb_dim_tempo.dt_registro)")
    return mapa, faltando


def montar_sql(mapa):
    """SELECT só com as colunas encontradas; identificadores vêm do catálogo e
    passam por _IDENT, valores vão por parâmetro."""
    def col(alias, campo):
        return f'{alias}."{mapa[campo][1]}"'

    sel = [f"{col('f', 'pk')} AS pk", f"{col('p', 'prof_cns')} AS acs_cns"]
    joins = [f'JOIN "tb_dim_profissional" p ON p."{mapa["prof_pk"][1]}" = {col("f", "fk_prof")}']
    if "prof_nome" in mapa:
        sel.append(f"{col('p', 'prof_nome')} AS acs_nome")
    for campo in ("uuid", "turno", "desfecho", "motivos", "microarea", "cns_cidadao", "cpf_cidadao", "peso"):
        if campo in mapa:
            sel.append(f"{col('f', campo)} AS {campo}")
    if "data_direta" in mapa:
        sel.append(f"{col('f', 'data_direta')} AS data_visita")
    else:
        joins.append(f'JOIN "tb_dim_tempo" t ON t."{mapa["tempo_pk"][1]}" = {col("f", "fk_tempo")}')
        sel.append(f"{col('t', 'tempo_data')} AS data_visita")
    if all(k in mapa for k in ("fk_unidade", "unidade_pk", "unidade_cnes")):
        joins.append(f'LEFT JOIN "tb_dim_unidade_saude" u ON u."{mapa["unidade_pk"][1]}" = {col("f", "fk_unidade")}')
        sel.append(f"{col('u', 'unidade_cnes')} AS cnes")
    if all(k in mapa for k in ("fk_equipe", "equipe_pk", "equipe_ine")):
        joins.append(f'LEFT JOIN "tb_dim_equipe" e ON e."{mapa["equipe_pk"][1]}" = {col("f", "fk_equipe")}')
        sel.append(f"{col('e', 'equipe_ine')} AS ine")
    return (f'SELECT {", ".join(sel)} FROM "{TABELA_FATO}" f {" ".join(joins)} '
            f"WHERE {col('f', 'pk')} > %s ORDER BY {col('f', 'pk')} LIMIT %s")


def _digitos(v, tamanho):
    s = re.sub(r"\D", "", str(v or ""))
    return s if len(s) == tamanho else None


def _int_ou_none(v, validos):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n in validos else None


def linha_para_item(linha):
    """Converte uma linha do SELECT no formato da API de ingestão. Devolve None
    se faltar o mínimo (CNS do ACS válido ou data)."""
    acs_cns = _digitos(linha.get("acs_cns"), 15)
    data_visita = linha.get("data_visita")
    if isinstance(data_visita, datetime):
        data_visita = data_visita.date()
    if not acs_cns or not isinstance(data_visita, date):
        return None

    cnes = _digitos(linha.get("cnes"), 7)
    uuid = str(linha.get("uuid") or "").strip()
    if not re.match(r"^[A-Za-z0-9:._-]{1,64}$", uuid):
        uuid = f"pec:{cnes or 'sem-cnes'}:{linha['pk']}"

    motivos = [int(m) for m in re.findall(r"\d+", str(linha.get("motivos") or ""))]
    item = {
        "uuid_origem": uuid,
        "acs_cns": acs_cns,
        "data_visita": data_visita.isoformat(),
        "motivos": motivos,
    }
    opcionais = {
        "acs_nome": (str(linha.get("acs_nome") or "").strip()[:160] or None),
        "cnes": cnes,
        "ine": _digitos(linha.get("ine"), 10),
        "microarea": (str(linha.get("microarea") or "").strip()[:10] or None),
        "turno": _int_ou_none(linha.get("turno"), {1, 2, 3}),
        "desfecho": _int_ou_none(linha.get("desfecho"), {1, 2, 3}),
        "cns_paciente": _digitos(linha.get("cns_cidadao"), 15),
        "cpf_paciente": _digitos(linha.get("cpf_cidadao"), 11),
    }
    try:
        peso = float(linha["peso"]) if linha.get("peso") is not None else None
        if peso is not None and 0 < peso <= 500:
            opcionais["peso_kg"] = peso
    except (TypeError, ValueError):
        pass
    item.update({k: v for k, v in opcionais.items() if v is not None})
    return item


# ── Banco do PEC e API ────────────────────────────────────────────────────────

def conectar(dsn):
    try:
        import psycopg
        conn = psycopg.connect(dsn, autocommit=True)
        conn.read_only = True
        return conn
    except ImportError:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.set_session(readonly=True, autocommit=True)
        return conn


def ler_schema(conn):
    tabelas = sorted({t for t, _ in CANDIDATOS.values()})
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name, column_name FROM information_schema.columns WHERE table_name = ANY(%s)",
        (tabelas,),
    )
    schema = {}
    for tabela, coluna in cur.fetchall():
        schema.setdefault(tabela, set()).add(coluna)
    return schema


def ler_lote(conn, sql, ultimo_pk, tamanho):
    cur = conn.cursor()
    cur.execute(sql, (ultimo_pk, tamanho))
    nomes = [d[0] for d in cur.description]
    return [dict(zip(nomes, r)) for r in cur.fetchall()]


def enviar(api_url, token, itens):
    import requests
    resp = requests.post(
        api_url.rstrip("/") + "/api/governo/acs/ingestao/visitas",
        json={"visitas": itens},
        headers={"Authorization": f"ApiKey {token}"},
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API respondeu {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def carregar_estado(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"ultimo_pk": 0}


def salvar_estado(caminho, estado):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f)
    os.replace(tmp, caminho)


def diagnostico(schema):
    mapa, faltando = mapear_colunas(schema)
    print("Tabelas encontradas:")
    for t in sorted({t for t, _ in CANDIDATOS.values()}):
        print(f"  {t}: {'sim' if t in schema else 'NÃO'}")
    print("\nCampos mapeados:")
    for campo in CANDIDATOS:
        alvo = mapa.get(campo)
        print(f"  {campo:14} -> {alvo[0] + '.' + alvo[1] if alvo else '(não encontrado)'}")
    if faltando:
        print("\nFALTANDO (obrigatório): " + ", ".join(faltando))
        return 1
    print("\nOK: dá para coletar.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Envia visitas domiciliares do PEC para o SoloCRT.")
    ap.add_argument("--dsn", default=os.environ.get("PEC_DSN"), help="DSN PostgreSQL do PEC (ou env PEC_DSN)")
    ap.add_argument("--api-url", default=os.environ.get("SOLOCRT_API_URL", "https://governo.soluscrt.com.br"))
    ap.add_argument("--token", default=os.environ.get("SOLOCRT_API_TOKEN"), help="Chave de API (ou env SOLOCRT_API_TOKEN)")
    ap.add_argument("--estado", default=os.environ.get("COLETOR_ESTADO", "coletor_pec_estado.json"))
    ap.add_argument("--lote", type=int, default=500)
    ap.add_argument("--max-lotes", type=int, default=0, help="0 = até acabar")
    ap.add_argument("--dry-run", action="store_true", help="Mostra o primeiro lote sem enviar")
    ap.add_argument("--diagnostico", action="store_true", help="Lista tabelas/colunas do PEC encontradas")
    args = ap.parse_args(argv)

    if not args.dsn:
        ap.error("informe --dsn ou a variável PEC_DSN")
    conn = conectar(args.dsn)
    schema = ler_schema(conn)
    if args.diagnostico:
        return diagnostico(schema)

    mapa, faltando = mapear_colunas(schema)
    if faltando:
        print("Não dá para coletar, faltam: " + ", ".join(faltando) + ". Rode --diagnostico.", file=sys.stderr)
        return 1
    if not args.dry_run and not args.token:
        ap.error("informe --token ou a variável SOLOCRT_API_TOKEN")

    sql = montar_sql(mapa)
    estado = carregar_estado(args.estado)
    lote_n, total = 0, {"criadas": 0, "atualizadas": 0, "rejeitadas": 0, "ignoradas": 0}
    tamanho = max(1, min(args.lote, 500))
    while True:
        linhas = ler_lote(conn, sql, estado["ultimo_pk"], tamanho)
        if not linhas:
            break
        itens = [i for i in (linha_para_item(l) for l in linhas) if i]
        total["ignoradas"] += len(linhas) - len(itens)
        if args.dry_run:
            print(json.dumps({"visitas": itens[:20]}, ensure_ascii=False, indent=2, default=str))
            print(f"(dry-run: {len(itens)} de {len(linhas)} linhas seriam enviadas neste lote)")
            return 0
        if itens:
            r = enviar(args.api_url, args.token, itens)
            total["criadas"] += r.get("criadas", 0)
            total["atualizadas"] += r.get("atualizadas", 0)
            total["rejeitadas"] += len(r.get("rejeitadas", []))
            for rej in r.get("rejeitadas", [])[:5]:
                print(f"rejeitada {rej.get('uuid_origem')}: {rej.get('motivo')}", file=sys.stderr)
        estado["ultimo_pk"] = max(l["pk"] for l in linhas)
        estado["ultima_execucao"] = datetime.now().isoformat(timespec="seconds")
        salvar_estado(args.estado, estado)
        lote_n += 1
        if args.max_lotes and lote_n >= args.max_lotes:
            break
    print(json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
