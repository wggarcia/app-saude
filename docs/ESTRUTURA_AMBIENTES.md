# Estrutura dos ambientes SolusCRT

Este repositório mantém três superfícies separadas. A regra é simples: código de um ambiente não deve nascer dentro do outro.

## Backend Healthtech

- Raiz do repositório: `manage.py`, `backend/`, `api/`, `templates/`, `static/`.
- Responsável por APIs, dashboards web, autenticação, billing, gestão, SST, hospital, farmácia, governo e integrações.
- Não deve conter projeto Flutter solto na raiz.

## App público da população

- Diretório: `app_saude/`.
- Finalidade: radar epidemiológico público da população.
- Plataformas mantidas: Android, iOS e Web.
- Não deve receber telas de SST, empresa, funcionário, hospital ou farmácia.

## App ocupacional

- Diretório: `app_ocupacional/`.
- Finalidade: Saúde e Segurança do Trabalho, com acesso de empresa e trabalhador.
- Plataformas mantidas: Android, iOS e Web.
- Deve consumir APIs empresariais/SST do backend, sem misturar código no app público.

## Ambientes proibidos

As estruturas abaixo indicam cópia acidental ou ambiente no lugar errado:

- `backend/app-saude/`
- `app_saude/app_ocupacional/`
- `android/`, `ios/`, `linux/`, `macos/`, `windows/`, `web/`, `lib/` ou `test/` na raiz.

Use `scripts/check_two_apps_structure.sh` antes de deploy para validar a organização.
