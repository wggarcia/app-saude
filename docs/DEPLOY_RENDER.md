# Deploy Render - SolusCRT Saude

Runbook de deploy seguro no Render. Use este arquivo como roteiro operacional; nao cole segredos em commits, prints ou issues.

## 1. Pre-flight local

Execute da raiz do repositorio:

```bash
git status --short --branch
python3 manage.py check
python3 manage.py makemigrations --check --dry-run
python3 manage.py test
SKIP_BUILD_MIGRATIONS=true PYTHON_BIN=python3 ./build.sh
```

Resultado esperado:

- `manage.py check`: `System check identified no issues`
- `makemigrations --check --dry-run`: `No changes detected`
- testes Django: `OK`
- build: dependencias instaladas e `collectstatic` concluido

## 2. Criar via Blueprint

Use o `render.yaml` versionado na raiz.

1. Acesse Render Dashboard.
2. Va em Blueprints.
3. Crie uma nova Blueprint Instance apontando para `wggarcia/app-saude`.
4. Confirme o servico `soluscrt-saude-api`.
5. Confirme o banco `soluscrt-saude-db`.
6. Preencha todos os campos `sync: false` com valores reais.

O Blueprint ja define:

- `buildCommand: ./build.sh`
- `preDeployCommand: python manage.py migrate --noinput && python manage.py bootstrap_acessos && python manage.py sanear_producao --apply`
- `startCommand: ./start.sh`
- `healthCheckPath: /api/public/resumo`
- `DATABASE_URL` conectado ao Postgres gerenciado

Em producao, o deploy nao executa mais `demo_setup` nem recria dados de demonstracao. O saneamento remove apenas residuos sintéticos explicitamente marcados e contas demo conhecidas.

## 3. Servico manual ja existente

Se o servico foi criado manualmente e nao por Blueprint, configure no painel:

```text
Build Command:
./build.sh

Pre-Deploy Command:
python manage.py migrate --noinput && python manage.py bootstrap_acessos && python manage.py sanear_producao --apply

Start Command:
./start.sh

Health Check Path:
/api/public/resumo
```

Tambem defina:

```text
SKIP_BUILD_MIGRATIONS=true
```

Se o plano atual nao permitir pre-deploy command, remova `SKIP_BUILD_MIGRATIONS` ou defina `SKIP_BUILD_MIGRATIONS=false`. Nesse modo, o `build.sh` roda `migrate` e `bootstrap_acessos` durante o build para manter compatibilidade.

Nao habilite mutacoes de demo em producao. Se precisar de demonstracao comercial, use um ambiente separado de homologacao.

## 4. Variaveis obrigatorias

Copie `.env.production.example` como referencia e preencha no Render, nunca no Git:

```text
DJANGO_ENV
DJANGO_DEBUG
DJANGO_SECRET_KEY
JWT_SECRET_KEY
JWT_EXP_HOURS
PAYMENT_PROVIDER
CORS_ALLOW_ALL_ORIGINS
DJANGO_ALLOWED_HOSTS
CSRF_TRUSTED_ORIGINS
CORS_ALLOWED_ORIGINS
PUBLIC_BASE_URL
DATABASE_URL
EMAIL_HOST
EMAIL_PORT
EMAIL_USE_TLS
EMAIL_HOST_USER
EMAIL_HOST_PASSWORD
DEFAULT_FROM_EMAIL
ASAAS_API_KEY
ASAAS_BASE_URL
ASAAS_WEBHOOK_TOKEN
ASAAS_USER_AGENT
FIREBASE_SERVICE_ACCOUNT_JSON
MAPBOX_ACCESS_TOKEN
GOOGLE_MAPS_BROWSER_KEY
GOOGLE_MAPS_IOS_KEY
```

Rotacione `DJANGO_SECRET_KEY` e `JWT_SECRET_KEY` se elas ja apareceram em arquivo local, print, historico de terminal ou conversa.

## 5. Deploy

Depois de commitar e enviar para `main`:

```bash
git push origin main
```

No Render, acompanhe:

- build
- pre-deploy
- start
- health check

Se precisar forcar pelo painel:

1. Abra o servico `soluscrt-saude-api`.
2. Clique em Manual Deploy.
3. Selecione Deploy latest commit.

## 6. Validacao pos-deploy

Execute:

```bash
BASE_URL="https://app-saude-p9n8.onrender.com"

curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/resumo"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/mapa"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/radar-local?cidade=Sao%20Paulo&estado=SP"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/api/public/alertas"
curl -sS -m 20 -w "\nHTTP_STATUS:%{http_code}\n" "$BASE_URL/privacidade/"
```

Resultado esperado: `HTTP_STATUS:200` em todos. O endpoint `radar-local` exige `cidade/estado` ou `latitude/longitude`.

Cheque CORS:

```bash
curl -sS -m 20 -D - -o /tmp/soluscrt-cors.json \
  -H "Origin: https://app.soluscrt.com.br" \
  "$BASE_URL/api/public/resumo" | sed -n '1,40p'
```

Resultado esperado depois do deploy novo: `access-control-allow-origin` compativel com a origem enviada.

## 7. Logs e rollback

Nos logs do Render, procure:

```text
Traceback
RuntimeError
DisallowedHost
CSRF
ASAAS_API_KEY
DJANGO_SECRET_KEY
JWT_SECRET_KEY
DATABASE_URL
```

Se houver falha critica:

1. Pause novas alteracoes.
2. No Render, use Rollback para o ultimo deploy verde.
3. Rode os endpoints publicos novamente.
4. Abra um hotfix pequeno e validado.
