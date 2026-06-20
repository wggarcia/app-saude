# ADDENDUM — MÓDULO PLANO DE SAÚDE (ANS)

**Versão:** 1.0.0
**Data:** 21/05/2026
**Vínculo:** Adendo obrigatório ao contrato principal quando o módulo `plano_saude_operadora` ou `plano_saude_enterprise` for contratado pela CONTRATANTE.

---

## Preâmbulo

Este Addendum complementa o Contrato de Prestação de Serviços Healthtech SolusCRT e o Anexo DPA/LGPD para regular especificamente o tratamento de dados pessoais e sensíveis de beneficiários de planos de saúde, em conformidade com:

- **LGPD** — Lei n.º 13.709/2018, especialmente Art. 11 (dados sensíveis de saúde);
- **Lei n.º 9.656/1998** — Lei dos Planos de Saúde;
- **RN ANS n.º 395/2016** — Prazos máximos de autorização de procedimentos (SLA ANS);
- **RN ANS n.º 452/2020** — Atualização de prazos e coberturas;
- **RN ANS n.º 566/2022** — Rol de procedimentos e eventos em saúde;
- **RN ANS n.º 305/2012** — Prazo de retenção de prontuários e dados de saúde;
- **Resolução Normativa TISS** — Padrão de troca de informação em saúde suplementar;
- **Resolução Normativa DIOPS** — Informações periódicas das operadoras;
- **Lei n.º 13.787/2018** — Prontuário eletrônico do paciente.

---

## 1. Dados Tratados no Módulo Plano de Saúde

### 1.1 Classificação como Dados Sensíveis (LGPD Art. 5.º, II e Art. 11)

Os seguintes dados tratados no módulo são classificados como **dados pessoais sensíveis** e recebem proteção máxima:

- Diagnósticos (CID), doenças e condições de saúde dos beneficiários;
- Histórico de procedimentos, internações, cirurgias e medicamentos;
- Guias de autorização (TISS) e respectivos pareceres;
- Sinistros e informações de utilização do plano;
- Dados de saúde bucal (módulo odontológico);
- Resultados de auditorias médicas e scores de risco;
- Dados de telemedicina e consultas remotas.

### 1.2 Base Legal Aplicável

| Finalidade | Base Legal |
|---|---|
| Gestão operacional do plano pela operadora contratante | LGPD Art. 11, II, "b" — cumprimento de obrigação legal/regulatória da operadora (ANS) |
| Auditoria médica interna pela operadora | LGPD Art. 11, II, "b" — obrigação legal / Art. 11, II, "g" — tutela da saúde por serviço de saúde |
| Comunicação com beneficiários sobre autorizações e coberturas | LGPD Art. 11, II, "a" — consentimento **ou** Art. 11, II, "b" — obrigação contratual/legal |
| Geração de relatórios regulatórios (DIOPS, SIB, TISS) | LGPD Art. 11, II, "b" — obrigação legal junto à ANS |
| Detecção de fraude e abuso | LGPD Art. 11, II, "g" — tutela da saúde / Art. 7.º, IX — interesse legítimo |
| Telemedicina | LGPD Art. 11, II, "a" — consentimento do beneficiário **e** Art. 11, II, "g" |

---

## 2. Papel da SolusCRT no Contexto ANS

2.1. A **CONTRATANTE** (operadora de plano de saúde) é a **Controladora** dos dados de seus beneficiários para fins de LGPD e é a pessoa jurídica diretamente regulada pela ANS.

2.2. A **SolusCRT** atua exclusivamente como **Operadora** (LGPD Art. 5.º, VII) dos dados de saúde dos beneficiários, processando-os conforme as instruções documentadas da CONTRATANTE.

2.3. A SolusCRT **não possui** registro de operadora de plano de saúde na ANS e **não toma decisões clínicas**. Toda decisão de autorizar, negar ou revisar procedimentos é de exclusiva responsabilidade da CONTRATANTE e de seus profissionais médicos.

---

## 3. Prazos SLA ANS Implementados na Plataforma

A plataforma monitora automaticamente os prazos da RN ANS n.º 395/2016 e n.º 452/2020:

| Tipo de Procedimento | Prazo ANS | Implementação |
|---|---|---|
| Urgência/Emergência | 4 horas | Monitor em tempo real + alerta imediato |
| Consulta eletiva | 7 dias úteis (≈168h) | Alerta em D-1 do vencimento |
| Exame de alta complexidade | 10 dias úteis (≈240h) | Alerta em D-2 do vencimento |
| Cirurgia/Internação eletiva | 21 dias úteis (≈504h) | Alerta semanal |
| Radioterapia/Quimioterapia | 10 dias úteis (≈240h) | Alerta em D-2 do vencimento |

3.1. O monitoramento é suporte tecnológico; a **responsabilidade de cumprir os prazos ANS é exclusivamente da CONTRATANTE**.

3.2. Falhas nos alertas automáticos da plataforma (ex.: downtime programado) não eximem a CONTRATANTE de suas obrigações regulatórias, sendo dever da operadora manter sistemas de controle próprios complementares.

---

## 4. Auditoria Médica — Limitações e Responsabilidades

4.1. O módulo de auditoria médica da plataforma oferece **indicadores de suporte à decisão** baseados em análise estatística de frequência de sinistros (scoring algorítmico).

4.2. Nenhum score, alerta ou indicador gerado pelo módulo de auditoria constitui:
- Diagnóstico médico;
- Parecer técnico de auditor médico credenciado;
- Fundamento suficiente para negar cobertura sem revisão por profissional médico habilitado.

