"""
Helper compartilhado pelos módulos do grupo "Apoio, Qualidade e Integrações"
que usam o template genérico OPERÁVEL (hospital_modulo_operavel.html):
KPIs + lista com filtros + criar + ações por linha + ações de módulo,
tudo configurado por um dict simples — sem duplicar HTML/JS por módulo.

Para módulos com diferencial próprio (ex.: Qualidade/NSP com IA de causa-raiz,
Custos com margem por DRG), continue usando um template dedicado.
"""
import json
from django.shortcuts import render


def render_modulo_operavel(request, config):
    return render(request, "hospital_modulo_operavel.html", {
        "config": config,
        "config_json": json.dumps(config, ensure_ascii=False),
    })
