"""
views_plano_antifraude.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Antifraude do Plano de Saúde (Fase 2 — VITA OS)

Analisa as guias TISS que a operadora RECEBE (LoteTISSRecebido + ItemContaTISS)
e sinaliza padrões de fraude/desperdício SEM depender de outro segmento (LGPD):

  1. Integridade TISS falhou (hash não confere) — possível adulteração do XML
  2. Guia/atendimento duplicado (mesma carteirinha + guia, ou mesmo
     prestador+beneficiário+procedimento no mesmo dia)
  3. Frequência anormal (mesmo beneficiário com muitas guias em poucos dias)
  4. Valor fora do padrão (item muito acima da mediana do procedimento)
  5. Prestador suspeito (alta taxa de duplicadas / valor médio muito acima)

Base para o "selo verificado por biometria" (Fase 2b): guias vindas de
hospitais SoloCRT com verificação facial entram com risco reduzido.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .biometria_token import validar_token
from .models import ItemContaTISS, LoteTISSRecebido
from .views_plano_saude import _ps_auth

# ─── Parâmetros das regras ────────────────────────────────────────────────────
JANELA_DIAS            = 90    # período analisado
FREQ_JANELA_DIAS       = 7     # janela p/ frequência anormal
FREQ_LIMITE            = 6     # nº de guias no período que dispara alerta
OUTLIER_FATOR          = 3.0   # valor > FATOR × mediana do procedimento
OUTLIER_MIN_AMOSTRAS   = 5     # mínimo de itens do procedimento p/ ter mediana
OUTLIER_VALOR_MINIMO   = Decimal("50")  # ignora bagatelas
PRESTADOR_DUP_TAXA     = 0.15  # >15% de guias duplicadas = prestador suspeito


def plano_antifraude_page(request):
    """Renderiza a página do painel antifraude."""
    empresa, err = _ps_auth(request)
    if err:
        # Página protegida: manda pro login/plano
        return render(request, "plano_antifraude.html", {"sem_acesso": True})
    return render(request, "plano_antifraude.html", {
        "empresa_nome": empresa.nome,
        "empresa_id": empresa.id,
    })


@require_http_methods(["GET"])
def api_plano_antifraude(request):
    """GET — roda o motor antifraude sobre as guias recebidas e retorna os achados."""
    empresa, err = _ps_auth(request)
    if err:
        return err

    desde = timezone.now() - timedelta(days=JANELA_DIAS)
    lotes = list(
        LoteTISSRecebido.objects
        .filter(empresa=empresa, recebido_em__gte=desde)
        .order_by("-recebido_em")
    )

    achados = []
    _gravidade_peso = {"alta": 3, "media": 2, "baixa": 1}

    # ── Regra 1: integridade TISS (hash não confere) ──────────────────────────
    for lo in lotes:
        if not lo.hash_confere:
            achados.append({
                "tipo": "integridade",
                "tipo_label": "Integridade TISS falhou",
                "gravidade": "alta",
                "titulo": f"XML adulterado — guia {lo.guia_numero or lo.numero_lote}",
                "detalhe": "O hash do arquivo TISS não confere: o conteúdo pode ter sido alterado após a geração.",
                "beneficiario": lo.beneficiario_nome,
                "prestador": lo.prestador_nome,
                "guia": lo.guia_numero,
                "valor": float(lo.valor_apresentado or 0),
                "data": lo.recebido_em.strftime("%d/%m/%Y"),
                "lote_id": lo.id,
            })

    # ── Regra 2: guia/atendimento duplicado ───────────────────────────────────
    por_chave = defaultdict(list)
    for lo in lotes:
        chave = (lo.beneficiario_carteirinha or "?", lo.guia_numero or "?")
        if chave != ("?", "?"):
            por_chave[chave].append(lo)
    for (cart, guia), grupo in por_chave.items():
        if len(grupo) > 1:
            valor = sum(float(x.valor_apresentado or 0) for x in grupo[1:])
            achados.append({
                "tipo": "duplicada",
                "tipo_label": "Guia duplicada",
                "gravidade": "alta",
                "titulo": f"Guia {guia} enviada {len(grupo)}× para a mesma carteirinha",
                "detalhe": f"A mesma guia aparece {len(grupo)} vezes — cobrança em duplicidade provável.",
                "beneficiario": grupo[0].beneficiario_nome,
                "prestador": grupo[0].prestador_nome,
                "guia": guia,
                "valor": valor,
                "data": grupo[0].recebido_em.strftime("%d/%m/%Y"),
                "lote_id": grupo[0].id,
            })

    # ── Regra 3: frequência anormal por beneficiário ──────────────────────────
    freq_desde = timezone.now() - timedelta(days=FREQ_JANELA_DIAS)
    por_benef = defaultdict(list)
    for lo in lotes:
        # Guia verificada por biometria = paciente real comprovadamente presente,
        # então não conta para "frequência suspeita" (não é fraude de identidade).
        if lo.biometria_verificada:
            continue
        if lo.recebido_em >= freq_desde and lo.beneficiario_carteirinha:
            por_benef[(lo.beneficiario_carteirinha, lo.beneficiario_nome)].append(lo)
    for (cart, nome), grupo in por_benef.items():
        if len(grupo) >= FREQ_LIMITE:
            achados.append({
                "tipo": "frequencia",
                "tipo_label": "Frequência anormal",
                "gravidade": "media",
                "titulo": f"{len(grupo)} guias em {FREQ_JANELA_DIAS} dias — {nome}",
                "detalhe": f"Beneficiário com {len(grupo)} atendimentos em {FREQ_JANELA_DIAS} dias. Verificar necessidade/possível uso indevido.",
                "beneficiario": nome,
                "prestador": "",
                "guia": "",
                "valor": sum(float(x.valor_apresentado or 0) for x in grupo),
                "data": grupo[0].recebido_em.strftime("%d/%m/%Y"),
                "lote_id": grupo[0].id,
            })

    # ── Regra 4: valor fora do padrão (outlier por procedimento) ──────────────
    itens = list(
        ItemContaTISS.objects
        .filter(lote__empresa=empresa, lote__recebido_em__gte=desde)
        .select_related("lote")
    )
    valores_por_proc = defaultdict(list)
    for it in itens:
        if it.codigo_procedimento and it.valor_unitario:
            valores_por_proc[it.codigo_procedimento].append(float(it.valor_unitario))
    medianas = {
        proc: statistics.median(vals)
        for proc, vals in valores_por_proc.items()
        if len(vals) >= OUTLIER_MIN_AMOSTRAS
    }
    for it in itens:
        med = medianas.get(it.codigo_procedimento)
        if not med or med <= 0:
            continue
        vu = float(it.valor_unitario or 0)
        if vu >= float(OUTLIER_VALOR_MINIMO) and vu > med * OUTLIER_FATOR:
            lo = it.lote
            achados.append({
                "tipo": "valor_outlier",
                "tipo_label": "Valor fora do padrão",
                "gravidade": "media",
                "titulo": f"{it.descricao or it.codigo_procedimento}: R$ {vu:,.2f} (mediana R$ {med:,.2f})",
                "detalhe": f"Valor {vu/med:.1f}× acima da mediana do procedimento {it.codigo_procedimento}.",
                "beneficiario": lo.beneficiario_nome,
                "prestador": lo.prestador_nome,
                "guia": lo.guia_numero,
                "valor": vu,
                "data": lo.recebido_em.strftime("%d/%m/%Y"),
                "lote_id": lo.id,
            })

    # ── Regra 5: prestador suspeito (alta taxa de duplicadas) ─────────────────
    por_prestador = defaultdict(lambda: {"total": 0, "dups": 0, "valor": 0.0, "nome": ""})
    dup_lotes = set()
    for grupo in por_chave.values():
        if len(grupo) > 1:
            for x in grupo[1:]:
                dup_lotes.add(x.id)
    for lo in lotes:
        chave = lo.prestador_cnes or lo.prestador_nome or "?"
        p = por_prestador[chave]
        p["total"] += 1
        p["nome"] = lo.prestador_nome or lo.prestador_cnes
        p["valor"] += float(lo.valor_apresentado or 0)
        if lo.id in dup_lotes:
            p["dups"] += 1
    for chave, p in por_prestador.items():
        if p["total"] >= 10 and (p["dups"] / p["total"]) > PRESTADOR_DUP_TAXA:
            taxa = p["dups"] / p["total"] * 100
            achados.append({
                "tipo": "prestador",
                "tipo_label": "Prestador suspeito",
                "gravidade": "alta",
                "titulo": f"{p['nome']}: {taxa:.0f}% de guias duplicadas",
                "detalhe": f"{p['dups']} de {p['total']} guias do prestador são duplicadas — padrão de cobrança indevida.",
                "beneficiario": "",
                "prestador": p["nome"],
                "guia": "",
                "valor": p["valor"],
                "data": "",
                "lote_id": None,
            })

    # Marca cada achado se a guia de origem tem selo biométrico (badge na UI)
    verif_por_lote = {lo.id: lo.biometria_verificada for lo in lotes}
    for a in achados:
        a["verificada"] = bool(verif_por_lote.get(a.get("lote_id")))

    # ── Ordena por gravidade e valor ──────────────────────────────────────────
    achados.sort(key=lambda a: (_gravidade_peso.get(a["gravidade"], 0), a["valor"]), reverse=True)

    valor_risco = sum(a["valor"] for a in achados)
    protegidas = sum(1 for lo in lotes if lo.biometria_verificada)
    resumo = {
        "total_guias":     len(lotes),
        "valor_total":     float(sum(float(x.valor_apresentado or 0) for x in lotes)),
        "total_achados":   len(achados),
        "flags_alta":      sum(1 for a in achados if a["gravidade"] == "alta"),
        "flags_media":     sum(1 for a in achados if a["gravidade"] == "media"),
        "valor_em_risco":  valor_risco,
        "protegidas_biometria": protegidas,
        "janela_dias":     JANELA_DIAS,
    }
    por_tipo = defaultdict(int)
    for a in achados:
        por_tipo[a["tipo_label"]] += 1

    return JsonResponse({
        "resumo": resumo,
        "por_tipo": dict(por_tipo),
        "achados": achados[:200],
    })


# ─── Ponto de entrada TISS com selo biométrico (Fase 2b) ──────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_tiss_receber_guia(request):
    """
    Recebe uma guia TISS na operadora, validando o selo biométrico (se vier).

    Este é o ponto de integração para quando a recepção TISS real existir:
    um hospital SoloCRT envia a guia com o campo `biometria_token` (gerado no
    check-in facial). Aqui o token é VALIDADO por assinatura (sem cruzar banco
    com o hospital) e a guia entra marcada como verificada por biometria.

    POST {
      prestador_nome, prestador_cnes?, prestador_codigo?,
      beneficiario_nome, beneficiario_carteirinha, beneficiario_cpf?,
      guia_numero, cid10?, valor_apresentado,
      biometria_token?    # selo gerado pelo hospital no check-in
    }
    """
    empresa, err = _ps_auth(request)
    if err:
        return err

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    if not data.get("beneficiario_nome") or not data.get("guia_numero"):
        return JsonResponse({"erro": "beneficiario_nome e guia_numero são obrigatórios."}, status=400)

    try:
        valor = Decimal(str(data.get("valor_apresentado", "0") or "0"))
    except (InvalidOperation, ValueError):
        valor = Decimal("0")

    # Valida o selo biométrico (se enviado)
    verificada = False
    score = 0.0
    token = (data.get("biometria_token") or "").strip()
    if token:
        payload = validar_token(token, cpf_esperado=data.get("beneficiario_cpf"))
        if payload:
            verificada = True
            score = float(payload.get("sc", 0) or 0)

    lote = LoteTISSRecebido.objects.create(
        empresa=empresa,
        prestador_nome=data.get("prestador_nome", ""),
        prestador_cnes=data.get("prestador_cnes", ""),
        prestador_codigo=data.get("prestador_codigo", ""),
        beneficiario_nome=data.get("beneficiario_nome", ""),
        beneficiario_carteirinha=data.get("beneficiario_carteirinha", ""),
        guia_numero=data.get("guia_numero", ""),
        cid10=data.get("cid10", ""),
        valor_apresentado=valor,
        biometria_verificada=verificada,
        biometria_score=score,
    )

    return JsonResponse({
        "ok": True,
        "lote_id": lote.id,
        "biometria_verificada": verificada,
        "biometria_score": round(score, 3),
        "mensagem": ("Guia recebida com selo biométrico válido — paciente verificado por rosto na origem."
                     if verificada else
                     "Guia recebida (sem selo biométrico)."),
    }, status=201)
