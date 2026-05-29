from datetime import timedelta
import unicodedata

from django.conf import settings
from django.db.models import F, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .access_control import api_requer_gerencia, get_setor
from .models import (
    ASOOcupacional,
    AcaoCorporativa,
    AfastamentoSST,
    AgendamentoSST,
    CATOcupacional,
    CheckinDiarioCorporativo,
    CheckinSemanalCorporativo,
    ColaboradorAliasCorporativo,
    ConfiguracaoSST,
    DepartamentoHospital,
    DescarteItemFarmacia,
    Dispensacao,
    DispensacaoMedicamento,
    DocumentoSST,
    EmpresaSetor,
    EmpresaTurno,
    EmpresaUnidade,
    EstoqueMovimento,
    EPIItem,
    ExameOcupacional,
    EntregaEPI,
    FornecedorFarmacia,
    FornecedorFarmaciaGestao,
    FuncionarioSST,
    InternacaoHospital,
    InventarioFarmacia,
    ItemFarmacia,
    ItemInventario,
    ItemPedidoCompra,
    LeitoHospital,
    LeitoHospitalar,
    LoteMedicamento,
    MedicamentoFarmacia,
    MovimentoEstoque,
    PacienteFarmacia,
    PacienteHospital,
    PacienteInternado,
    BeneficiarioPlano,
    GuiaAutorizacao,
    IndicadorSaudeGov,
    OrcamentoSaudeGov,
    PlanoAcaoGov,
    PlanoSaude,
    PrestadorPlanoSaude,
    PedidoApoioCorporativo,
    PedidoCompraFarmacia,
    PedidoFarmacia,
    PrescricaoHospitalar,
    PrescricaoMedica,
    ProgramaCorporativo,
    ProgramaSaudeGov,
    ReceitaMedica,
    Reembolso,
    Rede,
    RegistroSintoma,
    RegistroVacinacao,
    RiscoOcupacional,
    PlanoAcaoSST,
    CampanhaVacinacao,
    CheckinBemEstar,
    ClinicaCredenciada,
    ComissaoCIPA,
    CredencialAppFuncionario,
    MembroCIPA,
    NotificacaoFuncionario,
    ParticipanteReuniaoCIPA,
    PostoTrabalho,
    AgenteNocivoPostoTrabalho,
    FuncionarioPostoTrabalho,
    ReuniaoCIPA,
    Sinistro,
    SolicitacaoExame,
    TreinamentoNR,
    VinculoClinicaEmpresa,
    TriagemHospital,
    TriagemManchester,
    TransferenciaEstoque,
    UnidadeRede,
    eSocialEventoSST,
)
from .services.enterprise_dashboard import (
    build_enterprise_command_center_payload,
    build_enterprise_premium_suite_payload,
)


_DEMO_EMPRESAS_EMAILS = {
    "demo.sst@soluscrt.com",
    "demo.farmacia@soluscrt.com",
    "demo.hospital@soluscrt.com",
    "demo.governo@soluscrt.com",
    "demo.plano@soluscrt.com",
}


def _demo_mutations_enabled(empresa=None):
    """Retorna True se mutations de demo estao permitidas.

    Contas demo oficiais (demo.*@soluscrt.com) sempre podem executar seed,
    independente da variavel de ambiente — que só é relevante para contas
    comuns em ambientes de homologacao.
    """
    if empresa is not None and getattr(empresa, "email", None) in _DEMO_EMPRESAS_EMAILS:
        return True
    return bool(getattr(settings, "ALLOW_ENTERPRISE_DEMO_MUTATIONS", True))


def _seed_farmacia(empresa):
    hoje = timezone.localdate()
    criados = []
    fornecedor, created = FornecedorFarmacia.objects.get_or_create(
        empresa=empresa,
        nome="Fornecedor Demo Enterprise",
        defaults={"cnpj": "00.000.000/0001-91", "contato": "Central de Suprimentos", "email": "compras@demo.local", "telefone": "(11) 4000-0000"},
    )
    if created:
        criados.append("fornecedor")
    item, created = ItemFarmacia.objects.get_or_create(
        empresa=empresa,
        nome="Paracetamol 500mg Demo",
        defaults={"codigo": "MED-DEMO-001", "categoria": "medicamento", "unidade_medida": "comprimido", "estoque_minimo": 20, "estoque_atual": 120, "fornecedor": fornecedor},
    )
    if created:
        criados.append("item")
    for nome, codigo, estoque, minimo in (
        ("Dipirona 1g Demo", "MED-DEMO-002", 80, 15),
        ("Amoxicilina 500mg Demo", "MED-DEMO-003", 60, 12),
        ("Losartana 50mg Demo", "MED-DEMO-004", 140, 25),
    ):
        _, created = ItemFarmacia.objects.get_or_create(
            empresa=empresa,
            nome=nome,
            defaults={"codigo": codigo, "categoria": "medicamento", "unidade_medida": "caixa", "estoque_minimo": minimo, "estoque_atual": estoque, "fornecedor": fornecedor},
        )
        if created:
            criados.append(f"item:{codigo}")
    fornecedor_gestao, created = FornecedorFarmaciaGestao.objects.get_or_create(
        empresa=empresa,
        nome="Distribuidora Hospitalar Demo",
        defaults={"cnpj": "00.000.000/0002-72", "contato": "Atendimento B2B", "email": "b2b@demo.local", "telefone": "(11) 4000-1111", "prazo_entrega_dias": 3},
    )
    if created:
        criados.append("fornecedor_gestao")
    for nome, principio, qtd, minimo, controlado, refrigerado in (
        ("Paracetamol", "Paracetamol", 120, 20, False, False),
        ("Amoxicilina", "Amoxicilina", 60, 12, False, False),
        ("Insulina NPH", "Insulina humana NPH", 18, 10, False, True),
        ("Clonazepam", "Clonazepam", 25, 8, True, False),
    ):
        _, created = MedicamentoFarmacia.objects.get_or_create(
            empresa=empresa,
            nome=nome,
            concentracao="500mg" if nome != "Insulina NPH" else "100UI/mL",
            defaults={
                "principio_ativo": principio,
                "forma_farmaceutica": "comprimido" if nome != "Insulina NPH" else "injetavel",
                "fabricante": "Fabricante Demo",
                "classe_terapeutica": "analgesico" if nome == "Paracetamol" else "outro",
                "quantidade_atual": qtd,
                "quantidade_minima": minimo,
                "quantidade_maxima": qtd * 2,
                "preco_custo": 8,
                "preco_venda": 18,
                "controlado": controlado,
                "refrigerado": refrigerado,
            },
        )
        if created:
            criados.append(f"medicamento:{nome}")
    paciente, created = PacienteFarmacia.objects.get_or_create(
        empresa=empresa,
        cpf="000.000.000-91",
        defaults={"nome": "Paciente Demo Farmacia", "telefone": "(11) 99999-0000", "alergias": "Sem alergias conhecidas", "condicoes_cronicas": "Hipertensao controlada"},
    )
    if created:
        criados.append("paciente")
    receita, created = ReceitaMedica.objects.get_or_create(
        empresa=empresa,
        numero_receita="REC-DEMO-001",
        defaults={
            "paciente": paciente,
            "paciente_nome": paciente.nome,
            "paciente_cpf": paciente.cpf,
            "tipo": "simples",
            "medico_nome": "Dra. Demo Clinica",
            "medico_crm": "CRM/SP 000001",
            "data_emissao": hoje,
            "data_validade": hoje + timedelta(days=30),
            "item": item,
            "quantidade": 2,
            "posologia": "1 comprimido a cada 8 horas se dor ou febre.",
        },
    )
    if created:
        criados.append("receita")
    dispensacao, created = DispensacaoMedicamento.objects.get_or_create(
        empresa=empresa,
        item=item,
        paciente_cpf=paciente.cpf,
        defaults={"paciente_nome": paciente.nome, "quantidade": 2, "responsavel": "Farmaceutico Demo", "observacoes": "Dispensacao inicial de demonstracao."},
    )
    if created:
        criados.append("dispensacao")
        ReceitaMedica.objects.filter(id=receita.id).update(status="dispensada", dispensacao=dispensacao)
    dispensacao_gestao, created = Dispensacao.objects.get_or_create(
        empresa=empresa,
        paciente_cpf=paciente.cpf,
        prescricao_numero="REC-DEMO-001",
        defaults={
            "paciente_nome": paciente.nome,
            "medico_crm": "CRM/SP 000001",
            "medicamentos": [{"nome": item.nome, "quantidade": 2, "lote": "LOTE-DEMO-001"}],
            "valor_total": 36,
            "convenio": "Particular Demo",
            "status": "dispensada",
            "observacoes": "Dispensacao assistencial registrada no modulo gestao.",
        },
    )
    if created:
        criados.append("dispensacao_gestao")
    mov, created = MovimentoEstoque.objects.get_or_create(
        empresa=empresa,
        item=item,
        tipo="entrada",
        motivo="Entrada inicial demo enterprise",
        defaults={"quantidade": 120, "estoque_anterior": 0, "estoque_posterior": 120, "responsavel": "Operacao Demo"},
    )
    if created:
        criados.append("movimento")
    lote, created = LoteMedicamento.objects.get_or_create(
        empresa=empresa,
        item=item,
        numero_lote="LOTE-DEMO-001",
        defaults={"fabricante": "Industria Demo", "data_fabricacao": hoje - timedelta(days=45), "data_validade": hoje + timedelta(days=240), "quantidade_inicial": 120, "quantidade_atual": 118, "nota_fiscal": "NF-DEMO-001", "fornecedor": fornecedor},
    )
    if created:
        criados.append("lote")
    pedido, created = PedidoCompraFarmacia.objects.get_or_create(
        empresa=empresa,
        fornecedor=fornecedor,
        observacoes="Pedido inicial de demonstracao enterprise.",
        defaults={"status": "enviado"},
    )
    if created:
        criados.append("pedido")
        ItemPedidoCompra.objects.get_or_create(
            pedido=pedido,
            item=item,
            defaults={"quantidade_solicitada": 50, "quantidade_recebida": 0},
        )
    pedido_gestao, created = PedidoFarmacia.objects.get_or_create(
        empresa=empresa,
        fornecedor=fornecedor_gestao,
        observacao="Pedido gestao demo com medicamento definitivo.",
        defaults={"status": "enviado", "data_entrega_prevista": hoje + timedelta(days=3), "itens": [{"medicamento": "Paracetamol", "quantidade": 50, "preco_unitario": 8}], "valor_total": 400},
    )
    if created:
        criados.append("pedido_gestao")
    inventario, created = InventarioFarmacia.objects.get_or_create(
        empresa=empresa,
        descricao="Inventario inicial demo enterprise",
        defaults={"responsavel": "Operacao Demo", "observacoes": "Snapshot inicial para ativar processo."},
    )
    if created:
        criados.append("inventario")
        ItemInventario.objects.get_or_create(
            inventario=inventario,
            item=item,
            defaults={"estoque_sistema": item.estoque_atual, "estoque_contado": item.estoque_atual, "diferenca": 0},
        )
    descarte, created = DescarteItemFarmacia.objects.get_or_create(
        empresa=empresa,
        item=item,
        motivo="avaria",
        numero_manifesto="MTR-DEMO-001",
        defaults={"lote": lote, "quantidade": 1, "responsavel": "Farmaceutico Demo", "empresa_descarte": "Descarte Ambiental Demo", "observacoes": "Registro demonstrativo de descarte rastreavel."},
    )
    if created:
        criados.append("descarte")

    # ── Expansão para atingir 100% nas 4 capacidades ─────────────────────────
    # clinica: pacientes + receitas >= 8 (alvo=8)
    pacientes_extra = [
        ("000.000.001-01", "Beatriz Furtado Demo", "F", 10950, "beatriz@demo.local"),
        ("000.000.001-02", "Carlos Mendes Demo",   "M", 14600, ""),
        ("000.000.001-03", "Diana Castro Demo",    "F", 21900, "diana@demo.local"),
        ("000.000.001-04", "Eduardo Lima Demo",    "M", 18250, ""),
    ]
    pacientes_farm = [paciente]
    for cpf_f, nome_f, sexo_f, nasc_f, email_f in pacientes_extra:
        pf, created = PacienteFarmacia.objects.get_or_create(
            empresa=empresa, cpf=cpf_f,
            defaults={"nome": nome_f, "sexo": sexo_f,
                      "data_nascimento": hoje - timedelta(days=nasc_f),
                      "email": email_f, "telefone": "(11) 99000-0001", "ativo": True},
        )
        pacientes_farm.append(pf)
        if created:
            criados.append(f"paciente_extra_{cpf_f[-2:]}")

    receitas_extra = [
        (pacientes_farm[1], "Metformina 500mg", "CRM/SP 000099", 30),
        (pacientes_farm[2], "Losartana 50mg",   "CRM/SP 000099", 30),
        (pacientes_farm[3], "AAS 100mg",        "CRM/SP 000099", 30),
    ]
    for pf_r, med_r, crm_r, val_r in receitas_extra:
        _, created = ReceitaMedica.objects.get_or_create(
            empresa=empresa, paciente=pf_r, medicamento=med_r,
            defaults={"medico_nome": "Dr. Demo Extra", "medico_crm": crm_r,
                      "posologia": "1x ao dia", "validade_dias": val_r, "status": "ativa"},
        )
        if created:
            criados.append(f"receita_extra_{med_r[:10]}")

    # dispensacao: >= 10 (alvo=10) — adiciona 8 dispensacoes extra
    for idx_d in range(8):
        pf_d = pacientes_farm[idx_d % len(pacientes_farm)]
        _, created = Dispensacao.objects.get_or_create(
            empresa=empresa,
            paciente_cpf=pf_d.cpf,
            prescricao_numero=f"REC-EXT-{idx_d+1:03d}",
            defaults={
                "paciente_nome": pf_d.nome,
                "medico_crm": "CRM/SP 000099",
                "medicamentos": [{"nome": "Paracetamol 500mg", "quantidade": 10}],
                "valor_total": 15 + idx_d,
                "convenio": "Particular",
                "status": "dispensada",
                "observacoes": f"Dispensacao extra demo #{idx_d+1}",
            },
        )
        if created:
            criados.append(f"dispensacao_extra_{idx_d+1}")

    # rastreabilidade: lotes + inventarios >= 6 (alvo=6) — adiciona 3 lotes + 1 inventario
    for idx_l in range(3):
        _, created = LoteMedicamento.objects.get_or_create(
            empresa=empresa, item=item,
            numero_lote=f"LOTE-EXT-{idx_l+1:03d}",
            defaults={
                "fabricante": "Industria Demo Extra",
                "data_fabricacao": hoje - timedelta(days=30 + idx_l * 10),
                "data_validade": hoje + timedelta(days=300 - idx_l * 30),
                "quantidade_inicial": 50, "quantidade_atual": 50 - idx_l * 5,
                "nota_fiscal": f"NF-EXT-{idx_l+1:03d}",
                "fornecedor": fornecedor,
            },
        )
        if created:
            criados.append(f"lote_ext_{idx_l+1}")

    inv2, created = InventarioFarmacia.objects.get_or_create(
        empresa=empresa,
        descricao="Inventario parcial modulo gestao demo",
        defaults={"responsavel": "Operacao Demo 2", "observacoes": "Segundo inventario demo — contagem ciclica."},
    )
    if created:
        criados.append("inventario_2")

    return criados


