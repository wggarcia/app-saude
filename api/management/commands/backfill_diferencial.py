"""Preenche RegistroSintoma.diferencial nos registros anteriores à migração 0269.

Por que é preciso: o campo `diferencial` nasceu vazio. Enquanto um foco não tem
nenhum caso com diferencial gravado, o mapa cai no cálculo antigo — o que soma
taxas de sintoma sem olhar a anamnese e faz, por exemplo, Malária ranquear num
bairro do Rio cujos casos negaram viagem a área endêmica.

O que este comando faz: roda o MESMO classificador sobre os sintomas que cada
registro já guarda e grava o diferencial resultante. Não inventa dado, não
promove doença nenhuma, não altera `grupo` nem `classificacao` — só preenche um
campo que estava vazio.

Seguro por padrão: sem --aplicar, apenas simula e mostra o que faria.
Reversível: para desfazer, basta voltar o campo para NULL.
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Recalcula e grava o diferencial dos registros que estão sem ele (migração 0269)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Grava de verdade. Sem esta flag, só simula.",
        )
        parser.add_argument(
            "--limite",
            type=int,
            default=0,
            help="Processa no máximo N registros (0 = todos).",
        )
        parser.add_argument(
            "--empresa-id",
            type=int,
            default=None,
            help="Restringe a uma empresa (ex.: 47 = app público).",
        )

    def handle(self, *args, **options):
        from api.models import RegistroSintoma
        from api.views import classificar_padrao_completo
        from api.classificador_doencas import sintomas_do_registro

        aplicar = options["aplicar"]
        limite = options["limite"]
        empresa_id = options["empresa_id"]

        qs = RegistroSintoma.objects.using("owner").filter(diferencial__isnull=True)
        if empresa_id:
            qs = qs.filter(empresa_id=empresa_id)
        qs = qs.order_by("-data_registro")

        total = qs.count()
        if limite:
            qs = qs[:limite]

        self.stdout.write(f"Registros sem diferencial: {total}")
        if limite:
            self.stdout.write(f"Processando no máximo {limite}.")
        if not aplicar:
            self.stdout.write(self.style.WARNING("MODO SIMULAÇÃO — nada será gravado (use --aplicar)."))

        processados = 0
        gravados = 0
        vazios = 0
        amostra = []

        for registro in qs.iterator(chunk_size=500):
            processados += 1
            try:
                dados = sintomas_do_registro(registro)
                _grupo, _classificacao, ranking = classificar_padrao_completo(dados, setor="governo")
            except Exception as exc:  # um registro ruim não pode parar o lote
                self.stderr.write(f"  registro {registro.pk}: falhou ({exc})")
                continue

            if not ranking:
                vazios += 1
                continue

            if len(amostra) < 3:
                amostra.append((registro.pk, [r["doenca"] for r in ranking[:3]]))

            if aplicar:
                RegistroSintoma.objects.using("owner").filter(pk=registro.pk).update(diferencial=ranking)
            gravados += 1

            if processados % 500 == 0:
                self.stdout.write(f"  ... {processados} processados")

        self.stdout.write("")
        self.stdout.write("Amostra do diferencial calculado:")
        for pk, doencas in amostra:
            self.stdout.write(f"  registro {pk}: {' > '.join(doencas)}")

        self.stdout.write("")
        self.stdout.write(f"processados: {processados} | com diferencial: {gravados} | sem ranking: {vazios}")

        if aplicar:
            # O panorama é cacheado — sem isto o mapa só mudaria quando o cache expirasse.
            try:
                from api.epidemiologia import clear_panorama_cache
                clear_panorama_cache()
                self.stdout.write("cache do panorama limpo")
            except Exception as exc:
                self.stderr.write(f"não consegui limpar o cache do panorama: {exc}")
            self.stdout.write(self.style.SUCCESS("Backfill aplicado."))
        else:
            self.stdout.write(self.style.WARNING("Nada gravado (simulação). Rode com --aplicar para valer."))
