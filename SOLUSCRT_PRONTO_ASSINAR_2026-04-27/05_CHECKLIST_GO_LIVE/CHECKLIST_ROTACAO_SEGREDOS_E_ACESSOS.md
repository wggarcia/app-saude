# Checklist de Rotacao de Segredos e Acessos

## 1. Chaves de infraestrutura
- [ ] `ASAAS_API_KEY` rotacionada
- [ ] `ASAAS_WEBHOOK_TOKEN` rotacionado
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` rotacionado
- [ ] Chave APNs (Apple Push) validada
- [ ] `MAPBOX_ACCESS_TOKEN` rotacionado
- [ ] Demais tokens internos revisados

## 2. Ambientes
- [ ] Variaveis de ambiente atualizadas no Render
- [ ] Confirmado que nao ha chave antiga ativa
- [ ] Deploy concluido apos rotacao
- [ ] Testes de sanidade executados (login, pagamento, push, mapa)

## 3. Controles de acesso
- [ ] Contas de admin revisadas
- [ ] Contas inativas removidas/desativadas
- [ ] Senhas de alto privilegio trocadas
- [ ] 2FA ativado nas contas criticas

## 4. Evidencias
- [ ] Registro da data/hora de rotacao
- [ ] Responsavel pela rotacao identificado
- [ ] Evidencia de teste pos-rotacao anexada

## 5. Cadencia recomendada
- Rotacao obrigatoria a cada 90 dias
- Rotacao imediata em caso de exposicao ou suspeita de vazamento
