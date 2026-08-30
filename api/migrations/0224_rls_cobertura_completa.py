"""
Cobertura completa de RLS — DESACOPLADA em management command.

Aplicar RLS a ~148 tabelas em produção sem validar antes num Postgres de
homologação é arriscado (RLS mal-aplicada pode esconder linhas). Por isso a
LÓGICA foi movida para o management command idempotente:

    python manage.py aplicar_rls_cobertura --dry-run   # lista o que faria
    python manage.py aplicar_rls_cobertura             # aplica (só Postgres)

Esta migration é um MARCO no-op — mantém a cadeia intacta sem tocar no banco.
Rode o command depois de validar em homologação. Ver o command para o pattern
(replica a 0085: ENABLE + policy tenant_isolation por empresa_id).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0223_cifra_certificados_pfx'),
    ]

    operations = []
