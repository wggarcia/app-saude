#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SMOKE_BASE_URL:-${BASE_URL:-}}"
TIMEOUT="${SMOKE_TIMEOUT_SECONDS:-20}"
FORCE_LOGIN="${SMOKE_FORCE_LOGIN:-true}"
STRICT_AUTH="${SMOKE_STRICT_AUTH:-false}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ -z "$BASE_URL" ]; then
  echo "[FAIL] Defina SMOKE_BASE_URL ou BASE_URL para rodar o smoke test remoto"
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

pass_count=0
fail_count=0
warn_count=0

pass() {
  echo "[PASS] $1"
  pass_count=$((pass_count + 1))
}

fail() {
  echo "[FAIL] $1"
  fail_count=$((fail_count + 1))
}

warn() {
  echo "[WARN] $1"
  warn_count=$((warn_count + 1))
}

json_get() {
  local key="$1"
  local file="$2"
  "$PYTHON_BIN" - "$key" "$file" <<'PY'
import json
import sys

key = sys.argv[1]
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
value = data
for part in key.split("."):
    if isinstance(value, dict) and part in value:
        value = value[part]
    else:
        print("")
        raise SystemExit(0)
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
else:
    print("" if value is None else value)
PY
}

http_json() {
  local method="$1"
  local url="$2"
  local body_file="$3"
  shift 3
  : > "$body_file"
  curl -sS -L -m "$TIMEOUT" -X "$method" "$url" "$@" -o "$body_file" -w "%{http_code}"
}

assert_http_200() {
  local label="$1"
  local path="$2"
  local body_file="$tmp_dir/$(echo "$label" | tr ' /' '__').out"
  : > "$body_file"
  local status
  status="$(curl -sS -L -m "$TIMEOUT" "$BASE_URL$path" -o "$body_file" -w "%{http_code}")" || status="000"
  if [ "$status" = "200" ]; then
    pass "$label"
  else
    fail "$label (HTTP $status)"
    [ -s "$body_file" ] && sed -n '1,40p' "$body_file"
  fi
}

run_public_smoke() {
  assert_http_200 "Resumo público" "/api/public/resumo"
  assert_http_200 "Mapa público" "/api/public/mapa"
  assert_http_200 "Radar local público" "/api/public/radar-local?cidade=Sao%20Paulo&estado=SP"
  assert_http_200 "Alertas públicos" "/api/public/alertas"
  assert_http_200 "Política de privacidade" "/privacidade/"
}

login_retry_if_needed() {
  local label="$1"
  local endpoint="$2"
  local payload_file="$3"
  local cookie_file="$4"
  local response_file="$5"
  local status
  status="$(http_json "POST" "$BASE_URL$endpoint" "$response_file" -H "Content-Type: application/json" -c "$cookie_file" --data @"$payload_file")" || status="000"

  if [ "$status" = "409" ] && [ "$FORCE_LOGIN" = "true" ]; then
    local action
    action="$(json_get "acao" "$response_file")"
    if [ "$action" = "force_login" ]; then
      "$PYTHON_BIN" - "$payload_file" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as fh:
    payload = json.load(fh)
payload["force_login"] = True
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh)
PY
      status="$(http_json "POST" "$BASE_URL$endpoint" "$response_file" -H "Content-Type: application/json" -c "$cookie_file" --data @"$payload_file")" || status="000"
    fi
  fi

  echo "$status"
}

verify_empresa_like_login() {
  local label="$1"
  local endpoint="$2"
  local email="$3"
  local senha="$4"
  local expected_dashboard="$5"

  if [ -z "$email" ] || [ -z "$senha" ]; then
    if [ "$STRICT_AUTH" = "true" ]; then
      fail "$label sem credenciais; defina variaveis SMOKE_* para validar o fluxo autenticado"
    else
      warn "$label sem credenciais; smoke autenticado pulado"
    fi
    return
  fi

  local cookie_file="$tmp_dir/${label}_cookies.txt"
  local payload_file="$tmp_dir/${label}_payload.json"
  local response_file="$tmp_dir/${label}_login.json"
  local device_id="smoke-$(echo "$label" | tr '[:upper:]' '[:lower:]')-$(date +%s)"

  cat > "$payload_file" <<EOF
{"email":"$email","senha":"$senha","device_id":"$device_id","device_name":"Smoke Test $label","force_login":false}
EOF

  local status
  status="$(login_retry_if_needed "$label" "$endpoint" "$payload_file" "$cookie_file" "$response_file")"
  if [ "$status" != "200" ]; then
    fail "$label login (HTTP $status)"
    [ -s "$response_file" ] && sed -n '1,60p' "$response_file"
    return
  fi

  local token destination
  token="$(json_get "token" "$response_file")"
  destination="$(json_get "destination" "$response_file")"
  if [ -z "$token" ] || [ -z "$destination" ]; then
    fail "$label login sem token/destination"
    [ -s "$response_file" ] && sed -n '1,60p' "$response_file"
    return
  fi
  pass "$label login"

  if [ -n "$expected_dashboard" ] && [ "$destination" != "$expected_dashboard" ]; then
    fail "$label destination inesperado: $destination"
  else
    pass "$label destination"
  fi

  local tab_file="$tmp_dir/${label}_tab.json"
  local tab_status
  tab_status="$(http_json "POST" "$BASE_URL/api/sessao/aba" "$tab_file" -H "Authorization: Bearer $token" -b "$cookie_file" -c "$cookie_file")" || tab_status="000"
  if [ "$tab_status" = "200" ]; then
    pass "$label valida JWT em /api/sessao/aba"
  else
    fail "$label falhou em /api/sessao/aba (HTTP $tab_status)"
    [ -s "$tab_file" ] && sed -n '1,40p' "$tab_file"
    return
  fi

  local page_file="$tmp_dir/${label}_page.html"
  : > "$page_file"
  local page_status
  page_status="$(curl -sS -L -m "$TIMEOUT" "$BASE_URL$destination" -b "$cookie_file" -c "$cookie_file" -o "$page_file" -w "%{http_code}")" || page_status="000"
  if [ "$page_status" = "200" ]; then
    pass "$label dashboard"
  else
    fail "$label dashboard (HTTP $page_status)"
    [ -s "$page_file" ] && sed -n '1,40p' "$page_file"
  fi

  local gestao_path=""
  case "$destination" in
    "/dashboard-farmacia/") gestao_path="/farmacia/gestao/" ;;
    "/dashboard-hospital/") gestao_path="/hospital/gestao/" ;;
    "/dashboard-governo/") gestao_path="/governo/gestao/" ;;
  esac
  if [ -n "$gestao_path" ]; then
    local gestao_file="$tmp_dir/${label}_gestao.html"
    : > "$gestao_file"
    local gestao_status
    gestao_status="$(curl -sS -L -m "$TIMEOUT" "$BASE_URL$gestao_path" -b "$cookie_file" -c "$cookie_file" -o "$gestao_file" -w "%{http_code}")" || gestao_status="000"
    if [ "$gestao_status" = "200" ]; then
      pass "$label gestão"
    else
      fail "$label gestão (HTTP $gestao_status)"
      [ -s "$gestao_file" ] && sed -n '1,40p' "$gestao_file"
    fi
  fi
}

