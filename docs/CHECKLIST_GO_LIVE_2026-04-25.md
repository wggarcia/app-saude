# Checklist Go-Live SolusCRT Saude (25/04/2026)

## Decisao executiva
Status atual: **GO comercial condicional**.

Significado:
- Produto está tecnicamente estável para operar (backend + app validados).
- Liberação em produção depende só de **configuração operacional final** (chaves/ambiente/webhook) e smoke test final após deploy.

## Evidencias tecnicas executadas
- `python3 manage.py check`: OK
- `python3 manage.py test`: OK (**10 testes aprovados**)
- `flutter analyze` em `app_saude`: OK (sem issues)
- `flutter test` em `app_saude`: OK

## Correcoes fechadas nesta rodada
1. Hardening de produção no Django (`backend/settings.py`)
- `DEBUG` por variável de ambiente
- `SECRET_KEY` e `JWT_SECRET_KEY` obrigatórias em produção
- `ALLOWED_HOSTS`, `CORS` e `CSRF_TRUSTED_ORIGINS` controlados por env
- cookies e headers de segurança habilitados

2. Fluxo de pagamento Asaas robusto (`api/views_pagamento.py`)
- validação de `ASAAS_API_KEY` com extração segura (evita erro por texto colado da documentação)
- sanitização de `ASAAS_BASE_URL` (aceita variação com texto extra e mantém URL correta)
- exigência de CPF/CNPJ no checkout
- atualização/criação de cliente Asaas com `cpfCnpj`

3. Dados fiscais da empresa
- novo campo `Empresa.documento_fiscal`
- migration criada: `api/migrations/0008_empresa_documento_fiscal.py`

4. Tela de pagamento (`templates/pagamento.html`)
- campo de CPF/CNPJ obrigatório com validação de 11/14 dígitos
- envio do dado fiscal junto da criação de cobrança

5. App Flutter (qualidade de release)
- correções de async/context e logs em `tela_sintomas.dart`
- suite de testes e análise estáveis para release

## Pendencias operacionais (fora do código)
1. Render (produção)
- aplicar envs corretas:
  - `SECRET_KEY`
  - `JWT_SECRET_KEY`
  - `PAYMENT_PROVIDER=asaas`
  - `ASAAS_API_KEY` (chave real, iniciando com `$aact_prod_`)
  - `ASAAS_BASE_URL=https://api.asaas.com/v3`
  - `ASAAS_USER_AGENT=SolusCRT-Saude/1.0`
  - `ASAAS_WEBHOOK_TOKEN` (mesmo token cadastrado no Asaas)

2. Aplicar migration em produção
- `python3 manage.py migrate`

3. Asaas painel
- Webhook ativo em v3 apontando para:
  - `https://empresa.soluscrt.com.br/api/webhook`
- eventos mínimos habilitados:
  - `PAYMENT_CONFIRMED`
  - `PAYMENT_RECEIVED`
  - `PAYMENT_OVERDUE`
  - `PAYMENT_UPDATED`
  - `SUBSCRIPTION_CREATED` (se usar assinatura recorrente por API)

4. Smoke test final pós-deploy
- criar cobrança real de teste em `/pagamento/`
- confirmar retorno `sucesso/pendente` com `empresa_id`
- confirmar ativação de empresa após webhook
- confirmar login dashboard empresa ativo

## Criterio final de GO
Pode abrir comercial em escala quando:
- envs de produção estiverem corretas no Render
- webhook Asaas ativo + validado
- smoke test de pagamento concluído ponta a ponta
- app mobile em versão estável publicada (Apple/Google)