def _seed_hospital(empresa):  # noqa: C901
    """Seed hospital demo data to reach 100% on all 4 enterprise capacidades.

    Targets (from _suite_hospital):
    - porta_entrada (TriagemManchester + TriagemHospital) >= 10  alvo=10
    - leitos        (LeitoHospital + DepartamentoHospital)  >= 12  alvo=12
    - cuidado       (InternacaoHospital + PrescricaoMedica) >= 12  alvo=12
    - receita       (GuiaAutorizacao via unidade__empresa)  >= 8   alvo=8
    """
    hoje = timezone.localdate()
    agora = timezone.now()
    criados = []

    # ── 1. Departamentos (4) + Leitos (8) → leitos capacidade: 12/12 ──────────
    departamentos_data = [
        ("Emergencia", "emergencia", 20),
        ("UTI Adulto", "uti", 10),
        ("Clinica Medica", "clinica", 30),
        ("Maternidade", "maternidade", 15),
    ]
    deps = []
    for nome_d, tipo_d, cap_d in departamentos_data:
        dep, created = DepartamentoHospital.objects.get_or_create(
            empresa=empresa,
            nome=f"{nome_d} Demo",
            defaults={"tipo": tipo_d, "capacidade_leitos": cap_d, "responsavel": f"Coord. {nome_d} Demo"},
        )
        deps.append(dep)
        if created:
            criados.append(f"dep_{tipo_d}")

    leitos_data = [
        ("E-01", "observacao", "ocupado"),
        ("E-02", "uti", "ocupado"),
        ("C-01", "enfermaria", "disponivel"),
        ("C-02", "apartamento", "disponivel"),
        ("U-01", "uti", "ocupado"),
        ("U-02", "uti", "manutencao"),
        ("M-01", "maternidade", "disponivel"),
        ("M-02", "maternidade", "ocupado"),
    ]
    leitos = []
    for idx, (num, tipo_l, status_l) in enumerate(leitos_data):
        dep_alvo = deps[idx % len(deps)]
        leito, created = LeitoHospital.objects.get_or_create(
            empresa=empresa,
            departamento=dep_alvo,
            numero=f"{num}-DEMO",
            defaults={"tipo": tipo_l, "status": status_l},
        )
        leitos.append(leito)
        if created:
            criados.append(f"leito_{num}")

    # ── 2. Pacientes (5) ────────────────────────────────────────────────────────
    pacientes_data = [
        ("000.000.000-80", "Ana Lima Demo",     "F", 14600, "A+",  "Penicilina"),
        ("000.000.000-81", "Bruno Melo Demo",   "M", 21900, "O+",  ""),
        ("000.000.000-82", "Carla Nunes Demo",  "F", 10950, "B-",  "AAS"),
        ("000.000.000-83", "Diego Pires Demo",  "M", 18250, "AB+", ""),
        ("000.000.000-84", "Elena Souza Demo",  "F", 25550, "O-",  "Dipirona"),
    ]
    pacientes = []
    for cpf_p, nome_p, sexo_p, nasc_d, tipo_s, alergia in pacientes_data:
        pac, created = PacienteHospital.objects.get_or_create(
            empresa=empresa,
            cpf=cpf_p,
            defaults={
                "nome": nome_p, "sexo": sexo_p,
                "data_nascimento": hoje - timedelta(days=nasc_d),
                "tipo_sanguineo": tipo_s, "alergias": alergia,
                "telefone": "(11) 98000-0000", "endereco": "Rua Demo Hospital, 1",
            },
        )
        pacientes.append(pac)
        if created:
            criados.append(f"paciente_{cpf_p[-2:]}")

    # ── 3. Triagens (10) → porta_entrada: 10/10 ────────────────────────────────
    triagens_manchester = [
        ("Paciente Manchester 1 Demo", "000.111.001-00", "Dor toracica intensa", "vermelho", 5),
        ("Paciente Manchester 2 Demo", "000.111.002-00", "Falta de ar acentuada", "laranja", 12),
        ("Paciente Manchester 3 Demo", "000.111.003-00", "Crise hipertensiva", "laranja", 18),
        ("Paciente Manchester 4 Demo", "000.111.004-00", "Dor abdominal aguda", "amarelo", 35),
        ("Paciente Manchester 5 Demo", "000.111.005-00", "Febre e vomitos", "verde", 60),
    ]
    for nome_t, cpf_t, queixa_t, nivel_t, espera_t in triagens_manchester:
        _, created = TriagemManchester.objects.get_or_create(
            empresa=empresa,
            paciente_nome=nome_t,
            defaults={
                "paciente_cpf": cpf_t, "queixa_principal": queixa_t,
                "nivel": nivel_t, "tempo_espera_minutos": espera_t,
                "status": "em_atendimento", "medico_responsavel": "Dr. Demo Emergencia",
                "data_hora": agora - timedelta(hours=espera_t),
            },
        )
        if created:
            criados.append(f"triagem_manchester_{nivel_t}")

    triagens_hosp_data = [
        (0, "vermelho", "Parada cardiorespiratoria", "120x80", "40.1", 88, 120),
        (1, "laranja",  "Crise convulsiva", "130x85", "38.9", 92, 110),
        (2, "amarelo",  "Dor em flanco direito", "125x80", "37.5", 97, 88),
        (3, "verde",    "Laceracao superficial", "115x75", "36.8", 99, 76),
        (4, "azul",     "Renovacao de receita", "110x70", "36.5", 99, 70),
    ]
    for idx_t, prio_t, queixa_ht, pa_t, temp_t, sat_t, fc_t in triagens_hosp_data:
        pac_t = pacientes[idx_t % len(pacientes)]
        _, created = TriagemHospital.objects.get_or_create(
            empresa=empresa,
            paciente=pac_t,
            prioridade=prio_t,
            defaults={
                "queixa_principal": queixa_ht,
                "pressao_arterial": pa_t, "temperatura": temp_t,
                "saturacao": sat_t, "frequencia_cardiaca": fc_t,
                "responsavel": "Enf. Demo Triagem",
            },
        )
        if created:
            criados.append(f"triagem_hosp_{prio_t}")

    # ── 4. Internacoes (5) + Prescricoes (7) → cuidado: 12/12 ─────────────────
    internacao_dados = [
        (0, leitos[0], "I10",   "Hipertensao arterial sistemica",          "Dr. Cardio Demo"),
        (1, leitos[1], "J18.9", "Pneumonia bacteriana com suporte venti",  "Dra. Pneumo Demo"),
        (2, leitos[2], "K35.8", "Apendicite aguda pos-operatorio",         "Dr. Cirurgia Demo"),
        (3, leitos[4], "N18.3", "Insuficiencia renal cronica agudizada",   "Dra. Nefro Demo"),
        (4, leitos[7], "O80",   "Parto normal — puerperio imediato",       "Dra. Obst Demo"),
    ]
    internacoes = []
    for idx_i, leito_i, cid_i, diag_i, medico_i in internacao_dados:
        pac_i = pacientes[idx_i]
        internacao, created = InternacaoHospital.objects.get_or_create(
            empresa=empresa,
            paciente=pac_i,
            status="ativa",
            defaults={
                "leito": leito_i,
                "diagnostico": diag_i,
                "medico_responsavel": medico_i,
            },
        )
        internacoes.append(internacao)
        if created:
            criados.append(f"internacao_{cid_i}")

    prescricoes_dados = [
        (0, "Enalapril 10mg",       "1 comprimido", "oral",  "1x ao dia", 30),
        (0, "Furosemida 40mg",      "1 comprimido", "oral",  "2x ao dia", 14),
        (1, "Amoxicilina 1g EV",    "1g",           "ev",    "8/8h",      7),
        (1, "Dexametasona 4mg",     "1 ampola",     "ev",    "12/12h",    5),
        (2, "Dipirona 500mg",       "2 comprimidos","oral",  "6/6h SN",   5),
        (3, "Losartana 50mg",       "1 comprimido", "oral",  "1x ao dia", 30),
        (4, "Ocitocina 10UI",       "1 ampola",     "ev",    "SN",        1),
    ]
    for idx_p, med_p, dose_p, via_p, freq_p, dur_p in prescricoes_dados:
        if idx_p >= len(internacoes):
            continue
        _, created = PrescricaoMedica.objects.get_or_create(
            internacao=internacoes[idx_p],
            medicamento=med_p,
            defaults={"dose": dose_p, "via": via_p, "frequencia": freq_p, "duracao_dias": dur_p, "status": "ativa", "medico": internacoes[idx_p].medico_responsavel},
        )
        if created:
            criados.append(f"prescricao_{med_p[:15]}")

    # ── 5. UnidadeRede + PlanoSaude + BeneficiarioPlano + GuiaAutorizacao ──────
    #       → receita capacidade: 8 guias / alvo=8 → 100%
    try:
        unidade_rede, created = UnidadeRede.objects.get_or_create(
            empresa=empresa,
            defaults={
                "tipo": "hospital",
                "nome_unidade": "Hospital Demo Enterprise",
                "codigo_unidade": "HOSP-DEMO-001",
                "endereco": "Av. Hospital Demo, 1000 — Centro",
                "cidade": "Sao Paulo", "estado": "SP",
                "responsavel": "Diretor Clinico Demo",
                "telefone": "(11) 4000-5500",
                "ativa": True,
            },
        )
        if created:
            criados.append("unidade_rede")

        plano_h, created = PlanoSaude.objects.get_or_create(
            empresa=empresa, nome="Plano Hospitalar Convenio Demo",
            defaults={"registro_ans": "999901", "modalidade": "autogestao", "status": PlanoSaude.STATUS_ATIVO,
                      "abrangencia": "municipal"},
        )
        if created:
            criados.append("plano_hospital")

        benef_hosp_data = [
            ("000.999.001-00", "Beneficiario Hosp 1 Demo", "F", 12000, "PS-H001", "apartamento"),
            ("000.999.002-00", "Beneficiario Hosp 2 Demo", "M", 16000, "PS-H002", "enfermaria"),
            ("000.999.003-00", "Beneficiario Hosp 3 Demo", "F", 20000, "PS-H003", "apartamento"),
            ("000.999.004-00", "Beneficiario Hosp 4 Demo", "M", 9000,  "PS-H004", "enfermaria"),
        ]
        beneficiarios_h = []
        for cpf_b, nome_b, sexo_b, nasc_b, cart_b, acomo_b in benef_hosp_data:
            ben, _ = BeneficiarioPlano.objects.get_or_create(
                plano=plano_h, cpf=cpf_b,
                defaults={
                    "nome": nome_b, "sexo": sexo_b,
                    "data_nascimento": hoje - timedelta(days=nasc_b),
                    "numero_carteirinha": cart_b,
                    "data_inicio_vigencia": hoje - timedelta(days=365),
                    "situacao": BeneficiarioPlano.SITUACAO_ATIVO,
                    "plano_tipo": "Coletivo", "acomodacao": acomo_b,
                    "email": f"{cpf_b[:3].replace('.', '')}@demo.local",
                    "telefone": "(11) 99000-0000",
                },
            )
            beneficiarios_h.append(ben)

        guias_hosp_data = [
            ("GH-001", 0, GuiaAutorizacao.TIPO_INTERNACAO,  "71001099", "Internacao clinica",           "I10",   GuiaAutorizacao.STATUS_AUTORIZADA, "alta_complexidade"),
            ("GH-002", 1, GuiaAutorizacao.TIPO_EXAME,       "40301010", "Tomografia de torax",          "J18.9", GuiaAutorizacao.STATUS_AUTORIZADA, "urgente"),
            ("GH-003", 2, GuiaAutorizacao.TIPO_PROCEDIMENTO,"30901010", "Appendectomia",                "K35.8", GuiaAutorizacao.STATUS_AUTORIZADA, "urgente"),
            ("GH-004", 3, GuiaAutorizacao.TIPO_INTERNACAO,  "71002010", "Internacao nefrologica",       "N18.3", GuiaAutorizacao.STATUS_EM_ANALISE, "alta_complexidade"),
            ("GH-005", 0, GuiaAutorizacao.TIPO_EXAME,       "40601010", "Ecocardiograma",               "I10",   GuiaAutorizacao.STATUS_SOLICITADA, "eletiva"),
            ("GH-006", 1, GuiaAutorizacao.TIPO_CONSULTA,    "10101012", "Consulta pneumologia",         "J18.9", GuiaAutorizacao.STATUS_AUTORIZADA, "eletiva"),
            ("GH-007", 2, GuiaAutorizacao.TIPO_EXAME,       "40501010", "Ultrassom abdominal",          "K35.8", GuiaAutorizacao.STATUS_AUTORIZADA, "eletiva"),
            ("GH-008", 3, GuiaAutorizacao.TIPO_MEDICAMENTO, "90301039", "Eritropoetina renal",          "N18.3", GuiaAutorizacao.STATUS_NEGADA,     "alta_complexidade"),
        ]
        for num_g, ben_idx, tipo_g, cod_g, desc_g, cid_g, status_g, prio_g in guias_hosp_data:
            _, created = GuiaAutorizacao.objects.get_or_create(
                plano=plano_h,
                beneficiario=beneficiarios_h[ben_idx % len(beneficiarios_h)],
                numero_guia=num_g,
                defaults={
                    "unidade": unidade_rede,
                    "tipo": tipo_g,
                    "codigo_procedimento": cod_g,
                    "descricao_procedimento": desc_g,
                    "cid": cid_g,
                    "medico_solicitante": "Dr. Demo Hospital",
                    "crm_medico": "CRM/SP 999001",
                    "quantidade": 1,
                    "status": status_g,
                    "prioridade_clinica": prio_g,
                    "fila_status": GuiaAutorizacao.FILA_AUTORIZADA if status_g == GuiaAutorizacao.STATUS_AUTORIZADA else GuiaAutorizacao.FILA_TRIAGEM,
                    "auditor_responsavel": "Central Regulacao Demo",
                },
            )
            if created:
                criados.append(f"guia_{num_g}")
    except Exception as exc_g:
        criados.append(f"erro_guias:{str(exc_g)[:60]}")

    return criados


