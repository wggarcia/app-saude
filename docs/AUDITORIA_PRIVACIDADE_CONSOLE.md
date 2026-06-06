# Auditoria de Privacidade — Console Operação Central (SolusCRT)

**Objetivo:** verificar, endpoint por endpoint e campo por campo, se o console
administrativo do dono da SolusCRT (Operação Central) expõe **dados internos
privados dos clientes** ou apenas **metadados de gestão do contrato**.

**Resultado geral:** ✅ **Aprovado.** Nenhum endpoint do dono expõe dado pessoal
sensível dos titulares dos clientes (pacientes, trabalhadores, beneficiários,
cidadãos). O console trata exclusivamente metadados comerciais/operacionais e
métricas agregadas (contagens), necessários para administrar o SaaS.

Data da auditoria: 2026-06-06 · Escopo: branch `main` (commit no momento da auditoria).

---

## 1. Modelo de isolamento (defesa em camadas)

| Camada | Mecanismo | O que protege |
|---|---|---|
| Banco | **RLS (Row-Level Security)** por `empresa_id` | Conteúdo de cada cliente é isolado; um cliente nunca lê o do outro. A vigilância pública é escopada à empresa `populacao@soluscrt.com`. |
| Autenticação | **owner_token (JWT)** em `owner_paths` | Só a equipe da SolusCRT acessa `/console-operacional/`, `/api/operacao-central/*`, `/financeiro/`, `/governanca/`, `/gtm/`. |
| Autorização | **RBAC por papel** (admin/financeiro/suporte/leitura) | Restringe seção e ação por função; trava real no backend (403). |
| Rastreabilidade | **DonoAuditoriaAcao** | Toda ação do operador é registrada (quem/o quê/quando). |

---

## 2. Classificação de dados expostos no console

- **Identificação da conta** (legítimo — base legal: execução de contrato):
  nome da empresa cliente e e-mail **da conta** (contato comercial/cobrança).
- **Métricas operacionais agregadas** (apenas *números*, sem conteúdo):
  contagem de usuários, dispositivos, registros 24h, suspeitos 24h, % de uso.
- **Comercial**: pacote, plano, ciclo, faturamento estimado, status do contrato,
  data de expiração, progresso de onboarding.
- **Infraestrutura**: latência de banco, cache, status de integrações.
- **Vigilância pública**: dado **anônimo/agregado nacional** do app da população
  (não pertence a nenhum cliente pagante).

### ❌ NUNCA exposto no console
Pacientes, prontuários, ASOs, exames, CIDs/diagnósticos, prescrições, casos
notificados, beneficiários, dados de funcionários/colaboradores, CPF, telefone,
endereço — ou seja, **nenhum dado pessoal sensível (LGPD Art. 11)** dos titulares
dos clientes. Esse conteúdo permanece isolado no ambiente de cada cliente por RLS.

---

## 3. Auditoria endpoint por endpoint

### 3.1 `GET /api/operacao-central/resumo`
Campos por cliente (`clientes_payload`): `id, nome, email, tipo_conta, segmento,
ativo, pacote_codigo, pacote_label, setor_pacote, plano, max_usuarios,
max_dispositivos, data_expiracao, usuarios_ativos, dispositivos_ativos,
registros_24h, suspeitos_24h, uso_usuarios, uso_dispositivos, status_contrato,
faturamento_estimado_cliente, onboarding, playbook`.
- Classificação: **metadado + contagens**. `registros_24h`/`suspeitos_24h` são
  **números**, não o conteúdo dos registros.
- Demais blocos: `summary` (agregados globais), `carteiras`/`segmentos`
  (agregados), `vigilancia_publica` (app população, anônimo), `historico`/
  `comparativos` (séries agregadas), `financeiro` (eventos do SaaS), `auditoria`.
- **Veredito:** ✅ sem conteúdo privado de cliente.

### 3.2 `GET /api/operacao-central/financeiro-real`
MRR/ARR contratado, MRR realizado, ARPA, LTV, churn, inadimplência, movimentos,
MRR por segmento, receita mensal. **Tudo agregado financeiro do SaaS.** ✅

### 3.3 `GET /api/operacao-central/saude`
Latência de banco, cache, Asaas (só presença de chave + data do último
pagamento), geocodificação, frescor da ingestão (lê **apenas** a base pública).
Nenhum dado de cliente. ✅

