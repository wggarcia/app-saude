"""
Agente 2 — Analisador IA.

Lê notícias coletadas pelo Agente 1 (monitorar_noticias) que ainda não foram
analisadas por IA, envia cada uma para o Claude Haiku e salva a análise
estruturada de volta no banco.

Saída por notícia:
  - doença confirmada + CID-10
  - UF / município
  - casos estimados
  - tendência (crescendo | estavel | diminuindo)
  - score de risco 0–10
  - confiança 0–1
  - justificativa
  - ações recomendadas
  - nível de alerta recalculado pela IA (substitui o keyword match)

Requer: ANTHROPIC_API_KEY no ambiente.
Sem a chave a análise é pulada e o comando termina com aviso.
"""

import json
import os
import time

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import NoticiaEpidemiologica

MODEL_ID = "claude-haiku-4-5"
MAX_POR_RODADA = 50  # limite por execução para controlar custo

SYSTEM_PROMPT = """Você é o Agente Analisador Epidemiológico da SolusCRT.
Analise o título e resumo de uma notícia de saúde e retorne SOMENTE um JSON válido
com a seguinte estrutura (sem markdown, sem texto extra):

{
  "titulo_pt": "<título traduzido para português do Brasil, natural e claro>",
  "resumo_pt": "<resumo em português do Brasil, 1-3 frases, mesmo conteúdo do original>",
  "doenca_confirmada": "<nome padronizado ou null>",
  "cid10": "<código CID-10 ou null>",
  "regiao_uf": "<sigla UF brasileira ou null>",
  "municipio": "<nome do município ou null>",
  "casos_estimados": <número inteiro ou null>,
  "tendencia": "<crescendo|estavel|diminuindo|desconhecido>",
  "score_risco": <float 0.0 a 10.0>,
  "confianca": <float 0.0 a 1.0>,
  "nivel_alerta": "<informativo|alerta|critico>",
  "justificativa": "<1-2 frases explicando o score>",
  "acoes_recomendadas": ["<ação 1>", "<ação 2>"]
}

Sobre titulo_pt/resumo_pt: se o título ou resumo originais já estiverem em português,
apenas repita-os (corrigindo pontuação/clareza se necessário, sem mudar o sentido).
Se estiverem em outro idioma (inglês, hindi, mandarim etc.), traduza integralmente.
Nunca deixe texto em outro idioma nesses dois campos.

Critérios de score_risco:
  0-3  → informativo (notícia de contexto, sem urgência)
  4-6  → alerta (aumento de casos confirmado, vigilância necessária)
  7-8  → alerta alto (surto localizado, ação imediata na região)
  9-10 → crítico (epidemia ou emergência sanitária declarada)

Se a notícia não tem relação com saúde pública / epidemiologia, retorne score_risco: 0."""

USER_TEMPLATE = """Analise esta notícia epidemiológica:

TÍTULO: {titulo}
RESUMO: {resumo}
FONTE: {fonte}
DOENÇAS PRÉ-IDENTIFICADAS (keyword): {doencas}

Retorne o JSON de análise."""


