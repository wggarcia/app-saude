"""
Alerta One Health — Epizootias PNH / Febre Amarela.

Lê FonteOficialAgregado (fonte ms_epizootias_fa) para os N meses mais
recentes e gera NoticiaEpidemiologica para empresas de tipo governo.

Sem dado recente → sem alerta (nunca inventa). Usa unique_together
(empresa, url) para deduplicação automática — pode rodar toda vez após
coletar_epizootias_fa sem duplicar.

Uso:
    python manage.py gerar_alertas_one_health
    python manage.py gerar_alertas_one_health --meses 3
    python manage.py gerar_alertas_one_health --dry-run
"""
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from django.utils import timezone

from api.models import Empresa, FonteOficialAgregado, NoticiaEpidemiologica
from api.push_service import enviar_push_one_health, push_disponivel

FONTE_ID  = "ms_epizootias_fa"
INDICADOR = "febre_amarela_epizootias_pnh"

DEMAS_URL = "https://apidadosabertos.saude.gov.br/arboviroses/febre-amarela-epzootias"

UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco",
    "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}


def _score_e_nivel(total):
    if total >= 3:
        return 9.0, "critico"
    return 6.0, "alerta"


def _periodos_recentes(n):
    """n últimos meses no formato 'AAAA-Mmm' (ex: '2026-M07')."""
    hoje = timezone.now()
    periodos = []
    for delta in range(n):
        mes = hoje.month - delta
        ano = hoje.year
        if mes <= 0:
            mes += 12
            ano -= 1
        periodos.append(f"{ano}-M{mes:02d}")
    return periodos


class Command(BaseCommand):
    help = "Gera alertas One Health (epizootias PNH/FA) para empresas de governo."

    def add_arguments(self, parser):
        parser.add_argument("--meses", type=int, default=2,
                            help="Meses retroativos a verificar (default 2).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Exibe alertas sem salvar.")

    def handle(self, *args, **opts):
        dry_run  = opts["dry_run"]
        periodos = _periodos_recentes(opts["meses"])

        registros = list(
            FonteOficialAgregado.objects.filter(
                fonte_id=FONTE_ID,
                indicador=INDICADOR,
                periodo__in=periodos,
            )
        )

        if not registros:
            self.stdout.write("Nenhuma epizootia recente — sem alerta a gerar.")
            return

        empresas_gov = list(Empresa.objects.filter(tipo_conta="governo", ativo=True))
        if not empresas_gov:
            self.stdout.write(self.style.WARNING("Nenhuma empresa de governo ativa."))
            return

        criados = 0
        for reg in registros:
            uf      = reg.estado
            periodo = reg.periodo
            total   = int(reg.valor)
            score, nivel = _score_e_nivel(total)

            try:
                ano_str, mes_str = periodo.split("-M")
                ano = int(ano_str)
                mes = int(mes_str)
            except Exception:
                continue

            nome_uf = UF_NOMES.get(uf, uf)
            url     = f"{DEMAS_URL}?uf_ocor={uf}&ano_ocor={ano}&mes_ocor={mes}"

            titulo = (
                f"⚠ Sinal One Health: {total} epizootia(s) PNH em {nome_uf} "
                f"({mes:02d}/{ano}) — risco Febre Amarela"
            )
            resumo = (
                f"{total} epizootia(s) de primatas não-humanos (PNH) notificadas em "
                f"{nome_uf} em {mes:02d}/{ano}. "
                "No ciclo silvestre da Febre Amarela, macacos adoecem e morrem antes do "
                "primeiro caso humano — epizootia de PNH é sinal de alerta precoce "
                "e de notificação imediata pelo Ministério da Saúde. "
                "Fonte oficial: MS / DEMAS (Dados Abertos)."
            )

            if dry_run:
                self.stdout.write(
                    f"  [{nivel.upper()}][score={score}] {uf} | {total} epizootia(s) | {titulo[:70]}"
                )
                continue

            pub_em = timezone.now().replace(
                day=1, month=mes, year=ano,
                hour=0, minute=0, second=0, microsecond=0,
            )

            novo_nesta_uf = False
            for empresa in empresas_gov:
                try:
                    NoticiaEpidemiologica.objects.create(
                        empresa=empresa,
                        titulo=titulo,
                        fonte="One Health / MS-DEMAS",
                        url=url,
                        resumo=resumo,
                        doencas_detectadas=["Febre Amarela"],
                        nivel_alerta=nivel,
                        publicado_em=pub_em,
                        ia_analisado=True,
                        ia_score_risco=score,
                        ia_regiao_uf=uf,
                        ia_tendencia="crescendo" if total >= 3 else "estavel",
                        ia_confianca=0.92,
                        ia_justificativa=(
                            f"Sinal One Health direto: {total} epizootia(s) PNH confirmadas "
                            f"em {nome_uf} ({mes:02d}/{ano}) na fonte oficial MS/DEMAS. "
                            "Dado de notificação obrigatória — sem necessidade de inferência."
                        ),
                        ia_acoes=[
                            f"Verificar cobertura vacinal contra Febre Amarela em {nome_uf}",
                            "Acionar vigilância de epizootias junto à COVEV/SVS local",
                            "Alertar unidades de saúde na região sobre risco silvestre",
                        ],
                        ia_modelo_usado="one_health_direto",
                        alerta_disparado=True,
                    )
                    criados += 1
                    novo_nesta_uf = True
                except IntegrityError:
                    pass  # unique_together (empresa, url) — já existe, ignora

            # Push Firebase para cidadãos da UF quando há alerta novo
            if novo_nesta_uf and push_disponivel():
                push_titulo = f"Alerta One Health — {nome_uf}"
                push_msg = (
                    f"{total} epizootia(s) de primatas confirmadas em {nome_uf} ({mes:02d}/{ano}). "
                    "Sinal de risco silvestre para Febre Amarela. Mantenha vacinação em dia."
                )
                resultado_push = enviar_push_one_health(uf, push_titulo, push_msg)
                self.stdout.write(
                    f"  Push {uf}: {resultado_push.get('status')} "
                    f"({resultado_push.get('enviados', 0)}/{resultado_push.get('destinatarios', 0)} destinatários)"
                )

        self.stdout.write(self.style.SUCCESS(
            f"One Health: {criados} alerta(s) gerado(s) para {len(empresas_gov)} empresa(s) governo. "
            f"Disponível em /api/governo/noticias-epidemiologicas/"
        ))
