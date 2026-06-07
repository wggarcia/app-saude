from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from api.models import (
    DispositivoAutorizado,
    DonoAuditoriaAcao,
    Empresa,
    EmpresaUsuario,
    FinanceiroEventoSaaS,
    RegistroSintoma,
)
from api.services.public_integrity import q_registro_sintoma_sintetico
from api.planos import PACOTES_SAAS, detalhes_pacote, normalizar_ciclo, normalizar_codigo_pacote


# "rede" (rede hospitalar / multiunidades) não é um segmento próprio no console:
# é consolidado em Hospital. Mapa setor-do-pacote → segmento do console (5 reais).
_SEGMENTO_CONSOLE = {"rede": "hospital"}


def _segmento_console(setor):
    base = setor or "empresa"
    return _SEGMENTO_CONSOLE.get(base, base)


# ── RBAC: papéis × ações sensíveis do console ───────────────────────────────
# Fonte única de verdade. Usada na trava do backend E para montar a visão.
ACAO_PAPEIS = {
    "cliente_editar":  {"admin", "suporte"},
    "cliente_excluir": {"admin"},                      # exclusão: só admin
    "cliente_trial":   {"admin", "suporte"},
    "cliente_logout":  {"admin", "suporte"},
    "financeiro_acao": {"admin", "financeiro"},
    "onboarding_acao": {"admin", "suporte"},
    "exportar":        {"admin", "financeiro", "suporte"},
    "operadores":      {"admin"},
}


def dono_autorizado(dono, acao):
    """Trava de backend: o papel do dono pode executar a ação?"""
    papel = getattr(dono, "papel", "admin") or "admin"
    return papel in ACAO_PAPEIS.get(acao, {"admin"})


def permissoes_dono(papel):
    """Mapa de permissões resolvido para o frontend montar a visão (RBAC)."""
    papel = papel or "admin"
    return {
        "papel": papel,
        "somente_leitura": papel == "leitura",
        "acao_cliente": papel in {"admin", "suporte"},
        "cliente_excluir": papel == "admin",
        "acao_financeiro": papel in {"admin", "financeiro"},
        "acao_onboarding": papel in {"admin", "suporte"},
        "exportar": papel in {"admin", "financeiro", "suporte"},
        "ver_financeiro": papel != "suporte",      # Suporte não vê financeiro
        "ver_operadores": papel == "admin",        # Operadores só para admin
        "gerenciar_operadores": papel == "admin",
    }


def status_contrato(empresa, agora):
    if not empresa.ativo:
        if empresa.data_expiracao and empresa.data_expiracao < agora:
            return "inadimplente"
        return "inativo"
    if not empresa.data_expiracao:
        return "ativo_sem_expiracao"
    dias = (empresa.data_expiracao - agora).days
    if dias <= 7:
        return "vence_em_7_dias"
    if dias <= 30:
        return "vence_em_30_dias"
    return "ativo"


def segmento_empresa(empresa):
    return "governo" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else "empresa"


def setor_conta(empresa):
    if empresa.tipo_conta == Empresa.TIPO_GOVERNO:
        return "governo"
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return pacote.get("setor") or "empresa"


def dashboard_url_por_setor(setor):
    if setor == "governo":
        return "/dashboard-governo/"
    if setor == "farmacia":
        return "/dashboard-farmacia/"
    if setor == "hospital":
        return "/dashboard-hospital/"
    if setor == "plano_saude":
        return "/dashboard-plano-saude/"
    return "/dashboard-empresa/"


def dashboard_return_url(empresa):
    return dashboard_url_por_setor(setor_conta(empresa))


def setor_label(setor):
    return {
        "governo": "Governo",
        "farmacia": "Farmácia",
        "hospital": "Hospital",
        "empresa": "Empresa",
        "plano_saude": "Plano de Saúde",
    }.get(setor, "Empresa")


def playbook_cliente(status_cliente, uso_usuarios, uso_dispositivos, dias_para_expirar, registros_24h, suspeitos_24h):
    if status_cliente == "inadimplente":
        return {
            "risco": "critico",
            "proxima_acao": "Cobrar e suspender acesso se nao houver regularizacao.",
            "playbook": "Financeiro deve confirmar pagamento, registrar contato e reativar somente apos comprovacao.",
        }
    if status_cliente == "inativo":
        return {
            "risco": "alto",
            "proxima_acao": "Fazer recuperacao comercial ou encerrar contrato.",
            "playbook": "Enviar proposta de reativacao com prazo curto e revisar se o modulo contratado ainda faz sentido.",
        }
    if dias_para_expirar is not None and dias_para_expirar <= 7:
        return {
            "risco": "alto",
            "proxima_acao": "Renovar contrato nos proximos 7 dias.",
            "playbook": "Acionar decisor financeiro, confirmar ciclo de renovacao e registrar proxima data de vencimento.",
        }
    if uso_usuarios >= 90 or uso_dispositivos >= 90:
        return {
            "risco": "upsell",
            "proxima_acao": "Oferecer upgrade de plano antes de travar operacao.",
            "playbook": "Mostrar uso real, risco de limite e plano recomendado com mais usuarios/dispositivos.",
        }
    if registros_24h >= 500 or suspeitos_24h >= 10:
        return {
            "risco": "operacional",
            "proxima_acao": "Acompanhar carga e qualidade dos dados.",
            "playbook": "Verificar registros suspeitos, pressao de uso e necessidade de suporte tecnico preventivo.",
        }
    return {
        "risco": "normal",
        "proxima_acao": "Manter acompanhamento de sucesso do cliente.",
        "playbook": "Revisar valor percebido, uso semanal e oportunidades de expansao sem urgencia.",
    }


