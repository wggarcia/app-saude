from django.db import migrations


def _cpf_digitos(valor):
    """Cópia intencional de api.utils.cpf_digitos — migrações de dados não
    devem importar código do app, para não quebrar se a função for alterada
    ou removida no futuro."""
    return "".join(c for c in (valor or "") if c.isdigit())


def _resolver_ou_criar(IdentidadePaciente, empresa_id, nome, cpf, data_nascimento, cache):
    """Mesma prioridade de match do serviço identidade_paciente.resolver_identidade:
    CPF normalizado > nome exato. `cache` evita recriar a mesma identidade
    duas vezes dentro deste próprio backfill (Moderna e EMR convergem para
    uma só quando cpf/nome coincidem)."""
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
            data_nascimento=data_nascimento,
        )

    if chave_cpf:
        cache[chave_cpf] = identidade
    if chave_nome:
        cache[chave_nome] = identidade
    return identidade


def _backfill(apps, schema_editor):
    IdentidadePaciente = apps.get_model('api', 'IdentidadePaciente')
    PacienteInternado = apps.get_model('api', 'PacienteInternado')
    ProntuarioHospitalar = apps.get_model('api', 'ProntuarioHospitalar')

    cache = {}
    ligados_moderna = 0
    ligados_emr = 0

    # Moderna primeiro — é a linhagem com mais contexto (data_internacao,
    # status), então as identidades criadas aqui servem de destino preferencial
    # para o EMR casar em seguida, em vez de cada linhagem criar a sua própria.
    for pac in PacienteInternado.objects.filter(identidade__isnull=True):
        identidade = _resolver_ou_criar(
            IdentidadePaciente, pac.empresa_id, pac.nome, pac.cpf, pac.data_nascimento, cache,
        )
        if identidade:
            pac.identidade = identidade
            pac.save(update_fields=["identidade"])
            ligados_moderna += 1

    for pront in ProntuarioHospitalar.objects.filter(identidade__isnull=True):
        identidade = _resolver_ou_criar(
            IdentidadePaciente, pront.empresa_id, pront.paciente_nome,
            pront.paciente_cpf, pront.paciente_nascimento, cache,
        )
        if identidade:
            pront.identidade = identidade
            pront.save(update_fields=["identidade"])
            ligados_emr += 1

    sem_match = (
        PacienteInternado.objects.filter(identidade__isnull=True).count()
        + ProntuarioHospitalar.objects.filter(identidade__isnull=True).count()
    )
    print(
        f"\n[0156] MPI backfill — PacienteInternado ligados: {ligados_moderna}, "
        f"ProntuarioHospitalar ligados: {ligados_emr}, sem nome para gerar identidade: {sem_match}"
    )


class Migration(migrations.Migration):
    """Backfill do MPI (IdentidadePaciente) para PacienteInternado e
    ProntuarioHospitalar existentes. Não-destrutivo e idempotente — roda de
    novo sem duplicar (filtra identidade__isnull=True) e nunca apaga/altera
    dados de origem, só preenche a FK nova."""

    dependencies = [
        ('api', '0155_identidadepaciente'),
    ]

    operations = [
        migrations.RunPython(_backfill, migrations.RunPython.noop),
    ]
