"""
Solicitações de exames ocupacionais: empresa emite pedido → clínica recebe
(via SolusCRT ou por email). Suporta clínicas cadastradas no sistema e
clínicas externas (recebem por email com link de acompanhamento).
"""
import json
import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    SolicitacaoExame, FuncionarioSST, VinculoClinicaEmpresa, Empresa,
)
from .views_dashboard import _empresa_autenticada
from .access_control import requer_setor

logger = logging.getLogger(__name__)


# ── Catálogo de exames por categoria ──────────────────────────────────────────
CATALOGO_EXAMES = [
    {
        "categoria": "Clínica geral (todos os cargos)",
        "exames": [
            "Hemograma completo (série vermelha e branca)",
            "Glicemia em jejum",
            "Urina tipo 1 (EAS / sedimentoscopia)",
            "Acuidade visual (Snellen e Ishihara – daltonismo)",
            "Avaliação clínica geral (anamnese + exame físico)",
        ],
    },
    {
        "categoria": "Cardiovascular e metabólico",
        "exames": [
            "Eletrocardiograma (ECG) com laudo",
            "Teste ergométrico (esteira / bicicleta)",
            "Ecocardiograma",
            "Perfil lipídico (colesterol total, HDL, LDL, triglicerídeos)",
            "Função renal (ureia, creatinina, ácido úrico)",
            "Função hepática (TGO, TGP, GGT, bilirrubinas)",
            "Hemoglobina glicada (HbA1c)",
            "Pressão arterial monitorada (MAPA 24h)",
        ],
    },
    {
        "categoria": "Auditivo e respiratório",
        "exames": [
            "Audiometria tonal liminar (NHO-01 / PAIR)",
            "Audiometria de altas frequências",
            "Imitanciometria (timpanograma)",
            "Espirometria com broncodilatador (NHO-05)",
            "Raio-X de tórax PA e perfil",
            "Tomografia de tórax de alta resolução (TCAR)",
            "Prova de função pulmonar completa",
        ],
    },
    {
        "categoria": "Visual e neurológico",
        "exames": [
            "Acuidade visual corrigida e não corrigida",
            "Campimetria computadorizada (campo visual)",
            "Avaliação oftalmológica completa (biomicroscopia, fundo de olho)",
            "Eletroencefalograma (EEG)",
            "Exame neurológico clínico",
            "Avaliação psicossocial (DASS-21 / Maslach / PHQ-9)",
            "Avaliação psiquiátrica",
        ],
    },
    {
        "categoria": "Musculoesquelético e ergonômico",
        "exames": [
            "Avaliação ergonômica de posto de trabalho",
            "Avaliação musculoesquelética (coluna, membros superiores e inferiores)",
            "Raio-X de coluna lombar / cervical / dorsal",
            "Ultrassonografia de ombro / punho / joelho",
            "Ressonância magnética de coluna",
            "EMG / ENMG (eletroneuromiografia) de membros superiores",
            "Avaliação postural computadorizada",
        ],
    },
    {
        "categoria": "Toxicológico — agrotóxicos / pesticidas",
        "exames": [
            "Colinesterase eritrocitária (organofosforados e carbamatos)",
            "Colinesterase plasmática",
            "Pesticidas na urina (triagem)",
            "Avaliação dermatológica por exposição a químicos",
        ],
    },
    {
        "categoria": "Toxicológico — metais pesados e solventes",
        "exames": [
            "Chumbo no sangue (plumbemia / B-Pb)",
            "Zinco protoporfirina eritrocitária (ZPP)",
            "Mercúrio urinário",
            "Cromo urinário (hexavalente)",
            "Manganês no sangue",
            "Benzeno urinário (ácido trans,trans-mucônico — S-phenylmercapturic acid)",
            "Tolueno / Xileno urinário (ácido hipúrico / metilipúrico)",
            "Cádmio urinário",
            "Arsênio urinário",
            "Solventes no sangue (painel)",
        ],
    },
    {
        "categoria": "Toxicológico — drogas, álcool e aptidão crítica",
        "exames": [
            "Exame toxicológico de larga janela — cabelo ou pelo",
            "Painel toxicológico urinário — anfetaminas, metanfetaminas, cocaína, maconha, opiáceos e benzodiazepínicos",
            "Painel toxicológico salivar — drogas de abuso",
            "Dosagem de álcool etílico no sangue",
            "Etilglicuronídeo (EtG) urinário — álcool",
            "Carboxihemoglobina",
            "Metahemoglobina",
            "Triagem toxicológica ocupacional pós-acidente",
            "Avaliação médica de aptidão para função crítica",
        ],
    },
    {
        "categoria": "Risco biológico — saúde, laboratório e alimentos",
        "exames": [
            "Sorologia para Hepatite B (HBsAg, Anti-HBs, Anti-HBc)",
            "Sorologia para Hepatite A",
            "Sorologia para Hepatite C (Anti-HCV)",
            "Sorologia para HIV (ELISA + confirmação)",
            "Sorologia para Leptospirose (MAT)",
            "PPD (Tuberculina — Mantoux) para risco de tuberculose",
            "IGRA (QuantiFERON-TB Gold) para tuberculose",
            "Coproscopia / coproparasitológico (manipuladores de alimentos)",
            "Cultura de secreção nasal / orofaríngea (Staphylococcus aureus)",
            "Sorologia para Rubéola / Sarampo / Varicela (imunidade)",
            "Vacina Hepatite B — comprovante / anti-HBs pós-vacina",
            "Hemograma diferencial (eosinófilos para risco helmíntico)",
        ],
    },
    {
        "categoria": "Trabalho em altura (NR-35)",
        "exames": [
            "Avaliação clínica específica para trabalho em altura",
            "Avaliação vestibular (Romberg, Fukuda, marcha)",
            "Audiometria tonal liminar",
            "ECG com laudo cardiológico",
            "Avaliação neurológica (epilepsia / síncope / vertigem)",
            "Glicemia de jejum (controle de hipoglicemia)",
            "Avaliação psicológica (acrofobia / risco comportamental)",
            "Raio-X de coluna cervical (instabilidade)",
            "Pressão arterial (PA) em repouso e após esforço",
        ],
    },
    {
        "categoria": "Motorista profissional / operador de máquinas (NR-7 e CONTRAN)",
        "exames": [
            "Acuidade visual com e sem correção",
            "Avaliação de visão de cores (Ishihara / Farnsworth)",
            "Tonometria ocular (pressão intraocular)",
            "Avaliação auditiva (audiometria tonal)",
            "Tempo de reação psicomotora",
            "Avaliação psicológica para condutores (DETRAN)",
            "Avaliação neurológica (epilepsia / sonolência excessiva)",
            "ECG com laudo",
            "Glicemia de jejum e HbA1c",
            "Pesquisa de substâncias psicoativas (toxicológico — CNH)",
            "Avaliação osteoarticular de membros e coluna",
        ],
    },
    {
        "categoria": "Trabalho em espaço confinado (NR-33)",
        "exames": [
            "Avaliação clínica específica para espaço confinado",
            "Espirometria",
            "ECG",
            "Avaliação de claustrofobia / psicológica",
            "Raio-X de tórax",
            "Glicemia de jejum",
            "Pressão arterial",
        ],
    },
    {
        "categoria": "Trabalho com eletricidade (NR-10)",
        "exames": [
            "Avaliação clínica para risco elétrico",
            "ECG com laudo",
            "Avaliação neurológica (epilepsia)",
            "Avaliação psicológica (risco comportamental)",
            "Raio-X de tórax",
        ],
    },
    {
        "categoria": "Exposição ao calor / câmara fria",
        "exames": [
            "Avaliação cardiovascular completa (ECG + teste ergométrico)",
            "Função renal (creatinina, ureia)",
            "Hidratação e eletrólitos (Na, K, Mg)",
            "Avaliação dermatológica (queimaduras, lesões por frio)",
            "Raio-X de extremidades (pé / mão) para lesão por frio",
        ],
    },
    {
        "categoria": "Radiação ionizante (NR-15 / Anexo 5)",
        "exames": [
            "Hemograma completo com diferencial (leucopenia / aplasia)",
            "Plaquetas",
            "Dosimetria termoluminescente (TLD — comprovante)",
            "Raio-X de tórax anual",
            "Avaliação dermatológica (radiodermite)",
            "Avaliação ocular (catarata — lâmpada de fenda)",
            "Função tireoidiana (TSH, T4 livre) — para radioiodoterapia",
        ],
    },
    {
        "categoria": "Exposição a ruído (NR-15 / PAIR)",
        "exames": [
            "Audiometria tonal liminar (pré e pós-exposição)",
            "Audiometria de altas frequências (8–16 kHz)",
            "Imitanciometria",
            "Emissões otoacústicas (EOA)",
            "Dosimetria de ruído (medição ambiental — laudo LTCAT)",
        ],
    },
    {
        "categoria": "Vibração (mãos-braços / corpo inteiro)",
        "exames": [
            "Avaliação vascular periférica de membros superiores",
            "Capilaroscopia (fenômeno de Raynaud)",
            "Condução nervosa periférica (ENMG)",
            "Raio-X de punho e mão",
            "Avaliação musculoesquelética de coluna",
        ],
    },
    {
        "categoria": "Mineração e construção civil",
        "exames": [
            "Raio-X de tórax PA (pneumoconioses — NIOSH B-reader)",
            "Espirometria com avaliação de obstrução / restrição",
            "Tomografia de tórax (TCAR) — sílica / amianto",
            "Avaliação audiométrica (ruído de maquinário)",
            "Avaliação musculoesquelética e de coluna",
            "Chumbo no sangue (soldagem e pintura)",
            "Função renal (exposição a sílica e metais)",
        ],
    },
    {
        "categoria": "Saúde mental e trabalho noturno",
        "exames": [
            "Avaliação psicossocial (Burnout — Maslach Inventory)",
            "PHQ-9 (depressão) e GAD-7 (ansiedade)",
            "Avaliação de qualidade do sono (Epworth / Pittsburgh)",
            "Polissonografia (suspeita de apneia — trabalho noturno e motoristas)",
            "Avaliação psiquiátrica",
            "TSH e T4 livre (hipotireoidismo como causa de fadiga)",
            "Hemograma (anemia como causa de fadiga)",
        ],
    },
    {
        "categoria": "Gestante e amamentação",
        "exames": [
            "Beta-hCG (confirmação de gravidez)",
            "Toxoplasmose IgG/IgM",
            "Rubéola IgG/IgM",
            "CMV IgG/IgM",
            "Avaliação de riscos laborais para gestante (laudo médico do trabalho)",
            "Avaliação ergonômica para gestante",
        ],
    },
]

