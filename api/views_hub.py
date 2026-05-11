"""
Hub Enterprise — portal de módulos filtrado por setor do cliente.
Cada empresa vê APENAS os módulos do seu setor. Isolamento total de ambiente.
Page: GET /hub/
"""
from django.shortcuts import render, redirect
from .access_control import get_setor
from .views_dashboard import _empresa_autenticada

# Módulos disponíveis por setor — ISOLAMENTO TOTAL entre ambientes
MODULOS_POR_SETOR = {
    "empresa": {
        "Operacional": [
            {
                "icon": "🛡️", "nome": "Saúde & Segurança (SST)",
                "url": "/sst/", "badge": "live",
                "desc": "Funcionários, exames, ASO, EPIs, CAT, eSocial, treinamentos NR",
            },
            {
                "icon": "❤️", "nome": "Saúde Ocupacional",
                "url": "/dashboard-empresa/", "badge": "live",
                "desc": "Check-ins diários/semanais, bem-estar, burnout, apoio psicológico",
            },
        ],
        "Analytics & Relatórios": [
            {
                "icon": "📄", "nome": "Relatório Executivo",
                "url": "/relatorio-executivo/", "badge": "novo",
                "desc": "Relatório consolidado por período, exportável — SST e compliance",
            },
        ],
        "Compliance & Segurança": [
            {
                "icon": "🔒", "nome": "Compliance & Auditoria",
                "url": "/compliance/", "badge": "novo",
                "desc": "Trilha de auditoria, LGPD, dispositivos autorizados, exportação CSV",
            },
            {
                "icon": "📡", "nome": "Observabilidade & SLO",
                "url": "/observabilidade/", "badge": "novo",
                "desc": "Score de disponibilidade, latência por domínio, incidentes 30d",
            },
        ],
        "Plataforma de Dados & IA": [
            {
                "icon": "🤖", "nome": "MLOps Pipeline",
                "url": "/mlops/", "badge": "ia",
                "desc": "Registro de modelos, drift detection, fairness, monitoramento de performance",
            },
            {
                "icon": "📐", "nome": "Schema Registry",
                "url": "/schema-registry/", "badge": "novo",
                "desc": "Contratos de dados versionados, validação de payload, compatibilidade",
            },
            {
                "icon": "🗃", "nome": "Feature Store",
                "url": "/feature-store/", "badge": "novo",
                "desc": "Registry de features ML, dicionário de eventos, SLA de qualidade por fonte",
            },
            {
                "icon": "⚡", "nome": "Event Backbone",
                "url": "/eventos/", "badge": "novo",
                "desc": "Outbox Pattern, at-least-once delivery, DLQ, webhook subscriptions HMAC",
            },
        ],
    },
    "farmacia": {
        "Operacional": [
            {
                "icon": "💊", "nome": "Gestão Farmácia",
                "url": "/farmacia/gestao/", "badge": "live",
                "desc": "Estoque FEFO, dispensações, receitas, inventário, descarte, curva ABC",
            },
            {
                "icon": "📊", "nome": "Dashboard Farmácia",
                "url": "/dashboard-farmacia/", "badge": "live",
                "desc": "KPIs de demanda, alertas sazonais, abastecimento preventivo por bairro",
            },
        ],
        "Analytics & Relatórios": [
            {
                "icon": "📄", "nome": "Relatório Executivo",
                "url": "/relatorio-executivo/", "badge": "novo",
                "desc": "Relatório consolidado por período, exportável em PDF",
            },
        ],
        "Compliance & Segurança": [
            {
                "icon": "🔒", "nome": "Compliance & Auditoria",
                "url": "/compliance/", "badge": "novo",
                "desc": "Trilha de auditoria, LGPD, dispositivos autorizados, exportação CSV",
            },
            {
                "icon": "📡", "nome": "Observabilidade & SLO",
                "url": "/observabilidade/", "badge": "novo",
                "desc": "Score de disponibilidade, latência por domínio, incidentes 30d",
            },
        ],
    },
    "hospital": {
        "Operacional": [
            {
                "icon": "🏥", "nome": "Gestão Hospital",
                "url": "/hospital/gestao/", "badge": "live",
                "desc": "Leitos, internações, triagem, evoluções clínicas, alta médica",
            },
            {
                "icon": "📊", "nome": "Dashboard Hospital",
                "url": "/dashboard-hospital/", "badge": "live",
                "desc": "Ocupação, atendimentos, pressão assistencial, alertas de surto",
            },
        ],
        "Analytics & Relatórios": [
            {
                "icon": "📄", "nome": "Relatório Executivo",
                "url": "/relatorio-executivo/", "badge": "novo",
                "desc": "Relatório consolidado por período, exportável em PDF",
            },
        ],
        "Compliance & Segurança": [
            {
                "icon": "🔒", "nome": "Compliance & Auditoria",
                "url": "/compliance/", "badge": "novo",
                "desc": "Trilha de auditoria, LGPD, dispositivos autorizados, exportação CSV",
            },
            {
                "icon": "📡", "nome": "Observabilidade & SLO",
                "url": "/observabilidade/", "badge": "novo",
                "desc": "Score de disponibilidade, latência por domínio, incidentes 30d",
            },
        ],
        "Plataforma de Dados & IA": [
            {
                "icon": "🤖", "nome": "MLOps Pipeline",
                "url": "/mlops/", "badge": "ia",
                "desc": "Modelos clínicos, drift detection, fairness e monitoramento de performance",
            },
        ],
    },
    "governo": {
        "Operacional": [
            {
                "icon": "🏛", "nome": "Gestão Governo",
                "url": "/governo/gestao/", "badge": "live",
                "desc": "Vigilância epidemiológica, alertas, controle municipal e estadual",
            },
            {
                "icon": "📊", "nome": "Dashboard Governo",
                "url": "/dashboard-governo/", "badge": "live",
                "desc": "Sala de situação, mapa epidemiológico, indicadores municipais",
            },
        ],
        "Analytics & Relatórios": [
            {
                "icon": "📄", "nome": "Relatório Executivo",
                "url": "/relatorio-executivo/", "badge": "novo",
                "desc": "Relatório consolidado por período, exportável em PDF",
            },
        ],
        "Compliance & Segurança": [
            {
                "icon": "🔒", "nome": "Compliance & Auditoria",
                "url": "/compliance/", "badge": "novo",
                "desc": "Trilha de auditoria, LGPD, dispositivos autorizados, exportação CSV",
            },
            {
                "icon": "📡", "nome": "Observabilidade & SLO",
                "url": "/observabilidade/", "badge": "novo",
                "desc": "Score de disponibilidade, latência por domínio, incidentes 30d",
            },
        ],
    },
    "rede": {
        "Operacional": [
            {
                "icon": "🌐", "nome": "Gestão de Rede",
                "url": "/rede/gestao/", "badge": "live",
                "desc": "Multi-unidades, benchmarking entre unidades, configurações de rede",
            },
            {
                "icon": "📊", "nome": "Dashboard de Rede",
                "url": "/dashboard-rede/", "badge": "live",
                "desc": "KPIs consolidados de todas as unidades, mapa de rede, tendência 30d",
            },
        ],
        "Analytics & Relatórios": [
            {
                "icon": "📄", "nome": "Relatório Executivo",
                "url": "/relatorio-executivo/", "badge": "novo",
                "desc": "Relatório consolidado por período, exportável em PDF",
            },
        ],
        "Compliance & Segurança": [
            {
                "icon": "🔒", "nome": "Compliance & Auditoria",
                "url": "/compliance/", "badge": "novo",
                "desc": "Trilha de auditoria, LGPD, dispositivos autorizados, exportação CSV",
            },
            {
                "icon": "📡", "nome": "Observabilidade & SLO",
                "url": "/observabilidade/", "badge": "novo",
                "desc": "Score de disponibilidade, latência por domínio, incidentes 30d",
            },
        ],
    },
    "plano_saude": {
        "Operacional": [
            {
                "icon": "💳", "nome": "Gestão Plano de Saúde",
                "url": "/plano-saude/gestao/", "badge": "live",
                "desc": "Contratos, beneficiários, coberturas, sinistros, reembolsos",
            },
        ],
        "Analytics & Relatórios": [
            {
                "icon": "📄", "nome": "Relatório Executivo",
                "url": "/relatorio-executivo/", "badge": "novo",
                "desc": "Relatório consolidado por período, exportável em PDF",
            },
        ],
        "Compliance & Segurança": [
            {
                "icon": "🔒", "nome": "Compliance & Auditoria",
                "url": "/compliance/", "badge": "novo",
                "desc": "Trilha de auditoria, LGPD, dispositivos autorizados, exportação CSV",
            },
            {
                "icon": "📡", "nome": "Observabilidade & SLO",
                "url": "/observabilidade/", "badge": "novo",
                "desc": "Score de disponibilidade, latência por domínio, incidentes 30d",
            },
        ],
    },
}

