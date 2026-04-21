# Manual de Treinamento Interno - SolusCRT Saude

## 1. O que e o SolusCRT

O SolusCRT Saude e uma plataforma SaaS de sala de controle epidemiologica. Ela combina app populacional, mapas de risco, IA, fontes oficiais brasileiras, alertas territoriais e paineis separados para empresas, farmacias, hospitais, governo e operacao interna.

O produto nao deve ser explicado como "um mapa". A forma correta e:

> SolusCRT e uma sala de controle epidemiologica com IA para antecipar focos de sintomas, apoiar decisoes de saude e conectar populacao, empresas, hospitais, farmacias e governo.

## 2. Publicos do projeto

### Populacao

Usa o app gratuito para:

- Enviar sintomas de forma colaborativa.
- Visualizar focos publicos da propria regiao.
- Receber alertas oficiais emitidos pelo governo.

### Empresas

Usam o SaaS para:

- Monitorar riscos de surtos que afetam colaboradores.
- Reduzir afastamentos.
- Acompanhar unidades, bairros e regioes de atuacao.
- Ver sinais de crescimento ou queda de sintomas.

### Farmacias

Usam o SaaS para:

- Identificar crescimento de sintomas por bairro e municipio.
- Planejar estoque de medicamentos e produtos.
- Antecipar demanda por classes de sintomas e doencas provaveis.

### Hospitais, clinicas e laboratorios

Usam o SaaS para:

- Preparar triagem e pronto atendimento.
- Monitorar pressao assistencial por territorio.
- Antecipar aumento de demanda por sindromes respiratorias, arboviroses e outras condicoes.

### Governo

Usa ambiente dedicado e separado para:

- Monitoramento epidemiologico institucional.
- Cruzamento com fontes oficiais.
- Emissao de alertas para o app da populacao.
- Apoio a decisoes de vigilancia em saude.
- Contrato anual fechado, sem mensalidade simples.

### Operacao interna SolusCRT

Ambiente da empresa dona da SaaS para:

- Gerenciar clientes.
- Ajustar pacotes.
- Ver uso, dispositivos, receita estimada e sinais de infraestrutura.
- Controlar inadimplencia, renovacao e ativacao.

## 3. Ambientes e rotas

- Empresa: `/login-empresa/`
- Governo: `/login-governo/`
- Operacao interna: `/operacao-central/`
- Dashboard empresa: `/dashboard/`
- Dashboard farmacia: `/dashboard-farmacia/`
- Dashboard hospital: `/dashboard-hospital/`
- Dashboard governo: `/dashboard-governo/`
- App/API publica: `/api/public/...`

Nunca envie um cliente empresarial para o ambiente de governo. Nunca envie governo para o ambiente empresarial. Essa separacao e parte da proposta de confianca.

## 4. Conceitos essenciais

### SaaS

Software como Servico. O cliente acessa pela internet e paga pelo direito de uso, suporte, infraestrutura e evolucao da plataforma.

### B2B

Venda para empresas. Exemplo: farmacias, hospitais, industrias, redes privadas e clinicas.

### B2G

Venda para governo. Exemplo: prefeitura, secretaria municipal, secretaria estadual, consorcio publico.

### MRR

Receita recorrente mensal. Usada principalmente para empresas privadas.

### ACV

Valor anual do contrato. Muito importante para governo e grandes empresas.

### LGPD

Lei Geral de Protecao de Dados. Define regras para tratamento de dados pessoais e dados sensiveis. No SolusCRT, a comunicacao deve reforcar dados agregados, finalidade de saude publica/epidemiologica, seguranca e governanca.

### IA

Inteligencia Artificial. No SolusCRT, a IA ajuda a classificar sinais, estimar risco, comparar crescimento, sugerir atencao territorial e apoiar decisao. Nao substitui medico, vigilancia oficial ou diagnostico laboratorial.

### Epidemiologia

Area que estuda distribuicao, frequencia e fatores relacionados a doencas em populacoes.

### Vigilancia epidemiologica

Monitoramento continuo para detectar, investigar e responder a riscos de saude.

### Incidencia

Novos casos em um periodo. Exemplo: casos novos por 100 mil habitantes.

### Prevalencia

Total de casos existentes em um periodo ou populacao.

### Letalidade

Proporcao de pessoas que morrem entre os casos da doenca.

### Mortalidade

Obitos em relacao a populacao total.

### Surto

Aumento de casos acima do esperado em uma area ou grupo.

### Endemia

Doenca presente de forma constante em uma regiao.

### Epidemia

Aumento importante de casos em uma regiao.

### Pandemia

Epidemia com espalhamento internacional ou global.

### SRAG

Sindrome Respiratoria Aguda Grave. Indicador usado em vigilancia respiratoria.

### Arboviroses

Doencas transmitidas por artropodes, especialmente mosquitos. Exemplos: dengue, chikungunya e zika.

### Rt

