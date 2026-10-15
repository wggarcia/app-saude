# Assinatura digital ICP-Brasil — o que falta para ligar

Todo o software está pronto e testado. Falta **só o certificado**, que é compra
sua. Este documento é o passo a passo de quando você tiver o certificado em mãos.

## O que já funciona hoje, sem certificado

- A prescrição de quimioterapia tem um **conteúdo canônico** definido: paciente,
  diagnóstico, protocolo, ciclo, superfície corporal, cada dose calculada e a
  pré-medicação. É exatamente isso que será assinado.
- Esse conteúdo gera um **resumo SHA-256**. O resumo é o que prova, depois, que
  o documento não mudou.
- A tela mostra o estado real em cada caso: assinada e íntegra, assinada e
  **adulterada**, ou não assinada (dizendo o porquê).
- A detecção de adulteração já funciona e está coberta por teste: se alguém
  mudar uma dose depois da assinatura, a assinatura passa a `invalidada` e a
  tela mostra o aviso em vermelho.

## A regra que o sistema segue

**Sem certificado configurado, nada é marcado como assinado.** A tentativa é
registrada como `falha`, com o motivo, e a API devolve HTTP 503 listando o que
falta. Um sistema que finge assinar seria pior do que um sem assinatura, porque
a mentira teria valor jurídico.

## O que você precisa comprar

Um **certificado ICP-Brasil e-CPF do médico responsável** — não da empresa. Quem
assina prescrição é a pessoa física com registro no conselho.

Dois tipos servem:

| Tipo | Formato | Observação |
|------|---------|------------|
| **A1** | arquivo `.pfx` / `.p12`, validade 1 ano | **É o que o sistema já suporta.** Fica no servidor, assina sem ninguém presente. |
| **A3** | token USB ou cartão, validade até 3 anos | Exige o dispositivo plugado na máquina que assina — não serve para servidor remoto sem trabalho adicional. |

**Recomendação: A1**, porque o sistema assina no servidor, e o A3 exigiria que
alguém mantivesse um token físico conectado.

## Como ligar, depois de comprar (A1)

1. Coloque o arquivo do certificado num diretório **fora do repositório** e com
   permissão restrita ao usuário do serviço:

```bash
sudo install -o root -g root -m 600 /caminho/do/certificado.pfx /etc/soluscrt/certificado.pfx
```

2. Acrescente as três variáveis ao `.env` do VPS (e ao painel do Render, se for
   assinar por lá também):

```bash
ICP_ASSINATURA_PROVEDOR=a1_local
ICP_CERTIFICADO_A1_PATH=/etc/soluscrt/certificado.pfx
ICP_CERTIFICADO_A1_SENHA=<a senha do certificado>
```

3. Reinicie o serviço:

```bash
sudo systemctl restart soluscrt
```

4. Confirme que o sistema reconheceu, sem precisar assinar nada:

```bash
curl -s --unix-socket /run/soluscrt.sock -H 'Host: empresa.soluscrt.com.br' -H 'X-Forwarded-Proto: https' http://localhost/api/hospital/oncologia/assinatura/status
```

Deve responder `"disponivel": true`. Se vier `false`, o campo `pendencias` diz
exatamente o que está faltando.

## Cuidados que não são opcionais

- **O arquivo do certificado nunca entra no Git nem em backup público.** Ele é
  a identidade jurídica do médico: quem tem o arquivo e a senha assina no lugar
  dele.
- **A senha vai em variável de ambiente, nunca no código.**
- **O certificado A1 vence em 1 ano.** O sistema recusa assinar com certificado
  vencido (está coberto por teste), mas não avisa com antecedência — anote a
  data de validade na agenda.
- **Atenção à replicação para o Render (Oregon/EUA).** O banco é replicado a
  cada 6h; as assinaturas vão junto. Isso é aceitável (a assinatura é um dado
  do documento), mas o **arquivo do certificado** não deve ser copiado para lá
  sem uma decisão consciente.

## O que fica faltando mesmo depois do certificado

**Carimbo de tempo.** A assinatura registra a data do nosso servidor. Para que a
data tenha fé pública perante terceiros, é preciso contratar uma **Autoridade de
Carimbo do Tempo (ACT)** credenciada. O sistema já marca essa diferença: o campo
`data_com_fe_publica` vem `false` e a tela diz "sem carimbo de tempo de
autoridade externa: a data é a do servidor".

Sem ACT a assinatura continua válida — o que não se prova perante terceiros é
*quando* ela foi feita. Para prescrição de quimioterapia dentro da instituição
isso costuma ser suficiente; vale reavaliar se o documento passar a ser usado
em disputa judicial ou em auditoria de operadora.

## Onde está o código

| Arquivo | O que faz |
|---------|-----------|
| `api/services/assinatura_icp.py` | Conteúdo canônico, resumo SHA-256, provedores de assinatura |
| `api/models.py` → `AssinaturaDocumento` | Registro da assinatura e do certificado usado |
| `api/views_hospital_oncologia.py` | Endpoints de assinar e conferir |
| `templates/hospital_oncologia.html` | Faixa de assinatura no detalhe do ciclo |

Para suportar outro provedor no futuro (A3, ou um serviço de assinatura em
nuvem), basta criar uma classe que cumpra o contrato `ProvedorAssinatura` e
registrá-la em `_PROVEDORES`. Nada mais no sistema precisa mudar.
