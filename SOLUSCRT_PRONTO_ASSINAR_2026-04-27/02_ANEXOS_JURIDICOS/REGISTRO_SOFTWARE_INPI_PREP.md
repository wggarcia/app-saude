# Preparação — Registro de Software no INPI (Lei 9.609/98)

**Data de preparação:** 21/05/2026
**Requerente:** Wagner Garcia — CPF 091.189.637-65
**Portal:** https://www.gov.br/inpi/pt-br/servicos/programas-de-computador

---

## Dados para preencher no formulário INPI

### Identificação do Programa

| Campo | Valor a preencher |
|---|---|
| **Título do programa** | SolusCRT Saude |
| **Versão** | 1.0.0 |
| **Data de criação/conclusão** | 21/05/2026 |
| **Natureza** | Novo programa (não é atualização) |
| **Confidencialidade** | SIM — requerer sigilo por 50 anos (padrão recomendado) |

### Linguagem e Ambiente

| Campo | Valor |
|---|---|
| **Linguagem de programação principal** | Python 3.11 |
| **Linguagens secundárias** | Dart (Flutter 3.x), HTML5, CSS3, JavaScript |
| **Sistema operacional de desenvolvimento** | Linux (Ubuntu/Debian) / macOS |
| **Sistema operacional de execução** | Linux (servidor), Android 10+, iOS 15+ |
| **Banco de dados** | PostgreSQL 15 |
| **Tipo de interface** | Web (browser), Aplicativo móvel (iOS/Android) |

### Autores / Titulares

| Campo | Valor |
|---|---|
| **Autor 1 — nome** | Wagner Garcia |
| **Autor 1 — CPF** | 091.189.637-65 |
| **Autor 1 — endereço** | Niterói, RJ, Brasil |
| **Titular dos direitos** | Wagner Garcia (mesmo que o autor) |
| **Pessoa física ou jurídica** | Pessoa Jurídica — CNPJ 66.940.015/0001-48 |

### Descrição do Programa (copie este texto no formulário)

```
SolusCRT Saude é uma plataforma SaaS (Software como Serviço) de gestão
integrada em saúde, composta por seis módulos independentes e dois
aplicativos móveis:

1. MÓDULO EMPRESA/SST: Gestão de saúde ocupacional, conformidade com
   NRs (Normas Regulamentadoras), controle de ASO (Atestado de Saúde
   Ocupacional), CAT (Comunicação de Acidente de Trabalho), afastamentos,
   treinamentos de segurança, EPIs, laudos de exames e integração com
   o eSocial SST. Inclui módulo de bem-estar anônimo por arquitetura.

2. MÓDULO FARMÁCIA: Controle de estoque farmacêutico, rastreabilidade
   de lotes, dispensação, controle de medicamentos controlados (SCTC),
   pedidos de compra, gestão de fornecedores, análise de demanda por
   inteligência epidemiológica territorial.

3. MÓDULO HOSPITAL: Triagem de Manchester, gestão de leitos, internações,
   prescrições eletrônicas, faturamento hospitalar (APAC/AIH), indicadores
   de pressão assistencial e integração com fontes epidemiológicas.

4. MÓDULO GOVERNO: Sala de situação epidemiológica territorial, cruzamento
   de dados com fontes oficiais (DATASUS, InfoDengue, InfoGripe, IBGE/SIDRA),
   emissão e governança de alertas públicos, indicadores por bairro/município/
   estado e série temporal.

5. MÓDULO PLANO DE SAÚDE: Gestão de operadoras de planos de saúde,
   cadastro de beneficiários e contratos corporativos, guias de autorização
   (TISS), controle de SLA conforme RN ANS 395/452, auditoria médica por
   scoring algorítmico, telemedicina, odontologia e geração de relatórios
   regulatórios (DIOPS, SIB, TISS 3.05.00).

6. MÓDULO REDE DE SAÚDE: Gestão de rede de prestadores, unidades de saúde,
   credenciamento e geolocalização.

APLICATIVO DA POPULAÇÃO (gratuito): Coleta colaborativa e anônima de
sintomas para inteligência epidemiológica territorial, exibição de mapa
de risco e alertas oficiais. Disponível para Android e iOS.

APLICATIVO DO FUNCIONÁRIO: Acesso do trabalhador ao próprio ASO digital,
solicitações de exames, notificações de treinamentos, check-ins de
bem-estar anônimos. Vinculado ao módulo Empresa/SST.

A plataforma implementa: autenticação JWT multi-tenant, controle de
acesso por perfil (RBAC), rate limiting via Redis, trilha de auditoria
persistente, conformidade LGPD (Lei 13.709/2018), conformidade com
RNs da ANS e integração com gateway de pagamento Asaas.
```

### Campo "Finalidade / Aplicação"

```
Gestão integrada de saúde empresarial, hospitalar, farmacêutica,
governamental e de operadoras de planos de saúde. A plataforma
destina-se a empresas privadas, hospitais, redes de farmácias,
órgãos de governo municipal/estadual e operadoras de planos de
saúde, atuando como ferramenta de apoio à decisão, conformidade
regulatória e inteligência epidemiológica territorial.
```

---

## Depósito Técnico — Código-Fonte

