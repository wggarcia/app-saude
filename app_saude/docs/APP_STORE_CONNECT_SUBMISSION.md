# SolusCRT Saude - App Store Connect

Guia operacional para preencher o App Store Connect da primeira versao iOS.

## Identificacao

- Nome do app: SolusCRT Saude
- Bundle ID: com.soluscrt.saude
- SKU: SOLUSCRT-SAUDE-IOS-001
- Idioma principal: Portugues (Brasil)
- Versao: 1.0.0
- Build recomendado para novo upload: 2
- Categoria principal sugerida: Saude e fitness
- Categoria secundaria sugerida: Utilidades ou Medicina

## Informacoes Promocionais

### Subtitulo

Radar epidemiologico colaborativo para sua regiao.

### Texto promocional

Acompanhe sinais de sintomas na sua regiao, visualize focos no mapa e receba alertas publicos oficiais quando disponiveis.

### Descricao

O SolusCRT Saude e um aplicativo de monitoramento epidemiologico colaborativo para a populacao.

Com ele, voce pode acompanhar o radar de sintomas da sua regiao, visualizar focos no mapa publico e enviar sinais anonimos de sintomas para apoiar a leitura territorial de riscos em saude.

O app foi criado para fortalecer a prevencao, a comunicacao publica e a percepcao regional de surtos, ajudando a populacao a acompanhar mudancas no territorio de forma simples e responsavel.

Recursos principais:
- Radar local com leitura da sua regiao.
- Mapa publico de focos e sintomas recentes.
- Envio anonimo de sintomas.
- Alertas publicos quando publicados por gestao autorizada.
- Orientacoes preventivas sem substituir atendimento medico.

Importante: o SolusCRT Saude nao realiza diagnostico medico, nao substitui consulta profissional e nao deve ser usado para emergencias. Em caso de agravamento, procure atendimento medico ou servico de urgencia.

### Palavras-chave

saude, epidemiologia, sintomas, radar, mapa, surto, prevencao, alerta, dengue, gripe

### URL de suporte

https://app-saude-p9n8.onrender.com/

### URL de marketing

https://app-saude-p9n8.onrender.com/

### URL da politica de privacidade

Publicar uma pagina propria antes de enviar para revisao. Sugestao de caminho:

https://app-saude-p9n8.onrender.com/privacidade/

## App Review

### Informacoes de contato

Preencher com dados reais do responsavel pelo app.

### Notas para revisao

O SolusCRT Saude e um app informativo e colaborativo de monitoramento epidemiologico territorial.

O app coleta sintomas informados voluntariamente e localizacao aproximada enquanto o app esta em uso para exibir radar regional, mapa publico e alertas. O app nao fornece diagnostico medico, nao substitui atendimento profissional e nao e destinado a emergencias.

O envio de sintomas e anonimo e possui controles contra repeticao e abuso para proteger a confiabilidade dos dados.

## Privacidade do App

### Tracking

- O app rastreia usuarios entre apps/sites de terceiros? Nao.
- Usa dados para publicidade de terceiros? Nao.
- Compartilha dados com data brokers? Nao.

### Dados coletados

Marcar que o app coleta:

- Saude e fitness: sintomas informados voluntariamente.
- Localizacao: localizacao aproximada para leitura regional.
- Identificadores: identificador tecnico do dispositivo para limitar repeticoes e abuso.
- Dados de uso/diagnostico: somente se logs tecnicos forem ativados em producao.

Finalidades:

- Funcionalidade do app.
- Prevencao de fraude ou seguranca.
- Analise agregada do servico, se aplicavel.

Dados sensiveis:

- Sintomas podem ser considerados dados de saude. Informar com transparencia.

Vinculo ao usuario:

- Nao ha cadastro pessoal no app publico.
- O envio e tratado de forma anonima, mas existe identificador tecnico do dispositivo para protecao antifraude. Se o formulario perguntar sobre associacao a dispositivo/identificador, responder com cautela e marcar identificador tecnico.

## Classificacao Etaria

Responder de forma conservadora:

- Conteudo medico/tratamento: nenhum ou infrequente, pois o app e informativo.
- Acesso irrestrito a web: nao.
- Compras no app: nao.
- Conteudo gerado por usuario: envio de sintomas estruturados, sem texto livre publico.
- Idade sugerida: 12+ ou conforme resultado automatico da Apple.

## Criptografia e Export Compliance

O app usa HTTPS/TLS para comunicacao com o backend.

Normalmente, para apps que usam apenas criptografia padrao do sistema operacional/HTTPS, responder que usa criptografia padrao e seguir o fluxo automatico da Apple. Confirmar no App Store Connect conforme as opcoes exibidas.

## Dispositivo e Build

O projeto local esta configurado para:

- Team ID: 3K2E6MP3S3
- Bundle ID: com.soluscrt.saude
- Version: 1.0.0
- Build: 2

Para gerar novo upload depois de corrigir o Xcode:

```bash
cd /Users/angelica/backend/app_saude
flutter clean
flutter pub get
flutter build ipa --release
```

Se o erro `AssetCatalogSimulatorAgent` aparecer, atualizar/reiniciar o Xcode antes de tentar novamente.
