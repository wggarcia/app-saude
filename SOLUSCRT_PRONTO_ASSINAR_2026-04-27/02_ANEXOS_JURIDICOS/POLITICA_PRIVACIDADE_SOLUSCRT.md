# POLÍTICA DE PRIVACIDADE — SOLUSCRT SAUDE

**Versão:** 1.0.0
**Vigência:** a partir de 21/05/2026
**Controlador da plataforma:** Wagner Garcia (SolusCRT Saude), CPF 091.189.637-65, Niterói/RJ
**Contato DPO/Privacidade:** privacidade@soluscrt.com.br

---

## 1. Apresentação e Âmbito

Esta Política de Privacidade descreve como a **SolusCRT Saude** ("SolusCRT", "nós") coleta, usa, armazena, compartilha e protege dados pessoais no contexto da plataforma healthtech, do aplicativo móvel e dos serviços correlatos.

Aplica-se a:
- **Administradores e usuários corporativos** de empresas, hospitais, farmácias, operadoras de planos de saúde e órgãos governamentais contratantes ("Clientes");
- **Beneficiários finais** que utilizam o aplicativo móvel para relato de sintomas, acesso a alertas e consulta de informações de saúde pública;
- **Funcionários e colaboradores** cadastrados nas plataformas ocupacionais (SST, ASO, e-Social);
- **Visitantes** do site público soluscrt.com.br e soluscrtsaude.com.br.

Esta Política foi redigida em conformidade com:
- Lei n.º 13.709/2018 (LGPD);
- Lei n.º 12.965/2014 (Marco Civil da Internet);
- Decreto n.º 7.962/2013 (Comércio Eletrônico);
- Lei n.º 8.078/1990 (CDC), no que couber;
- Resoluções normativas da ANS aplicáveis aos módulos de plano de saúde.

---

## 2. Papéis de Tratamento

| Contexto | Controlador | Operador |
|---|---|---|
| Dados da operação do Cliente (funcionários, beneficiários, pacientes) | **O próprio Cliente** (empresa/hospital/governo) | **SolusCRT** |
| Dados da conta SolusCRT (faturamento, autenticação, suporte) | **SolusCRT** | — |
| Dados de saúde pública anonimizados (mapa, alertas) | **SolusCRT** | — |

Como **Operadora** nos dados do Cliente, a SolusCRT age exclusivamente conforme instrução contratual documentada.

---

## 3. Dados Coletados por Categoria

### 3.1 Dados cadastrais e de autenticação
- Nome, e-mail, CPF, cargo, telefone de administradores e usuários;
- Credenciais de acesso (hash seguro; senha jamais armazenada em texto plano);
- Dispositivo de acesso (device_id, device_name) para controle de sessão.

### 3.2 Dados técnicos e de uso
- Endereço IP, tipo de navegador, sistema operacional;
- Logs de acesso, trilha de auditoria de ações administrativas;
- Dados de sessão e cookies essenciais de autenticação.

### 3.3 Dados operacionais (inseridos pelo Cliente)
Variam conforme o módulo contratado. Exemplos:
- **Módulo SST/Empresa:** nome, CPF, cargo, dados de saúde ocupacional (ASO, CAT, afastamentos) dos funcionários;
- **Módulo Hospital:** dados de internação, triagem, prescrições;
- **Módulo Farmácia:** dados de dispensação, receitas, histórico de compras;
- **Módulo Plano de Saúde:** nome, CPF, número de carteirinha, dados de beneficiários, guias de autorização, sinistros, dados de cobertura — **tratados como dados sensíveis (LGPD Art. 11)**;
- **Módulo Governo:** dados epidemiológicos territoriais, indicadores de saúde pública.

### 3.4 Dados do aplicativo móvel (usuário final)
- Localização aproximada (nível de bairro/município) para relato de sintomas — somente com consentimento explícito;
- Sintomas relatados de forma pseudoanonimizada;
- Token push (FCM/APNs) para notificações de alertas;
- Dados de engajamento (telas acessadas, alertas visualizados).

