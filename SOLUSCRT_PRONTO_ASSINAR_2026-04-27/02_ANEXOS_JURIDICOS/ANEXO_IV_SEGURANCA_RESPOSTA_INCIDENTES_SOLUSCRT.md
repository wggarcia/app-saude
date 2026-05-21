# ANEXO IV — POLÍTICA DE SEGURANÇA DA INFORMAÇÃO E RESPOSTA A INCIDENTES

**Versão:** 1.0.0
**Data:** 21/05/2026
**Vínculo:** Anexo obrigatório de todos os contratos SolusCRT (B2B e B2G)

---

## 1. Objetivo

Definir os controles de segurança da informação implementados pela SolusCRT e o processo de detecção, contenção, comunicação e recuperação em incidentes de segurança, em conformidade com:

- LGPD Art. 46–49 (segurança e sigilo de dados pessoais);
- Resolução CD/ANPD n.º 2/2022 (comunicação de incidentes);
- ISO/IEC 27001:2022 (referência de controles, sem certificação formal neste momento);
- NIST SP 800-61r3 (referência de resposta a incidentes).

---

## 2. Arquitetura de Segurança da Plataforma

### 2.1 Autenticação e Autorização
- Autenticação por JWT (RS256) com validade máxima de 12 horas;
- Sessão com chave de rotação (`sessao_ativa_chave`) — invalidação imediata de sessões concorrentes;
- Controle de dispositivos autorizados por conta (`max_dispositivos`);
- Controle de usuários simultâneos (`max_usuarios`);
- Rate limiting por IP e por conta via Redis (proteção contra brute-force e DDoS camada de aplicação);
- Segregação de acesso por perfil de conta: empresa / governo / admin / operadora de plano de saúde.

### 2.2 Proteção de Dados
- TLS 1.2+ em todos os endpoints (HTTPS obrigatório em produção);
- Senhas armazenadas exclusivamente como hash (PBKDF2-SHA256, iterações compatíveis com OWASP);
- Dados sensíveis de saúde isolados por tenant (sem vazamento entre contas);
- Cookies `HttpOnly`, `SameSite=Lax`, `Secure` em produção;
- CSRF protection habilitado (Django CSRF middleware);
- Cabeçalhos de segurança: HSTS, X-Frame-Options, X-Content-Type-Options, CSP básico.

### 2.3 Infraestrutura
- Hospedagem na **Render Services, Inc.** (Oregon, EUA) com garantias SOC 2 Type II;
- Banco de dados PostgreSQL gerenciado com backups diários automatizados;
- Cache Redis isolado por conta;
- Variáveis de ambiente e segredos gerenciados exclusivamente via Render Secrets (nunca em repositório);
- Repositório com acesso restrito — PRs revisadas antes de merge em `main`.

### 2.4 Trilha de Auditoria
- Registro de login, logout, criação/modificação/exclusão de entidades críticas;
- Logs de acesso por dispositivo e IP;
- Logs de alertas emitidos e aprovados (módulo governo);
- Retenção mínima de 5 anos (Marco Civil, Art. 15).

---

## 3. Gestão de Vulnerabilidades

| Ação | Frequência |
|---|---|
| Rotação de JWT_SECRET_KEY e DJANGO_SECRET_KEY | A cada 90 dias ou em suspeita de comprometimento |
| Rotação de ASAAS_API_KEY e tokens de terceiros | A cada 180 dias ou imediatamente após rescisão de acesso |
| Atualização de dependências (pip, Flutter) | Revisão mensal; patches críticos em até 48h |
| Revisão de permissões de acesso (usuários internos) | Trimestral |
| Análise de logs de acesso anômalos | Semanal |

---

## 4. Classificação de Incidentes

