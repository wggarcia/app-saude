# Arquitetura Enterprise de Acesso e Ambientes (SST, Hospital, Farmácia, Plano de Saúde)

## 1. Objetivo
Estruturar a plataforma com padrão de empresa grande, separando ambientes e permissões por perfil para reduzir risco operacional, vazamento de dados sensíveis e confusão de navegação.

Perfis alvo:
- Gerência
- Operação
- RH
- TI
- Auditoria/Compliance (fase seguinte)

## 2. Benchmark de mercado (referências usadas)

### 2.1 Plano de Saúde / Seguradoras
- Oracle Health Insurance documenta RBAC com controle em três eixos: **quem** (role), **o que** (função) e **quais dados** (escopo de dados), com proteção de páginas UI e controle granular de dados sensíveis.
- Oracle também documenta que acesso à UI é protegido por privilégio e que usuários podem acumular múltiplos papéis.
- Guidewire documenta perfis de autoridade e atribuição de perfis a usuários via API administrativa.

### 2.2 Hospitalar
- OpenMRS usa separação de **roles** e **privileges**, com herança de papéis.
- ServiceNow Healthcare Operations separa acesso por tabela (role) e acesso por registro (responsibility), padrão útil para ambientes clínicos e governança por contexto.

### 2.3 SST / EHS
- Cority documenta segurança por função (Role Security) e escopo adicional (site/case), além de funções administrativas segregadas.
- VelocityEHS destaca administração centralizada de usuários, papéis e localizações, com sincronização de permissões entre apps.

### 2.4 Farmácia
- OpenEMR documenta ACL por papéis e grupos, inclusive permissões para módulo de dispensário/farmácia, reforçando segregação por função.

## 3. Padrões de segurança adotados
- RBAC NIST (modelo unificado; base para engenharia de papéis em escala).
- OWASP (autorização no servidor e automação de testes de autorização por matriz de papéis).
- HIPAA Security Rule (45 CFR 164.312) para controles técnicos e acesso mínimo necessário.

## 4. Modelo-alvo de ambientes

### 4.1 Ambientes separados por URL
- Operação setorial: `/farmacia/gestao/`, `/hospital/gestao/`, `/plano-saude/gestao/`, `/governo/gestao/`, `/rede/gestao/`, `/gestao/` (SST empresa)
- Portal TI: `/ti/` (e governo: `/governo/plataforma/`)
- Portal RH: `/rh/`
- Portal Gerência: `/gerencia/`

### 4.2 Regras centrais
- **Operação**: acessa somente ambiente operacional do setor.
- **RH**: acessa portal RH (credenciais, usuários e processos de pessoas).
- **TI**: acessa portal TI (integrações, chaves, segurança, logs e automações técnicas).
- **Gerência**: visão executiva + acesso transversal.

## 5. Matriz de permissão (MVP implementado)
- Operação -> Gestão setorial: permitido
- Operação -> RH: negado
- Operação -> TI: negado
- Operação -> Gerência: negado
- RH -> RH: permitido
- RH -> Gestão setorial: negado (redireciona para RH)
- RH -> TI: negado
- TI -> TI: permitido
- TI -> Gestão setorial: negado (redireciona para TI)
- TI -> RH: negado (acesso por fluxo dedicado)
- Gerência -> Gerência: permitido
- Gerência -> Gestão setorial: permitido
- Gerência -> TI: permitido
- Gerência -> RH: permitido

## 6. Implementação aplicada no código (fase atual)
- Núcleo de perfil centralizado em `api/access_control.py`:
  - classificação de perfil principal (`gerencia`, `rh`, `ti`, `operacao`)
  - cálculo de destino por perfil
  - decorators de bloqueio de página por perfil
- Destino de login por perfil em `api/views_auth.py` (usuários de empresa).
- Bloqueio de gestão operacional para perfis TI/RH com redirecionamento para portal correto.
- Inclusão do portal RH (`/rh/`) e separação de navegação nos templates.
- Links de tecnologia/RH condicionados por contexto de perfil.

## 7. Próximas fases (recomendado)
1. Introduzir permissões granulares por ação (CRUD + escopo de dados) por módulo.
2. Adicionar perfil Auditoria/Compliance com trilha imutável de auditoria.
3. Políticas de segregação por unidade/filial/setor (record-level security).
4. Assinatura de ações críticas (duplo controle em revogação, exportação e exclusões).
5. Testes automáticos de autorização por matriz completa (rota + API + dado).

## 8. Referências
- Oracle Health Insurance RBAC: https://docs.oracle.com/en/industries/insurance/health-insurance-components/policies-4.24.1/security/user-access/role-based-security.html
- Oracle Health Insurance User Authorization: https://docs.oracle.com/en/industries/insurance/health-insurance-components/authorizations-4.25.1/security/user-access/user-authorization.html
- Guidewire Authority Profiles: https://docs.guidewire.com/cloud/pc/202511/cloudapibf/cloudAPI/topics/141-Framework/04_users-and-groups/c_authority-profiles.html
- OpenMRS User Management and Access Control: https://guide.openmrs.org/administering-openmrs/user-management-and-access-control/
- ServiceNow Healthcare roles/responsibilities: https://www.servicenow.com/docs/r/qxDp6JuKeJYtGtszctTg9w/_ChG0hiTVefgUAVymUQF0g
- Cority About Security (Role/Site/Case): https://tgs.test.cority.com/gx2demo/HelpFiles/CorityUserGuide/App_AdministratorFunctions/About_Security.htm
- VelocityEHS (roles/permissions sync context): https://www.ehs.com/mobile
- OpenEMR ACL e permissões: https://www.open-emr.org/wiki/index.php/Basic_User_ACLs_In_OpenEMR_And_How_To_Customize_Them
- NIST RBAC model: https://www.nist.gov/publications/nist-model-role-based-access-control-towards-unified-standard
- NIST RBAC role engineering: https://csrc.nist.gov/Projects/role-based-access-control/role-engineering-and-rbac-standards
- OWASP Authorization Testing Automation: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation_Cheat_Sheet.html
- HIPAA Security Rule (HHS): https://www.hhs.gov/hipaa/for-professionals/security/index.html
- 45 CFR 164.312 (technical safeguards): https://www.law.cornell.edu/cfr/text/45/164.312
