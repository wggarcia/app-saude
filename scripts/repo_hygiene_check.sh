#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "[WARN] Sem repositorio git detectado; pulando hygiene check"
  exit 0
fi

fail_count=0
warn_count=0

fail() {
  echo "[FAIL] $1"
  fail_count=$((fail_count + 1))
}

warn() {
  echo "[WARN] $1"
  warn_count=$((warn_count + 1))
}

pass() {
  echo "[PASS] $1"
}

forbidden=()
while IFS= read -r path; do
  case "$path" in
    secrets/*|db.sqlite3|*.sqlite3|*.jks|*.keystore|key.properties|google-services.json|*/google-services.json|GoogleService-Info.plist|*/GoogleService-Info.plist)
      forbidden+=("$path")
      ;;
    .env|.env.local|.env.production|.env.staging|.env.*.local)
      forbidden+=("$path")
      ;;
  esac
done < <(git ls-files)

if [ ${#forbidden[@]} -eq 0 ]; then
  pass "Nenhum segredo ou banco local esta versionado"
else
  fail "Arquivos proibidos versionados:"
  printf '  - %s\n' "${forbidden[@]}"
fi

generated_matches="$(git ls-files | grep -E '(^|/)(staticfiles/|build/|__pycache__/)|\.pyc$' || true)"
if [ -z "$generated_matches" ]; then
  pass "Nenhum artefato gerado foi versionado"
else
  warn "Artefatos gerados versionados:"
  printf '%s\n' "$generated_matches" | sed 's/^/  - /'
fi

large_files="$(git ls-files -z | xargs -0 du -k 2>/dev/null | awk '$1 > 5120 {print $2 " (" $1 " KB)"}' || true)"
if [ -z "$large_files" ]; then
  pass "Nenhum arquivo versionado acima de 5 MB"
else
  warn "Arquivos grandes versionados detectados:"
  printf '%s\n' "$large_files" | sed 's/^/  - /'
fi

if [ $fail_count -gt 0 ]; then
  exit 1
fi

if [ $warn_count -gt 0 ]; then
  exit 0
fi

exit 0
