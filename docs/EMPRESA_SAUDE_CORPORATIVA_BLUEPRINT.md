# SoloCRT Corporativo

Blueprint do produto `empresa` como um ambiente proprio de saude ocupacional, desenvolvimento humano e continuidade operacional, preservando os ambientes epidemiologicos existentes (`governo`, `hospital`, `farmacia`).

## 1. Decisao de produto

O ambiente `empresa` deixa de ser uma variacao do dashboard epidemiologico setorial e passa a ser um segundo produto forte dentro do ecossistema SoloCRT.

### Permanecem como estao

- `governo`: vigilancia epidemiologica institucional e alertas oficiais.
- `hospital`: prontidao clinica, pressao assistencial, triagem e leitos.
- `farmacia`: inteligencia de demanda, estoque e abastecimento.

### Passa a existir como produto proprio

- `empresa`: saude ocupacional, saude mental, fadiga, desenvolvimento em escala, apoio institucional, inteligencia cultural e continuidade do trabalho.

## 2. Tese central

Empresas nao precisam de uma copia do ambiente hospitalar ou farmaceutico. Precisam de uma plataforma que responda:

- onde a operacao esta perdendo energia antes do afastamento aparecer?
- quais unidades, escalas ou liderancas estao entrando em risco?
- como agir sem expor individuos?
- quais programas de apoio, desenvolvimento e comunicacao precisam entrar nesta semana?

O produto deve funcionar como a combinacao de tres camadas:

- sinais internos anonimizados dos colaboradores
- contexto operacional e organizacional da empresa
- decisao assistida por IA para RH, SESMT, lideranca e operacoes

## 3. Estrutura correta do produto

O modulo corporativo nao deve ser um painel unico tentando fazer tudo. Ele precisa ser dividido em tres superficies claras.

### 3.1 plataforma healthtech institucional da empresa

Uso por:

- RH
- People
- SESMT
- lideranca operacional
- saude ocupacional
- diretoria

Responsabilidade:

- visao agregada e anonima
- indicadores institucionais
- planos de acao
- programas e campanhas
- leitura por unidade, setor, escala e lideranca

### 3.2 App mobile do colaborador

Uso por:

- funcionarios
- equipes embarcadas
- trabalhadores de campo
- times multiunidade e multinacionais

Responsabilidade:

- check-ins diarios e semanais
- pedido opcional de apoio
- trilhas curtas de bem-estar
- jornada de desenvolvimento pessoal
- microlearning e recursos offline

Regra de produto:

- este app e um produto mobile dedicado
- ele nao deve ser tratado como "um app dentro da plataforma healthtech"
- a healthtech da empresa o apresenta como parte do ecossistema, mas a experiencia do colaborador e separada

### 3.3 Motor corporativo de IA e analytics

Responsabilidade:

- agregacao anonima
- score de risco institucional
- leitura de fadiga, absenteismo e risco psicossocial
- matching, recomendacoes e priorizacao
- cruzamento com sinais de contexto quando fizer sentido

## 4. Publicos

### Comprador

- RH
- People
- saude ocupacional
- SESMT
- operacoes
- diretorias de unidades intensivas ou distribuidas

### Usuarios institucionais

- gestor de RH
- medico do trabalho
- tecnico de seguranca
- lider de operacao
- gerente de unidade
- diretor de operacoes

### Usuario final do app mobile

- colaborador

## 5. Problemas reais que o produto precisa resolver

### 5.1 Saude ocupacional

- afastamentos recorrentes
- fadiga fisica
- ergonomia ruim
- sinais precoces de desgaste
- retorno ao trabalho sem acompanhamento

### 5.2 Saude mental e psicossocial

- estresse cronico
- burnout silencioso
- baixa seguranca psicologica
- medo de pedir ajuda
- liderancas despreparadas para acolhimento

### 5.3 Operacoes em escala e ambiente confinado

- ciclos 14x14 e 28x28
- isolamento
- queda de energia cognitiva
- passagem de turno fraca
- dificuldade de aprendizado continuo

### 5.4 Operacoes multiculturais

