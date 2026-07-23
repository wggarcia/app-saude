"""
Gestão FAP — Fator Acidentário de Prevenção · SoloCRT SST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

O que é o FAP?
──────────────
FAP (Fator Acidentário de Prevenção) é um multiplicador definido anualmente
pelo INSS que ajusta o RAT (Risco Ambiental do Trabalho) de cada empresa.

  RAT ajustado = RAT base × FAP

• RAT base: alíquota de 1%, 2% ou 3% sobre a folha, conforme o grau de risco
  do CNAE da empresa (leve / médio / grave).
• FAP: varia de 0,5000 a 2,0000.
  – FAP < 1,0 → Bônus (redutor): empresa acidentou MENOS que a média do setor.
  – FAP = 1,0 → Neutro.
  – FAP > 1,0 → Malus (majorador): empresa acidentou MAIS que a média do setor.
• O FAP é calculado com base em acidentes e doenças do trabalho registrados nos
  dois anos anteriores (frequência, gravidade, custo e mortalidade).
• Publicado anualmente pelo MPS/INSS (geralmente em novembro/dezembro).
• Contestação: empresa pode contestar o FAP em até 30 dias da publicação
  via portal Meu INSS / PLENUS.

Impacto financeiro:
  Empresa com 100 funcionários, folha R$ 300.000/mês, RAT 3%
  → Sem FAP (neutro 1,0): R$ 9.000/mês em RAT
  → Com FAP 0,5 (bônus): R$ 4.500/mês → economia de R$ 54.000/ano
  → Com FAP 2,0 (malus): R$ 18.000/mês → custo extra de R$ 108.000/ano

Boa gestão SST → menos acidentes → FAP reduzido → economia real no FGTS/INSS.

Endpoints:
  GET  /api/sst/fap/                        — FAP atual + histórico da empresa
  POST /api/sst/fap/registrar/              — Registrar FAP do exercício
  GET  /api/sst/fap/<id>/                   — Detalhe de um registro FAP
  PATCH /api/sst/fap/<id>/                  — Atualizar registro FAP
  GET  /api/sst/fap/simulacao/              — Simular impacto financeiro
  GET  /api/sst/fap/contestacao/            — Guia de contestação + prazo
  GET  /api/sst/fap/kpis/                   — Painel executivo FAP
  GET  /api/sst/fap/historico/              — Evolução FAP por ano (gráfico)
"""

import logging
from datetime import date
from django.http import JsonResponse
from django.shortcuts import render, redirect
import json

logger = logging.getLogger(__name__)


def _checar_permissao_escrita_fap(request):
    """Retorna JsonResponse 403 se o principal não tem permissão de escrita no módulo FAP.
    FAP é coberto por sst.gestao_conformidade (inclui conformidade, eSocial, FAP, riscos).
    Retorna None se a permissão estiver ok."""
    from .access_control import principal_tem_algum_modulo
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    principal = getattr(request, "principal", None) or empresa
    if not principal_tem_algum_modulo(empresa, principal, ("sst.gestao_conformidade",)):
        return JsonResponse({
            "erro": "Acesso restrito. Requer permissão de Gestão / Conformidade SST para alterar o FAP.",
            "codigo_modulo": "sst.gestao_conformidade",
        }, status=403)
    return None


def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


# ─── Tabela RAT por grau de risco (NR-4 / Decreto 6.042/2007) ───────────────
GRAU_RISCO_RAT = {
    1: {"descricao": "Grau 1 — Risco Leve",   "aliquota_pct": 1.0},
    2: {"descricao": "Grau 2 — Risco Médio",   "aliquota_pct": 2.0},
    3: {"descricao": "Grau 3 — Risco Grave",   "aliquota_pct": 3.0},
}

