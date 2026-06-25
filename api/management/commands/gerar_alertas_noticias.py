"""
Agente 3 — Gerador de Alertas Epidemiológicos.

Lê notícias analisadas pelo Agente 2 (ia_analisado=True, alerta_disparado=False)
e cria NotificacaoFuncionario para todos os funcionários com token FCM ativo.
O signal em api/signals.py dispara o push Firebase automaticamente.

Critérios de disparo:
  score >= 4  → alerta normal
  score >= 7  → alerta urgente
  score >= 9  → alerta crítico
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    CredencialAppFuncionario,
    FuncionarioSST,
    NotificacaoFuncionario,
    NoticiaEpidemiologica,
)

SCORE_MIN   = 4.0
SCORE_ALTO  = 7.0
SCORE_CRIT  = 9.0


class Command(BaseCommand):
    help = "Agente 3: dispara push de alertas epidemiológicos via NotificacaoFuncionario."

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, help="Limita a uma empresa.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Mostra o que seria enviado sem criar notificações.")

    def handle(self, *args, **options):
        dry_run    = options["dry_run"]
        empresa_id = options.get("empresa_id")

        qs = NoticiaEpidemiologica.objects.filter(
            ia_analisado=True,
            alerta_disparado=False,
            ia_score_risco__gte=SCORE_MIN,
        )
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)

        pendentes = list(qs.select_related("empresa").order_by("-ia_score_risco"))

        if not pendentes:
            self.stdout.write("Nenhuma notícia com score ≥ 4 aguardando alerta.")
            return

        self.stdout.write(f"Processando {len(pendentes)} notícias elegíveis para alerta...")

        total_push = 0
        total_noticias = 0

        for noticia in pendentes:
            empresa = noticia.empresa
            score   = noticia.ia_score_risco or 0

            # Funcionários com token FCM ativo nesta empresa
            func_ids = list(
                CredencialAppFuncionario.objects
                .filter(empresa=empresa, ativo=True)
                .exclude(fcm_token="")
                .values_list("funcionario_id", flat=True)
                .distinct()
            )

            if not func_ids:
                self.stdout.write(f"  [{empresa.nome}] Sem funcionários com token — pulando.")
                with transaction.atomic():
                    noticia.alerta_disparado = True
                    noticia.save(update_fields=["alerta_disparado"])
                continue

            titulo  = self._titulo(noticia)
            msg     = self._mensagem(noticia)

            if dry_run:
                nivel = "CRÍTICO" if score >= SCORE_CRIT else "ALTO" if score >= SCORE_ALTO else "ALERTA"
                self.stdout.write(
                    f"  [DRY-RUN][{nivel}][score={score:.1f}] {empresa.nome} "
                    f"→ {len(func_ids)} funcionário(s): {titulo}"
                )
                total_push += len(func_ids)
                total_noticias += 1
                continue

            # Cria NotificacaoFuncionario → signal dispara push FCM automaticamente
            enviados = 0
            for func_id in func_ids:
                try:
                    func = FuncionarioSST.objects.get(pk=func_id)
                    NotificacaoFuncionario.objects.create(
                        funcionario=func,
                        empresa=empresa,
                        tipo=NotificacaoFuncionario.TIPO_GERAL,
                        titulo=titulo,
                        mensagem=msg,
                        referencia_id=noticia.pk,
                    )
                    enviados += 1
                except Exception as exc:
                    self.stderr.write(f"    Push para func {func_id}: {exc}")

            with transaction.atomic():
                noticia.alerta_disparado = True
                noticia.save(update_fields=["alerta_disparado"])

            self.stdout.write(f"  [{empresa.nome}] {enviados} push(es) disparados — score {score:.1f}")
            total_push     += enviados
            total_noticias += 1

        sufixo = " (DRY-RUN)" if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"Alertas{sufixo}: {total_noticias} notícias → {total_push} push notifications."
            )
        )

    def _titulo(self, noticia) -> str:
        score = noticia.ia_score_risco or 0
        if score >= SCORE_CRIT:
            prefixo = "ALERTA CRÍTICO"
        elif score >= SCORE_ALTO:
            prefixo = "Alerta Epidemiológico"
        else:
            prefixo = "Vigilância"

        doenca = ""
        if noticia.doencas_detectadas:
            doenca = noticia.doencas_detectadas[0].replace("_", " ").title()

        uf = f" — {noticia.ia_regiao_uf}" if noticia.ia_regiao_uf else ""
        return f"{prefixo}: {doenca}{uf}" if doenca else f"{prefixo}: {noticia.titulo[:60]}"

    def _mensagem(self, noticia) -> str:
        partes = [noticia.titulo[:150]]
        if noticia.ia_justificativa:
            partes.append(noticia.ia_justificativa)
        tendencia = {
            "crescendo":   "↑ Casos em crescimento",
            "estavel":     "→ Situação estável",
            "diminuindo":  "↓ Casos em queda",
        }.get(noticia.ia_tendencia, "")
        if tendencia:
            score = noticia.ia_score_risco or 0
            partes.append(f"{tendencia} | Risco: {score:.0f}/10")
        if noticia.ia_acoes:
            partes.append("Ação: " + noticia.ia_acoes[0])
        return "\n".join(partes)[:500]
