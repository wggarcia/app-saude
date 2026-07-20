#!/usr/bin/env python3
"""Troca com segurança os valores de APP_DATABASE_URL e DATABASE_URL no .env.

Contexto: para ativar a RLS, a conexão normal da app (APP_DATABASE_URL) precisa
usar o papel restrito (não-dono), e a conexão "owner" (DATABASE_URL) precisa usar
o papel dono. Hoje estão trocados. Este script inverte os dois valores.

Garantias:
  - Faz BACKUP do .env (com timestamp) antes de qualquer alteração.
  - Troca APENAS os dois valores entre si; nenhuma outra linha é tocada.
  - NUNCA imprime senha — mostra só o usuário (role) de cada URL, para conferência.
  - Reversível: rode de novo e ele troca de volta; ou restaure o backup.

Uso:
  python3 scripts/rls_swap_env.py            # usa /opt/soluscrt/.env
  ENV_PATH=/caminho/.env python3 scripts/rls_swap_env.py
"""
import os
import re
import shutil
import sys
import time
from urllib.parse import urlparse

ENV_PATH = os.environ.get("ENV_PATH", "/opt/soluscrt/.env")
KEYS = ("APP_DATABASE_URL", "DATABASE_URL")


def role_of(url: str) -> str:
    try:
        return urlparse(url).username or "?"
    except Exception:
        return "?"


def main() -> int:
    if not os.path.exists(ENV_PATH):
        print(f"ERRO: {ENV_PATH} nao encontrado.")
        return 1

    with open(ENV_PATH, "r") as f:
        lines = f.readlines()

    vals, idx = {}, {}
    for i, line in enumerate(lines):
        for k in KEYS:
            m = re.match(rf"^\s*{k}\s*=\s*(.*?)\s*$", line)
            if m:
                v = m.group(1)
                if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
                    v = v[1:-1]
                vals[k] = v
                idx[k] = i

    missing = [k for k in KEYS if k not in vals]
    if missing:
        print(f"ERRO: nao encontrei no .env: {', '.join(missing)}. Nada foi alterado.")
        return 1

    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = f"{ENV_PATH}.bak.{ts}"
    shutil.copy2(ENV_PATH, bak)

    a, b = KEYS
    print("ANTES da troca:")
    for k in KEYS:
        print(f"  {k} -> role={role_of(vals[k])}")

    new = dict(vals)
    new[a], new[b] = vals[b], vals[a]
    for k in KEYS:
        lines[idx[k]] = f"{k}={new[k]}\n"

    with open(ENV_PATH, "w") as f:
        f.writelines(lines)

    print("DEPOIS da troca:")
    for k in KEYS:
        print(f"  {k} -> role={role_of(new[k])}")
    print(f"\nBackup salvo em: {bak}")
    print("Reverter: rode este script de novo (troca de volta) ou restaure o backup acima.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
