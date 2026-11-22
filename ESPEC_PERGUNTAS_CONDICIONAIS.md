# Especificação — Perguntas condicionais de desempate (todas as doenças)

**Data:** 2026-11-21
**Origem:** o LLM respondeu "confiança moderada porque a linfadenopatia não foi mencionada". Ele identificou a pergunta que resolveria o caso e não pôde fazê-la.
**Princípio:** o formulário fica mais **fundo**, não mais **longo**. Cada pessoa só vê as perguntas que a resposta dela abriu.

> ⚠️ **Este documento precisa de revisão por médico antes de virar código.** O conteúdo clínico abaixo foi redigido por IA a partir de literatura, não por profissional habilitado.

---

## O problema que isto resolve

Hoje são 38 perguntas iguais para todo mundo, e elas não separam doenças parecidas. Adicionar perguntas fixas não escala: são 26 doenças, e cada par confundível precisa dos seus discriminadores — daria mais de cem perguntas, que ninguém responde.

O mecanismo certo **já existe no app**: febre e dor articular abrem follow-up de intensidade. Falta aplicá-lo onde ele decide o diagnóstico.

## Como funciona

Um sintoma-porta respondido **"Sim"** abre 2 a 4 perguntas específicas. Quem não tem o sintoma nunca vê essas perguntas. Na prática, cada pessoa responde de 3 a 8 extras — não 28.

---

## O mapa completo

### 1. Bolhinhas com líquido (`exantema_vesicular`) → Varicela vs Mpox
| Pergunta | Aponta para |
|---|---|
| A lesão **dói mais do que coça**? | Mpox |
| Tem **íngua** (caroço no pescoço, axila ou virilha)? | Mpox |
| Começou **no rosto**, ou pegou **palmas e plantas**? | Mpox |
| As bolhinhas estão **em fases diferentes** ao mesmo tempo? | Varicela |

### 2. Manchas na pele (`exantema`) → Sarampo, Zika, Dengue, Febre Maculosa, Chikungunya
| Pergunta | Aponta para |
|---|---|
| Começou **no rosto e desceu** pelo corpo? | Sarampo |
| **Coça muito**? | Zika |
| Tem manchas nas **palmas ou plantas**? | Febre Maculosa |
| Apareceu **quando a febre baixou**? | Dengue |
| Veio com **olhos vermelhos**? (já coletado) | Zika / Sarampo |

### 3. Tosse → Tuberculose, Coqueluche, Gripe, COVID, Bronquite, Resfriado, Sarampo
| Pergunta | Aponta para |
|---|---|
| Está tossindo há **mais de 3 semanas**? | Tuberculose |
| A tosse vem em **acessos**, com guincho ou vômito no fim? | Coqueluche |
| Tem **suor à noite** que molha a roupa? | Tuberculose |

### 4. Icterícia (pele/olhos amarelos) → Hepatite, Leptospirose, Febre Amarela
| Pergunta | Aponta para |
|---|---|
| **Urina escura** e **fezes claras**? | Hepatite |
| **Dor forte na panturrilha**? | Leptospirose |
| A febre **melhorou e voltou pior**? | Febre Amarela |

### 5. Diarreia → Gastroenterite, Cólera, Febre Tifoide, Esquistossomose
| Pergunta | Aponta para |
|---|---|
| Fezes **muito aquosas, parecendo água de arroz**? | Cólera |
| Com **sangue ou muco**? | Esquistossomose / disenteria |
| **Febre alta contínua** há mais de uma semana? | Febre Tifoide |

### 6. Dor nas articulações → Chikungunya, Dengue, Zika
*(já abre intensidade; acrescentar)*
| Pergunta | Aponta para |
|---|---|
| **Impede de andar** ou de segurar objetos? | Chikungunya |
| Dói nos **dois lados ao mesmo tempo** (mãos, pés)? | Chikungunya |
| Já dura **mais de 2 semanas**? | Chikungunya crônica |

### 7. Falta de ar → Hantavirose, COVID, Bronquite, Coqueluche
| Pergunta | Aponta para |
|---|---|
| Começou **de repente**, poucos dias depois da febre? | Hantavirose |
| **Piora ao deitar**? | Bronquite / cardíaco |

### 8. Perda de peso → Tuberculose, Chagas, Leishmaniose Visceral
| Pergunta | Aponta para |
|---|---|
| **Barriga inchada** ou sensação de volume do lado esquerdo? | Leishmaniose Visceral |
| **Suor à noite**? | Tuberculose |

### 9. Úlcera na pele → Leishmaniose Tegumentar
| Pergunta | Aponta para |
|---|---|
| A ferida é **indolor**, com **bordas elevadas**? | Leishmaniose Tegumentar |
| Está aberta há **mais de um mês**? | Leishmaniose Tegumentar |

