# Sala de Controle Epidemiologica SolusCRT

Esta camada define o que diferencia o produto de um dashboard comum: confianca institucional, metodo, governanca e decisao operacional.

## 1. Camadas de informacao

- Populacao: relatos anonimos enviados pelo app, usados como alerta precoce.
- Fontes oficiais: agregados de IBGE, Fiocruz, OpenDataSUS e DATASUS para historico, incidencia, prevalencia e validacao.
- IA: classificacao probabilistica, crescimento, anomalias, foco dominante e recomendacoes por segmento.
- Institucional: dados de hospitais, farmacias, laboratorios, empresas e governo quando integrados.

Cada indicador deve informar origem, confianca e limite de uso. Relato cidadao nunca deve ser tratado como caso confirmado.

## 2. Fluxo de alerta governamental

1. Rascunho: comunicado em construcao.
2. Em revisao: texto e territorio aguardam validacao.
3. Aprovado: autoridade ou responsavel autorizou publicacao.
4. Publicado: aparece no app e pode disparar push.
5. Revogado: alerta retirado com trilha historica preservada.

O sistema agora registra protocolo, responsaveis, timestamps e auditoria para cada etapa.

## 3. Matriz de decisao

O painel deve responder rapidamente:

- Governo: precisa emitir alerta, acionar campo, investigar bairro, reforcar campanha ou aguardar?
- Hospitais: precisa preparar triagem, leitos, oxigenio, equipe ou fluxo de emergencia?
- Farmacias/laboratorios: precisa aumentar estoque, testes, repelentes, hidratacao ou suporte respiratorio?
- Empresas: precisa ajustar protocolo interno, home office, comunicacao ou monitoramento?
- Populacao: precisa receber orientacao simples, segura e sem alarmismo?

## 4. Indicadores essenciais

- Incidencia por 100 mil habitantes.
- Prevalencia estimada no periodo.
- Crescimento percentual com decaimento quando casos deixam de entrar.
- Serie historica por municipio, bairro e UF.
- Perfil sociodemografico quando houver base legal e fonte confiavel.
- Mortalidade, letalidade, internacao e cobertura de acoes quando integradas a fontes oficiais.
- Limiar epidemico e alertas por cor.
- Score de confianca, suspeita e antifraude.

## 5. Regras de seguranca e confianca

- Publicar somente dados agregados para a populacao.
- Nunca expor localizacao individual.
- Bloquear envios repetidos por rede/aparelho/janela temporal.
- Separar dado confirmado de estimativa IA.
- Registrar auditoria de operacoes sensiveis.
- Exigir aprovacao para alerta publico governamental.
- Manter logs, backups, monitoramento e plano de resposta a incidente.

## 6. Mensagem comercial honesta

O SolusCRT Saude nao deve ser vendido como diagnostico medico. A proposta forte e:

"Plataforma de inteligencia epidemiologica e sala de controle territorial que combina sinais anonimos da populacao, fontes oficiais e IA para antecipar focos, orientar decisoes e apoiar governos, empresas, hospitais, farmacias e cidadaos."
