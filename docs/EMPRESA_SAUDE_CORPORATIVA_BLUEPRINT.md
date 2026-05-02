# SolusCRT Corporativo

Blueprint do novo ambiente `empresa` como produto proprio de saude ocupacional e bem-estar corporativo, preservando os ambientes epidemiologicos existentes (`governo`, `hospital`, `farmacia`).

## 1. Decisao de produto

O ambiente `empresa` deixa de ser uma variacao do dashboard epidemiologico setorial e passa a ser um produto proprio dentro do mesmo ecossistema SaaS.

### Permanecem como estao

- `governo`: vigilancia epidemiologica institucional e alertas oficiais.
- `hospital`: prontidao clinica, pressao assistencial, triagem e leitos.
- `farmacia`: inteligencia de demanda, estoque e abastecimento.

### Passa a existir como produto proprio

- `empresa`: saude ocupacional, saude mental, bem-estar, fadiga, absenteismo e acoes preventivas para RH, SESMT e lideranca.

## 2. Tese do produto

Empresas nao precisam de um espelho do ambiente hospitalar ou farmaceutico. Precisam de um ambiente que responda:

- Onde estao surgindo sinais de sofrimento emocional e fisico?
- Em quais unidades, turnos ou setores o risco esta aumentando?
- O problema parece interno, externo ou misto?
- O que a empresa deve fazer nesta semana para reduzir afastamentos e piora do quadro?

O produto deve operar como uma ponte entre:

- sinais internos anonimizados dos colaboradores
- contexto externo do SolusCRT epidemiologico
- plano de acao institucional com recomendacoes praticas

## 3. Publicos

### Comprador

- RH
- People
- Saude ocupacional
- SESMT
- Lideranca executiva
- Operacoes de campo e multiunidade

### Usuario institucional

- gestor de RH
- medico do trabalho
- tecnico de seguranca
- lider de unidade
- diretor de operacoes

### Usuario final do app

- colaborador

## 4. Estrutura do produto

O modulo corporativo sera composto por tres pecas:

1. Painel institucional web para empresa
2. App do colaborador
3. Motor analitico e de recomendacao corporativa

### 4.1 Painel institucional

Foco em leitura agregada e anonima.

### 4.2 App do colaborador

Foco em check-ins simples, sinais fisicos/emocionais e orientacao de autocuidado.

### 4.3 Motor corporativo

Foco em:

- agregacao anonima
- score de risco
- tendencias
- planos de acao da IA
- cruzamento com contexto externo epidemiologico

## 5. Mapa de telas do Painel Empresa

### 5.1 Home Executiva

Objetivo: leitura de 30 segundos para decisores.

Blocos:

- indice geral de bem-estar
- risco psicossocial
- risco fisico ocupacional
- tendencia de absenteismo
- unidades em atencao
- plano de acao da semana da IA

Widgets:

- `Indice Geral`: score 0-100 com variacao 7d e 30d
- `Risco Mental`: baixo, moderado, alto, critico
- `Risco Fisico`: baixo, moderado, alto, critico
- `Unidades Criticas`: top 5 unidades
- `Sinais Dominantes`: fadiga, sono ruim, estresse, dor
- `Leitura da IA`: texto curto com explicacao e acoes

### 5.2 Saude Mental

Objetivo: identificar sobrecarga, exaustao e piora emocional.

Blocos:

- humor medio agregado
- nivel de estresse
- fadiga emocional
- risco de burnout
- sensacao de apoio
- tendencia por unidade/setor/turno

Visualizacoes:

- serie temporal 7, 30 e 90 dias
- heatmap por unidade
- comparativo por turno
- distribuicao por intensidade

### 5.3 Saude Fisica e Ocupacional

Objetivo: monitorar sinais fisicos recorrentes e desgaste ocupacional.

Blocos:

- dores recorrentes
- fadiga fisica
- qualidade do sono
- desconforto ergonomico
- sinais respiratorios
- sinais por unidade e turno

Visualizacoes:

- radar de sintomas
- mapa organizacional por area
- tendencia de queixas fisicas

### 5.4 Unidades e Equipes

Objetivo: localizar rapidamente os pontos de maior risco.

Blocos:

- ranking de unidades em atencao
- comparacao entre setores
- comparacao entre turnos
- equipes com piora recente
- estabilidade vs volatilidade

Visualizacoes:

