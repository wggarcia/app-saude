# SolusCRT Saude - Cartilha de Montagem do Time Inicial

## 1. Quantas pessoas contratar no inicio (realista)
Para inicio comercial com controle de custo e qualidade:

- Minimo viavel: 4 pessoas
  - 1 Fundador(a) Operacao/Produto (voce)
  - 1 Engenheiro(a) Full Stack (backend + deploy)
  - 1 Suporte N1/N2 (cliente + triagem)
  - 1 Analista de Implantacao/CS (onboarding + sucesso do cliente)

- Recomendado para operar com folga: 6 pessoas
  - 1 Operacao/Produto
  - 2 Engenharia (backend/plataforma + app/integracoes)
  - 2 Suporte (N1/N2, turnos)
  - 1 CS/Implantacao

## 2. Quantos tecnicos de suporte sao suficientes?
### Fase 1 (0 a 10 clientes pagantes)
- 1 tecnico de suporte dedicado + fundador cobrindo escalonamento.

### Fase 2 (10 a 30 clientes)
- 2 tecnicos de suporte.
- Cobertura de horario comercial com fila e prioridade.

### Fase 3 (30+ clientes ou contratos criticos)
- 3 tecnicos de suporte.
- Plantao para P1 fora do horario.

Regra pratica:
- Ate 15 tickets/dia: 1 tecnico
- 15 a 35 tickets/dia: 2 tecnicos
- 35+ tickets/dia: 3 tecnicos

## 3. Perfil de cada funcao
### Suporte N1/N2
- comunicacao clara com cliente
- leitura de logs e evidencias
- execucao de runbooks
- abertura de bug com contexto tecnico

### Engenharia Plataforma
- incidentes P1/P2
- pagamentos/webhooks/integracoes
- observabilidade e correcoes de causa raiz

### CS/Implantacao
- onboarding
- treinamento cliente
- adocao de produto e renovacao

## 4. Checklist de preparo do time (30 dias)
### Semana 1 - Fundacao
- definir SLA oficial por pacote
- definir matriz de severidade P1-P4
- padronizar canal unico de tickets
- publicar runbook de pagamento, login, alerta e push

### Semana 2 - Operacao
- treinar suporte em 10 cenarios reais
- criar templates de comunicacao com cliente
- criar painel de metricas (tempo de resposta e resolucao)

### Semana 3 - Simulacao
- simular 2 incidentes P1
- simular 3 incidentes P2
- treinar escalonamento e post-mortem

### Semana 4 - Go-live controlado
- liberar clientes por onda (lotes pequenos)
- revisar tickets diarios
- ajustar gargalos de processo

## 5. Rotina diaria do suporte (passo a passo)
1. Abrir painel de monitoramento e tickets.
2. Priorizar P1/P2 antes de qualquer outro.
3. Confirmar recebimento de novos tickets.
4. Executar runbook e coletar evidencias.
5. Escalar quando nao houver mitigacao no tempo alvo.
6. Atualizar cliente conforme SLA.
7. Encerrar com causa raiz e prevencao.

## 6. Regras para nao quebrar operacao
- Nao corrigir em producao sem registrar ticket.
- Toda mudanca critica exige rollback claro.
- Todo erro recorrente vira tarefa de melhoria permanente.
- Sem runbook = nao escala comercial para aquele modulo.

## 7. Indicadores minimos que o time deve bater
- 1o retorno no prazo de SLA: >= 95%
- resolucao P1 no prazo: >= 90%
- reincidencia de incidente critico: < 10% no mes
- satisfacao de atendimento (CSAT): >= 4,5/5

## 8. Ferramentas minimas recomendadas
- ticketing (Jira/Linear/Freshdesk)
- alertas e logs centralizados
- base de conhecimento interna
- canal oficial de status para clientes

## 9. Quando contratar mais gente
- fila media acima de 24h por 5 dias uteis
- 2 ou mais P1 no mesmo mes sem dono fixo
- >30 clientes pagantes sem suporte em dupla

## 10. Plano conciente de contratacao (sugestao)
- Mes 0-2: 1 suporte + 1 engenharia + voce
- Mes 3-6: adicionar 1 suporte (total 2)
- Mes 6-9: adicionar 1 CS/implantacao
- Mes 9+: adicionar 2a engenharia se carga tecnica subir