- falhas de comunicacao entre nacionalidades
- risco por idioma tecnico
- desalinhamento cultural na lideranca
- conflitos de feedback, seguranca e colaboracao

## 6. Mapa dos modulos do produto

Os modulos abaixo definem o coracao do SoloCRT Corporativo.

### 6.1 Saude Ocupacional

Objetivo:

- monitorar risco fisico, sinais ocupacionais, dor, fadiga, sono e retorno ao trabalho

Ferramentas principais:

- radar de carga fisica
- mapa de sinais por unidade/setor/turno
- fila de retorno assistido
- campanhas de ergonomia e recuperacao
- leitura de risco por funcao operacional

### 6.2 Fadiga e Burnout

Objetivo:

- antecipar queda de energia, exaustao e impacto sobre escala, seguranca e continuidade

Ferramentas principais:

- score de fadiga por unidade e ciclo
- previsao de pressao sobre absenteismo
- sinal de burnout por grupos anonimos
- leitura de energia e sono
- recomendacoes de ajuste de pausa, cobertura e ritmo

### 6.3 Inteligencia Cultural e Comunicacao Multilingue

Objetivo:

- reduzir falhas de entendimento em equipes com diferentes nacionalidades, idiomas e estilos de trabalho

Ferramentas principais:

- trilhas de CQ (quociente cultural)
- glossario tecnico multilingue
- traducao assistida em contexto operacional
- microlearning de idioma tecnico
- kits de comunicacao para lideranca multicultural

### 6.4 Gestao de Escalas e Desenvolvimento On/Off

Objetivo:

- permitir desenvolvimento profissional sem colidir com a realidade das escalas longas

Ferramentas principais:

- trilhas assincronas com modo offline
- PDI on/off por ciclo
- metas separadas para embarque e folga
- agenda de retomada de aprendizado
- mapa de aderencia por unidade e turno

### 6.5 Mentoria e Suporte a Distancia

Objetivo:

- manter crescimento tecnico e apoio humano mesmo em ambientes remotos, dispersos ou confinados

Ferramentas principais:

- matching de mentoria entre unidades e paises
- registro de sessoes de mentoria
- feedback de fim de ciclo
- rituais de lideranca remota
- fila de acompanhamento de talentos em risco

### 6.6 Comunidades de Pratica e Transferencia de Conhecimento

Objetivo:

- evitar perda de conhecimento e fortalecer pertencimento entre equipes separadas por escala ou geografia

Ferramentas principais:

- comunidades por especialidade
- passagem de turno educativa
- biblioteca de videos curtos de handoff
- curadoria de boas praticas
- perguntas e respostas tecnicas por frente operacional

## 7. O que fica em cada superficie

## 7.1 plataforma healthtech institucional da empresa

Deve conter:

- home executiva
- saude ocupacional
- fadiga e burnout
- unidades, escalas e continuidade
- cultura e comunicacao
- mentoria e desenvolvimento
- campanhas e programas
- governanca e privacidade
- sala de decisao corporativa

Nao deve conter:

- experiencia principal do colaborador
- trilhas pessoais como fluxo central
- formularios longos pensados para uso diario do funcionario

## 7.2 App mobile do colaborador

Deve conter:

- onboarding e privacidade
- check-in diario
- check-in semanal
- pedido de apoio
- meu cuidado
- trilhas curtas
- microlearning de idioma e cultura
- desenvolvimento on/off
- mentoria e comunidades

Nao deve depender de:

- navegação da plataforma healthtech institucional
- contexto de dashboard executivo
- linguagem de produto voltada para RH

## 7.3 Motor de IA e analytics

Deve conter:

- agregacao anonima
- correlacao entre sinais
- recomendacao de programas
- priorizacao por unidade e escala
- matching de mentoria
- explicacao executiva acionavel

## 8. Mapa de telas do plataforma healthtech institucional

### 8.1 Home Executiva

Objetivo:

- leitura de 30 segundos para diretoria, RH e SESMT

Blocos:

- bem-estar geral
- risco psicossocial
- risco ocupacional
- fadiga e absenteismo provavel
- unidades em observacao
- planos recomendados da semana

### 8.2 Saude Ocupacional

Blocos:

