# Auditoria Estrutural Profunda — SoloCRT SaaS
Data: 24/05/2026
Escopo: SST, Farmacia, Hospital, Plano de Saude, Governo, TI, RH, Gerencia, Operacao

## 1. Resumo Executivo
- Status geral: funcional, mas ainda nao pronta para padrao enterprise em segregacao de acesso e consistencia de experiencia.
- Suite de testes: 238 testes executados, todos passando.
- Conclusao: existem fragilidades criticas de controle de acesso e pontos estruturais de UX/arquitetura que explicam a percepcao de ambiente "desgarrado".

## 2. Achados Criticos (P1)
### P1-01 — API executiva sem bloqueio de perfil gerencial
- Evidencia:
  - `api_executive_dashboard` valida autenticacao, mas nao valida perfil.
  - Arquivo: `api/views_executive.py`, funcao `api_executive_dashboard`.
- Impacto:
  - Operador pode consumir dados estrategicos da gerencia via API.
- Risco:
  - Vazamento de informacao sensivel de governanca.

### P1-02 — Acesso TI auto-concedido por texto do cargo
- Evidencia:
  - Auto atribuicao de permissao TI por heuristica de cargo.
  - Arquivo: `api/access_control.py`, funcoes `_usuario_tem_cargo_ti`, `_atribuir_permissao_ti_por_cargo`, `principal_tem_acesso_ti`.
- Impacto:
  - Quebra do fluxo formal "RH/Gerencia cadastra credencial TI".
- Risco:
  - Escalonamento indevido de privilegios.

### P1-03 — Endpoints de seed/reset demo sem decorator de gerencia
- Evidencia:
  - `api_enterprise_seed_operational_demo` e `api_enterprise_reset_demo` sem `@api_requer_gerencia`.
  - Arquivo: `api/views_enterprise.py`.
- Impacto:
  - Se mutacoes de demo estiverem habilitadas, usuario nao-gerencial pode alterar massa de dados.
- Risco:
  - Integridade de ambiente operacional.

## 3. Achados Altos (P2)
### P2-01 — SST exibe links TI/RH sem condicional de perfil
- Evidencia:
  - Sidebar SST sempre exibe RH/TI.
  - Arquivo: `templates/partials/sst_sidebar.html`.
- Impacto:
  - UX de "ambiente sem segregacao", mesmo com bloqueio backend.

### P2-02 — Hub SST exibe atalhos de Plataforma TI para perfis operacionais
- Evidencia:
  - Links diretos para `/gestao/plataforma/` no Hero e Modulos.
  - Arquivo: `templates/sst_hub.html`.
- Impacto:
  - Operador ve caminho de area tecnica e encontra erro/bloqueio depois.

### P2-03 — Botoes sensiveis visiveis no mapa para qualquer perfil
- Evidencia:
  - `Usuarios`, `Licencas`, `Seguranca` aparecem sem gate visual em dashboards.
  - Arquivos: `templates/dashboard_farmacia.html`, `templates/dashboard_hospital.html`, `templates/dashboard_unificado.html`.
- Impacto:
  - Inseguranca percebida pelo cliente final e fluxo confuso.

### P2-04 — Fluxo SST para perfil sem acesso redireciona para login
- Evidencia:
  - `_sst_redirect` sempre aponta para `/login-empresa/`.
  - Arquivo: `api/views_sst.py`.
- Impacto:
  - Usuario autenticado pode ser jogado indevidamente para login ao entrar no modulo errado.

## 4. Achados Medios (P3)
### P3-01 — Links de clinica quebrados
- Evidencia:
  - Links para `/clinica/solicitacoes/` e `/clinica/vinculos/` sem rota resolvivel.
  - Arquivo: `templates/clinica_solicitacoes.html`.
- Impacto:
  - Fluxo interrompido em navegacao da clinica.