def _seed_empresa(empresa):
    hoje = timezone.localdate()
    agora_base = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
    criados = []
    config, created = ConfiguracaoSST.objects.update_or_create(
        empresa=empresa,
        defaults={
            "nome_medico_coordenador": "Dra. Helena Demo Ocupacional",
            "crm_medico": "CRM/SP 123456",
            "especialidade_medico": "Medicina do Trabalho",
            "nome_engenheiro": "Eng. Marcos Demo Segurança",
            "crea_engenheiro": "CREA/SP 987654",
            "nome_tecnico": "Téc. Camila Demo SST",
            "registro_tecnico": "MTE 456789",
            "nome_enfermeiro": "Enf. Roberto Demo",
            "coren_enfermeiro": "COREN/SP 112233",
            "alerta_aso_dias": 30,
            "alerta_exame_dias": 30,
            "alerta_treinamento_dias": 60,
            "email_alertas": empresa.email,
            "alertas_ativos": True,
            "cnpj": "12.345.678/0001-90",
            "cnae_principal": "86.30-5-03 - Atividade médica ambulatorial restrita a consultas",
            "grau_risco": "3",
            "numero_funcionarios": 6,
            "endereco_completo": "Unidade Demo Enterprise - Avenida Saúde Ocupacional, 1000",
            "certificado_nome": "Certificado eSocial Demo Homologação",
            "certificado_validade": hoje + timedelta(days=330),
            "esocial_ambiente": "homologacao",
        },
    )
    criados.append("config_sst_atualizada" if not created else "config_sst")
    funcionario, created = FuncionarioSST.objects.get_or_create(
        empresa=empresa,
        cpf="000.000.000-93",
        defaults={"nome": "Colaborador Demo SST", "cargo": "Operador Demo", "setor": "Operacao", "sexo": "O", "data_admissao": hoje - timedelta(days=120), "classe_risco": "II", "ativo": True},
    )
    if created:
        criados.append("funcionario")
    funcionarios = [funcionario]
    funcionarios_demo = [
        ("000.000.000-94", "Ana Paula Demo", "Operadora de Produção", "Produção", "F", "III", 520),
        ("000.000.000-95", "Bruno Santos Demo", "Técnico de Manutenção", "Manutenção", "M", "IV", 410),
        ("000.000.000-96", "Carla Lima Demo", "Analista Administrativo", "Administrativo", "F", "I", 260),
        ("000.000.000-97", "Diego Rocha Demo", "Almoxarife", "Logística", "M", "II", 190),
        ("000.000.000-98", "Fernanda Costa Demo", "Enfermeira do Trabalho", "Ambulatório", "F", "II", 330),
    ]
    for cpf, nome, cargo, setor, sexo, classe, dias in funcionarios_demo:
        func, created = FuncionarioSST.objects.get_or_create(
            empresa=empresa,
            cpf=cpf,
            defaults={
                "nome": nome,
                "cargo": cargo,
                "setor": setor,
                "sexo": sexo,
                "data_admissao": hoje - timedelta(days=dias),
                "classe_risco": classe,
                "ativo": True,
            },
        )
        funcionarios.append(func)
        if created:
            criados.append(f"funcionario_{setor.lower()}")
    aso, created = ASOOcupacional.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionario,
        tipo="periodico",
        data_emissao=hoje,
        defaults={"data_validade": hoje + timedelta(days=365), "medico_responsavel": "Dra. Demo Ocupacional", "crm": "CRM/SP 000003", "resultado": "apto"},
    )
    if created:
        criados.append("aso")
    exame, created = ExameOcupacional.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionario,
        aso=aso,
        tipo_exame="audiometria",
        defaults={"data_realizacao": hoje, "data_validade": hoje + timedelta(days=365), "resultado": "Dentro dos parametros ocupacionais", "status": "realizado", "observacoes": "Exame demo vinculado ao ASO."},
    )
    if created:
        criados.append("exame")
    agendamento, created = AgendamentoSST.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionario,
        tipo="exame_periodico",
        data_hora=agora_base + timedelta(days=30),
        defaults={"status": "agendado", "local": "Clinica Demo Ocupacional", "medico": "Dra. Demo Ocupacional", "observacoes": "Agendamento periodico demo."},
    )
    if created:
        criados.append("agendamento")
    for tipo, titulo in (("PGR", "PGR Demo Enterprise"), ("PCMSO", "PCMSO Demo Enterprise"), ("LTCAT", "LTCAT Demo Enterprise")):
        _, created = DocumentoSST.objects.get_or_create(
            empresa=empresa,
            tipo=tipo,
            titulo=titulo,
            defaults={"status": "vigente", "responsavel_tecnico": "Resp. Tecnico Demo", "registro_profissional": "CREA/CRM-DEMO", "data_emissao": hoje, "data_validade": hoje + timedelta(days=365)},
        )
        if created:
            criados.append(tipo.lower())
    evento, created = eSocialEventoSST.objects.get_or_create(
        empresa=empresa,
        tipo_evento="S-2220",
        referencia=str(aso.id),
        defaults={"status": "pendente", "xml_gerado": "<eSocial demo='true' evento='S-2220' />"},
    )
    if created:
        criados.append("esocial")
    cat, created = CATOcupacional.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionario,
        numero_cat="CAT-DEMO-001",
        defaults={"tipo": "tipico", "gravidade": "leve", "data_acidente": hoje - timedelta(days=10), "local_acidente": "Unidade Demo", "descricao": "Ocorrencia leve registrada para teste completo.", "parte_corpo": "Mao", "cid": "S60", "houve_afastamento": True, "dias_afastamento": 3, "status_esocial": "pendente"},
    )
    if created:
        criados.append("cat")
    afastamento, created = AfastamentoSST.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionario,
        cat=cat,
        data_inicio=hoje - timedelta(days=9),
        defaults={"motivo": "acidente_trabalho", "cid": "S60", "data_prevista_retorno": hoje - timedelta(days=6), "data_retorno_real": hoje - timedelta(days=6), "status": "encerrado", "observacoes": "Afastamento demo encerrado."},
    )
    if created:
        criados.append("afastamento")
    evento_cat, created = eSocialEventoSST.objects.get_or_create(
        empresa=empresa,
        tipo_evento="S-2210",
        referencia=str(cat.id),
        defaults={"status": "pendente", "xml_gerado": "<eSocial demo='true' evento='S-2210' />"},
    )
    if created:
        criados.append("esocial_cat")
    treinamento, created = TreinamentoNR.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionario,
        nr="NR-6",
        defaults={"titulo": "NR-6 EPI Demo", "instrutor": "Instrutor Demo", "carga_horaria": 4, "data_realizacao": hoje, "data_validade": hoje + timedelta(days=365), "status": "valido"},
    )
    if created:
        criados.append("treinamento")
    documentos_extra = [
        ("laudo_insalubridade", "Laudo de Insalubridade Demo", "vigente", 360),
        ("laudo_periculosidade", "Laudo de Periculosidade Demo", "em_revisao", 45),
        ("PPP", "PPP Modelo por Função Demo", "vigente", 365),
        ("CIPA", "CIPA Ata de Posse e Calendário Demo", "vigente", 250),
    ]
    for tipo, titulo, status, validade in documentos_extra:
        _, created = DocumentoSST.objects.get_or_create(
            empresa=empresa,
            tipo=tipo,
            titulo=titulo,
            defaults={
                "status": status,
                "responsavel_tecnico": "Equipe SESMT Demo",
                "registro_profissional": "SESMT-DEMO",
                "data_emissao": hoje - timedelta(days=20),
                "data_validade": hoje + timedelta(days=validade),
                "observacoes": "Documento criado para simulação completa do SST.",
            },
        )
        if created:
            criados.append(f"documento_{tipo}")
    exames_demo = [
        (funcionarios[1], "acuidade_visual", "realizado", hoje - timedelta(days=25), hoje + timedelta(days=335), "Apto sem restrições"),
        (funcionarios[2], "eletrocardiograma", "pendente", None, hoje + timedelta(days=20), "Agendado para renovação"),
        (funcionarios[3], "laboratorial", "vencido", hoje - timedelta(days=430), hoje - timedelta(days=65), "Renovação atrasada"),
        (funcionarios[4], "espirometria", "realizado", hoje - timedelta(days=12), hoje + timedelta(days=350), "Dentro dos parâmetros"),
        (funcionarios[5], "psicologico", "realizado", hoje - timedelta(days=40), hoje + timedelta(days=325), "Acompanhamento preventivo"),
    ]
    for func, tipo_exame, status, realizacao, validade, resultado in exames_demo:
        _, created = ExameOcupacional.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            tipo_exame=tipo_exame,
            defaults={
                "data_realizacao": realizacao,
                "data_validade": validade,
                "resultado": resultado,
                "status": status,
                "observacoes": "Exame demo para trilha ocupacional completa.",
            },
        )
        if created:
            criados.append(f"exame_{tipo_exame}")
    aso_demo = [
        (funcionarios[1], "periodico", hoje - timedelta(days=20), hoje + timedelta(days=20), "apto"),
        (funcionarios[2], "mudanca_risco", hoje - timedelta(days=40), hoje + timedelta(days=320), "apto_restricao"),
        (funcionarios[3], "periodico", hoje - timedelta(days=390), hoje - timedelta(days=25), "apto"),
        (funcionarios[4], "admissional", hoje - timedelta(days=170), hoje + timedelta(days=195), "apto"),
        (funcionarios[5], "periodico", hoje - timedelta(days=80), hoje + timedelta(days=285), "apto"),
    ]
    for func, tipo, emissao, validade, resultado in aso_demo:
        _, created = ASOOcupacional.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            tipo=tipo,
            data_emissao=emissao,
            defaults={
                "data_validade": validade,
                "medico_responsavel": "Dra. Helena Demo Ocupacional",
                "crm": "CRM/SP 123456",
                "resultado": resultado,
                "restricoes": "Evitar levantamento de carga acima de 15kg." if resultado == "apto_restricao" else "",
            },
        )
        if created:
            criados.append(f"aso_{tipo}")
    cat_doenca, created = CATOcupacional.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionarios[1],
        numero_cat="CAT-DEMO-DOENCA-001",
        defaults={
            "tipo": "doenca",
            "gravidade": "moderado",
            "data_acidente": hoje - timedelta(days=18),
            "local_acidente": "Linha de embalagem",
            "descricao": "Caso demo de doença do trabalho por sobrecarga biomecânica e repetitividade.",
            "parte_corpo": "Coluna lombar",
            "cid": "M54.5",
            "houve_afastamento": True,
            "dias_afastamento": 12,
            "status_esocial": "pendente",
        },
    )
    if created:
        criados.append("cat_doenca_ocupacional")
    afast_doenca, created = AfastamentoSST.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionarios[1],
        cat=cat_doenca,
        data_inicio=hoje - timedelta(days=18),
        defaults={
            "motivo": "doenca_ocupacional",
            "cid": "M54.5",
            "data_prevista_retorno": hoje + timedelta(days=7),
            "status": "retorno_programado",
            "observacoes": "Afastamento demo vinculado a CID de doença do trabalho.",
        },
    )
    if created:
        criados.append("afastamento_doenca_ocupacional")
    afast_comum, created = AfastamentoSST.objects.get_or_create(
        empresa=empresa,
        funcionario=funcionarios[3],
        data_inicio=hoje - timedelta(days=5),
        defaults={
            "motivo": "doenca_comum",
            "cid": "J11",
            "data_prevista_retorno": hoje + timedelta(days=2),
            "status": "ativo",
            "observacoes": "Afastamento comum demo para comparação de absenteísmo.",
        },
    )
    if created:
        criados.append("afastamento_comum")
    eventos_extra = [
        ("S-2230", str(afast_doenca.id), "pendente", "<eSocial demo='true' evento='S-2230' />"),
        ("S-2240", "ambientes-risco-demo", "erro", "<eSocial demo='true' evento='S-2240' />"),
    ]
    for tipo_evento, referencia, status, xml in eventos_extra:
        _, created = eSocialEventoSST.objects.get_or_create(
            empresa=empresa,
            tipo_evento=tipo_evento,
            referencia=referencia,
            defaults={"status": status, "xml_gerado": xml, "mensagem_erro": "Ambiente de homologação demo: revisar fator de risco." if status == "erro" else ""},
        )
        if created:
            criados.append(f"esocial_{tipo_evento}")
    treinamentos_demo = [
        (funcionarios[1], "NR-12", "Segurança em máquinas e bloqueio", 8, hoje - timedelta(days=55), hoje + timedelta(days=310), "valido"),
        (funcionarios[2], "NR-10", "Segurança em eletricidade", 40, hoje - timedelta(days=760), hoje - timedelta(days=30), "vencido"),
        (funcionarios[2], "NR-35", "Trabalho em altura", 8, hoje + timedelta(days=10), hoje + timedelta(days=375), "agendado"),
        (funcionarios[3], "NR-5", "CIPA e prevenção", 20, None, None, "pendente"),
        (funcionarios[4], "NR-11", "Movimentação e armazenagem", 8, hoje - timedelta(days=70), hoje + timedelta(days=295), "valido"),
        (funcionarios[5], "NR-23", "Brigada e emergência", 8, hoje - timedelta(days=30), hoje + timedelta(days=335), "valido"),
    ]
    for func, nr, titulo, carga, realizacao, validade, status in treinamentos_demo:
        _, created = TreinamentoNR.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            nr=nr,
            titulo=titulo,
            defaults={
                "instrutor": "Instrutor SESMT Demo",
                "carga_horaria": carga,
                "data_realizacao": realizacao,
                "data_validade": validade,
                "status": status,
                "certificado": f"CERT-{nr}-{func.id}",
                "observacoes": "Trilha NR demo para painel enterprise.",
            },
        )
        if created:
            criados.append(f"treinamento_{nr}")
    epis_demo = [
        ("Protetor auricular plug CA Demo", "auditiva", "43210", 420, "3M Demo", "Controle de ruído ocupacional"),
        ("Respirador PFF2 CA Demo", "respiratoria", "54321", 300, "Safety Demo", "Proteção contra poeiras e aerodispersoides"),
        ("Óculos ampla visão CA Demo", "visual", "65432", 500, "Visão Demo", "Proteção contra partículas"),
        ("Luva nitrílica CA Demo", "maos", "76543", 210, "Luva Demo", "Manipulação química leve"),
        ("Botina com biqueira CA Demo", "pes", "87654", 390, "Calçados Demo", "Proteção mecânica"),
        ("Cinto paraquedista CA Demo", "altura", "98765", 240, "Altura Demo", "Trabalho em altura"),
    ]
    epis = []
    for nome, tipo, ca, validade, fornecedor, descricao in epis_demo:
        epi, created = EPIItem.objects.get_or_create(
            empresa=empresa,
            nome=nome,
            defaults={
                "tipo": tipo,
                "ca_numero": ca,
                "validade_ca": hoje + timedelta(days=validade),
                "fornecedor": fornecedor,
                "descricao": descricao,
                "ativo": True,
            },
        )
        epis.append(epi)
        if created:
            criados.append(f"epi_{tipo}")
    for idx, func in enumerate(funcionarios):
        epi = epis[idx % len(epis)]
        _, created = EntregaEPI.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            epi=epi,
            data_entrega=hoje - timedelta(days=30 + idx),
            defaults={"quantidade": 1, "observacoes": "Ficha demo de entrega digital de EPI."},
        )
        if created:
            criados.append("entrega_epi")
    riscos_demo = [
        ("Produção", "fisico", "Ruído contínuo acima de 85 dB(A)", "IV", 4, 4, "NR-15", "Protetor auditivo, enclausuramento parcial e dosimetria anual.", "Reavaliar engenharia de controle e mapa de ruído."),
        ("Manutenção", "acidente", "Intervenção em máquinas energizadas", "V", 4, 5, "NR-10, NR-12", "Permissão de trabalho e bloqueio LOTO.", "Digitalizar checklist LOTO por ordem de serviço."),
        ("Administrativo", "ergonomico", "Postura estática e mobiliário inadequado", "III", 3, 3, "NR-17", "Pausas e cadeiras ajustáveis.", "Executar AET e plano ergonômico por posto."),
        ("Logística", "quimico", "Contato com saneantes e produtos de limpeza", "III", 3, 3, "NR-6, NR-26", "FISPQ e luvas nitrílicas.", "Implantar matriz de compatibilidade química."),
        ("Ambulatório", "biologico", "Exposição a material biológico", "IV", 3, 4, "NR-32", "Perfurocortante, vacinação e protocolo pós-exposição.", "Auditar descarte e cobertura vacinal."),
        ("Todos", "psicossocial", "Sobrecarga operacional e pressão de atendimento", "III", 3, 3, "NR-1", "Canal de escuta e check-in semanal.", "Criar plano de prevenção psicossocial com indicadores."),
    ]
    riscos = []
    for setor, tipo, agente, nivel, prob, sev, nr_ref, existente, proposta in riscos_demo:
        risco, created = RiscoOcupacional.objects.get_or_create(
            empresa=empresa,
            setor=setor,
            agente=agente,
            defaults={
                "tipo_risco": tipo,
                "descricao": f"Risco demo monitorado pelo PGR no setor {setor}.",
                "nivel": nivel,
                "probabilidade": prob,
                "severidade": sev,
                "nr_referencia": nr_ref,
                "medida_controle_existente": existente,
                "medida_controle_proposta": proposta,
                "prazo": hoje + timedelta(days=60),
                "responsavel": "Equipe SESMT Demo",
                "status": "em_controle" if nivel in ("III", "IV") else "identificado",
            },
        )
        riscos.append(risco)
        if created:
            criados.append(f"risco_{tipo}")
    for risco in riscos:
        _, created = PlanoAcaoSST.objects.get_or_create(
            empresa=empresa,
            risco=risco,
            titulo=f"Plano de ação - {risco.agente[:70]}",
            defaults={
                "descricao": risco.medida_controle_proposta,
                "origem": "risco",
                "prioridade": "critica" if risco.nivel == "V" else ("alta" if risco.nivel == "IV" else "media"),
                "responsavel": risco.responsavel,
                "setor": risco.setor,
                "data_prazo": hoje + timedelta(days=45),
                "status": "em_andamento" if risco.nivel in ("IV", "V") else "aberto",
                "observacoes": "Plano demo conectado ao inventário de riscos.",
            },
        )
        if created:
            criados.append("plano_acao_sst")
    campanha, created = CampanhaVacinacao.objects.get_or_create(
        empresa=empresa,
        nome="Campanha Demo Influenza e Hepatite B",
        vacina="Influenza / Hepatite B",
        defaults={
            "descricao": "Campanha demo para trabalhadores expostos e grupos prioritários.",
            "data_inicio": hoje - timedelta(days=15),
            "data_fim": hoje + timedelta(days=20),
            "meta_doses": len(funcionarios),
            "doses_aplicadas": max(1, len(funcionarios) - 1),
            "local": "Ambulatório Ocupacional Demo",
            "responsavel": "Enf. Roberto Demo",
            "status": "em_andamento",
            "observacoes": "Usada para demonstrar vacinação ocupacional integrada ao SST.",
        },
    )
    if created:
        criados.append("campanha_vacinacao")
    for idx, func in enumerate(funcionarios[:-1]):
        _, created = RegistroVacinacao.objects.get_or_create(
            campanha=campanha,
            funcionario=func,
            dose="dose_unica",
            defaults={
                "data_aplicacao": hoje - timedelta(days=idx + 1),
                "lote_vacina": f"VAC-DEMO-{idx+1:03d}",
                "aplicador": "Enf. Roberto Demo",
                "observacoes": "Registro demo de vacinação ocupacional.",
            },
        )
        if created:
            criados.append("registro_vacinacao")
    agendamentos_demo = [
        (funcionarios[2], "treinamento", "confirmado", hoje + timedelta(days=10), "Sala NR Demo", "Instrutor SESMT Demo"),
        (funcionarios[3], "exame_periodico", "agendado", hoje + timedelta(days=14), "Clínica Ocupacional Demo", "Dra. Helena Demo"),
        (funcionarios[4], "consulta", "agendado", hoje + timedelta(days=3), "Ambulatório Demo", "Dra. Helena Demo"),
    ]
    for func, tipo, status, dia, local, medico in agendamentos_demo:
        _, created = AgendamentoSST.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            tipo=tipo,
            data_hora=agora_base + timedelta(days=(dia - hoje).days),
            defaults={"status": status, "local": local, "medico": medico, "observacoes": "Agenda demo SST integrada."},
        )
        if created:
            criados.append(f"agendamento_{tipo}")

    # ── Pedidos de Exame (SolicitacaoExame) ──────────────────────────────────
    import json as _json
    pedidos_exame = [
        (funcionarios[0], "periodico",
         ["Audiometria", "Hemograma Completo", "Glicemia", "Acuidade Visual"],
         "pendente", False, "ASO periódico anual — Operador Demo. Verificar histórico audiométrico.", None),
        (funcionarios[1], "admissional",
         ["Audiometria", "Espirometria", "Hemograma", "Raio-X Tórax PA"],
         "agendado", False, "Admissional — novo operador de produção. Agendado para Clínica Demo.",
         hoje + timedelta(days=5)),
        (funcionarios[2], "periodico",
         ["Audiometria", "Hemograma Completo", "ECG", "Glicemia"],
         "realizado", False, "Periódico realizado. Laudo em análise pelo médico coordenador.",
         hoje - timedelta(days=10)),
        (funcionarios[3], "mudanca_risco",
         ["Avaliação Ergonômica", "Hemograma", "Acuidade Visual"],
         "pendente", True, "⚠️ URGENTE — mudança de setor para Manutenção (maior grau de risco).", None),
        (funcionarios[4], "retorno_trabalho",
         ["Hemograma Completo", "Glicemia", "Acuidade Visual"],
         "realizado", False, "Retorno ao trabalho após afastamento por doença comum.",
         hoje - timedelta(days=6)),
        (funcionarios[5], "demissional",
         ["Hemograma", "Glicemia", "Acuidade Visual", "ECG"],
         "agendado", False, "Demissional — encerramento de contrato em 30 dias.",
         hoje + timedelta(days=20)),
    ]
    for func, tipo_aso, exames_l, status_p, urgente_p, obs_p, data_ag in pedidos_exame:
        _, created = SolicitacaoExame.objects.get_or_create(
            empresa=empresa,
            funcionario=func,
            tipo_aso=tipo_aso,
            defaults={
                "exames": _json.dumps(exames_l, ensure_ascii=False),
                "status": status_p,
                "urgente": urgente_p,
                "observacoes": obs_p,
                "data_agendamento": data_ag,
                "clinica_nome_externo": "Clínica Ocupacional Demo",
                "clinica_email_externo": "clinica@demo.soluscrt.com",
            },
        )
        if created:
            criados.append(f"solicitacao_exame_{tipo_aso}")

    # ── CIPA ─────────────────────────────────────────────────────────────────
    import datetime as _datetime
    cipa, cipa_created = ComissaoCIPA.objects.get_or_create(
        empresa=empresa,
        mandato_inicio=hoje - timedelta(days=200),
        defaults={
            "mandato_fim": hoje + timedelta(days=165),
            "numero_membros_eleitos": 4,
            "numero_membros_indicados": 2,
            "status": "ativa",
            "designacao_nr5": False,
        },
    )
    if cipa_created:
        criados.append("cipa")
        cargos_cipa = [
            (funcionarios[0], "presidente",      "eleito"),
            (funcionarios[1], "vice_presidente", "indicado"),
            (funcionarios[2], "secretario",      "eleito"),
            (funcionarios[3], "membro_eleito",   "eleito"),
            (funcionarios[4], "membro_indicado", "indicado"),
            (funcionarios[5], "membro_eleito",   "eleito"),
        ]
        for func, cargo_c, tipo_c in cargos_cipa:
            try:
                MembroCIPA.objects.create(
                    comissao=cipa, funcionario=func, cargo=cargo_c, tipo=tipo_c,
                    data_posse=hoje - timedelta(days=200), ativo=True,
                )
                criados.append(f"membro_cipa_{cargo_c}")
            except Exception:
                pass

        # Reuniões
        reuniao_realizada = ReuniaoCIPA.objects.create(
            comissao=cipa, tipo="ordinaria",
            data_reuniao=_datetime.datetime.combine(hoje - timedelta(days=30), _datetime.time(9, 0)),
            local="Sala de Reuniões — Demo",
            pauta="1. Análise de acidentes\n2. Revisão PGR\n3. Inspeções programadas",
            ata="Reunião realizada com quórum mínimo. Identificados 2 pontos de melhoria.",
            status="realizada",
        )
        criados.append("reuniao_cipa_realizada")
        reuniao_agendada = ReuniaoCIPA.objects.create(
            comissao=cipa, tipo="ordinaria",
            data_reuniao=_datetime.datetime.combine(hoje + timedelta(days=15), _datetime.time(9, 0)),
            local="Sala de Reuniões — Demo",
            pauta="1. Relatório de EPIs\n2. Quase-acidentes\n3. SIPAT 2026",
            status="agendada",
        )
        criados.append("reuniao_cipa_agendada")

        for func in funcionarios[:5]:
            try:
                ParticipanteReuniaoCIPA.objects.create(
                    reuniao=reuniao_realizada, funcionario=func, presente=True,
                )
            except Exception:
                pass

    # ── Credenciais APP (2 funcionários) ──────────────────────────────────────
    app_credentials = [
        (funcionarios[0], "colaborador.demo@app.local", "ColabDemo@2026"),
        (funcionarios[1], "ana.demo@app.local",         "AnaDemo@2026"),
    ]
    for func, email_app, senha_app in app_credentials:
        from django.contrib.auth.hashers import make_password as _mkpwd
        _, created = CredencialAppFuncionario.objects.get_or_create(
            funcionario=func,
            defaults={"email": email_app, "senha": _mkpwd(senha_app), "ativo": True},
        )
        if created:
            criados.append("credencial_app")

    # ── Notificações APP ──────────────────────────────────────────────────────
    notifs_demo = [
        (funcionarios[0], "EPI aguardando confirmação",
         "Você recebeu 3 EPIs. Confirme o recebimento no APP.",
         "epi", False),
        (funcionarios[0], "ASO periódico solicitado 🔬",
         "Pedido de exame periódico gerado. Compareça à clínica em jejum.",
         "exame", False),
        (funcionarios[0], "Treinamento NR-10 vencido ⚠️",
         "Segurança em Eletricidade venceu há 30 dias. Contate o RH.",
         "treinamento", False),
        (funcionarios[0], "Reunião CIPA — 15 dias 📅",
         f"Próxima reunião ordinária em {(hoje + timedelta(days=15)).strftime('%d/%m/%Y')} às 09h.",
         "cipa", False),
        (funcionarios[1], "Exame admissional agendado 📋",
         "Seu exame admissional está agendado. Apresente-se em jejum de 8h.",
         "exame", False),
    ]
    for func, titulo_n, corpo_n, cat_n, lida_n in notifs_demo:
        try:
            NotificacaoFuncionario.objects.create(
                funcionario=func, titulo=titulo_n, corpo=corpo_n,
                categoria=cat_n, lida=lida_n,
            )
            criados.append("notificacao_app")
        except Exception:
            pass

    # ── Check-ins de bem-estar ────────────────────────────────────────────────
    checkins_demo = [
        (funcionarios[0], "bom",    4, 4, 2, 4),
        (funcionarios[1], "otimo",  5, 5, 1, 5),
        (funcionarios[2], "neutro", 3, 3, 3, 3),
        (funcionarios[3], "ruim",   2, 2, 4, 2),
        (funcionarios[4], "bom",    4, 3, 2, 4),
        (funcionarios[5], "neutro", 3, 3, 3, 3),
    ]
    for func, humor, sf, sm, ne, st in checkins_demo:
        try:
            from django.db import transaction as _tx
            with _tx.atomic():
                CheckinBemEstar.objects.create(
                    empresa=empresa, funcionario=func,
                    humor=humor, saude_fisica=sf, saude_mental=sm,
                    nivel_estresse=ne, satisfacao_trabalho=st,
                )
            criados.append("checkin_bem_estar")
        except Exception:
            pass

    # ── Postos de trabalho + EPCs ─────────────────────────────────────────────
    postos_demo = [
        ("Operador de Produção — Linha Demo", "Produção",
         "Operação de prensas e linha de montagem"),
        ("Técnico de Manutenção Elétrica",    "Manutenção",
         "Manutenção preventiva/corretiva de painéis elétricos"),
    ]
    posto_objs_d = []
    for nome_p, setor_p, desc_p in postos_demo:
        p, created = PostoTrabalho.objects.get_or_create(
            empresa=empresa, nome=nome_p,
            defaults={
                "setor": setor_p, "descricao": desc_p,
                "responsavel_tecnico": "Eng. Marcos Demo Segurança",
                "responsavel_registro": "CREA/SP 987654",
                "data_laudo": hoje - timedelta(days=30),
                "vigencia_inicio": (hoje - timedelta(days=30)).strftime("%Y-%m"),
                "ativo": True,
            },
        )
        posto_objs_d.append(p)
        if created:
            criados.append("posto_trabalho")

    agentes_por_posto_d = [
        [("fisico", "01.01.001", "Ruído contínuo — prensas hidráulicas",
          "Sonômetro ABNT NBR ISO 9612", "87 dB(A)", "85 dB(A) NR-15",
          "Enclausuramento acústico e damper de vibração instalados", True,
          "Protetor Auditivo Plug Espuma (CA Demo)", "43210", True)],
        [("fisico", "01.04.001", "Risco elétrico — painéis média tensão",
          "Mapeamento risco NR-10", "13,8 kV", "≤1.000V c/ EPC",
          "Bloqueio LOTO obrigatório; barreiras dielétricas nos painéis", True,
          "Luva Dielétrica Classe 0; Botina Antiestática (CA Demo)", "87654", True)],
    ]
    for posto, agentes_l in zip(posto_objs_d, agentes_por_posto_d):
        for ag in agentes_l:
            try:
                AgenteNocivoPostoTrabalho.objects.get_or_create(
                    posto=posto, cod_agente=ag[1],
                    defaults=dict(
                        tipo_agente=ag[0], dsc_agente=ag[2],
                        tec_medicao=ag[3], intensidade=ag[4], limite_tolerancia=ag[5],
                        epc_descricao=ag[6], epc_eficaz=ag[7],
                        epi_descricao=ag[8], epi_ca=ag[9], epi_eficaz=ag[10],
                    ),
                )
                criados.append("agente_nocivo")
            except Exception:
                pass

    if posto_objs_d:
        for func in funcionarios[:2]:
            try:
                FuncionarioPostoTrabalho.objects.get_or_create(
                    funcionario=func,
                    posto=posto_objs_d[0],
                    data_inicio=func.data_admissao or hoje - timedelta(days=90),
                )
                criados.append("funcionario_posto")
            except Exception:
                pass

    # ── Clínica credenciada demo ──────────────────────────────────────────────
    try:
        clinica_demo, created = ClinicaCredenciada.objects.get_or_create(
            cnpj="00.100.200/0001-DEMO",
            defaults={
                "nome": "Clínica Medicina Ocupacional Demo",
                "tipo": "clinica_ocupacional",
                "especialidades": ["audiometria", "espirometria", "hemograma", "acuidade_visual", "ecg"],
                "cidade": "São Paulo", "uf": "SP", "cep": "01310-000",
                "endereco": "Av. Demo Empresarial, 1000 — Centro",
                "telefone": "(11) 3000-1000",
                "email": "clinica@demo.soluscrt.com",
                "responsavel_tecnico": "Dr. Demo Ocupacional",
                "crm": "CRM/SP 000001",
                "horario_atendimento": "Seg–Sex 07h–18h",
                "aceita_agendamento_online": True,
                "tempo_medio_laudo_dias": 2,
                "avaliacao_media": "4.9",
                "total_avaliacoes": 99,
                "status_credenciamento": "ativo",
                "ativa": True,
            },
        )
        if created:
            criados.append("clinica_credenciada")
            try:
                VinculoClinicaEmpresa.objects.get_or_create(
                    clinica=empresa,
                    empresa_contratante=empresa,
                    defaults={
                        "empresa_nome": clinica_demo.nome,
                        "empresa_email_convite": clinica_demo.email,
                        "status": "ativo",
                        "observacoes": "Clínica credenciada demo — SolusCRT",
                    },
                )
                criados.append("vinculo_clinica")
            except Exception:
                pass
    except Exception:
        pass

    # ── 2 eSocial extras → esocial capacidade: total>=6/alvo=6 → 100% ────────
    esocial_extras = [
        ("S-2240", "ambientes-risco-ghe-demo", "pendente",
         "<eSocial demo='true' evento='S-2240' ghe='Linha de Producao' />"),
        ("S-2220", "aso-admissional-2-demo",   "enviado",
         "<eSocial demo='true' evento='S-2220' tipo='admissional' />"),
    ]
    for tipo_ev, ref_ev, status_ev, xml_ev in esocial_extras:
        _, created = eSocialEventoSST.objects.get_or_create(
            empresa=empresa,
            tipo_evento=tipo_ev,
            referencia=ref_ev,
            defaults={"status": status_ev, "xml_gerado": xml_ev},
        )
        if created:
            criados.append(f"esocial_extra_{tipo_ev}")

    return criados


