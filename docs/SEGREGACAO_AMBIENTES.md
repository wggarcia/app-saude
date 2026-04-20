# Segregacao de Ambientes de Acesso

Objetivo: reforcar confianca comercial separando as entradas e os fluxos de empresa, governo e operacao interna.

## Ambientes

- Empresa: `/` e `/login-empresa/`
- Governo: `/login-governo/`
- Operacao interna: `/operacao-central/`

## Regras aplicadas

- O portal empresarial nao mostra links para governo ou operacao interna.
- O portal governamental nao mostra link para empresa ou operacao interna.
- O console operacional nao aparece no portal publico.
- Credencial governamental nao entra pelo endpoint empresarial `/api/login-empresa`.
- Credencial empresarial nao entra pelo endpoint governamental `/api/login-governo`.
- O painel governamental continua protegido por tipo de conta e por `acesso_governo`.
- As APIs internas usam prefixo neutro `/api/operacao-central/`.

## Observacao de seguranca

Separar rotas aumenta confianca e reduz exposicao visual, mas nao substitui controles reais. A protecao principal continua sendo autenticacao, autorizacao por tipo de conta, cookies seguros, JWT, sessao unica, auditoria e deploy com HTTPS.
