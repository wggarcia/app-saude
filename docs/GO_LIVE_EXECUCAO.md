# Go-Live Execucao - SolusCRT Saude

Checklist copiavel para executar o go-live controlado em producao.

## Bloco 1 - Deploy seguro no Render

1. Validar pre-flight local:

```bash
cd /Users/angelica/backend
git status --short --branch
python3 manage.py check
python3 manage.py makemigrations --check --dry-run
python3 manage.py test
SKIP_BUILD_MIGRATIONS=true PYTHON_BIN=python3 ./build.sh
```

2. Conferir Render:

```text
Banco Postgres: soluscrt-saude-db
Servico web: soluscrt-saude-api
Build Command: ./build.sh
Pre-Deploy Command: python manage.py migrate --noinput && python manage.py bootstrap_acessos
Start Command: ./start.sh
Health Check Path: /api/public/resumo
```

Observacao: producao nao deve executar `demo_setup` nem expor mutacoes de demonstracao. Demonstracoes interativas ficam no ambiente de homologacao.

3. Preencher segredos no Render usando `.env.production.example` como referencia.

4. Rotacionar chaves se houver qualquer chance de exposicao:

```text
DJANGO_SECRET_KEY
JWT_SECRET_KEY
JWT_EXP_HOURS
CORS_ALLOW_ALL_ORIGINS
ASAAS_API_KEY
ASAAS_WEBHOOK_TOKEN
FIREBASE_SERVICE_ACCOUNT_JSON
MAPBOX_ACCESS_TOKEN
GOOGLE_MAPS_BROWSER_KEY
GOOGLE_MAPS_IOS_KEY
```

5. Publicar:

```bash
git push origin main
```

6. Se o auto-deploy estiver desligado, acionar no painel Render:

```text
soluscrt-saude-api -> Manual Deploy -> Deploy latest commit
```

## Bloco 2 - Validacao tecnica final

1. Validar endpoints publicos:

```bash
BASE_URL="https://app-saude-p9n8.onrender.com"

curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/resumo"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/mapa"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/radar-local?cidade=Sao%20Paulo&estado=SP"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/alertas"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/privacidade/"
```

2. Rodar checks locais com ambiente de producao simulado:

```bash
DJANGO_ENV=production \
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY='troque-por-chave-forte-com-64-caracteres-ou-mais' \
JWT_SECRET_KEY='troque-por-outra-chave-forte-com-64-caracteres-ou-mais' \
JWT_EXP_HOURS=12 \
CORS_ALLOW_ALL_ORIGINS=false \
DJANGO_ALLOWED_HOSTS='app-saude-p9n8.onrender.com' \
CSRF_TRUSTED_ORIGINS='https://app-saude-p9n8.onrender.com' \
DATABASE_URL='postgresql://check:check@localhost:5432/soluscrt_check' \
python3 manage.py check --deploy
```

3. Rodar checklist consolidado:

```bash
PYTHON_BIN=python3 ./go_live_check.sh
```

Resultado esperado:

```text
FAIL: 0
STATUS FINAL: APROVADO
```

Se houver warning de variaveis ausentes localmente, valide se elas estao preenchidas no Render.

4. Smoke test manual em producao:

```text
[ ] Login empresa
[ ] Login governo
[ ] Login operacao
[ ] Emissao de JWT
[ ] Validacao de JWT em rota protegida
[ ] Envio publico de sintoma com localizacao
[ ] /api/public/resumo retorna dados coerentes
[ ] /api/public/mapa retorna pontos agregados
[ ] /api/public/radar-local retorna leitura territorial com `cidade/estado` ou `latitude/longitude`
[ ] /api/public/alertas retorna alerta publico
[ ] Fluxo de pagamento cria cobranca Asaas
[ ] Webhook Asaas valida token e atualiza status
[ ] Push/alertas nao gera erro no log
```

5. Conferir logs:

```text
[ ] Sem Traceback recorrente
[ ] Sem DisallowedHost
[ ] Sem erro de CSRF em dominio oficial
[ ] Sem chave secreta em log
[ ] Sem DATABASE_URL em log
[ ] Sem payload sensivel de saude individual exposto indevidamente
[ ] Sem token Asaas/Firebase/Maps em log
```

## Bloco 3 - Reenvio Apple

1. Confirmar URL publica:

```text
https://app-saude-p9n8.onrender.com/privacidade/
```

2. Revisar App Store Connect:

```text
[ ] App Privacy declara localizacao
[ ] App Privacy declara dados de saude/sintomas quando aplicavel
[ ] Finalidade: monitoramento epidemiologico, alertas publicos e seguranca antifraude
[ ] Texto de localizacao explica uso territorial e alertas proximos
[ ] Nota deixa claro que nao e diagnostico medico
[ ] URL de privacidade aponta para /privacidade/
[ ] URL de suporte aponta para pagina publica de suporte
```

3. Notas de revisao sugeridas:

```text
O SolusCRT Saude e um app de monitoramento epidemiologico populacional e alertas publicos. O app nao fornece diagnostico medico, prescricao ou atendimento de emergencia. A localizacao e usada para registrar sinais de saude de forma territorial, reduzir fraude e exibir alertas proximos. A politica de privacidade esta publicada em https://app-saude-p9n8.onrender.com/privacidade/.
```

4. Antes de enviar build:

```bash
cd /Users/angelica/backend/app_saude
flutter analyze
flutter test
```

5. Depois do envio:

```text
[ ] Registrar numero do build enviado
[ ] Registrar data/hora do envio
[ ] Salvar texto usado em App Review Notes
[ ] Monitorar e-mail/App Store Connect ate decisao
```

## Referencias internas

- Render: `docs/DEPLOY_RENDER.md`
- Producao: `docs/PRODUCTION_READINESS.md`
- Staging e smoke: `docs/STAGING_AND_SMOKE.md`
- Scorecard executivo: `docs/EXECUTIVE_SCORECARD.md`
- App Store: `app_saude/docs/APP_STORE_CONNECT_SUBMISSION.md`