def onboarding_eventos(empresa):
    eventos = FinanceiroEventoSaaS.objects.filter(
        empresa=empresa,
        tipo_evento__startswith="onboarding_",
    ).order_by("-criado_em")
    eventos_por_tipo = {}
    for evento in eventos:
        eventos_por_tipo.setdefault(evento.tipo_evento, evento)
    return eventos_por_tipo


def onboarding_cliente(empresa, usuarios_ativos, dispositivos_ativos, registros_24h):
    eventos = onboarding_eventos(empresa)
    checklist = [
        {
            "codigo": "contrato",
            "label": "Contrato/assinatura ativa",
            "ok": bool(empresa.ativo),
        },
        {
            "codigo": "pacote",
            "label": "Pacote e limites definidos",
            "ok": bool(empresa.pacote_codigo and empresa.max_usuarios and empresa.max_dispositivos),
        },
        {
            "codigo": "validade",
            "label": "Vigencia definida",
            "ok": bool(empresa.data_expiracao),
        },
        {
            "codigo": "usuarios",
            "label": "Usuarios operacionais",
            "ok": usuarios_ativos > 0,
        },
        {
            "codigo": "dispositivos",
            "label": "Dispositivo autorizado",
            "ok": dispositivos_ativos > 0,
        },
        {
            "codigo": "treinamento",
            "label": "Treinamento realizado",
            "ok": "onboarding_treinamento" in eventos,
        },
        {
            "codigo": "validacao",
            "label": "Validacao com dados reais",
            "ok": registros_24h > 0 or "onboarding_validacao" in eventos,
        },
        {
            "codigo": "go_live",
            "label": "Go-live aprovado",
            "ok": "onboarding_go_live" in eventos,
        },
    ]
    concluidos = sum(1 for item in checklist if item["ok"])
    score = round((concluidos / len(checklist)) * 100)
    etapa = "implantacao"
    if score >= 100:
        etapa = "go_live"
    elif score >= 75:
        etapa = "validacao"
    elif score >= 45:
        etapa = "treinamento"
    elif score <= 25:
        etapa = "kickoff"
    proxima = next((item["label"] for item in checklist if not item["ok"]), "Operacao acompanhada")
    return {
        "score": score,
        "etapa": etapa,
        "proxima_entrega": proxima,
        "checklist": checklist,
        "eventos": [
            {
                "tipo_evento": evento.tipo_evento,
                "status": evento.status,
                "observacao": evento.observacao or "",
                "criado_em": evento.criado_em.isoformat(),
            }
            for evento in eventos.values()
        ],
    }


def onboarding_snapshot(empresa, agora=None):
    agora = agora or timezone.now()
    usuarios_ativos = EmpresaUsuario.objects.filter(empresa=empresa, ativo=True).count()
    dispositivos_ativos = DispositivoAutorizado.objects.filter(empresa=empresa, ativo=True).count()
    registros_24h = RegistroSintoma.objects.filter(
        empresa=empresa,
        data_registro__gte=agora - timedelta(hours=24),
    ).count()
    return onboarding_cliente(empresa, usuarios_ativos, dispositivos_ativos, registros_24h)


def _resumo_vigilancia_publica(agora):
    """Resumo epidemiológico nacional do app da população para o console.

    Surfacing da camada pública (focos, casos, estados, doenças, crescimento)
    que antes não aparecia no painel administrativo. Tolerante a falhas.
    """
    vazio = {
        "disponivel": False,
        "casos_30d": 0, "casos_24h": 0, "focos": 0, "estados": 0,
        "crescimento_7d": 0.0, "suspeitos_24h": 0,
        "top_doencas": [], "top_estados": [],
    }
    try:
        empresa = Empresa.objects.filter(email="populacao@soluscrt.com").first()
        if not empresa:
            return vazio
        try:
            from api.middleware import _rls_set_empresa
            _rls_set_empresa(empresa.id)
        except Exception:
            pass

        base_30d = RegistroSintoma.objects.exclude(q_registro_sintoma_sintetico()).filter(
            empresa=empresa, data_registro__gte=agora - timedelta(days=30)
        )
        casos_30d = base_30d.count()
        casos_24h = base_30d.filter(data_registro__gte=agora - timedelta(hours=24)).count()
        suspeitos_24h = base_30d.filter(
            data_registro__gte=agora - timedelta(hours=24), suspeito=True
        ).count()

        focos = (
            base_30d.exclude(cidade__isnull=True).exclude(cidade="")
            .values("cidade", "bairro", "estado").distinct().count()
        )
        estados = (
            base_30d.exclude(estado__isnull=True).exclude(estado="")
            .values("estado").distinct().count()
        )

        # Crescimento 7d vs 7d anteriores; fallback de momentum 24h
        c7 = base_30d.filter(data_registro__gte=agora - timedelta(days=7)).count()
        c_prev = base_30d.filter(
            data_registro__gte=agora - timedelta(days=14),
            data_registro__lt=agora - timedelta(days=7),
        ).count()
        if c_prev:
            crescimento = round(((c7 - c_prev) / c_prev) * 100, 1)
        else:
            media_dia = c7 / 7.0 if c7 else 0.0
            crescimento = round(((casos_24h - media_dia) / media_dia) * 100, 1) if media_dia else 0.0
            crescimento = max(0.0, min(crescimento, 999.0))

        top_doencas = [
            {"grupo": r["grupo"], "total": r["total"]}
            for r in (
                base_30d.exclude(grupo__isnull=True).exclude(grupo="")
                .values("grupo").annotate(total=Count("id")).order_by("-total")[:5]
            )
        ]
        top_estados = [
            {"estado": r["estado"], "total": r["total"]}
            for r in (
                base_30d.exclude(estado__isnull=True).exclude(estado="")
                .values("estado").annotate(total=Count("id")).order_by("-total")[:8]
            )
        ]

        return {
            "disponivel": casos_30d > 0,
            "casos_30d": casos_30d,
            "casos_24h": casos_24h,
            "focos": focos,
            "estados": estados,
            "crescimento_7d": crescimento,
            "suspeitos_24h": suspeitos_24h,
            "top_doencas": top_doencas,
            "top_estados": top_estados,
        }
    except Exception:
        return vazio


