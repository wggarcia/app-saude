# Implementacao incremental do SolusCRT Corporativo

Guia de execucao para transformar o ambiente `empresa` em um produto proprio de saude ocupacional, desenvolvimento humano e continuidade operacional, sem quebrar os ambientes epidemiologicos.

## 1. Objetivo

Construir o novo produto em camadas, validando contrato de dados, privacidade, experiencia institucional e app mobile do colaborador antes de substituir qualquer experiencia antiga do ambiente `empresa`.

## 2. Principios

- nao quebrar `governo`, `hospital` e `farmacia`
- nao reutilizar o motor epidemiologico como base principal do corporativo
- separar plataforma healthtech institucional de app mobile do colaborador
- preservar autenticacao, billing e tenancy
- ativar o novo ambiente por feature flag, pacote ou rollout controlado
- desenhar o produto para parecer premium e operar como ferramenta real de empresa

## 3. Macroarquitetura de implementacao

O produto sera construido em tres trilhos paralelos:

1. `plataforma healthtech institucional`
2. `App mobile do colaborador`
3. `Motor corporativo de IA e analytics`

## 3.1 plataforma healthtech institucional

Responsavel por:

- dashboards executivos
- leitura agregada por unidade/setor/escala
- programas e campanhas
- governanca
- decisao assistida

## 3.2 App mobile do colaborador

Responsavel por:

- check-ins
- apoio
- autocuidado
- microlearning
- carreira on/off
- mentoria e comunidades

## 3.3 Motor corporativo

Responsavel por:

- anonimato
- consolidacao de sinais
- calculo de risco
- matching
- recomendacoes de IA

## 4. Fase 0: reposicionamento do produto

### Entregas

- blueprint aprovado
- definicao da separacao entre healthtech e app mobile
- mapa de modulos
- definicao de nomenclatura premium
- definicao de regras de anonimato

### Saidas tecnicas

- documento de produto
- taxonomia de modulos
- lista de rotas institucionais
- lista de contratos do app mobile

## 5. Fase 1: fundacao de dominio corporativo

### Back-end

- consolidar dominio `corporativo` em app proprio ou modulo isolado
- revisar models atuais e expandir o que ja existe
- manter todos os modelos referenciando `Empresa`

### Models institucionais

- `EmpresaUnidade`
- `EmpresaSetor`
- `EmpresaTurno`
- `EmpresaEscalaOperacional`
- `ProgramaCorporativo`
- `ComunidadePratica`

### Models do colaborador

- `ColaboradorAliasAnonimo`
- `ColaboradorConsentimento`
- `CheckinDiarioCorporativo`
- `CheckinSemanalCorporativo`
- `PedidoApoioCorporativo`
- `PlanoDesenvolvimentoOnOff`
- `TrilhaMicrolearning`

### Models de analytics e operacao

- `ResumoAgregadoCorporativo`
- `AcaoIACorporativa`
- `RiscoPsicossocialSnapshot`
- `RiscoOcupacionalSnapshot`
- `MentoriaCorporativa`
- `MentoriaMatching`
- `HandoffConhecimento`

### Cuidado

- nao tocar nos fluxos de `dashboard_farmacia`, `dashboard_hospital` e `dashboard_governo`

## 6. Fase 2: plataforma healthtech institucional premium

### Escopo do MVP institucional

- rota principal `/dashboard-empresa/`
- home executiva premium
- modulo saude ocupacional
- modulo fadiga e burnout
- modulo escalas e continuidade
- modulo cultura e comunicacao
- modulo mentoria e lideranca
- modulo governanca

### Decisoes de UX

- linguagem de cliente, nao de desenvolvedor
- visual de control room premium
- acao clara por modulo
- leitura de 30 segundos para decisores
- ausencia de fluxo "mobile-like" dentro da plataforma healthtech

### Rotas sugeridas

- `/dashboard-empresa/`
- `/empresa/saude-ocupacional/`
- `/empresa/fadiga-burnout/`
- `/empresa/escalas/`
- `/empresa/cultura-comunicacao/`
- `/empresa/mentoria-lideranca/`
- `/empresa/governanca/`

## 7. Fase 3: app mobile do colaborador

### Direcao

Este app deve ser tratado como produto mobile dedicado para funcionarios, e nao como um painel ou subpagina da plataforma healthtech institucional.

### Escopo MVP mobile