- sinais fisicos dominantes
- risco ergonomico
- retorno ao trabalho
- clusters de fadiga fisica
- mapa por unidade e funcao

### 8.3 Fadiga, Burnout e Saude Mental

Blocos:

- estresse agregado
- energia media
- qualidade do sono
- fadiga emocional
- seguranca psicologica
- burnout provavel por grupos anonimos

### 8.4 Escalas e Continuidade

Blocos:

- leitura por ciclo 14x14 / 28x28
- pressao por turno
- aderencia a pausas
- risco de quebra de cobertura
- desenvolvimento on/off

### 8.5 Cultura e Comunicacao

Blocos:

- equipes multiculturais em atencao
- gaps de idioma tecnico
- trilhas de CQ ativas
- glossarios mais acessados
- necessidade de traducao operacional

### 8.6 Mentoria e Lideranca

Blocos:

- mentores ativos
- talentos sem cobertura
- qualidade do feedback por ciclo
- liderancas sob maior pressao
- recomendacoes de apoio ao gestor

### 8.7 Comunidades e Conhecimento

Blocos:

- comunidades ativas
- handoffs publicados
- aderencia a compartilhamento
- especialidades sem curadoria
- topicos tecnicos mais recorrentes

### 8.8 Governanca

Blocos:

- politica de anonimato
- grupos minimos
- perfis de acesso
- auditoria
- consentimento
- uso de IA e explicabilidade

## 9. Mapa de telas do app mobile do colaborador

### 9.1 Onboarding e Privacidade

Mensagens obrigatorias:

- o que e anonimo
- o que a empresa ve
- o que a empresa nao ve
- quando um pedido de apoio pode ser identificado por consentimento

### 9.2 Check-in Diario

Campos:

- humor
- energia
- estresse
- sono
- dor fisica
- cansaco
- foco/concentracao
- vontade de pedir apoio

Tempo ideal:

- 30 a 60 segundos

### 9.3 Check-in Semanal

Campos:

- carga emocional
- sensacao de apoio
- percepcao de pressao
- seguranca psicologica
- relacao com o gestor
- equilibrio entre trabalho e descanso

### 9.4 Meu Cuidado

Conteudos:

- pausa guiada
- respiracao
- higiene do sono
- regulacao emocional
- rotina para desembarque/retorno

### 9.5 Idioma e Cultura

Conteudos:

- microlearning de idioma tecnico
- situacoes reais de feedback
- comportamento intercultural
- glossarios por funcao
- uso offline

### 9.6 Carreira On/Off

Conteudos:

- metas do ciclo embarcado
- metas do ciclo de folga
- retomada de trilhas
- progresso de PDI
- lembretes de estudo assincrono

### 9.7 Mentoria e Comunidades

Conteudos:

- mentor indicado
- agenda de contato
- comunidade por especialidade
- handoff em video
- perguntas e respostas tecnicas

### 9.8 Pedir Apoio

Fluxos:

- pedido anonimo orientado
- pedido com contato opcional
- canal humano
- orientacao para apoio profissional

## 10. Ferramentas por modulo

## 10.1 Inteligencia Cultural e Comunicacao Multilingue

Ferramentas MVP:

- catalogo de glossarios tecnicos
- biblioteca de microlearning por idioma
- playbooks curtos de CQ para liderancas

Ferramentas fase 2:

- traducao assistida contextual
- recomendador de trilhas por equipe
- integracao com fornecedores de CQ

## 10.2 Gestao de Ciclos de Escala

Ferramentas MVP:

- cadastro de ciclo por unidade
- leitura de check-ins por escala
- PDI on/off basico

Ferramentas fase 2:

- offline sync
- trilhas baixaveis
- lembretes inteligentes por janela de folga

## 10.3 Mentoria e Suporte a Distancia

Ferramentas MVP:

- matching simples mentor-mentorado
- registro de encontros
- feedback de fim de ciclo

Ferramentas fase 2:

- matching inteligente por idioma, senioridade e especialidade
- alertas de mentorados sem acompanhamento

## 10.4 Saude Mental em Ambiente Confinado

Ferramentas MVP:

