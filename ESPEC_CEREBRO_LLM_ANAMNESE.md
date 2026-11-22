# Especificação — Cérebro LLM + Prior Epidemiológico Vivo (anamnese do app cidadão)

**Data:** 2026-11-20
**Projeto:** SolusCRT / app_saude
**Natureza:** documento de implantação. Nenhum código foi alterado ao escrever isto.
**Objetivo em uma frase:** dar ao app uma anamnese mais certeira usando um LLM poderoso (Claude) como camada de raciocínio, **fundamentado** no conhecimento médico e **calibrado pelo dado epidemiológico real do governo**, sem reescrever nem desconfigurar o que já existe — principalmente os painéis do gestor.

---

## 1. Princípios (inegociáveis)

1. **Aditivo, nunca substitutivo.** A camada nova entra por fora. O classificador atual, o `grupo`, a `classificacao`, o panorama e os contratos de API permanecem.
2. **Triagem, não diagnóstico.** O resultado continua sendo apoio, com o aviso legal atual. Isso tem peso regulatório (ver §8).
3. **Emergência é determinística.** As urgências (rigidez de nuca, falta de ar, manchas roxas) continuam em regra fixa. O LLM nunca decide se é emergência.
4. **Nunca travar o envio.** Se o Claude ou a internet falhar, cai no classificador atual. O registro sempre acontece.
5. **Sem chute, e rastreável.** O LLM conversa e interpreta; o motor calcula. Toda hipótese tem de ser explicável (quais sintomas, qual prior).
6. **Fundamentar, não "treinar".** O Claude já conhece as doenças. Não se re-treina o modelo; dá-se a ele os protocolos e o dado local para raciocinar em cima.
7. **Perfeito não é meta.** A meta é poderoso + fundamentado + calibrado ao local + seguro. Nenhum sistema do mundo (nem o AMIE do Google) é perfeito; os estudos põem a acurácia de triagem em ~49–90%.

---

## 2. Arquitetura — as 3 peças

### Peça A — O cérebro (LLM de raciocínio)
- Reusa a infra Claude já existente ([email_ai.py:492](api/email_ai.py:492), `anthropic==0.40.0`, `ANTHROPIC_API_KEY` em [backend/settings.py:55](backend/settings.py:55)).
- **Modelo forte** (`claude-sonnet-4-6` ou classe Opus) para o raciocínio clínico; **Haiku** (`claude-haiku-4-5`) só para extrair sintomas do texto. Divisão para equilibrar custo.
- Entrada: os sintomas/respostas que o app já coleta. Saída: hipótese + conduta + sintomas estruturados.
- **Anti-ancoragem:** a cada passo, o motor devolve o diferencial completo ao LLM, obrigando-o a integrar toda a evidência (corrige a falha documentada "LLM se ancora na queixa principal").
- **Papel exato:** enriquece `dados_classificacao` **antes** de `classificar_padrao` ([views.py:2325](api/views.py:2325)), e grava a hipótese num **campo novo** — sem tocar no shape de saída de `classificar()`.

### Peça B — O prior vivo
- Hoje o prior é uma tabela estática por UF ([classificador_doencas.py:974](api/classificador_doencas.py:974)), lida por `_prior_geografico` ([classificador_doencas.py:1057](api/classificador_doencas.py:1057)).
- O prior vivo mistura essa tabela com **o que circula de fato no bairro/cidade agora** — do panorama + das fontes oficiais que já são integradas (SINAN/InfoDengue, [pipeline_oficial.py](api/pipeline_oficial.py)) + da detecção de surto já treinada em dado do governo ([epidemiologia_ml.py](api/epidemiologia_ml.py)).
- **Regra crítica (evitar recursão):** o prior vivo vem de um **snapshot desacoplado**, gerado periodicamente pela fila RQ (`soluscrt-rqworker`), gravado numa tabela própria. Nunca ler o panorama ao vivo dentro do classificador — o panorama já usa o prior ([epidemiologia.py:770](api/epidemiologia.py:770)), e isso criaria realimentação.
- **Onde há pouco dado**, o prior vivo cai para a tabela de literatura. (Coerente com o design de foco a partir de um relato, que é intencional.)

