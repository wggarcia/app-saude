# Revisão clínica — perguntas de desempate do SoloCRT

**Gerado em:** 21/11/2026, a partir do código em produção.

## Para quem revisa

O conteúdo clínico abaixo **foi redigido por IA a partir de literatura, não por profissional
habilitado**. Está implementado e testado tecnicamente, mas não deve orientar notificação ou
conduta antes desta revisão.

O sistema **não dá diagnóstico**. Ele ordena hipóteses para vigilância epidemiológica a partir
de sintomas autorrelatados por cidadãos num aplicativo, e o resultado é lido por gestores de
saúde, não por pacientes. Cada pergunta só aparece para quem respondeu "Sim" à pergunta-porta
dela — ninguém responde todas.

**O que se pede, em cada linha:**

1. A pergunta é compreensível para leigo e capta o achado pretendido?
2. O achado aponta mesmo para a doença indicada?
3. O valor é razoável? **Escala:** `0,75` = achado forte, assume a frente · `0,45` = move a
   agulha · `0,05` = praticamente afasta. São priores, depois multiplicados pelo escore de
   sintomas — não são a chance de a pessoa ter a doença.
4. Falta alguma pergunta que mudaria o diferencial?

**Anote ao lado:** OK · AJUSTAR (dizendo o quê) · REMOVER.

**Importante:** "Não" é diferente de "não perguntado". Quem não abre a porta não responde, e o
campo fica nulo — nunca é lido como negativa.

---

## Porta: Febre

*Só aparece para quem respondeu "Sim" em: **Você tem ou teve febre?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| A febre vem em ciclos — calafrio forte, depois febre, depois suor? | Episódios que se repetem com hora quase marcada, com melhora entre eles | Malária — 0,45; 0,60 com viagem a área endêmica | Malária cai a 0,08 |  |
| A febre baixou e voltou depois de um ou dois dias? *(também na porta Icterícia)* | Chegou a melhorar e então piorou de novo | Dengue 0,55 · Febre Amarela 0,50 | Febre Amarela cai a 0,15 |  |
| Tem íngua — caroço no pescoço, axila ou virilha? *(também na porta Bolhinhas com líquido)* | Caroço que dói ao apertar, do tamanho de um grão de feijão ou maior | Mpox (com bolhinhas) · Peste 0,10, ou 0,35 com contato com roedor (com febre, sem bolhinhas) | sem íngua, Peste cai a 0,0005 |  |

## Porta: Tosse

*Só aparece para quem respondeu "Sim" em: **Tem tosse?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| Está tossindo há mais de 3 semanas? | Conte desde o primeiro dia de tosse, mesmo que tenha melhorado no meio | Tuberculose 0,40; 0,55 com suor noturno | Tuberculose cai a 0,08; se SIM, Gripe/Resfriado/COVID caem a 0,20 |  |
| A tosse vem em acessos seguidos, com guincho ou vômito no fim? | Crises em que não consegue respirar entre uma tosse e outra | Coqueluche 0,60 | Coqueluche cai a 0,08 |  |
| Tem suor à noite que chega a molhar a roupa? *(também na porta Emagrecimento)* | Suor durante o sono, a ponto de precisar trocar de roupa ou lençol | Tuberculose 0,50 (e reforça a tosse crônica) | Tuberculose cai a 0,20 |  |

## Porta: Falta de ar

*Só aparece para quem respondeu "Sim" em: **Tem falta de ar?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| A falta de ar começou de repente, poucos dias depois da febre? | De uma hora para outra, e não aos poucos | Hantavirose 0,35; 0,50 com contato com roedor | Hantavirose cai a 0,05 |  |
| A falta de ar piora quando você deita? | Precisa de travesseiro alto ou de sentar para respirar melhor | Bronquite / DPOC 0,45 | — |  |

## Porta: Dor articular

*Só aparece para quem respondeu "Sim" em: **Tem dor nas articulações?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| A dor pega os dois lados ao mesmo tempo — as duas mãos, os dois pés? | Mesmas juntas dos dois lados do corpo | Chikungunya — 0,50 sozinha, 0,70 com a seguinte | com as duas negadas, Chikungunya cai a 0,15 |  |
| A dor nas juntas já dura mais de 2 semanas? | Mesmo que tenha melhorado e voltado | Chikungunya — idem | com as duas SIM, Dengue e Zika caem a 0,25 |  |

## Porta: Manchas na pele

