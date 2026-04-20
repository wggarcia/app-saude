# Base LGPD e Comunicacao de Saude

Este documento e um ponto de partida operacional. Antes de publicar, revise com advogado/consultor de privacidade.

## Politica de privacidade precisa explicar

- Quais dados sao coletados: sintomas informados, localizacao aproximada/regional, data/hora, identificador tecnico do aparelho e dados de uso.
- Finalidade: monitoramento epidemiologico, deteccao de focos, comunicados publicos e inteligencia agregada para governo/empresas contratantes.
- Base legal: consentimento do usuario para app publico e execucao de contrato/interesse publico quando aplicavel a clientes institucionais.
- Compartilhamento: dados agregados e anonimizados para paineis; nunca vender dados pessoais da populacao.
- Retencao: definir prazo para registros brutos e prazo maior apenas para agregados anonimizados.
- Direitos do titular: canal para acesso, correcao, exclusao e revogacao de consentimento quando aplicavel.

## Aviso dentro do app

Texto recomendado:

"O SolusCRT Saude acompanha sinais regionais de saude publica. As informacoes exibidas sao estimativas epidemiologicas e nao substituem diagnostico, consulta medica ou orientacao oficial de autoridades de saude. Em caso de sintomas graves, procure atendimento imediatamente."

## Operacao minima de seguranca

- Rotacionar secrets que ja circularam localmente.
- Proteger chaves Google/Mapbox por dominio, bundle id e package name.
- Ativar logs de auditoria para governo e console operacional.
- Fazer backup automatico e teste de restauracao.
- Ter plano de resposta a incidente com responsavel, prazo de comunicacao e processo de contencao.
