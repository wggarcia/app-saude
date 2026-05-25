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
from api.planos import PACOTES_SAAS, detalhes_pacote, normalizar_ciclo, normalizar_codigo_pacote


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


def build_owner_resumo_payload(dono):
    empresas = Empresa.objects.all()
    ativas = empresas.filter(ativo=True)
    usuarios_ativos_qs = EmpresaUsuario.objects.filter(ativo=True)
    dispositivos_ativos_qs = DispositivoAutorizado.objects.filter(ativo=True)
    agora = timezone.now()
    registros_24h = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(hours=24))
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
    confianca_media = round(float(RegistroSintoma.objects.aggregate(media=Avg("confianca"))["media"] or 0.0), 2)

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
        RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(days=13))
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
            "setor_pacote": pacote.get("setor"),
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

    return {
        "owner": dono.nome,
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
