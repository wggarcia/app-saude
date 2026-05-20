from datetime import timedelta
import unicodedata

from django.db.models import F, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .access_control import get_setor
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
    Sinistro,
    TreinamentoNR,
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
    return criados


def _seed_hospital(empresa):
    hoje = timezone.localdate()
    agora = timezone.now()
    criados = []
    dep, created = DepartamentoHospital.objects.get_or_create(
        empresa=empresa,
        nome="Emergencia Demo",
        defaults={"tipo": "emergencia", "capacidade_leitos": 12, "responsavel": "Coord. Demo"},
    )
    if created:
        criados.append("departamento")
    leito, created = LeitoHospitalar.objects.get_or_create(
        empresa=empresa,
        numero="E-DEMO-01",
        defaults={"ala": dep.nome, "tipo": "emergencia", "status": "ocupado", "paciente_nome": "Paciente Hospital Demo", "data_internacao": hoje, "previsao_alta": hoje + timedelta(days=2)},
    )
    if created:
        criados.append("leito")
    leito_classico, created = LeitoHospital.objects.get_or_create(
        empresa=empresa,
        departamento=dep,
        numero="E-CL-01",
        defaults={"tipo": "observacao", "status": "ocupado"},
    )
    if created:
        criados.append("leito_classico")
    paciente_classico, created = PacienteHospital.objects.get_or_create(
        empresa=empresa,
        cpf="000.000.000-94",
        defaults={"nome": "Paciente Clinico Demo", "data_nascimento": hoje - timedelta(days=14000), "sexo": "O", "telefone": "(11) 98888-0000", "endereco": "Rua Demo, 100", "tipo_sanguineo": "O+", "alergias": "Dipirona"},
    )
    if created:
        criados.append("paciente_hospital")
    triagem, created = TriagemManchester.objects.get_or_create(
        empresa=empresa,
        paciente_nome="Paciente Hospital Demo",
        data_hora=agora,
        defaults={"paciente_cpf": "000.000.000-92", "queixa_principal": "Dor toracica e falta de ar", "nivel": "laranja", "tempo_espera_minutos": 12, "status": "em_atendimento", "medico_responsavel": "Dr. Demo Emergencia"},
    )
    if created:
        criados.append("triagem")
    triagem_classica, created = TriagemHospital.objects.get_or_create(
        empresa=empresa,
        paciente=paciente_classico,
        prioridade="amarelo",
        defaults={"queixa_principal": "Febre persistente e dor abdominal", "pressao_arterial": "130x80", "temperatura": "38.2", "saturacao": 96, "frequencia_cardiaca": 92, "responsavel": "Enf. Demo"},
    )
    if created:
        criados.append("triagem_classica")
    paciente, created = PacienteInternado.objects.get_or_create(
        empresa=empresa,
        cpf="000.000.000-92",
        defaults={"nome": "Paciente Hospital Demo", "data_internacao": hoje, "leito": leito, "diagnostico_cid": "R07", "medico_responsavel": "Dr. Demo Emergencia", "convenio": "Plano Demo", "status": "internado"},
    )
    if created:
        criados.append("internacao")
    internacao_classica, created = InternacaoHospital.objects.get_or_create(
        empresa=empresa,
        paciente=paciente_classico,
        leito=leito_classico,
        status="ativa",
        defaults={"diagnostico": "Observacao clinica demo com protocolo assistencial.", "medico_responsavel": "Dr. Clinico Demo"},
    )
    if created:
        criados.append("internacao_classica")
    prescricao, created = PrescricaoHospitalar.objects.get_or_create(
        empresa=empresa,
        paciente=paciente,
        data=hoje,
        defaults={"medico_nome": "Dr. Demo Emergencia", "medico_crm": "CRM/SP 000002", "status": "ativa", "medicamentos": [{"nome": "Dipirona 1g", "dose": "1 ampola", "via": "EV", "frequencia": "6/6h"}]},
    )
    if created:
        criados.append("prescricao")
    prescricao_classica, created = PrescricaoMedica.objects.get_or_create(
        internacao=internacao_classica,
        medicamento="Amoxicilina 500mg Demo",
        defaults={"dose": "1 capsula", "via": "oral", "frequencia": "8/8h", "duracao_dias": 7, "status": "ativa", "medico": "Dr. Clinico Demo", "observacoes": "Prescricao demo vinculada a internacao classica."},
    )
    if created:
        criados.append("prescricao_classica")
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
    else:
        criados = []
    return {"setor": setor, "criados": criados, "total_criado": len(criados)}


def api_enterprise_command_center(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    return JsonResponse(build_enterprise_command_center_payload(empresa))


def api_enterprise_premium_suite(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    return JsonResponse(build_enterprise_premium_suite_payload(empresa))


@csrf_exempt
def api_enterprise_seed_operational_demo(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "Metodo nao permitido"}, status=405)

    resultado = seed_enterprise_operational_demo(empresa)
    resultado["suite"] = build_enterprise_premium_suite_payload(empresa)
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

    resultado = reset_enterprise_demo(empresa)
    resultado["suite"] = build_enterprise_premium_suite_payload(empresa)
    return JsonResponse(resultado)
