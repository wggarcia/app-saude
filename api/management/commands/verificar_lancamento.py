# -*- coding: utf-8 -*-
"""Verifica se a 1.0.30 está funcionando com gente de verdade.

Por que existe
--------------
Tudo o que foi testado antes do lançamento foi testado com casos que eu mesmo
escrevi. Isso prova que a máquina faz o que foi projetada para fazer — não
prova que funciona no uso real. Este comando responde quatro perguntas que só
o tráfego real pode responder:

1. As respostas novas estão CHEGANDO? Se a versão nova está na loja e ninguém
   responde as perguntas condicionais, alguma coisa quebrou entre app e API.
2. Elas estão MUDANDO alguma coisa? Dado que chega e não move o diferencial é
   pergunta inútil — atrito sem ganho.
3. A IA está respondendo? Ela é fail-open: quando falha, o registro fica só
   com o motor e ninguém percebe. Silêncio não é sinal de saúde.
4. Doença rara passou a aparecer demais? É o risco que o desenho tentou
   evitar; se o alarme falso apareceu, aparece aqui.

Uso:
    ./venv/bin/python manage.py verificar_lancamento
    ./venv/bin/python manage.py verificar_lancamento --dias 14
"""

from collections import Counter
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


# Campos abertos por porta — os que a 1.0.30 passou a enviar.
_DESEMPATE = [
    "febre_ciclica", "febre_bifasica", "tosse_mais_3_semanas", "tosse_paroxistica",
    "sudorese_noturna", "dispneia_subita_pos_febre", "dispneia_piora_deitado",
    "artralgia_simetrica", "artralgia_mais_2_semanas", "exantema_craniocaudal",
    "exantema_pruriginoso", "exantema_palmo_plantar", "exantema_apos_febre",
    "fezes_agua_arroz", "fezes_com_sangue", "febre_alta_prolongada",
    "urina_escura_fezes_claras", "dor_panturrilha", "barriga_inchada",
    "ulcera_indolor_bordas", "ulcera_mais_1_mes", "placa_na_garganta",
    "pescoco_inchado", "vesicula_dolorosa", "linfonodo_aumentado",
    "lesao_face_palmas", "vesiculas_estagios_variados", "mordedura_animal",
]


