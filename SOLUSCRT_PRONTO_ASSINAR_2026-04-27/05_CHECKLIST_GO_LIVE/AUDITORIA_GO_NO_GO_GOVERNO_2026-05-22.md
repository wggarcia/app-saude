# Auditoria Go/No-Go Governo — 22/05/2026

**Responsável pela revisão:** Codex + Wagner Garcia  
**Escopo:** prontidão técnica, operacional e documental para contratação governamental da SolusCRT  
**Conclusão executiva:** `QUASE GO`

## 1. Decisão objetiva

Hoje a SolusCRT está **pronta para demo, proposta comercial, piloto controlado e negociação institucional séria**.

Hoje a SolusCRT **ainda não está em nível de “100% pronto para assinatura governamental sem ressalvas”** por 3 motivos centrais:

1. o contrato governo pronto para assinatura ainda contém placeholders do órgão contratante e do valor;
2. a prontidão de produção depende de confirmação operacional no painel Render para secrets, canais e rotinas externas;
3. faltam evidências fechadas de operação institucional ativa, especialmente suporte, privacidade/DPO, backup e monitoramento.

## 2. O que foi validado nesta auditoria

### 2.1 Backend local

- `python3 manage.py check` → sem erros
- `python3 manage.py makemigrations --check --dry-run` → sem migrações pendentes
- `python3 manage.py test api.tests.PublicApiTests api.tests.TemporalDecayTests api.test_dashboard_sector_access` → **20 testes OK**

### 2.2 Produção pública