---

## 4. Finalidades e Bases Legais

| Finalidade | Base Legal (LGPD) |
|---|---|
| Autenticação e controle de acesso | Art. 7.º, V — execução de contrato |
| Prestação dos serviços contratados | Art. 7.º, V — execução de contrato |
| Dados sensíveis (saúde) — módulo Plano de Saúde e SST | Art. 11, II, "a" — consentimento do titular **ou** Art. 11, II, "g" — tutela da saúde, exclusivamente por profissional de saúde ou serviço de saúde autorizados |
| Dados sensíveis — gestão de contrato de saúde pelo Cliente | Art. 11, II, "b" — cumprimento de obrigação legal do Controlador (ANS, LGPD, e-Social) |
| Comunicações transacionais (alertas, cobranças, SLA) | Art. 7.º, V — execução de contrato |
| Monitoramento epidemiológico público (anonimizado) | Art. 7.º, IV — interesses legítimos / Art. 7.º, IX — interesse público |
| Prevenção a fraudes e segurança | Art. 7.º, IX — interesse legítimo |
| Cumprimento de obrigação legal (e-Social, ANPD, ANS) | Art. 7.º, II — obrigação legal |
| Faturamento e cobrança | Art. 7.º, V — execução de contrato |

---

## 5. Dados Sensíveis — Tratamento Reforçado

Dados de saúde são classificados como **dados sensíveis** (LGPD Art. 5.º, II) e recebem proteção adicional:

- Acesso restrito a perfis com necessidade operacional comprovada;
- Criptografia em trânsito (TLS 1.2+) e em repouso;
- Trilha de auditoria completa para cada acesso ou modificação;
- Proibição de uso para finalidade comercial não relacionada ao escopo contratado;
- Vedação de compartilhamento com terceiros sem base legal específica.

Para o **módulo Plano de Saúde**, aplica-se adicionalmente o **Addendum ANS** (documento separado neste pacote).

---

## 6. Compartilhamento de Dados

A SolusCRT **não vende** dados pessoais. Compartilhamentos ocorrem somente nas situações abaixo:

| Destinatário | Dados | Finalidade |
|---|---|---|
| Render (infraestrutura) | Todos os dados da plataforma | Hospedagem segura (Render Services, Inc.) |
| Asaas (pagamentos) | Dados de faturamento do Cliente | Processamento de cobrança |
| Firebase (Google) | Token push, analytics pseudoanonimizado | Notificações móveis |
| Zoho Mail | E-mail do destinatário | Envio de comunicações transacionais |
| Autoridades competentes | Conforme ordem judicial ou legal | Cumprimento de obrigação legal |

Todos os suboperadores listados mantêm nível de proteção compatível com LGPD e, no caso de infraestrutura norte-americana, com base nas cláusulas contratuais padrão (SCCs) ou certificações equivalentes.

---

## 7. Retenção de Dados

| Tipo de dado | Prazo de retenção |
|---|---|
| Dados de conta e autenticação | Vigência contratual + 5 anos |
| Logs de auditoria | 5 anos (Marco Civil, Art. 15) |
| Dados de saúde ocupacional (ASO, CAT) | Mínimo de 20 anos (NR-7/Portaria 1.823) |
| Dados de beneficiários plano de saúde | Vigência + 10 anos (ANS RN 305) |
| Dados do app (sintomas, localização) | 30 dias após coleta (anonimizados) |
| Dados de faturamento | 5 anos (obrigação fiscal) |

Após o encerramento do contrato, o Cliente tem **30 dias** para exportar seus dados. Após esse prazo, os dados são anonimizados ou descartados de forma segura.

---

## 8. Direitos dos Titulares

Em conformidade com LGPD Art. 18, o titular de dados pode, perante o **Controlador** (geralmente o Cliente que o empregou ou contratou):