# Lista plana para compatibilidade e busca
EXAMES_PADRAO = [e for cat in CATALOGO_EXAMES for e in cat["exames"]]


PERFIS_EXAMES_FUNCAO = [
    {
        "id": "administrativo",
        "nome": "Administrativo / escritório / atendimento",
        "palavras_chave": ["administrativo", "auxiliar", "assistente", "recepcionista", "atendente", "escritorio", "escritório", "financeiro", "rh"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Hemograma completo (série vermelha e branca)",
            "Glicemia em jejum",
            "Acuidade visual (Snellen e Ishihara – daltonismo)",
            "Avaliação ergonômica de posto de trabalho",
            "Avaliação psicossocial (DASS-21 / Maslach / PHQ-9)",
        ],
    },
    {
        "id": "saude_laboratorio",
        "nome": "Saúde / laboratório / enfermagem",
        "palavras_chave": ["enfermeiro", "enfermagem", "medico", "médico", "tecnico enfermagem", "técnico enfermagem", "laboratorio", "laboratório", "coleta", "biomedico", "biomédico"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Hemograma completo (série vermelha e branca)",
            "Sorologia para Hepatite B (HBsAg, Anti-HBs, Anti-HBc)",
            "Sorologia para Hepatite C (Anti-HCV)",
            "Sorologia para HIV (ELISA + confirmação)",
            "PPD (Tuberculina — Mantoux) para risco de tuberculose",
            "IGRA (QuantiFERON-TB Gold) para tuberculose",
            "Vacina Hepatite B — comprovante / anti-HBs pós-vacina",
            "Avaliação psicossocial (DASS-21 / Maslach / PHQ-9)",
        ],
    },
    {
        "id": "farmacia",
        "nome": "Farmácia / manipulação / dispensação",
        "palavras_chave": ["farmacia", "farmácia", "farmaceutico", "farmacêutico", "balconista", "manipulacao", "manipulação", "dispensacao", "dispensação"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Hemograma completo (série vermelha e branca)",
            "Glicemia em jejum",
            "Função hepática (TGO, TGP, GGT, bilirrubinas)",
            "Função renal (ureia, creatinina, ácido úrico)",
            "Avaliação dermatológica por exposição a químicos",
            "Acuidade visual corrigida e não corrigida",
            "Avaliação ergonômica de posto de trabalho",
        ],
    },
    {
        "id": "motorista",
        "nome": "Motorista profissional / transporte",
        "palavras_chave": ["motorista", "condutor", "caminhao", "caminhão", "transporte", "entregador", "van", "ambulancia", "ambulância"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Acuidade visual com e sem correção",
            "Avaliação de visão de cores (Ishihara / Farnsworth)",
            "Avaliação auditiva (audiometria tonal)",
            "Tempo de reação psicomotora",
            "Avaliação psicológica para condutores (DETRAN)",
            "Avaliação neurológica (epilepsia / sonolência excessiva)",
            "ECG com laudo",
            "Glicemia de jejum e HbA1c",
            "Pesquisa de substâncias psicoativas (toxicológico — CNH)",
            "Exame toxicológico de larga janela — cabelo ou pelo",
            "Avaliação osteoarticular de membros e coluna",
        ],
    },
    {
        "id": "operador_maquinas",
        "nome": "Operador de máquinas / empilhadeira / ponte rolante",
        "palavras_chave": ["operador", "maquina", "máquina", "empilhadeira", "ponte rolante", "guindaste", "trator", "retroescavadeira"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Acuidade visual com e sem correção",
            "Avaliação auditiva (audiometria tonal)",
            "Tempo de reação psicomotora",
            "Avaliação psicológica para condutores (DETRAN)",
            "Avaliação neurológica (epilepsia / sonolência excessiva)",
            "ECG com laudo",
            "Glicemia de jejum e HbA1c",
            "Painel toxicológico urinário — anfetaminas, metanfetaminas, cocaína, maconha, opiáceos e benzodiazepínicos",
            "Avaliação osteoarticular de membros e coluna",
        ],
    },
    {
        "id": "altura",
        "nome": "Trabalho em altura — NR-35",
        "palavras_chave": ["altura", "nr-35", "telhado", "andaime", "torre", "alpinista", "fachada"],
        "exames": [
            "Avaliação clínica específica para trabalho em altura",
            "Avaliação vestibular (Romberg, Fukuda, marcha)",
            "Audiometria tonal liminar",
            "ECG com laudo cardiológico",
            "Avaliação neurológica (epilepsia / síncope / vertigem)",
            "Glicemia de jejum (controle de hipoglicemia)",
            "Avaliação psicológica (acrofobia / risco comportamental)",
            "Pressão arterial (PA) em repouso e após esforço",
        ],
    },
    {
        "id": "espaco_confinado",
        "nome": "Espaço confinado — NR-33",
        "palavras_chave": ["confinado", "nr-33", "tanque", "silo", "galeria", "subterraneo", "subterrâneo"],
        "exames": [
            "Avaliação clínica específica para espaço confinado",
            "Espirometria",
            "ECG",
            "Avaliação de claustrofobia / psicológica",
            "Raio-X de tórax",
            "Glicemia de jejum",
            "Pressão arterial",
        ],
    },
    {
        "id": "eletricidade",
        "nome": "Eletricidade — NR-10",
        "palavras_chave": ["eletricista", "eletrica", "elétrica", "nr-10", "alta tensão", "alta tensao", "manutencao eletrica", "manutenção elétrica"],
        "exames": [
            "Avaliação clínica para risco elétrico",
            "ECG com laudo",
            "Avaliação neurológica (epilepsia)",
            "Avaliação psicológica (risco comportamental)",
            "Raio-X de tórax",
        ],
    },
    {
        "id": "ruido",
        "nome": "Ruído industrial / produção",
        "palavras_chave": ["produção", "producao", "industrial", "ruido", "ruído", "metalurgica", "metalúrgica", "serralheiro", "caldeireiro"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Audiometria tonal liminar (pré e pós-exposição)",
            "Audiometria de altas frequências (8–16 kHz)",
            "Imitanciometria",
            "Emissões otoacústicas (EOA)",
            "Dosimetria de ruído (medição ambiental — laudo LTCAT)",
        ],
    },
    {
        "id": "quimicos",
        "nome": "Químicos / solventes / pintura / limpeza pesada",
        "palavras_chave": ["quimico", "químico", "pintor", "pintura", "solvente", "limpeza", "higienizacao", "higienização", "desinfeccao", "desinfecção"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Hemograma completo (série vermelha e branca)",
            "Função hepática (TGO, TGP, GGT, bilirrubinas)",
            "Função renal (ureia, creatinina, ácido úrico)",
            "Espirometria com broncodilatador (NHO-05)",
            "Avaliação dermatológica por exposição a químicos",
            "Benzeno urinário (ácido trans,trans-mucônico — S-phenylmercapturic acid)",
            "Tolueno / Xileno urinário (ácido hipúrico / metilipúrico)",
            "Solventes no sangue (painel)",
        ],
    },
    {
        "id": "agrotoxicos",
        "nome": "Agrícola / pulverização / agrotóxicos",
        "palavras_chave": ["agricola", "agrícola", "rural", "pulverizador", "pulverizacao", "pulverização", "agrotoxico", "agrotóxico", "pesticida"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Hemograma completo (série vermelha e branca)",
            "Função hepática (TGO, TGP, GGT, bilirrubinas)",
            "Colinesterase eritrocitária (organofosforados e carbamatos)",
            "Colinesterase plasmática",
            "Pesticidas na urina (triagem)",
            "Avaliação dermatológica por exposição a químicos",
            "Espirometria com broncodilatador (NHO-05)",
        ],
    },
    {
        "id": "construcao_mineracao",
        "nome": "Construção civil / mineração / poeiras minerais",
        "palavras_chave": ["construcao", "construção", "obra", "pedreiro", "mineracao", "mineração", "mina", "soldador", "solda", "cimento", "silica", "sílica"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Raio-X de tórax PA (pneumoconioses — NIOSH B-reader)",
            "Espirometria com avaliação de obstrução / restrição",
            "Tomografia de tórax (TCAR) — sílica / amianto",
            "Avaliação audiométrica (ruído de maquinário)",
            "Avaliação musculoesquelética e de coluna",
            "Chumbo no sangue (soldagem e pintura)",
            "Função renal (exposição a sílica e metais)",
        ],
    },
    {
        "id": "alimentos",
        "nome": "Manipulação de alimentos / cozinha / mercado",
        "palavras_chave": ["cozinha", "cozinheiro", "alimentacao", "alimentação", "alimento", "padaria", "açougue", "acougue", "mercado", "supermercado"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Hemograma completo (série vermelha e branca)",
            "Coproscopia / coproparasitológico (manipuladores de alimentos)",
            "Cultura de secreção nasal / orofaríngea (Staphylococcus aureus)",
            "Sorologia para Hepatite A / B conforme risco local",
            "Avaliação dermatológica por exposição a químicos",
        ],
    },
    {
        "id": "camara_fria_calor",
        "nome": "Câmara fria / calor intenso",
        "palavras_chave": ["camara fria", "câmara fria", "frigorifico", "frigorífico", "calor", "forno", "fundicao", "fundição"],
        "exames": [
            "Avaliação cardiovascular completa (ECG + teste ergométrico)",
            "Função renal (creatinina, ureia)",
            "Hidratação e eletrólitos (Na, K, Mg)",
            "Avaliação dermatológica (queimaduras, lesões por frio)",
            "Raio-X de extremidades (pé / mão) para lesão por frio",
        ],
    },
    {
        "id": "radiacao",
        "nome": "Radiação ionizante / imagem / radiologia",
        "palavras_chave": ["radiologia", "raio x", "raio-x", "radiacao", "radiação", "tomografia", "mamografia", "medicina nuclear"],
        "exames": [
            "Hemograma completo com diferencial (leucopenia / aplasia)",
            "Plaquetas",
            "Dosimetria termoluminescente (TLD — comprovante)",
            "Raio-X de tórax anual",
            "Avaliação dermatológica (radiodermite)",
            "Avaliação ocular (catarata — lâmpada de fenda)",
            "Função tireoidiana (TSH, T4 livre) — para radioiodoterapia",
        ],
    },
    {
        "id": "seguranca_armada",
        "nome": "Segurança patrimonial / vigilante / função crítica",
        "palavras_chave": ["seguranca", "segurança", "vigilante", "porteiro", "vigia", "escolta", "armada", "arma"],
        "exames": [
            "Avaliação clínica geral (anamnese + exame físico)",
            "Acuidade visual com e sem correção",
            "Avaliação auditiva (audiometria tonal)",
            "Avaliação psicológica (risco comportamental)",
            "Avaliação psiquiátrica",
            "ECG com laudo",
            "Painel toxicológico urinário — anfetaminas, metanfetaminas, cocaína, maconha, opiáceos e benzodiazepínicos",
            "Triagem toxicológica ocupacional pós-acidente",
        ],
    },
]


