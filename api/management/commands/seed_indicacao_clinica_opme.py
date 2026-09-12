"""
CAMADA 1 · Base de indicação clínica (fonte A: diretrizes públicas).

Popula a tabela NACIONAL IndicacaoClinicaOPME (sem empresa, legível por todos)
com um conjunto inicial de indicações CID x procedimento, curado de diretrizes
das sociedades médicas. Cobre o foco da Unimed (Coluna e Buco Maxilo) + os
procedimentos do cenário de demonstração (Quadril).

É um PONTO DE PARTIDA — quando a Unimed definir a fonte oficial (as regras de
cobertura deles, fonte B), essas regras entram como override por operadora.

Idempotente (update_or_create por procedimento_tuss + cid10_prefixo).
Rodar:  python manage.py seed_indicacao_clinica_opme
        python manage.py seed_indicacao_clinica_opme --dry-run
"""
from django.core.management.base import BaseCommand

from api.models import IndicacaoClinicaOPME

# (procedimento_tuss, procedimento_descricao, especialidade, cid10_prefixo,
#  nivel, criterio, fonte)
INDICACOES = [
    # ── Quadril — artroplastia total (procedimento do cenário demo) ──────────
    ("30729068", "Artroplastia total de quadril", "Ortopedia — Quadril",
     "M16", "indicado", "", "Diretriz SBOT — coxartrose"),
    ("30729068", "Artroplastia total de quadril", "Ortopedia — Quadril",
     "S72.0", "indicado", "", "Fratura do colo do fêmur"),
    ("30729068", "Artroplastia total de quadril", "Ortopedia — Quadril",
     "M87", "indicado", "", "Osteonecrose da cabeça femoral"),
    ("30729068", "Artroplastia total de quadril", "Ortopedia — Quadril",
     "M54.5", "nao_indicado",
     "Lombalgia isolada não sustenta artroplastia de quadril", "Diretriz SBOT"),

    # ── Coluna — artrodese toracolombar (foco Unimed + demo) ─────────────────
    ("30715016", "Artrodese toracolombar via posterior", "Coluna",
     "M43.1", "indicado", "", "Espondilolistese com instabilidade"),
    ("30715016", "Artrodese toracolombar via posterior", "Coluna",
     "S22", "indicado", "", "Fratura de coluna torácica"),
    ("30715016", "Artrodese toracolombar via posterior", "Coluna",
     "S32", "indicado", "", "Fratura de coluna lombar"),
    ("30715016", "Artrodese toracolombar via posterior", "Coluna",
     "M48.0", "condicional",
     "após falha do tratamento conservador documentada", "Diretriz SBC — estenose"),
    ("30715016", "Artrodese toracolombar via posterior", "Coluna",
     "M51", "condicional",
     "após falha do tratamento conservador (≥ 6 semanas)", "Diretriz SBC — hérnia discal"),
    ("30715016", "Artrodese toracolombar via posterior", "Coluna",
     "M54.5", "nao_indicado",
     "lombalgia inespecífica não é indicação de artrodese", "Diretriz SBC"),

    # ── Buco Maxilo — osteossíntese de fratura (foco Unimed + demo) ──────────
    ("30401018", "Osteossíntese de fratura buco-maxilo-facial", "Buco Maxilo",
     "S02", "indicado", "", "Fratura de ossos da face"),
    ("30401018", "Osteossíntese de fratura buco-maxilo-facial", "Buco Maxilo",
     "S02.6", "indicado", "", "Fratura de mandíbula"),
]


class Command(BaseCommand):
    help = "Popula a base nacional de indicação clínica OPME (Camada 1, fonte A)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Mostra o que faria sem gravar.")

    def handle(self, *args, **opts):
        criadas = atualizadas = 0
        for (tuss, desc, esp, cid, nivel, criterio, fonte) in INDICACOES:
            if opts["dry_run"]:
                self.stdout.write(f"  [dry-run] {tuss} × {cid} → {nivel}")
                continue
            _obj, created = IndicacaoClinicaOPME.objects.update_or_create(
                procedimento_tuss=tuss, cid10_prefixo=cid,
                defaults=dict(procedimento_descricao=desc, especialidade=esp,
                              nivel=nivel, criterio=criterio, fonte=fonte, ativo=True),
            )
            criadas += int(created)
            atualizadas += int(not created)
        if opts["dry_run"]:
            self.stdout.write(self.style.WARNING(f"Dry-run — {len(INDICACOES)} regras."))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Base de indicação: {criadas} criadas, {atualizadas} atualizadas "
            f"({IndicacaoClinicaOPME.objects.count()} no total)."))