def _seed_plano_saude(empresa):
    hoje = timezone.localdate()
    agora = timezone.now()
    criados = []

    plano, created = PlanoSaude.objects.get_or_create(
        empresa=empresa,
        nome="Operadora Demo Prime",
        defaults={
            "registro_ans": "123456",
            "cnpj": "00.000.000/0001-99",
            "modalidade": "seguradora",
            "telefone": "(11) 4000-2200",
            "email": "operacao.demo@plano.local",
            "abrangencia": "nacional",
        },
    )
    if created:
        criados.append("plano_saude")

    beneficiarios_demo = [
        {
            "cpf": "000.000.000-21",
            "nome": "Alice Carteira",
            "numero_carteirinha": "PS-0001",
            "sexo": "F",
            "telefone": "(11) 99999-2101",
            "email": "alice@demo.local",
            "situacao": BeneficiarioPlano.SITUACAO_ATIVO,
            "acomodacao": "apartamento",
        },
        {
            "cpf": "000.000.000-22",
            "nome": "Bruno Elegibilidade",
            "numero_carteirinha": "PS-0002",
            "sexo": "M",
            "telefone": "(11) 99999-2202",
            "situacao": BeneficiarioPlano.SITUACAO_ATIVO,
            "acomodacao": "enfermaria",
        },
        {
            "cpf": "000.000.000-23",
            "nome": "Clara Jornada",
            "numero_carteirinha": "PS-0003",
            "sexo": "F",
            "email": "clara@demo.local",
            "situacao": BeneficiarioPlano.SITUACAO_SUSPENSO,
            "acomodacao": "uti",
        },
    ]
    beneficiarios = []
    for idx, item in enumerate(beneficiarios_demo, start=1):
        beneficiario, created = BeneficiarioPlano.objects.get_or_create(
            plano=plano,
            cpf=item["cpf"],
            defaults={
                "nome": item["nome"],
                "numero_carteirinha": item["numero_carteirinha"],
                "data_nascimento": hoje - timedelta(days=365 * (28 + idx)),
                "sexo": item["sexo"],
                "telefone": item.get("telefone", ""),
                "email": item.get("email", ""),
                "data_inicio_vigencia": hoje - timedelta(days=120 + idx),
                "situacao": item["situacao"],
                "plano_tipo": "Coletivo empresarial",
                "acomodacao": item["acomodacao"],
            },
        )
        if created:
            criados.append(f"beneficiario:{idx}")
        beneficiarios.append(beneficiario)

    prestadores_demo = [
        {
            "codigo_rede": "PR-HOSP-001",
            "nome_fantasia": "Hospital Referencia Demo",
            "tipo": PrestadorPlanoSaude.TIPO_HOSPITAL,
            "cidade": "Sao Paulo",
            "estado": "SP",
            "sla_autorizacao_horas": 24,
            "score_qualidade": 93,
            "especialidades": "Clinica medica, urgencia, imagem",
        },
        {
            "codigo_rede": "PR-CLIN-002",
            "nome_fantasia": "Clinica Especializada Demo",
            "tipo": PrestadorPlanoSaude.TIPO_CLINICA,
            "cidade": "Barueri",
            "estado": "SP",
            "sla_autorizacao_horas": 48,
            "score_qualidade": 88,
            "especialidades": "Ortopedia, fisiatria, reabilitacao",
        },
        {
            "codigo_rede": "PR-LAB-003",
            "nome_fantasia": "Laboratorio Rede Demo",
            "tipo": PrestadorPlanoSaude.TIPO_LABORATORIO,
            "cidade": "Osasco",
            "estado": "SP",
            "sla_autorizacao_horas": 12,
            "score_qualidade": 91,
            "especialidades": "Diagnostico, exames de imagem e laboratorio",
        },
    ]
    prestadores = []
    for idx, item in enumerate(prestadores_demo, start=1):
        prestador, created = PrestadorPlanoSaude.objects.get_or_create(
            empresa=empresa,
            codigo_rede=item["codigo_rede"],
            defaults={
                "nome_fantasia": item["nome_fantasia"],
                "razao_social": item["nome_fantasia"] + " LTDA",
                "cnpj": f"00.000.000/000{idx}-0{idx}",
                "tipo": item["tipo"],
                "registro_cnes": f"CNES-DEMO-{idx:03d}",
                "cidade": item["cidade"],
                "estado": item["estado"],
                "telefone": "(11) 4000-3300",
                "email": f"portal{idx}@prestador.demo",
                "contato_responsavel": f"Gestor Operacional {idx}",
                "sla_autorizacao_horas": item["sla_autorizacao_horas"],
                "portal_ativo": True,
                "score_qualidade": item["score_qualidade"],
                "especialidades": item["especialidades"],
                "status": PrestadorPlanoSaude.STATUS_CREDENCIADO,
            },
        )
        if created:
            criados.append(f"prestador:{idx}")
        prestadores.append(prestador)

    guia_autorizada, created = GuiaAutorizacao.objects.get_or_create(
        plano=plano,
        beneficiario=beneficiarios[0],
        numero_guia="GUIA-DEMO-001",
        defaults={
            "prestador": prestadores[2],
            "tipo": GuiaAutorizacao.TIPO_EXAME,
            "codigo_procedimento": "41001010",
            "descricao_procedimento": "Tomografia computadorizada de torax",
            "cid": "J18.9",
            "medico_solicitante": "Dra. Helena Demo",
            "crm_medico": "CRM/SP 123456",
            "quantidade": 1,
            "valor_estimado": "820.00",
            "status": GuiaAutorizacao.STATUS_AUTORIZADA,
            "prioridade_clinica": GuiaAutorizacao.PRIORIDADE_URGENTE,
            "fila_status": GuiaAutorizacao.FILA_AUTORIZADA,
            "auditor_responsavel": "Central de Regulacao Demo",
            "prazo_sla_em": agora - timedelta(hours=2),
            "numero_autorizacao": "AUTH-DEMO-001",
            "validade_autorizacao": hoje + timedelta(days=5),
        },
    )
    if created:
        criados.append("guia_autorizada")

    guia_negada, created = GuiaAutorizacao.objects.get_or_create(
        plano=plano,
        beneficiario=beneficiarios[1],
        numero_guia="GUIA-DEMO-002",
        defaults={
            "prestador": prestadores[1],
            "tipo": GuiaAutorizacao.TIPO_PROCEDIMENTO,
            "codigo_procedimento": "30101012",
            "descricao_procedimento": "Artroscopia com auditoria pendente",
            "cid": "M25.5",
            "medico_solicitante": "Dr. Caio Demo",
            "crm_medico": "CRM/SP 654321",
            "quantidade": 1,
            "valor_estimado": "2100.00",
            "status": GuiaAutorizacao.STATUS_NEGADA,
            "prioridade_clinica": GuiaAutorizacao.PRIORIDADE_ALTA_COMPLEXIDADE,
            "fila_status": GuiaAutorizacao.FILA_NEGADA,
            "auditor_responsavel": "Auditoria Clinica Demo",
            "justificativa_negativa": "Cobertura condicionada a protocolo clinico complementar.",
        },
    )
    if created:
        criados.append("guia_negada")

    guia_pendente, created = GuiaAutorizacao.objects.get_or_create(
        plano=plano,
        beneficiario=beneficiarios[0],
        numero_guia="GUIA-DEMO-003",
        defaults={
            "prestador": prestadores[0],
            "tipo": GuiaAutorizacao.TIPO_INTERNACAO,
            "codigo_procedimento": "71001099",
            "descricao_procedimento": "Internacao clinica com acompanhamento de custo",
            "cid": "I10",
            "medico_solicitante": "Dra. Helena Demo",
            "crm_medico": "CRM/SP 123456",
            "quantidade": 1,
            "valor_estimado": "4800.00",
            "status": GuiaAutorizacao.STATUS_SOLICITADA,
            "prioridade_clinica": GuiaAutorizacao.PRIORIDADE_INTERNACAO,
            "fila_status": GuiaAutorizacao.FILA_PENDENCIA_DOCUMENTAL,
            "auditor_responsavel": "Enf. Juliana Demo",
            "documentos_pendentes": "Laudo clinico e justificativa de internacao",
            "prazo_sla_em": agora - timedelta(hours=6),
        },
    )
    if created:
        criados.append("guia_pendente")
        GuiaAutorizacao.objects.filter(id=guia_pendente.id).update(
            solicitada_em=agora - timedelta(days=4)
        )

    sinistro, created = Sinistro.objects.get_or_create(
        empresa=empresa,
        plano=plano,
        beneficiario=beneficiarios[0],
        numero_sinistro="SIN-DEMO-001",
        defaults={
            "guia": guia_autorizada,
            "tipo": "exame",
            "status": "pago",
            "cid": "J18.9",
            "descricao_procedimento": "Tomografia concluida com pagamento aprovado",
            "prestador": "Hospital Referencia Demo",
            "medico": "Dra. Helena Demo",
            "data_atendimento": hoje - timedelta(days=3),
            "valor_total": "820.00",
            "valor_pago": "820.00",
            "observacao": "Sinistro demo pago para fechar o ciclo assistencial.",
            "data_fechamento": agora - timedelta(days=1),
        },
    )
    if created:
        criados.append("sinistro_pago")

    sinistro_aberto, created = Sinistro.objects.get_or_create(
        empresa=empresa,
        plano=plano,
        beneficiario=beneficiarios[1],
        numero_sinistro="SIN-DEMO-002",
        defaults={
            "guia": guia_negada,
            "tipo": "procedimento",
            "status": "em_analise",
            "cid": "M25.5",
            "descricao_procedimento": "Procedimento em auditoria clinica e contratual",
            "prestador": "Clinica Especializada Demo",
            "medico": "Dr. Caio Demo",
            "data_atendimento": hoje - timedelta(days=1),
            "valor_total": "2100.00",
            "observacao": "Sinistro em analise para demonstrar glosa e auditoria.",
        },
    )
    if created:
        criados.append("sinistro_em_analise")

    reembolso_pago, created = Reembolso.objects.get_or_create(
        empresa=empresa,
        plano=plano,
        beneficiario=beneficiarios[0],
        numero_reembolso="REE-DEMO-001",
        defaults={
            "sinistro": sinistro,
            "tipo_despesa": "consulta",
            "status": "pago",
            "valor_solicitado": "320.00",
            "valor_aprovado": "320.00",
            "valor_pago": "320.00",
            "data_pagamento": hoje - timedelta(days=1),
            "banco": "Banco Demo",
            "agencia": "0001",
            "conta": "12345-6",
            "descricao": "Livre escolha concluida",
        },
    )
    if created:
        criados.append("reembolso_pago")

    reembolso_analise, created = Reembolso.objects.get_or_create(
        empresa=empresa,
        plano=plano,
        beneficiario=beneficiarios[1],
        numero_reembolso="REE-DEMO-002",
        defaults={
            "sinistro": sinistro_aberto,
            "tipo_despesa": "exame",
            "status": "em_analise",
            "valor_solicitado": "540.00",
            "banco": "Banco Demo",
            "agencia": "0001",
            "conta": "12345-6",
            "descricao": "Reembolso em auditoria documental",
        },
    )
    if created:
        criados.append("reembolso_em_analise")

    sinais_demo = [
        {
            "device_id": "ps-epidemo-1",
            "doenca": "Influenza",
            "suspeito": True,
            "cidade": "Sao Paulo",
            "bairro": "Pinheiros",
            "latitude": -23.567,
            "longitude": -46.692,
            "febre": True,
            "tosse": True,
            "cansaco": True,
        },
        {
            "device_id": "ps-epidemo-2",
            "doenca": "Dengue",
            "suspeito": True,
            "cidade": "Sao Paulo",
            "bairro": "Butanta",
            "latitude": -23.569,
            "longitude": -46.721,
            "febre": True,
            "dor_corpo": True,
            "cansaco": True,
        },
        {
            "device_id": "ps-epidemo-3",
            "doenca": "Virose",
            "suspeito": False,
            "cidade": "Osasco",
            "bairro": "Centro",
            "latitude": -23.532,
            "longitude": -46.791,
            "tosse": True,
            "cansaco": True,
        },
    ]
    for idx, item in enumerate(sinais_demo, start=1):
        _, created = RegistroSintoma.objects.get_or_create(
            empresa=empresa,
            device_id=item["device_id"],
            defaults={
                "doenca": item["doenca"],
                "suspeito": item["suspeito"],
                "origem_dado": RegistroSintoma.ORIGEM_INSTITUCIONAL,
                "fonte_referencia": "seed_operadora_demo",
                "revisado": True,
                "cidade": item["cidade"],
                "bairro": item["bairro"],
                "estado": "SP",
                "pais": "Brasil",
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "febre": item.get("febre", False),
                "tosse": item.get("tosse", False),
                "dor_corpo": item.get("dor_corpo", False),
                "cansaco": item.get("cansaco", False),
            },
        )
        if created:
            criados.append(f"registro_epi:{idx}")

    # ── Expansão para atingir 100% nas 8 capacidades do plano ────────────────
    agora = timezone.now()

    # elegibilidade: planos_ativos + beneficiarios_ativos >= 12
    # Adiciona 2 planos + 9 beneficiarios ativos extra = total 3 planos + 11 ben. ativos = 14 >= 12
    plano2, created = PlanoSaude.objects.get_or_create(
        empresa=empresa, nome="Plano Empresarial Demo",
        defaults={"registro_ans": "234567", "modalidade": "autogestao", "abrangencia": "estadual",
                  "status": PlanoSaude.STATUS_ATIVO},
    )
    if created: criados.append("plano2")
    plano3, created = PlanoSaude.objects.get_or_create(
        empresa=empresa, nome="Plano Individual Demo",
        defaults={"registro_ans": "345678", "modalidade": "cooperativa", "abrangencia": "nacional",
                  "status": PlanoSaude.STATUS_ATIVO},
    )
    if created: criados.append("plano3")

    benef_extra_data = [
        ("000.000.000-31", "Fernando Rede Demo",  "M", 30, "PS-EX-001", BeneficiarioPlano.SITUACAO_ATIVO,  "apartamento", "fernando@demo.local", "(11) 99001-0001"),
        ("000.000.000-32", "Gabriela Plano Demo", "F", 25, "PS-EX-002", BeneficiarioPlano.SITUACAO_ATIVO,  "enfermaria",  "gabriela@demo.local", "(11) 99001-0002"),
        ("000.000.000-33", "Henrique VC Demo",    "M", 45, "PS-EX-003", BeneficiarioPlano.SITUACAO_ATIVO,  "apartamento", "henrique@demo.local", "(11) 99001-0003"),
        ("000.000.000-34", "Isabela Cobertura",   "F", 38, "PS-EX-004", BeneficiarioPlano.SITUACAO_ATIVO,  "enfermaria",  "isabela@demo.local",  "(11) 99001-0004"),
        ("000.000.000-35", "Joao Elegib Demo",    "M", 52, "PS-EX-005", BeneficiarioPlano.SITUACAO_ATIVO,  "apartamento", "joao@demo.local",     "(11) 99001-0005"),
        ("000.000.000-36", "Karla Sinistro Demo", "F", 29, "PS-EX-006", BeneficiarioPlano.SITUACAO_ATIVO,  "enfermaria",  "karla@demo.local",    "(11) 99001-0006"),
        ("000.000.000-37", "Lucas Reemb Demo",    "M", 41, "PS-EX-007", BeneficiarioPlano.SITUACAO_ATIVO,  "apartamento", "lucas@demo.local",    "(11) 99001-0007"),
        ("000.000.000-38", "Marina Fatura Demo",  "F", 33, "PS-EX-008", BeneficiarioPlano.SITUACAO_ATIVO,  "enfermaria",  "marina@demo.local",   "(11) 99001-0008"),
        ("000.000.000-39", "Nadia Epidem Demo",   "F", 27, "PS-EX-009", BeneficiarioPlano.SITUACAO_SUSPENSO,"enfermaria", "",                    "(11) 99001-0009"),
    ]
    beneficiarios_extra = []
    planos_ciclo = [plano, plano2, plano3]
    for idx_be, (cpf_be, nome_be, sexo_be, idade_be, cart_be, sit_be, acomo_be, email_be, tel_be) in enumerate(benef_extra_data):
        plano_be = planos_ciclo[idx_be % len(planos_ciclo)]
        ben_e, created = BeneficiarioPlano.objects.get_or_create(
            plano=plano_be, cpf=cpf_be,
            defaults={"nome": nome_be, "sexo": sexo_be,
                      "data_nascimento": hoje - timedelta(days=365 * idade_be),
                      "numero_carteirinha": cart_be,
                      "data_inicio_vigencia": hoje - timedelta(days=200 + idx_be * 10),
                      "situacao": sit_be, "plano_tipo": "Coletivo",
                      "acomodacao": acomo_be, "email": email_be, "telefone": tel_be},
        )
        beneficiarios_extra.append(ben_e)
        if created: criados.append(f"benef_extra_{idx_be+1}")

    # rede: prestadores_ativos + prestadores_portal >= 10
    prestadores_extra_data = [
        ("PR-LAB-004", "Laboratorio Central Demo",      PrestadorPlanoSaude.TIPO_LABORATORIO,  "Santo Andre", "SP", 8,  92, True),
        ("PR-IMG-005", "Clinica de Imagem Demo",        PrestadorPlanoSaude.TIPO_IMAGEM,       "Sao Paulo",   "SP", 12, 89, True),
        ("PR-PA-006",  "Pronto Atendimento Demo",       PrestadorPlanoSaude.TIPO_PRONTO_ATEND, "Campinas",    "SP", 4,  95, False),
        ("PR-HC-007",  "Homecare Especializado Demo",   PrestadorPlanoSaude.TIPO_HOMECARE,     "Sao Paulo",   "SP", 48, 87, True),
    ]
    for idx_pe, (cod_pe, nome_pe, tipo_pe, cid_pe, uf_pe, sla_pe, score_pe, portal_pe) in enumerate(prestadores_extra_data, 4):
        _, created = PrestadorPlanoSaude.objects.get_or_create(
            empresa=empresa, codigo_rede=cod_pe,
            defaults={
                "nome_fantasia": nome_pe, "razao_social": nome_pe + " LTDA",
                "cnpj": f"00.000.001/000{idx_pe}-0{idx_pe}",
                "tipo": tipo_pe, "registro_cnes": f"CNES-EX-{idx_pe:03d}",
                "cidade": cid_pe, "estado": uf_pe, "telefone": "(11) 4001-0000",
                "email": f"portal{idx_pe}@prestador.demo",
                "contato_responsavel": f"Gestor {idx_pe}",
                "sla_autorizacao_horas": sla_pe, "portal_ativo": portal_pe,
                "score_qualidade": score_pe,
                "status": PrestadorPlanoSaude.STATUS_CREDENCIADO,
            },
        )
        if created: criados.append(f"prestador_extra_{idx_pe}")

    # autorizacao / sinistralidade: mais guias e sinistros
    todos_prestadores = list(prestadores) if prestadores else []
    todos_beneficiarios = list(beneficiarios) + list(beneficiarios_extra)
    guias_extra_data = [
        ("GUIA-EXT-001", 0, GuiaAutorizacao.TIPO_EXAME,       "40305010", "Ressonancia magnetica",       "M54.5", GuiaAutorizacao.STATUS_AUTORIZADA, GuiaAutorizacao.PRIORIDADE_ELETIVA),
        ("GUIA-EXT-002", 1, GuiaAutorizacao.TIPO_CONSULTA,    "10101013", "Consulta ortopedia",          "M25.5", GuiaAutorizacao.STATUS_AUTORIZADA, GuiaAutorizacao.PRIORIDADE_ELETIVA),
        ("GUIA-EXT-003", 2, GuiaAutorizacao.TIPO_PROCEDIMENTO,"30601023", "Artroscopia joelho",          "M23.6", GuiaAutorizacao.STATUS_EM_ANALISE, GuiaAutorizacao.PRIORIDADE_URGENTE),
        ("GUIA-EXT-004", 3, GuiaAutorizacao.TIPO_EXAME,       "40101010", "Colonoscopia",                "K57.3", GuiaAutorizacao.STATUS_AUTORIZADA, GuiaAutorizacao.PRIORIDADE_ELETIVA),
        ("GUIA-EXT-005", 4, GuiaAutorizacao.TIPO_INTERNACAO,  "71001098", "Internacao cirurgica",        "K80.2", GuiaAutorizacao.STATUS_AUTORIZADA, GuiaAutorizacao.PRIORIDADE_URGENTE),
    ]
    prestador_ext = todos_prestadores[0] if todos_prestadores else None
    for num_ge, ben_idx_ge, tipo_ge, cod_ge, desc_ge, cid_ge, status_ge, prio_ge in guias_extra_data:
        if ben_idx_ge >= len(todos_beneficiarios):
            continue
        _, created = GuiaAutorizacao.objects.get_or_create(
            plano=planos_ciclo[ben_idx_ge % len(planos_ciclo)],
            beneficiario=todos_beneficiarios[ben_idx_ge],
            numero_guia=num_ge,
            defaults={
                "prestador": prestador_ext,
                "tipo": tipo_ge, "codigo_procedimento": cod_ge,
                "descricao_procedimento": desc_ge, "cid": cid_ge,
                "medico_solicitante": "Dr. Demo Plano Extra", "crm_medico": "CRM/SP 200000",
                "quantidade": 1, "status": status_ge,
                "prioridade_clinica": prio_ge,
                "fila_status": GuiaAutorizacao.FILA_AUTORIZADA if status_ge == GuiaAutorizacao.STATUS_AUTORIZADA else GuiaAutorizacao.FILA_AUDITORIA_CLINICA,
                "auditor_responsavel": "Regulacao Demo",
            },
        )
        if created: criados.append(f"guia_ext_{num_ge}")

    # sinistralidade: sinistros + sinistros_pagos >= 10
    sinistros_extra_data = [
        ("SIN-EXT-001", 3, "exame",      "em_analise", "M54.5", "500.00",  ""),
        ("SIN-EXT-002", 4, "consulta",   "pago",       "M25.5", "320.00",  "320.00"),
        ("SIN-EXT-003", 5, "internacao", "pago",       "K80.2", "8500.00", "8500.00"),
        ("SIN-EXT-004", 6, "exame",      "pago",       "K57.3", "1200.00", "1200.00"),
        ("SIN-EXT-005", 7, "procedimento","em_analise","M23.6", "3500.00", ""),
        ("SIN-EXT-006", 8, "consulta",   "pago",       "J18.9", "280.00",  "280.00"),
    ]
    for num_se, ben_idx_se, tipo_se, status_se, cid_se, val_se, pago_se in sinistros_extra_data:
        if ben_idx_se >= len(todos_beneficiarios):
            continue
        ben_se = todos_beneficiarios[ben_idx_se]
        _, created = Sinistro.objects.get_or_create(
            empresa=empresa,
            plano=planos_ciclo[ben_idx_se % len(planos_ciclo)],
            beneficiario=ben_se,
            numero_sinistro=num_se,
            defaults={
                "tipo": tipo_se, "status": status_se, "cid": cid_se,
                "descricao_procedimento": f"Procedimento demo {num_se}",
                "prestador": "Prestador Demo Extra", "medico": "Dr. Demo Plano",
                "data_atendimento": hoje - timedelta(days=5 + ben_idx_se),
                "valor_total": val_se,
                "valor_pago": pago_se if pago_se else None,
                "observacao": "Sinistro demo expansao plano saude.",
            },
        )
        if created: criados.append(f"sinistro_ext_{num_se}")

    # reembolso: reembolsos + reembolsos_pagos >= 8
    reembolsos_extra_data = [
        ("REE-EXT-001", 3, "consulta",   "pago",      "180.00", "180.00", "180.00", hoje - timedelta(days=3)),
        ("REE-EXT-002", 4, "exame",      "pago",      "450.00", "450.00", "450.00", hoje - timedelta(days=5)),
        ("REE-EXT-003", 5, "consulta",   "em_analise","220.00", "",       "",        None),
    ]
    for num_re, ben_idx_re, tipo_re, status_re, sol_re, apr_re, pago_re_v, data_pag_re in reembolsos_extra_data:
        if ben_idx_re >= len(todos_beneficiarios):
            continue
        ben_re = todos_beneficiarios[ben_idx_re]
        _, created = Reembolso.objects.get_or_create(
            empresa=empresa,
            plano=planos_ciclo[ben_idx_re % len(planos_ciclo)],
            beneficiario=ben_re,
            numero_reembolso=num_re,
            defaults={
                "tipo_despesa": tipo_re, "status": status_re,
                "valor_solicitado": sol_re,
                "valor_aprovado": apr_re if apr_re else None,
                "valor_pago": pago_re_v if pago_re_v else None,
                "data_pagamento": data_pag_re,
                "banco": "Banco Demo", "agencia": "0001", "conta": "99999-9",
                "descricao": f"Reembolso livre escolha {num_re}",
            },
        )
        if created: criados.append(f"reembolso_ext_{num_re}")

    # epidemiologia: registros_epi_total + suspeitos >= 8 (ultimos 30 dias)
    epi_extra = [
        ("ps-epi-4", "Gripe", True,  -23.545, -46.634, True,  False, True),
        ("ps-epi-5", "Dengue", True,  -23.561, -46.655, True,  True,  False),
        ("ps-epi-6", "Covid", False, -23.532, -46.671, True,  True,  False),
        ("ps-epi-7", "Dengue", True,  -23.548, -46.698, False, True,  True),
        ("ps-epi-8", "Gripe", False, -23.571, -46.712, True,  False, True),
    ]
    for dev_id, doenca_e, suspeito_e, lat_e, lon_e, febre_e, dor_e, tosse_e in epi_extra:
        _, created = RegistroSintoma.objects.get_or_create(
            empresa=empresa, device_id=dev_id,
            defaults={
                "doenca": doenca_e, "suspeito": suspeito_e,
                "origem_dado": RegistroSintoma.ORIGEM_INSTITUCIONAL,
                "revisado": True, "cidade": "Sao Paulo", "estado": "SP",
                "bairro": "Centro", "pais": "Brasil",
                "latitude": lat_e, "longitude": lon_e,
                "febre": febre_e, "dor_corpo": dor_e, "tosse": tosse_e,
            },
        )
        if created: criados.append(f"epi_extra_{dev_id}")

    return criados


