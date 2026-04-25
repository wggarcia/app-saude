# SolusCRT Saude - Padrao de SLA e Operacao de Suporte

## 1. Objetivo
Padronizar como o time de apoio atua em incidentes, chamados, comunicacao com clientes e escalonamento tecnico, mantendo previsibilidade e qualidade na operacao da SaaS.

**Diretriz obrigatoria:** a operacao interna de monitoramento e resposta a incidentes criticos e **24x7**, independentemente do plano comercial do cliente.

## 2. Escopo
- Painel Empresa
- Painel Governo
- Painel Operacao (Admin)
- APIs backend e jobs de dados oficiais
- App populacional (iOS/Android) em integracao com backend

## 3. Niveis de SLA (externo, para cliente)
### SLA Essencial
- Disponibilidade alvo: 99,5% mensal
- Atendimento: dias uteis, 8x5
- Primeiro retorno:
  - Critico (P1): ate 4h uteis
  - Alto (P2): ate 8h uteis
  - Medio/Baixo (P3/P4): ate 1 dia util

### SLA Profissional
- Disponibilidade alvo: 99,9% mensal
- Atendimento: 12x6
- Primeiro retorno:
  - P1: ate 1h
  - P2: ate 4h
  - P3/P4: ate 1 dia util

### SLA Critico
- Disponibilidade alvo: 99,95% mensal
- Atendimento: 24x7
- Primeiro retorno:
  - P1: ate 30 min
  - P2: ate 2h
  - P3/P4: ate 1 dia util

## 4. Severidade de incidentes (interno)
- P1 Critico:
  - indisponibilidade total
  - falha de login generalizada
  - perda de dados em andamento
  - cobranca indisponivel para todos
- P2 Alto:
  - funcionalidade central degradada sem parar tudo
  - envio de alerta com taxa alta de falha
- P3 Medio:
  - erro com contorno
  - lentidao localizada
- P4 Baixo:
  - ajuste visual, texto, pequenos bugs sem impacto severo

## 5. Tempos internos de acao (SLO operacional)
- P1:
  - triagem: 15 min
  - dono tecnico definido: 15 min
  - mitigacao inicial: 60 min
  - update para cliente: a cada 60 min
- P2:
  - triagem: 30 min
  - mitigacao: 4h
  - update para cliente: a cada 4h
- P3:
  - triagem: 1 dia util
  - resolucao: 5 dias uteis
- P4:
  - triagem: 2 dias uteis
  - resolucao: backlog planejado

## 6. Fluxo operacional (passo a passo)
1. Receber chamado (portal, email, WhatsApp corporativo).
2. Registrar ticket com:
   - cliente
   - ambiente
   - severidade inicial
   - evidencias (print, horario, URL, request ID)
3. Confirmar recebimento ao cliente com numero do ticket.
4. Executar triagem tecnica.
5. Classificar severidade final (P1 a P4).
6. Acionar responsavel da fila correta (suporte/app/backend/dados).
7. Aplicar mitigacao.
8. Comunicar status no prazo de SLA.
9. Validar com cliente.
10. Encerrar ticket com causa raiz e acao preventiva.

## 7. Regras de escalonamento
- P1 sempre escala para:
  - Lider de suporte
  - Lider tecnico backend
  - Responsavel de produto/operacao
- P2 escala em ate 2h se sem mitigacao.
- 2 falhas repetidas no mesmo modulo em 7 dias: abrir incidente de problema recorrente.

## 8. Runbook rapido por tipo de incidente
### 8.1 Falha em pagamento/assinatura
- Verificar:
  - `PAYMENT_PROVIDER`
  - `ASAAS_API_KEY`
  - `ASAAS_BASE_URL`
  - `ASAAS_WEBHOOK_TOKEN`
  - webhook no Asaas
- Confirmar log da rota `/api/assinatura/...`.
- Se erro 401/invalid token: revisar chave/ambiente.
- Se erro 500: capturar corpo do erro e registrar no ticket.

### 8.2 Alerta governo nao chega no app
- Verificar tokens ativos.
- Verificar push provider configurado.
- Publicar alerta de teste com recorte controlado.
- Checar entrega/falhas por token.

