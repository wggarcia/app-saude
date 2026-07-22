from django.db import migrations, models
import django.db.models.deletion

# IF NOT EXISTS para todos os objetos — idempotente em qualquer estado de DB.
# Cenário real: tabela existe no banco mas 0155 sumiu de django_migrations
# (restore parcial de backup). A migration re-confirma o estado sem falhar.
_CREATE_IDENTIDADE = """
CREATE TABLE IF NOT EXISTS "api_identidadepaciente" (
    "id"               bigserial    NOT NULL PRIMARY KEY,
    "nome"             varchar(200) NOT NULL,
    "cpf"              varchar(11)  NOT NULL DEFAULT '',
    "cns"              varchar(18)  NOT NULL DEFAULT '',
    "data_nascimento"  date         NULL,
    "criado_em"        timestamptz  NOT NULL,
    "atualizado_em"    timestamptz  NOT NULL,
    "empresa_id"       bigint       NOT NULL
        REFERENCES "api_empresa" ("id") DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS "idx_identpac_empresa_cpf"
    ON "api_identidadepaciente" ("empresa_id", "cpf");
CREATE INDEX IF NOT EXISTS "idx_identpac_empresa_nome"
    ON "api_identidadepaciente" ("empresa_id", "nome");
"""

_DROP_IDENTIDADE = 'DROP TABLE IF EXISTS "api_identidadepaciente" CASCADE;'


def _add_fk_column_sql(table, column):
    """SQL idempotente: adiciona coluna FK e constraint somente se ausentes."""
    return f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = '{table}'
          AND column_name  = '{column}'
    ) THEN
        ALTER TABLE "{table}" ADD COLUMN "{column}" bigint NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a
            ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.conrelid = '{table}'::regclass
          AND c.contype  = 'f'
          AND a.attname  = '{column}'
    ) THEN
        ALTER TABLE "{table}"
        ADD FOREIGN KEY ("{column}")
        REFERENCES "api_identidadepaciente" ("id")
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;
"""


class Migration(migrations.Migration):
    """MPI leve do segmento Hospital (Fase 0 + Fase 1 da convergência de
    identidade de paciente) — cria o hub IdentidadePaciente e liga
    PacienteInternado (Moderna) e ProntuarioHospitalar (EMR) a ele.

    Puramente aditivo: colunas novas, todas nullable, nenhuma constraint
    NOT NULL/UNIQUE. Dados existentes continuam válidos sem backfill —
    o backfill roda na migração seguinte (0156).

    Operações de banco são idempotentes (IF NOT EXISTS / DO blocks) para
    tolerar estado de DB onde a tabela já existe mas a migração sumiu de
    django_migrations (ex: restore parcial de backup)."""

    dependencies = [
        ('api', '0154_atendimentoubs_assinatura'),
    ]

    operations = [
        # --- IdentidadePaciente ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_CREATE_IDENTIDADE,
                    reverse_sql=_DROP_IDENTIDADE,
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='IdentidadePaciente',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nome', models.CharField(max_length=200)),
                        ('cpf', models.CharField(
                            blank=True, default='',
                            help_text='Somente dígitos — normalizado via cpf_digitos()',
                            max_length=11,
                        )),
                        ('cns', models.CharField(blank=True, default='', max_length=18, verbose_name='CNS')),
                        ('data_nascimento', models.DateField(blank=True, null=True)),
                        ('criado_em', models.DateTimeField(auto_now_add=True)),
                        ('atualizado_em', models.DateTimeField(auto_now=True)),
                        ('empresa', models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name='identidades_paciente', to='api.empresa',
                        )),
                    ],
                    options={
                        'verbose_name': 'Identidade de Paciente (MPI)',
                        'verbose_name_plural': 'Identidades de Paciente (MPI)',
                        'ordering': ['nome'],
                        'indexes': [
                            models.Index(fields=['empresa', 'cpf'], name='idx_identpac_empresa_cpf'),
                            models.Index(fields=['empresa', 'nome'], name='idx_identpac_empresa_nome'),
                        ],
                    },
                ),
            ],
        ),

        # --- PacienteInternado.identidade ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_add_fk_column_sql('api_pacienteinternado', 'identidade_id'),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='pacienteinternado',
                    name='identidade',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='perfis_internacao', to='api.identidadepaciente',
                        help_text='Vínculo com a identidade única do paciente (MPI) — populado por sync, não exposto na UI',
                    ),
                ),
            ],
        ),

        # --- ProntuarioHospitalar.identidade ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_add_fk_column_sql('api_prontuariohospitalar', 'identidade_id'),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='prontuariohospitalar',
                    name='identidade',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='prontuarios', to='api.identidadepaciente',
                        help_text='Vínculo com a identidade única do paciente (MPI) — populado por sync, não exposto na UI',
                    ),
                ),
            ],
        ),
    ]
