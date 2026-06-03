"""Provisiona as credenciais do APP do trabalhador para a conta demo SST.

Por que uma data migration?
--------------------------
A revisão da App Store (Guideline 2.1) exige que os avaliadores consigam
logar no app com luiz@app.local / carlos@app.local. As tentativas anteriores
de provisionar essas contas via `preDeployCommand`/`startCommand` do
render.yaml não surtiram efeito porque ambos são CONFIGURAÇÕES DO BLUEPRINT
do Render: só passam a valer após um "sync" manual no painel. Um deploy
comum continua executando a config antiga armazenada no serviço.

`manage.py migrate`, por outro lado, roda de forma garantida em produção
(faz parte do preDeployCommand vigente e é pré-requisito do schema). Logo,
embarcar o provisionamento como migração de dados é o caminho confiável e
independente de sync do Blueprint.

É idempotente e nunca levanta exceção (não pode quebrar o deploy): trata
explicitamente os conflitos do vínculo OneToOne funcionário↔credencial.
"""
from django.db import migrations
from django.contrib.auth.hashers import make_password


EMPRESA_DEMO_EMAIL = "demo.sst@soluscrt.com"

# (cpf, nome, cargo, setor, email_app, senha_app)
TRABALHADORES = [
    ("111.222.333-44", "Luiz Oliveira",       "Técnico de Segurança do Trabalho", "Produção",
     "luiz@app.local",   "Luiz@2026"),
    ("333.444.555-66", "Carlos Alberto Lima",  "Operador de Produção",            "Produção",
     "carlos@app.local", "Carlos@2026"),
]


def _provisiona(apps, schema_editor):
    Empresa = apps.get_model("api", "Empresa")
    FuncionarioSST = apps.get_model("api", "FuncionarioSST")
    CredencialAppFuncionario = apps.get_model("api", "CredencialAppFuncionario")

    empresa = Empresa.objects.filter(email=EMPRESA_DEMO_EMAIL).first()
    if not empresa:
        # Empresa demo ainda não existe neste banco — nada a fazer.
        return

    for cpf, nome, cargo, setor, email_app, senha_app in TRABALHADORES:
        try:
            func = FuncionarioSST.objects.filter(empresa=empresa, cpf=cpf).first()
            if not func:
                func = FuncionarioSST.objects.filter(empresa=empresa, nome=nome).first()
            if not func:
                func = FuncionarioSST.objects.create(
                    empresa=empresa, ativo=True, nome=nome, cpf=cpf,
                    cargo=cargo, setor=setor,
                )
            elif not func.ativo:
                func.ativo = True
                func.save(update_fields=["ativo"])

            cred_por_email = CredencialAppFuncionario.objects.filter(email=email_app).first()
            cred_do_func = CredencialAppFuncionario.objects.filter(funcionario=func).first()

            if cred_por_email and cred_do_func and cred_por_email.pk != cred_do_func.pk:
                cred_do_func.delete()
                cred = cred_por_email
                cred.funcionario = func
            elif cred_por_email:
                cred = cred_por_email
                cred.funcionario = func
            elif cred_do_func:
                cred = cred_do_func
                cred.email = email_app
            else:
                cred = CredencialAppFuncionario(funcionario=func, email=email_app)

            cred.senha = make_password(senha_app)
            cred.ativo = True
            cred.save()
        except Exception:  # noqa: BLE001 — nunca quebrar o deploy
            continue


def _noop(apps, schema_editor):
    # Não removemos credenciais demo no rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0091_registrosintoma_regsintoma_emp_data_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(_provisiona, _noop),
    ]