Numero efetivo de reproducao. Ajuda a entender se uma doenca tende a crescer ou diminuir.

### Georreferenciamento

Associar dados a uma localidade: bairro, municipio, estado, coordenada ou territorio.

### Hotspot

Area com concentracao de sinais/casos.

### Decaimento temporal

Regra do SolusCRT: se nao houver novos envios, o foco nao cai imediatamente. Ele fica preservado por 10 dias e depois reduz gradualmente ate 30 dias. Isso evita uma falsa sensacao de melhora.

## 5. Fontes oficiais brasileiras

### IBGE/SIDRA

Fonte para populacao e denominadores territoriais. Ajuda a calcular taxas por 100 mil habitantes.

### InfoDengue / Fiocruz

Fonte para arboviroses como dengue, chikungunya e zika.

### InfoGripe / Fiocruz

Fonte para vigilancia respiratoria e SRAG.

### OpenDataSUS

Portal de dados abertos do Ministerio da Saude.

### DATASUS

Conjunto de sistemas nacionais de informacao em saude.

### SINAN

Sistema de Informacao de Agravos de Notificacao.

### SIM

Sistema de Informacao sobre Mortalidade.

### SIH

Sistema de Informacoes Hospitalares.

### SIVEP-Gripe

Sistema usado para vigilancia de SRAG e influenza.

## 6. Como explicar o mapa

O mapa mostra focos territoriais com base em sinais enviados pelo app e dados agregados. O ponto ou cor nao e diagnostico medico. Ele representa risco territorial e tendencia.

Frase recomendada:

> O mapa mostra onde os sinais estao surgindo, crescendo ou diminuindo, permitindo resposta mais rapida antes que o problema vire crise.

## 7. Como explicar o app

O app e gratuito para a populacao. Ele tem tres funcoes principais:

- Enviar sintomas.
- Ver mapa publico da propria regiao.
- Receber alertas oficiais.

Frase recomendada:

> O cidadao participa como sensor colaborativo de saude, e a plataforma transforma esses sinais em inteligencia territorial agregada.

## 8. Como explicar a IA

A IA nao promete diagnostico individual. Ela trabalha com padroes populacionais, crescimento de sintomas, sinais suspeitos, confianca do envio e provaveis grupos de doencas.

Nunca diga:

- "A IA diagnostica a doenca da pessoa."
- "A IA substitui o medico."
- "O sistema garante prever toda epidemia."

Diga:

- "A IA apoia vigilancia e tomada de decisao."
- "A IA identifica padroes e anomalias."
- "A IA ajuda a priorizar territorios e a antecipar riscos."

## 9. Como explicar seguranca

Pontos de seguranca:

- Ambientes separados para empresa, governo e operacao.
- Controle de usuarios.
- Controle de dispositivos.
- Sessao unica por usuario.
- Antifraude no envio de sintomas.
- Dados agregados para monitoramento territorial.
- Auditoria e trilha institucional.
- Contratos e LGPD como base de governanca.

## 10. Precos por setor

### Empresas

- Empresa Starter: R$ 799/mes ou R$ 7.990/ano.
- Empresa Profissional: R$ 1.990/mes ou R$ 19.900/ano.
- Empresa Enterprise: R$ 4.900/mes ou R$ 49.000/ano.

### Farmacias

- Farmacia Local: R$ 699/mes ou R$ 6.990/ano.
- Rede Farmaceutica Regional: R$ 6.000/mes ou R$ 60.000/ano.

### Hospitais

- Hospital Medio: R$ 12.000/mes ou R$ 120.000/ano.
- Rede Hospitalar: R$ 60.000/mes ou R$ 600.000/ano.

### Governo

Governo e somente contrato anual fechado:

- Municipio pequeno: R$ 120.000/ano.
- Municipio medio: R$ 360.000/ano.
- Capital/regiao metropolitana: R$ 1.200.000/ano.
- Estado: R$ 3.600.000/ano.

## 11. Perguntas frequentes internas

### O SolusCRT ja substitui sistemas oficiais?

Nao. Ele complementa e antecipa sinais. Fontes oficiais validam e contextualizam.

### O app da populacao e pago?

Nao. A populacao usa gratuitamente.

### Governo paga mensal?

Nao. Governo deve ser contrato anual fechado.

### O mapa pode ficar vazio?

Sim, se nao houver sinais recentes. Isso e normal em banco novo ou regiao sem envios. O mapa cresce conforme a populacao usa o app.

### O cliente pode instalar em varios computadores?

Sim, conforme pacote contratado. O sistema controla usuarios e dispositivos.

## 12. Treinamento recomendado

1. Estudar este manual.
2. Acessar os tres ambientes: empresa, governo e operacao.
3. Simular envio pelo app.
4. Ver o hotspot aparecer no mapa.
5. Explicar o produto em 60 segundos.
6. Explicar os pacotes por setor.
7. Treinar objecoes de LGPD, preco, governo e confiabilidade.