# CNAEs de exemplo por grau de risco (amostra representativa)
CNAE_GRAU_RISCO = {
    # Grau 1 — Risco Leve
    "6201500": 1,  # Desenvolvimento de programas de computador
    "6202300": 1,  # Desenvolvimento e licenciamento de programas
    "7020400": 1,  # Atividades de consultoria em gestão empresarial
    "8630507": 1,  # Atividades de reprodução humana assistida
    # Grau 2 — Risco Médio
    "8610101": 2,  # Atividades de atendimento hospitalar
    "8621601": 2,  # UTI móvel
    "4771701": 2,  # Comércio varejista de produtos farmacêuticos
    "8650001": 2,  # Atividades de fisioterapia
    # Grau 3 — Risco Grave
    "1011201": 3,  # Frigorífico — abate de bovinos
    "2311700": 3,  # Fabricação de vidro plano
    "0910600": 3,  # Atividades de apoio à extração de petróleo
    "4330403": 3,  # Obras de alvenaria
}


def _grau_risco_cnae(cnae: str) -> int:
    """Retorna grau de risco 1, 2 ou 3 para o CNAE. Default: 2."""
    cnae_limpo = cnae.replace(".", "").replace("/", "").replace("-", "").strip()
    return CNAE_GRAU_RISCO.get(cnae_limpo, 2)


def _calcular_fap_impacto(rat_base_pct: float, fap_valor: float, folha_mensal: float) -> dict:
    """Calcula impacto financeiro do FAP sobre a folha salarial."""
    rat_ajustado_pct = rat_base_pct * fap_valor
    custo_rat_mensal = folha_mensal * rat_ajustado_pct / 100
    custo_rat_sem_fap = folha_mensal * rat_base_pct / 100
    delta_mensal = custo_rat_sem_fap - custo_rat_mensal  # positivo = economia
    return {
        "rat_base_pct": round(rat_base_pct, 4),
        "fap_valor": round(fap_valor, 4),
        "rat_ajustado_pct": round(rat_ajustado_pct, 4),
        "folha_mensal": round(folha_mensal, 2),
        "custo_rat_mensal": round(custo_rat_mensal, 2),
        "custo_rat_anual": round(custo_rat_mensal * 12, 2),
        "custo_rat_sem_fap_mensal": round(custo_rat_sem_fap, 2),
        "custo_rat_sem_fap_anual": round(custo_rat_sem_fap * 12, 2),
        "delta_mensal": round(delta_mensal, 2),    # positivo = economia
        "delta_anual": round(delta_mensal * 12, 2),
        "tipo_fap": _classificar_fap(fap_valor),
        "impacto_resumo": _resumo_impacto(fap_valor, delta_mensal),
    }


def _classificar_fap(fap_valor: float) -> str:
    if fap_valor < 1.0:
        return "bonus"      # FAP redutor — empresa melhor que a média
    elif fap_valor == 1.0:
        return "neutro"
    else:
        return "malus"      # FAP majorador — empresa pior que a média


def _resumo_impacto(fap_valor: float, delta_mensal: float) -> str:
    if delta_mensal > 0:
        return f"✅ Economia de R$ {delta_mensal:,.2f}/mês — FAP {fap_valor:.4f} (bônus)"
    elif delta_mensal < 0:
        return f"⚠️ Custo adicional de R$ {abs(delta_mensal):,.2f}/mês — FAP {fap_valor:.4f} (malus)"
    return "➡️ Impacto neutro — FAP = 1,0"


def _fap_dict(fap):
    impacto = _calcular_fap_impacto(
        float(fap.rat_base_pct),
        float(fap.fap_valor),
        float(fap.folha_salarial_mensal),
    )
    return {
        "id": fap.id,
        "ano": fap.ano,
        "cnae": fap.cnae,
        "cnae_descricao": fap.cnae_descricao,
        "grau_risco": fap.grau_risco,
        "rat_base_pct": float(fap.rat_base_pct),
        "fap_valor": float(fap.fap_valor),
        "rat_ajustado_pct": float(fap.rat_base_pct) * float(fap.fap_valor),
        "folha_salarial_mensal": float(fap.folha_salarial_mensal),
        "fonte": fap.fonte,
        "publicado_em": str(fap.publicado_em or ""),
        "prazo_contestacao": str(fap.prazo_contestacao or ""),
        "contestado": fap.contestado,
        "resultado_contestacao": fap.resultado_contestacao,
        "observacoes": fap.observacoes,
        "criado_em": str(fap.criado_em.date()),
        **impacto,
    }


