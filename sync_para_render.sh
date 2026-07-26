#!/bin/bash
# Replica o banco do VPS (primário, Brasil) para o Render (standby, Oregon/EUA).
# Direção: VPS -> Render. Roda a cada 6h via cron:
#   0 */6 * * * /opt/soluscrt/sync_para_render.sh
#
# Robustez (lições desta base — erros engolidos custaram caro antes):
#  - VALIDA que o dump não está vazio ANTES de enviar. O restore usa --clean
#    (dropa tudo no Render primeiro); um dump quebrado/vazio + --clean APAGARIA
#    o standby inteiro. Mesmo modo de falha do backup vazio de 20/07/2026.
#  - NÃO mascara erro de restore. Antes: ON_ERROR_STOP=0 + sempre logava
#    "concluido", escondendo restore parcial. Agora conta os ERROR do psql e,
#    se houver qualquer um, loga "SYNC FALHOU" e sai != 0 (cron enxerga a falha).
#  - O restore segue best-effort (ON_ERROR_STOP=0) para o standby receber o
#    máximo possível, mas o resultado é REPORTADO com honestidade.

set -uo pipefail

LOGFILE="/var/log/soluscrt/sync_render.log"
ENV_FILE="/opt/soluscrt/.env"
RENDER_TARGET="srv-d77gompr0fns7382kbo0@ssh.oregon.render.com"
RENDER_KEY="/root/.ssh/render_sync_key"
DUMP_MIN_BYTES=100000   # piso de sanidade; dump real é vários MB

mkdir -p /var/log/soluscrt

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOGFILE"; }

log "=== iniciando sync VPS->Render ==="

# Lê só DATABASE_URL do .env, sem executar o arquivo inteiro (mesmo padrão
# seguro do backup_postgres.sh). Papel dono -> pg_dump enxerga tudo, inclusive
# dado sob RLS.
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)"
if [ -z "${DATABASE_URL:-}" ]; then
    log "ERRO: DATABASE_URL ausente em $ENV_FILE — sync abortado"
    exit 1
fi

DUMP_FILE="/tmp/sync_para_render_$(date +%s).sql"
RESTORE_OUT="/tmp/sync_render_restore_$(date +%s).out"
trap 'rm -f "$DUMP_FILE" "$RESTORE_OUT"' EXIT

# 1. Dump do primário
if ! pg_dump "$DATABASE_URL" --no-owner --no-privileges --clean --if-exists -f "$DUMP_FILE" 2>> "$LOGFILE"; then
    log "ERRO: pg_dump do primário falhou — sync abortado, Render intocado"
    exit 1
fi

# 2. Valida tamanho ANTES de enviar (--clean dropa o Render; dump vazio apagaria o standby)
DUMP_SIZE=$(stat -c%s "$DUMP_FILE" 2>/dev/null || echo 0)
if [ "$DUMP_SIZE" -lt "$DUMP_MIN_BYTES" ]; then
    log "ERRO: dump suspeito (${DUMP_SIZE} bytes < ${DUMP_MIN_BYTES}) — sync abortado para NÃO apagar o standby"
    exit 1
fi

# 3. Restaura no Render (best-effort), capturando a saída
cat "$DUMP_FILE" | ssh -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new \
    -i "$RENDER_KEY" "$RENDER_TARGET" \
    "psql \"\$DATABASE_URL\" -v ON_ERROR_STOP=0" > "$RESTORE_OUT" 2>&1
SSH_RC=$?
cat "$RESTORE_OUT" >> "$LOGFILE"

if [ "$SSH_RC" -ne 0 ]; then
    log "SYNC FALHOU: conexão/psql com o Render retornou rc=$SSH_RC — standby NÃO atualizado"
    exit 1
fi

# 4. Detecta erros de restore que o ON_ERROR_STOP=0 deixaria passar calado
N_ERR=$(grep -cE "^ERROR:|^psql.*error|^FATAL" "$RESTORE_OUT" || true)
if [ "${N_ERR:-0}" -gt 0 ]; then
    log "SYNC FALHOU: $N_ERR erro(s) no restore do Render — standby pode estar inconsistente (ver linhas acima)"
    exit 1
fi

log "=== sync concluido OK (dump ${DUMP_SIZE} bytes, 0 erros no restore) ==="