def _seed_governo(empresa):  # noqa: C901
    """Seed governo demo data to reach 100% on all 4 enterprise capacidades.

    Targets (from _suite_governo):
    - vigilancia  (ProgramaSaudeGov + IndicadorSaudeGov) >= 8  alvo=8
    - rede        (UnidadeSaude)                          >= 6  alvo=6
    - epidemiologia(RegistroSintoma recentes + AlertaGov) >= 8  alvo=8
    - gestao      (OrcamentoSaudeGov + PlanoAcaoGov)      >= 4  alvo=4
    """
    from api.models import (
        ProgramaSaudeGov, IndicadorSaudeGov, UnidadeSaude,
        AlertaGovernamental, OrcamentoSaudeGov, PlanoAcaoGov,
    )
    import uuid as _uuid
    import random as _rnd_gov

    criados = []
    hoje = timezone.localdate()

    # ── 1. Programas de Saude (5) → vigilancia parcial ────────────────────────
    programas_data = [
        ("Dengue Zero 2026",        "ativo",    2_800_000, 1_950_000, "Coord. Vigilância Epidemiológica", "Toda a população"),
        ("Vacinação em Dia",        "ativo",    1_200_000,   980_000, "Coord. Imunizações",              "Crianças 0-5 e adultos 60+"),
        ("Saude Mental na Rede",    "ativo",      850_000,   620_000, "Coord. Saude Mental",              "Populacao em sofrimento psiquico"),
        ("Rede Cegonha Municipal",  "ativo",    1_500_000, 1_100_000, "Coord. Saude da Mulher",           "Gestantes e puerperas"),
        ("Combate ao Tabagismo",    "ativo",      300_000,   210_000, "Coord. Promocao Saude",            "Adultos fumantes"),
    ]
    programas = []
    for nome_p, status_p, orc_prev, orc_exec, resp_p, pop_p in programas_data:
        prog, created = ProgramaSaudeGov.objects.get_or_create(
            empresa=empresa, nome=nome_p,
            defaults={
                "descricao": f"Programa demo: {nome_p}.",
                "status": status_p,
                "orcamento_previsto": orc_prev,
                "orcamento_executado": orc_exec,
                "responsavel": resp_p,
                "populacao_alvo": pop_p,
                "data_inicio": hoje.replace(month=1, day=1),
                "data_fim_prevista": hoje.replace(month=12, day=31),
            },
        )
        programas.append(prog)
        if created: criados.append(f"programa_{nome_p[:10]}")

    # ── 2. Indicadores (6) → vigilancia: total programs+indicadores=11 >= 8 ──
    indicadores_data = [
        ("Cobertura Vacinal Poliomielite", "percentual",   95,  87.3, "%"),
        ("Taxa de Incidencia de Dengue",   "quantitativo",  2,   5.4, "/100k hab"),
        ("Cobertura de eSF",              "percentual",   80,  64.2, "%"),
        ("Taxa de Mortalidade Infantil",   "quantitativo",  8,  11.2, "/1000 NV"),
        ("Internacoes por Causas Exter.",  "quantitativo", 15,  18.7, "/10k hab"),
        ("Cobertura Vacinal Influenza",   "percentual",   90,  78.4, "%"),
    ]
    for nome_i, tipo_i, meta_i, val_i, unid_i in indicadores_data:
        _, created = IndicadorSaudeGov.objects.get_or_create(
            empresa=empresa, nome=nome_i,
            defaults={"tipo": tipo_i, "meta": meta_i, "valor_atual": val_i,
                      "unidade": unid_i, "periodo_referencia": str(hoje.year)},
        )
        if created: criados.append(f"indicador_{nome_i[:12]}")

    # ── 3. Unidades de Saude (8) → rede: 8/6 → 100% ─────────────────────────
    unidades_data = [
        ("2079798", "UBS Jardim Sao Paulo",   "ubs",         "Sao Paulo", -23.5450, -46.6310),
        ("2079844", "UPA 24h Lapa",           "upa",         "Sao Paulo", -23.5337, -46.7070),
        ("2079871", "CAPS II Pinheiros",      "caps_ii",     "Sao Paulo", -23.5678, -46.6923),
        ("2079899", "Hospital Municipal",     "hospital",    "Sao Paulo", -23.5489, -46.6388),
        ("2080001", "UBS Vila Prudente",      "ubs",         "Sao Paulo", -23.5915, -46.5660),
        ("2080002", "UPA Zona Norte",         "upa",         "Sao Paulo", -23.4860, -46.6120),
        ("2080003", "CEO Dentario Demo",      "ceo",         "Sao Paulo", -23.5510, -46.6340),
        ("2080004", "Policlinica Regional",   "policlinica", "Sao Paulo", -23.5613, -46.6559),
    ]
    for cnes_u, nome_u, tipo_u, mun_u, lat_u, lon_u in unidades_data:
        _, created = UnidadeSaude.objects.get_or_create(
            empresa=empresa, nome=nome_u,
            defaults={"cnes": cnes_u, "tipo": tipo_u, "status": "ativa",
                      "municipio": mun_u, "uf": "SP", "latitude": lat_u, "longitude": lon_u},
        )
        if created: criados.append(f"unidade_{tipo_u[:4]}")

    # ── 4. Alertas (2) → epidemiologia parcial ────────────────────────────────
    alertas_data = [
        ("Aumento de Dengue — Zona Norte", "alto",     "SP", "Sao Paulo", "Zona Norte",
         "Aumento de 65% nos casos confirmados. Intensificar eliminacao de criadouros."),
        ("Alerta Influenza — Zona Leste",  "moderado", "SP", "Sao Paulo", "Zona Leste",
         "Incremento de sindrome gripal na faixa etaria 60+. Reforcar vacinacao."),
    ]
    for titulo_a, nivel_a, uf_a, cid_a, bairro_a, msg_a in alertas_data:
        _, created = AlertaGovernamental.objects.get_or_create(
            empresa=empresa, titulo=titulo_a,
            defaults={"mensagem": msg_a, "nivel": nivel_a, "estado": uf_a,
                      "cidade": cid_a, "bairro": bairro_a,
                      "ativo": True, "status": AlertaGovernamental.STATUS_PUBLICADO},
        )
        if created: criados.append(f"alerta_{nivel_a}")

    # ── 5. Registros de Sintoma (15) → epidemiologia: 15+2=17 >= 8 → 100% ───
    _rnd_gov.seed(42)
    doencas_g = ["dengue", "dengue", "dengue", "influenza", "influenza",
                 "covid", "covid", "dengue", "influenza", "covid",
                 "dengue", "influenza", "covid", "dengue", "influenza"]
    for i in range(15):
        try:
            RegistroSintoma.objects.create(
                empresa=empresa, id_anonimo=_uuid.uuid4(),
                doenca=doencas_g[i],
                febre=True, dor_cabeca=(i % 2 == 0), dor_corpo=(i % 3 != 0),
                cidade="Sao Paulo", estado="SP", bairro="Zona Norte",
                latitude=-23.51 + _rnd_gov.uniform(-0.05, 0.05),
                longitude=-46.64 + _rnd_gov.uniform(-0.05, 0.05),
                origem_dado="cidadao",
            )
            criados.append("sintoma")
        except Exception:
            pass

    # ── 6. Orcamento (1) + Planos de Acao (3) → gestao: 4/4 → 100% ─────────
    try:
        _, created = OrcamentoSaudeGov.objects.get_or_create(
            empresa=empresa, ano=hoje.year,
            defaults={
                "total_previsto": 48_000_000,
                "total_executado": 35_600_000,
                "fonte_recurso": "Transferencias federais + fundo municipal",
                "observacoes": "Orcamento demo 2026 — demonstracao de gestao financeira.",
            },
        )
        if created: criados.append("orcamento_2026")
    except Exception as exc_o:
        criados.append(f"erro_orcamento:{str(exc_o)[:40]}")

    planos_acao_g = [
        ("Intensificar mutiroes anti-Aedes",         programas[0] if programas else None, "alta", "em_andamento", 65),
        ("Campanha de vacinacao polio 0-5 anos",     programas[1] if len(programas) > 1 else None, "alta", "em_andamento", 45),
        ("Ampliacao de CAPS na Zona Leste",          programas[2] if len(programas) > 2 else None, "media", "pendente", 10),
    ]
    for titulo_pa, programa_pa, prio_pa, status_pa, prog_pa in planos_acao_g:
        _, created = PlanoAcaoGov.objects.get_or_create(
            empresa=empresa, titulo=titulo_pa,
            defaults={
                "programa": programa_pa, "prioridade": prio_pa,
                "status": status_pa, "progresso": prog_pa,
                "responsavel": "Secretaria Municipal de Saude",
                "prazo": hoje.replace(month=12, day=31),
                "descricao": f"Plano de acao demo: {titulo_pa}.",
            },
        )
        if created: criados.append(f"plano_acao_{prio_pa}")

    return criados