- onboarding e privacidade
- check-in diario
- check-in semanal
- pedido de apoio
- meu cuidado
- trilhas curtas de bem-estar

### Escopo fase 2 mobile

- microlearning de idioma tecnico
- cultura e CQ
- carreira on/off
- mentoria
- comunidades de pratica
- videos de handoff
- operacao offline com sync posterior

### Contratos de API sugeridos

- `/api/corporativo/mobile/config`
- `/api/corporativo/mobile/onboarding`
- `/api/corporativo/mobile/checkin-diario`
- `/api/corporativo/mobile/checkin-semanal`
- `/api/corporativo/mobile/pedir-apoio`
- `/api/corporativo/mobile/trilhas`
- `/api/corporativo/mobile/mentoria`
- `/api/corporativo/mobile/comunidades`

## 8. Fase 4: modulos de negocio

## 8.1 Inteligencia Cultural e Comunicacao Multilingue

### MVP

- glossario tecnico por idioma e operacao
- trilhas curtas de cultura
- playbooks de lideranca multicultural

### Evolucao

- traducao assistida em contexto
- recomendacao automatica de trilhas
- integracoes com plataformas de CQ

## 8.2 Gestao de Ciclos 14x14 / 28x28

### MVP

- cadastro de escalas por unidade
- leitura de check-ins por ciclo
- PDI on/off simples

### Evolucao

- trilhas offline
- sincronizacao assíncrona
- planejamento de aprendizagem por janela de folga

## 8.3 Mentoria e Suporte a Distancia

### MVP

- matching manual ou semiautomatico
- agenda simples de mentoria
- feedback de fim de ciclo

### Evolucao

- matching por idioma, senioridade e especialidade
- alertas de talentos sem cobertura
- score de aderencia de lideranca

## 8.4 Saude Mental em Ambiente Confinado

### MVP

- leitura de fadiga, estresse e sono
- fila de pedidos de apoio
- score psicossocial por grupos anonimos

### Evolucao

- trilhas de regulacao emocional
- programas por unidade
- comunidades moderadas

## 9. Fase 5: motor corporativo de IA

### Entradas

- check-ins diarios
- check-ins semanais
- pedidos de apoio
- aderencia a programas
- sinais por unidade, turno e escala
- dados de cultura, aprendizado e mentoria quando existirem

### Saidas

- score de risco ocupacional
- score de risco psicossocial
- absenteismo provavel
- liderancas em atencao
- recomendacao de programas
- priorizacao por unidade e escala

### Perguntas que o motor precisa responder

- onde a empresa esta perdendo energia?
- onde a escala esta gerando risco?
- qual lideranca precisa de apoio?
- qual programa deve entrar primeiro?
- onde ha risco cultural, de idioma ou de handoff?

## 10. Fase 6: governanca e conformidade

### Entregas

- grupos minimos
- mascaramento de dados
- limites de filtro
- trilha de auditoria
- consentimento explicito
- separacao entre dado de cuidado e dado disciplinar

## 11. Fase 7: migracao de experiencia

Quando o modulo novo estiver maduro:

- `empresa` aponta definitivamente para `/dashboard-empresa/`
- o app mobile vira o canal oficial do colaborador
- a antiga nocao de "app dentro da plataforma healthtech" e removida
- hospital/farmacia/governo permanecem intactos

## 12. Ordem sugerida das proximas entregas

1. consolidar o blueprint e encerrar desalinhamento conceitual
2. refatorar a plataforma healthtech institucional para os modulos premium corretos
3. separar tecnicamente o app mobile do colaborador
4. implementar APIs mobile dedicadas
5. implementar cultura/comunicacao, escalas, mentoria e saude mental no modelo de dados
6. enriquecer o motor de IA com sinais desses modulos
7. homologar governanca, anonimato e rollout

## 13. Definicao de pronto do MVP

O MVP pode ser considerado pronto quando:

- empresa entra em um dashboard premium coerente com saude ocupacional
- colaborador usa um app mobile proprio, nao uma extensão da plataforma healthtech
- check-ins, apoio e leituras por unidade/escala funcionam
- IA produz alertas institucionais utilizaveis
- pelo menos um fluxo de cultura, um de escala e um de mentoria estao ativos
- anonimato esta protegido por regra tecnica e visual
- nao ha regressao nos ambientes epidemiologicos