Validação feita em [https://app-saude-p9n8.onrender.com](https://app-saude-p9n8.onrender.com):

- `/api/public/resumo` → `200`
- `/api/public/mapa` → `200`
- `/api/public/radar-local?cidade=Sao%20Paulo&estado=SP` → `200`
- `/api/public/alertas` → `200`
- `/privacidade/` → `200`
- `/termos/` → `200`
- `/seguranca-lgpd/` → `200`

### 2.3 Guard rails de produção já existentes no código

O projeto já impede subida “frouxa” em produção:

- exige `DJANGO_SECRET_KEY` e `JWT_SECRET_KEY` longas em produção;
- exige `DATABASE_URL` de PostgreSQL gerenciado em produção;
- exige `ASAAS_WEBHOOK_TOKEN` em produção;
- ativa cookies seguros, redirect HTTPS e HSTS por padrão em produção.

Referências:

- [backend/settings.py](/Users/angelica/backend/backend/settings.py:44)
- [backend/settings.py](/Users/angelica/backend/backend/settings.py:86)
- [backend/settings.py](/Users/angelica/backend/backend/settings.py:270)
- [backend/settings.py](/Users/angelica/backend/backend/settings.py:280)

### 2.4 Infraestrutura declarada

O `render.yaml` já traz uma base boa de operação:

- `DJANGO_ENV=production`
- `DJANGO_DEBUG=false`
- `healthCheckPath: /api/public/resumo`
- web service + PostgreSQL + Redis + crons de operação
- secrets marcados como `sync: false` para configuração no painel

Referência:

- [render.yaml](/Users/angelica/backend/render.yaml:1)

### 2.5 Pacote jurídico e operacional

Existe material consistente para contratação e governança:

- contrato governo anual
- política de privacidade
- termos de uso
- anexo de segurança e resposta a incidentes
- anexo de continuidade e transição
- SLA operacional
- checklist comercial/go-live

Referências:

- [CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/01_CONTRATOS/CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md:1)
- [ANEXO_IV_SEGURANCA_RESPOSTA_INCIDENTES_SOLUSCRT.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/02_ANEXOS_JURIDICOS/ANEXO_IV_SEGURANCA_RESPOSTA_INCIDENTES_SOLUSCRT.md:1)
- [ANEXO_V_PLANO_CONTINUIDADE_TRANSICAO_SOLUSCRT.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/02_ANEXOS_JURIDICOS/ANEXO_V_PLANO_CONTINUIDADE_TRANSICAO_SOLUSCRT.md:1)
- [sla_operacao_soluscrt.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/03_OPERACAO_SLA/sla_operacao_soluscrt.md:1)
- [CHECKLIST_FINAL_GO_COMERCIAL_SOLUSCRT.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/05_CHECKLIST_GO_LIVE/CHECKLIST_FINAL_GO_COMERCIAL_SOLUSCRT.md:1)

## 3. Bloqueadores reais para “100% pronto governo”

### 3.1 Contrato governo ainda não está pronto para assinatura literal

O contrato base do governo ainda contém placeholders críticos:

- `[ORGAO/ENTE PUBLICO]`
- `[CNPJ ORGAO]`
- `[ENDERECO]`
- `[NOME AUTORIDADE]`
- `[CPF]`
- `[CARGO]`
- `[VALOR ANUAL]`

Enquanto isso não for preenchido para o órgão específico, o material está pronto como **template de contratação**, mas não como **instrumento pronto para assinatura final**.

Referência:

- [CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/01_CONTRATOS/CONTRATO_SAAS_GOVERNO_ANUAL_SOLUSCRT_PRONTO_ASSINAR.md:11)

### 3.2 Produção exige secrets e serviços reais confirmados no Render

O repositório mostra claramente que a plataforma depende da configuração manual dos secrets abaixo no painel:

- `DJANGO_SECRET_KEY`
- `JWT_SECRET_KEY`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `ASAAS_API_KEY`
- `ASAAS_WEBHOOK_TOKEN`
- `FIREBASE_SERVICE_ACCOUNT_JSON`
- `MAPBOX_ACCESS_TOKEN`
- `GOOGLE_MAPS_BROWSER_KEY`
- `GOOGLE_MAPS_IOS_KEY`
- `SOLUSCRT_BOOTSTRAP_*`

Isso é bom do ponto de vista de segurança, mas significa que a auditoria local **não substitui** a confirmação operacional no painel Render.

Referência:

- [render.yaml](/Users/angelica/backend/render.yaml:33)

### 3.3 `check --deploy` não pode ser carimbado só no ambiente local de desenvolvimento

Rodando `python3 manage.py check --deploy` no contexto local atual, aparecem warnings de ambiente de dev.

Quando a configuração é forçada para “produção”, o próprio projeto bloqueia a inicialização se secrets e infraestrutura obrigatórios não estiverem presentes, o que mostra uma proteção correta do sistema.

Conclusão: para fechar este item como evidência de go-live, a checagem deve ser executada **no Render ou em shell com variáveis reais de produção**.

Referências:

- [backend/settings.py](/Users/angelica/backend/backend/settings.py:86)
- [backend/settings.py](/Users/angelica/backend/backend/settings.py:270)
- [CHECKLIST_FINAL_GO_COMERCIAL_SOLUSCRT.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/05_CHECKLIST_GO_LIVE/CHECKLIST_FINAL_GO_COMERCIAL_SOLUSCRT.md:39)

### 3.4 Canais institucionais ainda precisam de evidência funcional

Há referências a:

- `suporte@soluscrt.com.br`
- `privacidade@soluscrt.com.br`

Mas esta auditoria não validou envio/recebimento real desses canais. Para governo, isso precisa estar operacional e testado.

Referências:

- [templates/status.html](/Users/angelica/backend/templates/status.html:106)
- [api/views.py](/Users/angelica/backend/api/views.py:928)
- [CHECKLIST_FINAL_GO_COMERCIAL_SOLUSCRT.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/05_CHECKLIST_GO_LIVE/CHECKLIST_FINAL_GO_COMERCIAL_SOLUSCRT.md:88)

### 3.5 Backup e monitoramento precisam de evidência operacional, não só documental

Os documentos falam em backup, monitoramento e resposta a incidentes, e o `render.yaml` possui `healthCheckPath` e crons. Mas ainda falta evidência concreta de:

- backup ativo e restaurável;
- monitoramento externo de uptime;
- canal de alerta operacional recebendo eventos;
- rotina de teste de restauração.

Referências:

- [ANEXO_IV_SEGURANCA_RESPOSTA_INCIDENTES_SOLUSCRT.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/02_ANEXOS_JURIDICOS/ANEXO_IV_SEGURANCA_RESPOSTA_INCIDENTES_SOLUSCRT.md:40)
- [sla_operacao_soluscrt.md](/Users/angelica/backend/SOLUSCRT_PRONTO_ASSINAR_2026-04-27/03_OPERACAO_SLA/sla_operacao_soluscrt.md:162)
- [render.yaml](/Users/angelica/backend/render.yaml:9)

## 4. Classificação final por cenário

- **Demo / apresentação institucional:** `GO`
- **Proposta comercial e negociação:** `GO`
- **Piloto controlado com órgão público:** `GO`, com ata de escopo e ambiente validado
- **Assinatura governamental definitiva sem ressalvas:** `NÃO GO` ainda

## 5. O que falta para virar “100% pronto”

### 5.1 Itens obrigatórios

1. Preencher e revisar o contrato governo para o órgão real.
2. Confirmar todos os `sync: false` no painel Render.
3. Executar `python manage.py check --deploy` com ambiente real de produção.
4. Validar suporte e privacidade com teste real de envio e recebimento.
5. Evidenciar backup ativo, restauração e monitoramento.

### 5.2 Itens altamente recomendados

1. Registrar print ou log de smoke test completo em produção.
2. Fechar teste real do fluxo Asaas.
3. Consolidar um kit de contratação com contrato, anexos, SLA, política, termos e proposta.
4. Preparar um documento curto de implantação 30 dias para o órgão contratante.

## 6. Plano de fechamento em 1 dia

### Manhã

1. Abrir painel Render e conferir todos os secrets.
2. Rodar `check --deploy` com shell de produção.
3. Validar canais `suporte@` e `privacidade@`.

### Tarde

1. Preencher contrato do órgão.
2. Registrar evidência de backup/monitoramento.
3. Rodar smoke test final e salvar prova.

### Final do dia

Se os 5 itens obrigatórios estiverem concluídos, a classificação sobe para:

`100% PRONTO PARA CONTRATAÇÃO GOVERNAMENTAL`

## 7. Parecer final desta auditoria

A SolusCRT **não está “crua” nem “experimental”**. A plataforma já demonstra maturidade real de produto, arquitetura de produção, documentação jurídica e operação básica. O que falta agora é **last mile institucional**: evidência operacional, fechamento contratual do órgão e validação formal dos canais e controles externos.

Em linguagem objetiva:

- **produto:** pronto
- **produção pública:** funcional
- **jurídico base:** forte
- **assinatura governamental final hoje:** depende de fechamento operacional e documental
