# Coletor PEC → SoloCRT

Leva as visitas domiciliares registradas pelos agentes comunitários de saúde (no tablet/e-SUS Território → PEC) para o painel de ACS do SoloCRT. Roda na rede da prefeitura, ao lado do PEC, e só **lê** o banco do PEC.

## Antes de começar

1. No SoloCRT, um usuário de TI ou da gerência gera uma **chave de API** na Plataforma de TI do Governo (Chaves de API). A chave aparece uma vez só, então guarde.
2. Peça à TI do município um usuário PostgreSQL **somente leitura** no banco do PEC.
3. Instale Python 3.10+ e as dependências:

```bash
pip install "psycopg[binary]" requests
```

## Uso

```bash
export PEC_DSN="postgresql://leitor:SENHA@localhost:5433/esus"
export SOLOCRT_API_TOKEN="<chave de API>"
```

Primeiro confira se o banco tem o que o coletor espera:

```bash
python coletor_pec.py --diagnostico
```

Veja o que seria enviado, sem enviar nada:

```bash
python coletor_pec.py --dry-run
```

Envie:

```bash
python coletor_pec.py
```

O coletor guarda em `coletor_pec_estado.json` até onde já enviou. Na próxima execução, continua dali. Reenviar a mesma visita não duplica: ela é atualizada. Para rodar todo dia, agende no cron (Linux) ou no Agendador de Tarefas (Windows).

## Limitações conhecidas

- **Os nomes de tabelas e colunas do PEC ainda não foram validados num PEC real** e mudam entre versões. O `--diagnostico` mostra o que foi e o que não foi encontrado. Se faltar algo obrigatório, o coletor não envia nada. Ajuste `CANDIDATOS` no início de `coletor_pec.py`.
- Visitas importadas do PEC já estão no e-SUS: o SoloCRT nunca as reexporta.
