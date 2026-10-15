# Assinatura digital ICP-Brasil — como funciona e quem compra o quê

> **Duas correções importantes.**
>
> 1. Uma versão anterior mandava a SoloCRT comprar um certificado e configurá-lo
>    numa variável de ambiente global. Errado em dois níveis: o escopo (um
>    certificado para a instalação inteira, num produto multi-tenant) e o dono
>    (a empresa em vez do profissional).
> 2. Outra versão afirmava que a SoloCRT precisaria se inscrever num CRM e
>    nomear um Diretor Técnico médico. **Também errado.** Esse dever é do
>    ESTABELECIMENTO DE SAÚDE que usa o sistema. Pela Lei 6.839/80 o registro em
>    conselho segue a **atividade básica** da empresa, e desenvolver software não
>    é atividade médica — o CFM inscreve prestadores e intermediadores de
>    assistência à saúde. Quem fornece a ferramenta não é nenhum dos dois.
>
> O desenho atual é o descrito abaixo.

## Quem assina, afinal

Prescrição é **ato médico**. Quem assina é o **médico, pessoa física**, com
certificado vinculado ao CPF e ao CRM dele.

- **Não é a SoluSCRT.** A empresa que fornece o software não assina ato médico.
- **Não é o hospital.** O hospital pode ter e-CNPJ, mas e-CNPJ não assina
  prescrição.
- **É cada médico.** Um hospital com 40 oncologistas tem 40 configurações.

Consequência prática: **a SoluSCRT não compra certificado nenhum** e não deveria
guardar chave privada de médico algum.

## Os quatro caminhos suportados

| Provedor | Onde fica a chave privada | Quando usar |
|---|---|---|
| **VIDaaS** | Cofre do provedor | **Recomendado.** Certificado em nuvem da CFM, vinculado ao registro no CRM. Muitos médicos já têm. |
| **BirdID** | Cofre do provedor | Alternativa em nuvem, também usada por sistemas clínicos do mercado. |
| **API do hospital** | No hospital | Cliente que **já tem** serviço de assinatura próprio. É o caminho de migração. |
| **A1 em arquivo** | No servidor | Só instalação dedicada. Evitar em SaaS. |

### Por que nuvem é o padrão

No certificado em nuvem a chave nunca sai do cofre do provedor credenciado: o
médico autoriza cada assinatura pelo celular. O sistema só manda o resumo do
documento e recebe a assinatura de volta.

Se guardássemos o arquivo A1 e a senha de dezenas de médicos no servidor, quem
tivesse acesso ao banco poderia assinar como qualquer um deles — **inclusive
documentos que não têm nada a ver com o hospital**. É um passivo que não vale a
pena correr.

## Caminho de migração: hospital que já assina

Este é o ponto que permite trazer cliente sem obrigá-lo a trocar de fornecedor
de certificado. O hospital cadastra o provedor `api_hospital` com a URL do
serviço dele, e o nosso sistema passa a delegar a assinatura.

**Contrato esperado** — `POST` na URL informada, com `Authorization: Bearer <token>`:

```json
{
  "hash": "a3f1…",
  "algoritmo": "SHA-256",
  "tipo_documento": "prescricao_quimio",
  "profissional": {"nome": "Dra. Helena Duarte", "cpf": "…", "registro": "CRM-MS 12345"}
}
```

Resposta esperada:

```json
{
  "assinatura_b64": "MIIF…",
  "certificado": {
    "titular": "HELENA DUARTE",
    "cpf_cnpj": "…",
    "emissor": "AC …",
    "numero_serie": "1a2b3c",
    "valido_de": "2026-01-01T00:00:00-03:00",
    "valido_ate": "2027-01-01T00:00:00-03:00"
  },
  "carimbo_tempo_em": null
}
```

Regras que o sistema aplica sozinho:

- a URL **tem de ser HTTPS** (resumo clínico e token não trafegam em claro);
- resposta sem `assinatura_b64` **não marca nada como assinado**;
- o token fica **cifrado em repouso** e nunca volta numa resposta da API;
- tempo limite de 20 s — assinar é síncrono na beira do leito, melhor falhar
  rápido e explicar do que pendurar a tela.

## Como cada cliente configura

Pela tela do hospital, em Certificados de Assinantes, ou pela API:

```bash
POST /api/hospital/oncologia/certificados/
```

```json
{
  "profissional_nome": "Dra. Helena Duarte",
  "profissional_cpf": "00000000000",
  "profissional_registro": "CRM-MS 12345",
  "provedor": "vidaas",
  "identificador_provedor": "00000000000",
  "cliente_id": "…",
  "cliente_secreto": "…"
}
```

A configuração **só fica `ativo` se realmente der para assinar**. Incompleta,
nasce `pendente` e o campo `pendencias` diz exatamente o que falta — para
ninguém descobrir na frente do paciente que a assinatura não funciona.

Remover um assinante **desativa** em vez de apagar: as assinaturas já feitas
apontam para a configuração e precisam continuar auditáveis.

## A regra que o sistema nunca quebra

**Sem certificado utilizável, nada é marcado como assinado.** A tentativa vira
`falha` registrada, a API devolve HTTP 503 com a lista do que falta, e a tela diz
"não configurada". Um sistema que finge assinar é pior que um sem assinatura,
porque a mentira teria valor jurídico.

