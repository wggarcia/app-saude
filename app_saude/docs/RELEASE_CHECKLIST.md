# Release Checklist

## Identidade
- Confirmar nome final `SolusCRT Saude`
- Definir icone final em alta resolucao
- Definir splash final com arte proprietaria

## Android
- Confirmar `applicationId = com.soluscrt.saude`
- Criar keystore de producao
- Configurar assinatura release no Gradle
- Gerar `flutter build appbundle --release`
- Preencher ficha da Play Store

## iOS
- Confirmar bundle `com.soluscrt.saude`
- Validar time de assinatura Apple
- Configurar certificados e provisioning profile
- Gerar `flutter build ipa --release`
- Preencher App Privacy e ficha da App Store

## Produto e compliance
- Revisar politica de privacidade publica
- Revisar texto de uso de localizacao
- Revisar aviso de que o app nao substitui atendimento medico
- Validar fluxo antifraude e limites de envio publico

## QA
- Rodar `flutter analyze`
- Rodar `flutter test`
- Validar localizacao no Android
- Validar localizacao no iPhone
- Validar envio unico por rede/aparelho
- Validar radar local e mapa publico

## Publicacao
- Preparar 4 capturas de tela por loja
- Definir texto final de store listing
- Publicar primeiro em faixa de testes fechados
- Monitorar crash, latencia e taxa de envio