- score de fadiga e estresse
- leitura de sono e energia
- fila de pedidos de apoio
- campanhas de acolhimento

Ferramentas fase 2:

- trilhas de regulacao emocional
- programas por unidade
- comunidades de pratica moderadas

## 11. Modelo de dados recomendado

## 11.1 Entidades institucionais

- `EmpresaUnidade`
- `EmpresaSetor`
- `EmpresaTurno`
- `EmpresaEscalaOperacional`
- `ProgramaCorporativo`
- `MentoriaCorporativa`
- `ComunidadePratica`

## 11.2 Entidades do colaborador

- `ColaboradorAliasAnonimo`
- `ColaboradorConsentimento`
- `CheckinDiarioCorporativo`
- `CheckinSemanalCorporativo`
- `PedidoApoioCorporativo`
- `PlanoDesenvolvimentoOnOff`
- `TrilhaMicrolearning`

## 11.3 Entidades de analytics

- `ResumoAgregadoCorporativo`
- `AcaoIACorporativa`
- `RiscoPsicossocialSnapshot`
- `RiscoOcupacionalSnapshot`
- `MentoriaMatching`
- `HandoffConhecimento`

## 12. Regras de anonimato e seguranca

Essas regras precisam nascer no MVP, nao depois.

### Obrigatorias

- o painel institucional nao mostra dado individual bruto
- grupos com menos de 8 respostas nao aparecem
- nao mostrar cruzamentos que permitam reidentificacao indireta
- lideranca ve apenas agregado
- pedido de apoio nominal so ocorre com consentimento explicito
- auditoria institucional registra acesso a dados agregados e exportacoes

### Recomendadas

- limitar recortes por combinacao de filtros
- atrasar levemente exibicao de pequenos grupos
- mascarar extremos quando a amostra for baixa
- separar identificador tecnico da camada analitica
- diferenciar dado de bem-estar de dado disciplinar

## 13. IA corporativa

O modulo corporativo deve produzir recomendacoes com explicacao, nao apenas score.

### Perguntas que a IA precisa responder

- onde a piora esta surgindo?
- o problema e fisico, emocional, cultural ou operacional?
- qual unidade, escala ou lideranca precisa agir primeiro?
- qual programa deve entrar nesta semana?
- onde a empresa esta perdendo aprendizagem, pertencimento ou cobertura?
- o risco vem da rotina interna, do desenho da escala ou do contexto externo?

### Tipos de saida

- resumo executivo
- ranking de unidades em risco
- campanha sugerida
- recomendacao para RH e SESMT
- plano de apoio a lideranca
- alerta de fadiga, burnout ou quebra de continuidade

## 14. MVP recomendado

### Fase 1

- novo dashboard institucional premium
- check-in diario
- check-in semanal
- fila de pedidos de apoio
- saude ocupacional e saude mental agregadas
- leitura por unidade, setor e escala
- cultura e idioma em versao inicial
- anonimato e governanca

### Fase 2

- app mobile dedicado com offline
- carreira on/off
- matching de mentoria
- comunidades de pratica
- handoff educativo
- campanhas acionaveis por modulo

### Fase 3

- traducao assistida contextual
- integracao com plataformas externas de CQ
- predicao de absenteismo
- score de risco de lideranca
- benchmark entre unidades

## 15. Riscos de produto

### Se fizer do jeito errado

- o modulo empresa vira copia fraca de hospital/farmacia
- o app do colaborador vira formulario sem valor percebido
- excesso de coleta sensivel reduz adesao
- anonimato mal implementado gera risco juridico e reputacional

### Se fizer do jeito certo

- o ecossistema ganha um segundo produto premium de verdade
- a empresa passa a ter ferramentas reais de saude ocupacional e desenvolvimento
- os colaboradores ganham um produto proprio, util e discreto
- o SoloCRT amplia valor sem quebrar o epidemiologico

## 16. Decisao final

O caminho correto e:

- manter o epidemiologico intacto
- separar a plataforma healthtech institucional do app mobile do colaborador
- criar um motor corporativo proprio de IA e analytics
- posicionar `empresa` como saude ocupacional, desenvolvimento e continuidade operacional
