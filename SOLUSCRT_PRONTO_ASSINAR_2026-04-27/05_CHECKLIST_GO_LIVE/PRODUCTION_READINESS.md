# SolusCRT Saude - Checklist de Producao

Este checklist separa o que o codigo ja exige do que precisa ser configurado fora do repositorio antes de vender o SaaS.

## 1. Secrets obrigatorios

Configure na plataforma de hospedagem, nunca no Git:

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`
- `JWT_SECRET_KEY`
- `PAYMENT_PROVIDER=asaas`
- `DATABASE_URL`
- `PUBLIC_BASE_URL`
- `ASAAS_API_KEY`
- `ASAAS_BASE_URL=https://api.asaas.com/v3`
- `ASAAS_WEBHOOK_TOKEN`
- `ASAAS_USER_AGENT`
- `FIREBASE_SERVICE_ACCOUNT_JSON` ou `FIREBASE_SERVICE_ACCOUNT_PATH`
- `MAPBOX_ACCESS_TOKEN`
- `GOOGLE_MAPS_BROWSER_KEY`
- `GOOGLE_MAPS_IOS_KEY`

Depois de mover os secrets, rotacione chaves que ja ficaram em arquivos locais ou historico Git.

## 2. Infraestrutura minima

- Usar Postgres gerenciado em producao.
- Ativar HTTPS, HSTS e cookies seguros.
- Configurar backups automaticos diarios do banco.
- Configurar monitoramento de erro, uptime e latencia.
- Ter ambiente de staging separado antes do ambiente oficial.
- Executar `python manage.py migrate --noinput` durante deploy.
- Executar `python manage.py collectstatic --noinput` durante deploy.

## 3. App store

- Android: criar keystore propria e configurar `app_saude/android/key.properties` localmente ou variaveis `ANDROID_KEYSTORE_PATH`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`.
- iOS: configurar `GOOGLE_MAPS_IOS_KEY` no build setting do Xcode, revisar bundle id, capabilities, APNs e perfil de assinatura.
- Firebase: registrar APNs no Firebase para push iOS.
- Publicar somente depois que a URL de producao responder `/api/public/resumo`, `/api/public/mapa`, `/api/public/radar-local` e `/api/public/alertas`.

## 4. LGPD e saude publica

- Politica de privacidade clara sobre localizacao aproximada, sintomas, finalidade e retencao.
- Termos de uso explicando que o app nao fornece diagnostico medico.
- Canal de contato para privacidade/DPO.
- Processo de exclusao/anonimizacao quando aplicavel.
- Registro de auditoria para acoes administrativas e governamentais.
- Plano de resposta a incidente de seguranca.

## 5. Gate de publicacao

Antes de vender para empresas/governo:

- `python manage.py check`
- `DJANGO_ENV=production DJANGO_DEBUG=false python manage.py check --deploy`
- `python manage.py test`
- `cd app_saude && flutter analyze`
- `cd app_saude && flutter test`
- Smoke test em staging com login empresa, governo, console operacional, pagamento, mapa e envio publico.

## 6. Gate institucional

- Revisar a metodologia com profissional de epidemiologia/saude publica.
- Revisar politica LGPD com profissional juridico.
- Validar textos de alerta publico com autoridade responsavel.
- Testar fluxo de alerta: rascunho, revisao, aprovacao, publicacao e revogacao.
- Validar separacao visual entre relato cidadao, fonte oficial, estimativa IA e alerta confirmado.
