"""seed_opme_previsibilidade_demo — histórico de consumo de OPME para a demo.

A Previsibilidade de Consumo (2ª métrica de sucesso da Unimed) precisa de vários
meses de série para mostrar o que o motor faz. O tenant de demonstração tinha só
~12 pedidos em 3 meses, o que faz o motor (corretamente) reportar previsibilidade
baixa — honesto, mas fraco para o Pit Day.

Este comando popula 12 meses de consumo por procedimento/especialidade no tenant
de DEMONSTRAÇÃO (nunca num cliente real), com padrões realistas:
  - Quadril: série crescente  → tendência 'alta' + alerta de compra antecipada;
  - Coluna:  série estável    → alta previsibilidade.

É idempotente e reversível: todos os pacientes recebem o prefixo [DEMO-PREV];
rodar de novo (ou com --clear) apaga o lote anterior antes de recriar. Exige
--apply para escrever (por padrão só mostra o que faria) e um alvo explícito.

Uso:
  python manage.py seed_opme_previsibilidade_demo                      # preview
  python manage.py seed_opme_previsibilidade_demo --apply              # aplica
  python manage.py seed_opme_previsibilidade_demo --apply --clear      # só limpa
  python manage.py seed_opme_previsibilidade_demo --apply --email demo.hospital@soluscrt.com
"""
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

TAG = "[DEMO-PREV]"
EMAIL_PADRAO = "demo.hospital@soluscrt.com"

# Séries mensais (12 meses, do mais ANTIGO ao mais RECENTE) = nº de pedidos no mês.
PADROES = [
    {
        "chave": "quadril",
        "tuss": "30729068",
        "opme": "Prótese Total de Quadril Não Cimentada — Linha Standard",
        "especialidade": "Ortopedia — Quadril",
        # crescimento acelerado → tendência 'alta' (calibrado no motor real:
        # tend=alta, previsibilidade≈41 ≥ limiar do alerta de compra antecipada).
        "serie": [3, 3, 3, 4, 4, 5, 6, 7, 9, 11, 13, 16],
    },
    {
        "chave": "coluna",
        "tuss": "30715016",
        "opme": "Sistema de Fixação Pedicular Titânio — 4 parafusos",
        "especialidade": "Coluna",
        "serie": [4, 5, 4, 5, 5, 4, 5, 5, 4, 5, 5, 5],     # estável
    },
]


def _primeiro_dia_meses_atras(n):
    """Retorna a lista de (ano, mes) dos últimos n meses, do mais antigo ao atual."""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    seq = []
    for _ in range(n):
        seq.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    seq.reverse()
    return seq


class Command(BaseCommand):
    help = "Popula histórico de consumo OPME (12 meses) no tenant de demonstração."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Escreve de verdade (sem isto, só mostra o preview).")
        parser.add_argument("--clear", action="store_true",
                            help="Apenas remove o lote [DEMO-PREV] e sai.")
        parser.add_argument("--email", default=EMAIL_PADRAO,
                            help=f"E-mail do tenant demo (padrão: {EMAIL_PADRAO}).")
        parser.add_argument("--empresa-id", type=int, default=None,
                            help="Alvo por id (tem prioridade sobre --email).")

    def handle(self, *args, **opts):
        from api.models import (Empresa, CatalogoOPME, OPMEProcedimento,
                                AutorizacaoOPME, ItemAutorizacaoOPME)

        # ── Alvo explícito e validado (nunca roda no escuro) ────────────────────
        if opts["empresa_id"]:
            empresa = Empresa.objects.filter(id=opts["empresa_id"]).first()
        else:
            empresa = Empresa.objects.filter(email=opts["email"]).first()
        if not empresa:
            raise CommandError("Tenant de demonstração não encontrado — verifique --email/--empresa-id.")
        # Trava de segurança: só age em conta claramente de demonstração.
        if "demo" not in (empresa.email or "").lower():
            raise CommandError(
                f"'{empresa.email}' não parece uma conta de demonstração. Abortando "
                "para não escrever dados fabricados num tenant real.")

        self.stdout.write(f"Tenant alvo: #{empresa.id} {empresa.email} ({empresa.nome})")

        # ── Limpeza do lote anterior (idempotência) ─────────────────────────────
        antigos = AutorizacaoOPME.objects.filter(
            empresa=empresa, paciente_nome__startswith=TAG)
        n_antigos = antigos.count()
        self.stdout.write(f"Lote [DEMO-PREV] existente: {n_antigos} pedido(s).")

        if opts["clear"]:
            if opts["apply"]:
                antigos.delete()
                self.stdout.write(self.style.SUCCESS(f"Removidos {n_antigos} pedido(s). Fim (--clear)."))
            else:
                self.stdout.write("[preview] removeria o lote acima. Use --apply.")
            return

        # ── Resolve catálogo + procedimentos ────────────────────────────────────
        plano = []
        for p in PADROES:
            opme = CatalogoOPME.objects.filter(
                empresa=empresa, descricao=p["opme"]).first()
            if not opme:
                raise CommandError(
                    f"Catálogo não tem '{p['opme']}' no tenant demo — rode o seed base primeiro.")
            proc = OPMEProcedimento.objects.filter(
                empresa=empresa, codigo_tuss=p["tuss"]).first()
            total = sum(p["serie"])
            plano.append((p, opme, proc, total))
            self.stdout.write(
                f"  • {p['chave']}: {total} pedidos em 12 meses · {p['opme']} · esp='{p['especialidade']}'"
                + ("" if proc else "  (procedimento ausente — especialidade não será setada)"))

        if not opts["apply"]:
            self.stdout.write("[preview] nada foi escrito. Use --apply para aplicar.")
            return

        # ── Aplica ──────────────────────────────────────────────────────────────
        with transaction.atomic():
            antigos.delete()   # recria do zero → idempotente
            meses = _primeiro_dia_meses_atras(12)
            criados = 0
            for p, opme, proc, _total in plano:
                # especialidade no procedimento faz a dimensão 'especialidade' funcionar
                if proc and proc.especialidade != p["especialidade"]:
                    proc.especialidade = p["especialidade"]
                    proc.save(update_fields=["especialidade"])
                seq = 0
                for (ano, mes), qtd_mes in zip(meses, p["serie"]):
                    for _ in range(qtd_mes):
                        seq += 1
                        dia = 5 + (seq % 20)   # espalha dentro do mês
                        quando = timezone.make_aware(datetime(ano, mes, dia, 10, 0))
                        aut = AutorizacaoOPME.objects.create(
                            empresa=empresa,
                            paciente_nome=f"{TAG} Paciente {p['chave']}-{ano}{mes:02d}-{seq}",
                            medico_solicitante="Dr. Demonstração",
                            procedimento_tuss=p["tuss"],
                            status="aprovada",
                            numero_protocolo="",
                            validade_ate=(quando.date() + timedelta(days=90)),
                        )
                        aut.numero_protocolo = f"OPME-{ano}-{aut.pk:06d}"
                        # backdate: solicitado_em é auto_now_add → só via update()
                        AutorizacaoOPME.objects.filter(pk=aut.pk).update(
                            solicitado_em=quando, numero_protocolo=aut.numero_protocolo)
                        ItemAutorizacaoOPME.objects.create(
                            autorizacao=aut, opme=opme, quantidade=1,
                            quantidade_aprovada=1, status="aprovado",
                            preco_solicitado=opme.preco_maximo)
                        criados += 1

        self.stdout.write(self.style.SUCCESS(
            f"OK — {criados} pedido(s) [DEMO-PREV] criados em 12 meses. "
            f"Reversível: rode com --apply --clear para remover."))