### Peça C — O ciclo de aprendizado
- O modelo já tem `doenca_confirmada` ([classificador_doencas.py:1941](api/classificador_doencas.py:1941)) e `revisado`/`origem_dado`/`fonte_referencia` ([models.py:172](api/models.py:172)), hoje não preenchidos.
- Construir o canal de confirmação (UBS/agente diz "era dengue") que preenche `doenca_confirmada`.
- Com o tempo, esses desfechos recalibram os pesos — trocam peso de literatura por peso aprendido.
- **Verdade honesta:** o dado do governo (SINAN) dá **contagem por região** (ótimo para o prior), não pares "sintomas deste paciente → diagnóstico". O aprendizado por paciente depende deste ciclo, não do SINAN.

---

## 3. Regras de ouro (o que NÃO pode quebrar o gestor)

Os painéis do gestor ficam **a jusante**: leem o resultado gravado, não o processo. Protegidos desde que:

1. **Não mexer em `RegistroSintoma.grupo` nem `classificacao`** — os dashboards agregam por `grupo` ([dashboard_core.py:319](api/services/dashboard_core.py:319)). Pode-se **adicionar** campos (migração), nunca remover/renomear nem mudar o domínio de valores.
2. **Não mexer no shape de `classificar()`** ([classificador_doencas.py:1949](api/classificador_doencas.py:1949)): chaves `primario, score, grupo, cid10, confianca, ranking, red_flags, urgencia_absoluta, ...`.
3. **Não mexer no shape do panorama** `{generated_at, overview, layers:{bairros,municipios,estados}, filters}` nem nas chaves `surveillance_index`, `resource_pressure`, `government_briefing` ([epidemiologia.py:1493](api/epidemiologia.py:1493)).
4. **Não mexer no contrato de `/api/public/registrar`** (`status, grupo, classificacao, confianca, suspeito, local, cidadao`) nem dos endpoints `app_*` — o Flutter já os consome. O bloco `cidadao` pode ser **enriquecido** mantendo as chaves atuais.

---

## 4. Roteiro linear (fases)

### Fase 0 — Reparos de coleta (base para tudo)
Sem isso, o cérebro raciocina sobre dado furado.
- Separar as 4 comorbidades, hoje colapsadas num OR ([tela_sintomas.dart:332](app_saude/lib/telas/sintomas/tela_sintomas.dart:332)); novas colunas no modelo.
- Corrigir a pergunta das vesículas, que descreve varicela ([tela_sintomas.dart:166](app_saude/lib/telas/sintomas/tela_sintomas.dart:166)).
- Começar a preencher `origem_dado` e `fonte_referencia` no registro público ([views.py:2375](api/views.py:2375)).
- **Risco de quebra:** nulo para o gestor (só adiciona dado). Esforço: baixo.

### Fase 1 — O cérebro (texto), aditivo
- Novo serviço `anamnese_ia` (um wrapper central Claude — que hoje não existe; cada view instancia o seu).
- No `registrar_sintoma_publico`: o classificador atual responde na hora (como hoje); o cérebro refina **em segundo plano** pela fila RQ, ou inline com timeout curto + fallback.
- Grava a hipótese do LLM num campo novo (`hipotese_ia`), **sem** tocar em `grupo`/`classificacao`.
- **Risco de quebra:** baixo; o fluxo síncrono atual continua intacto. Esforço: médio.

### Fase 2 — O prior vivo
- Comando/job RQ que gera o snapshot de prevalência local por (bairro/cidade/UF) a partir do panorama + fontes oficiais, numa tabela nova.
- `_prior_geografico` passa a mesclar tabela estática + snapshot. Fallback para a tabela quando não há dado.
- **Risco de quebra:** médio — mexe no prior, que afeta a gravação e a agregação. Mitigar com snapshot desacoplado e testes de regressão do panorama. Esforço: médio.

### Fase 3 — Fundamentação ampla (cobertura "de todas as doenças")
- Ampliar a lista estruturada de doenças e dar ao Claude os **protocolos do Ministério da Saúde** (RAG) para raciocinar sobre elas.
- Incluir no panorama as doenças hoje de fora (ex.: Mpox), respeitando as regras de ouro.
- **Risco de quebra:** baixo-médio. Esforço: médio-alto (curadoria clínica).

### Fase 4 — Ciclo de aprendizado
- Canal de confirmação de desfecho (`doenca_confirmada`) via UBS/agente.
- Recalibração periódica dos pesos a partir dos desfechos.
- **Risco de quebra:** baixo. Esforço: alto (processo + produto).

