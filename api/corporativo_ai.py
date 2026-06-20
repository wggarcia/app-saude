from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import (
    CheckinDiarioCorporativo,
    CheckinSemanalCorporativo,
    EmpresaCargoCorporativo,
    EvidenciaCompetenciaCorporativa,
    FuncaoCriticaCorporativa,
    PedidoApoioCorporativo,
    TrilhaCompetenciaCorporativa,
    ValidacaoCompetenciaCorporativa,
)
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


def _competence_snapshot(empresa):
    trilhas = TrilhaCompetenciaCorporativa.objects.filter(empresa=empresa, ativo=True)
    evidencias = EvidenciaCompetenciaCorporativa.objects.filter(empresa=empresa)
    funcoes = FuncaoCriticaCorporativa.objects.filter(empresa=empresa, ativo=True)
    cargos = EmpresaCargoCorporativo.objects.filter(empresa=empresa, ativo=True)
    validacoes = ValidacaoCompetenciaCorporativa.objects.filter(empresa=empresa)

    trilhas_count = trilhas.count()
    cargos_count = cargos.count()
    funcoes_count = funcoes.count()
    evidencias_count = evidencias.count()
    pendentes = validacoes.filter(resultado=ValidacaoCompetenciaCorporativa.RESULTADO_PENDENTE).count()
    aprovadas = validacoes.filter(resultado=ValidacaoCompetenciaCorporativa.RESULTADO_APROVADA).count()

    readiness = 0
    if evidencias_count:
        readiness = round((aprovadas / max(1, evidencias_count)) * 100)

    return {
        "tracks_count": trilhas_count,
        "roles_count": cargos_count,
        "critical_functions_count": funcoes_count,
        "evidence_count": evidencias_count,
        "pending_validations": pendentes,
        "approved_validations": aprovadas,
        "readiness_score": readiness,
    }


