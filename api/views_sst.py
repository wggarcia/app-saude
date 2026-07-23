"""
Views SST — Saúde e Segurança do Trabalho
Endpoints para o painel de saúde ocupacional da empresa.
"""
import csv
import io
import json
from collections import defaultdict
from datetime import date, timedelta


def _paginar(request, qs, limit_default=100, limit_max=500):
    """Return (page_qs, meta_dict) applying ?limit= and ?offset= from request."""
    total = qs.count()
    limit_raw = str(request.GET.get("limit", "")).strip().lower()
    all_raw = str(request.GET.get("all", "")).strip().lower()
    if all_raw in {"1", "true", "yes", "sim"} or limit_raw in {"all", "max", "0", "-1"}:
        return qs, {"total": total, "limit": total, "offset": 0, "all": True}
    try:
        limit = min(int(request.GET.get("limit", limit_default)), limit_max)
    except (ValueError, TypeError):
        limit = limit_default
    limit = max(limit, 1)
    try:
        offset = max(int(request.GET.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0
    return qs[offset: offset + limit], {"total": total, "limit": limit, "offset": offset}

from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .access_control import (
    api_requer_feature,
    dentro_do_limite,
    get_setor,
    principal_pode_operacao_setorial,
    requer_feature_pacote,
    requer_permissao_modulo,
)
from .models import (
    AfastamentoSST,
    ASOOcupacional,
    CATOcupacional,
    AssinaturaDocumentoSST,
    DocumentoSST,
    Empresa,
    EntregaEPI,
    ExameOcupacional,
    FuncionarioSST,
    TreinamentoNR,
    eSocialEventoSST,
)
from .views_dashboard import _empresa_autenticada as _empresa_autenticada_base
from .utils import validar_cpf_cadastro


def _cpf_limpo(cpf):
    return "".join(c for c in (cpf or "") if c.isdigit())


CID_SST_DOENCA_TRABALHO = [
    {
        "grupo": "Transtornos mentais relacionados ao trabalho",
        "itens": [
            ("F32", "Episodio depressivo"),
            ("F33", "Transtorno depressivo recorrente"),
            ("F41.1", "Ansiedade generalizada"),
            ("F43.0", "Reacao aguda ao estresse"),
            ("F43.1", "Estado de estresse pos-traumatico"),
            ("F43.2", "Transtornos de adaptacao"),
            ("F48.0", "Neurastenia / esgotamento"),
        ],
    },
    {
        "grupo": "LER/DORT e sistema osteomuscular",
        "itens": [
            ("G56.0", "Sindrome do tunel do carpo"),
            ("G56.2", "Lesao do nervo cubital"),
            ("M50", "Transtornos dos discos cervicais"),
            ("M51", "Transtornos de discos intervertebrais"),
            ("M53", "Dorsopatias nao classificadas em outra parte"),
            ("M54.2", "Cervicalgia"),
            ("M54.5", "Dor lombar baixa"),
            ("M65", "Sinovite e tenossinovite"),
            ("M65.4", "Tenossinovite estiloide radial de De Quervain"),
            ("M70", "Transtornos dos tecidos moles relacionados ao uso"),
            ("M75", "Lesoes do ombro"),
            ("M77", "Outras entesopatias"),
        ],
    },
    {
        "grupo": "Audicao, ruido e vibracao",
        "itens": [
            ("H83.3", "Efeitos do ruido sobre o ouvido interno"),
            ("H90.3", "Perda de audicao neurossensorial bilateral"),
            ("H91.9", "Perda de audicao nao especificada"),
            ("T75.2", "Efeitos da vibracao"),
            ("I73.0", "Sindrome de Raynaud"),
        ],
    },
    {
        "grupo": "Pneumoconioses e doencas respiratorias ocupacionais",
        "itens": [
            ("J60", "Pneumoconiose dos mineiros de carvao"),
            ("J61", "Pneumoconiose devida a amianto e outras fibras minerais"),
            ("J62", "Pneumoconiose devida a poeira contendo silica"),
            ("J63", "Pneumoconiose devida a outras poeiras inorganicas"),
            ("J64", "Pneumoconiose nao especificada"),
            ("J65", "Pneumoconiose associada a tuberculose"),
            ("J66", "Doencas das vias aereas devidas a poeiras organicas"),
            ("J67", "Pneumonite de hipersensibilidade devida a poeiras organicas"),
            ("J68", "Afeccoes respiratorias por inalacao de produtos quimicos"),
            ("J69", "Pneumonite devida a solidos e liquidos"),
            ("J70", "Afeccoes respiratorias por outros agentes externos"),
            ("J45", "Asma"),
        ],
    },
    {
        "grupo": "Dermatoses ocupacionais",
        "itens": [
            ("L23", "Dermatite alergica de contato"),
            ("L24", "Dermatite irritativa de contato"),
            ("L25", "Dermatite de contato nao especificada"),
            ("L56", "Outras alteracoes agudas da pele devidas a radiacao ultravioleta"),
            ("L57", "Alteracoes da pele devidas a exposicao cronica a radiacao nao ionizante"),
        ],
    },
    {
        "grupo": "Infeccoes e exposicoes biologicas ocupacionais",
        "itens": [
            ("A15", "Tuberculose respiratoria confirmada"),
            ("A16", "Tuberculose respiratoria sem confirmacao bacteriologica"),
            ("A18", "Tuberculose de outros orgaos"),
            ("B18", "Hepatite viral cronica"),
            ("B20", "Doenca pelo HIV resultando em doencas infecciosas"),
            ("Z20.5", "Contato e exposicao a hepatite viral"),
            ("Z20.6", "Contato e exposicao ao HIV"),
        ],
    },
    {
        "grupo": "Intoxicacoes, agentes quimicos e metais",
        "itens": [
            ("T51", "Efeito toxico do alcool"),
            ("T52", "Efeito toxico de solventes organicos"),
            ("T53", "Efeito toxico de derivados halogenados"),
            ("T54", "Efeito toxico de substancias corrosivas"),
            ("T56", "Efeito toxico de metais"),
            ("T57", "Efeito toxico de substancias inorganicas"),
            ("T59", "Efeito toxico de gases, fumacas e vapores"),
            ("T60", "Efeito toxico de pesticidas"),
            ("T65", "Efeito toxico de outras substancias"),
        ],
    },
    {
        "grupo": "Exposicoes ocupacionais e fatores de risco",
        "itens": [
            ("Z57.0", "Exposicao ocupacional ao ruido"),
            ("Z57.1", "Exposicao ocupacional a radiacao"),
            ("Z57.2", "Exposicao ocupacional a poeira"),
            ("Z57.3", "Exposicao ocupacional a contaminantes do ar"),
            ("Z57.4", "Exposicao ocupacional a agentes toxicos na agricultura"),
            ("Z57.5", "Exposicao ocupacional a agentes toxicos em outras industrias"),
            ("Z57.6", "Exposicao ocupacional a temperaturas extremas"),
            ("Z57.7", "Exposicao ocupacional a vibracao"),
            ("Z57.8", "Exposicao ocupacional a outros fatores de risco"),
            ("Z57.9", "Exposicao ocupacional a fator de risco nao especificado"),
        ],
    },
]


def _cid_sst_codigos():
    return {
        codigo.upper()
        for grupo in CID_SST_DOENCA_TRABALHO
        for codigo, _descricao in grupo["itens"]
    }


def _validar_cid_doenca_trabalho(tipo, cid):
    if tipo not in ("doenca", "doenca_ocupacional"):
        return None
    codigo = (cid or "").strip().upper()
    if not codigo:
        return "Selecione um CID de doença relacionada ao trabalho."
    if codigo not in _cid_sst_codigos():
        return "CID não permitido para doença do trabalho nesta lista SST."
    return None


def _buscar_funcionario(empresa, data):
    """Resolve funcionário por ID ou por nome parcial (case-insensitive)."""
    fid = data.get("funcionario_id")
    if fid:
        return FuncionarioSST.objects.filter(id=fid, empresa=empresa, ativo=True).first()
    nome = (data.get("funcionario_nome") or "").strip()
    if not nome:
        return None
    return (
        FuncionarioSST.objects
        .filter(empresa=empresa, ativo=True, nome__icontains=nome)
        .order_by("nome")
        .first()
    )


def _classificar_tipo_exame(nome):
    texto = (nome or "").lower()
    if any(p in texto for p in ["audiometr", "ruído", "ruido", "otoac"]):
        return "audiometria"
    if any(p in texto for p in ["visual", "oftal", "ishihara", "campimetr", "tonometr"]):
        return "acuidade_visual"
    if any(p in texto for p in ["espirom", "pulmonar", "tórax", "torax", "tcar"]):
        return "espirometria"
    if any(p in texto for p in ["ecg", "eletrocardiograma", "cardio", "ergométrico", "ergometrico"]):
        return "eletrocardiograma"
    if any(p in texto for p in ["raio", "rx", "ressonância", "ressonancia", "tomografia", "ultrassom", "ultrassonografia"]):
        return "raio_x"
    if any(p in texto for p in ["psicol", "psiqui", "psicossocial", "phq", "gad", "burnout"]):
        return "psicologico"
    if any(p in texto for p in ["hemograma", "glicemia", "urina", "sorologia", "toxicol", "chumbo", "mercúrio", "mercurio", "colinesterase", "função", "funcao", "hepática", "hepatica", "renal"]):
        return "laboratorial"
    return "outro"


def _empresa_sst_autenticada(request):
    empresa = _empresa_autenticada_base(request)
    if not empresa:
        return None
    if get_setor(empresa) != "empresa":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return empresa


_empresa_autenticada = _empresa_sst_autenticada


def _sst_nao_autorizado():
    return JsonResponse({"erro": "nao autenticado ou sem acesso SST"}, status=401)


# ── Dashboard principal ──────────────────────────────────────────────────────

def api_sst_dashboard(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    em_30d = hoje + timedelta(days=30)
    em_60d = hoje + timedelta(days=60)
    inicio_ano = hoje.replace(month=1, day=1)

    func_qs = FuncionarioSST.objects.filter(empresa=empresa)
    func_ativos = func_qs.filter(ativo=True).count()

    # ASOs
    aso_qs = ASOOcupacional.objects.filter(empresa=empresa)
    asos_vencendo = list(
        aso_qs.filter(data_validade__gte=hoje, data_validade__lte=em_30d)
        .select_related("funcionario")
        .order_by("data_validade")[:10]
    )
    asos_vencidos = aso_qs.filter(data_validade__lt=hoje).count()
    asos_a_vencer_60d = aso_qs.filter(data_validade__gte=hoje, data_validade__lte=em_60d).count()

    # Exames
    exam_qs = ExameOcupacional.objects.filter(empresa=empresa)
    exames_atrasados = exam_qs.filter(status="vencido").count()
    exames_vencendo_30d = exam_qs.filter(
        status="pendente", data_validade__gte=hoje, data_validade__lte=em_30d
    ).count()

    # CATs
    cat_qs = CATOcupacional.objects.filter(empresa=empresa)
    cats_abertas = cat_qs.filter(status_esocial__in=("nao_enviado", "pendente")).count()
    cats_recentes = list(
        cat_qs.order_by("-data_acidente")[:5].select_related("funcionario")
    )

    # eSocial
    esocial_qs = eSocialEventoSST.objects.filter(empresa=empresa)
    esocial_pendentes = esocial_qs.filter(status__in=("pendente", "enviado")).count()
    esocial_erros = esocial_qs.filter(status="erro").count()
    esocial_transmitidos_mes = esocial_qs.filter(
        status="transmitido", data_envio__date__gte=hoje.replace(day=1)
    ).count()
    esocial_por_tipo = {}
    for tp in ("S-2210", "S-2220", "S-2240"):
        ultimo = esocial_qs.filter(tipo_evento=tp).order_by("-criado_em").first()
        esocial_por_tipo[tp] = {
            "label": dict(eSocialEventoSST.TIPO_EVENTO).get(tp, tp),
            "status": ultimo.status if ultimo else "nao_enviado",
            "data": ultimo.data_envio.strftime("%d/%m/%Y") if ultimo and ultimo.data_envio else None,
        }

    # Afastamentos
    afas_qs = AfastamentoSST.objects.filter(empresa=empresa)
    afastamentos_ativos = afas_qs.filter(status="ativo").count()
    afastamentos_ano = afas_qs.filter(data_inicio__gte=inicio_ano).count()

    # Absenteísmo
    absenteismo_pct = round((afastamentos_ativos / max(func_ativos, 1)) * 100, 1) if func_ativos else 0.0

    # Documentos SST
    docs_qs = DocumentoSST.objects.filter(empresa=empresa)
    docs_status = {}
    for tp in ("PGR", "PCMSO", "LTCAT", "laudo_insalubridade", "PPP", "CIPA"):
        doc = docs_qs.filter(tipo=tp).order_by("-data_emissao").first()
        if doc:
            vencido = doc.data_validade and doc.data_validade < hoje
            docs_status[tp] = {
                "status": "vencido" if vencido else doc.status,
                "validade": doc.data_validade.strftime("%d/%m/%Y") if doc.data_validade else None,
                "responsavel": doc.responsavel_tecnico,
            }
        else:
            docs_status[tp] = {"status": "nao_cadastrado", "validade": None, "responsavel": ""}

    # Alertas críticos
    alertas = []
    if asos_vencidos:
        alertas.append({"nivel": "critico", "mensagem": f"{asos_vencidos} ASO(s) vencido(s)"})
    if asos_vencendo:
        alertas.append({"nivel": "alto", "mensagem": f"{len(asos_vencendo)} ASO(s) vencem em 30 dias"})
    if exames_atrasados:
        alertas.append({"nivel": "critico", "mensagem": f"{exames_atrasados} exame(s) em atraso"})
    if esocial_erros:
        alertas.append({"nivel": "critico", "mensagem": f"{esocial_erros} evento(s) eSocial com erro"})
    if esocial_pendentes:
        alertas.append({"nivel": "alto", "mensagem": f"{esocial_pendentes} evento(s) eSocial pendentes"})
    if docs_status.get("PGR", {}).get("status") in ("vencido", "nao_cadastrado"):
        alertas.append({"nivel": "alto", "mensagem": "PGR não cadastrado ou vencido"})
    if docs_status.get("PCMSO", {}).get("status") in ("vencido", "nao_cadastrado"):
        alertas.append({"nivel": "alto", "mensagem": "PCMSO não cadastrado ou vencido"})

    return JsonResponse({
        "empresa_nome": empresa.nome,
        "funcionarios_ativos": func_ativos,
        "asos": {
            "vencendo_30d": [
                {
                    "funcionario": a.funcionario.nome,
                    "cargo": a.funcionario.cargo,
                    "tipo": dict(ASOOcupacional.TIPO).get(a.tipo, a.tipo),
                    "validade": a.data_validade.strftime("%d/%m/%Y") if a.data_validade else None,
                    "dias_restantes": (a.data_validade - hoje).days if a.data_validade else None,
                    "resultado": a.resultado,
                }
                for a in asos_vencendo
            ],
            "vencidos": asos_vencidos,
            "a_vencer_60d": asos_a_vencer_60d,
        },
        "exames": {
            "atrasados": exames_atrasados,
            "vencendo_30d": exames_vencendo_30d,
        },
        "cats": {
            "abertas": cats_abertas,
            "recentes": [
                {
                    "funcionario": c.funcionario.nome,
                    "tipo": dict(CATOcupacional.TIPO).get(c.tipo, c.tipo),
                    "gravidade": c.gravidade,
                    "data": c.data_acidente.strftime("%d/%m/%Y"),
                    "status_esocial": c.status_esocial,
                }
                for c in cats_recentes
            ],
        },
        "esocial": {
            "pendentes": esocial_pendentes,
            "erros": esocial_erros,
            "transmitidos_mes": esocial_transmitidos_mes,
            "por_tipo": esocial_por_tipo,
        },
        "afastamentos": {
            "ativos": afastamentos_ativos,
            "no_ano": afastamentos_ano,
            "absenteismo_pct": absenteismo_pct,
        },
        "documentos": docs_status,
        "alertas": alertas,
    })


def api_sst_contexto_integrado(request):
    """
    Contexto unificado para sincronizar informacoes entre abas SST.
    Retorna KPIs compactos para navegacao lateral, cards rapidos e IA operacional.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    # Defesa extra: evita NameError em releases antigas onde o import global
    # de timezone pode ter sido removido em merge/cherry-pick.
    from django.utils import timezone as dj_timezone

    hoje = date.today()
    em_30d = hoje + timedelta(days=30)
    ano_atual = hoje.year

    func_ativos = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
    total_func_ativos = func_ativos.count()

    asos_qs = ASOOcupacional.objects.filter(empresa=empresa)
    asos_vencidos = asos_qs.filter(data_validade__lt=hoje).count()
    asos_vencendo_30d = asos_qs.filter(
        data_validade__gte=hoje, data_validade__lte=em_30d
    ).count()

    exames_qs = ExameOcupacional.objects.filter(empresa=empresa)
    exames_atrasados = exames_qs.filter(status="vencido").count()

    cats_abertas = CATOcupacional.objects.filter(
        empresa=empresa, status_esocial__in=("nao_enviado", "pendente", "erro")
    ).count()

    afas_ativos = AfastamentoSST.objects.filter(empresa=empresa, status="ativo").count()

    esocial_qs = eSocialEventoSST.objects.filter(empresa=empresa)
    esocial_erros = esocial_qs.filter(status="erro").count()
    esocial_pendentes = esocial_qs.filter(status__in=("pendente", "enviado")).count()

    trein_vencidos = TreinamentoNR.objects.filter(
        empresa=empresa,
        data_validade__isnull=False,
        data_validade__lt=hoje,
    ).count()

    epis_ativos_ids = set(
        EntregaEPI.objects.filter(
            empresa=empresa,
            data_devolucao__isnull=True,
        ).values_list("funcionario_id", flat=True)
    )
    sem_epi = max(total_func_ativos - len(epis_ativos_ids), 0)

    conformes = 0
    for f in func_ativos.only("id"):
        aso = asos_qs.filter(funcionario=f).order_by("-data_emissao").first()
        aso_ok = bool(aso and (aso.data_validade is None or aso.data_validade >= hoje))
        exame_vencido = exames_qs.filter(funcionario=f, status="vencido").exists()
        epi_ok = f.id in epis_ativos_ids
        trein_ok = TreinamentoNR.objects.filter(
            empresa=empresa, funcionario=f, data_validade__gte=hoje
        ).exists()
        if aso_ok and not exame_vencido and epi_ok and trein_ok:
            conformes += 1
    indice_conformidade = round((conformes / max(total_func_ativos, 1)) * 100, 1) if total_func_ativos else 0.0

    # Modelos de expansao SST
    from .models import (
        AvaliacaoPsicossocial,
        FAPEmpresa,
        LaudoTecnicoSST,
        PPPFuncionario,
        ResultadoExameLaboratorio,
    )

    psicossocial_ativas = AvaliacaoPsicossocial.objects.filter(
        empresa=empresa, status="ativa"
    ).count()
    ppp_pendentes = PPPFuncionario.objects.filter(
        empresa=empresa, status="rascunho"
    ).count()
    laudos_pendentes = LaudoTecnicoSST.objects.filter(
        empresa=empresa, status__in=("rascunho", "vencido")
    ).count()
    fap_ano_atual = FAPEmpresa.objects.filter(empresa=empresa, ano=ano_atual).count()
    laboratorio_alertas = ResultadoExameLaboratorio.objects.filter(
        empresa=empresa, criticidade__in=("atencao", "critico")
    ).count()

    prioridade_legal = []
    if esocial_erros:
        prioridade_legal.append(f"{esocial_erros} erro(s) no eSocial")
    if esocial_pendentes:
        prioridade_legal.append(f"{esocial_pendentes} pendencia(s) de transmissao eSocial")
    if cats_abertas:
        prioridade_legal.append(f"{cats_abertas} CAT(s) em aberto")
    prioridade_atencao = [
        f"{asos_vencidos} ASO(s) vencido(s)" if asos_vencidos else "",
        f"{exames_atrasados} exame(s) atrasado(s)" if exames_atrasados else "",
        f"{sem_epi} funcionario(s) sem EPI ativo" if sem_epi else "",
    ]
    prioridade_atencao = [msg for msg in prioridade_atencao if msg]

    return JsonResponse({
        "empresa_nome": empresa.nome,
        "gerado_em": dj_timezone.now().isoformat(),
        "kpis": {
            "funcionarios_ativos": total_func_ativos,
            "asos_vencidos": asos_vencidos,
            "asos_vencendo_30d": asos_vencendo_30d,
            "exames_atrasados": exames_atrasados,
            "cats_abertas": cats_abertas,
            "afastamentos_ativos": afas_ativos,
            "esocial_erros": esocial_erros,
            "esocial_pendentes": esocial_pendentes,
            "treinamentos_vencidos": trein_vencidos,
            "epis_sem_entrega": sem_epi,
            "conformidade_indice": indice_conformidade,
            "psicossocial_ativas": psicossocial_ativas,
            "ppp_pendentes": ppp_pendentes,
            "laudos_pendentes": laudos_pendentes,
            "laboratorio_alertas": laboratorio_alertas,
            "fap_ano_atual": fap_ano_atual,
        },
        "prioridades": {
            "legal": prioridade_legal,
            "atencao": prioridade_atencao,
        },
    })


# ── Funcionários ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_funcionarios(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = (
            FuncionarioSST.objects
            .filter(empresa=empresa, ativo=True)
            .select_related("unidade")
            .order_by("nome")
        )
        page, meta = _paginar(request, qs, limit_default=1000, limit_max=10000)
        return JsonResponse({
            "funcionarios": [
                {
                    "id": f.id,
                    "nome": f.nome,
                    "cpf": f.cpf,
                    "matricula": f.matricula,
                    "cargo": f.cargo,
                    "setor": f.setor,
                    "sexo": f.sexo,
                    "unidade": f.unidade.nome if f.unidade else None,
                    "data_admissao": f.data_admissao.strftime("%d/%m/%Y") if f.data_admissao else None,
                    "data_admissao_iso": str(f.data_admissao) if f.data_admissao else "",
                    "data_nascimento_iso": str(f.data_nascimento) if f.data_nascimento else "",
                    "classe_risco": f.classe_risco,
                }
                for f in page
            ],
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = (data.get("nome") or "").strip()
        cargo = (data.get("cargo") or "").strip()
        if not nome or not cargo:
            return JsonResponse({"erro": "nome e cargo são obrigatórios"}, status=400)

        ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf", ""), empresa)
        if not ok_cpf:
            return JsonResponse({"erro": erro_cpf}, status=400)

        contagem_atual = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        if not dentro_do_limite(empresa, "max_funcionarios", contagem_atual):
            return JsonResponse({
                "erro": "Limite de funcionarios do seu plano atingido. Faca upgrade para cadastrar mais.",
                "upgrade_necessario": True,
            }, status=403)

        f = FuncionarioSST.objects.create(
            empresa=empresa,
            nome=nome,
            cpf=_cpf_limpo(data.get("cpf", ""))[:11],
            matricula=data.get("matricula", ""),
            cargo=cargo,
            setor=data.get("setor", ""),
            classe_risco=data.get("classe_risco", "II"),
        )
        return JsonResponse({"id": f.id, "nome": f.nome}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_funcionario_detalhe(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "funcionário não encontrado"}, status=404)

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        if "nome" in data:
            func.nome = data["nome"].strip()[:200]
        if "cpf" in data:
            ok_cpf, erro_cpf = validar_cpf_cadastro(data["cpf"], empresa)
            if not ok_cpf:
                return JsonResponse({"erro": erro_cpf}, status=400)
            func.cpf = _cpf_limpo(data["cpf"])[:11]
        if "matricula" in data:
            func.matricula = data["matricula"].strip()[:40]
        if "cargo" in data:
            func.cargo = data["cargo"].strip()[:120]
        if "setor" in data:
            func.setor = data["setor"].strip()[:120]
        if "sexo" in data:
            func.sexo = data["sexo"]
        if "classe_risco" in data:
            func.classe_risco = data["classe_risco"]
        if data.get("data_nascimento"):
            from datetime import date as _date
            try:
                func.data_nascimento = _date.fromisoformat(data["data_nascimento"])
            except ValueError:
                pass
        if data.get("data_admissao"):
            from datetime import date as _date
            try:
                func.data_admissao = _date.fromisoformat(data["data_admissao"])
            except ValueError:
                pass
        func.save()
        return JsonResponse({"ok": True, "id": func.id, "nome": func.nome})

    if request.method == "DELETE":
        func.ativo = False
        func.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── ASO ───────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_asos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        from .views_solicitacao_exame import CATALOGO_EXAMES, PERFIS_EXAMES_FUNCAO
        ev_map = {}
        for ev in (
            eSocialEventoSST.objects
            .filter(empresa=empresa, tipo_evento="S-2220")
            .exclude(referencia="")
            .values("referencia", "status", "protocolo")
            .order_by("-id")
        ):
            ref = str(ev.get("referencia") or "").strip()
            if ref and ref not in ev_map:
                ev_map[ref] = {
                    "status": ev.get("status") or "nao_enviado",
                    "protocolo": ev.get("protocolo") or "",
                }
        qs = (
            ASOOcupacional.objects
            .filter(empresa=empresa)
            .select_related("funcionario")
            .prefetch_related("exames")
            .order_by("-data_emissao", "-id")
        )
        page, meta = _paginar(request, qs, limit_default=1000, limit_max=10000)
        return JsonResponse({
            "asos": [
                {
                    "id": a.id,
                    "funcionario": a.funcionario.nome,
                    "funcionario_id": a.funcionario_id,
                    "tipo": a.tipo,
                    "tipo_label": a.get_tipo_display(),
                    "data_emissao": a.data_emissao.strftime("%d/%m/%Y"),
                    "data_validade": a.data_validade.strftime("%d/%m/%Y") if a.data_validade else None,
                    "resultado": a.resultado,
                    "resultado_label": a.get_resultado_display(),
                    "medico": a.medico_responsavel,
                    "crm": a.crm,
                    "cid_inapto": a.cid_inapto,
                    "riscos_ocupacionais": a.riscos_ocupacionais,
                    "exames": [
                        e.observacoes or e.get_tipo_exame_display()
                        for e in a.exames.all()
                    ],
                    "restricoes": a.restricoes,
                    "observacoes": a.observacoes,
                    "status_esocial": ev_map.get(str(a.id), {}).get("status", "nao_enviado"),
                    "protocolo_esocial": ev_map.get(str(a.id), {}).get("protocolo", ""),
                }
                for a in page
            ],
            "catalogo_exames": CATALOGO_EXAMES,
            "perfis_funcao": PERFIS_EXAMES_FUNCAO,
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado. Cadastre-o primeiro em Funcionários."}, status=404)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        resultado = data.get("resultado", "apto")
        cid_inapto = (data.get("cid_inapto") or "").strip().upper()
        if resultado in ("inapto", "apto_restricao") and not cid_inapto:
            return JsonResponse({"erro": "CID é obrigatório quando o resultado for Inapto ou Apto com Restrição."}, status=400)
        aso = ASOOcupacional.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo=data.get("tipo", "periodico"),
            data_emissao=parse_date(data.get("data_emissao")) or date.today(),
            data_validade=parse_date(data.get("data_validade")),
            medico_responsavel=data.get("medico", ""),
            crm=data.get("crm", ""),
            resultado=data.get("resultado", "apto"),
            cid_inapto=(data.get("cid_inapto") or "").strip().upper(),
            riscos_ocupacionais=data.get("riscos_ocupacionais", ""),
            restricoes=data.get("restricoes", ""),
            observacoes=data.get("observacoes", ""),
        )
        exames = data.get("exames") or []
        if isinstance(exames, list):
            for nome_exame in exames:
                nome = str(nome_exame or "").strip()
                if not nome:
                    continue
                ExameOcupacional.objects.create(
                    empresa=empresa,
                    funcionario=func,
                    aso=aso,
                    tipo_exame=_classificar_tipo_exame(nome),
                    data_realizacao=aso.data_emissao,
                    data_validade=aso.data_validade,
                    resultado="Realizado / avaliado no ASO",
                    status="realizado",
                    observacoes=nome,
                )
        # notificação para o app do funcionário
        try:
            from .models import NotificacaoFuncionario
            tipo_label = dict(ASOOcupacional.TIPO).get(aso.tipo, aso.tipo)
            resultado_label = dict(ASOOcupacional.RESULTADO).get(aso.resultado, aso.resultado)
            NotificacaoFuncionario.objects.create(
                funcionario=func,
                empresa=empresa,
                tipo="aso",
                titulo=f"Novo ASO — {tipo_label}",
                mensagem=f"Um ASO {tipo_label} foi emitido para você. Resultado: {resultado_label}. Validade: {aso.data_validade.strftime('%d/%m/%Y') if aso.data_validade else '—'}.",
                referencia_id=aso.id,
            )
        except Exception:
            pass  # notificação é best-effort

        return JsonResponse({"id": aso.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── CAT ───────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_cats(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        s2210_map = {}
        for ev in (
            eSocialEventoSST.objects
            .filter(empresa=empresa, tipo_evento="S-2210")
            .exclude(referencia="")
            .values("id", "referencia", "status", "protocolo")
            .order_by("-id")
        ):
            ref = str(ev.get("referencia") or "").strip()
            if ref and ref not in s2210_map:
                s2210_map[ref] = ev
        qs = (
            CATOcupacional.objects
            .filter(empresa=empresa)
            .select_related("funcionario")
            .order_by("-data_acidente", "-id")
        )
        page, meta = _paginar(request, qs, limit_default=1000, limit_max=10000)
        return JsonResponse({
            "cats": [
                {
                    "id": c.id,
                    "funcionario": c.funcionario.nome,
                    "funcionario_cpf": c.funcionario.cpf,
                    "tipo": c.get_tipo_display(),
                    "tipo_raw": c.tipo,
                    "tp_cat": getattr(c, "tp_cat", "1"),
                    "gravidade": c.gravidade,
                    "data_acidente": c.data_acidente.strftime("%d/%m/%Y"),
                    "hora_acidente": c.hora_acidente.strftime("%H:%M") if c.hora_acidente else None,
                    "descricao": c.descricao,
                    "cid": c.cid,
                    "local_acidente": c.local_acidente,
                    "parte_corpo": c.parte_corpo,
                    "cod_parte_corpo": getattr(c, "cod_parte_corpo", "730"),
                    "lateralidade": getattr(c, "lateralidade", "9"),
                    "cod_agente_causador": getattr(c, "cod_agente_causador", "0099"),
                    "houve_afastamento": c.houve_afastamento,
                    "dias_afastamento": c.dias_afastamento,
                    "testemunha_nome": getattr(c, "testemunha_nome", ""),
                    "testemunha_telefone": getattr(c, "testemunha_telefone", ""),
                    "status_esocial": s2210_map.get(str(c.id), {}).get("status", c.status_esocial),
                    "numero_cat": c.numero_cat,
                    "protocolo_esocial": s2210_map.get(str(c.id), {}).get("protocolo") or c.protocolo_esocial,
                    "evento_id": s2210_map.get(str(c.id), {}).get("id"),
                }
                for c in page
            ],
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado. Cadastre-o primeiro em Funcionários."}, status=404)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        def _parse_hora(s):
            if not s:
                return None
            try:
                from datetime import time as dtime
                parts = s.replace(":", "").strip()
                return dtime(int(parts[:2]), int(parts[2:4]))
            except Exception:
                return None
        tipo_cat = data.get("tipo", "tipico")
        cid = (data.get("cid") or "").strip().upper()
        erro_cid = _validar_cid_doenca_trabalho(tipo_cat, cid)
        if erro_cid:
            return JsonResponse({"erro": erro_cid}, status=400)
        cat = CATOcupacional.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo=tipo_cat,
            tp_cat=data.get("tp_cat", "1"),
            gravidade=data.get("gravidade", "leve"),
            data_acidente=parse_date(data.get("data_acidente")) or date.today(),
            hora_acidente=_parse_hora(data.get("hora_acidente")),
            descricao=data.get("descricao", ""),
            local_acidente=data.get("local_acidente", ""),
            parte_corpo=data.get("parte_corpo", ""),
            cod_parte_corpo=data.get("cod_parte_corpo", "730"),
            lateralidade=data.get("lateralidade", "9"),
            cod_agente_causador=data.get("cod_agente_causador", "0099"),
            cid=cid,
            houve_afastamento=bool(data.get("houve_afastamento")),
            dias_afastamento=int(data.get("dias_afastamento") or 0),
            testemunha_nome=data.get("testemunha_nome", ""),
            testemunha_telefone=data.get("testemunha_telefone", ""),
        )
        return JsonResponse({"id": cat.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_sst_cids_ocupacionais(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    return JsonResponse({
        "grupos": [
            {
                "grupo": grupo["grupo"],
                "itens": [
                    {"codigo": codigo, "descricao": descricao}
                    for codigo, descricao in grupo["itens"]
                ],
            }
            for grupo in CID_SST_DOENCA_TRABALHO
        ],
        "total": sum(len(grupo["itens"]) for grupo in CID_SST_DOENCA_TRABALHO),
        "uso": "Selecionar quando o registro for doença ocupacional/doença do trabalho.",
    })


# ── Documentos SST ────────────────────────────────────────────────────────────

@csrf_exempt
def api_documentos_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = DocumentoSST.objects.filter(empresa=empresa)
        return JsonResponse({
            "documentos": [
                {
                    "id": d.id,
                    "tipo": d.tipo,
                    "titulo": d.titulo,
                    "status": d.status,
                    "validade": d.data_validade.strftime("%d/%m/%Y") if d.data_validade else None,
                    "responsavel": d.responsavel_tecnico,
                }
                for d in qs
            ]
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        doc = DocumentoSST.objects.create(
            empresa=empresa,
            tipo=data.get("tipo", "outro"),
            titulo=data.get("titulo", ""),
            status=data.get("status", "vigente"),
            responsavel_tecnico=data.get("responsavel", ""),
            registro_profissional=data.get("registro", ""),
            data_emissao=parse_date(data.get("data_emissao")),
            data_validade=parse_date(data.get("data_validade")),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": doc.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Afastamentos ──────────────────────────────────────────────────────────────

@csrf_exempt
@api_requer_feature("sst.afastamentos")
def api_afastamentos_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        s2230_map = {}
        for ev in (
            eSocialEventoSST.objects
            .filter(empresa=empresa, tipo_evento="S-2230")
            .exclude(referencia="")
            .values("id", "referencia", "status", "protocolo")
            .order_by("-id")
        ):
            ref = str(ev.get("referencia") or "").strip()
            if ref and ref not in s2230_map:
                s2230_map[ref] = ev
        qs = (
            AfastamentoSST.objects
            .filter(empresa=empresa)
            .select_related("funcionario")
            .order_by("-data_inicio", "-id")
        )
        page, meta = _paginar(request, qs, limit_default=1000, limit_max=10000)
        return JsonResponse({
            "afastamentos": [
                {
                    "id": a.id,
                    "funcionario": a.funcionario.nome,
                    "funcionario_id": a.funcionario_id,
                    "motivo": a.motivo,
                    "motivo_label": a.get_motivo_display(),
                    "cid": a.cid,
                    "data_inicio": a.data_inicio.isoformat(),
                    "data_inicio_br": a.data_inicio.strftime("%d/%m/%Y"),
                    "data_retorno": (a.data_retorno_real or a.data_prevista_retorno).isoformat() if (a.data_retorno_real or a.data_prevista_retorno) else None,
                    "data_retorno_br": (a.data_retorno_real or a.data_prevista_retorno).strftime("%d/%m/%Y") if (a.data_retorno_real or a.data_prevista_retorno) else None,
                    "status": a.status,
                    "s2230_status": s2230_map.get(str(a.id), {}).get("status"),
                    "s2230_evento_id": s2230_map.get(str(a.id), {}).get("id"),
                    "s2230_enviado": (s2230_map.get(str(a.id), {}).get("status") in {"pendente", "transmitido", "retificado"}),
                }
                for a in page
            ],
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, {
            "funcionario_nome": data.get("funcionario") or data.get("funcionario_nome"),
            "funcionario_id": data.get("funcionario_id"),
        })
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado. Cadastre-o primeiro em Funcionários."}, status=404)
        from datetime import datetime
        def parse_date(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        motivo = data.get("motivo") or "doenca_comum"
        cid = (data.get("cid") or "").strip().upper()
        erro_cid = _validar_cid_doenca_trabalho(motivo, cid)
        if erro_cid:
            return JsonResponse({"erro": erro_cid}, status=400)
        inicio = parse_date(data.get("data_inicio")) or date.today()
        retorno = parse_date(data.get("data_retorno") or data.get("data_prevista_retorno"))
        afastamento = AfastamentoSST.objects.create(
            empresa=empresa,
            funcionario=func,
            motivo=motivo,
            cid=cid,
            data_inicio=inicio,
            data_prevista_retorno=retorno,
            status="retorno_programado" if retorno else "ativo",
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": afastamento.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
@api_requer_feature("sst.afastamentos")
def api_afastamento_retorno(request, afastamento_id):
    """Registra retorno real de um afastamento."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    try:
        af = AfastamentoSST.objects.get(id=afastamento_id, empresa=empresa)
    except AfastamentoSST.DoesNotExist:
        return JsonResponse({"erro": "Afastamento não encontrado"}, status=404)

    if request.method in ("POST", "PATCH", "PUT"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        from datetime import datetime as _dt
        def _parse(s):
            if not s:
                return date.today()
            try:
                return _dt.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return date.today()
        af.data_retorno_real = _parse(data.get("data_retorno_real") or data.get("data_retorno"))
        af.status = "encerrado"
        af.save(update_fields=["data_retorno_real", "status", "atualizado_em"])
        # notifica funcionário
        try:
            from .models import NotificacaoFuncionario
            NotificacaoFuncionario.objects.create(
                funcionario=af.funcionario,
                empresa=empresa,
                tipo="geral",
                titulo="Retorno ao trabalho registrado",
                mensagem=f"Seu afastamento foi encerrado. Data de retorno: {af.data_retorno_real.strftime('%d/%m/%Y')}.",
                referencia_id=af.id,
            )
        except Exception:
            pass
        return JsonResponse({"ok": True, "status": "encerrado"})

    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_afastamentos_pdf(request):
    """GET — relatório PDF de afastamentos, com gráfico por motivo."""
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_afastamentos

    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    status_label = {"ativo": "Ativo", "encerrado": "Encerrado", "retorno_programado": "Retorno Programado"}
    linhas = []
    for a in (
        AfastamentoSST.objects
        .filter(empresa=empresa)
        .select_related("funcionario")
        .order_by("-data_inicio")
    ):
        retorno = a.data_retorno_real or a.data_prevista_retorno
        fim_calculo = a.data_retorno_real or hoje
        dias = (fim_calculo - a.data_inicio).days if a.data_inicio else 0
        linhas.append({
            "funcionario_nome": a.funcionario.nome,
            "motivo_label": a.get_motivo_display(),
            "cid": a.cid,
            "data_inicio": a.data_inicio.strftime("%d/%m/%Y") if a.data_inicio else None,
            "data_retorno": retorno.strftime("%d/%m/%Y") if retorno else None,
            "dias": max(dias, 0),
            "status_raw": a.status,
            "status_label": status_label.get(a.status, a.status),
        })

    pdf_bytes = gerar_pdf_afastamentos(linhas, empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="relatorio_afastamentos.pdf"'
    return resp


# ── Páginas SST ───────────────────────────────────────────────────────────────

def _sst_redirect(request):
    return redirect("/login-empresa/")


def sst_home_redirect(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)

    # info de trial para banner no dashboard
    trial_dias = None
    trial_ativo = False
    try:
        trial = empresa.trial
        if trial and not trial.convertido:
            from django.utils import timezone
            if trial.expira_em > timezone.now():
                trial_ativo = True
                trial_dias = trial.dias_restantes()
    except Exception:
        pass

    return render(request, "sst_hub.html", {
        "empresa_nome": empresa.nome,
        "trial_ativo": trial_ativo,
        "trial_dias": trial_dias,
    })


def sst_configuracoes_redirect(request):
    if not _empresa_autenticada(request):
        return _sst_redirect(request)
    return redirect("/dashboard-empresa/#sst")


@requer_permissao_modulo("sst.operacional")
def sst_funcionarios_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_funcionarios.html", {"empresa_nome": empresa.nome})


@requer_permissao_modulo("sst.operacional")
def sst_asos_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_asos.html", {"empresa_nome": empresa.nome})


@requer_permissao_modulo("sst.operacional")
def sst_exames_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_exames.html", {"empresa_nome": empresa.nome})


@requer_feature_pacote("sst.afastamentos", "Afastamentos")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_afastamentos_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_afastamentos.html", {"empresa_nome": empresa.nome})


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_cats_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_cats.html", {"empresa_nome": empresa.nome})


@requer_permissao_modulo("sst.operacional")
def sst_documentos_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_documentos.html", {"empresa_nome": empresa.nome})


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_esocial_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_esocial.html", {"empresa_nome": empresa.nome})


# ── Exames (API) ──────────────────────────────────────────────────────────────

@csrf_exempt
def api_exames(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        status_filtro = request.GET.get("status", "")
        qs = ExameOcupacional.objects.filter(empresa=empresa).select_related("funcionario")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        page, meta = _paginar(request, qs.order_by("data_realizacao"), limit_default=1000, limit_max=10000)
        return JsonResponse({
            "exames": [
                {
                    "id": e.id,
                    "funcionario_id": e.funcionario_id,
                    "funcionario": e.funcionario.nome,
                    "cargo": e.funcionario.cargo,
                    "tipo_exame": e.tipo_exame,
                    "tipo_exame_label": e.get_tipo_exame_display(),
                    "data_realizacao": e.data_realizacao.strftime("%Y-%m-%d") if e.data_realizacao else None,
                    "data_validade": e.data_validade.strftime("%Y-%m-%d") if e.data_validade else None,
                    "status": e.status,
                    "resultado": e.resultado,
                }
                for e in page
            ],
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
        tipos_validos = {tipo for tipo, _label in ExameOcupacional.TIPO_EXAME}
        status_validos = {status for status, _label in ExameOcupacional.STATUS}
        tipo = data.get("tipo_exame", "outro")
        if tipo not in tipos_validos:
            return JsonResponse({"erro": "Tipo de exame inválido"}, status=400)
        status = data.get("status", "pendente")
        if status not in status_validos:
            return JsonResponse({"erro": "Status de exame inválido"}, status=400)
        try:
            dr_str = data.get("data_realizacao") or ""
            dr = date.fromisoformat(dr_str) if dr_str else date.today()
        except ValueError:
            dr = date.today()
        try:
            dv_str = data.get("data_validade") or ""
            dv = date.fromisoformat(dv_str) if dv_str else None
        except ValueError:
            dv = None
        exame = ExameOcupacional.objects.create(
            empresa=empresa,
            funcionario=func,
            tipo_exame=tipo,
            data_realizacao=dr,
            data_validade=dv,
            resultado=data.get("resultado", ""),
            status=status,
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": exame.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── eSocial (API) ─────────────────────────────────────────────────────────────

@csrf_exempt
def api_esocial_eventos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = eSocialEventoSST.objects.filter(empresa=empresa).order_by("-criado_em")
        page, meta = _paginar(request, qs, limit_default=1000, limit_max=10000)
        return JsonResponse({
            "eventos": [
                {
                    "id": ev.id,
                    "tipo": ev.tipo_evento,
                    "label": dict(eSocialEventoSST.TIPO_EVENTO).get(ev.tipo_evento, ev.tipo_evento),
                    "status": ev.status,
                    "referencia": ev.referencia,
                    "protocolo": ev.protocolo,
                    "mensagem_erro": ev.mensagem_erro,
                    "data_envio": ev.data_envio.strftime("%d/%m/%Y %H:%M") if ev.data_envio else None,
                    "criado_em": ev.criado_em.strftime("%d/%m/%Y"),
                }
                for ev in page
            ],
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        ev = eSocialEventoSST.objects.create(
            empresa=empresa,
            tipo_evento=data.get("tipo_evento", "S-2220"),
            referencia=data.get("referencia", ""),
            status="pendente",
        )
        return JsonResponse({"id": ev.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Páginas: Relatórios e Agendamento ────────────────────────────────────────

@requer_permissao_modulo("sst.gestao_conformidade")
def sst_relatorios_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_relatorios.html", {"empresa_nome": empresa.nome})


@requer_feature_pacote("sst.agenda_medica", "Agenda Médica")
@requer_permissao_modulo("sst.operacional")
def sst_agendamento_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_agendamento.html", {"empresa_nome": empresa.nome})


def sst_funcionarios_novo_redirect(request):
    return redirect("/sst/funcionarios/?modal=novo")


def sst_documentos_novo_redirect(request):
    return redirect("/sst/documentos/?modal=novo")


# ── API: Relatórios ──────────────────────────────────────────────────────────

def _mes_label(ano, mes):
    meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    return f"{meses[mes-1]}/{str(ano)[2:]}"


def api_relatorios_sst(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    if hoje.month == 12:
        inicio_12m = date(hoje.year, 1, 1)
    else:
        inicio_12m = date(hoje.year - 1, hoje.month + 1, 1)

    # ── Série mensal de ASOs ──────────────────────────────────────────────────
    asos_qs = ASOOcupacional.objects.filter(empresa=empresa, data_emissao__gte=inicio_12m)
    asos_por_mes = defaultdict(int)
    for a in asos_qs.values("data_emissao"):
        d = a["data_emissao"]
        asos_por_mes[(d.year, d.month)] += 1

    # ── Série mensal de CATs ──────────────────────────────────────────────────
    cats_qs = CATOcupacional.objects.filter(empresa=empresa, data_acidente__gte=inicio_12m)
    cats_por_mes = defaultdict(int)
    for c in cats_qs.values("data_acidente"):
        d = c["data_acidente"]
        cats_por_mes[(d.year, d.month)] += 1

    # ── Série mensal de Afastamentos ─────────────────────────────────────────
    afas_qs = AfastamentoSST.objects.filter(empresa=empresa, data_inicio__gte=inicio_12m)
    afas_por_mes = defaultdict(int)
    dias_por_mes = defaultdict(int)
    for a in afas_qs.values("data_inicio", "data_retorno_real", "data_prevista_retorno"):
        d = a["data_inicio"]
        afas_por_mes[(d.year, d.month)] += 1
        fim = a["data_retorno_real"] or a["data_prevista_retorno"] or d
        dias_por_mes[(d.year, d.month)] += max(0, (fim - d).days)

    # ── Monta série ───────────────────────────────────────────────────────────
    serie = []
    m = inicio_12m
    while m <= hoje:
        k = (m.year, m.month)
        serie.append({
            "label": _mes_label(m.year, m.month),
            "ano": m.year,
            "mes": m.month,
            "asos": asos_por_mes.get(k, 0),
            "cats": cats_por_mes.get(k, 0),
            "afastamentos": afas_por_mes.get(k, 0),
            "dias_afastados": dias_por_mes.get(k, 0),
        })
        m = date(m.year + (1 if m.month == 12 else 0), (m.month % 12) + 1, 1)

    # ── Exames por tipo e status ──────────────────────────────────────────────
    exames_status = (
        ExameOcupacional.objects.filter(empresa=empresa)
        .values("tipo_exame", "status")
        .annotate(total=Count("id"))
    )
    exames_resumo = defaultdict(lambda: {"pendente": 0, "realizado": 0, "vencido": 0})
    for e in exames_status:
        exames_resumo[e["tipo_exame"]][e["status"]] = e["total"]

    tipo_labels = dict(ExameOcupacional.TIPO_EXAME)
    exames_out = [
        {
            "tipo": t,
            "label": tipo_labels.get(t, t),
            **cnts,
            "total": sum(cnts.values()),
        }
        for t, cnts in sorted(exames_resumo.items())
    ]

    # ── Documentos compliance ─────────────────────────────────────────────────
    docs_status = (
        DocumentoSST.objects.filter(empresa=empresa)
        .values("tipo", "status")
        .annotate(n=Count("id"))
    )
    docs_out = [{"tipo": d["tipo"], "status": d["status"], "total": d["n"]} for d in docs_status]

    # ── FAP inputs (referência) ───────────────────────────────────────────────
    total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
    total_cats_ano = CATOcupacional.objects.filter(empresa=empresa, data_acidente__year=hoje.year).count()
    total_afas_acidente = AfastamentoSST.objects.filter(
        empresa=empresa,
        data_inicio__year=hoje.year,
        motivo__in=["acidente_trabalho", "doenca_ocupacional"],
    ).count()
    freq_acidente = round((total_cats_ano / total_func * 1000), 2) if total_func > 0 else 0

    fap_inputs = {
        "total_funcionarios": total_func,
        "cats_ano": total_cats_ano,
        "afastamentos_acidente_ano": total_afas_acidente,
        "frequencia_acidente": freq_acidente,
        "referencia": f"Jan–{_mes_label(hoje.year, hoje.month)} {hoje.year}",
    }

    if request.GET.get("formato") == "csv":
        return _exportar_csv_relatorio(serie, empresa.nome)

    return JsonResponse({
        "serie_mensal": serie,
        "exames_por_tipo": exames_out,
        "documentos": docs_out,
        "fap_inputs": fap_inputs,
        "gerado_em": hoje.isoformat(),
    })


def _exportar_csv_relatorio(serie, empresa_nome):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Empresa", empresa_nome])
    w.writerow([])
    w.writerow(["Mês", "ASOs emitidos", "CATs registradas", "Afastamentos", "Dias afastados"])
    for s in serie:
        w.writerow([s["label"], s["asos"], s["cats"], s["afastamentos"], s["dias_afastados"]])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8-sig")
    resp["Content-Disposition"] = f'attachment; filename="sst_relatorio_{date.today()}.csv"'
    return resp


# ── Prontuário do Funcionário ─────────────────────────────────────────────────

@requer_permissao_modulo("sst.clinico")
def sst_prontuario_page(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return redirect("/sst/funcionarios/")
    return render(request, "sst_prontuario.html", {
        "empresa_nome": empresa.nome,
        "funcionario_id": funcionario_id,
        "funcionario_nome": func.nome,
    })


def api_prontuario_funcionario(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

    hoje = date.today()

    # ASOs
    asos = ASOOcupacional.objects.filter(empresa=empresa, funcionario=func).order_by("-data_emissao")
    asos_out = [
        {
            "id": a.id,
            "tipo": a.tipo,
            "tipo_label": a.get_tipo_display(),
            "data_emissao": a.data_emissao.strftime("%d/%m/%Y") if a.data_emissao else None,
            "data_validade": a.data_validade.strftime("%d/%m/%Y") if a.data_validade else None,
            "dias_restantes": (a.data_validade - hoje).days if a.data_validade else None,
            "medico": a.medico_responsavel,
            "resultado": a.resultado,
            "resultado_label": a.get_resultado_display(),
        }
        for a in asos
    ]

    # Exames
    exames = ExameOcupacional.objects.filter(empresa=empresa, funcionario=func).order_by("-data_realizacao")
    exames_out = [
        {
            "id": e.id,
            "tipo_exame": e.tipo_exame,
            "tipo_label": e.get_tipo_exame_display(),
            "data_realizacao": e.data_realizacao.strftime("%d/%m/%Y") if e.data_realizacao else None,
            "data_validade": e.data_validade.strftime("%d/%m/%Y") if e.data_validade else None,
            "dias_restantes": (e.data_validade - hoje).days if e.data_validade else None,
            "status": e.status,
            "resultado": e.resultado,
        }
        for e in exames
    ]

    # CATs
    cats = CATOcupacional.objects.filter(empresa=empresa, funcionario=func).order_by("-data_acidente")
    cats_out = [
        {
            "id": c.id,
            "tipo": c.tipo,
            "tipo_label": c.get_tipo_display(),
            "gravidade": c.gravidade,
            "gravidade_label": c.get_gravidade_display(),
            "data_acidente": c.data_acidente.strftime("%d/%m/%Y") if c.data_acidente else None,
            "cid": c.cid,
            "numero_cat": c.numero_cat,
            "status_esocial": c.status_esocial,
            "houve_afastamento": c.houve_afastamento,
        }
        for c in cats
    ]

    # Afastamentos
    afas = AfastamentoSST.objects.filter(empresa=empresa, funcionario=func).order_by("-data_inicio")
    afas_out = [
        {
            "id": a.id,
            "motivo": a.motivo,
            "motivo_label": a.get_motivo_display(),
            "cid": a.cid,
            "data_inicio": a.data_inicio.strftime("%d/%m/%Y") if a.data_inicio else None,
            "data_retorno": (a.data_retorno_real or a.data_prevista_retorno),
            "data_retorno_fmt": (a.data_retorno_real or a.data_prevista_retorno).strftime("%d/%m/%Y") if (a.data_retorno_real or a.data_prevista_retorno) else None,
            "dias": (a.data_retorno_real or a.data_prevista_retorno or hoje) and ((a.data_retorno_real or a.data_prevista_retorno or hoje) - a.data_inicio).days if a.data_inicio else None,
            "status": a.status,
            "status_label": a.get_status_display(),
        }
        for a in afas
    ]

    # Último ASO
    ultimo_aso = asos_out[0] if asos_out else None
    proximo_vencimento = None
    if ultimo_aso and ultimo_aso["dias_restantes"] is not None:
        proximo_vencimento = ultimo_aso["dias_restantes"]

    assinatura_prontuario = (
        AssinaturaDocumentoSST.objects
        .filter(empresa=empresa, funcionario=func, tipo_documento="prontuario")
        .order_by("-criado_em")
        .first()
    )
    assinatura_prontuario_assinada = (
        AssinaturaDocumentoSST.objects
        .filter(empresa=empresa, funcionario=func, tipo_documento="prontuario", status="assinado")
        .order_by("-assinado_em", "-criado_em")
        .first()
    )
    assinatura_prontuario_pendente = (
        AssinaturaDocumentoSST.objects
        .filter(empresa=empresa, funcionario=func, tipo_documento="prontuario", status="pendente")
        .order_by("-criado_em")
        .first()
    )
    assinatura_prontuario = assinatura_prontuario_assinada or assinatura_prontuario_pendente or assinatura_prontuario

    # App Ocupacional — verifica se funcionário tem credencial
    from .models import CredencialAppFuncionario
    try:
        cred_app = CredencialAppFuncionario.objects.get(funcionario=func, ativo=True)
        app_registrado = True
        app_email = cred_app.email
    except CredencialAppFuncionario.DoesNotExist:
        app_registrado = False
        app_email = None

    return JsonResponse({
        "funcionario": {
            "id": func.id,
            "nome": func.nome,
            "cpf": func.cpf,
            "matricula": func.matricula,
            "cargo": func.cargo,
            "setor": func.setor,
            "classe_risco": func.classe_risco,
            "classe_risco_label": func.get_classe_risco_display(),
            "data_admissao": func.data_admissao.strftime("%d/%m/%Y") if func.data_admissao else None,
            "ativo": func.ativo,
        },
        "resumo": {
            "total_asos": len(asos_out),
            "total_exames": len(exames_out),
            "total_cats": len(cats_out),
            "total_afastamentos": len(afas_out),
            "dias_ate_vencimento_aso": proximo_vencimento,
            "exames_vencidos": sum(1 for e in exames_out if e["status"] == "vencido"),
            "exames_pendentes": sum(1 for e in exames_out if e["status"] == "pendente"),
        },
        "asos": asos_out,
        "exames": exames_out,
        "cats": cats_out,
        "afastamentos": afas_out,
        "assinatura_prontuario": (
            {
                "id": assinatura_prontuario.id,
                "token": assinatura_prontuario.token,
                "status": assinatura_prontuario.status,
                "status_label": assinatura_prontuario.get_status_display(),
                "signatario_nome": assinatura_prontuario.signatario_nome,
                "signatario_cpf": assinatura_prontuario.signatario_cpf,
                "signatario_email": assinatura_prontuario.signatario_email,
                "criado_em": timezone.localtime(assinatura_prontuario.criado_em).strftime("%d/%m/%Y %H:%M"),
                "assinado_em": timezone.localtime(assinatura_prontuario.assinado_em).strftime("%d/%m/%Y %H:%M") if assinatura_prontuario.assinado_em else None,
                "link_assinatura": f"/assinatura/sst/{assinatura_prontuario.token}/",
                "link_validacao": f"/validar-assinatura/{assinatura_prontuario.token}/",
            }
            if assinatura_prontuario
            else None
        ),
        "app": {
            "registrado": app_registrado,
            "email": app_email,
        },
    })


# ── Convite App Ocupacional ───────────────────────────────────────────────────

@csrf_exempt
def api_convidar_app_funcionario(request, funcionario_id):
    """
    POST /api/sst/funcionarios/<id>/convidar-app
    Envia um email de convite ao funcionário para registrar-se no App Ocupacional.
    Body (opcional): { "email": "email_do_funcionario@ex.com" }
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

    # Verifica se já tem app registrado
    from .models import CredencialAppFuncionario
    try:
        cred = CredencialAppFuncionario.objects.get(funcionario=func, ativo=True)
        return JsonResponse({
            "status": "ja_registrado",
            "mensagem": f"Este funcionário já possui acesso ao app (e-mail: {cred.email}).",
            "email": cred.email,
        })
    except CredencialAppFuncionario.DoesNotExist:
        pass

    # Obtém o email de destino do body ou do funcionário
    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}

    email_destino = (body.get("email") or "").strip()
    if not email_destino or "@" not in email_destino:
        return JsonResponse({"erro": "Informe o e-mail do funcionário para enviar o convite."}, status=400)

    from .email_service import enviar_convite_app_funcionario
    enviar_convite_app_funcionario(func, empresa, email_destino)

    return JsonResponse({
        "status": "ok",
        "mensagem": f"Convite enviado para {email_destino}. O funcionário deve baixar o App Ocupacional SoloCRT e cadastrar-se com o CPF.",
    })


# ── Treinamentos NR ───────────────────────────────────────────────────────────

from .models import TreinamentoNR
from .normas_regulamentadoras import catalogo_normas_json_ready


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_treinamentos_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_treinamentos.html", {
        "empresa_nome": empresa.nome,
        "normas_json": json.dumps(catalogo_normas_json_ready()),
    })


def _criar_treinamento(empresa, func, data):
    """Cria um TreinamentoNR a partir do payload — compartilhado entre o registro
    individual (api_treinamentos) e o registro em lote (api_treinamentos_lote)."""
    tipo_treinamento = None
    if data.get("tipo_treinamento_id"):
        tipo_treinamento = TipoTreinamentoNR.objects.filter(id=data["tipo_treinamento_id"], empresa=empresa).first()

    nr = data.get("nr", "")
    if not nr and tipo_treinamento:
        nr = tipo_treinamento.nr
    categoria = data.get("categoria", "")
    if not categoria and tipo_treinamento:
        categoria = tipo_treinamento.categoria

    try:
        dr = date.fromisoformat(data.get("data_realizacao") or "") if data.get("data_realizacao") else None
    except ValueError:
        dr = None
    try:
        dv = date.fromisoformat(data.get("data_validade") or "") if data.get("data_validade") else None
    except ValueError:
        dv = None
    hoje = date.today()
    if dv and dv < hoje:
        status_auto = "vencido"
    elif dr and dr <= hoje:
        status_auto = "valido"
    elif dr and dr > hoje:
        status_auto = "agendado"
    else:
        status_auto = "pendente"

    carga_horaria = data.get("carga_horaria")
    if carga_horaria in (None, "") and tipo_treinamento:
        carga_horaria = tipo_treinamento.carga_horaria_padrao

    return TreinamentoNR.objects.create(
        empresa=empresa,
        funcionario=func,
        tipo_treinamento=tipo_treinamento,
        nr=nr,
        categoria=categoria,
        titulo=data.get("titulo", "") or (tipo_treinamento.nome if tipo_treinamento else ""),
        instrutor=data.get("instrutor", ""),
        carga_horaria=int(carga_horaria or 0),
        data_realizacao=dr,
        data_validade=dv,
        status=data.get("status") or status_auto,
        certificado=data.get("certificado", ""),
        observacoes=data.get("observacoes", ""),
    )


@csrf_exempt
def api_treinamentos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        status_filtro = request.GET.get("status", "")
        nr_filtro = request.GET.get("nr", "")
        qs = TreinamentoNR.objects.filter(empresa=empresa).select_related("funcionario").order_by("data_validade")
        if status_filtro:
            qs = qs.filter(status=status_filtro)
        if nr_filtro:
            qs = qs.filter(nr=nr_filtro)
        hoje = date.today()
        page, meta = _paginar(request, qs, limit_default=1000, limit_max=10000)
        return JsonResponse({
            "treinamentos": [
                {
                    "id": t.id,
                    "funcionario_id": t.funcionario_id,
                    "funcionario": t.funcionario.nome,
                    "cargo": t.funcionario.cargo,
                    "nr": t.nr,
                    "nr_label": t.get_nr_display() if t.nr else "",
                    "categoria": t.categoria,
                    "tipo_treinamento_id": t.tipo_treinamento_id,
                    "titulo": t.titulo,
                    "instrutor": t.instrutor,
                    "carga_horaria": t.carga_horaria,
                    "data_realizacao": t.data_realizacao.strftime("%d/%m/%Y") if t.data_realizacao else None,
                    "data_validade": t.data_validade.strftime("%d/%m/%Y") if t.data_validade else None,
                    "dias_restantes": (t.data_validade - hoje).days if t.data_validade else None,
                    "status": t.status,
                    "certificado": t.certificado,
                }
                for t in page
            ],
            **meta,
        })

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func = _buscar_funcionario(empresa, data)
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
        t = _criar_treinamento(empresa, func, data)
        return JsonResponse({"id": t.id, "ok": True}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_treinamentos_lote(request):
    """POST — registra o mesmo treinamento (turma/sessão) para uma LISTA de
    funcionários de uma vez, em vez de repetir o cadastro pessoa por pessoa."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    funcionario_ids = data.get("funcionario_ids") or []
    if not funcionario_ids:
        return JsonResponse({"erro": "Selecione ao menos um funcionário"}, status=400)

    from .models import FuncionarioSST
    funcionarios = list(FuncionarioSST.objects.filter(empresa=empresa, id__in=funcionario_ids))
    encontrados = {f.id for f in funcionarios}

    criados = []
    erros = []
    for fid in funcionario_ids:
        func = next((f for f in funcionarios if f.id == fid), None)
        if not func:
            erros.append({"funcionario_id": fid, "erro": "não encontrado"})
            continue
        try:
            t = _criar_treinamento(empresa, func, data)
            criados.append(t.id)
        except Exception as exc:
            erros.append({"funcionario_id": fid, "erro": str(exc)})

    return JsonResponse({"ok": True, "criados": len(criados), "ids": criados, "erros": erros}, status=201)


def api_treinamentos_resumo(request):
    """Resumo de treinamentos por NR e status — para dashboard."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    from django.db.models import Count
    hoje = date.today()
    vencendo_30 = TreinamentoNR.objects.filter(
        empresa=empresa, status="valido",
        data_validade__gte=hoje, data_validade__lte=hoje + timedelta(days=30),
    ).count()
    vencidos = TreinamentoNR.objects.filter(empresa=empresa, status="vencido").count()
    validos = TreinamentoNR.objects.filter(empresa=empresa, status="valido").count()
    pendentes = TreinamentoNR.objects.filter(empresa=empresa, status__in=["pendente","agendado"]).count()

    por_nr = (
        TreinamentoNR.objects.filter(empresa=empresa)
        .values("nr", "status")
        .annotate(total=Count("id"))
    )
    nr_map = {}
    nr_labels = dict(TreinamentoNR.NR_CHOICES)
    for row in por_nr:
        k = row["nr"]
        if k not in nr_map:
            nr_map[k] = {"nr": k, "label": nr_labels.get(k, k), "valido": 0, "vencido": 0, "pendente": 0, "agendado": 0}
        nr_map[k][row["status"]] = row["total"]

    return JsonResponse({
        "vencendo_30d": vencendo_30,
        "vencidos": vencidos,
        "validos": validos,
        "pendentes": pendentes,
        "por_nr": sorted(nr_map.values(), key=lambda x: x["nr"]),
    })


# ── Catálogo de Tipos de Treinamento (carga horária editável) ────────────────

@csrf_exempt
def api_tipos_treinamento(request):
    """GET lista tipos de treinamento do catálogo | POST cria novo tipo."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    if request.method == "GET":
        qs = TipoTreinamentoNR.objects.filter(empresa=empresa, ativo=True)
        return JsonResponse({"tipos": [{
            "id": t.id,
            "nr": t.nr,
            "nr_label": t.get_nr_display() if t.nr else "",
            "categoria": t.categoria,
            "rotulo_agrupamento": t.rotulo_agrupamento,
            "nome": t.nome,
            "carga_horaria_padrao": t.carga_horaria_padrao,
            "periodicidade_dias": t.periodicidade_dias,
        } for t in qs]})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = data.get("nome", "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        try:
            carga = int(data.get("carga_horaria_padrao") or 0)
        except (TypeError, ValueError):
            return JsonResponse({"erro": "carga_horaria_padrao inválida"}, status=400)
        if carga <= 0:
            return JsonResponse({"erro": "carga_horaria_padrao deve ser maior que zero"}, status=400)
        nr = data.get("nr", "")
        categoria = data.get("categoria", "").strip()
        if not nr and not categoria:
            return JsonResponse({"erro": "Informe a NR ou uma categoria livre (ex: Onboarding, Produto)"}, status=400)
        tipo, criado = TipoTreinamentoNR.objects.update_or_create(
            empresa=empresa, nr=nr, categoria=categoria, nome=nome,
            defaults={
                "carga_horaria_padrao": carga,
                "periodicidade_dias": data.get("periodicidade_dias") or None,
                "ativo": True,
            },
        )
        return JsonResponse({"id": tipo.id, "criado": criado}, status=201 if criado else 200)
    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_tipos_treinamento_detail(request, tipo_id):
    """PUT edita carga horária/periodicidade | DELETE inativa um tipo do catálogo."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    tipo = TipoTreinamentoNR.objects.filter(id=tipo_id, empresa=empresa).first()
    if not tipo:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        if "nome" in data and data["nome"].strip():
            tipo.nome = data["nome"].strip()
        if "nr" in data:
            tipo.nr = data["nr"]
        if "categoria" in data:
            tipo.categoria = data["categoria"].strip()
        if "carga_horaria_padrao" in data:
            try:
                carga = int(data["carga_horaria_padrao"])
            except (TypeError, ValueError):
                return JsonResponse({"erro": "carga_horaria_padrao inválida"}, status=400)
            if carga <= 0:
                return JsonResponse({"erro": "carga_horaria_padrao deve ser maior que zero"}, status=400)
            tipo.carga_horaria_padrao = carga
        if "periodicidade_dias" in data:
            tipo.periodicidade_dias = data["periodicidade_dias"] or None
        tipo.save()
        return JsonResponse({"ok": True})
    if request.method == "DELETE":
        tipo.ativo = False
        tipo.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Relatório de Homem-Hora (controle interno / auditoria) ───────────────────

def _homem_hora_linhas(empresa, data_ini=None, data_fim=None):
    qs = TreinamentoNR.objects.filter(empresa=empresa, status__in=["valido", "vencido"]).select_related("tipo_treinamento")
    if data_ini:
        qs = qs.filter(data_realizacao__gte=data_ini)
    if data_fim:
        qs = qs.filter(data_realizacao__lte=data_fim)
    grupos = {}
    nr_labels = dict(TreinamentoNR.NR_CHOICES)
    for t in qs:
        if t.tipo_treinamento:
            rotulo = t.tipo_treinamento.rotulo_agrupamento
            nome_tipo = t.tipo_treinamento.nome
        else:
            rotulo = nr_labels.get(t.nr, t.nr) if t.nr else (t.categoria or "Treinamento Geral")
            nome_tipo = t.titulo or "Sem título"
        chave = (rotulo, nome_tipo)
        if chave not in grupos:
            grupos[chave] = {"nr": rotulo, "nome_tipo": nome_tipo, "participantes": 0, "carga_horaria": t.carga_horaria, "homem_hora": 0}
        grupos[chave]["participantes"] += 1
        grupos[chave]["homem_hora"] += t.carga_horaria
    linhas = sorted(grupos.values(), key=lambda l: (l["nr"], l["nome_tipo"]))
    total_geral = sum(l["homem_hora"] for l in linhas)
    return linhas, total_geral


def api_treinamentos_homem_hora(request):
    """GET — relatório de homem-hora agregado por tipo/NR, para controle interno e auditoria."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    data_ini = request.GET.get("data_inicio") or None
    data_fim = request.GET.get("data_fim") or None
    linhas, total_geral = _homem_hora_linhas(empresa, data_ini, data_fim)
    return JsonResponse({"linhas": linhas, "total_geral": total_geral})


def api_treinamentos_homem_hora_pdf(request):
    """GET — relatório PDF de homem-hora agregado por tipo/NR."""
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_homem_hora_treinamentos
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    data_ini = request.GET.get("data_inicio") or None
    data_fim = request.GET.get("data_fim") or None
    linhas, total_geral = _homem_hora_linhas(empresa, data_ini, data_fim)
    if data_ini and data_fim:
        periodo_label = f"Período de {data_ini} a {data_fim}"
    else:
        periodo_label = "Todos os treinamentos válidos/concluídos"
    pdf_bytes = gerar_pdf_homem_hora_treinamentos(linhas, total_geral, empresa.nome, periodo_label)
    disposicao = "attachment" if request.GET.get("download") else "inline"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'{disposicao}; filename="relatorio_homem_hora_treinamentos.pdf"'
    return resp


@csrf_exempt
def api_treinamentos_homem_hora_email(request):
    """POST — envia o relatório de homem-hora em PDF por e-mail (transmissão)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    destinatario = (data.get("email") or "").strip()
    if not destinatario or "@" not in destinatario:
        return JsonResponse({"erro": "Informe um e-mail válido"}, status=400)

    from .pdf_sst import gerar_pdf_homem_hora_treinamentos
    from django.core.mail import EmailMessage

    data_ini = data.get("data_inicio") or None
    data_fim = data.get("data_fim") or None
    linhas, total_geral = _homem_hora_linhas(empresa, data_ini, data_fim)
    periodo_label = f"Período de {data_ini} a {data_fim}" if (data_ini and data_fim) else "Todos os treinamentos válidos/concluídos"
    pdf_bytes = gerar_pdf_homem_hora_treinamentos(linhas, total_geral, empresa.nome, periodo_label)

    try:
        msg = EmailMessage(
            subject=f"[SoloCRT] Relatório de Homem-Hora — {empresa.nome}",
            body=(
                f"Segue em anexo o relatório de homem-hora de treinamentos ({periodo_label}).\n\n"
                f"Total geral: {total_geral} homem-hora.\n\n"
                "-- \nSoloCRT · Sistema de Gestão SST"
            ),
            from_email=None,
            to=[destinatario],
        )
        msg.attach("relatorio_homem_hora_treinamentos.pdf", pdf_bytes, "application/pdf")
        enviados = msg.send(fail_silently=False)
        if enviados < 1:
            return JsonResponse({"erro": "Servidor de e-mail não confirmou o envio."}, status=502)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Erro ao enviar relatório de homem-hora por e-mail: %s", exc)
        return JsonResponse({"erro": f"Falha ao enviar e-mail: {exc}"}, status=502)

    return JsonResponse({"ok": True})


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_normas_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_normas.html", {
        "empresa_nome": empresa.nome,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  SST — Configurações
# ─────────────────────────────────────────────────────────────────────────────
from .models import ConfiguracaoSST, EPIItem, EntregaEPI, InspecaoEPI, InstrumentoMedicaoSST, TipoTreinamentoNR

@requer_permissao_modulo("sst.administracao")
def sst_configuracoes_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    import json as _json
    config_json = "null"
    if config:
        config_json = _json.dumps({
            "nome_medico_coordenador": config.nome_medico_coordenador,
            "crm_medico": config.crm_medico,
            "especialidade_medico": config.especialidade_medico,
            "nome_engenheiro": config.nome_engenheiro,
            "crea_engenheiro": config.crea_engenheiro,
            "nome_tecnico": config.nome_tecnico,
            "registro_tecnico": config.registro_tecnico,
            "nome_enfermeiro": config.nome_enfermeiro,
            "coren_enfermeiro": config.coren_enfermeiro,
            "alerta_aso_dias": config.alerta_aso_dias,
            "alerta_exame_dias": config.alerta_exame_dias,
            "alerta_treinamento_dias": config.alerta_treinamento_dias,
            "email_alertas": config.email_alertas,
            "alertas_ativos": config.alertas_ativos,
            "cnpj": config.cnpj,
            "cnae_principal": config.cnae_principal,
            "grau_risco": config.grau_risco,
            "numero_funcionarios": config.numero_funcionarios,
            "endereco_completo": config.endereco_completo,
        })
    return render(request, "sst_configuracoes.html", {
        "empresa_nome": empresa.nome,
        "config_json": config_json,
    })


@csrf_exempt
def api_sst_mensagem_massa(request):
    """Envia notificação/mensagem para todos os funcionários (ou de um setor)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    if request.method == "GET":
        # histórico: últimas 50 notificações gerais enviadas pela empresa
        from .models import NotificacaoFuncionario, EmpresaSetor
        items = list(
            NotificacaoFuncionario.objects
            .filter(empresa=empresa, tipo="geral")
            .values("id", "titulo", "mensagem", "criado_em", "funcionario__nome")
            .order_by("-criado_em")[:50]
        )
        # agrupa por (titulo, mensagem, criado_em) para mostrar uma linha por envio
        from itertools import groupby
        agrupado = {}
        for i in items:
            chave = (i["titulo"], i["mensagem"], i["criado_em"].strftime("%d/%m/%Y %H:%M"))
            agrupado.setdefault(chave, {"titulo": i["titulo"], "mensagem": i["mensagem"],
                                        "enviado_em": chave[2], "total": 0})
            agrupado[chave]["total"] += 1
        return JsonResponse({"mensagens": list(agrupado.values())[:20]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        titulo = (data.get("titulo") or data.get("assunto") or "").strip()[:200]
        mensagem = (data.get("mensagem") or data.get("corpo") or "").strip()
        setor_id = data.get("setor_id")
        if not titulo or not mensagem:
            return JsonResponse({"erro": "título e mensagem são obrigatórios"}, status=400)

        from .models import NotificacaoFuncionario
        qs = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
        if setor_id:
            qs = qs.filter(setor=setor_id)

        criados = 0
        for func in qs[:500]:
            NotificacaoFuncionario.objects.create(
                funcionario=func,
                empresa=empresa,
                tipo="geral",
                titulo=titulo,
                mensagem=mensagem,
            )
            criados += 1
        return JsonResponse({"ok": True, "enviados": criados}, status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_sst_configuracoes(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
        if not config:
            return JsonResponse({"config": None})
        return JsonResponse({"config": {
            "nome_medico_coordenador": config.nome_medico_coordenador,
            "crm_medico": config.crm_medico,
            "especialidade_medico": config.especialidade_medico,
            "nome_engenheiro": config.nome_engenheiro,
            "crea_engenheiro": config.crea_engenheiro,
            "nome_tecnico": config.nome_tecnico,
            "registro_tecnico": config.registro_tecnico,
            "nome_enfermeiro": config.nome_enfermeiro,
            "coren_enfermeiro": config.coren_enfermeiro,
            "alerta_aso_dias": config.alerta_aso_dias,
            "alerta_exame_dias": config.alerta_exame_dias,
            "alerta_treinamento_dias": config.alerta_treinamento_dias,
            "email_alertas": config.email_alertas,
            "alertas_ativos": config.alertas_ativos,
            "cnpj": config.cnpj,
            "cnae_principal": config.cnae_principal,
            "grau_risco": config.grau_risco,
            "numero_funcionarios": config.numero_funcionarios,
            "endereco_completo": config.endereco_completo,
        }})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        config, _ = ConfiguracaoSST.objects.get_or_create(empresa=empresa)
        fields = [
            "nome_medico_coordenador","crm_medico","especialidade_medico",
            "nome_engenheiro","crea_engenheiro","nome_tecnico","registro_tecnico",
            "nome_enfermeiro","coren_enfermeiro","email_alertas",
            "cnpj","cnae_principal","grau_risco","endereco_completo",
        ]
        for f in fields:
            if f in data:
                setattr(config, f, data[f])
        int_fields = ["alerta_aso_dias","alerta_exame_dias","alerta_treinamento_dias","numero_funcionarios"]
        for f in int_fields:
            if f in data:
                try:
                    setattr(config, f, int(data[f]))
                except (ValueError, TypeError):
                    pass
        if "alertas_ativos" in data:
            config.alertas_ativos = bool(data["alertas_ativos"])
        config.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"erro": "método não permitido"}, status=405)


# ─────────────────────────────────────────────────────────────────────────────
#  SST — EPI / EPC
# ─────────────────────────────────────────────────────────────────────────────

@requer_permissao_modulo("sst.gestao_conformidade")
def sst_epis_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_epis.html", {"empresa_nome": empresa.nome})


@csrf_exempt
def api_epis_catalogo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        epis = EPIItem.objects.filter(empresa=empresa, ativo=True)
        hoje = date.today()
        return JsonResponse({"epis": [{
            "id": e.id,
            "nome": e.nome,
            "tipo": e.tipo,
            "tipo_label": e.get_tipo_display(),
            "ca_numero": e.ca_numero,
            "validade_ca": e.validade_ca.isoformat() if e.validade_ca else None,
            "dias_validade_ca": (e.validade_ca - hoje).days if e.validade_ca else None,
            "fornecedor": e.fornecedor,
            "descricao": e.descricao,
            "exige_inspecao_periodica": e.exige_inspecao_periodica,
            "norma_inspecao": e.norma_inspecao,
            "periodicidade_inspecao_dias": e.periodicidade_inspecao_dias,
        } for e in epis]})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = data.get("nome","").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        epi = EPIItem.objects.create(
            empresa=empresa,
            nome=nome,
            tipo=data.get("tipo","outro"),
            ca_numero=data.get("ca_numero",""),
            validade_ca=data.get("validade_ca") or None,
            fornecedor=data.get("fornecedor",""),
            descricao=data.get("descricao",""),
            exige_inspecao_periodica=bool(data.get("exige_inspecao_periodica", False)),
            norma_inspecao=data.get("norma_inspecao",""),
            periodicidade_inspecao_dias=data.get("periodicidade_inspecao_dias") or None,
        )
        return JsonResponse({"id": epi.id, "nome": epi.nome}, status=201)
    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_epis_catalogo_lote(request):
    """Importação em lote de EPIs via CSV."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)

    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        return JsonResponse({"erro": "Envie o arquivo CSV no campo 'arquivo'."}, status=400)
    from .utils import validar_arquivo_upload
    erro_tipo = validar_arquivo_upload(arquivo)
    if erro_tipo:
        return JsonResponse({"erro": erro_tipo}, status=400)

    try:
        conteudo = arquivo.read().decode("utf-8-sig")
        leitor = csv.DictReader(io.StringIO(conteudo))
    except Exception:
        return JsonResponse({"erro": "Arquivo CSV inválido."}, status=400)

    importados = 0
    atualizados = 0
    erros = []
    tipo_map = {
        "protecao auditiva": "auditiva",
        "proteção auditiva": "auditiva",
        "auditiva": "auditiva",
        "protecao respiratoria": "respiratoria",
        "proteção respiratória": "respiratoria",
        "respiratoria": "respiratoria",
        "respiratória": "respiratoria",
        "protecao visual": "visual",
        "proteção visual": "visual",
        "visual": "visual",
        "protecao de maos": "maos",
        "proteção de mãos": "maos",
        "maos": "maos",
        "mãos": "maos",
        "protecao de pes": "pes",
        "proteção de pés": "pes",
        "pes": "pes",
        "pés": "pes",
        "protecao de cabeca": "cabeca",
        "proteção de cabeça": "cabeca",
        "cabeca": "cabeca",
        "cabeça": "cabeca",
        "protecao contra quedas": "altura",
        "proteção contra quedas": "altura",
        "altura": "altura",
        "protecao do corpo": "corpo",
        "proteção do corpo": "corpo",
        "corpo": "corpo",
        "outro": "outro",
    }

    for idx, row in enumerate(leitor, start=2):
        try:
            nome = (row.get("nome") or row.get("epi") or "").strip()
            if not nome:
                erros.append(f"Linha {idx}: nome obrigatório.")
                continue

            tipo_raw = (row.get("tipo") or "outro").strip().lower()
            tipo = tipo_map.get(tipo_raw, "outro")
            ca_numero = (row.get("ca_numero") or row.get("ca") or "").strip()
            validade_ca = (row.get("validade_ca") or row.get("validade") or "").strip() or None
            fornecedor = (row.get("fornecedor") or "").strip()
            descricao = (row.get("descricao") or row.get("observacoes") or "").strip()

            epi_qs = EPIItem.objects.filter(
                empresa=empresa,
                nome__iexact=nome,
                ca_numero__iexact=ca_numero,
                ativo=True,
            )
            epi = epi_qs.first()
            if epi:
                epi.tipo = tipo
                epi.validade_ca = validade_ca
                epi.fornecedor = fornecedor
                epi.descricao = descricao
                epi.save()
                atualizados += 1
            else:
                EPIItem.objects.create(
                    empresa=empresa,
                    nome=nome,
                    tipo=tipo,
                    ca_numero=ca_numero,
                    validade_ca=validade_ca,
                    fornecedor=fornecedor,
                    descricao=descricao,
                )
                importados += 1
        except Exception as ex:
            erros.append(f"Linha {idx}: {ex}")

    return JsonResponse({
        "ok": True,
        "importados": importados,
        "atualizados": atualizados,
        "erros": erros,
        "total_linhas": importados + atualizados + len(erros),
    })


@csrf_exempt
def api_epis_catalogo_detail(request, epi_id):
    """PUT /api/sst/epis/catalogo/<epi_id>/ — editar EPI do catálogo"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        epi = EPIItem.objects.get(id=epi_id, empresa=empresa)
    except EPIItem.DoesNotExist:
        return JsonResponse({"erro": "EPI não encontrado"}, status=404)
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = data.get("nome", "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        epi.nome = nome
        epi.tipo = data.get("tipo", epi.tipo)
        epi.ca_numero = data.get("ca_numero", epi.ca_numero)
        epi.validade_ca = data.get("validade_ca") or None
        epi.fornecedor = data.get("fornecedor", epi.fornecedor)
        epi.descricao = data.get("descricao", epi.descricao)
        if "exige_inspecao_periodica" in data:
            epi.exige_inspecao_periodica = bool(data["exige_inspecao_periodica"])
        if "norma_inspecao" in data:
            epi.norma_inspecao = data["norma_inspecao"]
        if "periodicidade_inspecao_dias" in data:
            epi.periodicidade_inspecao_dias = data["periodicidade_inspecao_dias"] or None
        epi.save()
        return JsonResponse({"id": epi.id, "nome": epi.nome, "ok": True})
    if request.method == "DELETE":
        epi.ativo = False
        epi.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_epis_entregas(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        func_id = request.GET.get("funcionario_id")
        qs = EntregaEPI.objects.filter(empresa=empresa).select_related("funcionario","epi")
        if func_id:
            qs = qs.filter(funcionario_id=func_id)
        hoje = date.today()
        ultima_por_entrega = {}
        for insp in InspecaoEPI.objects.filter(empresa=empresa, entrega_id__in=[e.id for e in qs]).order_by("-data_inspecao"):
            ultima_por_entrega.setdefault(insp.entrega_id, insp)
        resultado = []
        for e in qs:
            ultima = ultima_por_entrega.get(e.id)
            proxima_inspecao = ultima.proxima_inspecao if ultima else None
            resultado.append({
                "id": e.id,
                "funcionario_id": e.funcionario_id,
                "funcionario_nome": e.funcionario.nome,
                "epi_id": e.epi_id,
                "epi_nome": e.epi.nome,
                "epi_tipo": e.epi.get_tipo_display(),
                "ca_numero": e.epi.ca_numero,
                "numero_serie_item": e.numero_serie_item,
                "data_entrega": e.data_entrega.isoformat(),
                "quantidade": e.quantidade,
                "data_devolucao": e.data_devolucao.isoformat() if e.data_devolucao else None,
                "observacoes": e.observacoes,
                "ativo": e.data_devolucao is None,
                "exige_inspecao_periodica": e.epi.exige_inspecao_periodica,
                "norma_inspecao": e.epi.norma_inspecao,
                "ultima_inspecao": ultima.data_inspecao.isoformat() if ultima else None,
                "ultima_inspecao_resultado": ultima.resultado if ultima else None,
                "proxima_inspecao": proxima_inspecao.isoformat() if proxima_inspecao else None,
                "inspecao_vencida": bool(
                    e.epi.exige_inspecao_periodica and e.data_devolucao is None and
                    proxima_inspecao and proxima_inspecao < hoje
                ),
            })
        return JsonResponse({"entregas": resultado})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        from .models import FuncionarioSST
        func = FuncionarioSST.objects.filter(id=data.get("funcionario_id"), empresa=empresa).first()
        epi  = EPIItem.objects.filter(id=data.get("epi_id"), empresa=empresa).first()
        if not func or not epi:
            return JsonResponse({"erro": "funcionário ou EPI não encontrado"}, status=404)
        entrega = EntregaEPI.objects.create(
            empresa=empresa,
            funcionario=func,
            epi=epi,
            data_entrega=data.get("data_entrega") or date.today().isoformat(),
            quantidade=int(data.get("quantidade", 1)),
            numero_serie_item=data.get("numero_serie_item",""),
            observacoes=data.get("observacoes",""),
        )
        return JsonResponse({"id": entrega.id}, status=201)
    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_epis_devolver(request, entrega_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    entrega = EntregaEPI.objects.filter(id=entrega_id, empresa=empresa).first()
    if not entrega:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    entrega.data_devolucao = date.today()
    entrega.save(update_fields=["data_devolucao"])
    return JsonResponse({"ok": True})


def api_epis_pdf_ficha(request, funcionario_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import FuncionarioSST
    from .pdf_sst import gerar_pdf_ficha_epi
    from django.http import HttpResponse
    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    entregas = EntregaEPI.objects.filter(empresa=empresa, funcionario=func).select_related("epi")
    pdf_bytes = gerar_pdf_ficha_epi(func, entregas, empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="ficha_epi_{func.matricula or func.id}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
#  SST — Inspeção Periódica de EPI (NR-10 teste dielétrico, NR-35 talabarte/cinto etc.)
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_epi_inspecoes(request):
    """GET lista inspeções (todas ou por entrega) | POST registra nova inspeção."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        entrega_id = request.GET.get("entrega_id")
        qs = InspecaoEPI.objects.filter(empresa=empresa).select_related("entrega__funcionario", "entrega__epi")
        if entrega_id:
            qs = qs.filter(entrega_id=entrega_id)
        return JsonResponse({"inspecoes": [{
            "id": i.id,
            "entrega_id": i.entrega_id,
            "funcionario_nome": i.entrega.funcionario.nome,
            "epi_nome": i.entrega.epi.nome,
            "numero_serie_item": i.entrega.numero_serie_item,
            "data_inspecao": i.data_inspecao.isoformat(),
            "resultado": i.resultado,
            "resultado_label": i.get_resultado_display(),
            "responsavel_tecnico": i.responsavel_tecnico,
            "numero_laudo": i.numero_laudo,
            "proxima_inspecao": i.proxima_inspecao.isoformat() if i.proxima_inspecao else None,
            "observacoes": i.observacoes,
        } for i in qs]})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        entrega = EntregaEPI.objects.filter(id=data.get("entrega_id"), empresa=empresa).select_related("epi").first()
        if not entrega:
            return JsonResponse({"erro": "entrega de EPI não encontrada"}, status=404)
        data_inspecao = data.get("data_inspecao") or date.today().isoformat()
        proxima = data.get("proxima_inspecao")
        if not proxima and entrega.epi.periodicidade_inspecao_dias:
            from datetime import timedelta, datetime as dt
            base = dt.fromisoformat(data_inspecao).date() if isinstance(data_inspecao, str) else data_inspecao
            proxima = (base + timedelta(days=entrega.epi.periodicidade_inspecao_dias)).isoformat()
        inspecao = InspecaoEPI.objects.create(
            empresa=empresa,
            entrega=entrega,
            data_inspecao=data_inspecao,
            resultado=data.get("resultado", "aprovado"),
            responsavel_tecnico=data.get("responsavel_tecnico", ""),
            numero_laudo=data.get("numero_laudo", ""),
            proxima_inspecao=proxima or None,
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": inspecao.id}, status=201)
    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_epi_inspecoes_pendentes(request):
    """GET — entregas ativas de EPIs que exigem inspeção periódica, com status de vencimento."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    hoje = date.today()
    qs = EntregaEPI.objects.filter(
        empresa=empresa, data_devolucao__isnull=True, epi__exige_inspecao_periodica=True,
    ).select_related("funcionario", "epi")
    ultima_por_entrega = {}
    for insp in InspecaoEPI.objects.filter(empresa=empresa, entrega_id__in=[e.id for e in qs]).order_by("-data_inspecao"):
        ultima_por_entrega.setdefault(insp.entrega_id, insp)
    resultado = []
    for e in qs:
        ultima = ultima_por_entrega.get(e.id)
        proxima = ultima.proxima_inspecao if ultima else None
        resultado.append({
            "entrega_id": e.id,
            "funcionario_nome": e.funcionario.nome,
            "epi_nome": e.epi.nome,
            "norma_inspecao": e.epi.norma_inspecao,
            "numero_serie_item": e.numero_serie_item,
            "ultima_inspecao": ultima.data_inspecao.isoformat() if ultima else None,
            "proxima_inspecao": proxima.isoformat() if proxima else None,
            "dias_para_vencer": (proxima - hoje).days if proxima else None,
            "vencida": bool(proxima and proxima < hoje) or ultima is None,
        })
    resultado.sort(key=lambda r: (r["dias_para_vencer"] is None, r["dias_para_vencer"] if r["dias_para_vencer"] is not None else 0))
    return JsonResponse({"pendentes": resultado})


def api_epi_inspecoes_pdf(request):
    """GET — relatório PDF consolidado de inspeções periódicas de EPI."""
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_inspecoes_epi
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    inspecoes = InspecaoEPI.objects.filter(empresa=empresa).select_related(
        "entrega__funcionario", "entrega__epi"
    ).order_by("-data_inspecao")
    pdf_bytes = gerar_pdf_inspecoes_epi(inspecoes, empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="relatorio_inspecoes_epi.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
#  SST — Calibração de Instrumentos de Medição (decibelímetro, luxímetro etc.)
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_instrumentos_medicao(request):
    """GET lista instrumentos | POST cria novo instrumento."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    if request.method == "GET":
        hoje = date.today()
        qs = InstrumentoMedicaoSST.objects.filter(empresa=empresa, ativo=True)
        return JsonResponse({"instrumentos": [{
            "id": it.id,
            "nome": it.nome,
            "tipo": it.tipo,
            "tipo_label": it.get_tipo_display(),
            "numero_serie": it.numero_serie,
            "fabricante": it.fabricante,
            "norma_referencia": it.norma_referencia,
            "laboratorio_calibracao": it.laboratorio_calibracao,
            "numero_certificado": it.numero_certificado,
            "data_ultima_calibracao": it.data_ultima_calibracao.isoformat() if it.data_ultima_calibracao else None,
            "data_proxima_calibracao": it.data_proxima_calibracao.isoformat() if it.data_proxima_calibracao else None,
            "dias_para_vencer": (it.data_proxima_calibracao - hoje).days if it.data_proxima_calibracao else None,
            "status": it.status_calculado,
            "observacoes": it.observacoes,
        } for it in qs]})
    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = data.get("nome", "").strip()
        if not nome:
            return JsonResponse({"erro": "nome obrigatório"}, status=400)
        it = InstrumentoMedicaoSST.objects.create(
            empresa=empresa,
            nome=nome,
            tipo=data.get("tipo", "outro"),
            numero_serie=data.get("numero_serie", ""),
            fabricante=data.get("fabricante", ""),
            norma_referencia=data.get("norma_referencia", ""),
            laboratorio_calibracao=data.get("laboratorio_calibracao", ""),
            numero_certificado=data.get("numero_certificado", ""),
            data_ultima_calibracao=data.get("data_ultima_calibracao") or None,
            data_proxima_calibracao=data.get("data_proxima_calibracao") or None,
            status=data.get("status", "calibrado"),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"id": it.id}, status=201)
    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_instrumentos_medicao_detail(request, instrumento_id):
    """PUT edita | DELETE inativa um instrumento de medição."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    it = InstrumentoMedicaoSST.objects.filter(id=instrumento_id, empresa=empresa).first()
    if not it:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in ["nome", "tipo", "numero_serie", "fabricante", "norma_referencia",
                      "laboratorio_calibracao", "numero_certificado", "status", "observacoes"]:
            if campo in data:
                setattr(it, campo, data[campo])
        if "data_ultima_calibracao" in data:
            it.data_ultima_calibracao = data["data_ultima_calibracao"] or None
        if "data_proxima_calibracao" in data:
            it.data_proxima_calibracao = data["data_proxima_calibracao"] or None
        it.save()
        return JsonResponse({"ok": True})
    if request.method == "DELETE":
        it.ativo = False
        it.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_instrumentos_calibracao_pdf(request):
    """GET — relatório PDF consolidado de calibração de instrumentos."""
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_calibracao_instrumentos
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    instrumentos = InstrumentoMedicaoSST.objects.filter(empresa=empresa, ativo=True)
    pdf_bytes = gerar_pdf_calibracao_instrumentos(instrumentos, empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="relatorio_calibracao_instrumentos.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
#  SST — PDFs de ASO / CAT / Prontuário
# ─────────────────────────────────────────────────────────────────────────────

def api_aso_pdf(request, aso_id):
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_aso
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import ASOOcupacional, FuncionarioSST
    aso = ASOOcupacional.objects.filter(id=aso_id, funcionario__empresa=empresa).select_related("funcionario").first()
    if not aso:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    pdf_bytes = gerar_pdf_aso(aso, aso.funcionario, empresa.nome, config)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="aso_{aso.id}.pdf"'
    return resp


def api_cat_pdf(request, cat_id):
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_cat
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import CATOcupacional
    cat = CATOcupacional.objects.filter(id=cat_id, funcionario__empresa=empresa).select_related("funcionario").first()
    if not cat:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    config = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    pdf_bytes = gerar_pdf_cat(cat, cat.funcionario, empresa.nome, config)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="cat_{cat.id}.pdf"'
    return resp


def api_prontuario_pdf(request, funcionario_id):
    from django.http import HttpResponse
    from .pdf_sst import gerar_pdf_prontuario
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import FuncionarioSST, ASOOcupacional, ExameOcupacional, CATOcupacional, AfastamentoSST
    func = FuncionarioSST.objects.filter(id=funcionario_id, empresa=empresa).first()
    if not func:
        return JsonResponse({"erro": "não encontrado"}, status=404)
    asos        = ASOOcupacional.objects.filter(funcionario=func).order_by("-data_emissao")
    exames      = ExameOcupacional.objects.filter(funcionario=func).order_by("-data_realizacao")
    cats        = CATOcupacional.objects.filter(funcionario=func).order_by("-data_acidente")
    afastamentos = AfastamentoSST.objects.filter(funcionario=func).order_by("-data_inicio")
    pdf_bytes = gerar_pdf_prontuario(func, list(asos), list(exames), list(cats), list(afastamentos), empresa.nome)
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="prontuario_{func.matricula or func.id}.pdf"'
    return resp


def api_epis_sem_epi(request):
    """GET → funcionários sem nenhuma entrega de EPI ativa"""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    from .models import FuncionarioSST, EntregaEPI
    ativos = FuncionarioSST.objects.filter(empresa=empresa, ativo=True)
    # IDs que já têm pelo menos uma entrega sem devolução
    com_epi_ids = EntregaEPI.objects.filter(
        empresa=empresa, data_devolucao__isnull=True
    ).values_list("funcionario_id", flat=True)
    sem_epi = ativos.exclude(id__in=com_epi_ids)
    return JsonResponse({
        "funcionarios": [
            {"id": f.id, "nome": f.nome, "cargo": f.cargo or "—"}
            for f in sem_epi
        ],
        "total": sem_epi.count(),
    })


# ── Relatório de Conformidade SST ───────────────────────────────────────────────
def api_sst_conformidade(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    hoje = date.today()
    em_30d = hoje + timedelta(days=30)

    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).order_by("nome")
    from .models import EntregaEPI

    resultado = []
    for f in funcionarios:
        # ASO vigente
        aso = ASOOcupacional.objects.filter(funcionario=f, empresa=empresa).order_by("-data_emissao").first()
        aso_ok = aso is not None and (aso.data_validade is None or aso.data_validade >= hoje)
        aso_alerta = aso is not None and aso.data_validade and hoje <= aso.data_validade <= em_30d

        # Exames OK
        exames_vencidos = ExameOcupacional.objects.filter(
            empresa=empresa, funcionario=f, status="vencido"
        ).count()
        exames_ok = exames_vencidos == 0

        # EPI entregue
        epi_ativo = EntregaEPI.objects.filter(
            empresa=empresa, funcionario=f, data_devolucao__isnull=True
        ).exists()

        # Treinamentos válidos
        from .models import TreinamentoNR
        trein = TreinamentoNR.objects.filter(empresa=empresa, funcionario=f).order_by("-data_realizacao").first()
        trein_ok = trein is not None and (trein.data_validade is None or trein.data_validade >= hoje)

        # Afastamento ativo
        afastado = AfastamentoSST.objects.filter(empresa=empresa, funcionario=f, status="ativo").exists()

        score = sum([aso_ok, exames_ok, epi_ativo, trein_ok])
        status = "conforme" if score == 4 else ("alerta" if score >= 2 else "critico")

        resultado.append({
            "id": f.id,
            "nome": f.nome,
            "cargo": f.cargo,
            "setor": f.setor,
            "aso_ok": aso_ok,
            "aso_alerta": aso_alerta,
            "aso_validade": str(aso.data_validade) if aso and aso.data_validade else None,
            "exames_ok": exames_ok,
            "exames_vencidos": exames_vencidos,
            "epi_ok": epi_ativo,
            "treinamento_ok": trein_ok,
            "afastado": afastado,
            "score": score,
            "status": status,
        })

    total = len(resultado)
    conformes = sum(1 for r in resultado if r["status"] == "conforme")
    alertas = sum(1 for r in resultado if r["status"] == "alerta")
    criticos = sum(1 for r in resultado if r["status"] == "critico")

    return JsonResponse({
        "resumo": {
            "total": total,
            "conformes": conformes,
            "alertas": alertas,
            "criticos": criticos,
            "indice_conformidade": round(conformes / max(total, 1) * 100, 1),
        },
        "funcionarios": resultado,
    })


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_conformidade_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_conformidade.html", {"empresa_nome": empresa.nome})


@requer_permissao_modulo("sst.operacional")
def sst_bem_estar_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_redirect(request)
    return render(request, "sst_bem_estar.html", {"empresa_nome": empresa.nome})


def api_sst_conformidade_pdf(request):
    """Exporta relatório de conformidade SST em PDF."""
    from django.http import HttpResponse
    from .pdf_ops import gerar_pdf_conformidade_sst
    from .models import EntregaEPI
    from datetime import date, timedelta

    empresa = _empresa_autenticada(request)
    if not empresa:
        from django.http import JsonResponse
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    alerta_dias = 30
    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).order_by("nome")
    resultado = []

    for f in funcionarios:
        # ASO
        aso = ASOOcupacional.objects.filter(
            empresa=empresa,
            funcionario=f,
        ).order_by("-data_emissao").first()
        aso_ok = bool(aso and (aso.data_validade is None or aso.data_validade >= hoje))
        aso_alerta = bool(aso and aso.data_validade and hoje <= aso.data_validade <= hoje + timedelta(days=alerta_dias))

        # Exames
        exames = ExameOcupacional.objects.filter(empresa=empresa, funcionario=f)
        exames_vencidos = sum(1 for e in exames if e.data_validade and e.data_validade < hoje)
        exames_ok = exames.exists() and exames_vencidos == 0

        # EPI
        epi_ativo = EntregaEPI.objects.filter(
            empresa=empresa,
            funcionario=f,
            data_devolucao__isnull=True,
        ).exists()

        # Treinamento NR
        trein_ok = TreinamentoNR.objects.filter(
            empresa=empresa,
            funcionario=f,
            data_validade__gte=hoje,
        ).exists()

        # Afastamento
        afastado = AfastamentoSST.objects.filter(
            empresa=empresa,
            funcionario=f,
            status="ativo",
        ).exists()

        score = sum([aso_ok, exames_ok, epi_ativo, trein_ok])
        if score == 4:
            status = "conforme"
        elif score >= 2:
            status = "alerta"
        else:
            status = "critico"

        resultado.append({
            "nome": f.nome,
            "cargo": f.cargo,
            "setor": f.setor,
            "aso_ok": aso_ok,
            "aso_alerta": aso_alerta,
            "aso_validade": str(aso.data_validade) if aso and aso.data_validade else None,
            "exames_ok": exames_ok,
            "exames_vencidos": exames_vencidos,
            "epi_ok": epi_ativo,
            "treinamento_ok": trein_ok,
            "afastado": afastado,
            "score": score,
            "status": status,
        })

    total = len(resultado)
    conformes = sum(1 for r in resultado if r["status"] == "conforme")
    alertas = sum(1 for r in resultado if r["status"] == "alerta")
    criticos = sum(1 for r in resultado if r["status"] == "critico")
    resumo = {
        "total": total,
        "conformes": conformes,
        "alertas": alertas,
        "criticos": criticos,
        "indice_conformidade": round(conformes / max(total, 1) * 100, 1),
    }

    buf = gerar_pdf_conformidade_sst(empresa, resumo, resultado)
    resp = HttpResponse(buf, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="conformidade_sst.pdf"'
    return resp


@api_requer_feature("sst.relatorio_consolidado")
def api_sst_relatorio_consolidado_pdf(request):
    """Gera PDF consolidado de SST com conformidade, ASOs, exames, afastamentos, CATs e agenda."""
    from datetime import date, timedelta

    from django.http import HttpResponse, JsonResponse

    from .models import (
        ASOSSE,
        CATRegistro,
        AfastamentoSST,
        AgendamentoSST,
        DocumentoSST,
        EntregaEPI,
        ExameMedico,
        FuncionarioSST,
        InspecaoEPI,
        TreinamentoNR,
    )
    from .pdf_ops import gerar_pdf_relatorio_sst_consolidado
    from api.views_agendamento_sst import _agenda_to_dict

    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    alerta_dias = 30
    funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).order_by("nome")
    resultado = []

    for funcionario in funcionarios:
        aso = ASOOcupacional.objects.filter(
            empresa=empresa,
            funcionario=funcionario,
        ).order_by("-data_emissao").first()
        aso_ok = bool(aso and (aso.data_validade is None or aso.data_validade >= hoje))
        exames = ExameMedico.objects.filter(empresa=empresa, funcionario=funcionario)
        exames_vencidos = sum(1 for exame in exames if exame.data_validade and exame.data_validade < hoje)
        exames_ok = exames.exists() and exames_vencidos == 0
        epi_ativo = EntregaEPI.objects.filter(
            empresa=empresa,
            funcionario=funcionario,
            data_devolucao__isnull=True,
        ).exists()
        treinamento_ok = TreinamentoNR.objects.filter(
            empresa=empresa,
            funcionario=funcionario,
            data_validade__gte=hoje,
        ).exists()
        score = sum([aso_ok, exames_ok, epi_ativo, treinamento_ok])
        status = "conforme" if score == 4 else "alerta" if score >= 2 else "critico"
        resultado.append({
            "nome": funcionario.nome,
            "cargo": funcionario.cargo,
            "setor": funcionario.setor,
            "score": score,
            "status": status,
        })

    total = len(resultado)
    conformes = sum(1 for item in resultado if item["status"] == "conforme")
    alertas = sum(1 for item in resultado if item["status"] == "alerta")
    criticos = sum(1 for item in resultado if item["status"] == "critico")

    asos_lista = []
    for aso in ASOSSE.objects.filter(
        empresa=empresa,
        funcionario__empresa=empresa,
        funcionario__ativo=True,
    ).select_related("funcionario").order_by("data_validade"):
        vencido = aso.data_validade and aso.data_validade < hoje
        alerta = aso.data_validade and hoje <= aso.data_validade <= hoje + timedelta(days=alerta_dias)
        if vencido or alerta:
            asos_lista.append({
                "funcionario_nome": aso.funcionario.nome,
                "tipo_display": getattr(aso, "tipo", "—") or "—",
                "data_validade": str(aso.data_validade) if aso.data_validade else "—",
                "vencido": vencido,
                "alerta": alerta,
            })

    exames_vencidos_lista = []
    for exame in ExameMedico.objects.filter(
        empresa=empresa,
        funcionario__empresa=empresa,
        funcionario__ativo=True,
        data_validade__lt=hoje,
    ).select_related("funcionario").order_by("data_validade"):
        exames_vencidos_lista.append({
            "funcionario_nome": exame.funcionario.nome,
            "tipo_exame": getattr(exame, "tipo_exame", "—") or "—",
            "data_vencimento": str(exame.data_validade) if exame.data_validade else "—",
            "dias_vencido": (hoje - exame.data_validade).days if exame.data_validade else 0,
        })

    afastamentos_lista = []
    for afastamento in AfastamentoSST.objects.filter(
        empresa=empresa,
        funcionario__empresa=empresa,
        status="ativo",
    ).select_related("funcionario").order_by("data_inicio"):
        dias = (hoje - afastamento.data_inicio).days if afastamento.data_inicio else 0
        afastamentos_lista.append({
            "funcionario_nome": afastamento.funcionario.nome,
            "cid": getattr(afastamento, "cid", "—") or "—",
            "data_inicio": str(afastamento.data_inicio) if afastamento.data_inicio else "—",
            "dias": dias,
            "tipo_display": afastamento.get_motivo_display() if hasattr(afastamento, "get_motivo_display") else "—",
        })

    cats_lista = []
    for cat in CATRegistro.objects.filter(
        empresa=empresa,
        funcionario__empresa=empresa,
    ).select_related("funcionario").order_by("-data_acidente")[:30]:
        cats_lista.append({
            "funcionario_nome": cat.funcionario.nome,
            "data_acidente": str(cat.data_acidente) if cat.data_acidente else "—",
            "tipo_display": cat.get_tipo_display() if hasattr(cat, "get_tipo_display") else "—",
            "cid_principal": getattr(cat, "cid", "—") or "—",
            "status": getattr(cat, "status", "—"),
        })

    agendamentos = AgendamentoSST.objects.filter(
        empresa=empresa,
        status__in=["agendado", "confirmado"],
        data_hora__date__lt=hoje,
    ).select_related("funcionario").order_by("data_hora")[:30]

    treinamentos_lista = []
    for t in TreinamentoNR.objects.filter(
        empresa=empresa,
        funcionario__empresa=empresa,
        funcionario__ativo=True,
        data_validade__lte=hoje + timedelta(days=alerta_dias),
    ).select_related("funcionario", "tipo_treinamento").order_by("data_validade"):
        vencido = bool(t.data_validade and t.data_validade < hoje)
        nome_tipo = t.tipo_treinamento.rotulo_agrupamento if t.tipo_treinamento else (
            dict(TreinamentoNR.NR_CHOICES).get(t.nr, t.nr) if t.nr else (t.categoria or "Treinamento Geral")
        )
        treinamentos_lista.append({
            "funcionario_nome": t.funcionario.nome,
            "nr_display": nome_tipo,
            "data_validade": str(t.data_validade) if t.data_validade else "—",
            "situacao": "Vencido" if vencido else "Vencendo",
        })

    entregas_com_inspecao = EntregaEPI.objects.filter(
        empresa=empresa, data_devolucao__isnull=True, epi__exige_inspecao_periodica=True,
    ).select_related("funcionario", "epi")
    ultima_por_entrega = {}
    for insp in InspecaoEPI.objects.filter(
        empresa=empresa, entrega_id__in=[e.id for e in entregas_com_inspecao]
    ).order_by("-data_inspecao"):
        ultima_por_entrega.setdefault(insp.entrega_id, insp)
    inspecoes_lista = []
    for e in entregas_com_inspecao:
        ultima = ultima_por_entrega.get(e.id)
        proxima = ultima.proxima_inspecao if ultima else None
        vencida = bool(proxima and proxima < hoje) or ultima is None
        if not vencida:
            continue
        inspecoes_lista.append({
            "funcionario_nome": e.funcionario.nome,
            "epi_nome": e.epi.nome,
            "norma": e.epi.norma_inspecao or "—",
            "proxima_inspecao": str(proxima) if proxima else "Nunca inspecionado",
            "situacao": "Vencida" if (proxima and proxima < hoje) else "Sem inspeção",
        })

    documentos_lista = []
    for d in DocumentoSST.objects.filter(empresa=empresa).order_by("tipo"):
        documentos_lista.append({
            "tipo_display": d.get_tipo_display(),
            "titulo": d.titulo,
            "responsavel_tecnico": d.responsavel_tecnico,
            "data_validade": str(d.data_validade) if d.data_validade else "—",
            "status": d.status,
            "status_display": d.get_status_display(),
        })

    dados = {
        "resumo": {
            "total": total,
            "conformes": conformes,
            "alertas": alertas,
            "criticos": criticos,
            "indice_conformidade": round(conformes / max(total, 1) * 100, 1),
        },
        "funcionarios": resultado,
        "asos": asos_lista,
        "exames_vencidos": exames_vencidos_lista,
        "afastamentos": afastamentos_lista,
        "cats": cats_lista,
        "agendamentos_atrasados": [_agenda_to_dict(item) for item in agendamentos],
        "treinamentos_nr": treinamentos_lista,
        "inspecoes_epi": inspecoes_lista,
        "documentos_sst": documentos_lista,
    }

    buffer = gerar_pdf_relatorio_sst_consolidado(empresa, dados)
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="sst_relatorio_consolidado_{hoje}.pdf"'
    return response
