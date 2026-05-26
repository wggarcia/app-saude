# Roteiro de Homologação Produção — SST SolusCRT

Data base: 26/05/2026

## Como usar
1. Abra a planilha: `docs/CHECKLIST_HOMOLOGACAO_PRODUCAO_SST_2026-05-26.csv`.
2. Execute os casos na ordem `HML-001` até `HML-036`.
3. Em cada linha, preencha:
   - `Responsavel`
   - `Inicio` e `Fim`
   - `Status` (`OK`, `NOK`, `BLOQUEADO`)
   - `Evidencia` (print, protocolo eSocial, PDF, link interno)
   - `Observacoes`
4. Atualize `GoNoGo` para `SIM` somente quando o item estiver `OK`.

## Critério de liberação
- `GO` apenas se:
  - Todos os itens `CRITICA` estiverem `OK`;
  - Não houver `NOK` sem plano de correção imediato com prazo e responsável;
  - Eventos eSocial `S-2210`, `S-2220`, `S-2230`, `S-2240` transmitidos com protocolo válido.

## Evidências mínimas obrigatórias
- Diagnóstico gov.br em produção (`HML-003`).
- 4 protocolos eSocial (um por evento crítico).
- 1 PDF válido de PPP e 1 PDF válido de laudo técnico.
- 1 evidência de importação em lote (EPI/EPC ou laboratório).
- 1 print da Gerência Executiva sem erro visual.

## Classificação de severidade
- `CRITICA`: bloqueia go-live.
- `ALTA`: pode bloquear conforme impacto operacional/regulatório.
- `MEDIA`: corrigir em janela acordada.

## Recomendação de execução
- Janela sugerida: 2h a 3h.
- Equipe mínima: SST, RH, Segurança do Trabalho, TI e Gestão.
- Encerramento com ata curta de decisão (`GO` ou `NO-GO`) e próximos passos.
