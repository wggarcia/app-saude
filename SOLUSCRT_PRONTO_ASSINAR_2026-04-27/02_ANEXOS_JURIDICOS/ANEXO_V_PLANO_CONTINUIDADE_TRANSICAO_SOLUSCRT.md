# ANEXO V — PLANO DE CONTINUIDADE DE SERVIÇO E TRANSIÇÃO DE DADOS

**Versão:** 1.0.0
**Data:** 21/05/2026
**Vínculo:** Anexo obrigatório do Contrato B2G; recomendado para B2B com volume >500 usuários

---

## 1. Objetivo

Garantir a continuidade operacional da plataforma SolusCRT durante eventos adversos e assegurar ao Cliente um processo organizado, seguro e completo de transição de dados em caso de encerramento contratual.

---

## 2. Continuidade de Serviço

### 2.1 Arquitetura de Resiliência

| Componente | Configuração | Impacto em falha |
|---|---|---|
| Render Web Service | Plano Starter com auto-restart | Reinício automático em <2 min |
| PostgreSQL (Render DB) | Backup diário automatizado | Recuperação com RPO de até 24h |
| Redis (Render Redis) | In-memory cache | Perda de sessões ativas; re-login necessário |
| CDN/Static Assets | Render CDN | Fallback para origin server |
| Workers Cron (SLA, SST, Trial) | Render Cron Jobs | Próxima execução no ciclo seguinte |

### 2.2 Objetivos de Recuperação

| Métrica | Meta (Plano Essencial) | Meta (Plano Profissional) | Meta (Plano Crítico) |
|---|---|---|---|
| RTO (Recovery Time Objective) | 4 horas | 2 horas | 30 minutos |
| RPO (Recovery Point Objective) | 24 horas | 4 horas | 1 hora |
| Disponibilidade mensal alvo | 99,5% | 99,7% | 99,9% |

### 2.3 Procedimento de Recuperação após Desastre

1. **Detecção:** monitoramento automatizado (Render Health Check em `/api/public/resumo`);
2. **Acionamento:** responsável técnico notificado em até 15 minutos via alerta do Render;
3. **Avaliação:** determinar se é falha de aplicação, infraestrutura ou banco;
4. **Recuperação de aplicação:** redeploy forçado via pipeline CI/CD (`git push origin main`);
5. **Recuperação de banco:** restauração do snapshot mais recente via Render Postgres Console;
6. **Validação:** smoke test nos endpoints críticos (`/api/public/resumo`, `/api/login`, `/api/plano-saude/dashboard`);
7. **Comunicação:** notificação ao Cliente no prazo do SLA contratado;
8. **Documentação:** registro do evento, causa raiz e ação corretiva.

### 2.4 Manutenções Programadas

- Janela preferencial: domingos entre 02h00 e 05h00 BRT;
- Comunicação prévia: mínimo 48 horas para manutenções planejadas;
- Manutenções emergenciais: notificação simultânea ao início;
- Canal de comunicação: e-mail ao administrador da conta + banner na plataforma.

---

## 3. Transição de Dados — Encerramento Contratual

### 3.1 Gatilhos de Transição

A fase de transição é ativada em qualquer dos seguintes cenários:
- Encerramento por vencimento de prazo sem renovação;
- Rescisão por comum acordo;
- Rescisão unilateral por descumprimento;
- Migração do Cliente para outra plataforma;
- Encerramento das operações da SolusCRT (ver cláusula 5).

### 3.2 Cronograma de Transição

| Fase | Prazo | Ação |
|---|---|---|
| **T-30 dias** | 30 dias antes do encerramento | SolusCRT notifica o Cliente sobre início da janela de exportação |
| **T-15 dias** | 15 dias antes | Cliente nomeia responsável técnico de transição |
| **T-0 (encerramento)** | Data de encerramento | Acesso de leitura mantido por 30 dias corridos |
| **T+30 dias** | 30 dias após encerramento | Acesso encerrado; dados entram em processo de anonimização/exclusão |
| **T+60 dias** | 60 dias após encerramento | Confirmação de exclusão ou anonimização enviada ao Cliente |

### 3.3 Formatos de Exportação Disponíveis

| Módulo / Dado | Formato | Endpoint / Método |
|---|---|---|
| Beneficiários (Plano de Saúde) | JSON, CSV | `/api/plano-saude/odontologia/` + scripts de exportação |
| Guias de Autorização | JSON | `/api/plano-saude/regulatorio/gerar/` (tipo=TISS) |
| Sinistros | JSON, CSV | Export via painel admin |
| Funcionários SST | JSON, CSV | Export via painel admin |
| Dados epidemiológicos | JSON | API pública + export admin |
| Logs de auditoria | JSON | Solicitação formal ao suporte |
| Faturamento / Notas | PDF, JSON | Painel financeiro |

### 3.4 Responsabilidade pelo Processo

- **SolusCRT:** disponibilizar os dados no formato acordado, garantir integridade e autenticidade;
- **Cliente:** executar a exportação dentro da janela de 30 dias, validar integridade dos dados recebidos e confirmar conclusão por escrito;
- Dados não exportados dentro da janela são de responsabilidade exclusiva do Cliente quanto à perda.

### 3.5 Suporte Técnico na Transição

- Plano Essencial: suporte por e-mail para dúvidas de exportação;
- Plano Profissional: até 4 horas de assistência técnica remota para transição;
- Plano Crítico: até 16 horas de assistência técnica remota + transferência de conhecimento.

---

## 4. Continuidade em Caso de Incidente de Segurança

Em caso de incidente que afete a integridade dos dados do Cliente:

1. SolusCRT notifica o Cliente em até 72h (conforme Anexo IV);
2. Avaliação conjunta do impacto nos dados do Cliente;
3. Disponibilização de exportação emergencial dos dados não corrompidos;
4. Plano de recuperação documentado e compartilhado com o Cliente;
5. Se dados do Cliente forem irrecuperáveis, SolusCRT apresentará relatório forense.

---

## 5. Continuidade em Caso de Encerramento da SolusCRT

Na eventualidade de encerramento das operações da SolusCRT (cessação de atividade, insolvência, venda da empresa):

5.1. O Cliente será notificado com antecedência mínima de **90 dias**;

5.2. Os dados do Cliente permanecerão disponíveis para exportação por **90 dias** após a notificação, sem custo adicional;

5.3. A SolusCRT disponibilizará, mediante solicitação formal, um dump completo do banco de dados do Cliente em formato PostgreSQL padrão (`.sql`), garantindo portabilidade total;

5.4. Segredos técnicos necessários para operação autônoma (chaves de API de terceiros do Cliente, documentação de APIs) serão entregues ao Cliente;

5.5. Essa cláusula constitui obrigação irrevogável e sobrevive ao encerramento do contrato principal.

---

## 6. Confidencialidade na Transição

Todos os dados exportados e qualquer documentação técnica compartilhada durante a transição estão sujeitos às cláusulas de confidencialidade do NDA bilateral (Anexo II) pelo prazo de 5 anos.

---

## 7. Registro e Evidência

Ao final do processo de transição, as Partes firmarão **Termo de Encerramento** registrando:
- Data de conclusão da exportação;
- Formatos e volumes de dados entregues;
- Confirmação de exclusão/anonimização dos dados pela SolusCRT;
- Liberação de responsabilidades mútuas (quitação).

---

*Este Anexo integra o contrato de prestação de serviços SolusCRT e tem validade equivalente ao instrumento principal.*

*Versão 1.0.0 — 21/05/2026*