# ──────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

def api_fap_lista(request):
    """
    GET  → Lista FAPs registrados da empresa (histórico completo).
    POST → Alias para registrar (atalho). Requer permissão de gestão de conformidade.
    """
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    if request.method == "POST":
        erro_perm = _checar_permissao_escrita_fap(request)
        if erro_perm:
            return erro_perm
        return api_fap_registrar(request)

    try:
        from .models import FAPEmpresa
        qs = FAPEmpresa.objects.filter(empresa=empresa).order_by("-ano")
        atual = qs.first()

        return JsonResponse({
            "fap_atual": _fap_dict(atual) if atual else None,
            "historico": [_fap_dict(f) for f in qs[:10]],
            "total_registros": qs.count(),
            "o_que_e_fap": {
                "definicao": "Fator Acidentário de Prevenção — multiplicador do RAT publicado anualmente pelo INSS.",
                "formula": "RAT ajustado = RAT base × FAP",
                "faixa": "0,5000 (mínimo) a 2,0000 (máximo)",
                "bonus": "FAP < 1,0 → empresa melhor que a média do setor → desconto no RAT",
                "malus": "FAP > 1,0 → empresa pior que a média do setor → acréscimo no RAT",
                "publicacao": "Publicado pelo INSS em novembro/dezembro para vigência no ano seguinte",
                "contestacao_prazo_dias": 30,
                "fonte_dados": "Acidentes e doenças do trabalho dos 2 anos anteriores (CAT + benefícios concedidos)",
                "portal_inss": "https://www.gov.br/previdencia/pt-br/fap",
            },
        })
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=500)


def api_fap_registrar(request):
    """POST — Registra o FAP do exercício informado pelo INSS. Requer permissão de gestão de conformidade."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    erro_perm = _checar_permissao_escrita_fap(request)
    if erro_perm:
        return erro_perm

    data = _json(request)
    campos_obrig = ["ano", "fap_valor", "folha_salarial_mensal"]
    for c in campos_obrig:
        if data.get(c) is None:
            return JsonResponse({"erro": f"Campo obrigatório: {c}"}, status=400)

    try:
        from .models import FAPEmpresa
        ano = int(data["ano"])
        fap_valor = float(data["fap_valor"])
        folha = float(data["folha_salarial_mensal"])

        if not (0.5 <= fap_valor <= 2.0):
            return JsonResponse({"erro": "FAP deve estar entre 0,5000 e 2,0000"}, status=400)

        cnae = data.get("cnae", empresa.cnae if hasattr(empresa, "cnae") else "")
        grau_risco = data.get("grau_risco") or _grau_risco_cnae(cnae)
        rat_base = GRAU_RISCO_RAT.get(int(grau_risco), {"aliquota_pct": 2.0})["aliquota_pct"]

        fap, criado = FAPEmpresa.objects.get_or_create(
            empresa=empresa,
            ano=ano,
            defaults={
                "cnae": cnae,
                "cnae_descricao": data.get("cnae_descricao", ""),
                "grau_risco": int(grau_risco),
                "rat_base_pct": rat_base,
                "fap_valor": fap_valor,
                "folha_salarial_mensal": folha,
                "fonte": data.get("fonte", "manual"),
                "publicado_em": data.get("publicado_em"),
                "prazo_contestacao": data.get("prazo_contestacao"),
                "observacoes": data.get("observacoes", ""),
            }
        )

        if not criado:
            # Atualiza valores existentes
            fap.fap_valor = fap_valor
            fap.folha_salarial_mensal = folha
            fap.grau_risco = int(grau_risco)
            fap.rat_base_pct = rat_base
            if data.get("cnae"):
                fap.cnae = cnae
            fap.observacoes = data.get("observacoes", fap.observacoes)
            fap.save()

        return JsonResponse({
            "sucesso": True,
            "criado": criado,
            "fap": _fap_dict(fap),
        }, status=201 if criado else 200)
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=500)


def api_fap_detalhe(request, fap_id):
    """GET / PATCH — Detalhe e edição de um registro FAP. PATCH requer permissão de gestão de conformidade."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FAPEmpresa
        fap = FAPEmpresa.objects.get(id=fap_id, empresa=empresa)

        if request.method == "PATCH":
            erro_perm = _checar_permissao_escrita_fap(request)
            if erro_perm:
                return erro_perm
            data = _json(request)
            campos_editaveis = [
                "fap_valor", "folha_salarial_mensal", "cnae", "cnae_descricao",
                "grau_risco", "fonte", "publicado_em", "prazo_contestacao",
                "contestado", "resultado_contestacao", "observacoes",
            ]
            for campo in campos_editaveis:
                if campo in data:
                    setattr(fap, campo, data[campo])
            if "grau_risco" in data:
                fap.rat_base_pct = GRAU_RISCO_RAT.get(int(data["grau_risco"]), {"aliquota_pct": 2.0})["aliquota_pct"]
            fap.save()

        return JsonResponse(_fap_dict(fap))
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=404)