4.3. A CONTRATANTE é responsável por garantir que toda negativa de cobertura seja fundamentada por médico auditor devidamente inscrito no CRM, conforme Lei n.º 9.656/1998, Art. 12, e Resolução CFM n.º 1.659/2002.

4.4. Qualquer processo regulatório da ANS, ação judicial ou reclamação de beneficiário decorrente de negativa de cobertura é de exclusiva responsabilidade da CONTRATANTE.

---

## 5. Geração de Relatórios Regulatórios (TISS, DIOPS, SIB)

5.1. A plataforma gera **payloads estruturados** nos padrões TISS 3.05.00, DIOPS e SIB para facilitar o cumprimento das obrigações periódicas da operadora junto à ANS.

5.2. Os dados contidos nos relatórios refletem exclusivamente as informações inseridas pela CONTRATANTE na plataforma. A SolusCRT não se responsabiliza por omissões, erros ou inconsistências nos dados de origem.

5.3. A **transmissão efetiva** dos relatórios aos sistemas da ANS é de responsabilidade exclusiva da CONTRATANTE, utilizando suas credenciais de acesso ao portal ANS.

5.4. A SolusCRT não possui integração automática com os sistemas legados da ANS (TISS Web Services, DIOPS online). A exportação é manual via painel da plataforma.

---

## 6. Telemedicina — Conformidade CFM

6.1. O módulo de telemedicina suporta a gestão de autorizações e agendamentos de consultas remotas.

6.2. A SolusCRT **não é** provedora de plataforma de telemedicina. A realização efetiva das teleconsultas ocorre em plataformas parceiras (Conexa, iClinic, DrConsulta ou outra indicada pela operadora).

6.3. A conformidade com a **Resolução CFM n.º 2.314/2022** (telemedicina), incluindo registro em prontuário eletrônico, identificação do médico e consentimento do paciente, é obrigação da CONTRATANTE e do profissional médico responsável.

---

## 7. Retenção de Dados de Saúde dos Beneficiários

Em conformidade com RN ANS n.º 305/2012 e demais normas aplicáveis:

| Tipo de Dado | Prazo Mínimo de Retenção |
|---|---|
| Prontuários / Histórico de procedimentos | 20 anos após o último atendimento |
| Guias de autorização e pareceres | 10 anos |
| Registros de sinistros | 10 anos |
| Dados financeiros do plano (faturamento) | 5 anos (obrigação fiscal) |
| Logs de auditoria interna | 5 anos |

7.1. Durante a vigência contratual, a SolusCRT mantém os dados conforme os prazos acima.

7.2. Ao encerrar o contrato, o prazo de exportação de 30 dias (Contrato Principal, Cláusula 11.2) é improrrogável. **A CONTRATANTE é integralmente responsável por garantir que os dados de saúde dos beneficiários permaneçam acessíveis pelo período legal exigido**, devendo exportá-los e armazená-los em solução própria antes do encerramento.

---

## 8. Comunicação com Beneficiários

8.1. E-mails transacionais enviados pela plataforma em nome da CONTRATANTE (confirmação de autorização, negativa de guia, carta boleto, etc.) são disparados a partir do remetente técnico `noreply@soluscrt.com.br` mas contêm o nome e dados de identificação da CONTRATANTE.

8.2. A CONTRATANTE é responsável por garantir que possui base legal válida para contato com seus beneficiários (contrato de plano de saúde / consentimento).

8.3. Pedidos de opt-out de comunicações por parte de beneficiários devem ser tratados pela CONTRATANTE, que é responsável por atualizar os dados na plataforma.

---

## 9. Acesso de Beneficiários aos Próprios Dados (LGPD Art. 18)

9.1. Requisições de titulares (beneficiários) sobre seus dados de saúde armazenados na plataforma devem ser encaminhadas à CONTRATANTE (Controladora).

9.2. A SolusCRT apoiará a CONTRATANTE fornecendo extrato técnico dos dados do beneficiário mediante solicitação formal documentada, no prazo de até 5 dias úteis.

---

## 10. Segurança Específica para Dados de Saúde

Além dos controles gerais do Anexo IV, aplicam-se aos dados do módulo Plano de Saúde:

- Isolamento de tenant: dados de beneficiários de uma operadora são inacessíveis a qualquer outra conta;
- Campos de diagnóstico (CID) com acesso restrito a perfis com permissão médica;
- Exportação de relatórios regulatórios requer autenticação reforçada;
- Score de auditoria médica não é exposto a beneficiários na plataforma.

---

## 11. Vigência e Hierarquia

Este Addendum entra em vigor na data de ativação do módulo `plano_saude_operadora` ou `plano_saude_enterprise` e vigora enquanto a CONTRATANTE mantiver o módulo ativo. Em caso de conflito com o Contrato Principal, prevalece o Addendum nas matérias específicas a ele.

---

**ASSINATURAS**

**SOLUSCRT (CONTRATADA/OPERADORA)**
Nome: Wagner Garcia
CPF: 091.189.637-65
Assinatura eletrônica: ______________________________________

**CONTRATANTE (OPERADORA DE PLANO DE SAÚDE)**
Razão social: ______________________________________________
Registro ANS n.º: ___________________________________________
Representante legal: _______________________________________
CPF: _______________________________________________________
Cargo: _____________________________________________________
Assinatura eletrônica: ______________________________________

---

*Versão 1.0.0 — 21/05/2026*
