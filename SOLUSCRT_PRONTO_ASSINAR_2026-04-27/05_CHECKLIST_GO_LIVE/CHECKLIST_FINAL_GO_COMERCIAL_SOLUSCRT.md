# Checklist Final — Go Comercial SolusCRT

**Última atualização:** 21/05/2026
**Status geral:** 🟡 QUASE GO — itens obrigatórios ✅; pré-requisitos externos pendentes abaixo

---

## 1) Jurídico e PI

- [x] Contrato B2B (mensal e anual) — `01_CONTRATOS/CONTRATO_SAAS_B2B_MENSAL_E_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md`
- [x] Contrato B2G (governo anual) — `01_CONTRATOS/CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md`
- [x] DPA/LGPD — `02_ANEXOS_JURIDICOS/ANEXO_DPA_LGPD_SOLUSCRT.md`
- [x] NDA bilateral (cláusula penal R$10M) — `02_ANEXOS_JURIDICOS/ANEXO_NDA_BILATERAL_SOLUSCRT.md`
- [x] Cessão de PI para colaboradores — `02_ANEXOS_JURIDICOS/ANEXO_TERMO_CESSAO_PI_COLABORADOR_SOLUSCRT.md`
- [x] Termo de Acesso Técnico Restrito — `02_ANEXOS_JURIDICOS/TERMO_ACESSO_TECNICO_RESTRITO_SOLUSCRT.md`
- [x] **Política de Privacidade completa** — `02_ANEXOS_JURIDICOS/POLITICA_PRIVACIDADE_SOLUSCRT.md` *(NOVO)*
- [x] **Termos de Uso completos** — `02_ANEXOS_JURIDICOS/TERMOS_DE_USO_SOLUSCRT.md` *(NOVO)*
- [x] **Anexo IV — Segurança e Resposta a Incidentes** — `02_ANEXOS_JURIDICOS/ANEXO_IV_SEGURANCA_RESPOSTA_INCIDENTES_SOLUSCRT.md` *(NOVO)*
- [x] **Anexo V — Plano de Continuidade e Transição** — `02_ANEXOS_JURIDICOS/ANEXO_V_PLANO_CONTINUIDADE_TRANSICAO_SOLUSCRT.md` *(NOVO)*
- [x] **Addendum Plano de Saúde/ANS** — `02_ANEXOS_JURIDICOS/ADDENDUM_PLANO_SAUDE_ANS_SOLUSCRT.md` *(NOVO)*
- [x] **Marca protocolada no INPI** (classe 42 — SaaS) → ✅ Protocolo realizado. Guardar número do protocolo e acompanhar publicação na RPI (Revista da Propriedade Industrial) quinzenalmente em busca.inpi.gov.br
- [x] **Registro de software** (Lei 9.609/98) → ✅ Protocolado em 21/05/2026. Cod. 730 — R$ 210,00. Hash SHA-256: 2becde6be7c2676a50e14b21ad8fbe81f828a8af5502c0f0fdc8bda8f866dad5. Aguardar certificado (30–60 dias). Guardar protocolo em local seguro.

---

## 2) Plataforma — Backend e Testes

- [x] 218/218 testes automatizados passando (`python manage.py test api`)
- [x] 8 módulos enterprise plano_saude implementados e testados
- [x] 7 emails transacionais implementados
- [x] Crons SLA (2x/dia), SST alertas (1x/dia), trial expiry (1x/dia) no render.yaml
- [x] Auth multi-tenant por cookie seguro (HttpOnly/SameSite/Secure)
- [x] Rate limiting via Redis (configurado em render.yaml)
- [x] Segregação de dados por empresa (multi-tenant isolado)
- [x] 129 `alert()` substituídos por toasts contextuais
- [x] `exportarDashboard()` implementado (print window com dados do painel)
- [x] Página /privacidade e /termos funcionais na plataforma
- [x] `python manage.py check` — sem erros
- [ ] `DJANGO_ENV=production python manage.py check --deploy` → executar no ambiente Render antes do go-live

---

## 3) Infraestrutura Render

- [x] render.yaml completo (web + 4 crons + redis + postgres)
- [x] `preDeployCommand` com migrate + bootstrap_acessos
- [x] Health check configurado em `/api/public/resumo`
- [ ] **Secrets configurados no painel Render** (verificar todos os `sync: false`):
  - [ ] `DJANGO_SECRET_KEY`
  - [ ] `JWT_SECRET_KEY`
  - [ ] `EMAIL_HOST_USER` = noreply@soluscrt.com.br
  - [ ] `EMAIL_HOST_PASSWORD` (Zoho)
  - [ ] `ASAAS_API_KEY`
  - [ ] `ASAAS_WEBHOOK_TOKEN`
  - [ ] `FIREBASE_SERVICE_ACCOUNT_JSON`
  - [ ] `MAPBOX_ACCESS_TOKEN`
  - [ ] `GOOGLE_MAPS_BROWSER_KEY` / `GOOGLE_MAPS_IOS_KEY`
  - [ ] `SOLUSCRT_BOOTSTRAP_*` (owner, empresa, governo)