- heatmap por unidade
- cards por setor
- tabela de prioridade operacional

### 5.5 Alertas e IA

Objetivo: traduzir sinais em decisao.

Blocos:

- alerta
- explicacao da causa
- impacto estimado
- urgencia
- janela recomendada de acao
- plano sugerido

Exemplos de saida:

- "Unidade Norte com crescimento de fadiga e sono ruim em 14 dias."
- "Turno da noite com combinacao de estresse alto e queda de energia."
- "Contexto respiratorio regional elevando risco de absenteismo."

### 5.6 Campanhas e Acoes

Objetivo: sair de observacao para intervencao.

Tipos de campanha:

- pausa e recuperacao
- sono e rotina
- ergonomia
- hidratacao
- respiratorio sazonal
- apoio emocional

Medidas:

- adesao
- engajamento
- impacto antes/depois
- acoes abertas

### 5.7 Contexto Externo

Objetivo: cruzar ambiente interno com risco territorial.

Blocos:

- indice epidemiologico regional
- sintomas predominantes no territorio
- cidades com piora
- impacto esperado na forca de trabalho

Exemplo de leitura:

- aumento de sinais respiratorios na regiao + fadiga interna em unidades locais
- pressao emocional interna sem correlacao epidemiologica externa

### 5.8 Governanca

Objetivo: dar seguranca juridica e operacional ao modulo.

Blocos:

- politica de anonimato
- grupos minimos para exibicao
- perfis de acesso
- auditoria de uso
- consentimento e finalidade

## 6. Mapa de telas do App do Colaborador

### 6.1 Onboarding e Privacidade

Mensagens obrigatorias:

- o que e anonimo
- o que a empresa pode ver
- o que a empresa nao pode ver
- quando um pedido pode sair do anonimato por consentimento

### 6.2 Check-in Diario

Campos sugeridos:

- humor hoje
- energia
- estresse
- qualidade do sono
- dor fisica
- cansaco
- sintomas fisicos
- vontade de pedir apoio

Tempo ideal: 30 a 60 segundos

### 6.3 Check-in Semanal

Campos sugeridos:

- carga emocional
- sensacao de apoio
- percepcao de pressao
- concentracao
- satisfacao geral
- seguranca psicologica

### 6.4 Registrar Sinais

Tipos:

- dor corporal
- dor de cabeca
- exaustao
- ansiedade
- irritabilidade
- tristeza persistente
- falta de ar
- tosse
- disturbio de sono

### 6.5 Meu Cuidado

Conteudos:

- pausa guiada
- respiracao
- higiene do sono
- organizacao de rotina
- orientacao preventiva

### 6.6 Pedir Apoio

Fluxos:

- pedido anonimo orientado
- pedido com contato opcional
- orientacao para canal interno
- orientacao para ajuda profissional

### 6.7 Meu Historico

Uso individual:

- tendencia pessoal de bem-estar
- dias melhores/piores
- continuidade dos check-ins

## 7. Modelo de dados MVP

## 7.1 Entidades institucionais

- `EmpresaUnidade`
- `EmpresaSetor`
- `EmpresaTurno`
- `EmpresaPerfilAcessoCorporativo`

## 7.2 Entidades do colaborador

- `ColaboradorVinculo`
- `ColaboradorConsentimento`
- `ColaboradorAliasAnonimo`

## 7.3 Entidades de saude corporativa

- `CheckinDiarioCorporativo`
- `CheckinSemanalCorporativo`
- `SinalSaudeCorporativo`
- `PedidoApoioCorporativo`
- `CampanhaCorporativa`
- `CampanhaAdesao`
- `AcaoIACorporativa`
- `ResumoAgregadoCorporativo`

## 7.4 Campos minimos de check-in diario

- empresa
- unidade
- setor
- turno
- colaborador_alias
- data
- humor
- energia
- estresse
- sono
- dor
- fadiga
- sintomas_fisicos
- sintomas_emocionais
- apoio_solicitado

## 7.5 Campos minimos de check-in semanal

- empresa
- unidade
- setor
- turno
- colaborador_alias
- semana_referencia
- carga_emocional
- sensacao_de_apoio
- pressao_de_trabalho
- seguranca_psicologica
- bem_estar_geral

## 8. Regras de anonimato e seguranca

Essas regras devem nascer no MVP, nao depois.

### Regras obrigatorias