def api_fap_simulacao(request):
    """
    GET — Simula impacto do FAP sobre diferentes cenários de folha.
    Parâmetros: folha_mensal, rat_pct (ou grau_risco), fap_valores (CSV: 0.5,0.8,1.0,1.5,2.0)
    """
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        folha = float(request.GET.get("folha_mensal", 100000))
        grau_risco = int(request.GET.get("grau_risco", 2))
        rat_base = float(request.GET.get("rat_pct", 0) or GRAU_RISCO_RAT.get(grau_risco, {"aliquota_pct": 2.0})["aliquota_pct"])

        fap_str = request.GET.get("fap_valores", "0.5,0.6667,0.8,1.0,1.25,1.5,2.0")
        fap_valores = [float(v.strip()) for v in fap_str.split(",") if v.strip()]

        cenarios = []
        for fv in fap_valores:
            c = _calcular_fap_impacto(rat_base, fv, folha)
            c["fap_valor"] = round(fv, 4)
            c["label"] = f"FAP {fv:.4f} ({_classificar_fap(fv)})"
            cenarios.append(c)

        # Busca FAP atual da empresa para comparação
        from .models import FAPEmpresa
        fap_atual = FAPEmpresa.objects.filter(empresa=empresa).order_by("-ano").first()

        return JsonResponse({
            "parametros": {
                "folha_mensal": folha,
                "grau_risco": grau_risco,
                "rat_base_pct": rat_base,
                "descricao_grau": GRAU_RISCO_RAT.get(grau_risco, {}).get("descricao", ""),
            },
            "cenarios": cenarios,
            "fap_atual_empresa": _fap_dict(fap_atual) if fap_atual else None,
            "melhor_cenario": cenarios[0] if cenarios else None,
            "pior_cenario": cenarios[-1] if cenarios else None,
            "dica": "Invista em SST para reduzir acidentes e conquistar FAP < 1,0 (bônus). "
                    "Com FAP 0,5 você paga apenas metade do RAT.",
        })
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=500)