def seed_enterprise_operational_demo(empresa):
    setor = get_setor(empresa)
    if setor == "farmacia":
        criados = _seed_farmacia(empresa)
    elif setor == "hospital":
        criados = _seed_hospital(empresa)
    elif setor == "empresa":
        criados = _seed_empresa(empresa)
    elif setor == "plano_saude":
        criados = _seed_plano_saude(empresa)
    elif setor == "governo":
        criados = _seed_governo(empresa)
    else:
        criados = []
    return {"setor": setor, "criados": criados, "total_criado": len(criados)}


@api_requer_gerencia
def api_enterprise_command_center(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    return JsonResponse(build_enterprise_command_center_payload(empresa))


@api_requer_gerencia
def api_enterprise_premium_suite(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    return JsonResponse(build_enterprise_premium_suite_payload(empresa))


@csrf_exempt
@api_requer_gerencia
def api_enterprise_seed_operational_demo(request):
    import traceback as _tb
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "Metodo nao permitido"}, status=405)
    if not _demo_mutations_enabled(empresa):
        return JsonResponse({
            "erro": "Seed demo desativado neste ambiente. Use homologacao ou habilite ALLOW_ENTERPRISE_DEMO_MUTATIONS.",
        }, status=403)

    try:
        resultado = seed_enterprise_operational_demo(empresa)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("seed_enterprise_operational_demo error: %s\n%s", exc, _tb.format_exc())
        return JsonResponse({"erro": str(exc), "detalhe": _tb.format_exc()[-500:]}, status=500)

    try:
        resultado["suite"] = build_enterprise_premium_suite_payload(empresa)
    except Exception as exc:
        resultado["suite"] = {}
        resultado["suite_erro"] = str(exc)

    return JsonResponse(resultado)


