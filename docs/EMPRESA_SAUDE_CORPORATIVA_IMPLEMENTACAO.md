# Implementacao incremental do modulo empresa

Guia de execucao para transformar o ambiente `empresa` em um modulo proprio de saude corporativa sem quebrar os ambientes epidemiologicos.

## Objetivo

Construir o novo produto em camadas, validando contrato de dados, privacidade e experiencia antes de substituir a experiencia atual do ambiente `empresa`.

## Principios

- nao quebrar `governo`, `hospital` e `farmacia`
- nao reutilizar `RegistroSintoma` como base principal do corporativo
- isolar o dominio corporativo
- preservar autenticacao, billing e tenancy
- ativar o novo ambiente por feature flag ou pacote

## Fase 0: preparacao

### Entregas

- blueprint aprovado
- decisao de nomenclatura do produto
- definicao de MVP
- definicao de regras de anonimato

### Saidas tecnicas

- documento de produto
- dicionario de dados inicial
- lista de rotas

## Fase 1: fundacao de dominio

### Back-end

- criar app Django `corporativo` ou modulo equivalente
- criar models base:
  - `EmpresaUnidade`
  - `EmpresaSetor`
  - `EmpresaTurno`
  - `ColaboradorAliasAnonimo`
  - `CheckinDiarioCorporativo`
  - `CheckinSemanalCorporativo`
  - `ResumoAgregadoCorporativo`

### Regras

- empresa continua sendo tenant raiz
- todos os modelos novos referenciam `Empresa`
- agregacao passa por camada propria

### Cuidado

- nao tocar nos fluxos de `dashboard_farmacia`, `dashboard_hospital` e `dashboard_governo`

## Fase 2: app do colaborador

### Escopo

- endpoint de onboarding
- endpoint de check-in diario
- endpoint de check-in semanal
- endpoint de sinais
- endpoint de pedido de apoio

### UX

- texto simples
- feedback rapido
- foco em 30-60 segundos por interacao

## Fase 3: dashboard empresa MVP

### Escopo

- nova rota `/dashboard-empresa/`
- home executiva
- modulo saude mental
- modulo saude fisica
- modulo unidades
- modulo alertas IA

### Implementacao

- nao adaptar `dashboard_unificado.html`
- criar template proprio em `templates/corporativo/dashboard_empresa.html`

## Fase 4: IA corporativa

### Entradas

- check-ins diarios
- check-ins semanais
- sinais por unidade/setor/turno
- contexto epidemiologico externo opcional

### Saidas

- alertas
- score de risco
- recomendacoes de campanha
- plano de acao por unidade

## Fase 5: governanca

### Entregas

- grupos minimos
- mascaramento de dados
- limites de filtro
- auditoria de visualizacao
- consentimento e politicas

## Fase 6: migracao de experiencia

Quando o modulo novo estiver utilizavel:

- `empresa` deixa de apontar para o dashboard unificado atual
- `empresa` passa a apontar para `/dashboard-empresa/`
- hospital/farmacia/governo permanecem iguais

## Estrategia de rollout

### Opcao recomendada

- liberar por feature flag ou pacote
- manter ambiente empresa antigo por um periodo de transicao
- ativar o novo dashboard apenas para contas selecionadas

## Ordem sugerida das proximas implementacoes

1. criar o app/modulo `corporativo`
2. criar os models base e migrations
3. criar APIs de check-in
4. criar home executiva do dashboard empresa
5. criar leitura agregada minima
6. adicionar IA corporativa MVP
7. conectar com contexto externo do SolusCRT

## Definicao de pronto do MVP

O MVP pode ser considerado pronto quando:

- colaborador consegue enviar check-in diario
- empresa consegue ver agregado por unidade/setor
- IA produz pelo menos um resumo executivo e um alerta utilizavel
- anonimato esta protegido por regras de exibicao
- modulo empresa opera sem qualquer regressao nos ambientes epidemiologicos
