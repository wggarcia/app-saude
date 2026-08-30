"""
Aplica RLS às tabelas multi-tenant de vínculo INDIRETO — as que não têm coluna
empresa_id própria, mas pertencem a um tenant via FK para um model que tem
(ex.: EvolucaoProntuario → ProntuarioHospitalar.empresa_id).

Usa policy com SUBCONSULTA ao pai (sem mudar schema, sem denormalizar):

    USING (fk_col IN (SELECT id FROM pai WHERE empresa_id = <tenant>))

O mapa filho→pai é DESCOBERTO por introspecção dos models (1 ou 2 hops até um
model com FK `empresa`), evitando transcrição manual. Rode SEMPRE --dry-run
primeiro e revise o mapa; aplique só após validar em Postgres de homologação.

  python manage.py aplicar_rls_indireto --dry-run
  python manage.py aplicar_rls_indireto
"""
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection

_TENANT = "NULLIF(current_setting('app.empresa_id', true), '')::bigint"


def _tem_empresa(model):
    return any(f.name == "empresa" and f.is_relation
               and (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False))
               for f in model._meta.get_fields())


def _fks(model):
    """(campo, model_alvo, coluna) de cada FK/OneToOne do model — ambos criam
    coluna e vínculo de isolamento (O2O era ignorado antes, escondendo pais)."""
    out = []
    for f in model._meta.get_fields():
        # concrete=True → relação FORWARD (tem coluna no banco); exclui rels reversas.
        if (f.is_relation and f.related_model is not None and getattr(f, "concrete", False)
                and (getattr(f, "many_to_one", False) or getattr(f, "one_to_one", False))):
            out.append((f, f.related_model, f.column))
    return out


def _descobrir_caminho(model):
    """Retorna (using, descricao, hops) para isolar `model`, ou (None, None, 0).
    1-hop é confiável (FK única direta ao tenant); 2-hop é heurístico e PODE
    escolher um caminho semanticamente errado — por isso fica separado e exige
    revisão/flag para aplicar."""
    # 1 hop: FK direta para um pai com empresa_id
    for f, alvo, col in _fks(model):
        if _tem_empresa(alvo):
            pai = alvo._meta.db_table
            return (f'"{col}" IN (SELECT id FROM "{pai}" '
                    f'WHERE empresa_id = {_TENANT})'), f"1-hop→{alvo.__name__}", 1
    # 2 hops: FK para um pai que, por sua vez, tem FK para um avô com empresa_id
    for f, alvo, col in _fks(model):
        for f2, avo, col2 in _fks(alvo):
            if _tem_empresa(avo):
                pai = alvo._meta.db_table
                avo_t = avo._meta.db_table
                return (f'"{col}" IN (SELECT id FROM "{pai}" WHERE "{col2}" IN '
                        f'(SELECT id FROM "{avo_t}" WHERE empresa_id = {_TENANT}))'
                        ), f"2-hop→{alvo.__name__}→{avo.__name__}", 2
    return None, None, 0


def _policy_sql(tabela, using):
    return (
        f'ALTER TABLE "{tabela}" ENABLE ROW LEVEL SECURITY;\n'
        f'DROP POLICY IF EXISTS tenant_isolation ON "{tabela}";\n'
        f'CREATE POLICY tenant_isolation ON "{tabela}" '
        f'AS PERMISSIVE FOR ALL TO PUBLIC USING ({using}) WITH CHECK ({using});'
    )


class Command(BaseCommand):
    help = "Aplica RLS (policy por subconsulta) às tabelas de vínculo indireto ao tenant."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Imprime o mapa filho→pai e as policies, sem aplicar.")
        parser.add_argument("--incluir-2hop", action="store_true",
                            help="Também aplica os caminhos de 2 hops (heurísticos — revise o dry-run antes!).")

    def handle(self, *args, **opts):
        um_hop = []      # (tabela, using, desc, nome)
        dois_hop = []
        sem_caminho = []
        for m in apps.get_app_config("api").get_models():
            if _tem_empresa(m):
                continue  # já coberto pela cobertura direta
            using, desc, hops = _descobrir_caminho(m)
            item = (m._meta.db_table, using, desc, m.__name__)
            if hops == 1:
                um_hop.append(item)
            elif hops == 2:
                dois_hop.append(item)
            else:
                sem_caminho.append(m.__name__)

        self.stdout.write(f"1-hop (confiável): {len(um_hop)}  |  "
                          f"2-hop (heurístico, revisar): {len(dois_hop)}  |  "
                          f"sem caminho (globais/plataforma): {len(sem_caminho)}")

        if opts["dry_run"]:
            self.stdout.write("\n— 1-HOP (serão aplicados) —")
            for tabela, using, desc, nome in sorted(um_hop):
                self.stdout.write(f"  [{desc}] {nome} ({tabela})")
            self.stdout.write("\n— 2-HOP (só com --incluir-2hop; REVISE cada um) —")
            for tabela, using, desc, nome in sorted(dois_hop):
                self.stdout.write(f"  [{desc}] {nome} ({tabela})")
            self.stdout.write("\n— SEM CAMINHO (sem RLS; confirme que são globais) —")
            self.stdout.write("  " + ", ".join(sorted(sem_caminho)))
            self.stdout.write(self.style.WARNING("\nDry-run — nada foi alterado."))
            return

        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING(
                f"Banco é {connection.vendor} — RLS é do PostgreSQL. Nada aplicado."))
            return

        alvos = list(um_hop)
        if opts["incluir_2hop"]:
            alvos += dois_hop
        aplicadas = 0
        with connection.cursor() as cur:
            for tabela, using, desc, nome in alvos:
                for stmt in _policy_sql(tabela, using).split(";\n"):
                    if stmt.strip():
                        cur.execute(stmt)
                aplicadas += 1
        extra = "" if opts["incluir_2hop"] else f" ({len(dois_hop)} de 2-hop NÃO aplicados — use --incluir-2hop após revisar)"
        self.stdout.write(self.style.SUCCESS(f"RLS indireto aplicado em {aplicadas} tabelas.{extra}"))
