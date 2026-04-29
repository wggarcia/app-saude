# Guia Operacional - Contratos SolusCRT (Assinatura Online)

**Status:** PUBLICADO  
**Versao:** 1.0.0  
**Data:** 25/04/2026

## 1) Arquivos-base
- B2B (empresa/farmacia/hospital):  
  `docs/CONTRATO_SAAS_B2B_ANUAL_SOLUSCRT.md` (v1.0.0)
- B2G (governo):  
  `docs/CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT.md` (v1.0.0)

## 2) Campos que devem ser preenchidos antes de enviar
- Razao social da SolusCRT
- CNPJ da SolusCRT
- Endereco da SolusCRT
- Razao social/CNPJ/endereco do cliente
- Valor anual contratado
- Pacote contratado (usuarios/dispositivos/modulos)
- SLA contratado
- Foro (cidade/UF)
- Responsavel legal e cargo de cada parte

## 3) Fluxo recomendado de assinatura online
1. Gerar versao final em PDF com numero interno do contrato.
2. Anexar pacote e SLA como anexos oficiais.
3. Enviar para assinatura eletrônica (Clicksign, DocuSign, ZapSign ou similar).
4. Exigir autenticação minima do signatario (e-mail + evidencias de IP/data/hora).
5. Guardar o documento assinado, hash, log de assinatura e trilha de envio.
6. Registrar no CRM/ERP data de inicio, vencimento e renovacao.

## 4) Regras comerciais obrigatorias
- Governo: sempre contrato anual fechado.
- Empresa/farmacia/hospital: anual (ou mensal quando politica comercial permitir).
- Sem assinatura concluida: nao liberar escopo fora do teste.
- Toda excecao comercial deve ser aprovada pela operacao/diretoria.

## 5) Anexos minimos por contrato
- Anexo Comercial (pacote, limites e valores)
- Anexo SLA
- Anexo LGPD/DPA
- Politica de Seguranca e resposta a incidentes

## 6) Controle de versao contratual (obrigatorio)
1. Toda alteracao gera nova versao semanticamente numerada (ex: v1.0.1, v1.1.0, v2.0.0).
2. Nao sobrescrever historico: manter versoes anteriores arquivadas.
3. Registrar no contrato:
   - versao
   - data de publicacao
   - resumo da alteracao
4. Para novo cliente, sempre usar a versao mais recente publicada.
5. Para cliente ativo, aditivo deve citar a versao do contrato em vigor.
