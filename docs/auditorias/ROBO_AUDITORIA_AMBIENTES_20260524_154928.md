# Relatorio do Robo de Auditoria de Ambientes

Execucao: `robo-auditoria-20260524_154928`
Gerado em: `2026-05-24 15:49:38 -03`

## Resumo Executivo
- Checks totais: **202**
- Checks OK: **198**
- Checks com falha: **4**
- Critica: **1**
- Alta: **3**
- Media: **0**
- Baixa: **0**

## Resultado por Ambiente
| Ambiente | OK/Total | Falhas | Critica | Alta | Media | Baixa |
|---|---:|---:|---:|---:|---:|---:|
| SST | 41/42 | 1 | 0 | 1 | 0 | 0 |
| Farmacia | 40/40 | 0 | 0 | 0 | 0 | 0 |
| Hospital | 39/40 | 1 | 0 | 1 | 0 | 0 |
| Plano de Saude | 38/40 | 2 | 1 | 1 | 0 | 0 |
| Governo | 40/40 | 0 | 0 | 0 | 0 | 0 |

## Achados Priorizados
1. [CRITICA] [plano_saude] Bloqueio pagina cruzada (/dashboard-empresa/)
Caminho: `/dashboard-empresa/`
Esperado: Nao retornar 200
Obtido: HTTP 200

2. [ALTA] [hospital] Sem links misturados em /hospital/gestao/
Caminho: `/hospital/gestao/`
Esperado: 0 links para outros segmentos
Obtido: 1 link(s) suspeito(s)
Evidencia: `/plano-saude/gestao/`

3. [ALTA] [plano_saude] /dashboard/ redireciona para o ambiente correto
Caminho: `/dashboard/`
Esperado: 302 -> /dashboard-plano-saude/
Obtido: 302 -> /dashboard-empresa/

4. [ALTA] [sst] Destino perfil operacao
Caminho: `/api/login`
Esperado: /gestao/
Obtido: /dashboard-empresa/

## Recomendacoes de Correcao
1. Corrigir primeiro todos os achados CRITICA (acesso cruzado 200, API propria fora do ar, login/destino quebrado).
2. Depois tratar os achados ALTA (links misturados, regras de perfil inconsistentes, redirecionamentos incorretos).
3. Reexecutar este robo apos cada lote de ajustes para validar regressao zero.
