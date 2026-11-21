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

## Ordem sugerida

1. Vesículas (fecha varicela × Mpox, o caso que originou tudo)
2. Manchas e tosse (maior cobertura: 13 doenças)
3. Icterícia e diarreia
4. O resto

Começar por um comprova o mecanismo antes de escrever 28 perguntas.
