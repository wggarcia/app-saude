from django.db import migrations, models
import django.db.models.deletion


def _add_fk_column_sql(table, column):
    """SQL idempotente: adiciona coluna FK e constraint somente se ausentes.
    Cópia intencional do helper de 0155_identidadepaciente.py — mesmo motivo:
    tolerar estado de banco onde a coluna já existe mas a migração sumiu de
    django_migrations (restore parcial de backup)."""
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


def _campo_identidade(related_name):
    return models.ForeignKey(
        blank=True, null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name=related_name, to='api.identidadepaciente',
        help_text='Vínculo com a identidade única do paciente (MPI) — populado por sync, não exposto na UI',
    )


class Migration(migrations.Migration):
    """Fase 1 da extensão do MPI (IdentidadePaciente) — item #11 da auditoria
    de jul/2026 — para os módulos de Oncologia e CCIH, que hoje identificam
    paciente só por texto livre (paciente_nome/cpf_paciente).

    Puramente aditivo: colunas novas, todas nullable, nenhuma constraint
    NOT NULL/UNIQUE. Dados existentes continuam válidos sem backfill — o
    backfill roda na migração seguinte (0166), mesmo padrão de 0155/0156.

    Operações de banco são idempotentes (IF NOT EXISTS / DO blocks), mesmo
    motivo de 0155: tolerar estado de DB onde a coluna já existe mas a
    migração sumiu de django_migrations."""

    dependencies = [
        ('api', '0164_alter_iaautorizacaoclinica_modelo_versao_and_more'),
    ]

    operations = [
        # --- CicloQuimioterapia.identidade ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_add_fk_column_sql('api_cicloquimioterapia', 'identidade_id'),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='cicloquimioterapia',
                    name='identidade',
                    field=_campo_identidade('ciclos_quimioterapia_mpi'),
                ),
            ],
        ),

        # --- APACOncologia.identidade ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_add_fk_column_sql('api_apaconcologia', 'identidade_id'),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='apaconcologia',
                    name='identidade',
                    field=_campo_identidade('apacs_oncologia_mpi'),
                ),
            ],
        ),

        # --- InfeccaoHospitalar.identidade ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_add_fk_column_sql('api_infeccaohospitalar', 'identidade_id'),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='infeccaohospitalar',
                    name='identidade',
                    field=_campo_identidade('infeccoes_hospitalares_mpi'),
                ),
            ],
        ),

        # --- ProtocoloIsolamento.identidade ---
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=_add_fk_column_sql('api_protocoloisolamento', 'identidade_id'),
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='protocoloisolamento',
                    name='identidade',
                    field=_campo_identidade('isolamentos_mpi'),
                ),
            ],
        ),
    ]