### P3-02 — Monolito de rotas/views/templates com alto custo de manutencao
- Evidencia:
  - `backend/urls.py` ~1410 linhas.
  - `api/views_sst.py` ~2264 linhas.
  - `api/views_dashboard.py` ~1508 linhas.
  - `templates/plano_saude_gestao.html` ~3947 linhas.
- Impacto:
  - Alta probabilidade de regressao em ajustes visuais e de permissao.

## 5. Performance e Escalabilidade
### PERF-01 — Endpoint `/api/public/mapa` suscetivel a N+1 e alto custo de agregacao
- Evidencia tecnica:
  - Consulta com agregacoes multiplas por area e filtros dinâmicos.
  - Modelo `RegistroSintoma` sem `Meta.indexes` especificos para campos usados no mapa.
- Arquivos:
  - `api/views.py` (funcao `app_mapa_publico`).
  - `api/models.py` (classe `RegistroSintoma` sem indices dedicados).
- Impacto:
  - Degradacao sob volume alto (coerente com alerta Sentry de N+1/performance).

### PERF-02 — KPI de Plano de Saude em modelos sem indices focados
- Evidencia tecnica:
  - Consultas de contagem/soma por empresa/status/data em `Sinistro`, `GuiaAutorizacao`, `Reembolso`.
  - Classes sem `Meta.indexes` nessas entidades.
- Arquivos:
  - `api/views_plano_saude.py` (funcao `api_ps_kpis`).
  - `api/models.py` (classes `Sinistro`, `GuiaAutorizacao`, `Reembolso`).
- Impacto:
  - Lentidao progressiva conforme base cresce.

## 6. Maturidade por Ambiente
### SST
- Pontos fortes:
  - Cobertura funcional extensa.
  - Rotas de modulo completas.
- Gaps:
  - Segregacao visual de RH/TI/Gerencia incompleta.
  - Navegacao do hub nao alinhada ao modelo de perfil.

### Farmacia / Hospital / Plano / Governo
- Pontos fortes:
  - Gestao setorial com decorators de setor e operacao.
  - Blocos gerenciais condicionais em boa parte dos templates.
- Gaps:
  - Botoes sensiveis ainda visiveis em dashboard de mapa.
  - Inconsistencias de UX entre telas setoriais.

### TI / RH / Gerencia
- Pontos fortes:
  - Rotas dedicadas existem (`/ti/`, `/rh/`, `/gerencia/`).
  - Decorators de pagina presentes.
- Gaps:
  - Regras de concessao TI por cargo fragilizam governanca.
  - API executiva sem gate de gerencia.

## 7. Plano de Correcao Recomendado
### Fase 1 (Critica, imediata)
1. Bloquear API executiva para gerencia (`@api_requer_gerencia`).
2. Remover auto-concessao TI por cargo; exigir credencial/permissao explicita.
3. Proteger seed/reset demo com perfil gerencial.
4. Corrigir exibicao de links sensiveis no SST e dashboards.

### Fase 2 (Estrutural)
1. Refatorar navegacao setorial para componente unico por perfil.
2. Unificar header/sidebar padrao entre todos os ambientes.
3. Padronizar contratos de contexto de template (`mostrar_link_ti`, `mostrar_link_rh`, `mostrar_aba_gerencia`).

### Fase 3 (Escala e resiliencia)
1. Adicionar indices direcionados em `RegistroSintoma`, `Sinistro`, `GuiaAutorizacao`, `Reembolso`.
2. Otimizar `app_mapa_publico` e `api_ps_kpis` com pre-aggregacao/caching.
3. Quebrar monolitos de views/templates em modulos menores.

## 8. Estado da Auditoria
- Auditoria concluida com varredura de:
  - Rotas, decorators, middlewares, templates de navegacao, endpoints de perfil e APIs sensiveis.
  - Validacao automatizada de testes.
  - Inspecao de consistencia de links e pontos de acesso por perfil.