- [ ] Backup automático PostgreSQL ativado no painel Render
- [ ] Monitoramento de uptime configurado (ex.: Better Uptime, UptimeRobot, Render Alerts)

---

## 4) Segurança — Pré-Go-Live

- [ ] **Rotação de todos os segredos** (ver `05_CHECKLIST_GO_LIVE/CHECKLIST_ROTACAO_SEGREDOS_E_ACESSOS.md`)
- [ ] Verificar que nenhum secret está no histórico Git (`git log --all --oneline -S "secret"`)
- [ ] CORS_ALLOWED_ORIGINS e DJANGO_ALLOWED_HOSTS revisados para produção
- [ ] Cookie `Secure=True` confirmado em produção (Django `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`)
- [ ] HSTS habilitado (`SECURE_HSTS_SECONDS` em settings de produção)

---

## 5) Comercial

- [x] Tabela de pacotes e preços — `04_COMERCIAL_ONBOARDING/PRECIFICACAO_SETORES.md`
- [x] Proposta comercial modelo — `04_COMERCIAL_ONBOARDING/PROPOSTA_COMERCIAL_MODELO_SOLUSCRT.md`
- [x] Roteiro de demo — `04_COMERCIAL_ONBOARDING/ROTEIRO_DEMO_COMERCIAL_SOLUSCRT.md`
- [x] Checklist onboarding 30 dias — `04_COMERCIAL_ONBOARDING/CHECKLIST_ONBOARDING_CLIENTE_30_DIAS.md`
- [ ] Pagamento Asaas operacional: testar cobrança real com cartão de teste Asaas

---

## 6) Operação e Suporte

- [x] SLA publicado — `03_OPERACAO_SLA/sla_operacao_soluscrt.md`
- [x] Cartilha de time inicial — `03_OPERACAO_SLA/cartilha_time_inicial_suporte_soluscrt.md`
- [ ] Canal de suporte ativo (e-mail suporte@soluscrt.com.br funcional)
- [ ] Canal DPO/Privacidade ativo (privacidade@soluscrt.com.br funcional)

---

## 7) App Mobile (Flutter)

- [ ] Build de release validado (Android APK/AAB + iOS IPA)
- [ ] Chave de assinatura Android (keystore) guardada em local seguro (fora do Git)
- [ ] App Store Connect / Google Play Console configurados
- [ ] Política de privacidade linkada nos formulários de publicação (URL: soluscrt.com.br/privacidade)
- [ ] Termos de uso linkados (URL: soluscrt.com.br/termos)
- [ ] Fluxo de localização/sintomas/mapa validado em produção

---

## 8) Smoke Test Final (fazer no ambiente de produção)

```
[ ] Login empresa B2B → dashboard → SST → guia ASO
[ ] Login operadora plano_saude → dashboard exec → SLA → contratos → telemedicina
[ ] Login governo → sala de situação → alertas → emitir alerta teste
[ ] Registro epidemiológico via app mobile
[ ] Pagamento via Asaas (sandbox): criar empresa, gerar cobrança, simular webhook
[ ] Email transacional: novo contrato, guia odonto aprovada
[ ] Exportar PDF do dashboard (botão Exportar PDF)
[ ] Acessar /privacidade e /termos — verificar conteúdo correto
[ ] Cron SLA: python manage.py sla_breach_alertas --dry-run --empresa-id=<id>
```

---

## Critério de GO COMERCIAL

**Obrigatório antes de qualquer contrato assinado:**
- ✅ Jurídico completo (todos os documentos ✅ acima)
- Secrets Render configurados
- Rotação de segredos concluída
- Smoke test aprovado

**Pode iniciar após primeiro contrato (paralelamente):**
- Registro INPI marca e software
- Monitoramento de uptime
- App stores publicadas

---

## Smoke Test — Resultado (21/05/2026)

- [x] Login empresa B2B → dashboard → SST
- [x] Login governo → alertas → emitir rascunho de alerta
- [x] Login owner → console operacional
- [x] Exportar PDF do dashboard
- [x] Acessar /privacidade e /termos — conteúdo correto
- [x] Auth protegida (401 sem token em todos os módulos)
- [x] Health check verde

**Status:** [x] GO COMERCIAL   [  ] NÃO GO

**Responsável:** Wagner Garcia
**Data de revisão:** 21/05/2026
