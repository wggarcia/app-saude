from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import CheckinDiarioCorporativo, CheckinSemanalCorporativo, PedidoApoioCorporativo
from .planos import detalhes_pacote


MIN_GROUP_SIZE = 8


def _safe_avg(payload, key, digits=1):
    value = payload.get(key)
    return round(float(value or 0.0), digits)


def _mood_score(diario):
    humor = _safe_avg(diario, "avg_humor")
    energia = _safe_avg(diario, "avg_energia")
    sono = _safe_avg(diario, "avg_sono")
    estresse = _safe_avg(diario, "avg_estresse")
    score = ((humor + energia + sono) / 3.0) * 20 - (estresse - 1.0) * 8
    return max(0, min(100, round(score)))


def _risk_band(value):
    if value >= 75:
        return "critico"
    if value >= 55:
        return "alto"
    if value >= 35:
        return "moderado"
    return "baixo"


def _stress_score(diario, semanal):
    estresse = _safe_avg(diario, "avg_estresse")
    ansiedade = _safe_avg(diario, "avg_ansiedade")
    carga = _safe_avg(semanal, "avg_carga_emocional")
    burnout = _safe_avg(semanal, "avg_risco_burnout")
    score = ((estresse + ansiedade + carga + burnout) / 4.0) * 25
    return max(0, min(100, round(score)))


def _physical_score(diario):
    fadiga = _safe_avg(diario, "avg_fadiga")
    dor = _safe_avg(diario, "avg_dor_fisica")
    sono_ruim = max(0, 5 - _safe_avg(diario, "avg_sono"))
    sintomas = diario.get("respiratorios", 0) + diario.get("dor_corporal_total", 0) + diario.get("cefaleia_total", 0)
    respondents = diario.get("respondents", 0) or 1
    symptom_pressure = min(4.0, (sintomas / respondents) * 4.0)
    score = ((fadiga + dor + sono_ruim + symptom_pressure) / 4.0) * 25
    return max(0, min(100, round(score)))


def _top_signal(diario):
    candidates = {
        "estresse elevado": _safe_avg(diario, "avg_estresse"),
        "fadiga fisica": _safe_avg(diario, "avg_fadiga"),
        "sono ruim": max(0, 5 - _safe_avg(diario, "avg_sono")),
        "ansiedade": _safe_avg(diario, "avg_ansiedade"),
    }
    return max(candidates, key=candidates.get) if candidates else "bem-estar geral"


def _top_units(base_diario):
    rows = (
        base_diario.exclude(unidade__isnull=True)
        .values("unidade__nome")
        .annotate(
            respondents=Count("id"),
            avg_estresse=Avg("estresse"),
            avg_fadiga=Avg("fadiga"),
            avg_humor=Avg("humor"),
            avg_sono=Avg("sono"),
        )
        .order_by("-respondents", "-avg_estresse")[:8]
    )
    results = []
    for row in rows:
        if row["respondents"] < MIN_GROUP_SIZE:
            continue
        stress_score = ((float(row["avg_estresse"] or 0.0) + float(row["avg_fadiga"] or 0.0)) / 2.0) * 25
        results.append({
            "name": row["unidade__nome"],
            "respondents": row["respondents"],
            "risk_score": round(stress_score),
            "risk_band": _risk_band(stress_score),
        })
    return results