### 3.4 `GET /api/operacao-central/app-funcionario`
Contagens de adoção (trabalhadores, com credencial, com push, engajados) e
ranking **por empresa** (nome da empresa + contagens). **Sem nome/CPF de
trabalhador individual.** ✅

### 3.5 `GET /api/operacao-central/operadores`
Lista os **operadores da própria SolusCRT** (equipe interna do SaaS), não
clientes. Campos: nome, e-mail, papel, status, última sessão. ✅

### 3.6 `GET /api/operacao-central/exportar` (CSV)
- `clientes`: nome, email, segmento, pacote, plano, ativo, usuarios, dispositivos,
  registros_24h, suspeitos_24h, expira_em → **metadado + contagens**.
- `financeiro`: cliente, tipo_evento, pacote, ciclo, valor, status, observacao
  (nota do próprio SaaS), criado_em.
- `auditoria`: operador, empresa, acao, detalhes, criado_em.
- **Veredito:** ✅ sem conteúdo privado de cliente.

### 3.7 `GET /api/operacao-central/auditoria`
Registro das ações dos operadores do SaaS. ✅

### 3.8 Ações de escrita (gated por RBAC)
`cliente/atualizar`, `cliente/excluir`, `cliente/reset-trial`,
`cliente/forcar-logout`, `financeiro/acao`, `onboarding/acao`,
`operador/acao` — operam sobre **metadados do contrato/conta**, nunca sobre
conteúdo dos titulares. Cada uma exige papel autorizado (403 caso contrário) e
é auditada.

### 3.9 Módulos `/financeiro/`, `/gtm/`, `/governanca/`
- **Financeiro OS** (`/api/financeiro/metricas`, `/cohorts`): métricas e cohorts
  **agregados**. ✅
- **GTM** (`/api/gtm/funil`, `/pipeline`, `/expansao`): funil e oportunidades de
  upsell (nome da empresa + plano atual/próximo). Metadado comercial. ✅
- **Governança** (`burn-multiple`, `pricing-valor`, `ml-fairness`,
  `causal-impact`, `caixa`, `metodologia`, `auditoria`): indicadores
  **agregados** de gestão/risco. ✅

### 3.10 `GET /api/operacao/readiness`
Prontidão enterprise (indicadores técnicos/operacionais agregados). ✅

---

## 4. Varredura automatizada de PII

Busca por termos sensíveis (`cpf`, `paciente`, `prontuario`, `aso`, `exame`,
`cid`, `beneficiario`, `diagnostico`, `telefone`, `endereco`, `nome_paciente`,
`nome_funcionario`) nos módulos servidos ao dono
(`views_financeiro.py`, `views_gtm.py`, `governanca.py`, `services/dashboard_core.py`):

- **Resultado:** nenhum vazamento. As únicas ocorrências em `governanca.py` são
  textos de **salvaguarda** ("não fornecer diagnóstico médico individual"),
  reforçando a postura de privacidade.

---

## 5. Enquadramento LGPD

- **Papéis:** no console, a SolusCRT atua como **operadora**, tratando apenas
  metadados de gestão do contrato. Cada **cliente é o controlador** dos dados
  pessoais dos seus titulares (pacientes/trabalhadores/beneficiários/cidadãos).
- **Dado sensível de saúde (Art. 11):** nunca trafega para o console; permanece
  isolado no ambiente do cliente por RLS.
- **App da população:** dado anônimo/pseudonimizado e agregado; o console e os
  painéis veem apenas totais e séries, não relatos individuais identificáveis.
- **Minimização e finalidade:** os campos expostos restringem-se ao necessário
  para cobrança, capacidade, suporte e crescimento.

---

## 6. Conclusão

✅ O console **Operação Central** respeita o isolamento multi-tenant. O dono da
SolusCRT administra o **negócio** (contratos, uso, cobrança, capacidade,
crescimento) sem acesso ao **conteúdo** privado dos clientes. A separação é
sustentada por RLS (banco), autenticação de operador, RBAC por papel e trilha de
auditoria — postura adequada para compromissos de LGPD e para clientes
enterprise/governo.

### Recomendações de melhoria contínua (opcionais)
1. Mascarar parcialmente o e-mail da conta nas exportações para papéis de leitura.
2. Adicionar retenção/expurgo configurável da trilha de auditoria do operador.
3. Registrar em auditoria também os **acessos de leitura** a exportações sensíveis.
4. Teste automatizado (CI) que falhe se algum endpoint do dono passar a retornar
   campos de PII (guardião anti-regressão de privacidade).