1. **Confirmação** de existência de tratamento;
2. **Acesso** aos dados tratados;
3. **Correção** de dados incompletos ou inexatos;
4. **Anonimização, bloqueio ou eliminação** de dados desnecessários ou tratados em desconformidade;
5. **Portabilidade** a outro fornecedor de serviço;
6. **Eliminação** de dados tratados com consentimento, quando revogado;
7. **Informação** sobre compartilhamentos;
8. **Recusa ou revogação de consentimento**, com informação sobre consequências;
9. **Revisão de decisões automatizadas**.

Para exercer direitos em relação a dados gerenciados pela SolusCRT como **Controladora** (conta da plataforma, faturamento): enviar solicitação para **privacidade@soluscrt.com.br** com identificação do titular e descrição do pedido. Prazo de resposta: até 15 dias úteis.

---

## 9. Cookies

| Categoria | Cookie | Finalidade | Duração |
|---|---|---|---|
| Essencial | `auth_token` | Autenticação segura de sessão | Sessão / 12h |
| Essencial | `empresa_id`, `tipo_conta` | Roteamento correto do usuário | Sessão / 12h |
| Funcional | `owner_token` | Sessão do console administrativo SolusCRT | Sessão |

**Não utilizamos** cookies de rastreamento, publicidade ou analytics de terceiros. Ao realizar login na plataforma, o usuário concorda com o uso dos cookies essenciais listados acima.

---

## 10. Segurança da Informação

Medidas técnicas e organizacionais implementadas:

- Autenticação por JWT com rotação de chave de sessão;
- Controle de acesso por perfil de conta (empresa/governo/admin/operadora de plano);
- HTTPS/TLS em todas as comunicações;
- Rate limiting via Redis;
- Segregação de dados por empresa (multi-tenant isolado);
- Trilha de auditoria persistente e imutável;
- Backup diário automatizado (Render Postgres);
- Rotação periódica de segredos (conforme CHECKLIST_ROTACAO_SEGREDOS_E_ACESSOS.md).

---

## 11. Incidentes de Segurança

Em caso de incidente com risco relevante a titulares:

1. A SolusCRT notificará os Clientes afetados **em até 72 horas** da confirmação do incidente;
2. A ANPD será notificada nos prazos e formas estabelecidos pela Resolução CD/ANPD n.º 2/2022;
3. A comunicação incluirá: natureza do evento, categorias de dados, medidas adotadas e contato do DPO.

Canal de reporte de incidentes: **privacidade@soluscrt.com.br** (24h).

---

## 12. Transferência Internacional de Dados

A plataforma é hospedada na infraestrutura da **Render Services, Inc.** (EUA), com servidores na região `Oregon (US-West)`. A transferência internacional de dados é realizada com base em:

- Cláusulas Contratuais Padrão (SCCs) da Comissão Europeia, aceitas pela ANPD como mecanismo equivalente;
- Cláusulas específicas de segurança e confidencialidade nos contratos com suboperadores.

---

## 13. Menores de Idade

A plataforma SolusCRT não é destinada a menores de 18 anos como usuários corporativos. Para o aplicativo móvel (relato de sintomas), eventuais dados de menores só são coletados com consentimento dos responsáveis legais, conforme LGPD Art. 14.

---

## 14. Alterações desta Política

Alterações relevantes serão comunicadas por e-mail (ao administrador da conta) com antecedência mínima de 15 dias antes da entrada em vigor. A versão vigente sempre estará disponível em **soluscrt.com.br/privacidade** e no rodapé da plataforma.

---

## 15. Contato e DPO

**Responsável pela Privacidade (DPO designado):**
Wagner Garcia
privacidade@soluscrt.com.br
Niterói/RJ — Brasil

Para solicitações de titulares, dúvidas sobre esta Política ou notificações de incidentes, utilizar exclusivamente o e-mail acima.

---

*Última atualização: 21/05/2026 — Versão 1.0.0*