def _aggregate_diario(qs):
    return qs.aggregate(
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


def _aggregate_semanal(qs):
    return qs.aggregate(
        weekly_respondents=Count("id"),
        avg_carga_emocional=Avg("carga_emocional"),
        avg_seguranca_psicologica=Avg("seguranca_psicologica"),
        avg_apoio_percebido=Avg("apoio_percebido"),
        avg_pressao_trabalho=Avg("pressao_trabalho"),
        avg_bem_estar_geral=Avg("bem_estar_geral"),
        avg_risco_burnout=Avg("risco_burnout"),
    )


def _delta_sign(current, previous):
    diff = current - previous
    if abs(diff) < 2:
        return 0
    return diff


def build_empresa_corporativo_payload(empresa):
    pacote = detalhes_pacote(empresa.pacote_codigo)
    company_label = empresa.nome or "Empresa"
    now = timezone.now()
    daily_cutoff = now.date() - timedelta(days=30)
    prev_daily_cutoff = now.date() - timedelta(days=60)
    weekly_cutoff = now.date() - timedelta(days=84)
    prev_weekly_cutoff = now.date() - timedelta(days=168)

    base_diario = CheckinDiarioCorporativo.objects.filter(empresa=empresa, data_referencia__gte=daily_cutoff)
    base_semanal = CheckinSemanalCorporativo.objects.filter(empresa=empresa, semana_referencia__gte=weekly_cutoff)
    prev_diario = CheckinDiarioCorporativo.objects.filter(
        empresa=empresa,
        data_referencia__gte=prev_daily_cutoff,
        data_referencia__lt=daily_cutoff,
    )
    prev_semanal = CheckinSemanalCorporativo.objects.filter(
        empresa=empresa,
        semana_referencia__gte=prev_weekly_cutoff,
        semana_referencia__lt=weekly_cutoff,
    )
    support_count = PedidoApoioCorporativo.objects.filter(
        empresa=empresa,
        status__in=[PedidoApoioCorporativo.STATUS_NOVO, PedidoApoioCorporativo.STATUS_EM_ANALISE],
    ).count()

    diario = _aggregate_diario(base_diario)
    semanal = _aggregate_semanal(base_semanal)
    prev_diario_agg = _aggregate_diario(prev_diario)
    prev_semanal_agg = _aggregate_semanal(prev_semanal)

    mood_score = _mood_score(diario)
    stress_score = _stress_score(diario, semanal)
    physical_score = _physical_score(diario)
    top_signal = _top_signal(diario)
    top_units = _top_units(base_diario)
    recommendations = _build_recommendations(company_label, mood_score, stress_score, physical_score, support_count, top_signal)
    competence = _competence_snapshot(empresa)

    prev_mood = _mood_score(prev_diario_agg)
    prev_stress = _stress_score(prev_diario_agg, prev_semanal_agg)
    prev_physical = _physical_score(prev_diario_agg)

    respondents = diario.get("respondents", 0)
    weekly_respondents = semanal.get("weekly_respondents", 0)
    privacy_ready = respondents >= MIN_GROUP_SIZE or weekly_respondents >= MIN_GROUP_SIZE
    has_prev = (prev_diario_agg.get("respondents") or 0) >= MIN_GROUP_SIZE

    return {
        "product": {
            "name": "SolusCRT Corporativo",
            "subtitle": "Saude ocupacional, escalas, cultura, lideranca e continuidade operacional",
            "company": company_label,
            "package_label": pacote["label"],
        },
        "ecosystem": {
            "name": "Ecossistema Institucional SolusCRT",
            "segments": ["Healthtech empresarial", "Farmacia", "Hospital", "Operacao territorial"],
            "promise": (
                "Uma unica camada institucional para autenticar operacoes setoriais e abrir "
                "o ambiente adequado apos o login."
            ),
        },
        "access_code": empresa.codigo_acesso_corporativo,
        "hero": {
            "title": "Operating System de Saude, Escala e Desenvolvimento",
            "eyebrow": "Ambiente empresa · Control room premium",
            "summary": (
                f"{company_label} opera um ambiente proprio para saude ocupacional, risco psicossocial, "
                "fadiga, desenvolvimento em escala, comunicacao multicultural e continuidade da operacao."
            ),
            "positioning": (
                "Este ambiente nao replica o epidemiologico. Ele funciona como um sistema institucional "
                "para RH, SESMT, operacoes e liderancas coordenarem cuidado, desempenho e confiabilidade."
            ),
            "value_points": [
                "antecipar absenteismo, fadiga e risco psicossocial antes da ruptura operacional",
                "organizar cultura, idioma, mentoria e desenvolvimento em operacoes multiunidade",
                "transformar sinais anonimos em programas acionaveis para lideranca e RH",
            ],
        },
        "executive_cards": [
            {
                "label": "Bem-estar geral",
                "value": f"{mood_score}/100",
                "detail": f"Score institucional de energia e confiabilidade; {_risk_summary(mood_score)}.",
                "delta": _delta_sign(mood_score, prev_mood) if has_prev else None,
                "delta_label": "vs. periodo anterior",
            },
            {
                "label": "Risco psicossocial",
                "value": _risk_band(stress_score).upper(),
                "detail": f"Indice {stress_score}/100 com foco em estresse, ansiedade, carga emocional e burnout.",
                "delta": _delta_sign(stress_score, prev_stress) if has_prev else None,
                "delta_inverted": True,
                "delta_label": "vs. periodo anterior",
            },
            {
                "label": "Risco ocupacional",
                "value": _risk_band(physical_score).upper(),
                "detail": f"Indice {physical_score}/100 para fadiga, dor, sono ruim e carga fisica recorrente.",
                "delta": _delta_sign(physical_score, prev_physical) if has_prev else None,
                "delta_inverted": True,
                "delta_label": "vs. periodo anterior",
            },
            {
                "label": "Pedidos de apoio",
                "value": str(support_count),
                "detail": "Fila de acolhimento institucional e cuidado ativo.",
                "delta": None,
                "delta_label": None,
            },
            {
                "label": "Readiness tecnica",
                "value": f"{competence['readiness_score']}/100",
                "detail": "Sinal inicial de prontidao de competencia, evidencias e validacoes da operacao.",
                "delta": None,
                "delta_label": None,
            },
        ],
        "summary": {
            "respondents": respondents,
            "weekly_respondents": weekly_respondents,
            "privacy_ready": privacy_ready,
            "top_signal": top_signal,
            "headline": recommendations["headline"],
        },
        "surfaces": [
            {
                "title": "Plataforma healthtech institucional",
                "summary": "Painel premium para RH, SESMT, diretoria e liderancas acompanharem risco, programas e continuidade.",
                "owner": "empresa",
            },
            {
                "title": "App mobile do colaborador",
                "summary": "Produto dedicado para celular com check-ins, apoio, microlearning, mentoria e jornada on/off.",
                "owner": "colaborador",
            },
            {
                "title": "Camada de IA corporativa",
                "summary": "Motor que prioriza unidades, programas, liderancas e riscos a partir de sinais anonimos e contexto operacional.",
                "owner": "analytics",
            },
        ],
        "module_nav": [
            "Saude Ocupacional",
            "Fadiga e Burnout",
            "Competencia Tecnica",
            "Escalas 14x14 / 28x28",
            "Cultura e Comunicacao",
            "Mentoria e Lideranca",
            "Governanca e Privacidade",
        ],
        "modules": [
            {
                "title": "Saude Ocupacional",
                "band": _risk_band(physical_score),
                "audience": "SESMT, medicina do trabalho e operacao",
                "summary": "Organiza leitura de dor, fadiga, sono, carga fisica e retorno assistido sem transformar o produto em prontuario.",
                "metrics": [
                    f"risco ocupacional {physical_score}/100",
                    f"fadiga media {_safe_avg(diario, 'avg_fadiga')}/5",
                    f"dor fisica {_safe_avg(diario, 'avg_dor_fisica')}/5",
                ],
                "actions": [
                    "mapear frentes com sono ruim, dor e fadiga recorrente",
                    "ligar ergonomia, pausa e retorno assistido ao plano semanal",
                ],
            },
            {
                "title": "Fadiga e Burnout",
                "band": _risk_band(stress_score),
                "audience": "RH, lideranca e saude ocupacional",
                "summary": "Antecipar queda de energia, sobrecarga e perda de presenca antes que o problema vire afastamento ou erro operacional.",
                "metrics": [
                    f"risco psicossocial {stress_score}/100",
                    f"energia media {_safe_avg(diario, 'avg_energia')}/5",
                    f"burnout {_safe_avg(semanal, 'avg_risco_burnout')}/5",
                ],
                "actions": [
                    "priorizar grupos com estresse alto e energia em queda",
                    "acionar campanha de recuperacao emocional e ajuste de ritmo",
                ],
            },
            {
                "title": "Competencia Tecnica",
                "band": "moderado" if competence["pending_validations"] else "baixo",
                "audience": "operacao, supervisao tecnica e treinamento",
                "summary": "Liga trilhas por cargo, funcoes criticas, evidencias de campo e validacao por supervisor para medir prontidao real.",
                "metrics": [
                    f"trilhas {competence['tracks_count']}",
                    f"funcoes criticas {competence['critical_functions_count']}",
                    f"evidencias {competence['evidence_count']}",
                ],
                "actions": [
                    "mapear lacunas por cargo, setor e equipamento critico",
                    "priorizar validacoes pendentes antes de liberar autonomia operacional",
                ],
            },
            {
                "title": "Escalas 14x14 / 28x28",
                "band": "moderado" if respondents else "baixo",
                "audience": "operacoes, RH e desenvolvimento",
                "summary": "Gerenciar aprendizado, energia e continuidade em equipes embarcadas ou de longa permanencia sem sobrecarregar o colaborador.",
                "metrics": [
                    f"respondentes diarios {respondents}",
                    f"respondentes semanais {weekly_respondents}",
                    "PDI on/off planejado por ciclo",
                ],
                "actions": [
                    "separar metas de performance embarcada e folga",
                    "medir risco por turno, cobertura e janela de descanso",
                ],
            },
            {
                "title": "Cultura e Comunicacao",
                "band": "baixo",
                "audience": "liderancas multiculturais e operacao global",
                "summary": "Reduzir falha de entendimento em equipes com diferentes idiomas, estilos de feedback e rotinas tecnicas.",
                "metrics": [
                    "microlearning tecnico offline",
                    "glossario operacional multilingue",
                    "playbooks de CQ por lideranca",
                ],
                "actions": [
                    "estruturar trilhas de idioma tecnico por frente operacional",
                    "preparar kits de comunicacao curta para liderancas multiculturais",
                ],
            },
            {
                "title": "Mentoria e Lideranca",
                "band": "moderado" if support_count else "baixo",
                "audience": "desenvolvimento humano e gestores de unidade",
                "summary": "Criar suporte humano continuo para quem opera longe, em escala ou em ambiente confinado, com mentoria, feedback e rituais simples.",
                "metrics": [
                    f"pedidos de apoio {support_count}",
                    "matching remoto entre unidades",
                    "feedback de fim de ciclo",
                ],
                "actions": [
                    "criar matching por senioridade, idioma e especialidade",
                    "medir quais liderancas estao sem suporte ou com pressao crescente",
                ],
            },
            {
                "title": "Governanca e Privacidade",
                "band": "baixo" if privacy_ready else "moderado",
                "audience": "juridico, compliance, RH e diretoria",
                "summary": "Separar cuidado institucional de vigilancia, com leitura anonima, grupos minimos e trilha de auditoria para o uso de IA.",
                "metrics": [
                    f"grupo minimo {MIN_GROUP_SIZE}",
                    "sem dado individual no painel",
                    "auditoria institucional ativa",
                ],
                "actions": [
                    "proteger recortes pequenos e exportacoes sensiveis",
                    "manter consentimento explicito para qualquer apoio nominal",
                ],
            },
        ],
        "questions": [
            "Onde a operacao esta perdendo energia antes do afastamento aparecer?",
            "Quais escalas, unidades ou liderancas precisam de suporte nesta semana?",
            "Qual programa entra primeiro: fadiga, ergonomia, apoio psicossocial ou desenvolvimento?",
            "Quais competencias criticas ainda nao estao comprovadas em campo?",
            "O que fica no painel executivo e o que precisa migrar para o app mobile do colaborador?",
        ],
        "competence": competence,
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
                "title": "Programa de cultura, idioma e escala",
                "owner": "people + operacao",
                "items": [
                    "microlearning tecnico multilingue por operacao",
                    "PDI on/off para ciclos 14x14 e 28x28",
                    "ritual de handoff e mentoria remota entre unidades",
                ],
            },
            {
                "title": "Programa de competencia critica",
                "owner": "supervisao tecnica + treinamento",
                "items": [
                    "trilhas por cargo, setor e equipamento critico",
                    "evidencia pratica validada por supervisor",
                    "readiness tecnico para assumir autonomia operacional",
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
                "auditoria institucional em acessos, IA e exportacoes",
            ],
        },
        "mobile_product": {
            "title": "Produto mobile do colaborador",
            "summary": "O colaborador nao usa a plataforma healthtech institucional. Ele participa por um app mobile proprio, com experiencia discreta e orientada a uso cotidiano.",
            "note": "A empresa coordena programas pelo painel; o funcionario usa o mobile para check-ins, apoio, microlearning, mentoria e trilhas on/off.",
            "capabilities": [
                "check-in diario e semanal sem exposicao ao gestor",
                "pedido opcional de apoio com consentimento",
                "trilhas de competencia por funcao e equipamento",
                "microlearning tecnico, idioma e cultura",
                "mentoria, comunidades e handoff educativo",
            ],
        },
    }
