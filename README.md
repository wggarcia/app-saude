# SoloCRT – Estrutura de Apps

Este repositório possui **2 apps Flutter separados** e um backend Django:

## 1) `app_saude` (POPULAÇÃO)
- App epidemiológico público.
- Sem acesso empresarial e sem portal do trabalhador.

## 2) `app_ocupacional` (SAÚDE OCUPACIONAL)
- App dedicado ao ambiente healthtech ocupacional.
- Entradas:
  - Acesso Empresarial
  - Portal do Trabalhador

## 3) Backend (Django)
- APIs e painéis institucionais na raiz do projeto.

---

## Rodar cada app separadamente

### App populacional
```bash
cd app_saude
flutter pub get
flutter run -d chrome
```

### App ocupacional
```bash
cd app_ocupacional
flutter pub get
flutter run -d chrome
```

### Scripts prontos (recomendado)
```bash
# Abrir app_ocupacional no Xcode (gera iOS, instala pods e abre workspace)
./scripts/open_xcode_ocupacional.sh

# Rodar app_ocupacional no Chrome na porta 8080 (ou outra porta)
./scripts/run_ocupacional_web.sh 8080

# Preparar os 2 apps (app_saude + app_ocupacional) com plataformas iOS/Android/Web
./scripts/bootstrap_two_apps.sh

# Validar estrutura final sem duplicação
./scripts/check_two_apps_structure.sh
```

---

## Regra de produto
- O app populacional deve permanecer limpo e focado em epidemiologia.
- Funcionalidades empresariais/trabalhador ficam somente no `app_ocupacional`.
