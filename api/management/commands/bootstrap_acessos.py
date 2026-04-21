import os

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand

from api.models import DonoSaaS, Empresa
from api.planos import detalhes_pacote, pacote_governo_padrao, pacote_padrao, normalizar_codigo_pacote


def _env(name, default=""):
    return os.environ.get(name, default).strip()


class Command(BaseCommand):
    help = "Cria acessos iniciais de produção usando variáveis de ambiente seguras."

    def handle(self, *args, **options):
        reset_passwords = _env("SOLUSCRT_BOOTSTRAP_RESET_PASSWORDS", "false").lower() == "true"
        criados = []
        atualizados = []
        ignorados = []

        self._bootstrap_empresa(
            env_prefix="SOLUSCRT_BOOTSTRAP_EMPRESA",
            tipo_conta=Empresa.TIPO_EMPRESA,
            acesso_governo=False,
            reset_passwords=reset_passwords,
            criados=criados,
            atualizados=atualizados,
            ignorados=ignorados,
        )
        self._bootstrap_empresa(
            env_prefix="SOLUSCRT_BOOTSTRAP_GOVERNO",
            tipo_conta=Empresa.TIPO_GOVERNO,
            acesso_governo=True,
            reset_passwords=reset_passwords,
            criados=criados,
            atualizados=atualizados,
            ignorados=ignorados,
        )
        self._bootstrap_dono(
            reset_passwords=reset_passwords,
            criados=criados,
            atualizados=atualizados,
            ignorados=ignorados,
        )

        if criados:
            self.stdout.write(self.style.SUCCESS("Acessos criados: " + ", ".join(criados)))
        if atualizados:
            self.stdout.write(self.style.SUCCESS("Acessos atualizados: " + ", ".join(atualizados)))
        if ignorados:
            self.stdout.write("Bootstrap ignorado: " + ", ".join(ignorados))
        if not criados and not atualizados and not ignorados:
            self.stdout.write("Nenhum bootstrap configurado.")

    def _bootstrap_empresa(self, env_prefix, tipo_conta, acesso_governo, reset_passwords, criados, atualizados, ignorados):
        email = _env(f"{env_prefix}_EMAIL").lower()
        senha = _env(f"{env_prefix}_PASSWORD")
        nome = _env(f"{env_prefix}_NOME", "SolusCRT")
        pacote_codigo = normalizar_codigo_pacote(
            _env(f"{env_prefix}_PACOTE", pacote_governo_padrao() if acesso_governo else pacote_padrao())
        )

        if not email or not senha:
            ignorados.append(f"{env_prefix}: email/senha ausentes")
            return

        pacote = detalhes_pacote(pacote_codigo)
        empresa, created = Empresa.objects.get_or_create(
            email=email,
            defaults={
                "nome": nome,
                "senha": make_password(senha),
                "ativo": True,
                "tipo_conta": tipo_conta,
                "acesso_governo": acesso_governo,
                "pacote_codigo": pacote_codigo,
                "plano": "anual" if acesso_governo else "mensal",
                "max_dispositivos": pacote["dispositivos"],
                "max_usuarios": pacote["usuarios"],
            },
        )

        update_fields = []
        for field, value in {
            "nome": nome,
            "ativo": True,
            "tipo_conta": tipo_conta,
            "acesso_governo": acesso_governo,
            "pacote_codigo": pacote_codigo,
            "plano": "anual" if acesso_governo else (empresa.plano or "mensal"),
            "max_dispositivos": pacote["dispositivos"],
            "max_usuarios": pacote["usuarios"],
            "sessao_ativa_chave": None,
            "sessao_ativa_device_id": None,
            "sessao_ativa_em": None,
        }.items():
            if getattr(empresa, field) != value:
                setattr(empresa, field, value)
                update_fields.append(field)

        if reset_passwords and not created:
            empresa.senha = make_password(senha)
            update_fields.append("senha")

        if update_fields:
            empresa.save(update_fields=sorted(set(update_fields)))

        (criados if created else atualizados).append(email)

    def _bootstrap_dono(self, reset_passwords, criados, atualizados, ignorados):
        email = _env("SOLUSCRT_BOOTSTRAP_OWNER_EMAIL").lower()
        senha = _env("SOLUSCRT_BOOTSTRAP_OWNER_PASSWORD")
        nome = _env("SOLUSCRT_BOOTSTRAP_OWNER_NOME", "Operacao SolusCRT")

        if not email or not senha:
            ignorados.append("SOLUSCRT_BOOTSTRAP_OWNER: email/senha ausentes")
            return

        dono, created = DonoSaaS.objects.get_or_create(
            email=email,
            defaults={
                "nome": nome,
                "senha": make_password(senha),
                "ativo": True,
            },
        )

        update_fields = []
        for field, value in {
            "nome": nome,
            "ativo": True,
            "sessao_ativa_chave": None,
            "sessao_ativa_em": None,
        }.items():
            if getattr(dono, field) != value:
                setattr(dono, field, value)
                update_fields.append(field)

        if reset_passwords and not created:
            dono.senha = make_password(senha)
            update_fields.append("senha")

        if update_fields:
            dono.save(update_fields=sorted(set(update_fields)))

        (criados if created else atualizados).append(email)