# ──────────────────────────────────────────────────────────────────────────────
# RESET DEMO — apaga todos os registros de demonstração por setor
# ──────────────────────────────────────────────────────────────────────────────

def _reset_farmacia(empresa):
    """Remove todos os dados demo criados por _seed_farmacia."""
    removidos = 0
    # Itens e dispensações demo
    demo_items = ItemFarmacia.objects.filter(empresa=empresa, codigo__icontains="DEMO")
    removidos += demo_items.count()
    demo_items.delete()

    demo_meds = MedicamentoFarmacia.objects.filter(empresa=empresa, fabricante__icontains="Demo")
    removidos += demo_meds.count()
    demo_meds.delete()

    demo_lotes = LoteMedicamento.objects.filter(empresa=empresa, numero_lote__icontains="DEMO")
    removidos += demo_lotes.count()
    demo_lotes.delete()

    demo_pacs = PacienteFarmacia.objects.filter(empresa=empresa, cpf__startswith="000.000.000")
    removidos += demo_pacs.count()
    demo_pacs.delete()

    demo_inv = InventarioFarmacia.objects.filter(empresa=empresa, responsavel__icontains="Demo")
    removidos += demo_inv.count()
    demo_inv.delete()

    demo_ped = PedidoCompraFarmacia.objects.filter(empresa=empresa, observacoes__icontains="Demo")
    removidos += demo_ped.count()
    demo_ped.delete()

    demo_forn = FornecedorFarmaciaGestao.objects.filter(empresa=empresa, nome__icontains="Demo")
    removidos += demo_forn.count()
    demo_forn.delete()

    demo_forn2 = FornecedorFarmacia.objects.filter(empresa=empresa, nome__icontains="Demo")
    removidos += demo_forn2.count()
    demo_forn2.delete()

    return removidos


