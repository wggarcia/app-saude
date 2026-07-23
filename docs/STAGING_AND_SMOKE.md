# Staging And Smoke - SoloCRT Saude

Este arquivo define o caminho minimo para ter um ambiente de staging separado e um smoke test remoto reproduzivel.

## 1. Objetivo

Staging existe para responder 3 perguntas antes de publicar em producao:

1. O deploy sobe sem regressao?
2. Os fluxos criticos autenticados continuam funcionando?
3. Pagamento, dashboards e operacao respondem com credenciais reais de teste?

## 2. Blueprint de staging

Arquivos relacionados:

- [render.staging.yaml](/Users/angelica/backend/render.staging.yaml)
- [.env.staging.example](/Users/angelica/backend/.env.staging.example)

Fluxo sugerido no Render:

1. Criar uma nova Blueprint Instance apontando para `render.staging.yaml`.
2. Usar nomes separados de servico e banco:
   - `soluscrt-saude-staging-api`
   - `soluscrt-saude-staging-db`
3. Preencher todos os `sync: false` no painel do Render.
4. Definir o dominio/base URL real de staging nas variaveis:
   - `DJANGO_ALLOWED_HOSTS`
   - `CSRF_TRUSTED_ORIGINS`
   - `CORS_ALLOWED_ORIGINS`
   - `PUBLIC_BASE_URL`
5. Preencher os bootstraps setoriais para o smoke autenticado nascer pronto:
   - `SOLUSCRT_BOOTSTRAP_FARMACIA_*`
   - `SOLUSCRT_BOOTSTRAP_HOSPITAL_*`
   - `SOLUSCRT_BOOTSTRAP_EMPRESA_*`
   - `SOLUSCRT_BOOTSTRAP_GOVERNO_*`
   - `SOLUSCRT_BOOTSTRAP_OWNER_*`

## 3. Credenciais de smoke

Nunca commitar credenciais. Para smoke remoto, exporte apenas no shell/CI:

```bash
export SMOKE_BASE_URL="https://soluscrt-saude-staging.onrender.com"

export SMOKE_FARMACIA_EMAIL="farmacia-staging@exemplo.com"
export SMOKE_FARMACIA_PASSWORD="..."

export SMOKE_HOSPITAL_EMAIL="hospital-staging@exemplo.com"
export SMOKE_HOSPITAL_PASSWORD="..."

export SMOKE_EMPRESA_EMAIL="empresa-staging@exemplo.com"
export SMOKE_EMPRESA_PASSWORD="..."

export SMOKE_GOVERNO_EMAIL="governo-staging@exemplo.com"
export SMOKE_GOVERNO_PASSWORD="..."

export SMOKE_OPERACAO_EMAIL="operacao-staging@soluscrt.com.br"
export SMOKE_OPERACAO_PASSWORD="..."
```

O comando `bootstrap_acessos` agora suporta criar contas piloto de:

- empresa
- farmacia
- hospital
- governo
- operacao

Isso evita staging "verde pela metade", em que o smoke exige perfis que o bootstrap nao provisiona.

As contas demo e os comandos de seed/reset ficam restritos a staging/homologacao. Producao deve permanecer com dados reais, sem regeneracao automatica de demo e com saneamento dos residuos sintéticos conhecidos.

## 4. Rodar smoke remoto

```bash
./scripts/smoke_platform.sh
```

O script valida:

- endpoints publicos
- politica de privacidade
- login farmacia
- login hospital
- login empresa
- login governo
- login operacao
- emissao de token
- `/api/sessao/aba` para validar JWT empresarial/governamental
- dashboard autenticado
- telas de gestao setorial quando aplicavel
- `/api/operacao-central/resumo` para operacao

Se alguma credencial nao estiver definida, o script marca `WARN` e continua.
Se `SMOKE_STRICT_AUTH=true`, credenciais ausentes viram `FAIL`.

## 5. Workflow manual no GitHub

Arquivo relacionado:

- [.github/workflows/staging-smoke.yml](/Users/angelica/backend/.github/workflows/staging-smoke.yml)

Secrets esperados:

- `STAGING_BASE_URL`
- `STAGING_SMOKE_FARMACIA_EMAIL`
- `STAGING_SMOKE_FARMACIA_PASSWORD`
- `STAGING_SMOKE_HOSPITAL_EMAIL`
- `STAGING_SMOKE_HOSPITAL_PASSWORD`
- `STAGING_SMOKE_EMPRESA_EMAIL`
- `STAGING_SMOKE_EMPRESA_PASSWORD`
- `STAGING_SMOKE_GOVERNO_EMAIL`
- `STAGING_SMOKE_GOVERNO_PASSWORD`
- `STAGING_SMOKE_OPERACAO_EMAIL`
- `STAGING_SMOKE_OPERACAO_PASSWORD`

O workflow foi pensado para rodar manualmente depois de um deploy em staging e falhar se faltar URL base ou credencial autenticada.

## 6. Quando bloquear deploy

Nao publique em producao se qualquer item abaixo falhar:

- login em staging
- dashboard setorial
- tela de gestao setorial
- console operacional
- endpoints publicos basicos

## 7. Proximo passo ideal

Depois de validar o script manualmente, plugue o smoke remoto no pipeline de staging com:

1. deploy para staging
2. execucao de `./scripts/smoke_platform.sh`
3. promocao manual para producao somente se staging estiver verde
