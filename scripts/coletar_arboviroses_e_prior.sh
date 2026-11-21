#!/usr/bin/env bash
#
# Coleta semanal das arboviroses no SINAN e recálculo do prior vivo.
#
# Por que existe: dengue, chikungunya e zika nunca estiveram no cron — só o
# SIVEP estava. Eram importações manuais, e por isso a série ficou parada no
# arquivo de 2025 por ~10 meses sem ninguém notar (ver a correção de ano
# dinâmico em api/pipeline_oficial.py). Sem este agendamento, o dado volta a
# envelhecer e os fatores do prior vivo congelam no dia em que foram gerados —
# o que faria o sistema anunciar um surto que já passou.
#
# --max-linhas alto é obrigatório: o padrão lê 50.000 linhas, e o arquivo
# nacional não é ordenado por UF, então a amostra sai enviesada por estado (numa
# execução com o padrão, o RJ ficou com 5 linhas). O prior vivo trabalha por
# estado, então precisa do arquivo inteiro.
#
# A ordem importa: o prior vivo roda DEPOIS da coleta, senão recalcula em cima
# do dado velho. Por isso é um script só, encadeado, e não três linhas de cron.
#
# Agendado para o dia 1 de cada mês, 02:00 (`0 2 1 * *`), por decisão do dono:
# a coleta é pesada e mensal alivia o servidor.
#
# O custo dessa escolha, para quem for mexer depois: o prior vivo já descarta os
# 4 períodos mais recentes por atraso de notificação, e agora soma a isso até ~4
# semanas de espera pela próxima coleta. Na prática o sinal pode estar ~2 meses
# atrás do presente. Para ajustar o prior isso é aceitável — não é sistema de
# alerta precoce. Se um dia virar alerta, precisa voltar a ser semanal.
set -uo pipefail

APP_DIR="/opt/soluscrt"
LOG_DIR="/var/log/soluscrt"
LOG="${LOG_DIR}/sinan_arboviroses.log"
PY="${APP_DIR}/venv/bin/python"

mkdir -p "$LOG_DIR"
cd "$APP_DIR" || exit 1

# shellcheck disable=SC1091
set -a; . "${APP_DIR}/.env"; set +a
export APP_DATABASE_URL=

echo "===== $(date '+%Y-%m-%d %H:%M:%S') — início =====" >> "$LOG"

falhas=0
for fonte in sinan_agravos sinan_chikungunya sinan_zika; do
    echo "--- $fonte ---" >> "$LOG"
    if "$PY" manage.py processar_fonte_oficial "$fonte" \
        --executar-download --max-linhas 3000000 >> "$LOG" 2>&1; then
        echo "    ok" >> "$LOG"
    else
        echo "    FALHOU" >> "$LOG"
        falhas=$((falhas + 1))
    fi
done

# O prior vivo roda mesmo se uma das coletas falhar: as outras séries seguem
# válidas, e ele ignora sozinho quem não tem dado suficiente. Mas registra o
# aviso, porque fator calculado sobre série incompleta merece desconfiança.
if [ "$falhas" -gt 0 ]; then
    echo "AVISO: $falhas coleta(s) falharam — prior vivo pode ficar defasado" >> "$LOG"
fi

echo "--- prior vivo ---" >> "$LOG"
"$PY" manage.py calcular_prior_vivo --aplicar >> "$LOG" 2>&1 \
    || echo "    FALHOU" >> "$LOG"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') — fim (falhas: $falhas) =====" >> "$LOG"
