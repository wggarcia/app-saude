# Relatorio de Stress Test SolusCRT Brasil

- Inicio: 22/04/2026 06:22:07
- Registros sinteticos criados: 1350
- Requisicoes exercitadas: 604
- Latencia media: 51.7 ms
- Latencia p95: 26.54 ms
- Erros capturados: 0
- Resultado do decaimento ate 1%: APROVADO

## Leitura Executiva

O teste simulou uma sala de controle epidemiologica nacional com sinais populacionais em todas as regioes do Brasil, validando mapa publico, APIs do app, dashboards B2B/B2G, alertas governamentais e governanca epidemiologica.

## Escopo Tecnico

- Carga inicial feita pelo endpoint publico do app (`/api/public/registrar`) para simular envio real da populacao.
- Cobertura geografica distribuida pelas 5 regioes do Brasil, com capitais/territorios de todos os estados e DF.
- Cada minuto representou 1 dia epidemiologico, totalizando 30 dias simulados em 30 minutos.
- A janela de risco ficou estavel por 10 dias sem novos sintomas e depois reduziu progressivamente ate 1% no dia 30.
- O teste usou prefixo sintetico rastreavel e limpeza seletiva, sem apagar registros reais.

## Indicadores Dia a Dia

| Dia simulado | Indice ativo | Retencao | Hotspots | Erros | Latencia media |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1350.00 | 100.00% | 28 | 0 | 643.34 ms |
| 2 | 1350.00 | 100.00% | 28 | 0 | 5.57 ms |
| 3 | 1350.00 | 100.00% | 28 | 0 | 4.94 ms |
| 4 | 1350.00 | 100.00% | 28 | 0 | 6.62 ms |
| 5 | 1350.00 | 100.00% | 28 | 0 | 5.86 ms |
| 6 | 1350.00 | 100.00% | 28 | 0 | 5.69 ms |
| 7 | 1350.00 | 100.00% | 28 | 0 | 5.95 ms |
| 8 | 1350.00 | 100.00% | 28 | 0 | 5.48 ms |
| 9 | 1350.00 | 100.00% | 28 | 0 | 5.65 ms |
| 10 | 1350.00 | 100.00% | 28 | 0 | 5.81 ms |
| 11 | 1283.85 | 95.10% | 28 | 0 | 5.86 ms |
| 12 | 1216.35 | 90.10% | 28 | 0 | 5.39 ms |
| 13 | 1150.20 | 85.20% | 28 | 0 | 6.88 ms |
| 14 | 1082.70 | 80.20% | 28 | 0 | 5.65 ms |
| 15 | 1015.20 | 75.20% | 28 | 0 | 5.59 ms |
| 16 | 949.05 | 70.30% | 28 | 0 | 6.04 ms |
| 17 | 881.55 | 65.30% | 28 | 0 | 7.17 ms |
| 18 | 815.40 | 60.40% | 28 | 0 | 5.85 ms |
| 19 | 747.90 | 55.40% | 28 | 0 | 6.02 ms |
| 20 | 681.75 | 50.50% | 28 | 0 | 688.11 ms |
| 21 | 615.60 | 45.60% | 28 | 0 | 5.55 ms |
| 22 | 548.10 | 40.60% | 28 | 0 | 5.87 ms |
| 23 | 481.95 | 35.70% | 28 | 0 | 6.35 ms |
| 24 | 414.45 | 30.70% | 28 | 0 | 5.76 ms |
| 25 | 348.30 | 25.80% | 28 | 0 | 5.89 ms |
| 26 | 280.80 | 20.80% | 28 | 0 | 5.83 ms |
| 27 | 213.30 | 15.80% | 28 | 0 | 5.42 ms |
| 28 | 147.15 | 10.90% | 28 | 0 | 5.37 ms |
| 29 | 79.65 | 5.90% | 28 | 0 | 5.96 ms |
| 30 | 13.50 | 1.00% | 9 | 0 | 4.78 ms |

## Governo

- O painel governamental foi exercitado junto com alertas, matriz de decisao e panorama epidemiologico.
- A simulacao representa coordenacao de vigilancia, comunicacao publica e priorizacao territorial.
- O comportamento esperado e manter estabilidade epidemiologica por 10 dias sem novos envios e reduzir gradualmente depois disso.
- Leitura operacional: nos dias 1 a 10, governo manteria vigilancia ativa e comunicacao preventiva; depois do dia 10, acompanharia queda sustentada antes de reduzir nivel de resposta.
- Acao recomendada no pico: acionar vigilancia municipal/estadual, validar sinais com fontes oficiais, preparar alerta publico e priorizar municipios com hotspots persistentes.

## Empresas, Farmacias e Hospitais

- Dashboards empresariais, farmacia e hospital foram acessados em ciclo continuo para medir disponibilidade durante o estresse.
- O uso esperado para empresas e antecipar absenteismo, risco ocupacional e comunicacao preventiva.
- O uso esperado para farmacias/hospitais e preparar estoque, triagem, leitos e pronto atendimento conforme os focos.
- Leitura empresarial: empresas acompanhariam risco territorial para orientar home office, escalas, higiene reforcada e comunicacao com colaboradores.
- Leitura farmacia/hospital: farmacias reforcariam estoque por perfil de sintomas; hospitais ajustariam triagem, equipe e capacidade de pronto atendimento.

## App da Populacao

- Endpoints de resumo, mapa, radar local e alertas publicos foram acionados continuamente.
- A leitura do app deve mostrar focos apenas enquanto houver indice ativo epidemiologico.
- Comunicados governamentais aparecem pela API publica mesmo quando push nativo nao entrega no simulador.
- O app foi validado pela camada de API; testes nativos em iOS/Android ainda devem ser repetidos antes de publicar nova versao nas lojas.

## Bugs e Riscos Observados

- Nenhum erro HTTP >= 400 foi capturado durante a rotina.
- Risco residual: o teste foi executado no backend local com Django Client; antes de comercializar, repetir em Render com banco Postgres e monitoramento de logs.
- Risco residual: o teste nao substitui teste visual manual no app nativo, especialmente permissao de localizacao, mapa e recebimento de push.
- Risco residual: fontes oficiais externas podem variar por disponibilidade; manter cache, timeout e jobs assincronos para nao travar dashboard.

## Conclusao

No pico, o indice ativo chegou a 1350.00. No fim, chegou a 13.50 (1.00% do volume inicial).

Arquivo do relatorio: `docs/relatorios/stress_soluscrt_brasil_20260422_062207.md`