verify_operacao_login() {
  local email="$1"
  local senha="$2"
  if [ -z "$email" ] || [ -z "$senha" ]; then
    if [ "$STRICT_AUTH" = "true" ]; then
      fail "Operação sem credenciais; defina variaveis SMOKE_OPERACAO_* para validar o console"
    else
      warn "Operação sem credenciais; smoke autenticado pulado"
    fi
    return
  fi

  local cookie_file="$tmp_dir/operacao_cookies.txt"
  local payload_file="$tmp_dir/operacao_payload.json"
  local response_file="$tmp_dir/operacao_login.json"

  cat > "$payload_file" <<EOF
{"email":"$email","senha":"$senha"}
EOF

  local status
  status="$(http_json "POST" "$BASE_URL/api/operacao-central/login" "$response_file" -H "Content-Type: application/json" -c "$cookie_file" --data @"$payload_file")" || status="000"
  if [ "$status" != "200" ]; then
    fail "Operação login (HTTP $status)"
    [ -s "$response_file" ] && sed -n '1,60p' "$response_file"
    return
  fi
  pass "Operação login"

  local destination
  destination="$(json_get "destination" "$response_file")"
  if [ "$destination" = "/console-operacional/" ]; then
    pass "Operação destination"
  else
    fail "Operação destination inesperado: $destination"
  fi

  local page_file="$tmp_dir/operacao_page.html"
  : > "$page_file"
  local page_status
  page_status="$(curl -sS -L -m "$TIMEOUT" "$BASE_URL/console-operacional/" -b "$cookie_file" -c "$cookie_file" -o "$page_file" -w "%{http_code}")" || page_status="000"
  if [ "$page_status" = "200" ]; then
    pass "Operação dashboard"
  else
    fail "Operação dashboard (HTTP $page_status)"
    [ -s "$page_file" ] && sed -n '1,40p' "$page_file"
  fi

  local api_file="$tmp_dir/operacao_resumo.json"
  : > "$api_file"
  local api_status
  api_status="$(curl -sS -L -m "$TIMEOUT" "$BASE_URL/api/operacao-central/resumo" -b "$cookie_file" -c "$cookie_file" -o "$api_file" -w "%{http_code}")" || api_status="000"
  if [ "$api_status" = "200" ]; then
    pass "Operação resumo autenticado"
  else
    fail "Operação resumo autenticado (HTTP $api_status)"
    [ -s "$api_file" ] && sed -n '1,40p' "$api_file"
  fi
}

echo "=== SoloCRT • Remote Smoke Test ==="
echo "BASE_URL: $BASE_URL"
echo "STRICT_AUTH: $STRICT_AUTH"

run_public_smoke
verify_empresa_like_login "Farmacia" "/api/login-empresa" "${SMOKE_FARMACIA_EMAIL:-}" "${SMOKE_FARMACIA_PASSWORD:-}" "/dashboard-farmacia/"
verify_empresa_like_login "Hospital" "/api/login-empresa" "${SMOKE_HOSPITAL_EMAIL:-}" "${SMOKE_HOSPITAL_PASSWORD:-}" "/dashboard-hospital/"
verify_empresa_like_login "Empresa" "/api/login-empresa" "${SMOKE_EMPRESA_EMAIL:-}" "${SMOKE_EMPRESA_PASSWORD:-}" "/dashboard-empresa/"
verify_empresa_like_login "Governo" "/api/login-governo" "${SMOKE_GOVERNO_EMAIL:-}" "${SMOKE_GOVERNO_PASSWORD:-}" "/dashboard-governo/"
verify_operacao_login "${SMOKE_OPERACAO_EMAIL:-}" "${SMOKE_OPERACAO_PASSWORD:-}"

echo
echo "=== Resumo ==="
echo "PASS: $pass_count"
echo "WARN: $warn_count"
echo "FAIL: $fail_count"

if [ "$fail_count" -gt 0 ]; then
  echo "STATUS FINAL: REPROVADO"
  exit 1
fi

if [ "$warn_count" -gt 0 ]; then
  echo "STATUS FINAL: APROVADO COM RESSALVAS"
  exit 0
fi

echo "STATUS FINAL: APROVADO"