def _build_recommendations(company, mood_score, stress_score, physical_score, support_count, top_signal):
    actions = []

    if stress_score >= 55:
        actions.append({
            "title": "Pressao psicossocial em alta",
            "urgency": _risk_band(stress_score),
            "summary": "Reforcar pausas, acolhimento de lideranca e monitorar sobrecarga nas equipes com piora recente.",
            "action": "Campanha de recuperacao emocional e escuta ativa em 7 dias.",
        })

    if physical_score >= 55:
        actions.append({
            "title": "Sinais fisicos recorrentes",
            "urgency": _risk_band(physical_score),
            "summary": "Aumentaram fadiga, dor ou sono ruim, o que sugere pressao operacional ou ergonomica.",
            "action": "Avaliar escala, ergonomia e pausas curtas nas unidades mais pressionadas.",
        })

    if support_count > 0:
        actions.append({
            "title": "Pedidos de apoio ativos",
            "urgency": "moderado" if support_count < 3 else "alto",
            "summary": f"Existem {support_count} pedidos de apoio abertos aguardando fluxo institucional.",
            "action": "Definir rota de acolhimento pelo RH ou saude ocupacional.",
        })

    if not actions:
        actions.append({
            "title": "Cenario inicial estavel",
            "urgency": "baixo",
            "summary": f"{company} ainda nao apresenta pressao agregada suficiente para um alerta critico.",
            "action": "Expandir adesao aos check-ins e acompanhar o sinal dominante.",
        })

    return {
        "top_signal": top_signal,
        "actions": actions,
        "headline": (
            f"O sinal dominante atual e {top_signal}. "
            f"Bem-estar em {mood_score}/100, risco psicossocial em {stress_score}/100 e risco fisico em {physical_score}/100."
        ),
    }


def _risk_summary(score):
    band = _risk_band(score)
    if band == "critico":
        return "exige resposta executiva imediata"
    if band == "alto":
        return "precisa de intervencao coordenada"
    if band == "moderado":
        return "pede acompanhamento proximo"
    return "permite consolidar prevencao"