### Fase 5 — Voz (opcional, por cima)
- Whisper no aparelho (offline, LGPD) ou no VPS; `flutter_tts` para a resposta.
- A voz é só entrada/saída; não muda o cérebro. **Read-back** obrigatório ("entendi X, certo?").
- **Risco de quebra:** nulo para o backend. Esforço: alto.

---

## 5. Modelo, custo e desempenho
- Raciocínio: modelo forte. Extração: Haiku. Fallback: classificador atual.
- Chamada do cérebro **não** bloqueia o registro (fila RQ ou timeout curto).
- Tratamento de indisponibilidade/billing já existe como padrão ([email_ai.py:528](api/email_ai.py:528)) — reaproveitar.

## 6. Segurança e regulação
- **ANVISA:** uma anamnese que entrega hipótese de doença provavelmente é Software como Dispositivo Médico (RDC 657/2022, 751/2022) — exige documentar técnica de IA e dados. Manter o enquadramento de triagem/apoio reduz risco, mas não elimina.
- **CFM:** o dever do diagnóstico é do profissional; o software estrutura. Manter o aviso legal atual.
- **LGPD:** se entrar voz, transcrever e **descartar o áudio**, guardar só o dado estruturado, com consentimento.
- **Supervisão médica** no desenho do roteiro clínico do LLM (não prescrever, não nomear doença rara ao cidadão, parar em emergência).

## 7. Verdades honestas (o que isto NÃO resolve)
- **Perfeito não existe.** Meta: poderoso, fundamentado, local, seguro.
- **O LLM não é treinado nas suas doenças** — é fundamentado. O ganho de "aprender com os seus pacientes" depende da Fase 4 (desfecho confirmado), não do SINAN.
- **O prior vivo só é bom onde há dado.** Bairro vazio = prior de literatura.
- **O dado do governo** serve ao prior e à detecção de surto, não ao treino sintoma-a-sintoma.

## 8. A confirmar antes de codar
- A rota do segundo fluxo que também chama o classificador ([views.py:2184](api/views.py:2184)) — a camada precisa cobrir os dois.
- Os parsers Dart do Flutter, para garantir que o bloco `cidadao` enriquecido não quebre a tela de resultado.

---

## 8.1 Estado das fases — 21/11/2026

| Fase | Estado | Evidência |
|---|---|---|
| 0 — contexto granular | **pronta** | 4 comorbidades separadas; pergunta das vesículas corrigida; `origem_dado` e `fonte_referencia` preenchidos no envio público (`app_saude <versão>`) |
| 1 — cérebro LLM | **pronta** | `anamnese_ia` rodando no worker; 6 registros com hipótese em produção |
| 2 — prior vivo | **pronta** | 240 fatores em 17 doenças, cron mensal; comparação sazonal contra as mesmas semanas do ano anterior |
| 3 — fundamentação ampla | **mecanismo pronto, conteúdo pendente** | catálogo 26→30; panorama alcança as 30 pelo diferencial gravado (100% dos 2.167 registros); `api/protocolos_ms.py` injeta o critério oficial do MS no prompt para as 3 hipóteses do topo. **3 de 30 doenças com fonte verificada** — o Guia de Vigilância não abriu em nenhuma das 4 tentativas; o resto se transcreve na revisão clínica |
| 4 — ciclo de aprendizado | **pronta** | `POST /api/registro/desfecho` grava `doenca_confirmada`; `GET /api/classificador/calibracao` devolve acurácia. Antes: 0 de 2.167 registros tinham desfecho e a calibração devolvia `sem_dados` para sempre |
| 5 — voz | não iniciada | marcada como opcional na própria especificação |

**O que a Fase 4 destrava:** era a única fase capaz de responder se o sistema
acerta na vida real. Sem desfecho confirmado, tudo o que se pode afirmar é que
ele faz o que foi projetado para fazer — nunca que acerta o diagnóstico.

**Pendência fora do código:** revisão clínica das 27 perguntas de desempate por
profissional habilitado. Documento pronto em `REVISAO_CLINICA_PERGUNTAS.md`.

## 9. Resumo de uma linha
Cérebro LLM forte, **fundamentado** em todas as doenças que ele já conhece + protocolos do MS, **calibrado pelo prior vivo** do dado oficial e do seu mapa, com ciclo de aprendizado próprio — tudo **aditivo**, com o gestor intacto porque ele lê o resultado, não o processo.