def build_owner_resumo_payload(dono):
    empresas = Empresa.objects.all()
    ativas = empresas.filter(ativo=True)
    usuarios_ativos_qs = EmpresaUsuario.objects.filter(ativo=True)
    dispositivos_ativos_qs = DispositivoAutorizado.objects.filter(ativo=True)
    agora = timezone.now()
    registros_base = RegistroSintoma.objects.exclude(q_registro_sintoma_sintetico())
    registros_24h = registros_base.filter(data_registro__gte=agora - timedelta(hours=24))
    eventos_financeiros_qs = FinanceiroEventoSaaS.objects.select_related("empresa")
    auditoria_qs = DonoAuditoriaAcao.objects.select_related("empresa", "dono").order_by("-criado_em")

    total_empresas = empresas.count()
    total_empresas_governo = empresas.filter(tipo_conta=Empresa.TIPO_GOVERNO).count()
    ativas_lista = list(ativas.only("id", "pacote_codigo"))
    total_clientes_ativos = len(ativas_lista)
    total_usuarios_ativos = usuarios_ativos_qs.count()
    total_dispositivos_ativos = dispositivos_ativos_qs.count()
    total_registros_24h = registros_24h.count()
    total_suspeitos_24h = registros_24h.filter(suspeito=True).count()
    confianca_media = round(float(registros_base.aggregate(media=Avg("confianca"))["media"] or 0.0), 2)

    registros_por_empresa = {
        item["empresa_id"]: {
            "registros_24h": int(item["total"]),
            "suspeitos_24h": int(item["suspeitos"]),
        }
        for item in registros_24h.values("empresa_id").annotate(
            total=Count("id"),
            suspeitos=Count("id", filter=Q(suspeito=True)),
        )
    }
    usuarios_por_empresa = {
        item["empresa_id"]: int(item["total"])
        for item in usuarios_ativos_qs.values("empresa_id").annotate(total=Count("id"))
    }
    dispositivos_por_empresa = {
        item["empresa_id"]: int(item["total"])
        for item in dispositivos_ativos_qs.values("empresa_id").annotate(total=Count("id"))
    }

    faturamento_mensal = 0.0
    faturamento_anual = 0.0
    por_pacote = []

    for codigo, pacote in PACOTES_SAAS.items():
        total = sum(
            1
            for empresa in ativas_lista
            if normalizar_codigo_pacote(empresa.pacote_codigo) == codigo
        )
        por_pacote.append({
            "codigo": codigo,
            "label": pacote["label"],
            "clientes": total,
            "usuarios": pacote["usuarios"],
            "dispositivos": pacote["dispositivos"],
        })
        mensal_equivalente = (pacote["anual"] / 12) if pacote.get("ciclos") == ["anual"] else pacote["mensal"]
        faturamento_mensal += total * mensal_equivalente
        faturamento_anual += total * pacote["anual"]

    carga_estimada_mb_dia = round((total_registros_24h * 0.012) + (total_dispositivos_ativos * 0.004), 2)
    historico_uso_rows = (
        registros_base.filter(data_registro__gte=agora - timedelta(days=13))
        .annotate(day=TruncDate("data_registro"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    uso_por_dia = {str(item["day"]): int(item["total"]) for item in historico_uso_rows}
    uso_series = []
    for offset in range(14):
        day = (agora - timedelta(days=13 - offset)).date().isoformat()
        uso_series.append({"date": day, "total": uso_por_dia.get(day, 0)})

    media_7d = sum(item["total"] for item in uso_series[-7:]) / max(len(uso_series[-7:]), 1)
    media_3d = sum(item["total"] for item in uso_series[-3:]) / max(len(uso_series[-3:]), 1)
    projected_7d_mb_dia = round(max(media_7d, media_3d) * 0.014 + (total_dispositivos_ativos * 0.0045), 2)
    capacity_pressure = "baixa"
    if projected_7d_mb_dia >= 30:
        capacity_pressure = "critica"
    elif projected_7d_mb_dia >= 18:
        capacity_pressure = "alta"
    elif projected_7d_mb_dia >= 8:
        capacity_pressure = "moderada"

    receita_mensal_rows = (
        eventos_financeiros_qs.filter(criado_em__gte=agora - timedelta(days=210), status__in=["aprovado", "manual", "registrado"])
        .annotate(month=TruncMonth("criado_em"))
        .values("month")
        .annotate(valor=Sum("valor"))
        .order_by("month")
    )
    receita_series = [
        {
            "month": item["month"].date().isoformat(),
            "valor": float(item["valor"] or 0),
        }
        for item in receita_mensal_rows
    ]

    empresas_lista = list(empresas.order_by("-ativo", "nome")[:200])

    capacidade_alertas = []
    clientes_payload = []
    comparativo_clientes = []
    carteira_empresa = {"clientes": 0, "ativos": 0, "faturamento_mensal_estimado": 0.0, "registros_24h": 0}
    carteira_governo = {"clientes": 0, "ativos": 0, "faturamento_mensal_estimado": 0.0, "registros_24h": 0}

    # ── Carteira por SEGMENTO real (setor do pacote): empresa(SST)/farmacia/
    # hospital/governo/rede/plano_saude — visão que faltava no console.
    # 5 segmentos reais da SolusCRT. "rede" NÃO é um segmento próprio — é a
    # camada multiunidades (rede hospitalar / rede de farmácias) acessada de
    # dentro de Hospital/Farmácia; por isso é consolidada em Hospital aqui.
    SEGMENTO_META = {
        "empresa":     {"label": "Saúde Ocupacional (SST)", "emoji": "🦺", "ordem": 1},
        "farmacia":    {"label": "Farmácia",                "emoji": "💊", "ordem": 2},
        "hospital":    {"label": "Hospital",                "emoji": "🏥", "ordem": 3},
        "plano_saude": {"label": "Plano de Saúde",          "emoji": "🩺", "ordem": 4},
        "governo":     {"label": "Governo / Vigilância",    "emoji": "🏛️", "ordem": 5},
    }
    seg_carteiras = {
        codigo: {
            "setor": codigo,
            "label": meta["label"],
            "emoji": meta["emoji"],
            "ordem": meta["ordem"],
            "clientes": 0,
            "ativos": 0,
            "inativos": 0,
            "usuarios_ativos": 0,
            "dispositivos_ativos": 0,
            "registros_24h": 0,
            "suspeitos_24h": 0,
            "faturamento_mensal_estimado": 0.0,
            "faturamento_anual_estimado": 0.0,
            "vencendo_7_dias": 0,
            "onboarding_pendente": 0,
        }
        for codigo, meta in SEGMENTO_META.items()
    }

    for empresa in empresas_lista:
        metricas_registro = registros_por_empresa.get(empresa.id, {})
        empresa_registros_24h = metricas_registro.get("registros_24h", 0)
        empresa_suspeitos_24h = metricas_registro.get("suspeitos_24h", 0)
        usuarios_ativos_empresa = usuarios_por_empresa.get(empresa.id, 0)
        dispositivos_ativos_empresa = dispositivos_por_empresa.get(empresa.id, 0)
        uso_usuarios = round((usuarios_ativos_empresa / max(empresa.max_usuarios, 1)) * 100, 2)
        uso_dispositivos = round((dispositivos_ativos_empresa / max(empresa.max_dispositivos, 1)) * 100, 2)
        dias_para_expirar = None
        if empresa.data_expiracao:
            dias_para_expirar = max((empresa.data_expiracao - agora).days, 0)
        status_cliente = status_contrato(empresa, agora)
        segmento = segmento_empresa(empresa)
        pacote_codigo_normalizado = normalizar_codigo_pacote(empresa.pacote_codigo)
        pacote = detalhes_pacote(pacote_codigo_normalizado)
        plano_normalizado = "anual" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else normalizar_ciclo(pacote_codigo_normalizado, empresa.plano)
        faturamento_estimado_cliente = pacote["anual"] if plano_normalizado == "anual" else pacote["mensal"]
        faturamento_mensal_equivalente = pacote["anual"] / 12 if plano_normalizado == "anual" else pacote["mensal"]
        playbook = playbook_cliente(
            status_cliente,
            uso_usuarios,
            uso_dispositivos,
            dias_para_expirar,
            empresa_registros_24h,
            empresa_suspeitos_24h,
        )
        onboarding = onboarding_cliente(
            empresa,
            usuarios_ativos_empresa,
            dispositivos_ativos_empresa,
            empresa_registros_24h,
        )

        carteira = carteira_governo if segmento == "governo" else carteira_empresa
        carteira["clientes"] += 1
        carteira["ativos"] += 1 if empresa.ativo else 0
        carteira["faturamento_mensal_estimado"] += faturamento_mensal_equivalente if empresa.ativo else 0
        carteira["registros_24h"] += empresa_registros_24h

        # Carteira por segmento real (setor do pacote).
        # "rede" é a camada multiunidades — consolida em Hospital.
        setor_real = _segmento_console(pacote.get("setor"))
        seg = seg_carteiras.get(setor_real)
        if seg is not None:
            seg["clientes"] += 1
            seg["ativos"] += 1 if empresa.ativo else 0
            seg["inativos"] += 0 if empresa.ativo else 1
            seg["usuarios_ativos"] += usuarios_ativos_empresa
            seg["dispositivos_ativos"] += dispositivos_ativos_empresa
            seg["registros_24h"] += empresa_registros_24h
            seg["suspeitos_24h"] += empresa_suspeitos_24h
            if empresa.ativo:
                seg["faturamento_mensal_estimado"] += faturamento_mensal_equivalente
                seg["faturamento_anual_estimado"] += pacote["anual"]
            if dias_para_expirar is not None and dias_para_expirar <= 7:
                seg["vencendo_7_dias"] += 1
            if onboarding["score"] < 100:
                seg["onboarding_pendente"] += 1

        mensagens = []
        if uso_usuarios >= 85:
            mensagens.append(f"uso de usuários em {uso_usuarios:.1f}%")
        if uso_dispositivos >= 85:
            mensagens.append(f"uso de dispositivos em {uso_dispositivos:.1f}%")
        if empresa_suspeitos_24h >= 10:
            mensagens.append(f"{empresa_suspeitos_24h} registros suspeitos em 24h")
        if dias_para_expirar is not None and dias_para_expirar <= 7:
            mensagens.append(f"contrato expira em {dias_para_expirar} dia(s)")
        if empresa_registros_24h >= 500:
            mensagens.append(f"alto volume com {empresa_registros_24h} registros em 24h")

        if mensagens:
            capacidade_alertas.append({
                "empresa": empresa.nome,
                "email": empresa.email,
                "segmento": segmento,
                "mensagens": mensagens,
                "uso_usuarios": uso_usuarios,
                "uso_dispositivos": uso_dispositivos,
                "registros_24h": empresa_registros_24h,
                "suspeitos_24h": empresa_suspeitos_24h,
                "dias_para_expirar": dias_para_expirar,
                "status_contrato": status_cliente,
            })

        clientes_payload.append({
            "id": empresa.id,
            "nome": empresa.nome,
            "email": empresa.email,
            "tipo_conta": empresa.tipo_conta,
            "segmento": segmento,
            "ativo": empresa.ativo,
            "pacote_codigo": pacote_codigo_normalizado,
            "pacote_label": pacote["label"],
            "setor_pacote": _segmento_console(pacote.get("setor")),
            "ciclos_permitidos": pacote.get("ciclos", ["mensal", "anual"]),
            "plano": plano_normalizado,
            "max_usuarios": empresa.max_usuarios,
            "max_dispositivos": empresa.max_dispositivos,
            "data_expiracao": empresa.data_expiracao.isoformat() if empresa.data_expiracao else None,
            "usuarios_ativos": usuarios_ativos_empresa,
            "dispositivos_ativos": dispositivos_ativos_empresa,
            "registros_24h": empresa_registros_24h,
            "suspeitos_24h": empresa_suspeitos_24h,
            "uso_usuarios": uso_usuarios,
            "uso_dispositivos": uso_dispositivos,
            "status_contrato": status_cliente,
            "faturamento_estimado_cliente": faturamento_estimado_cliente,
            "onboarding": onboarding,
            **playbook,
        })
        comparativo_clientes.append({
            "nome": empresa.nome,
            "segmento": segmento,
            "registros_24h": empresa_registros_24h,
            "suspeitos_24h": empresa_suspeitos_24h,
            "faturamento_estimado_cliente": faturamento_estimado_cliente,
            "uso_combinado": round((uso_usuarios + uso_dispositivos) / 2, 2),
            "status_contrato": status_cliente,
            "onboarding_score": onboarding["score"],
            "onboarding_etapa": onboarding["etapa"],
        })

    capacidade_alertas.sort(key=lambda item: (len(item["mensagens"]), item["registros_24h"], item["uso_dispositivos"]), reverse=True)
    eventos_financeiros = eventos_financeiros_qs.order_by("-criado_em")[:25]
    auditoria_recente = auditoria_qs[:25]
    vencendo_7 = sum(1 for item in clientes_payload if item["status_contrato"] == "vence_em_7_dias")
    vencendo_30 = sum(1 for item in clientes_payload if item["status_contrato"] == "vence_em_30_dias")
    inadimplentes = sum(1 for item in clientes_payload if item["status_contrato"] == "inadimplente")
    inativos = sum(1 for item in clientes_payload if item["status_contrato"] == "inativo")
    cobranca_ativa = vencendo_7 + inadimplentes
    onboarding_pendente = sum(1 for item in clientes_payload if item["onboarding"]["score"] < 100)
    go_live_pendentes = sum(1 for item in clientes_payload if item["onboarding"]["etapa"] != "go_live")
    comparativo_uso = sorted(comparativo_clientes, key=lambda item: (item["uso_combinado"], item["registros_24h"]), reverse=True)[:8]
    comparativo_receita = sorted(comparativo_clientes, key=lambda item: item["faturamento_estimado_cliente"], reverse=True)[:8]

    recomendacao_infra = "Capacidade confortável para o volume atual."
    if capacity_pressure == "moderada":
        recomendacao_infra = "Planeje expansão preventiva de banco, cache e observabilidade antes da próxima onda."
    elif capacity_pressure == "alta":
        recomendacao_infra = "Preparar expansão de banda, workers e banco nas próximas 72h para evitar degradação."
    elif capacity_pressure == "critica":
        recomendacao_infra = "Prioridade máxima para escalar infraestrutura, filas e réplica de leitura imediatamente."

    carteiras_por_segmento = sorted(
        (
            {
                **seg,
                "faturamento_mensal_estimado": round(seg["faturamento_mensal_estimado"], 2),
                "faturamento_anual_estimado": round(seg["faturamento_anual_estimado"], 2),
            }
            for seg in seg_carteiras.values()
        ),
        key=lambda s: s["ordem"],
    )

    # ── Vigilância Pública (app da população) — camada epidemiológica ──────
    vigilancia_publica = _resumo_vigilancia_publica(agora)

    return {
        "owner": dono.nome,
        "seu_papel": getattr(dono, "papel", "admin"),
        "permissoes": permissoes_dono(getattr(dono, "papel", "admin")),
        "summary": {
            "clientes_total": total_empresas,
            "clientes_ativos": total_clientes_ativos,
            "clientes_governo": total_empresas_governo,
            "usuarios_ativos": total_usuarios_ativos,
            "dispositivos_ativos": total_dispositivos_ativos,
            "registros_24h": total_registros_24h,
            "suspeitos_24h": total_suspeitos_24h,
            "faturamento_mensal_estimado": round(faturamento_mensal, 2),
            "faturamento_anual_equivalente": round(faturamento_anual, 2),
            "carga_estimada_mb_dia": carga_estimada_mb_dia,
            "projecao_carga_mb_dia": projected_7d_mb_dia,
            "nivel_pressao_capacidade": capacity_pressure,
            "confianca_media": confianca_media,
            "vencendo_7_dias": vencendo_7,
            "vencendo_30_dias": vencendo_30,
            "inadimplentes": inadimplentes,
            "inativos": inativos,
            "cobranca_ativa": cobranca_ativa,
            "onboarding_pendente": onboarding_pendente,
            "go_live_pendentes": go_live_pendentes,
        },
        "pacotes": por_pacote,
        "alertas_capacidade": capacidade_alertas[:12],
        "carteiras": {
            "empresa": {
                **carteira_empresa,
                "faturamento_mensal_estimado": round(carteira_empresa["faturamento_mensal_estimado"], 2),
            },
            "governo": {
                **carteira_governo,
                "faturamento_mensal_estimado": round(carteira_governo["faturamento_mensal_estimado"], 2),
            },
        },
        "carteiras_por_segmento": carteiras_por_segmento,
        "vigilancia_publica": vigilancia_publica,
        "historico": {
            "receita": receita_series,
            "uso": uso_series,
        },
        "comparativos": {
            "top_uso": comparativo_uso,
            "top_receita": comparativo_receita,
        },
        "operacoes": {
            "recomendacao_infra": recomendacao_infra,
        },
        "financeiro": [
            {
                "empresa": evento.empresa.nome,
                "tipo_evento": evento.tipo_evento,
                "pacote_codigo": evento.pacote_codigo,
                "ciclo": evento.ciclo,
                "valor": float(evento.valor),
                "status": evento.status,
                "observacao": evento.observacao,
                "criado_em": evento.criado_em.isoformat(),
            }
            for evento in eventos_financeiros
        ],
        "auditoria": [
            {
                "dono": item.dono.nome,
                "empresa": item.empresa.nome if item.empresa else "Plataforma",
                "acao": item.acao,
                "detalhes": item.detalhes,
                "criado_em": item.criado_em.isoformat(),
            }
            for item in auditoria_recente
        ],
        "clientes": clientes_payload,
    }


# ════════════════════════════════════════════════════════════════════════════
#  FINANCEIRO REAL — MRR / Churn / LTV (recorrência + pagamentos Asaas)
# ════════════════════════════════════════════════════════════════════════════
_EVENTOS_RECEITA = {"pagamento_aprovado", "renovacao_manual", "upgrade", "cobranca_manual", "reativacao_manual"}
_EVENTOS_CHURN = {"cancelamento_operacional", "inadimplencia", "downgrade"}


def build_owner_financeiro_real(dono=None):
    """
    Inteligência financeira real do SaaS:
      • MRR contratado (recorrência das contas ativas)
      • MRR realizado (pagamentos aprovados/Asaas nos últimos 30 dias)
      • ARPA, LTV estimado, churn (logo e receita)
      • Movimentos de MRR (novo/expansão/contração/perdido)
      • Receita realizada mês a mês (6 meses) e inadimplência
    """
    agora = timezone.now()
    ref_30 = agora - timedelta(days=30)
    ref_60 = agora - timedelta(days=60)

    ativas = list(Empresa.objects.filter(ativo=True).only("id", "pacote_codigo", "plano", "tipo_conta"))

    mrr_contratado = 0.0
    arr_contratado = 0.0
    mrr_por_segmento = {}
    for empresa in ativas:
        codigo = normalizar_codigo_pacote(empresa.pacote_codigo)
        pacote = detalhes_pacote(codigo)
        plano = "anual" if empresa.tipo_conta == Empresa.TIPO_GOVERNO else normalizar_ciclo(codigo, empresa.plano)
        mrr_eq = (pacote["anual"] / 12) if plano == "anual" else pacote["mensal"]
        mrr_contratado += mrr_eq
        arr_contratado += pacote["anual"] if plano == "anual" else pacote["mensal"] * 12
        setor = _segmento_console(pacote.get("setor"))
        mrr_por_segmento[setor] = mrr_por_segmento.get(setor, 0.0) + mrr_eq

    clientes_ativos = len(ativas)
    arpa = (mrr_contratado / clientes_ativos) if clientes_ativos else 0.0

    eventos = FinanceiroEventoSaaS.objects.filter(criado_em__gte=ref_60)
    receita_30 = float(
        eventos.filter(criado_em__gte=ref_30, tipo_evento__in=_EVENTOS_RECEITA, valor__gt=0)
        .aggregate(s=Sum("valor"))["s"] or 0
    )
    receita_30_anterior = float(
        eventos.filter(criado_em__gte=ref_60, criado_em__lt=ref_30, tipo_evento__in=_EVENTOS_RECEITA, valor__gt=0)
        .aggregate(s=Sum("valor"))["s"] or 0
    )

    # Movimentos de MRR no período (contagem de eventos)
    novos = eventos.filter(criado_em__gte=ref_30, tipo_evento="pagamento_aprovado").count()
    expansao = eventos.filter(criado_em__gte=ref_30, tipo_evento="upgrade").count()
    contracao = eventos.filter(criado_em__gte=ref_30, tipo_evento="downgrade").count()
    perdidos = eventos.filter(criado_em__gte=ref_30, tipo_evento__in=["cancelamento_operacional", "inadimplencia"]).count()

    # Churn logo (clientes perdidos / base ativa+perdidos)
    base_churn = max(clientes_ativos + perdidos, 1)
    churn_logo = round((perdidos / base_churn) * 100, 2)
    # LTV ≈ ARPA / churn mensal (com piso de churn para não explodir)
    churn_frac = max(churn_logo / 100, 0.005)
    ltv = round(arpa / churn_frac, 2) if arpa else 0.0

    # Receita realizada mês a mês (6 meses)
    receita_mensal_rows = (
        FinanceiroEventoSaaS.objects
        .filter(criado_em__gte=agora - timedelta(days=190), tipo_evento__in=_EVENTOS_RECEITA, valor__gt=0)
        .annotate(month=TruncMonth("criado_em"))
        .values("month").annotate(valor=Sum("valor")).order_by("month")
    )
    receita_series = [
        {"month": r["month"].date().isoformat(), "valor": float(r["valor"] or 0)}
        for r in receita_mensal_rows
    ]

    inadimplencia_valor = float(
        eventos.filter(criado_em__gte=ref_30, tipo_evento="inadimplencia").aggregate(s=Sum("valor"))["s"] or 0
    )

    crescimento_receita = 0.0
    if receita_30_anterior > 0:
        crescimento_receita = round(((receita_30 - receita_30_anterior) / receita_30_anterior) * 100, 1)

    SEG_LABEL = {
        "empresa": "SST", "farmacia": "Farmácia", "hospital": "Hospital",
        "plano_saude": "Plano de Saúde", "governo": "Governo",
    }
    mrr_segmentos = sorted(
        ({"setor": k, "label": SEG_LABEL.get(k, k), "mrr": round(v, 2)} for k, v in mrr_por_segmento.items()),
        key=lambda x: x["mrr"], reverse=True,
    )

    return {
        "mrr_contratado": round(mrr_contratado, 2),
        "arr_contratado": round(arr_contratado, 2),
        "mrr_realizado_30d": round(receita_30, 2),
        "gap_realizado_vs_contratado": round(mrr_contratado - receita_30, 2),
        "arpa": round(arpa, 2),
        "ltv_estimado": ltv,
        "churn_logo_30d": churn_logo,
        "crescimento_receita_30d": crescimento_receita,
        "inadimplencia_30d": round(inadimplencia_valor, 2),
        "clientes_ativos": clientes_ativos,
        "movimentos": {
            "novos": novos, "expansao": expansao,
            "contracao": contracao, "perdidos": perdidos,
        },
        "mrr_por_segmento": mrr_segmentos,
        "receita_mensal": receita_series,
        "fonte": "Recorrência das contas ativas + eventos de pagamento (Asaas).",
    }


# ════════════════════════════════════════════════════════════════════════════
#  SAÚDE DO SISTEMA — infraestrutura e integrações em tempo real
# ════════════════════════════════════════════════════════════════════════════
def build_owner_saude_sistema(dono=None):
    """Diagnóstico de saúde operacional: banco, cache, integrações e frescor."""
    import os
    import time as _time
    from django.db import connection
    from django.core.cache import cache as _cache

    agora = timezone.now()
    componentes = []

    def _add(nome, ok, detalhe, latencia_ms=None, nivel=None):
        componentes.append({
            "componente": nome,
            "status": "ok" if ok else "falha",
            "nivel": nivel or ("ok" if ok else "critico"),
            "detalhe": detalhe,
            "latencia_ms": latencia_ms,
        })

    # Banco de dados
    try:
        t0 = _time.monotonic()
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        lat = round((_time.monotonic() - t0) * 1000, 1)
        nivel = "ok" if lat < 80 else "atencao" if lat < 250 else "critico"
        _add("Banco de dados", True, f"{connection.vendor} respondeu em {lat} ms", lat, nivel)
    except Exception as exc:
        _add("Banco de dados", False, f"erro: {type(exc).__name__}")

    # Cache
    try:
        t0 = _time.monotonic()
        _cache.set("_saude_ping", "1", 10)
        ok_cache = _cache.get("_saude_ping") == "1"
        lat = round((_time.monotonic() - t0) * 1000, 1)
        _add("Cache", ok_cache, "operacional" if ok_cache else "sem retorno", lat,
             "ok" if ok_cache else "atencao")
    except Exception as exc:
        _add("Cache", False, f"erro: {type(exc).__name__}", nivel="atencao")

    # Integração de pagamento (Asaas)
    asaas_key = bool(os.environ.get("ASAAS_API_KEY") or os.environ.get("ASAAS_TOKEN"))
    ultimo_pgto = (
        FinanceiroEventoSaaS.objects.filter(tipo_evento="pagamento_aprovado")
        .order_by("-criado_em").values_list("criado_em", flat=True).first()
    )
    if asaas_key:
        det = "chave configurada"
        if ultimo_pgto:
            dias = (agora - ultimo_pgto).days
            det += f"; último pagamento há {dias} dia(s)"
        _add("Pagamentos (Asaas)", True, det, nivel="ok")
    else:
        _add("Pagamentos (Asaas)", False, "ASAAS_API_KEY ausente — cobranças via Asaas indisponíveis", nivel="atencao")

    # Geocodificação (vigilância)
    try:
        from api.utils_geo import _fallback_local
        g = _fallback_local(-22.9711, -43.1835)
        ok_geo = g.get("cidade") == "Rio de Janeiro"
        _add("Geocodificação", ok_geo, f"referência local ({g.get('cidade')})", nivel="ok" if ok_geo else "atencao")
    except Exception as exc:
        _add("Geocodificação", False, f"erro: {type(exc).__name__}", nivel="atencao")

    # Frescor de dados públicos (app população)
    try:
        emp_pub = Empresa.objects.filter(email="populacao@soluscrt.com").first()
        if emp_pub:
            try:
                from api.middleware import _rls_set_empresa
                _rls_set_empresa(emp_pub.id)
            except Exception:
                pass
            ultimo = (
                RegistroSintoma.objects.filter(empresa=emp_pub)
                .order_by("-data_registro").values_list("data_registro", flat=True).first()
            )
            if ultimo:
                horas = round((agora - ultimo).total_seconds() / 3600, 1)
                nivel = "ok" if horas < 48 else "atencao" if horas < 168 else "critico"
                _add("Ingestão app população", True, f"último sinal há {horas} h", nivel=nivel)
            else:
                _add("Ingestão app população", False, "sem registros", nivel="atencao")
        else:
            _add("Ingestão app população", False, "empresa pública não provisionada", nivel="atencao")
    except Exception as exc:
        _add("Ingestão app população", False, f"erro: {type(exc).__name__}", nivel="atencao")

    total = len(componentes)
    ok_count = sum(1 for c in componentes if c["status"] == "ok")
    criticos = sum(1 for c in componentes if c["nivel"] == "critico")
    atencao = sum(1 for c in componentes if c["nivel"] == "atencao")
    if criticos:
        saude_geral = "critico"
    elif atencao:
        saude_geral = "atencao"
    else:
        saude_geral = "ok"

    return {
        "saude_geral": saude_geral,
        "componentes_ok": ok_count,
        "componentes_total": total,
        "criticos": criticos,
        "atencao": atencao,
        "componentes": componentes,
        "verificado_em": agora.isoformat(),
    }


# ════════════════════════════════════════════════════════════════════════════
#  APP FUNCIONÁRIO — adoção e engajamento do app do trabalhador
# ════════════════════════════════════════════════════════════════════════════
def build_owner_app_funcionario(dono=None):
    """
    Métricas de adoção do app do trabalhador (App Funcionário):
      • trabalhadores cadastrados, com credencial de app e com app instalado
        (push token), funil de adesão e instalação
      • engajamento: check-ins de bem-estar e leitura de notificações (30d)
      • novas ativações (30d) e ranking de empresas por adesão
    """
    from api.models import (
        FuncionarioSST, CredencialAppFuncionario,
        CheckinBemEstar, NotificacaoFuncionario,
    )

    agora = timezone.now()
    ref_30 = agora - timedelta(days=30)

    trabalhadores = FuncionarioSST.objects.filter(ativo=True)
    total_trab = trabalhadores.count()

    creds = CredencialAppFuncionario.objects.filter(ativo=True)
    com_credencial = creds.count()
    com_push = creds.exclude(fcm_token="").count()
    novas_30d = creds.filter(criado_em__gte=ref_30).count()

    taxa_adesao = round((com_credencial / total_trab) * 100, 1) if total_trab else 0.0
    taxa_instalacao = round((com_push / com_credencial) * 100, 1) if com_credencial else 0.0

    # Engajamento (30 dias)
    checkins_30d = CheckinBemEstar.objects.filter(criado_em__gte=ref_30)
    checkins_total = checkins_30d.count()
    func_engajados = checkins_30d.values("funcionario_id").distinct().count()
    taxa_engajamento = round((func_engajados / com_credencial) * 100, 1) if com_credencial else 0.0

    notif = NotificacaoFuncionario.objects.filter(criado_em__gte=ref_30)
    notif_enviadas = notif.count()
    notif_lidas = notif.filter(lida=True).count()
    taxa_leitura = round((notif_lidas / notif_enviadas) * 100, 1) if notif_enviadas else 0.0

    # Ranking de empresas por adesão (top 8)
    trab_por_emp = {
        r["empresa_id"]: r["t"]
        for r in trabalhadores.values("empresa_id").annotate(t=Count("id"))
    }
    cred_por_emp = {}
    push_por_emp = {}
    for r in creds.values("funcionario__empresa_id").annotate(
        t=Count("id"), p=Count("id", filter=~Q(fcm_token=""))
    ):
        eid = r["funcionario__empresa_id"]
        cred_por_emp[eid] = r["t"]
        push_por_emp[eid] = r["p"]

    nomes = {e.id: e.nome for e in Empresa.objects.filter(id__in=list(trab_por_emp.keys()))}
    ranking = []
    for eid, trab in trab_por_emp.items():
        c = cred_por_emp.get(eid, 0)
        ranking.append({
            "empresa": nomes.get(eid, f"#{eid}"),
            "trabalhadores": trab,
            "com_credencial": c,
            "com_push": push_por_emp.get(eid, 0),
            "adesao": round((c / trab) * 100, 1) if trab else 0.0,
        })
    ranking.sort(key=lambda x: (x["adesao"], x["com_credencial"]), reverse=True)

    return {
        "total_trabalhadores": total_trab,
        "com_credencial": com_credencial,
        "com_push": com_push,
        "sem_credencial": max(total_trab - com_credencial, 0),
        "taxa_adesao": taxa_adesao,
        "taxa_instalacao": taxa_instalacao,
        "novas_ativacoes_30d": novas_30d,
        "engajamento": {
            "funcionarios_engajados_30d": func_engajados,
            "checkins_30d": checkins_total,
            "taxa_engajamento": taxa_engajamento,
            "notif_enviadas_30d": notif_enviadas,
            "notif_lidas_30d": notif_lidas,
            "taxa_leitura": taxa_leitura,
        },
        "ranking_empresas": ranking[:8],
    }


# ════════════════════════════════════════════════════════════════════════════
#  OPERADORES / RBAC — equipe com acesso ao console
# ════════════════════════════════════════════════════════════════════════════
PAPEL_DESCRICAO = {
    "admin": "Acesso total + gestão de operadores",
    "financeiro": "Cobrança, renovação e financeiro",
    "suporte": "Operação de clientes e onboarding",
    "leitura": "Somente visualização",
}


def build_owner_operadores_payload(dono):
    """Lista os operadores do console (equipe com acesso), com papel e sessão."""
    from api.models import DonoSaaS
    agora = timezone.now()
    operadores = []
    for op in DonoSaaS.objects.all().order_by("-ativo", "nome"):
        online = bool(op.sessao_ativa_chave)
        ultima = op.sessao_ativa_em
        operadores.append({
            "id": op.id,
            "nome": op.nome,
            "email": op.email,
            "papel": op.papel,
            "papel_label": dict(DonoSaaS.PAPEIS).get(op.papel, op.papel),
            "papel_descricao": PAPEL_DESCRICAO.get(op.papel, ""),
            "ativo": op.ativo,
            "online": online,
            "ultima_sessao": ultima.isoformat() if ultima else None,
            "criado_em": op.criado_em.isoformat() if op.criado_em else None,
            "eh_voce": op.id == dono.id,
        })
    total = len(operadores)
    ativos = sum(1 for o in operadores if o["ativo"])
    return {
        "operadores": operadores,
        "total": total,
        "ativos": ativos,
        "online": sum(1 for o in operadores if o["online"]),
        "papeis": [{"valor": v, "label": l, "descricao": PAPEL_DESCRICAO.get(v, "")} for v, l in DonoSaaS.PAPEIS],
        "seu_papel": dono.papel,
        "pode_gerenciar": dono.papel == DonoSaaS.PAPEL_ADMIN,
    }