def api_fap_contestacao(request):
    """GET — Guia completo de contestação do FAP + prazo da empresa."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FAPEmpresa
        fap_atual = FAPEmpresa.objects.filter(empresa=empresa).order_by("-ano").first()

        hoje = date.today()
        prazo_vencido = False
        dias_restantes = None
        if fap_atual and fap_atual.prazo_contestacao:
            dias_restantes = (fap_atual.prazo_contestacao - hoje).days
            prazo_vencido = dias_restantes < 0

        return JsonResponse({
            "fap_atual": _fap_dict(fap_atual) if fap_atual else None,
            "prazo_contestacao": {
                "dias_restantes": dias_restantes,
                "prazo_vencido": prazo_vencido,
                "alerta": (
                    "⚠️ Prazo de contestação vencido." if prazo_vencido
                    else f"📅 {dias_restantes} dias restantes para contestar." if dias_restantes is not None
                    else "Registre o FAP para calcular prazo."
                ),
            },
            "como_contestar": {
                "prazo_legal": "30 dias corridos após publicação no DOU",
                "portal": "https://www.gov.br/previdencia/pt-br/fap → 'Contestação FAP'",
                "sistema_inss": "PLENUS — sistema de contestação do INSS",
                "documentos_necessarios": [
                    "Relação de CATs emitidas no período base",
                    "Relação de benefícios de AT/DAT concedidos pelo INSS",
                    "Folha de pagamento do período base",
                    "RAIS dos dois anos anteriores",
                    "Laudos técnicos (LTCAT/LIP) comprovando ausência de agentes nocivos",
                    "PPP dos funcionários afastados (se aplicável)",
                    "Laudo de ergonomia e plano de ação (PCMSO/PGR atualizado)",
                ],
                "motivos_contestacao": [
                    "CAT registrada indevidamente (acidente de trajeto computado como típico)",
                    "Benefício concedido para CNPJ errado",
                    "Funcionário já havia saído da empresa na data do acidente",
                    "Nexo causal questionável — sem laudo médico definitivo",
                    "Erro aritmético no cálculo INSS",
                ],
                "resultado_possivel": "Redução do FAP se contestação aprovada → economia imediata no próximo exercício",
                "assessoria": "Recomendamos suporte de advogado previdenciário ou médico do trabalho especialista em FAP",
            },
            "impacto_sst_no_fap": {
                "acoes_reduzem_fap": [
                    "Reduzir número de acidentes típicos e doenças ocupacionais",
                    "Emitir CATs apenas quando obrigatório (não para acidentes leves sem afastamento)",
                    "Manter PCMSO e PGR/PPRA atualizados",
                    "Treinamentos NR obrigatórios em dia",
                    "Programa de reabilitação para retorno ao trabalho (evita benefícios longos)",
                    "Gestão de ergonomia e agentes nocivos (LTCAT atualizado)",
                    "CIPA atuante e registrada",
                ],
                "indicadores_inss": [
                    "Frequência de acidentes (nº CATs / vínculos empregatícios)",
                    "Gravidade (dias de afastamento / benefícios concedidos)",
                    "Custo (valor dos benefícios pagos pelo INSS)",
                    "Mortalidade (óbitos por acidente de trabalho)",
                ],
            },
        })
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=500)


def api_fap_historico(request):
    """GET — Evolução do FAP por ano (ideal para gráfico de linha)."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FAPEmpresa
        qs = FAPEmpresa.objects.filter(empresa=empresa).order_by("ano")

        historico = []
        for fap in qs:
            impacto = _calcular_fap_impacto(
                float(fap.rat_base_pct), float(fap.fap_valor), float(fap.folha_salarial_mensal)
            )
            historico.append({
                "ano": fap.ano,
                "fap_valor": float(fap.fap_valor),
                "rat_base_pct": float(fap.rat_base_pct),
                "rat_ajustado_pct": round(float(fap.rat_base_pct) * float(fap.fap_valor), 4),
                "tipo_fap": _classificar_fap(float(fap.fap_valor)),
                "delta_anual": impacto["delta_anual"],
                "custo_rat_anual": impacto["custo_rat_anual"],
            })

        # Tendência: melhorando ou piorando?
        tendencia = "sem_dados"
        if len(historico) >= 2:
            ultimo = historico[-1]["fap_valor"]
            penultimo = historico[-2]["fap_valor"]
            if ultimo < penultimo:
                tendencia = "melhorando"    # FAP caindo = bom
            elif ultimo > penultimo:
                tendencia = "piorando"
            else:
                tendencia = "estavel"

        return JsonResponse({
            "historico": historico,
            "tendencia": tendencia,
            "tendencia_label": {
                "melhorando": "📉 FAP caindo — parabéns! Menos acidentes que no ano anterior.",
                "piorando": "📈 FAP subindo — atenção! Aumente ações preventivas de SST.",
                "estavel": "➡️ FAP estável.",
                "sem_dados": "Registre ao menos dois anos para ver tendência.",
            }.get(tendencia, ""),
            "total_anos": len(historico),
        })
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=500)