class Command(BaseCommand):
    help = "Agente 2: analisa notícias não processadas com Claude Haiku e salva análise estruturada."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max",
            type=int,
            default=MAX_POR_RODADA,
            help=f"Máximo de notícias a analisar nesta execução (padrão {MAX_POR_RODADA}).",
        )
        parser.add_argument(
            "--empresa-id",
            type=int,
            help="Limita a análise a uma empresa específica.",
        )
        parser.add_argument(
            "--re-analisar",
            action="store_true",
            help="Re-analisa notícias que já passaram pela IA (útil após mudanças no prompt).",
        )

    def handle(self, *args, **options):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            self.stdout.write(
                self.style.WARNING(
                    "ANTHROPIC_API_KEY não encontrada no ambiente. "
                    "Configure a chave em console.anthropic.com e adicione "
                    "como variável de ambiente no Render. Análise IA pulada."
                )
            )
            return

        try:
            import anthropic
        except ImportError:
            self.stderr.write("Pacote 'anthropic' não instalado. Execute: pip install anthropic")
            return

        client = anthropic.Anthropic(api_key=api_key)

        qs = NoticiaEpidemiologica.objects.all()
        if options.get("empresa_id"):
            qs = qs.filter(empresa_id=options["empresa_id"])
        if not options["re_analisar"]:
            qs = qs.filter(ia_analisado=False)

        pendentes = list(qs.order_by("-criado_em")[: options["max"]])
        total = len(pendentes)

        if total == 0:
            self.stdout.write("Nenhuma notícia pendente de análise IA.")
            return

        self.stdout.write(f"Iniciando análise IA de {total} notícias com {MODEL_ID}...")

        analisadas = 0
        erros = 0

        for i, noticia in enumerate(pendentes, 1):
            self.stdout.write(f"  [{i}/{total}] {noticia.titulo[:70]}...")
            resultado = self._analisar(client, noticia)
            if resultado:
                self._salvar(noticia, resultado)
                analisadas += 1
            else:
                erros += 1
            # Pausa mínima para não exceder rate limit do Haiku
            if i % 10 == 0:
                time.sleep(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Análise IA concluída: {analisadas} processadas, {erros} erros."
            )
        )

    def _analisar(self, client, noticia) -> dict | None:
        user_msg = USER_TEMPLATE.format(
            titulo=noticia.titulo,
            resumo=noticia.resumo[:1500],
            fonte=noticia.fonte,
            doencas=", ".join(noticia.doencas_detectadas) or "nenhuma",
        )
        try:
            response = client.messages.create(
                model=MODEL_ID,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
            # Remove blocos markdown se o modelo inserir
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            self.stderr.write(f"    JSON inválido da IA para notícia {noticia.pk}: {exc}")
        except Exception as exc:
            self.stderr.write(f"    Erro API para notícia {noticia.pk}: {exc}")
        return None

    @transaction.atomic
    def _salvar(self, noticia, r: dict):
        # Mapeia score para nível de alerta com override da IA
        score = float(r.get("score_risco") or 0)
        nivel_ia = r.get("nivel_alerta", "informativo")
        if nivel_ia not in ("informativo", "alerta", "critico"):
            nivel_ia = "critico" if score >= 9 else "alerta" if score >= 4 else "informativo"

        titulo_pt = (r.get("titulo_pt") or "").strip()
        resumo_pt = (r.get("resumo_pt") or "").strip()
        if titulo_pt:
            noticia.titulo = titulo_pt[:500]
        if resumo_pt:
            noticia.resumo = resumo_pt

        noticia.ia_analisado       = True
        noticia.ia_score_risco     = score
        noticia.ia_cid10           = (r.get("cid10") or "")[:10]
        noticia.ia_regiao_uf       = (r.get("regiao_uf") or "")[:2]
        noticia.ia_municipio       = (r.get("municipio") or "")[:120]
        noticia.ia_casos_estimados = r.get("casos_estimados")
        noticia.ia_tendencia       = (r.get("tendencia") or "desconhecido")[:20]
        noticia.ia_confianca       = float(r.get("confianca") or 0)
        noticia.ia_justificativa   = r.get("justificativa") or ""
        noticia.ia_acoes           = r.get("acoes_recomendadas") or []
        noticia.ia_modelo_usado    = MODEL_ID
        noticia.nivel_alerta       = nivel_ia  # sobrescreve o keyword match

        # Atualiza lista de doenças se a IA identificou uma diferente
        doenca_ia = r.get("doenca_confirmada")
        if doenca_ia and doenca_ia not in noticia.doencas_detectadas:
            noticia.doencas_detectadas = list(noticia.doencas_detectadas) + [doenca_ia]

        noticia.save(update_fields=[
            "titulo", "resumo",
            "ia_analisado", "ia_score_risco", "ia_cid10", "ia_regiao_uf",
            "ia_municipio", "ia_casos_estimados", "ia_tendencia", "ia_confianca",
            "ia_justificativa", "ia_acoes", "ia_modelo_usado",
            "nivel_alerta", "doencas_detectadas",
        ])