| Severidade | Definição | Exemplos |
|---|---|---|
| **P1 — Crítico** | Comprometimento de dados pessoais ou sensíveis em escala; indisponibilidade total da produção | Vazamento de banco; ransomware; acesso não autorizado a dados de saúde |
| **P2 — Alto** | Comprometimento de uma conta específica; funcionalidade crítica indisponível | Sequestro de sessão; falha em pagamentos; indisponibilidade parcial >4h |
| **P3 — Médio** | Anomalia de segurança sem comprometimento confirmado de dados; performance degradada | Tentativas de força bruta detectadas; lentidão >30min |
| **P4 — Baixo** | Evento informacional; vulnerabilidade sem exploração confirmada | Dependência desatualizada; alerta de monitoramento isolado |

---

## 5. Processo de Resposta a Incidentes

### Fase 1 — Detecção e Triagem (0–2 horas)
1. Identificação do evento por monitoramento automatizado, reporte de usuário ou auditoria;
2. Triagem inicial: confirmar se é incidente real ou falso positivo;
3. Classificação de severidade (P1–P4);
4. Notificação do responsável técnico de plantão.

### Fase 2 — Contenção (2–6 horas para P1/P2)
1. Isolamento imediato do vetor de comprometimento (revogação de sessões, bloqueio de IP, desativação de conta comprometida);
2. Preservação de evidências: snapshots do banco, logs de acesso, registros de rede;
3. Avaliação do escopo: quais contas, dados e períodos foram afetados.

### Fase 3 — Comunicação (conforme cronograma abaixo)

| Destinatário | Prazo | Canal |
|---|---|---|
| Clientes afetados (P1/P2) | Até 72h após confirmação | E-mail + plataforma |
| ANPD (se dados pessoais afetados) | Até 72h após confirmação (Res. CD/ANPD n.º 2/2022) | Portal gov.br/anpd |
| ANS (se dados de beneficiários plano de saúde) | Conforme normativa vigente | Portal ANS |
| Clientes (P3) | Até 7 dias | E-mail |

A comunicação aos Clientes incluirá, no mínimo:
- Data e hora de detecção do incidente;
- Natureza e categorias de dados potencialmente afetados;
- Número aproximado de titulares afetados;
- Medidas de contenção adotadas;
- Plano de mitigação e prevenção de recorrência;
- Contato do responsável pelo incidente.

### Fase 4 — Erradicação e Recuperação
1. Remoção da causa raiz;
2. Restauração de backup (quando necessário) com validação de integridade;
3. Reforço de controles de segurança no ponto de falha;
4. Validação funcional antes de retorno à produção.

### Fase 5 — Pós-Incidente
1. Post-mortem documentado em até 15 dias úteis;
2. Identificação de melhorias de processo e técnicas;
3. Atualização do plano de resposta, se aplicável;
4. Comunicação de encerramento ao Cliente e à ANPD.

---

## 6. Testes e Simulações

| Atividade | Frequência |
|---|---|
| Teste de restauração de backup | Trimestral |
| Revisão do plano de resposta a incidentes | Anual |
| Teste de procedimento de rotação de segredos | Semestral |
| Verificação de acesso de ex-colaboradores/fornecedores | No desligamento e trimestralmente |

---

## 7. Contatos de Emergência de Segurança

- **Incidente de segurança (24h):** privacidade@soluscrt.com.br — assunto: `[INCIDENTE P1]`
- **Responsável técnico:** Wagner Garcia — soluscrtsaude@gmail.com
- **ANPD (relato de incidente):** https://www.gov.br/anpd/pt-br/assuntos/incidentes

---

## 8. Responsabilidade do Cliente

O Cliente (Controlador) é responsável por:
- Implementar autenticação multifator (2FA) para seus usuários administrativos quando disponível;
- Gerir acessos de seus colaboradores e revogar prontamente acessos de desligados;
- Notificar a SolusCRT imediatamente ao suspeitar de comprometimento de credenciais;
- Não compartilhar tokens de API, senhas ou credenciais com terceiros não autorizados.

---

*Este Anexo integra o contrato de prestação de serviços SolusCRT e tem validade equivalente ao instrumento principal.*

*Versão 1.0.0 — 21/05/2026*