def api_fap_kpis(request):
    """GET — Painel executivo FAP: impacto financeiro, alertas, ações recomendadas."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import FAPEmpresa, CATOcupacional, FuncionarioSST

        fap_atual = FAPEmpresa.objects.filter(empresa=empresa).order_by("-ano").first()
        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()

        # Acidentes dos últimos 12 meses (para projetar próximo FAP)
        from datetime import timedelta
        hoje = date.today()
        janela = hoje - timedelta(days=365)
        total_cats = 0
        try:
            total_cats = CATOcupacional.objects.filter(empresa=empresa, data_acidente__gte=janela).count()
        except Exception:
            pass

        # Taxa de frequência de acidentes
        taxa_freq = round(total_cats / max(total_func, 1) * 1000, 2)  # por 1.000 vínculos

        alertas = []
        if fap_atual:
            fv = float(fap_atual.fap_valor)
            if fv > 1.5:
                alertas.append({"nivel": "critico", "msg": f"FAP {fv:.4f} — custo adicional severo. Plano de ação urgente."})
            elif fv > 1.0:
                alertas.append({"nivel": "atencao", "msg": f"FAP {fv:.4f} — malus aplicado. Reduza acidentes para próximo exercício."})
            elif fv < 0.6667:
                alertas.append({"nivel": "info", "msg": f"FAP {fv:.4f} — excelente! Bônus máximo próximo (0,5000)."})

            if fap_atual.prazo_contestacao:
                dias = (fap_atual.prazo_contestacao - hoje).days
                if 0 < dias <= 10:
                    alertas.append({"nivel": "urgente", "msg": f"⚠️ Prazo de contestação vence em {dias} dias!"})
                elif dias <= 0:
                    alertas.append({"nivel": "info", "msg": "Prazo de contestação encerrado."})

        if total_cats > 5:
            alertas.append({"nivel": "atencao", "msg": f"{total_cats} CATs nos últimos 12 meses — pode impactar FAP do próximo exercício."})

        impacto = None
        if fap_atual:
            impacto = _calcular_fap_impacto(
                float(fap_atual.rat_base_pct),
                float(fap_atual.fap_valor),
                float(fap_atual.folha_salarial_mensal),
            )

        return JsonResponse({
            "ano_atual": fap_atual.ano if fap_atual else None,
            "fap_valor": float(fap_atual.fap_valor) if fap_atual else None,
            "tipo_fap": _classificar_fap(float(fap_atual.fap_valor)) if fap_atual else None,
            "rat_base_pct": float(fap_atual.rat_base_pct) if fap_atual else None,
            "rat_ajustado_pct": round(float(fap_atual.rat_base_pct) * float(fap_atual.fap_valor), 4) if fap_atual else None,
            "impacto_financeiro": impacto,
            "indicadores_acidente": {
                "total_funcionarios_ativos": total_func,
                "cats_ultimos_12_meses": total_cats,
                "taxa_frequencia_por_mil": taxa_freq,
                "benchmark_setor": "< 5,0 por mil vínculos (referência INSS)",
            },
            "alertas": alertas,
            "fap_registrado": fap_atual is not None,
            "acao_sugerida": (
                "Conteste o FAP se identificar inconsistências nos dados do INSS."
                if fap_atual and float(fap_atual.fap_valor) > 1.0
                else "Mantenha o bom trabalho em SST para preservar o bônus FAP."
                if fap_atual
                else "Registre o FAP do exercício atual para acompanhar o impacto financeiro."
            ),
            "grau_risco_tabela": GRAU_RISCO_RAT,
        })
    except Exception:
        logger.exception("Erro interno FAP")
        return JsonResponse({"erro": "Erro interno ao processar requisição FAP"}, status=500)


# ── Página HTML ───────────────────────────────────────────────────────────────

from .access_control import api_requer_permissao_modulo, requer_permissao_modulo


@requer_permissao_modulo("sst.gestao_conformidade")
def sst_fap_page(request):
    from .views_dashboard import _empresa_autenticada
    from .views_sst import _empresa_sst_autenticada
    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_fap.html", {
        "empresa_nome": empresa.nome,
    })