## Integridade: a parte que já funciona sem certificado algum

A prescrição tem um **conteúdo canônico** (paciente, diagnóstico, protocolo,
ciclo, superfície corporal, cada dose e a pré-medicação) e um **resumo SHA-256**
gravado junto da assinatura. Se alguém alterar uma dose depois, o resumo
recalculado não confere, a assinatura passa a `invalidada` e a tela avisa.

Isso vale hoje, em qualquer cliente, mesmo sem nenhum certificado configurado.

## O que falta mesmo com certificado

**Carimbo de tempo.** A data registrada é a do nosso servidor. Para a data ter fé
pública perante terceiros é preciso uma **Autoridade de Carimbo do Tempo (ACT)**
credenciada. O sistema marca essa diferença: `data_com_fe_publica` vem `false` e
a tela diz "sem carimbo de tempo de autoridade externa".

Sem ACT a assinatura continua válida — o que não se prova perante terceiros é
*quando* ela foi feita.

## Quem cumpre o quê (Resolução CFM 2.299/2021)

| Dever | De quem é | Onde fica no sistema |
|---|---|---|
| Art. 2º — documento com nome, CRM, endereço e RQE do médico; paciente com documento legal; **data e hora** | Médico, com os dados que o sistema estampa | `CertificadoAssinante` + `ResponsabilidadeTecnica`; entram no conteúdo assinado |
| Art. 4º — assinatura ICP-Brasil **NGS2**, validável pelo ITI ou pelo CFM | Médico (certificado é dele) | Aba Assinatura Digital, por profissional |
| Art. 5º — inscrição no CRM da sede + **Diretor Técnico médico** | **Estabelecimento de saúde** (o hospital cliente) | Painel de conformidade: `ResponsabilidadeTecnica` |
| Art. 8º — garantir que o prescritor é médico regular, pelo Cadastro Nacional de Médicos | Estabelecimento, com apoio do sistema | `CFM_WS_USUARIO`/`CFM_WS_SENHA` — web service **tarifado** (Res. CFM 2.129/2015) |

**O que a SoloCRT não precisa fazer:** inscrever-se em CRM, nomear diretor
técnico médico ou comprar certificado. Nada disso recai sobre quem fornece o
software. O que recai é **estruturar o produto para o cliente conseguir
cumprir** — que é o que o painel de conformidade faz: diz ao hospital, item a
item, o que falta.

## O que o módulo de oncologia exige, na prática

A prescrição de quimioterapia de **paciente internado** não é Notificação de
Receita: a Portaria 344/98 dispensa a Notificação para internados, e a
dispensação se faz com receita privativa do estabelecimento. Some-se que
doxorrubicina, carboplatina e paclitaxel não estão nas listas da 344/98.

**Mas há exceções dentro da própria oncologia**, e elas estão no módulo de
quimioterapia oral: **talidomida** (lista C3) e **tretinoína/ATRA** (lista C2)
são controladas e vão para casa com o paciente. Opioides para dor oncológica
também. Para esses, vale a RDC 1.000/2025 por inteiro — inclusive a integração
com o SNCR.

## RDC 1.000/2025 e o SNCR — prazos

| Data | O que muda |
|---|---|
| 15/02/2026 | RDC 1.000/2025 entra em vigor |
| 30/09/2026 | Começa a emissão eletrônica integrada ao SNCR |
| até 29/10/2026 | Transição: convivem papel e eletrônico com e sem integração |
| **30/10/2026** | Receita branca emitida **eletronicamente** tem de estar integrada ao SNCR |

A emissão eletrônica **continua opcional**. Mas sistema não integrado ao SNCR
fica impedido de emitir esses receituários eletronicamente. Assinatura exigida:
Notificação de Receita e Receita de Controle Especial = **qualificada
ICP-Brasil**; receita sujeita à retenção aceita avançada (inclusive gov.br).

A ANVISA já publicou a documentação da API do SNCR e um ambiente de treinamento.
A integração é trabalho do sistema de prescrição — ou seja, nosso, se um cliente
precisar emitir controlado eletronicamente.

## Pendência regulatória a confirmar

Há indicação de que a **RDC 1.000/2025** da ANVISA passou a valer em fevereiro de
2026 para receituários eletrônicos de controle, e orientações sanitárias estaduais
exigem assinatura ICP-Brasil em receitas de controle especial e antimicrobianos.
Isso pode tornar a assinatura **obrigatória** em parte do fluxo, não opcional.

**Confirmar no site da ANVISA e do CFM antes de prometer prazo a cliente.** Esta
é uma pendência de negócio, não de software.

## Onde está o código

| Arquivo | O que faz |
|---|---|
| `api/services/assinatura_icp.py` | Conteúdo canônico, resumo, e os provedores |
| `api/models.py` → `CertificadoAssinante` | Configuração por empresa e por profissional |
| `api/models.py` → `AssinaturaDocumento` | A assinatura e o certificado usado |
| `api/views_hospital_oncologia.py` | Endpoints de certificados, assinar e conferir |
| `templates/hospital_oncologia.html` | Faixa de assinatura no detalhe do ciclo |

Para suportar outro provedor, basta uma classe que cumpra o contrato
`ProvedorAssinatura` e uma entrada em `CertificadoAssinante.PROVEDOR`. Nada mais
no sistema precisa mudar.
