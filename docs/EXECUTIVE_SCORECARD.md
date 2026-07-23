# Executive Scorecard - SoloCRT Saude

Use este scorecard semanal para parar de avaliar o produto por volume de feature e passar a avaliar por capacidade de escala.

## 1. Nota geral

Pontue cada pilar de `0` a `10`.

- Produto
- Engenharia
- Operacao
- Go-to-market
- Receita e expansao
- Compliance e seguranca

## 2. Rubrica

### Produto

- `0-3`: muito amplo, pouca clareza de wedge
- `4-6`: segmentos definidos, mas sem foco comercial dominante
- `7-8`: um wedge vende repetidamente
- `9-10`: expansao organica entre contas e prova clara de valor

### Engenharia

- `0-3`: deploy instavel, sem testes confiaveis
- `4-6`: CI e guardrails existem, mas operacao ainda manual
- `7-8`: staging, smoke e rollback previsiveis
- `9-10`: engenharia acelera sem aumentar risco

### Operacao

- `0-3`: suporte reativo e sem playbook
- `4-6`: processos existem, mas dependem de pessoas-chave
- `7-8`: onboarding, incidentes e go-live padronizados
- `9-10`: operacao previsivel e escalavel

### Go-to-market

- `0-3`: sem tese clara de canal e ICP
- `4-6`: ICP e oferta existem, conversao ainda irregular
- `7-8`: canal repetivel e onboarding comercial padrao
- `9-10`: motor de distribuicao previsivel

### Receita e expansao

- `0-3`: monetizacao sem previsibilidade
- `4-6`: primeiros contratos e renovacoes, pouca expansao
- `7-8`: upsell/cross-sell ja acontecem
- `9-10`: expansao por conta e cohortes saudaveis

### Compliance e seguranca

- `0-3`: dependencia de boa vontade operacional
- `4-6`: boas praticas presentes, evidencias incompletas
- `7-8`: auditoria, logs, backups e acessos sob controle
- `9-10`: seguranca demonstravel para auditoria e venda enterprise

## 3. KPIs obrigatorios da semana

Preencha toda segunda-feira:

- `ARR` ou receita recorrente ativa
- numero de clientes ativos
- numero de clientes em onboarding
- tempo medio ate go-live
- taxa de ativacao por segmento
- taxa de uso semanal por perfil
- incidentes criticos da semana
- tempo medio de resolucao
- deploys bem-sucedidos
- smoke tests verdes / totais
- churn logo / churn de receita
- expansao de receita por conta

## 4. Regra de decisao

Se a nota de `Produto + Go-to-market + Receita` for menor que `Engenharia + Operacao`, o time provavelmente esta construindo mais do que vendendo.

Se a nota de `Engenharia + Operacao + Compliance` for menor que `Produto + Go-to-market`, a empresa pode crescer mais rapido do que consegue sustentar.

## 5. Meta realista de 90 dias

Objetivo: atingir pelo menos:

- Produto `7`
- Engenharia `7`
- Operacao `7`
- Go-to-market `6`
- Receita e expansao `6`
- Compliance e seguranca `7`

Isso nao e um unicornio ainda. Mas ja e um negocio com capacidade real de escalar sem quebrar.
