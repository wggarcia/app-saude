# Pacote de Submissao Apple - SolusCRT Saude

Use este arquivo como fonte unica para preencher App Store Connect e responder a revisao.

## Status tecnico

- Bundle ID: `com.soluscrt.saude`
- Versao: `1.0.0`
- Build atual no `pubspec.yaml`: `15`
- Privacy Policy URL: `https://app-saude-p9n8.onrender.com/privacidade/`
- Support URL: `https://app-saude-p9n8.onrender.com/suporte/`
- Marketing URL: `https://app-saude-p9n8.onrender.com/`
- Tracking: nao
- ATT prompt: nao usar, porque nao ha tracking para publicidade ou data brokers.
- Privacy Manifest: `app_saude/ios/Runner/PrivacyInfo.xcprivacy`
- Localizacao iOS: somente `NSLocationWhenInUseUsageDescription`
- Background modes: `remote-notification`
- Export Compliance: HTTPS/TLS padrao, `ITSAppUsesNonExemptEncryption=false`

## Texto curto

Radar epidemiologico colaborativo para acompanhar sinais de sintomas, mapa publico e alertas territoriais.

## Descricao

O SolusCRT Saude e um aplicativo informativo de monitoramento epidemiologico colaborativo para a populacao.

Com ele, voce pode acompanhar o radar de sintomas da sua regiao, visualizar focos no mapa publico e enviar sinais sem cadastro nominal para apoiar a leitura territorial de riscos em saude.

O app foi criado para fortalecer prevencao, comunicacao publica e percepcao regional de surtos, ajudando a populacao a acompanhar mudancas no territorio de forma simples e responsavel.

Recursos principais:
- Radar local com leitura da sua regiao.
- Mapa publico de focos e sintomas recentes.
- Envio de sintomas estruturados sem cadastro nominal.
- Alertas publicos quando publicados por gestao autorizada.
- Orientacoes preventivas sem substituir atendimento medico.

Importante: o SolusCRT Saude nao realiza diagnostico medico, nao substitui consulta profissional, nao prescreve tratamento e nao deve ser usado para emergencias. Em caso de agravamento, procure atendimento medico ou servico de urgencia.

## Notas para App Review

O SolusCRT Saude e um app informativo e colaborativo de monitoramento epidemiologico territorial.

O app coleta sintomas informados voluntariamente e localizacao enquanto o app esta em uso para exibir radar regional, mapa publico e alertas. O app nao fornece diagnostico medico, nao substitui atendimento profissional, nao prescreve tratamento e nao e destinado a emergencias.

O envio de sintomas nao exige cadastro nominal e possui controles contra repeticao e abuso. O identificador tecnico usado para antifraude e um UUID aleatorio gerado pelo proprio app e salvo localmente, nao um identificador nativo permanente do aparelho.

Politica de privacidade publica: https://app-saude-p9n8.onrender.com/privacidade/

O app nao usa dados para publicidade de terceiros, nao vende dados pessoais, nao compartilha dados com data brokers e nao rastreia usuarios entre apps ou sites de terceiros.

## App Privacy - Respostas recomendadas

Tracking:
- Usa dados para rastrear usuario entre apps/sites de terceiros? `Nao`
- Usa IDFA? `Nao`
- Usa data broker? `Nao`

Dados coletados:
- Health and Fitness / Health: `Sim`
  - Conteudo: sintomas informados voluntariamente.
  - Uso: App Functionality, Fraud Prevention/Security.
  - Vinculado ao usuario/dispositivo: responder de forma conservadora como `Sim`.
  - Tracking: `Nao`
- Location: `Sim`
  - Declaracao: Precise Location, pois o backend recebe latitude/longitude no envio de sintomas.
  - Uso: App Functionality, Fraud Prevention/Security.
  - Vinculado ao usuario/dispositivo: responder de forma conservadora como `Sim`.
  - Tracking: `Nao`
- Identifiers / Device ID: `Sim`
  - Conteudo: UUID aleatorio app-scoped e token de notificacao.
  - Uso: App Functionality, Fraud Prevention/Security, envio de alertas.
  - Vinculado ao usuario/dispositivo: `Sim`.
  - Tracking: `Nao`
- Diagnostics: `Somente se logs/crash/performance forem coletados por servicos ativados em producao.`

Dados vinculados ao usuario:
- Nao ha cadastro pessoal no app publico.
- Como ha identificador tecnico app-scoped e token de notificacao, responder de forma conservadora se o App Store Connect perguntar sobre vinculo a identificador/dispositivo.

## Permissoes

Location purpose string:

```text
O SolusCRT Saude usa sua localizacao enquanto o app esta aberto para mostrar riscos epidemiologicos da sua regiao e enviar sintomas com recorte territorial.
```

Temporary precise location:

```text
O SolusCRT Saude precisa confirmar sua localizacao precisa no momento do envio para nao registrar sintomas na cidade errada.
```

## Checklist antes de enviar

```bash
cd /Users/angelica/backend
python3 manage.py check

cd /Users/angelica/backend/app_saude
flutter analyze
flutter test
flutter build ios --release --no-codesign
```

No App Store Connect:

```text
[ ] Privacy Policy URL aponta para /privacidade/
[ ] Support URL aponta para /suporte/
[ ] App Privacy bate com este arquivo
[ ] Review Notes coladas
[ ] Screenshots nao prometem diagnostico, tratamento ou previsao clinica individual
[ ] Descricao evita termos como diagnostico, triagem medica, prescricao ou emergencia
[ ] Build novo enviado e selecionado
```