class Command(BaseCommand):
    help = "Confere se a versão nova do app está entregando o que prometeu."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=7)

    def handle(self, *args, **options):
        from api.models import RegistroSintoma
        from api.classificador_doencas import DOENCAS_SENTINELA

        dias = options["dias"]
        desde = timezone.now() - timedelta(days=dias)
        # using("owner"): sem contexto de tenant o papel restrito não enxerga
        # linha nenhuma sob RLS, e o relatório sairia zerado sem erro — o que
        # seria pior que falhar.
        qs = RegistroSintoma.objects.using("owner").filter(data_registro__gte=desde)
        total = qs.count()

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\nÚltimos %d dias — %d registros\n" % (dias, total)))
        if not total:
            self.stdout.write("Sem registros no período. Nada a verificar.")
            return

        # 1) De qual versão vêm
        versoes = Counter(
            (v or "(sem procedência)").strip()
            for v in qs.values_list("fonte_referencia", flat=True)
        )
        self.stdout.write("1) DE ONDE VEM")
        for v, n in versoes.most_common(6):
            self.stdout.write("     %-28s %5d  (%4.1f%%)" % (v, n, 100 * n / total))
        nova = sum(n for v, n in versoes.items() if "1.0.30" in v)
        if not nova:
            self.stdout.write(self.style.WARNING(
                "     Nenhum envio da 1.0.30 ainda — a loja pode não ter liberado."))

        # 2) As perguntas novas estão sendo respondidas
        respondidos = {
            c: qs.exclude(**{c + "__isnull": True}).count() for c in _DESEMPATE
        }
        com_alguma = sum(1 for c, n in respondidos.items() if n)
        total_respostas = sum(respondidos.values())
        self.stdout.write("\n2) AS PERGUNTAS NOVAS CHEGAM?")
        self.stdout.write("     campos que já receberam resposta: %d de %d"
                          % (com_alguma, len(_DESEMPATE)))
        self.stdout.write("     respostas no total: %d" % total_respostas)
        if total_respostas:
            for c, n in sorted(respondidos.items(), key=lambda x: -x[1])[:8]:
                if n:
                    self.stdout.write("       %-28s %5d" % (c, n))
        else:
            self.stdout.write(self.style.WARNING(
                "     NENHUMA resposta de desempate. Se já há envios da 1.0.30,"
                " alguma coisa quebrou entre o app e a API."))

        # 3) A IA está respondendo
        com_ia_qs = qs.exclude(hipotese_ia__isnull=True).exclude(hipotese_ia="")
        com_ia = com_ia_qs.count()
        # Dispensado E com hipótese ao mesmo tempo existe: o portão marcou o
        # registro antes de o dono ligar ANAMNESE_IA_SEMPRE. Subtrair os dois
        # dava "2 de 1 elegíveis (200%)" — relatório que mente não serve para
        # decidir nada. Elegível é quem NÃO foi dispensado e segue sem hipótese,
        # mais quem tem hipótese.
        dispensada = qs.filter(hipotese_ia_dispensada=True).exclude(
            pk__in=com_ia_qs.values("pk")).count()
        elegiveis = max(total - dispensada, com_ia)
        discorda = qs.filter(hipotese_ia_concorda=False).exclude(
            hipotese_ia__isnull=True).exclude(hipotese_ia="").count()
        self.stdout.write("\n3) A IA ESTÁ RESPONDENDO?")
        self.stdout.write("     com hipótese: %d de %d elegíveis (%s)" % (
            com_ia, elegiveis,
            ("%.0f%%" % (100 * com_ia / elegiveis)) if elegiveis else "—"))
        self.stdout.write("     discordou do motor: %d" % discorda)
        if elegiveis and com_ia / elegiveis < 0.8:
            self.stdout.write(self.style.ERROR(
                "     ALERTA: a IA está falhando em boa parte dos casos."
                " Ela é fail-open — o registro fica só com o motor e nada avisa."
                " Ver journalctl -u soluscrt-rqworker."))
        modelos = Counter(m for m in qs.values_list("hipotese_ia_modelo", flat=True) if m)
        for m, n in modelos.most_common(3):
            self.stdout.write("       %-24s %5d" % (m, n))

        # 4) Doença rara passou a aparecer demais
        classificacoes = Counter()
        for c in qs.values_list("classificacao", flat=True):
            if not c:
                continue
            # "Gripe (Influenza) (52% confiança) — vs COVID-19: ..."
            # O nome está ANTES do travessão; pegar o último pedaço trazia o
            # texto da comparação para a tabela, como se fosse diagnóstico.
            # E "URGÊNCIA: X — Doença (n%)" põe o nome depois do travessão.
            nome = c.strip()
            if nome.upper().startswith("URGÊNCIA"):
                nome = nome.split("—", 1)[-1]
            else:
                nome = nome.split("—", 1)[0]
            nome = nome.split("(")[0].strip() or "(sem nome)"
            classificacoes[nome] += 1
        self.stdout.write("\n4) O QUE O MOTOR ESTÁ DIZENDO")
        for nome, n in classificacoes.most_common(8):
            marca = "  ← sentinela" if nome in DOENCAS_SENTINELA else ""
            self.stdout.write("     %-28s %5d  (%4.1f%%)%s"
                              % (nome, n, 100 * n / total, marca))
        raras = sum(n for nome, n in classificacoes.items() if nome in DOENCAS_SENTINELA)
        if total and raras / total > 0.15:
            self.stdout.write(self.style.WARNING(
                "\n     ATENÇÃO: %.0f%% dos casos saíram como doença sentinela."
                " Acima de 15%% é sinal de alarme falso, não de surto —"
                " conferir antes de notificar." % (100 * raras / total)))

        # 5) O laço de aprendizado
        confirmados = qs.exclude(doenca_confirmada__isnull=True).exclude(
            doenca_confirmada="").count()
        self.stdout.write("\n5) DESFECHOS CONFIRMADOS (Fase 4)")
        self.stdout.write("     %d de %d" % (confirmados, total))
        if not confirmados:
            self.stdout.write(
                "     Ainda ninguém grava desfecho. Enquanto isso, não há como"
                " saber se o sistema acerta na vida real — só que ele funciona"
                " como foi projetado.")
        self.stdout.write("")