### 8.3 Empresa bloqueada por plano nao ativo
- Confirmar status `Empresa.ativo`.
- Confirmar webhook de pagamento processado.
- Reprocessar confirmacao quando necessario.

## 9. Comunicacao padrao com cliente
### Confirmacao de recebimento
"Recebemos seu chamado [ID]. Nossa triagem inicial foi iniciada e retornaremos em ate [prazo do SLA]."

### Em andamento
"Seu chamado [ID] esta em tratamento com nosso time tecnico. Proxima atualizacao ate [horario]."

### Resolvido
"O chamado [ID] foi resolvido. Causa raiz: [resumo]. Acao preventiva: [resumo]."

## 10. Indicadores semanais (obrigatorios)
- volume de tickets por severidade
- tempo medio de 1o retorno
- tempo medio de resolucao
- taxa de reincidencia (7/30 dias)
- disponibilidade mensal por ambiente

## 11. Governanca e auditoria
- Todo P1/P2 exige post-mortem.
- Todo post-mortem deve conter:
  - linha do tempo
  - causa raiz
  - impacto
  - correcoes aplicadas
  - prevencao futura

## 12. Operacao 24x7 (NOC-lite) - padrao minimo
### 12.1 Time minimo para sustentar 24x7 no inicio comercial
- 1 Lider de Operacao (voce/fundador), responsavel por decisao final e comunicacao executiva.
- 2 Engenheiros (backend/integracoes + app/plataforma), em escala de sobreaviso.
- 2 Analistas de Suporte N1/N2, cobrindo triagem e atendimento inicial.
- 1 Analista de Implantacao/CS, para onboarding e continuidade com cliente.

### 12.2 Escala recomendada
- Janela comercial (08:00-20:00): suporte ativo + engenharia de plantao.
- Madrugada (20:00-08:00): sobreaviso P1/P2 com acionamento em ate 15 minutos.
- Fim de semana/feriado: sobreaviso integral com rota de escalonamento definida.

### 12.3 Regra de acionamento
- Alerta automatico P1: abre incidente e notifica canal de plantao imediatamente.
- Sem acknowledge em 10 min: escalar para segundo responsavel.
- Sem mitigacao em 30 min: escalar para lider de operacao.

## 13. Monitoramento ativo 24x7 - checklist obrigatorio
### 13.1 Sinais tecnicos monitorados
- Uptime HTTP (empresa, governo, admin e endpoints publicos).
- Latencia P95/P99 das rotas criticas (`/api/login`, `/api/assinatura`, `/api/webhook`, `/api/governo/alertas/fluxo`).
- Taxa de erro 5xx/4xx por endpoint.
- Filas e falhas de push (FCM/APNs).
- Falhas de webhook Asaas por codigo de erro.
- CPU/RAM/disco da aplicacao e banco.
- Jobs oficiais (execucao, atraso e falha).

### 13.2 Alertas minimos
- P1: indisponibilidade total, erro em pagamento, falha webhook em producao, login indisponivel.
- P2: degradacao persistente de latencia, falha parcial de push, alta reincidencia de erro funcional.
- P3: anomalias de desempenho sem impacto massivo.

### 13.3 Rotina diaria de operacao
1. Revisar painel de disponibilidade ultimas 24h.
2. Revisar erros P1/P2 e reincidencias.
3. Revisar webhook/pagamento/push.
4. Revisar incidentes abertos e risco de SLA.
5. Registrar plano de acao do dia.

## 14. Cadencia de governanca operacional
- Daily operacional: 15 minutos, todos os dias.
- Reuniao semanal de incidentes: 60 minutos.
- Revisao mensal de SLA (diretoria): disponibilidade, MTTR, reincidencia, riscos comerciais.

## 15. Meta operacional para go comercial
- Cobertura de monitoramento 24x7 ativa.
- Escala de plantao publicada e testada.
- 100% dos P1 com post-mortem em ate 48h.
- Indicador de primeira resposta dentro do SLA >= 95%.