### 10. Febre → Malária, Dengue, Febre Amarela
*(já abre intensidade; acrescentar)*
| Pergunta | Aponta para |
|---|---|
| Vem **em ciclos**, com calafrio forte e depois suor? | Malária |
| **Baixou e voltou** depois de um ou dois dias? | Dengue / Febre Amarela |

---

## O que muda no sistema

1. **App:** a estrutura de follow-up já existe (`followup` em `_PerguntaSintoma`). Precisa aceitar follow-ups por sintoma, não só intensidade.
2. **Modelo:** campos booleanos novos, nuláveis — null significa "não foi perguntado", que é diferente de "não".
3. **Classificador:** usar os novos campos como discriminadores. **Aqui está o ganho real** — hoje o prior decide; com estes campos, a evidência decide.
4. **LLM:** passa a receber respostas específicas em vez de reclamar do que falta.

## O que NÃO fazer

- **Não transformar em peso alto automático.** "Tem íngua" não é Mpox; é um dado a favor. Os pesos entram com a mesma disciplina do resto.
- **Não perguntar o que não discrimina.** Cada pergunta acima separa candidatos. Pergunta que não separa é só atrito.
- **Não deixar obrigatória.** "Não sei" tem que ser resposta válida — e `null` ≠ `False`.

## Estado da implementação — 21/11/2026

As **10 portas estão implementadas**. 25 perguntas condicionais, 25 campos
nuláveis no modelo, discriminadores ligados no classificador e rótulos
entregues ao LLM.

| Porta | Perguntas | Doenças que separa | Verificado |
|---|---|---|---|
| Vesículas | 4 | Varicela × Mpox | ✅ |
| Manchas | 4 | Sarampo, Zika, Dengue, Febre Maculosa, Chikungunya | ✅ |
| Tosse | 2 (+suor noturno) | Tuberculose, Coqueluche, agudas | ✅ |
| Icterícia | 3 | Hepatite, Leptospirose, Febre Amarela | ✅ |
| Diarreia | 3 | Febre Tifoide, Esquistossomose, Gastroenterite | ⚠️ ver Cólera |
| Dor articular | 2 | Chikungunya × Dengue × Zika | ✅ |
| Falta de ar | 2 | Hantavirose, Bronquite/DPOC | ✅ |
| Perda de peso | 2 | Leishmaniose Visceral × Tuberculose | ✅ |
| Úlcera | 2 | Leishmaniose Tegumentar | ✅ |
| Febre | 2 | Malária, Dengue, Febre Amarela | ✅ |

Duas perguntas servem a duas portas cada — suor noturno (tosse e perda de
peso) e febre que baixou e voltou (febre e icterícia). Por isso `condicionalDe`
virou `condicionaisDe`, uma lista.

**Teste:** 13 de 14 casos-sonda mudam para a doença esperada, e 600 casos
aleatórios sem respostas de desempate dão resultado idêntico ao de antes — ou
seja, app antigo não muda de comportamento (`null` continua sendo "não
perguntado").

### Catálogo ampliado — 21/11/2026

Três doenças foram acrescentadas ao `DOENCAS_BRASIL`, que foi de 26 para **29**:
**Cólera** (A00), **Difteria** (A36.0) e **Peste** (A20.0).

Não são doenças novas no sistema. As três já tinham série oficial do SINAN
importada, prior vivo calculado, opção de notificação para o gestor e nome na
`DOENCAS_SENTINELA` do `anamnese_ia` — a lista do "isto não pode passar
batido". Faltava só a entrada no catálogo, e sem ela nem o motor bayesiano
podia rankeá-las nem o LLM podia nomeá-las, porque o prompt o prende à mesma
lista. O portão de relevância clínica procurava por elas em todo envio e nunca
as encontraria.

Prior deliberadamente quase nulo (0,002 / 0,002 / 0,001): são raras, e é a
evidência que deve levantá-las. Em 600 casos aleatórios sem respostas de
desempate, nenhuma das três aparece como hipótese principal e **nenhum**
resultado mudou em relação a antes.

Duas perguntas novas, na porta da dor de garganta, para a difteria ser
detectável: placa aderente e pescoço inchado. E a pergunta da íngua passou a
ter duas portas — com bolhinhas separa Mpox de varicela; com febre e sem
bolhinhas é o bubão da peste.

**Total: 52 perguntas de sintoma — 25 fixas e 27 condicionais, em 11 portas.**

### ⚠️ Raiva Humana continua inalcançável

É a quarta sentinela, e ficou de fora de propósito. Para ser detectável
precisaria de uma pergunta de exposição que não existe — mordedura ou
arranhadura de animal — e de sinais que o formulário não coleta (hidrofobia,
aerofobia, agitação). Acrescentá-la sem isso criaria no catálogo o mesmo
problema que a cólera tinha nas perguntas: um nome sem caminho até ele.

Soma-se que a raiva humana se manifesta num estágio em que ninguém está
respondendo formulário no celular. **Decisão pendente:** ou entra com pergunta
de exposição própria, ou sai da `DOENCAS_SENTINELA`, onde hoje é código morto.
