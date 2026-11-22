# SoloCRT Saúde 1.0.30 (31)

## Para a App Store — "O que há de novo"

Texto sugerido, em português, dentro do limite de 4.000 caracteres:

> **Perguntas que se adaptam ao que você responde**
>
> Agora, quando você marca um sintoma, o app pode fazer algumas perguntas a
> mais sobre ele — só sobre aquele sintoma, e só para quem o marcou. São
> perguntas curtas que ajudam a distinguir doenças parecidas entre si.
>
> **Aviso sobre mordedura de animal**
>
> Se você informar que foi mordido, arranhado ou lambido por um animal, o app
> orienta na hora a procurar uma unidade de saúde. A vacina antirrábica depende
> de começar cedo.
>
> **Tela de revisão mais completa**
>
> Antes de enviar, você agora vê todas as suas respostas, não só os sintomas
> marcados.

## Checklist antes de enviar

- [ ] Versão `1.0.30+31` no pubspec e na procedência enviada ao servidor
- [ ] Build aponta para produção (`https://app.solocrt.com.br`) — confirmado:
      sem `--dart-define=USE_LOCAL_API`, `Config.baseUrl` devolve produção
- [ ] Backend já no ar aceitando os campos novos (commit `2f7c739`, migrações
      0273–0275 aplicadas em 21/11/2026)
- [ ] Privacidade na App Store: **nenhum dado novo de identificação** foi
      adicionado. As perguntas novas são clínicas e seguem anônimas, no mesmo
      registro que já existia
- [ ] Revisão clínica das perguntas — **pendente**, ver
      `REVISAO_CLINICA_PERGUNTAS.md` na raiz do projeto

## O que mudou tecnicamente

| Área | Mudança |
|---|---|
| Perguntas | 27 condicionais em 11 portas; de 38 fixas para 41–46 no caso realista |
| Campos novos enviados | 27 nuláveis + `mordedura_animal` + `app_versao` |
| Aviso | Profilaxia antirrábica ao responder "sim" para mordedura |
| Tela de revisão | Nova seção "Respostas de detalhamento" |
| Compatibilidade | Backend aceita envios da 1.0.29 sem mudança de comportamento |

## Aviso que permanece

As perguntas clínicas foram redigidas por IA a partir de literatura e **ainda
não foram revisadas por médico habilitado**. O app continua sendo apoio de
triagem e monitoramento epidemiológico — não dá diagnóstico, e o aviso de que
não substitui atendimento médico segue na tela de revisão.
