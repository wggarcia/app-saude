# Ordem de Assinatura e Execucao - SolusCRT

## 1) Preenchimento unico (5 a 10 min)
Preencha primeiro:
- `FICHA_DADOS_PREENCHIMENTO_UNICO.md`

Com isso, voce evita retrabalho em todos os contratos.

## 2) Assinatura com empresas/farmacias/hospitais
Documento principal:
- `../01_CONTRATOS/CONTRATO_SAAS_B2B_MENSAL_E_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md`

Anexos obrigatorios:
- `../02_ANEXOS_JURIDICOS/ANEXO_DPA_LGPD_SOLUSCRT.md`
- `../03_OPERACAO_SLA/sla_operacao_soluscrt.md`
- Anexo comercial do pacote (usuarios/maquinas/valor)

## 3) Assinatura com governo
Documento principal:
- `../01_CONTRATOS/CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md`

Anexos obrigatorios:
- `../02_ANEXOS_JURIDICOS/ANEXO_DPA_LGPD_SOLUSCRT.md`
- `../03_OPERACAO_SLA/sla_operacao_soluscrt.md`
- Termo de referencia/escopo e matriz de responsabilidades

## 4) Assinatura online (padrao)
1. Exportar contrato em PDF.
2. Subir no provedor de assinatura (Clicksign, DocuSign, ZapSign ou similar).
3. Exigir assinatura de representante legal de ambas as partes.
4. Ativar registro de trilha: IP, data/hora, hash e e-mail.
5. Arquivar PDF assinado + comprovante de trilha na pasta do cliente.

## 5) Pos-assinatura (go-live cliente)
1. Validar pagamento/contrato ativo.
2. Criar usuario administrador do cliente.
3. Aplicar pacote (usuarios/maquinas).
4. Treinamento de onboarding.
5. Check de primeiro acesso e aceite.

## 6) Bloqueios comerciais (nao abrir excecao)
- Nao liberar producao sem contrato assinado.
- Nao liberar governo em contrato mensal.
- Nao operar sem aceite de LGPD/DPA.
- Nao vender SLA critico sem escala operacional definida.
