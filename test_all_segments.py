#!/usr/bin/env python3
"""
Comprehensive smoke-test for all 5 demo segments.
Tests every major endpoint per segment, seeds, then re-tests.
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8099"

ACCOUNTS = [
    {"label": "SST/Empresa",    "email": "demo.sst@solocrt.com",      "senha": "Demo@SST2026"},
    {"label": "Farmácia",       "email": "demo.farmacia@solocrt.com",  "senha": "Demo@Farm2026"},
    {"label": "Hospital",       "email": "demo.hospital@solocrt.com",  "senha": "Demo@Hosp2026"},
    {"label": "Governo",        "email": "demo.governo@solocrt.com",   "senha": "Demo@Gov2026"},
    {"label": "Plano de Saúde", "email": "demo.plano@solocrt.com",     "senha": "Demo@Plano2026"},
]

COMMON = [
    "/api/enterprise/command-center",
    "/api/enterprise/premium-suite",
    "/api/rede/kpis",
    "/api/alertas",
    "/api/billing/status",
]

SECTOR = {
    "SST/Empresa": [
        "/api/sst/dashboard",
        "/api/sst/funcionarios",
        "/api/sst/riscos/",
        "/api/sst/asos",
        "/api/sst/treinamentos",
        "/api/sst/epis/catalogo",
        "/api/sst/epis/entregas",
        "/api/sst/cats",
        "/api/sst/afastamentos",
        "/api/sst/esocial",
        "/api/sst/documentos",
        "/api/sst/conformidade",
        "/api/sst/configuracoes",
        "/api/sst/exames",
        "/api/sst/agendamentos",
        "/api/sst/planos-acao/",
        "/api/sst/bem-estar/resumo",
        "/api/sst/wellness/resumo/",
        # /api/sst/cipa/kpis/ — plan-gated (higher tier)
        "/api/sst/vacinacao/kpis/",
        # /api/sst/biometria/kpis/ — plan-gated (higher tier)
        "/api/sst/psicossocial/kpis/",
        "/api/sst/laudos/kpis/",
        "/api/sst/ppp/kpis/",
        "/api/sst/fap/kpis/",
        "/api/sst/agendamentos/kpis",
        "/api/sst/esocial/kpis/",
        "/api/sst/postos",
        "/api/sst/relatorios",
        "/api/sst/contexto-integrado",
        # /api/corporativo/* — uses cookie auth (different auth flow), not Bearer JWT
    ],
    "Farmácia": [
        "/api/rede/",
        "/api/farmacia/dashboard",
        "/api/farmacia/itens/",
        # /api/farmacia/medicamentos/ — endpoint does not exist
        "/api/farmacia/pacientes/",
        "/api/farmacia/receitas/",
        "/api/farmacia/dispensacoes/",
        "/api/farmacia/lotes/",
        "/api/farmacia/pedidos/",
        "/api/farmacia/inventarios/",
        "/api/farmacia/fornecedores/",
        "/api/farmacia/fornecedores-gestao",
        "/api/farmacia/pedidos-gestao",
        "/api/farmacia/dispensacao",
        "/api/farmacia/estoque",
        "/api/farmacia/movimentos/",
        "/api/farmacia/lotes/kpis/",
        "/api/farmacia/ops/kpis/",
        "/api/farmacia/kpis/avancados/",
        "/api/farmacia/ia/dashboard/",
        "/api/farmacia/ia/curva-abc/",
        "/api/farmacia/ia/previsao-demanda/",
        "/api/farmacia/rede/kpis/",
        "/api/farmacia/rede/estoque/",
        "/api/farmacia/dre/dashboard",
        "/api/farmacia/dre/lista",
        "/api/farmacia/auditoria/",
        "/api/farmacia/conformidade/",
        "/api/farmacia/livro-controlado/",
        "/api/farmacia/lotes/bloqueio/",
        "/api/farmacia/descartes/",
        "/api/farmacia/pbm/convenios",
        "/api/farmacia/pbm/kpis",
        "/api/farmacia/delivery/kpis",
        "/api/farmacia/delivery/pedidos",
        "/api/farmacia/pdv/sessao-atual",
        "/api/farmacia/pdv/historico",
    ],
    "Hospital": [
        "/api/hospital/dashboard",
        "/api/hospital/pacientes/",
        "/api/hospital/leitos/",
        "/api/hospital/departamentos/",
        "/api/hospital/triagens/",
        "/api/hospital/internacoes/",
        "/api/hospital/ops/kpis/",
        "/api/hospital/exames/",
        "/api/hospital/exames/dashboard/",
        "/api/hospital/farmacia/",
        "/api/hospital/farmacia/kpis/",
        "/api/hospital/cirurgia/kpis/",
        "/api/hospital/cirurgia/agenda/",
        "/api/hospital/cirurgia/",
        "/api/hospital/centro-cirurgico/",
        "/api/hospital/tiss/kpis/",
        "/api/hospital/tiss/",
        "/api/hospital/lis/kpis/",
        "/api/hospital/lis/",
        "/api/hospital/imagem/kpis/",
        "/api/hospital/imagem/",
        "/api/hospital/prontuario/",
        "/api/hospital/analytics/",
        "/api/hospital/faturamento/dashboard/",
        "/api/hospital/uti/dashboard/",
        "/api/hospital/contexto-integrado/",
    ],
    "Governo": [
        "/api/governo/programas/",
        "/api/governo/indicadores/",
        "/api/governo/unidades/",
        "/api/governo/alertas",
        "/api/governo/orcamentos/",
        "/api/governo/planos-acao/",
        "/api/governo/ops/kpis/",
        "/api/governo/pec/kpis/",
        "/api/governo/pec/",
        "/api/governo/dashboard/fase2/",
        "/api/governo/producao/",
        "/api/governo/producao/dashboard/",
        "/api/governo/regulacao/",
        "/api/governo/regulacao/dashboard/",
        "/api/governo/regulacao-assistencial/",
        "/api/governo/regulacao-assistencial/kpis/",
        "/api/governo/previne/",
        "/api/governo/previne/dashboard/",
        "/api/governo/contratos/",
        "/api/governo/atos-normativos/",
        "/api/governo/teleconsulta/kpis/",
        "/api/governo/teleconsulta/",
        "/api/governo/rag/kpis/",
        "/api/governo/rag/",
        "/api/governo/farmacia-basica/kpis/",
        "/api/governo/farmacia-basica/itens/",
        "/api/governo/faturamento-sus/kpis/",
        "/api/governo/faturamento-sus/lotes/",
        "/api/governo/esus/status/",
        "/api/governo/esus/logs/",
        # /api/governo/plataforma/* — requires TI role (not available on demo account)
    ],
    "Plano de Saúde": [
        "/api/planos-saude/",
        "/api/plano-saude/rede",
        "/api/plano-saude/rede/kpis",
        "/api/plano-saude/carencias/",
        # /api/plano-saude/portabilidade/ — POST-only endpoint (405 on GET by design)
    ],
}

def req(method, path, token=None, body=None):
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            b = json.loads(e.read())
        except Exception:
            b = {}
        return e.code, b
    except Exception as ex:
        return 0, {"__ex__": str(ex)}


def login(email, senha):
    status, body = req("POST", "/api/login", body={"email": email, "senha": senha})
    if status == 200:
        return body.get("token")
    # 409 = sessao_em_uso — retry with force_login
    if status == 409:
        status, body = req("POST", "/api/login", body={"email": email, "senha": senha, "force_login": True})
        if status == 200:
            return body.get("token")
    return None


errors_all = {}  # label -> list of (path, status, msg)

for account in ACCOUNTS:
    label = account["label"]
    errors = []
    print(f"\n{'='*64}")
    print(f"  {label}  ({account['email']})")
    print(f"{'='*64}")

    token = login(account["email"], account["senha"])
    if not token:
        print("  ❌  LOGIN FAILED")
        errors_all[label] = [("LOGIN", 0, "failed")]
        continue
    print("  ✅  Login OK")

    # Seed
    s, b = req("POST", "/api/enterprise/seed-operational-demo", token=token)
    if s == 200:
        print(f"  ✅  Seed OK — criados={b.get('total_criado','?')}")
    else:
        msg = str(b.get("erro", b))[:80]
        print(f"  ⚠️   Seed {s}: {msg}")

    # Test endpoints
    endpoints = COMMON + SECTOR.get(label, [])
    for path in endpoints:
        status, body = req("GET", path, token=token)
        if status == 200:
            print(f"  ✅  {path}")
        elif status in (400, 404, 405):
            note = str(body.get("erro", body.get("error", "")))[:60]
            print(f"  ⚠️   {path} → {status} {note}")
            errors.append((path, status, note))
        else:
            note = str(body.get("erro", body.get("error", body.get("detalhe", ""))))[:100]
            print(f"  ❌  {path} → {status} {note}")
            errors.append((path, status, note))

    errors_all[label] = errors

print(f"\n\n{'='*64}")
print("  FINAL SUMMARY")
print(f"{'='*64}")
total_ok = 0
total_fail = 0
for label, errs in errors_all.items():
    if errs and errs[0][0] == "LOGIN":
        print(f"  ❌  {label}: LOGIN FAILED")
        total_fail += 1
        continue
    n_ep = len(COMMON) + len(SECTOR.get(label, []))
    n_err = len([e for e in errs if e[1] not in (400, 404, 405)])
    n_warn = len([e for e in errs if e[1] in (400, 404, 405)])
    n_ok = n_ep - len(errs)
    total_ok += n_ok
    total_fail += n_err
    print(f"  {'✅' if n_err==0 else '❌'}  {label}: {n_ok}/{n_ep} OK  {n_err} errors  {n_warn} warnings")
    for path, status, note in errs:
        tag = "  ⚠️" if status in (400, 404, 405) else "  ❌"
        print(f"      {tag}  {path} → {status}  {note}")

print(f"\n  TOTAL: {total_ok} OK, {total_fail} ERRORS")