- o painel institucional nao mostra dado individual bruto
- grupos com menos de 8 respostas nao aparecem
- nao mostrar cruzamentos que permitam reidentificacao indireta
- lideranca ve apenas agregado
- pedido de apoio nominal so ocorre com consentimento explicito
- auditoria institucional registra acesso a dados agregados e exportacoes

### Regras recomendadas

- limitar recortes por combinacao de filtros
- atrasar levemente exibicao de pequenos grupos
- mascarar extremos quando a amostra for baixa
- separar identificador tecnico do colaborador da camada analitica

## 9. Integracao com o ecossistema atual

## 9.1 O que reaproveitar

- `Empresa` como tenant principal
- autenticacao institucional
- licencas, pacotes e billing
- usuarios da empresa (`EmpresaUsuario`)
- auditoria institucional
- padrao atual de dashboards e APIs
- infraestrutura de deploy e operacao

## 9.2 O que nao misturar

- `RegistroSintoma` epidemiologico nao deve virar deposito do corporativo
- dashboards hospital/farmacia/governo nao devem ser derivados do corporativo
- motor de risco epidemiologico nao deve ser reaproveitado sem camada propria de interpretacao corporativa

## 9.3 Separacao recomendada de dominio

Criar um dominio proprio para o modulo corporativo, por exemplo:

- `api/corporativo_models.py`
- `api/views_corporativo.py`
- `api/corporativo_ai.py`
- `templates/corporativo/...`

Alternativa melhor ainda:

- novo app Django `corporativo/`

Essa opcao reduz acoplamento com o modulo epidemiologico.

## 10. Rotas previstas

### Web

- `/dashboard-empresa/`
- `/empresa/saude-mental/`
- `/empresa/saude-fisica/`
- `/empresa/unidades/`
- `/empresa/alertas-ia/`
- `/empresa/campanhas/`
- `/empresa/contexto-externo/`
- `/empresa/governanca/`

### API institucional

- `/api/empresa/resumo`
- `/api/empresa/saude-mental`
- `/api/empresa/saude-fisica`
- `/api/empresa/unidades`
- `/api/empresa/alertas-ia`
- `/api/empresa/campanhas`
- `/api/empresa/contexto-externo`

### API do app do colaborador

- `/api/corporativo/checkin-diario`
- `/api/corporativo/checkin-semanal`
- `/api/corporativo/sinais`
- `/api/corporativo/pedir-apoio`
- `/api/corporativo/meu-historico`

## 11. IA corporativa

O modulo corporativo deve gerar recomendacoes com explicacao, nao apenas score.

### Perguntas que a IA precisa responder

- onde a piora esta surgindo?
- o padrao e fisico, emocional ou misto?
- qual unidade precisa de acao nesta semana?
- isso parece vir do ambiente interno ou do contexto externo?
- qual acao simples gera mais efeito agora?

### Tipos de saida

- resumo executivo
- alertas priorizados
- recomendacao por unidade
- campanha sugerida
- risco de absenteismo
- leitura explicavel do por que

## 12. MVP recomendado

### Fase 1

- dashboard-empresa novo
- check-in diario
- check-in semanal
- saude mental e fisica agregadas
- unidades e setores
- alertas IA basicos
- anonimato e governanca

### Fase 2

- campanhas de bem-estar
- pedido de apoio
- cruzamento com contexto epidemiologico externo
- historico individual no app

### Fase 3

- predicao de absenteismo
- benchmark interno entre unidades
- automacoes de campanha
- exportacao executiva

## 13. Riscos de produto

### Se fizer do jeito errado

- o modulo empresa vira copia ruim de hospital/farmacia
- excesso de coleta sensivel afasta adesao
- anonimato mal implementado gera risco juridico e reputacional
- mistura de dominio epidemiologico com dominio corporativo gera confusao tecnica

### Se fizer do jeito certo

- o ecossistema ganha um segundo produto forte
- o modulo empresa passa a resolver problema real de RH e saude ocupacional
- o SolusCRT amplia valor sem quebrar o que ja existe

## 14. Decisao final

O caminho correto e:

- manter o epidemiologico intacto
- criar um produto corporativo novo dentro do mesmo ecossistema
- usar backend compartilhado apenas onde faz sentido
- separar dominio, dados, dashboards e IA do modulo empresa

Esse desenho reduz risco de regressao e cria uma linha de produto clara para empresas.