def _reset_hospital(empresa):
    """Remove todos os dados demo criados por _seed_hospital."""
    removidos = 0

    demo_leitos = LeitoHospitalar.objects.filter(empresa=empresa, numero__icontains="DEMO")
    removidos += demo_leitos.count()
    demo_leitos.delete()

    demo_pacs = PacienteHospital.objects.filter(empresa=empresa, cpf__startswith="000.000.000")
    removidos += demo_pacs.count()
    demo_pacs.delete()

    demo_deps = DepartamentoHospital.objects.filter(empresa=empresa, nome__icontains="Demo")
    removidos += demo_deps.count()
    demo_deps.delete()

    return removidos


def _reset_empresa(empresa):
    """Remove dados demo da empresa SST/corporativo."""
    removidos = 0

    demo_funcs = FuncionarioSST.objects.filter(empresa=empresa, cpf__startswith="000.000.000")
    removidos += demo_funcs.count()
    demo_funcs.delete()

    demo_trein = TreinamentoNR.objects.filter(empresa=empresa, instrutor__icontains="Demo")
    removidos += demo_trein.count()
    demo_trein.delete()

    demo_aso = ASOOcupacional.objects.filter(empresa=empresa, medico__icontains="Demo")
    removidos += demo_aso.count()
    demo_aso.delete()

    demo_epi = EPIItem.objects.filter(empresa=empresa, ca__icontains="DEMO")
    removidos += demo_epi.count()
    demo_epi.delete()

    demo_risco = RiscoOcupacional.objects.filter(empresa=empresa, descricao__icontains="Demo")
    removidos += demo_risco.count()
    demo_risco.delete()

    return removidos


def _reset_plano_saude(empresa):
    """Remove dados demo criados por _seed_plano_saude."""
    from .models import GlosaItem, CoparticipacaoRegra, FaturamentoBeneficiario, ProgramaSaude, InscricaoPrograma
    removidos = 0

    demo_planos = PlanoSaude.objects.filter(empresa=empresa, nome__icontains="Demo")
    for plano in demo_planos:
        # Cascade: beneficiarios → sinistros → guias → glosas
        beneficiarios = BeneficiarioPlano.objects.filter(plano=plano)
        for ben in beneficiarios:
            sinistros = Sinistro.objects.filter(beneficiario=ben)
            for sin in sinistros:
                g = GlosaItem.objects.filter(sinistro=sin)
                removidos += g.count(); g.delete()
                guias = GuiaAutorizacao.objects.filter(sinistro=sin)
                removidos += guias.count(); guias.delete()
            fat = FaturamentoBeneficiario.objects.filter(beneficiario=ben)
            removidos += fat.count(); fat.delete()
            insc = InscricaoPrograma.objects.filter(beneficiario=ben)
            removidos += insc.count(); insc.delete()
            removidos += sinistros.count(); sinistros.delete()
        cop = CoparticipacaoRegra.objects.filter(plano=plano)
        removidos += cop.count(); cop.delete()
        prog = ProgramaSaude.objects.filter(empresa=empresa, nome__icontains="Demo")
        removidos += prog.count(); prog.delete()
        prest = PrestadorPlanoSaude.objects.filter(plano=plano, nome_fantasia__icontains="Demo")
        removidos += prest.count(); prest.delete()
        removidos += beneficiarios.count(); beneficiarios.delete()

    removidos += demo_planos.count()
    demo_planos.delete()
    return removidos


def reset_enterprise_demo(empresa):
    """Dispatcher de reset por setor."""
    setor = get_setor(empresa)
    if setor == "farmacia":
        removidos = _reset_farmacia(empresa)
    elif setor == "hospital":
        removidos = _reset_hospital(empresa)
    elif setor == "empresa":
        removidos = _reset_empresa(empresa)
    elif setor == "plano_saude":
        removidos = _reset_plano_saude(empresa)
    else:
        removidos = 0
    return {"setor": setor, "removidos": removidos}


@csrf_exempt
@api_requer_gerencia
def api_enterprise_reset_demo(request):
    """
    POST /api/enterprise/reset-demo
    Apaga todos os dados de demonstração do ambiente logado.
    """
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "Metodo nao permitido"}, status=405)
    if not _demo_mutations_enabled(empresa):
        return JsonResponse({
            "erro": "Reset demo desativado neste ambiente. Use homologacao ou habilite ALLOW_ENTERPRISE_DEMO_MUTATIONS.",
        }, status=403)

    resultado = reset_enterprise_demo(empresa)
    resultado["suite"] = build_enterprise_premium_suite_payload(empresa)
    return JsonResponse(resultado)