def _empresa(request):
    e = _empresa_autenticada(request)
    if not e:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return e, None


def _sol_dict(s):
    return {
        "id": s.id,
        "funcionario_id": s.funcionario_id,
        "funcionario_nome": s.funcionario.nome,
        "funcionario_cargo": s.funcionario.cargo,
        "funcionario_cpf": s.funcionario.cpf,
        "clinica_id": s.clinica_id,
        "clinica_nome": (
            s.clinica.nome if s.clinica
            else s.clinica_nome_externo or "Clínica externa"
        ),
        "clinica_email_externo": s.clinica_email_externo,
        "email_enviado": s.email_enviado,
        "tipo_aso": s.tipo_aso,
        "tipo_aso_label": s.get_tipo_aso_display(),
        "exames": json.loads(s.exames) if s.exames else [],
        "urgente": s.urgente,
        "observacoes": s.observacoes,
        "status": s.status,
        "status_label": s.get_status_display(),
        "data_solicitacao": s.data_solicitacao.strftime("%d/%m/%Y %H:%M"),
        "data_agendamento": s.data_agendamento.isoformat() if s.data_agendamento else None,
        "data_realizacao": s.data_realizacao.isoformat() if s.data_realizacao else None,
        "resposta_clinica": s.resposta_clinica,
    }


