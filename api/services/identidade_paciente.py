"""
Serviço de resolução de identidade de paciente (MPI leve) do segmento Hospital.

Fonte única de matching entre as linhagens de paciente hoje fragmentadas
(Moderna: PacienteInternado; EMR: ProntuarioHospitalar; e, em fases futuras,
CCIH/SAME/Hemoterapia) — todas resolvem para o mesmo IdentidadePaciente.

CPF é a única chave confiável entre linhagens porque o formato de
armazenamento diverge (11 dígitos crus em CCIH/Hemoterapia, 14 mascarados em
Moderna/EMR/Legado) — por isso a comparação nunca usa a string bruta, sempre
`cpf_digitos()`. Na ausência de CPF, cai para nome exato (e data de
nascimento quando disponível), o que pode gerar falsos positivos com
homônimos — aceitável nesta fase (expand), mas não deve ser usado para fundir
identidades automaticamente sem revisão.
"""
from api.models import IdentidadePaciente
from api.utils import cpf_digitos


def resolver_identidade(empresa, *, nome="", cpf="", data_nascimento=None, cns="", criar=True):
    """Acha (ou cria) o IdentidadePaciente correspondente, escopado por empresa.

    Prioridade de match: CPF normalizado > nome exato (+ data_nascimento
    quando informada). Retorna None se não achar e `criar=False`, ou se não
    houver nome suficiente para criar um registro novo.
    """
    nome = (nome or "").strip()
    cpf_norm = cpf_digitos(cpf)[:11]

    identidade = None
    if cpf_norm:
        identidade = (
            IdentidadePaciente.objects
            .filter(empresa=empresa, cpf=cpf_norm)
            .order_by("-id").first()
        )
    if not identidade and nome:
        qs = IdentidadePaciente.objects.filter(empresa=empresa, nome=nome)
        if data_nascimento:
            qs = qs.filter(data_nascimento=data_nascimento)
        identidade = qs.order_by("-id").first()

    if identidade:
        campos = []
        if cpf_norm and not identidade.cpf:
            identidade.cpf = cpf_norm
            campos.append("cpf")
        if data_nascimento and not identidade.data_nascimento:
            identidade.data_nascimento = data_nascimento
            campos.append("data_nascimento")
        if cns and not identidade.cns:
            identidade.cns = cns
            campos.append("cns")
        if campos:
            identidade.save(update_fields=campos)
        return identidade

    if not criar or not nome:
        return None

    return IdentidadePaciente.objects.create(
        empresa=empresa, nome=nome, cpf=cpf_norm,
        data_nascimento=data_nascimento, cns=cns,
    )
