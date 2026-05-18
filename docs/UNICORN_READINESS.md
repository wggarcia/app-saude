# Unicorn Readiness - SolusCRT Saude

Este documento transforma "virar um unicornio" em trabalho objetivo, com prioridades concretas de produto, engenharia e operacao.

## 1. Diagnostico honesto

O repositorio ja mostra uma plataforma com escopo enterprise:

- 2 apps Flutter separados: populacao e ocupacional.
- Backend Django central para epidemiologia, SST, farmacia, hospital, governo e compliance.
- CI com Postgres e testes automatizados.
- Deploy documentado em Render.
- Seguranca basica de producao e Sentry preparados por configuracao.

Mas ainda nao existe "100% de unicornio" porque:

- O monolito cresceu rapido e concentra muito risco em poucos arquivos.
- Parte da operacao ainda depende de checklist manual.
- Staging, backups, monitoramento e smoke tests de producao ainda nao estao completamente automatizados.
- O produto e muito amplo; sem foco comercial rigoroso, breadth vira custo.
- O codigo por si so nao prova market fit, retencao, distribuicao nem ARR.

## 2. North Star real

Objetivo: sair de "produto impressionante" para "maquina repetivel de crescimento e confianca".

Isso exige 5 pilares:

1. Produto com wedge claro.
2. Operacao confiavel.
3. Engenharia escalavel.
4. Seguranca e compliance auditaveis.
5. Go-to-market com metricas de receita e expansao.

## 3. Prioridades P0

Estas sao as entregas que nao podem ficar para depois:

1. Zerar drift de migracoes.
2. Fazer CI falhar em erro real de deploy-check.
3. Bloquear versionamento acidental de segredos, bancos locais e artefatos gerados.
4. Criar staging separado do ambiente oficial.
5. Automatizar smoke test de login, pagamento, mapa e dashboards setoriais.
6. Ligar Sentry real em producao e revisar alertas.
7. Garantir backup e teste de restauracao do banco.

## 4. Prioridades P1

1. Quebrar dominios grandes do backend em modulos mais claros:
   - identidade e sessao
   - faturamento e billing
   - epidemiologia publica
   - operacao farmacia
   - operacao hospital
   - SST / ocupacional
2. Reduzir arquivos gigantes com extracao gradual de servicos, serializers e componentes.
3. Criar testes de smoke por dominio critico.
4. Padronizar observabilidade com metricas reais em vez de placeholders.
5. Formalizar trilha de auditoria para acoes sensiveis.

## 5. Prioridades P2

1. Definir o wedge comercial principal:
   - SST enterprise
   - farmacia/hospital
   - governo / vigilancia
2. Medir:
   - ativacao
   - churn
   - expansao por conta
   - tempo ate go-live
   - uso semanal por perfil
3. Criar playbooks de onboarding e suporte por segmento.
4. Separar roadmap "core platform" de roadmap "customizacoes por vertical".

## 6. Meta dos proximos 90 dias

### 0-30 dias

- CI mais duro
- staging funcional
- backups validados
- Sentry ligado
- smoke tests minimos
- hygiene checks no repositorio

### 31-60 dias

- refatoracao dos maiores pontos de concentracao
- observabilidade real
- reduzir risco de deploy
- playbooks operacionais por setor

### 61-90 dias

- foco no wedge comercial vencedor
- metricas de expansao e retencao
- narrativa de investidor baseada em uso e receita, nao em volume de features

## 7. Definicao de "parece unicornio"

Voce vai estar perto disso quando conseguir dizer, com dados:

- temos um wedge que vende repetidamente
- temos onboarding previsivel
- temos baixa friccao de deploy
- temos confianca operacional
- temos seguranca auditavel
- temos evidencia de expansao de receita por conta

Sem isso, o produto pode ser excelente, mas ainda sera uma plataforma promissora, nao uma maquina de escala.

## 8. Primeiro corte seguro de refatoracao

Arquivo de execucao:

- `docs/MONOLITH_FIRST_CUT.md`

Resumo:

1. auth e sessao
2. dashboards setoriais
3. operacao farmacia

Essa ordem maximiza ganho estrutural sem tentar reescrever a plataforma inteira de uma vez.