def _enviar_email_solicitacao(sol):
    """Envia email da solicitação para clínica externa."""
    exames = json.loads(sol.exames) if sol.exames else []
    empresa = sol.empresa
    func = sol.funcionario
    backend = getattr(settings, "EMAIL_BACKEND", "")
    smtp_user = (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    smtp_password = (getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()
    if "smtp.EmailBackend" in backend and (not smtp_user or not smtp_password):
        return False, "SMTP não configurado no Render: preencha EMAIL_HOST_USER e EMAIL_HOST_PASSWORD."
    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if (not from_email or "noreply@soluscrt.com.br" in from_email) and smtp_user:
        from_email = f"SolusCRT <{smtp_user}>"
    reply_to = []
    if getattr(empresa, "email", ""):
        reply_to = [empresa.email]

    corpo = f"""
Olá, {sol.clinica_nome_externo or 'Clínica'},

A empresa **{empresa.nome}** enviou um pedido de exame ocupacional pelo sistema SolusCRT.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PEDIDO DE EXAME — {sol.get_tipo_aso_display().upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Funcionário: {func.nome}
CPF: {func.cpf or 'Não informado'}
Cargo: {func.cargo}
{'⚠️ URGENTE — prioridade de agendamento' if sol.urgente else ''}

EXAMES SOLICITADOS:
{''.join(f'  • {e}{chr(10)}' for e in exames) if exames else '  (conforme avaliação médica)'}

{'OBSERVAÇÕES:' + chr(10) + sol.observacoes if sol.observacoes else ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Para confirmar o agendamento, entre em contato com a empresa:
  Empresa: {empresa.nome}
  Email: {empresa.email if hasattr(empresa, 'email') else ''}

Após a realização, a empresa pode importar o ASO pelo portal SolusCRT.

--
SolusCRT · Sistema de Gestão SST
https://empresa.soluscrt.com.br
    """.strip()

    agora = timezone.now()
    try:
        msg = EmailMessage(
            subject=f"[SolusCRT] Pedido de Exame — {func.nome} — {empresa.nome}",
            body=corpo,
            from_email=from_email,
            to=[sol.clinica_email_externo],
            reply_to=reply_to,
        )
        enviados = msg.send(fail_silently=False)
        if enviados < 1:
            sol.email_enviado = False
            sol.resposta_clinica = f"Servidor SMTP nao confirmou envio para {sol.clinica_email_externo}."
            sol.save(update_fields=["email_enviado", "resposta_clinica"])
            logger.warning(
                "SolicitacaoExame %s nao teve envio confirmado pelo backend SMTP para %s",
                sol.pk,
                sol.clinica_email_externo,
            )
            return False, "Servidor SMTP nao confirmou envio."

        sol.email_enviado = True
        sol.email_enviado_em = agora
        sol.resposta_clinica = (
            f"Email entregue ao SMTP em "
            f"{timezone.localtime(sol.email_enviado_em).strftime('%d/%m/%Y %H:%M')} "
            f"para {sol.clinica_email_externo}."
        )
        sol.save(update_fields=["email_enviado", "email_enviado_em", "resposta_clinica"])
        logger.info(
            "SolicitacaoExame %s entregue ao SMTP para %s",
            sol.pk,
            sol.clinica_email_externo,
        )
        return True, None
    except Exception as e:
        sol.email_enviado = False
        sol.resposta_clinica = f"Falha no envio para {sol.clinica_email_externo}: {e}"
        sol.save(update_fields=["email_enviado", "resposta_clinica"])
        logger.exception(
            "Falha ao enviar SolicitacaoExame %s para %s",
            sol.pk,
            sol.clinica_email_externo,
        )
        return False, str(e)


# ── Página empresa ─────────────────────────────────────────────────────────────

@requer_setor("empresa")
def sst_solicitacoes_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "sst_solicitacoes.html", {"empresa_nome": empresa.nome})


# ── API empresa ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_solicitacoes_exame(request):
    empresa, err = _empresa(request)
    if err:
        return err

    if request.method == "GET":
        status_f = request.GET.get("status", "")
        qs = SolicitacaoExame.objects.filter(empresa=empresa).select_related(
            "funcionario", "clinica"
        )
        if status_f:
            qs = qs.filter(status=status_f)
        return JsonResponse({
            "solicitacoes": [_sol_dict(s) for s in qs],
            "catalogo": CATALOGO_EXAMES,
            "perfis_funcao": PERFIS_EXAMES_FUNCAO,
            "exames_padrao": EXAMES_PADRAO,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        func_id = data.get("funcionario_id")
        if not func_id:
            return JsonResponse({"erro": "funcionario_id é obrigatório"}, status=400)
        func = FuncionarioSST.objects.filter(id=func_id, empresa=empresa).first()
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

        tipo = data.get("tipo_aso", "periodico")
        if tipo not in dict(SolicitacaoExame.TIPO_ASO):
            return JsonResponse({"erro": "Tipo de ASO inválido"}, status=400)

        # modo: "sistema" | "email" | "interno"
        modo = data.get("modo", "interno")
        clinica = None
        vinculo = None
        clinica_nome_ext = ""
        clinica_email_ext = ""

        if modo == "sistema":
            clinica_id = data.get("clinica_id")
            if not clinica_id:
                return JsonResponse({"erro": "Selecione a clínica"}, status=400)
            vinculo = VinculoClinicaEmpresa.objects.filter(
                empresa_contratante=empresa, clinica_id=clinica_id, status="ativo"
            ).first()
            clinica = Empresa.objects.filter(id=clinica_id).first()
            if not clinica:
                return JsonResponse({"erro": "Clínica não encontrada"}, status=404)

        elif modo == "email":
            clinica_email_ext = (data.get("clinica_email") or "").strip()
            clinica_nome_ext = (data.get("clinica_nome") or "").strip()
            if not clinica_email_ext:
                return JsonResponse({"erro": "Email da clínica é obrigatório"}, status=400)

        exames = data.get("exames", [])
        sol = SolicitacaoExame.objects.create(
            empresa=empresa,
            funcionario=func,
            clinica=clinica,
            vinculo=vinculo,
            tipo_aso=tipo,
            exames=json.dumps(exames, ensure_ascii=False),
            urgente=bool(data.get("urgente", False)),
            observacoes=data.get("observacoes", "").strip(),
            clinica_nome_externo=clinica_nome_ext,
            clinica_email_externo=clinica_email_ext,
        )

        email_erro = None
        if modo == "email" and clinica_email_ext:
            ok, email_erro = _enviar_email_solicitacao(sol)

        resp = _sol_dict(sol)
        resp["modo"] = modo
        if email_erro:
            resp["aviso_email"] = f"Pedido salvo, mas o email nao foi confirmado: {email_erro}"
        return JsonResponse(resp, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_solicitacao_detalhe(request, sol_id):
    empresa, err = _empresa(request)
    if err:
        return err

    sol = SolicitacaoExame.objects.filter(id=sol_id, empresa=empresa).select_related(
        "funcionario", "clinica"
    ).first()
    if not sol:
        return JsonResponse({"erro": "Solicitação não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse(_sol_dict(sol))

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        acao = data.get("acao")
        if acao == "reenviar_email":
            if not sol.clinica_email_externo:
                return JsonResponse({"erro": "Sem email externo cadastrado"}, status=400)
            ok, err_msg = _enviar_email_solicitacao(sol)
            if not ok:
                return JsonResponse({"erro": err_msg}, status=500)
            return JsonResponse({"ok": True, "mensagem": "Email reenviado e aceito para envio"})
        return JsonResponse({"erro": "Ação inválida"}, status=400)

    if request.method == "DELETE":
        if sol.status not in ("pendente",):
            return JsonResponse({"erro": "Só é possível cancelar solicitações pendentes"}, status=400)
        sol.status = "cancelado"
        sol.save()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_clinicas_disponiveis(request):
    empresa, err = _empresa(request)
    if err:
        return err

    vinculos = VinculoClinicaEmpresa.objects.filter(
        empresa_contratante=empresa, status="ativo"
    ).select_related("clinica")

    return JsonResponse({
        "clinicas": [
            {"id": v.clinica_id, "nome": v.clinica.nome, "vinculo_id": v.id}
            for v in vinculos
        ]
    })


# ── Página clínica ─────────────────────────────────────────────────────────────

def clinica_solicitacoes_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "clinica_solicitacoes.html", {"empresa_nome": empresa.nome})


# ── API clínica ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_clinica_solicitacoes(request):
    clinica, err = _empresa(request)
    if err:
        return err

    if request.method == "GET":
        status_f = request.GET.get("status", "")
        qs = SolicitacaoExame.objects.filter(clinica=clinica).select_related(
            "funcionario", "empresa"
        )
        if status_f:
            qs = qs.filter(status=status_f)

        def _enrich(s):
            d = _sol_dict(s)
            d["empresa_solicitante"] = s.empresa.nome
            return d

        return JsonResponse({"solicitacoes": [_enrich(s) for s in qs]})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_clinica_solicitacao_acao(request, sol_id):
    clinica, err = _empresa(request)
    if err:
        return err

    sol = SolicitacaoExame.objects.filter(id=sol_id, clinica=clinica).select_related(
        "funcionario", "empresa"
    ).first()
    if not sol:
        return JsonResponse({"erro": "Solicitação não encontrada"}, status=404)

    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    acao = data.get("acao")
    from datetime import date, datetime

    if acao == "agendar":
        data_ag = data.get("data_agendamento")
        if not data_ag:
            return JsonResponse({"erro": "data_agendamento é obrigatória"}, status=400)
        try:
            sol.data_agendamento = datetime.strptime(data_ag, "%Y-%m-%d").date()
        except Exception:
            return JsonResponse({"erro": "Data inválida"}, status=400)
        sol.status = "agendado"
        sol.resposta_clinica = data.get("resposta_clinica", sol.resposta_clinica)
        sol.save()
        return JsonResponse({"ok": True, "status": sol.status})

    if acao == "realizar":
        data_real = data.get("data_realizacao")
        try:
            sol.data_realizacao = datetime.strptime(data_real, "%Y-%m-%d").date() if data_real else date.today()
        except Exception:
            sol.data_realizacao = date.today()
        sol.status = "realizado"
        sol.resposta_clinica = data.get("resposta_clinica", sol.resposta_clinica)
        sol.save()
        return JsonResponse({"ok": True, "status": sol.status})

    if acao == "cancelar":
        sol.status = "cancelado"
        sol.resposta_clinica = data.get("resposta_clinica", "")
        sol.save()
        return JsonResponse({"ok": True, "status": sol.status})

    return JsonResponse({"erro": f"Ação inválida: {acao}"}, status=400)