*Só aparece para quem respondeu "Sim" em: **Surgiram manchas ou vermelhidão na pele?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| As manchas começaram no rosto e foram descendo pelo corpo? | Primeiro rosto e pescoço, depois tronco, depois pernas | Sarampo 0,55; 0,65 com olho vermelho | Sarampo cai a 0,12 |  |
| As manchas coçam muito? | Coceira forte, a ponto de atrapalhar o sono | Zika 0,55 | Zika cai a 0,20 |  |
| Tem manchas nas palmas das mãos ou nas plantas dos pés? | Olhe as duas mãos e os dois pés antes de responder | Febre Maculosa 0,60 | Febre Maculosa cai a 0,10 |  |
| As manchas apareceram quando a febre baixou? | Primeiro a febre passou, depois surgiram as manchas | Dengue 0,60 · Chikungunya 0,35 | Dengue cai a 0,20 |  |

## Porta: Diarreia

*Só aparece para quem respondeu "Sim" em: **Tem diarreia?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| As fezes estão muito aquosas, parecendo água de arroz? | Líquidas e esbranquiçadas, quase sem resíduo | Cólera 0,55 (0,30 se houver febre ou sangue) | Cólera cai a 0,001; se SIM, Gastroenterite cai a 0,30 |  |
| As fezes têm sangue ou muco? | Sangue vivo, fezes escuras como piche, ou catarro nas fezes | Esquistossomose 0,45 | — |  |
| Está com febre alta contínua há mais de uma semana? | Febre que quase não baixa, todos os dias | Febre Tifoide 0,55 | Tifoide cai a 0,10; se SIM, Dengue/Chik/Zika caem a 0,20 |  |

## Porta: Icterícia

*Só aparece para quem respondeu "Sim" em: **A pele ou os olhos ficaram amarelados?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| A urina está escura e as fezes claras? | Urina cor de Coca-Cola, fezes esbranquiçadas como massa de vidraceiro | Hepatite A/B 0,60 | Hepatite cai a 0,20 |  |
| Sente dor forte na batata da perna? | Dor na panturrilha que piora ao apertar | Leptospirose 0,55; 0,65 com enchente | Leptospirose cai a 0,20 |  |
| A febre baixou e voltou depois de um ou dois dias? *(também na porta Febre)* | Chegou a melhorar e então piorou de novo | Dengue 0,55 · Febre Amarela 0,50 | Febre Amarela cai a 0,15 |  |

## Porta: Bolhinhas com líquido

*Só aparece para quem respondeu "Sim" em: **As manchas na pele têm bolhinhas com líquido?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| As bolhinhas doem mais do que coçam? | Pense no que incomoda mais: a dor ou a coceira | Mpox — 0,45 com 1 achado, 0,75 com 2 ou mais | 2 negados → Mpox cai a 0,05 |  |
| Tem íngua — caroço no pescoço, axila ou virilha? *(também na porta Febre)* | Caroço que dói ao apertar, do tamanho de um grão de feijão ou maior | Mpox (com bolhinhas) · Peste 0,10, ou 0,35 com contato com roedor (com febre, sem bolhinhas) | sem íngua, Peste cai a 0,0005 |  |
| Começou no rosto, ou apareceu nas palmas das mãos ou plantas dos pés? | Onde surgiram as primeiras bolhinhas | Mpox — idem | — |  |
| Há bolhinhas novas e feridas já com casquinha ao mesmo tempo? | Umas acabando de surgir enquanto outras já secaram | Varicela 0,85 | — |  |

## Porta: Emagrecimento

*Só aparece para quem respondeu "Sim" em: **Emagreceu sem dieta ou motivo aparente?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| A barriga está inchada, ou sente um volume do lado esquerdo? | Barriga crescendo sem ganhar peso, ou peso embaixo das costelas à esquerda | Leishmaniose Visceral 0,60 | LV cai a 0,20 |  |
| Tem suor à noite que chega a molhar a roupa? *(também na porta Tosse)* | Suor durante o sono, a ponto de precisar trocar de roupa ou lençol | Tuberculose 0,50 (e reforça a tosse crônica) | Tuberculose cai a 0,20 |  |

## Porta: Úlcera de pele

*Só aparece para quem respondeu "Sim" em: **Tem uma ferida ou úlcera na pele que não cicatriza?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| A ferida é indolor e tem as bordas elevadas? | Não dói ao tocar, e a borda é mais alta que o fundo | L. Tegumentar 0,75; 0,80 se aberta há +1 mês | com as duas negadas, cai a 0,20 |  |
| A ferida está aberta há mais de um mês? | Sem cicatrizar, mesmo com pomada ou curativo | L. Tegumentar 0,70 | — |  |

## Porta: Dor de garganta

*Só aparece para quem respondeu "Sim" em: **Tem dor de garganta?***

