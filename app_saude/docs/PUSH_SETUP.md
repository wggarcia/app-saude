# Push Setup

## O que ja esta pronto
- registro de token do aparelho no backend
- armazenamento de tokens publicos
- emissao de alerta governamental no painel
- tentativa de disparo via Firebase Admin no backend
- recebimento de notificacao no app com Firebase Messaging
- exibicao local quando a notificacao chega em primeiro plano

## O que falta para push real em producao

### Android
- criar projeto Firebase para `com.soluscrt.saude`
- baixar `google-services.json`
- colocar em `app_saude/android/app/google-services.json`

### iPhone
- criar app iOS no mesmo projeto Firebase para `com.soluscrt.saude`
- baixar `GoogleService-Info.plist`
- colocar em `app_saude/ios/Runner/GoogleService-Info.plist`
- configurar APNs Key no Apple Developer e no Firebase Cloud Messaging

### Backend
- instalar `firebase-admin`
- definir uma destas variaveis de ambiente:
  - `FIREBASE_SERVICE_ACCOUNT_JSON`
  - `FIREBASE_SERVICE_ACCOUNT_PATH`

## Variavel sugerida
`FIREBASE_SERVICE_ACCOUNT_JSON` com o JSON completo da service account do Firebase

## Fluxo
1. o app inicia e pede permissao de notificacao
2. o Firebase Messaging gera o token do aparelho
3. o app envia token + device_id + territorio-base ao backend
4. o governo publica um alerta no painel
5. o backend envia push para os aparelhos do recorte territorial correspondente

## Observacao
Sem os arquivos do Firebase e a credencial de backend, o sistema continua funcional, mas o push nativo do sistema operacional fica em modo inativo e o alerta aparece apenas quando o app abre e consulta o feed publico.