O INPI exige um **extrato do código-fonte** para depósito. Você NÃO precisa
entregar todo o código — apenas um trecho representativo.

### Regra padrão INPI:
- Se o código tiver **até 100 páginas**: depositar integral
- Se tiver **mais de 100 páginas**: depositar as **primeiras 50** + **últimas 50 páginas**
- Formato aceito: PDF (recomendado), TXT ou impresso

### Como gerar o extrato para o SolusCRT

Execute no terminal para gerar o PDF do extrato:

```bash
# No diretório /Users/angelica/backend
# Instalar dependência se necessário: pip install enscript (ou usar cat)

# Listar os principais arquivos do backend
find . -name "*.py" \
  -not -path "*/migrations/*" \
  -not -path "*/__pycache__/*" \
  -not -path "*/venv/*" \
  -not -path "*/.git/*" \
  | sort | head -20

# Gerar extrato das primeiras 50 páginas (aprox. 3000 linhas)
# Arquivos principais a incluir:
# - backend/settings.py (configuração geral)
# - api/models.py (primeiras 500 linhas)
# - api/views.py (primeiras 500 linhas)
# - api/views_plano_saude.py (primeiras 300 linhas)
# - backend/urls.py (início)

cat backend/settings.py \
    api/models.py \
    api/views.py \
    api/views_plano_saude.py \
    backend/urls.py \
    | head -3000 > /tmp/soluscrt_extrato_inicio.txt

# Gerar extrato das últimas 50 páginas (aprox. últimas 3000 linhas)
cat api/models.py \
    api/views_plano_saude.py \
    api/email_service.py \
    api/tests.py \
    | tail -3000 > /tmp/soluscrt_extrato_fim.txt

# Unir em um único arquivo
cat /tmp/soluscrt_extrato_inicio.txt \
    /tmp/soluscrt_extrato_fim.txt \
    > /tmp/SOLUSCRT_DEPOSITO_INPI.txt

echo "Arquivo gerado. Linhas: $(wc -l < /tmp/SOLUSCRT_DEPOSITO_INPI.txt)"
```

Depois converta para PDF:
- macOS: abra o .txt no TextEdit → Arquivo → Exportar como PDF
- Ou: use `enscript -p - arquivo.txt | ps2pdf - arquivo.pdf`

### Capa do depósito (primeira página do PDF)

```
PROGRAMA DE COMPUTADOR — DEPÓSITO DE EXTRATO DE CÓDIGO-FONTE

Título: SolusCRT Saude
Versão: 1.0.0
Linguagem principal: Python 3.11
Data de conclusão: 21/05/2026
Autor/Titular: Wagner Garcia — CPF 091.189.637-65
Niterói, RJ, Brasil

Este extrato foi produzido para fins de registro junto ao INPI
conforme Lei n.º 9.609/1998 e é parte integrante do pedido de
registro de programa de computador.

CONFIDENCIAL — Solicita-se sigilo por 50 (cinquenta) anos nos
termos do art. 2.º, § 3.º da Lei 9.609/1998.
```

---

## Taxa (GRU — Guia de Recolhimento da União)

| Situação | Código GRU | Valor |
|---|---|---|
| Pedido de Registro de Programa de Computador - RPC (Cod. 730) | 730 | R$ 210,00 |

**Como pagar:**
1. Acesse: https://www.gov.br/inpi/pt-br/servicos/programas-de-computador/tabela-de-retribuicoes
2. Gere a GRU com o serviço "Depósito de Programa de Computador"
3. Pague via banco (boleto ou PIX Gov)
4. Guarde o comprovante — você vai anexar ao pedido

---

## O que acontece depois do depósito

| Prazo | Evento |
|---|---|
| Na hora | Número de protocolo gerado — GUARDE ESTE NÚMERO |
| 30–60 dias | Exame formal (INPI verifica se documentação está completa) |
| Se aprovado | Certificado de Registro emitido (PDF com QR Code) |
| Se houver pendência | Notificação para complementar — prazo 60 dias |

**Proteção começa na data do protocolo**, não na data do certificado.

---

## Registro do App Flutter (separado, recomendado)

Registrar o app móvel como obra separada:
- Título: "SolusCRT Saude — Aplicativo Móvel"
- Linguagem: Dart (Flutter 3.x)
- Mesmos autores/titulares
- Extrato: arquivos `lib/main.dart` + principais telas

Custo adicional: mais R$ 210,00 (um depósito por programa, Cod. 730).

---

## Checklist de envio

- [ ] Conta INPI criada/acessada em: https://www.gov.br/inpi
- [ ] GRU paga e comprovante em mãos
- [ ] PDF do extrato de código-fonte preparado (com capa)
- [ ] Formulário preenchido com dados acima
- [ ] Sigilo de 50 anos marcado
- [ ] Número de protocolo anotado após envio
- [ ] Comprovante de depósito salvo em local seguro

---

## Onde guardar o certificado

Quando o certificado chegar (PDF com QR Code):
- Salvar em: `SOLUSCRT_PRONTO_ASSINAR_2026-04-27/02_ANEXOS_JURIDICOS/`
- Nome sugerido: `CERTIFICADO_REGISTRO_SOFTWARE_INPI_SOLUSCRT.pdf`
- Backup: Google Drive, iCloud e HD externo

*Preparado em 21/05/2026*