| Pergunta ao cidadão | Dica na tela | Se SIM | Se NÃO | Revisão |
|---|---|---|---|---|
| Tem placa branca ou acinzentada na garganta? | Uma casca grudada na garganta ou nas amígdalas, difícil de soltar | Difteria — 0,45 sozinha, 0,70 com pescoço inchado | Difteria cai a 0,001; se SIM, Resfriado/Gripe caem a 0,25 |  |
| O pescoço está inchado dos dois lados? | Pescoço visivelmente mais grosso, não só um caroço | Difteria — idem | — |  |

---

**Total: 30 perguntas de desempate, em 11 portas.** Mais 1 pergunta de exposição feita a todos (mordedura de animal).

## Pontos que eu já sei que merecem atenção

1. **Cólera, Difteria, Peste e Raiva Humana** entraram no catálogo com prior quase nulo
   (0,002 / 0,002 / 0,001 / 0,0005), para que a clínica as levante e não o acaso. Os priores
   e os achados que as levantam estão corretos?
2. **"Fezes como água de arroz"** é o único discriminador de cólera. Basta?
3. **Raiva Humana** não pergunta hidrofobia, aerofobia nem agitação — o formulário não coleta
   esses sinais. Depende só do antecedente de mordedura.
4. **Febre que baixou e voltou** serve a dengue e febre amarela, e aparece na porta da febre e
   na da icterícia. Está bem alocada?
5. **Suor noturno** vale para tuberculose nas duas portas em que aparece. Deveria pesar igual?
6. A **intensidade da febre e da dor articular** é coletada mas não discrimina doença. Vale
   transformar em discriminador?
7. **Peste** usa a mesma pergunta de íngua da Mpox, separada só por haver ou não bolhinhas.
   Essa separação é suficiente?

---

## Parte 2 — Definições de caso do Ministério da Saúde

Esta parte é a Fase 3 da especificação: dar ao modelo o **critério oficial**, e
não só conhecimento geral. Vigilância não funciona com conhecimento geral —
funciona com a definição de caso, que é o que determina se há notificação, em
que prazo, e o que a equipe faz em seguida.

Tentei obter isso sozinho em quatro caminhos: as páginas por doença do gov.br,
a central de publicações da SVSA, o Guia de Vigilância em Saúde no bvsms, e a
Portaria GM/MS nº 10.175/2026 no Diário Oficial. Só as páginas por doença
abriram, e quase nenhuma traz definição de caso. O Guia — que é a fonte real —
deu 404, e o Diário Oficial derrubou a conexão.

**O mecanismo está pronto** (`api/protocolos_ms.py`): o que estiver preenchido
aqui entra no raciocínio do modelo, só para as 3 hipóteses do topo de cada
caso. O que ficar em branco simplesmente não entra — nada é inventado.

**O que se pede:** transcrever do Guia de Vigilância em Saúde. Transcrever, não
resumir: é o texto oficial que dá autoridade à linha.

### Já preenchido (conferir)

| Doença | Definição de caso suspeito | Notificação | Fonte | Confere? |
|---|---|---|---|---|
| Mpox | Indivíduo de qualquer idade que apresente início súbito de lesão em mucosas e/ou erupção cutânea aguda sugestiva de mpox **[transcrição parcial — completar]** | imediata | https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/m/mpox/definicao-de-caso |  |
| Hantavirose | — em branco — | imediata | https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/h/hantavirose |  |
| Febre Maculosa | — em branco — | — não informado na fonte — | https://www.gov.br/saude/pt-br/assuntos/saude-de-a-a-z/f/febre-maculosa |  |

### A transcrever

| Doença | Definição de caso suspeito | Notificação (imediata/semanal) |
|---|---|---|
| Sarampo |  |  |
| Difteria |  |  |
| Coqueluche |  |  |
| Cólera |  |  |
| Peste |  |  |
| Raiva Humana |  |  |
| Febre Amarela |  |  |
| Malaria |  |  |
| Leptospirose |  |  |
| Febre Tifoide |  |  |
| Meningite |  |  |
| Tuberculose |  |  |
| Hanseníase |  |  |
| Leishmaniose Visceral |  |  |
| Leishmaniose Tegumentar |  |  |
| Doença de Chagas |  |  |
| Esquistossomose |  |  |
| Varicela |  |  |
| Dengue |  |  |
| Chikungunya |  |  |
| Zika |  |  |
| Hepatite A/B |  |  |

---

## Assinatura

Nome: ______________________________   CRM: ______________

Data: ____/____/______   Assinatura: ______________________________
