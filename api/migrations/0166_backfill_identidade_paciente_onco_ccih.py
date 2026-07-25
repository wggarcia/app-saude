from django.db import migrations


def _cpf_digitos(valor):
    """Cópia intencional de api.utils.cpf_digitos — migrações de dados não
    devem importar código do app, para não quebrar se a função for alterada
    ou removida no futuro. Mesma cópia usada em 0156."""
    return "".join(c for c in (valor or "") if c.isdigit())


def _resolver_ou_criar(IdentidadePaciente, empresa_id, nome, cpf, cache):
    """Mesma prioridade de match de 0156/identidade_paciente.resolver_identidade:
    CPF normalizado > nome exato. `cache` evita recriar a mesma identidade
    duas vezes dentro deste backfill quando Oncologia e CCIH convergem para
    o mesmo paciente."""
    nome = (nome or "").strip()
    cpf_norm = _cpf_digitos(cpf)[:11]

    chave_cpf = (empresa_id, "cpf", cpf_norm) if cpf_norm else None
    chave_nome = (empresa_id, "nome", nome) if nome else None

    if chave_cpf and chave_cpf in cache:
        return cache[chave_cpf]
    if chave_nome and chave_nome in cache:
        return cache[chave_nome]

    identidade = None
    if cpf_norm:
        identidade = IdentidadePaciente.objects.filter(empresa_id=empresa_id, cpf=cpf_norm).order_by("-id").first()
    if not identidade and nome:
        identidade = IdentidadePaciente.objects.filter(empresa_id=empresa_id, nome=nome).order_by("-id").first()

    if not identidade:
        if not nome:
            return None
        identidade = IdentidadePaciente.objects.create(
            empresa_id=empresa_id, nome=nome, cpf=cpf_norm,
        )

    if chave_cpf:
        cache[chave_cpf] = identidade
    if chave_nome:
        cache[chave_nome] = identidade
    return identidade


def _backfill(apps, schema_editor):
    IdentidadePaciente = apps.get_model('api', 'IdentidadePaciente')
    CicloQuimioterapia = apps.get_model('api', 'CicloQuimioterapia')
    APACOncologia = apps.get_model('api', 'APACOncologia')
    InfeccaoHospitalar = apps.get_model('api', 'InfeccaoHospitalar')
    ProtocoloIsolamento = apps.get_model('api', 'ProtocoloIsolamento')

    cache = {}
    ligados = {"ciclos": 0, "apacs": 0, "infeccoes": 0, "isolamentos": 0}

    for ciclo in CicloQuimioterapia.objects.filter(identidade__isnull=True):
        identidade = _resolver_ou_criar(
            IdentidadePaciente, ciclo.empresa_id, ciclo.paciente_nome, ciclo.cpf_paciente, cache,
        )
        if identidade:
            ciclo.identidade = identidade
            ciclo.save(update_fields=["identidade"])
            ligados["ciclos"] += 1

    for apac in APACOncologia.objects.filter(identidade__isnull=True):
        identidade = _resolver_ou_criar(
            IdentidadePaciente, apac.empresa_id, apac.paciente_nome, apac.cpf_paciente, cache,
        )
        if identidade:
            apac.identidade = identidade
            apac.save(update_fields=["identidade"])
            ligados["apacs"] += 1

    for inf in InfeccaoHospitalar.objects.filter(identidade__isnull=True):
        identidade = _resolver_ou_criar(
            IdentidadePaciente, inf.empresa_id, inf.paciente_nome, inf.cpf_paciente, cache,
        )
        if identidade:
            inf.identidade = identidade
            inf.save(update_fields=["identidade"])
            ligados["infeccoes"] += 1

    # ProtocoloIsolamento não guarda CPF próprio — herda a identidade da
    # InfeccaoHospitalar referenciada (já resolvida acima, mesmo run) quando
    # houver o vínculo; senão cai para match só por nome.
    for iso in ProtocoloIsolamento.objects.filter(identidade__isnull=True):
        identidade = None
        if iso.infeccao_id:
            infeccao = InfeccaoHospitalar.objects.filter(pk=iso.infeccao_id).first()
            if infeccao and infeccao.identidade_id:
                identidade = infeccao.identidade
        if not identidade:
            identidade = _resolver_ou_criar(
                IdentidadePaciente, iso.empresa_id, iso.paciente_nome, "", cache,
            )
        if identidade:
            iso.identidade = identidade
            iso.save(update_fields=["identidade"])
            ligados["isolamentos"] += 1

    sem_match = (
        CicloQuimioterapia.objects.filter(identidade__isnull=True).count()
        + APACOncologia.objects.filter(identidade__isnull=True).count()
        + InfeccaoHospitalar.objects.filter(identidade__isnull=True).count()
        + ProtocoloIsolamento.objects.filter(identidade__isnull=True).count()
    )
    print(
        f"\n[0166] MPI backfill Oncologia/CCIH — Ciclos: {ligados['ciclos']}, "
        f"APACs: {ligados['apacs']}, Infecções: {ligados['infeccoes']}, "
        f"Isolamentos: {ligados['isolamentos']}, sem nome para gerar identidade: {sem_match}"
    )


class Migration(migrations.Migration):
    """Backfill do MPI (IdentidadePaciente) para CicloQuimioterapia,
    APACOncologia, InfeccaoHospitalar e ProtocoloIsolamento existentes.
    Não-destrutivo e idempotente — roda de novo sem duplicar (filtra
    identidade__isnull=True) e nunca apaga/altera dados de origem, só
    preenche a FK nova. Mesmo padrão de 0156."""

    dependencies = [
        ('api', '0165_hospital_oncologia_ccih_identidade_fk'),
    ]

    operations = [
        migrations.RunPython(_backfill, migrations.RunPython.noop),
    ]
