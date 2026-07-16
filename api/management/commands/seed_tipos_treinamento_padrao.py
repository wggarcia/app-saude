from django.core.management.base import BaseCommand

from api.models import Empresa, TipoTreinamentoNR

CATALOGO_PADRAO = [
    {"nr": "NR-35", "categoria": "", "nome": "NR-35 Básico — Trabalho em Altura", "carga_horaria_padrao": 8, "periodicidade_dias": 730},
    {"nr": "NR-33", "categoria": "", "nome": "NR-33 — Trabalhador Autorizado (Espaços Confinados)", "carga_horaria_padrao": 16, "periodicidade_dias": 365},
    {"nr": "NR-10", "categoria": "", "nome": "NR-10 Básico — Segurança em Eletricidade", "carga_horaria_padrao": 40, "periodicidade_dias": 730},
    {"nr": "NR-12", "categoria": "", "nome": "NR-12 — Capacitação em Máquinas e Equipamentos", "carga_horaria_padrao": 8, "periodicidade_dias": 730},
    {"nr": "NR-20", "categoria": "", "nome": "NR-20 — Inflamáveis e Combustíveis (Intermediário)", "carga_horaria_padrao": 8, "periodicidade_dias": 1095},
    {"nr": "NR-6", "categoria": "", "nome": "NR-6 — Uso Correto de EPI", "carga_horaria_padrao": 4, "periodicidade_dias": 365},
    {"nr": "NR-5", "categoria": "", "nome": "NR-5 — CIPA", "carga_horaria_padrao": 20, "periodicidade_dias": 365},
    {"nr": "NR-11", "categoria": "", "nome": "NR-11 — Operador de Empilhadeira", "carga_horaria_padrao": 16, "periodicidade_dias": 730},
    {"nr": "NR-23", "categoria": "", "nome": "NR-23 — Brigada de Incêndio", "carga_horaria_padrao": 16, "periodicidade_dias": 365},
    {"nr": "NR-17", "categoria": "", "nome": "NR-17 — Ergonomia", "carga_horaria_padrao": 4, "periodicidade_dias": 730},
    {"nr": "", "categoria": "Onboarding", "nome": "Integração de Novos Funcionários", "carga_horaria_padrao": 4, "periodicidade_dias": None},
    {"nr": "", "categoria": "Liderança", "nome": "Treinamento de Liderança", "carga_horaria_padrao": 8, "periodicidade_dias": None},
    {"nr": "", "categoria": "Produto", "nome": "Treinamento de Produto / Processo", "carga_horaria_padrao": 4, "periodicidade_dias": None},
]


class Command(BaseCommand):
    help = (
        "Cria um catálogo padrão de Tipos de Treinamento (NRs mais comuns + categorias gerais) "
        "para empresas que ainda não têm nenhum tipo cadastrado — deixa o seletor 'Tipo de "
        "Treinamento (catálogo)' já utilizável sem exigir cadastro manual prévio. Idempotente: "
        "não duplica em empresas que já têm catálogo próprio."
    )

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, default=None, help="Aplica só a uma empresa específica.")

    def handle(self, *args, **options):
        empresa_id = options.get("empresa_id")
        empresas = Empresa.objects.using("owner").all()
        if empresa_id:
            empresas = empresas.filter(id=empresa_id)

        total_empresas = 0
        total_criados = 0
        for empresa in empresas:
            if TipoTreinamentoNR.objects.using("owner").filter(empresa=empresa).exists():
                continue
            criados_aqui = 0
            for item in CATALOGO_PADRAO:
                TipoTreinamentoNR.objects.using("owner").create(empresa=empresa, **item)
                criados_aqui += 1
            if criados_aqui:
                total_empresas += 1
                total_criados += criados_aqui
                self.stdout.write(f"Empresa {empresa.id} ({empresa.nome}): {criados_aqui} tipos criados.")

        self.stdout.write(self.style.SUCCESS(
            f"Concluído: {total_criados} tipos criados em {total_empresas} empresa(s)."
        ))
