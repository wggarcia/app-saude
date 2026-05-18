# Monolith First Cut - SolusCRT Saude

Este plano define o primeiro corte seguro de refatoracao para reduzir risco sem travar entrega.

## 1. Principio

Nao comecar quebrando tudo em microservicos.

Primeiro objetivo: transformar o monolito atual em um monolito modular com fronteiras claras.

## 1.1 Status atual

- `Corte 1` iniciado e ja aplicado com extracao de auth/sessao para `api/services/auth_session.py`
- `Corte 2` iniciado com extracao de funcoes de setor, onboarding e resumo operacional para `api/services/dashboard_core.py`
- `Corte 2` avancou com command center e premium suite movidos de `api/views_enterprise.py` para `api/services/enterprise_dashboard.py`
- proximo alvo dentro de dashboard: separar agregadores por setor sem mudar rotas publicas

## 2. Ordem recomendada

### Corte 1 - Auth e sessao

Arquivos de origem:

- `api/views_auth.py`
- `api/middleware.py`
- `api/access_control.py`
- partes de `api/views_dashboard.py`

Destino:

- `api/services/auth_session.py`
- `api/services/device_registry.py`
- `api/services/token_service.py`

Motivo:

- login e sessao sao o coracao do produto
- esse fluxo ja esta sendo exercitado por CI e smoke
- melhora seguranca e reduz regressao transversal

### Corte 2 - Dashboards setoriais

Arquivos de origem:

- `api/views_dashboard.py`
- `api/views_enterprise.py`

Destino:

- `api/services/dashboard_core.py`
- `api/services/dashboard_farmacia.py`
- `api/services/dashboard_hospital.py`
- `api/services/dashboard_governo.py`

Motivo:

- hoje o acoplamento entre tela, autenticacao e agregacao de dados esta alto

### Corte 3 - Operacao Farmacia

Arquivos de origem:

- `api/views_farmacia_ops.py`
- `api/views_farmacia_avancado.py`
- `api/views_lotes_farmacia.py`
- `templates/farmacia_gestao.html`

Destino:

- `api/services/farmacia/estoque.py`
- `api/services/farmacia/dispensacao.py`
- `api/services/farmacia/lotes.py`
- componentes HTML parciais menores

Motivo:

- e uma das areas mais ricas e com maior potencial comercial
- ja vimos na pratica que o template ficou grande demais

## 3. Regra de extracao

Cada corte deve obedecer:

1. sem alterar contrato de rota se nao for necessario
2. sem mover tudo de uma vez
3. extrair primeiro logica pura
4. manter testes cobrindo o comportamento anterior
5. medir diff de risco por deploy

## 4. Definicao de pronto por corte

Um corte so termina quando:

- CI continua verde
- smoke continua verde
- nenhum endpoint perdeu compatibilidade
- o arquivo original diminuiu materialmente
- a nova fronteira tem testes proprios
