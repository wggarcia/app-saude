#!/usr/bin/env bash
# Backup diário do Postgres de produção — grátis, roda no próprio VPS via cron.
#
# Requisitos no VPS (uma vez só, antes do primeiro cron run):
#   1. Gerar a passphrase de criptografia, fora do repositório e fora do .env
#      (nunca em variável de ambiente de uma linha — lição do bug do Firebase
#      push desta mesma sessão):
#        install -d -m 700 /opt/soluscrt_backups
#        openssl rand -base64 48 > /opt/soluscrt_backups/.backup_passphrase
#        chmod 600 /opt/soluscrt_backups/.backup_passphrase
#   2. Testar uma vez manualmente:
#        /opt/soluscrt/scripts/backup_postgres.sh
#   3. Agendar no cron do usuário root (ou de quem roda o serviço):
#        crontab -e
#        15 3 * * * /opt/soluscrt/scripts/backup_postgres.sh >> /opt/soluscrt_backups/cron.log 2>&1
#
# Restauração (quando precisar):
#   openssl enc -d -aes-256-cbc -pbkdf2 -pass file:/opt/soluscrt_backups/.backup_passphrase \
#     -in /opt/soluscrt_backups/postgres/soluscrt_YYYYMMDD_HHMMSS.dump.enc \
#     -out /tmp/restore.dump
#   pg_restore --clean --if-exists -d "$DATABASE_URL" /tmp/restore.dump
#   rm -f /tmp/restore.dump   # nunca deixar o dump decifrado no disco depois de usar

set -euo pipefail

ENV_FILE="/opt/soluscrt/.env"
BACKUP_DIR="/opt/soluscrt_backups/postgres"
PASSPHRASE_FILE="/opt/soluscrt_backups/.backup_passphrase"
LOG_FILE="/opt/soluscrt_backups/backup.log"
RETENCAO_DIAS=30

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE" >&2
}

falhar() {
    log "ERRO: $*"
    exit 1
}

[ -f "$ENV_FILE" ] || falhar "arquivo de env não encontrado em $ENV_FILE"
[ -f "$PASSPHRASE_FILE" ] || falhar "passphrase não encontrada em $PASSPHRASE_FILE — rode o setup do cabeçalho deste script primeiro"

# Carrega só a variável DATABASE_URL do .env, sem executar o arquivo inteiro
# (evita rodar comandos arbitrários se o .env algum dia tiver algo além de VAR=valor).
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2-)"
[ -n "$DATABASE_URL" ] || falhar "DATABASE_URL vazia ou ausente em $ENV_FILE"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
DUMP_TMP="$(mktemp)"
DESTINO="$BACKUP_DIR/soluscrt_${TIMESTAMP}.dump.enc"

trap 'rm -f "$DUMP_TMP"' EXIT

log "Iniciando backup — destino: $DESTINO"

if ! pg_dump --format=custom --no-owner --no-privileges --file="$DUMP_TMP" "$DATABASE_URL"; then
    falhar "pg_dump falhou (código $?) — backup NÃO foi gerado"
fi

TAMANHO="$(stat -c%s "$DUMP_TMP" 2>/dev/null || stat -f%z "$DUMP_TMP")"
[ "$TAMANHO" -gt 0 ] || falhar "pg_dump gerou arquivo vazio — abortando, backup corrompido não é melhor que backup nenhum"

if ! openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$PASSPHRASE_FILE" -in "$DUMP_TMP" -out "$DESTINO"; then
    falhar "criptografia do dump falhou — $DESTINO pode estar incompleto, removendo"
fi
rm -f "$DUMP_TMP"

chmod 600 "$DESTINO"
log "Backup concluído: $DESTINO ($TAMANHO bytes antes da criptografia)"

REMOVIDOS="$(find "$BACKUP_DIR" -name 'soluscrt_*.dump.enc' -mtime "+${RETENCAO_DIAS}" -print -delete | wc -l)"
[ "$REMOVIDOS" -gt 0 ] && log "Rotação: removidos $REMOVIDOS backup(s) com mais de ${RETENCAO_DIAS} dias"

log "OK"