LABEL_SETOR = {
    "empresa": "Saúde Ocupacional",
    "farmacia": "Farmácia",
    "hospital": "Hospital",
    "governo": "Governo",
    "rede": "Rede de Saúde",
    "plano_saude": "Plano de Saúde",
}

VOLTAR_SETOR = {
    "empresa": ("/dashboard-empresa/", "← Painel SST"),
    "farmacia": ("/farmacia/gestao/", "← Gestão Farmácia"),
    "hospital": ("/hospital/gestao/", "← Gestão Hospital"),
    "governo": ("/dashboard-governo/", "← Painel Governo"),
    "rede": ("/rede/gestao/", "← Gestão Rede"),
    "plano_saude": ("/plano-saude/gestao/", "← Gestão Plano"),
}


def hub_view(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")

    setor = get_setor(empresa)
    categorias = MODULOS_POR_SETOR.get(setor, MODULOS_POR_SETOR["empresa"])
    voltar_url, voltar_label = VOLTAR_SETOR.get(setor, ("/dashboard-empresa/", "← Painel"))

    empresa_nome = (
        getattr(empresa, "nome_fantasia", None)
        or getattr(empresa, "razao_social", None)
        or getattr(empresa, "nome", "")
        or ""
    )

    return render(request, "hub_enterprise.html", {
        "empresa_id": empresa.id,
        "setor": setor,
        "setor_label": LABEL_SETOR.get(setor, setor.title()),
        "empresa_nome": empresa_nome,
        "categorias": categorias.items(),
        "voltar_url": voltar_url,
        "voltar_label": voltar_label,
    })
