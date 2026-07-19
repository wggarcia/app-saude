from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "Diagnostica o estado do mapa epidemiológico público"

    def add_arguments(self, parser):
        parser.add_argument(
            "--device",
            type=str,
            default="",
            help="device_id para verificar limite de 7 dias",
        )

    def handle(self, *args, **options):
        from api.models import Empresa, RegistroSintoma
        from api.epidemiologia import PUBLIC_APP_EMAIL, _public_population_empresa

        self.stdout.write("=" * 60)
        self.stdout.write("DIAGNÓSTICO DO MAPA EPIDEMIOLÓGICO")
        self.stdout.write("=" * 60)

        # 1. Verifica empresa via owner
        self.stdout.write("\n[1] Empresa pública via conexão 'owner':")
        try:
            e_owner = Empresa.objects.using("owner").filter(email=PUBLIC_APP_EMAIL).first()
            if e_owner:
                self.stdout.write(self.style.SUCCESS(f"  OK  → id={e_owner.pk}, nome='{e_owner.nome}'"))
            else:
                self.stdout.write(self.style.ERROR(f"  FALHOU → empresa '{PUBLIC_APP_EMAIL}' não encontrada via 'owner'"))
        except Exception as ex:
            self.stdout.write(self.style.ERROR(f"  ERRO → {ex}"))
            e_owner = None

        # 2. Verifica empresa via default
        self.stdout.write("\n[2] Empresa pública via conexão 'default':")
        try:
            e_default = Empresa.objects.filter(email=PUBLIC_APP_EMAIL).first()
            if e_default:
                self.stdout.write(self.style.SUCCESS(f"  OK  → id={e_default.pk}, nome='{e_default.nome}'"))
            else:
                self.stdout.write(self.style.ERROR(f"  FALHOU → empresa não encontrada via 'default'"))
        except Exception as ex:
            self.stdout.write(self.style.ERROR(f"  ERRO → {ex}"))
            e_default = None

        empresa = e_owner or e_default

        # 3. Conta registros (tenta owner, cai para default se sem permissão)
        self.stdout.write("\n[3] Contagem de RegistroSintoma:")
        agora = timezone.now()
        for db_alias in ("owner", "default"):
            try:
                total = RegistroSintoma.objects.using(db_alias).count()
                self.stdout.write(f"  Total ({db_alias}): {total}")
                if empresa:
                    count_empresa = RegistroSintoma.objects.using(db_alias).filter(empresa=empresa).count()
                    self.stdout.write(f"  Para empresa pública ({db_alias}): {count_empresa}")
                break
            except Exception as ex:
                self.stdout.write(self.style.WARNING(f"  sem permissão via '{db_alias}': {ex}"))

        # 4. Registros por janela de tempo
        self.stdout.write("\n[4] Registros por janela de tempo:")
        for db_alias in ("owner", "default"):
            try:
                for label, delta in [("24h", timedelta(hours=24)), ("7d", timedelta(days=7)), ("30d", timedelta(days=30))]:
                    n = RegistroSintoma.objects.using(db_alias).filter(
                        data_registro__gte=agora - delta
                    ).count()
                    self.stdout.write(f"  últimas {label} ({db_alias}): {n}")
                break
            except Exception:
                pass

        # 5. Últimos 3 registros
        self.stdout.write("\n[5] Últimos 3 registros:")
        for db_alias in ("owner", "default"):
            try:
                ultimos = RegistroSintoma.objects.using(db_alias).order_by("-data_registro")[:3]
                for r in ultimos:
                    self.stdout.write(
                        f"  id={r.id_anonimo} | {r.data_registro:%d/%m %H:%M} | "
                        f"bairro='{r.bairro}' cidade='{r.cidade}' estado='{r.estado}' | "
                        f"lat={r.latitude} lon={r.longitude} | "
                        f"device='{(r.device_id or 'N/A')[:16]}...'"
                    )
                break
            except Exception as ex:
                self.stdout.write(self.style.WARNING(f"  sem permissão via '{db_alias}': {ex}"))

        # 6. Verifica função de cache
        self.stdout.write("\n[6] _public_population_empresa() (cache em memória):")
        try:
            emp_cached = _public_population_empresa()
            if emp_cached:
                self.stdout.write(self.style.SUCCESS(f"  OK  → id={emp_cached.pk}"))
            else:
                self.stdout.write(self.style.ERROR("  RETORNOU None — mapa fica vazio!"))
                self.stdout.write("  → Execute: python manage.py reset_empresa_cache")
        except Exception as ex:
            self.stdout.write(self.style.ERROR(f"  ERRO: {ex}"))

        # 7. Verifica rate limit por device_id (se passado)
        device_id = (options.get("device") or "").strip()
        if device_id and empresa:
            self.stdout.write(f"\n[7] Rate limit para device '{device_id[:20]}...':")
            janela = agora - timedelta(days=7)
            try:
                bloqueado = RegistroSintoma.objects.using("owner").filter(
                    empresa=empresa,
                    device_id=device_id,
                    data_registro__gte=janela,
                ).exists()
                if bloqueado:
                    self.stdout.write(self.style.WARNING(
                        "  BLOQUEADO → já enviou nos últimos 7 dias (ja_considerado)"
                    ))
                    self.stdout.write(
                        "  → Para resetar: python manage.py reset_sintoma_teste --device=" + device_id
                    )
                else:
                    self.stdout.write(self.style.SUCCESS("  LIVRE → pode enviar"))
            except Exception as ex:
                self.stdout.write(self.style.ERROR(f"  ERRO: {ex}"))

        self.stdout.write("\n" + "=" * 60)
