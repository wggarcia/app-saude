# SolusCRT Ocupacional

App Flutter dedicado ao ambiente de Saúde e Segurança do Trabalho.

## Escopo

- Acesso da empresa para painel SST.
- Acesso do trabalhador para perfil, ASOs e treinamentos.
- Consumo das APIs empresariais/SST do backend Django.

Este app não deve receber telas do radar epidemiológico público. O app da população fica em `../app_saude`.

## Execução

```bash
flutter pub get
flutter run
```

Para apontar para outro backend:

```bash
flutter run --dart-define=API_BASE_URL=https://seu-backend
```