def build_empresa_corporativo_payload(empresa):
    pacote = detalhes_pacote(empresa.pacote_codigo)
    company_label = empresa.nome or "Empresa"
    now = timezone.now()
    daily_cutoff = now.date() - timedelta(days=30)
    weekly_cutoff = now.date() - timedelta(days=84)

    base_diario = CheckinDiarioCorporativo.objects.filter(empresa=empresa, data_referencia__gte=daily_cutoff)
    base_semanal = CheckinSemanalCorporativo.objects.filter(empresa=empresa, semana_referencia__gte=weekly_cutoff)
    support_count = PedidoApoioCorporativo.objects.filter(
        empresa=empresa,
        status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE],
    ).count()

    diario = base_diario.aggregate(
        respondents=Count("id"),
        avg_humor=Avg("humor"),
        avg_energia=Avg("energia"),
        avg_estresse=Avg("estresse"),
        avg_sono=Avg("sono"),
        avg_dor_fisica=Avg("dor_fisica"),
        avg_fadiga=Avg("fadiga"),
        avg_ansiedade=Avg("ansiedade"),
        avg_tristeza=Avg("tristeza"),
        avg_irritabilidade=Avg("irritabilidade"),
        respiratorios=Count("id", filter=Q(sintomas_respiratorios=True)),
        dor_corporal_total=Count("id", filter=Q(dor_corporal=True)),
        cefaleia_total=Count("id", filter=Q(dor_cabeca=True)),
        pedidos_apoio=Count("id", filter=Q(apoio_solicitado=True)),
    )
    semanal = base_semanal.aggregate(
        weekly_respondents=Count("id"),
        avg_carga_emocional=Avg("carga_emocional"),
        avg_seguranca_psicologica=Avg("seguranca_psicologica"),
        avg_apoio_percebido=Avg("apoio_percebido"),
        avg_pressao_trabalho=Avg("pressao_trabalho"),
        avg_bem_estar_geral=Avg("bem_estar_geral"),
        avg_risco_burnout=Avg("risco_burnout"),
    )

    mood_score = _mood_score(diario)
    stress_score = _stress_score(diario, semanal)
    physical_score = _physical_score(diario)
    top_signal = _top_signal(diario)
    top_units = _top_units(base_diario)
    recommendations = _build_recommendations(company_label, mood_score, stress_score, physical_score, support_count, top_signal)

    respondents = diario.get("respondents", 0)
    weekly_respondents = semanal.get("weekly_respondents", 0)
    privacy_ready = respondents >= MIN_GROUP_SIZE or weekly_respondents >= MIN_GROUP_SIZE

    return {
        "product": {
            "name": "SolusCRT Corporativo",
            "subtitle": "Saude ocupacional, bem-estar e inteligencia institucional",
            "company": company_label,
            "package_label": pacote["label"],
        },
        "ecosystem": {
            "name": "Ecossistema Institucional SolusCRT",
            "segments": ["SaaS empresarial", "Farmacia", "Hospital", "Operacao territorial"],
            "promise": (
                "Uma unica camada institucional para autenticar operacoes setoriais e abrir "
                "o ambiente adequado apos o login."
            ),
        },
        "access_code": empresa.codigo_acesso_corporativo,
        "hero": {
            "title": "Centro de Saude Corporativa",
            "summary": (
                f"{company_label} opera um ambiente proprio para saude ocupacional, risco psicossocial, "
                "bem-estar e prevencao institucional com leitura anonima da forca de trabalho."
            ),
            "positioning": (
                "Este produto nao replica o dashboard epidemiologico. Ele funciona como um command center "
                "executivo para RH, SESMT, lideranca e seguranca do trabalho."
            ),
            "value_points": [
                "antecipar absenteismo e fadiga antes de virar afastamento",
                "detectar pressao psicossocial, burnout e queda de seguranca psicologica",
                "cruzar sinais fisicos e emocionais com resposta institucional acionavel",
            ],
        },
        "executive_cards": [
            {
                "label": "Bem-estar geral",
                "value": f"{mood_score}/100",
                "detail": f"Score lider para confiabilidade operacional; {_risk_summary(mood_score)}.",
            },
            {
                "label": "Risco psicossocial",
                "value": _risk_band(stress_score).upper(),
                "detail": f"Indice {stress_score}/100 com foco em estresse, ansiedade, carga emocional e burnout.",
            },
            {
                "label": "Risco fisico",
                "value": _risk_band(physical_score).upper(),
                "detail": f"Indice {physical_score}/100 para fadiga, dor, sono ruim e carga fisica recorrente.",
            },
            {
                "label": "Pedidos de apoio",
                "value": str(support_count),
                "detail": "Fila de acolhimento institucional e cuidado ativo.",
            },
        ],
        "priority_needs": [
            {
                "title": "Burnout e absenteismo",
                "detail": "Empresas precisam enxergar sinais precoces de exaustao, afastamento e perda de energia antes do impacto operacional.",
                "evidence": "Gallup relaciona burnout a mais ausencia, turnover e queda de desempenho.",
            },
            {
                "title": "Risco psicossocial e seguranca",
                "detail": "Pressao, baixa autonomia, falta de apoio do gestor e medo de falar elevam risco ocupacional e mental.",
                "evidence": "WHO destaca riscos psicossociais, assedio, longas jornadas e baixo suporte como foco central.",
            },
            {
                "title": "Retorno ao trabalho e apoio humano",
                "detail": "Fluxos de apoio e retorno gradual reduzem agravamento e ajudam a manter vinculo com o trabalho.",
                "evidence": "WHO recomenda retorno assistido, acomodacoes razoaveis e apoio continuo.",
            },
            {
                "title": "Formacao gerencial",
                "detail": "A lideranca imediata precisa de sinais simples para agir com pausa, acolhimento, escala e carga de trabalho.",
                "evidence": "Gallup aponta o gestor como agente-chave na prevencao do burnout.",
            },
        ],
        "pillars": [
            {
                "title": "Saude mental",
                "description": "Estresse, fadiga emocional, burnout, sobrecarga e seguranca psicologica com leitura agregada.",
                "metrics": [
                    f"estresse medio {_safe_avg(diario, 'avg_estresse')}/5",
                    f"ansiedade media {_safe_avg(diario, 'avg_ansiedade')}/5",
                    f"carga emocional {_safe_avg(semanal, 'avg_carga_emocional')}/5",
                    f"burnout {_safe_avg(semanal, 'avg_risco_burnout')}/5",
                ],
            },
            {
                "title": "Saude fisica e ocupacional",
                "description": "Dor, fadiga fisica, sono ruim, sinais respiratorios e carga ergonomica por contexto operacional.",
                "metrics": [
                    f"fadiga media {_safe_avg(diario, 'avg_fadiga')}/5",
                    f"dor fisica {_safe_avg(diario, 'avg_dor_fisica')}/5",
                    f"sono {_safe_avg(diario, 'avg_sono')}/5",
                    f"sinais respiratorios {diario.get('respiratorios', 0)}",
                ],
            },
            {
                "title": "Unidades e equipes",
                "description": "Leitura agregada por unidade, setor, turno e tendencia operacional sem expor individuos.",
                "metrics": [
                    f"respondentes diarios {respondents}",
                    f"respondentes semanais {weekly_respondents}",
                    f"top signal {top_signal}",
                    f"unidades com leitura {len(top_units)}",
                ],
            },
            {
                "title": "IA corporativa",
                "description": "Recomendacoes de campanha, apoio, escala e prevencao com explicacao para RH e lideranca.",
                "metrics": [
                    recommendations["actions"][0]["title"],
                    recommendations["actions"][0]["urgency"],
                    f"acoes {len(recommendations['actions'])}",
                    "plano semanal",
                ],
            },
        ],
        "command_center": [
            {
                "title": "Radar de absenteismo",
                "summary": "Conecta humor, energia, sono e burnout para antecipar perda de presenca e confiabilidade operacional.",
                "focus": "lideranca, RH e operacao",
            },
            {
                "title": "Risco psicossocial",
                "summary": "Monitora estresse, ansiedade, seguranca psicologica e pressao do trabalho por grupos anonimos.",
                "focus": "SESMT, RH e compliance",
            },
            {
                "title": "Carga fisica e ergonomia",
                "summary": "Ajuda a detectar onde a rotina esta produzindo fadiga, dor corporal, sono ruim e sobrecarga fisica.",
                "focus": "medicina do trabalho e operacao",
            },
            {
                "title": "Apoio e retorno ao trabalho",
                "summary": "Organiza fila de apoio, acolhimento e plano gradual de retorno sem transformar o sistema em prontuario.",
                "focus": "saude ocupacional e people",
            },
        ],
        "summary": {
            "respondents": respondents,
            "weekly_respondents": weekly_respondents,
            "privacy_ready": privacy_ready,
            "top_signal": top_signal,
            "headline": recommendations["headline"],
        },
        "recommendations": recommendations["actions"],
        "top_units": top_units,
        "programs": [
            {
                "title": "Programa de recuperacao de fadiga",
                "owner": "operacao + lideranca",
                "items": [
                    "revisao de pausas e micro-recuperacao",
                    "monitor de energia e sono por unidade",
                    "intervencao em turnos com piora consecutiva",
                ],
            },
            {
                "title": "Programa de risco psicossocial",
                "owner": "RH + SESMT",
                "items": [
                    "escuta estruturada em areas com stress alto",
                    "ritual gerencial semanal de carga e apoio",
                    "monitor de seguranca psicologica por grupo minimo",
                ],
            },
            {
                "title": "Programa de ergonomia e sintoma fisico",
                "owner": "saude ocupacional",
                "items": [
                    "mapa de dor corporal por frente operacional",
                    "campanhas de postura e recuperacao",
                    "acionamento rapido para clusters fisicos",
                ],
            },
        ],
        "privacy": {
            "group_minimum": MIN_GROUP_SIZE,
            "ready": privacy_ready,
            "principles": [
                "sem exibicao de dado individual no painel da empresa",
                "grupos pequenos ficam ocultos",
                "pedido de apoio nominal so com consentimento",
                "auditoria institucional em acessos e exportacoes",
            ],
        },
        "app_employee": {
            "title": "App do colaborador",
            "subtitle": "Jornada dedicada para check-ins, autocuidado e pedido seguro de apoio.",
            "screens": [
                "onboarding e privacidade",
                "check-in diario",
                "check-in semanal",
                "registrar sinais",
                "meu cuidado",
                "pedir apoio",
                "historico pessoal",
            ],
            "journey": [
                "check-in rapido sem exposicao ao gestor",
                "registro de sinais fisicos e emocionais",
                "trilhas curtas de autocuidado",
                "pedido opcional de ajuda com consentimento",
            ],
        },
    }
