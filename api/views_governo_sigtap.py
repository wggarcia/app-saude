"""
SIGTAP — Tabela de Procedimentos SUS
GET /api/governo/sigtap/buscar         Busca por código ou nome (paginada)
GET /api/governo/sigtap/<codigo>       Detalhe com CIDs compatíveis
GET /api/governo/sigtap/validar        Valida procedimento + CID
GET /api/governo/sigtap/grupos         Lista grupos e subgrupos
GET /api/governo/sigtap/kpis           Status da última importação
POST /api/governo/sigtap/validar-bpa   Valida lista de itens antes de transmitir BPA
"""
import math

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from .access_control import get_setor, principal_pode_operacao_setorial, api_requer_permissao_modulo
from .services.auth_session import empresa_autenticada_from_request


def _gov(request):
    """Retorna empresa governo autenticada ou None."""
    emp = empresa_autenticada_from_request(request)
    if not emp or get_setor(emp) != "governo":
        return None
    if not principal_pode_operacao_setorial(request):
        return None
    return emp


# ── Busca ─────────────────────────────────────────────────────────────────────

@api_requer_permissao_modulo("governo.atencao_clinica", "governo.administrativo")
def api_sigtap_buscar(request):
    """
    GET /api/governo/sigtap/buscar?q=<texto>&complexidade=AB&instrumento=BPA-I&page=1
    Busca procedimentos por código parcial ou parte do nome.
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import ProcedimentoSIGTAP

    q              = (request.GET.get("q") or "").strip()
    complexidade   = (request.GET.get("complexidade") or "").strip().upper()
    instrumento    = (request.GET.get("instrumento") or "").strip().upper()
    grupo          = (request.GET.get("grupo") or "").strip()
    page           = max(1, int(request.GET.get("page") or 1))
    page_size      = 30

    qs = ProcedimentoSIGTAP.objects.filter(ativo=True)

    if q:
        if q.replace(".", "").isdigit():
            # Busca por código (aceita com ou sem pontos)
            codigo_limpo = q.replace(".", "").replace("-", "")
            qs = qs.filter(codigo__startswith=codigo_limpo)
        else:
            qs = qs.filter(descricao__icontains=q)

    if complexidade:
        qs = qs.filter(complexidade=complexidade)
    if instrumento:
        qs = qs.filter(instrumento_registro=instrumento)
    if grupo:
        qs = qs.filter(grupo=grupo)

    total   = qs.count()
    offset  = (page - 1) * page_size
    procs   = qs[offset: offset + page_size]

    return JsonResponse({
        "total":       total,
        "pagina":      page,
        "paginas":     math.ceil(total / page_size) if total else 1,
        "resultados":  [_proc_resumo(p) for p in procs],
        "disponivel":  total > 0,
        "aviso":       None if total > 0 else (
            "Tabela SIGTAP ainda não importada. "
            "Execute: python manage.py import_sigtap --competencia AAAAMM"
        ),
    })


@api_requer_permissao_modulo("governo.atencao_clinica", "governo.administrativo")
def api_sigtap_detalhe(request, codigo):
    """GET /api/governo/sigtap/<codigo> — detalhe + CIDs compatíveis."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import ProcedimentoSIGTAP

    codigo_limpo = codigo.replace(".", "").replace("-", "").zfill(10)
    try:
        proc = ProcedimentoSIGTAP.objects.prefetch_related("cids").get(codigo=codigo_limpo)
    except ProcedimentoSIGTAP.DoesNotExist:
        return JsonResponse({"erro": f"Procedimento {codigo} não encontrado"}, status=404)

    cids = [c.cid for c in proc.cids.all()]
    return JsonResponse({
        **_proc_resumo(proc),
        "cids_compativeis": cids,
        "total_cids":       len(cids),
        "composicao_codigo": {
            "grupo":            proc.codigo[0:2],
            "subgrupo":         proc.codigo[2:4],
            "forma_organizacao": proc.codigo[4:6],
            "area_atuacao":     proc.codigo[6:8],
            "procedimento":     proc.codigo[8:10],
        },
    })


@api_requer_permissao_modulo("governo.atencao_clinica", "governo.administrativo")
def api_sigtap_validar(request):
    """
    GET /api/governo/sigtap/validar?codigo=<code>&cid=<cid>
    Valida se o CID é compatível com o procedimento (para BPA/APAC/AIH).
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import ProcedimentoSIGTAP, ProcedimentoSIGTAPCID

    codigo = (request.GET.get("codigo") or "").replace(".", "").replace("-", "").strip().zfill(10)
    cid    = (request.GET.get("cid") or "").strip().upper().replace(".", "")

    if not codigo or len(codigo) != 10:
        return JsonResponse({"erro": "Parâmetro 'codigo' inválido (10 dígitos)"}, status=400)

    try:
        proc = ProcedimentoSIGTAP.objects.get(codigo=codigo, ativo=True)
    except ProcedimentoSIGTAP.DoesNotExist:
        return JsonResponse({
            "valido":    False,
            "codigo":    codigo,
            "cid":       cid,
            "motivo":    "Procedimento não encontrado na tabela SIGTAP",
        })

    cids_proc = list(proc.cids.values_list("cid", flat=True))

    # Se não há CIDs cadastrados para o procedimento, qualquer CID é aceito
    if not cids_proc:
        cid_ok = True
        motivo = "Procedimento sem restrição de CID na tabela"
    elif not cid:
        cid_ok = False
        motivo = "CID obrigatório para este procedimento"
    else:
        # Aceita CID exato ou código de categoria (ex: J18 aceita J180, J181, J189)
        cid_ok = (
            cid in cids_proc or
            any(c.startswith(cid) for c in cids_proc) or
            any(cid.startswith(c) for c in cids_proc)
        )
        motivo = "CID compatível com o procedimento" if cid_ok else (
            f"CID {cid} não está na lista de CIDs compatíveis com {codigo}"
        )

    return JsonResponse({
        "valido":              cid_ok,
        "codigo":              codigo,
        "descricao_proc":      proc.descricao,
        "cid":                 cid,
        "motivo":              motivo,
        "complexidade":        proc.complexidade,
        "instrumento":         proc.instrumento_registro,
        "valor_total":         float(proc.valor_total),
        "exige_autorizacao":   proc.exige_autorizacao,
        "cids_aceitos_amostra": cids_proc[:20],
        "total_cids":          len(cids_proc),
    })


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_permissao_modulo("governo.atencao_clinica", "governo.administrativo")
def api_sigtap_validar_bpa(request):
    """
    POST /api/governo/sigtap/validar-bpa
    Valida uma lista de itens BPA antes de transmitir ao DATASUS.
    Body: {"itens": [{"codigo": "0101010010", "cid": "J00", "quantidade": 2}, ...]}
    """
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    import json
    from .models import ProcedimentoSIGTAP, ProcedimentoSIGTAPCID

    try:
        body  = json.loads(request.body)
        itens = body.get("itens") or []
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    if not itens or len(itens) > 500:
        return JsonResponse({"erro": "Envie entre 1 e 500 itens"}, status=400)

    # Pre-load todos os procedimentos necessários
    codigos   = {str(i.get("codigo", "")).replace(".", "").replace("-", "").zfill(10) for i in itens}
    proc_map  = {
        p.codigo: p
        for p in ProcedimentoSIGTAP.objects.filter(codigo__in=codigos, ativo=True)
    }
    cid_map   = {}
    for proc in proc_map.values():
        cid_map[proc.codigo] = set(proc.cids.values_list("cid", flat=True))

    resultados = []
    erros      = 0
    for item in itens:
        codigo    = str(item.get("codigo", "")).replace(".", "").replace("-", "").zfill(10)
        cid       = str(item.get("cid", "")).strip().upper().replace(".", "")
        quantidade = int(item.get("quantidade") or 1)

        proc = proc_map.get(codigo)
        if not proc:
            resultados.append({
                "codigo": codigo,
                "cid": cid,
                "valido": False,
                "motivo": "Procedimento não encontrado no SIGTAP",
            })
            erros += 1
            continue

        cids_proc = cid_map.get(codigo, set())
        if cids_proc:
            cid_ok = (
                cid in cids_proc or
                any(c.startswith(cid) for c in cids_proc) or
                any(cid.startswith(c) for c in cids_proc)
            )
        else:
            cid_ok = True

        qt_ok  = proc.quantidade_maxima == 0 or quantidade <= proc.quantidade_maxima
        valido = cid_ok and qt_ok
        if not valido:
            erros += 1

        motivo_parts = []
        if not cid_ok:
            motivo_parts.append(f"CID {cid} incompatível")
        if not qt_ok:
            motivo_parts.append(f"Quantidade {quantidade} excede máximo {proc.quantidade_maxima}")

        resultados.append({
            "codigo":            codigo,
            "descricao":         proc.descricao,
            "cid":               cid,
            "quantidade":        quantidade,
            "valido":            valido,
            "motivo":            " | ".join(motivo_parts) if motivo_parts else "OK",
            "complexidade":      proc.complexidade,
            "instrumento":       proc.instrumento_registro,
            "valor_unitario":    float(proc.valor_total),
            "valor_total_item":  float(proc.valor_total) * quantidade,
            "exige_autorizacao": proc.exige_autorizacao,
        })

    valor_total = sum(r["valor_total_item"] for r in resultados if r["valido"])

    return JsonResponse({
        "total_itens":   len(itens),
        "itens_validos": len(itens) - erros,
        "itens_invalidos": erros,
        "pode_transmitir": erros == 0,
        "valor_total_estimado": round(valor_total, 2),
        "resultados":    resultados,
    })


@api_requer_permissao_modulo("governo.atencao_clinica", "governo.administrativo")
def api_sigtap_grupos(request):
    """GET /api/governo/sigtap/grupos — lista grupos com contagem de procedimentos."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import ProcedimentoSIGTAP
    from django.db.models import Count

    grupos = (
        ProcedimentoSIGTAP.objects
        .filter(ativo=True)
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("grupo")
    )

    _NOME_GRUPO = {
        "01": "Ações de Promoção e Prevenção em Saúde",
        "02": "Procedimentos com Finalidade Diagnóstica",
        "03": "Procedimentos Clínicos",
        "04": "Procedimentos Cirúrgicos",
        "05": "Transplantes de Órgãos, Tecidos e Células",
        "06": "Medicamentos",
        "07": "Órteses, Próteses e Materiais Especiais",
        "08": "Ações Complementares da Atenção à Saúde",
    }

    return JsonResponse({
        "grupos": [
            {
                "codigo":  g["grupo"],
                "nome":    _NOME_GRUPO.get(g["grupo"], f"Grupo {g['grupo']}"),
                "total_procedimentos": g["total"],
            }
            for g in grupos
        ]
    })


@api_requer_permissao_modulo("governo.atencao_clinica", "governo.administrativo")
def api_sigtap_kpis(request):
    """GET /api/governo/sigtap/kpis — status e métricas da tabela importada."""
    empresa = _gov(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Governo"}, status=403)

    from .models import ProcedimentoSIGTAP, SIGTAPImportacao
    from django.db.models import Count

    ultima = SIGTAPImportacao.objects.filter(sucesso=True).first()
    total_proc = ProcedimentoSIGTAP.objects.filter(ativo=True).count()

    por_complexidade = (
        ProcedimentoSIGTAP.objects.filter(ativo=True)
        .values("complexidade")
        .annotate(total=Count("id"))
        .order_by("complexidade")
    )

    return JsonResponse({
        "importada":           ultima is not None,
        "competencia_atual":   ultima.competencia if ultima else None,
        "importado_em":        ultima.importado_em.isoformat() if ultima else None,
        "total_procedimentos": total_proc,
        "por_complexidade": [
            {"complexidade": p["complexidade"] or "N/I", "total": p["total"]}
            for p in por_complexidade
        ],
        "aviso": (
            "Tabela SIGTAP não importada. Execute: "
            "python manage.py import_sigtap --competencia AAAAMM"
        ) if not ultima else None,
    })


# ── Helpers internos ──────────────────────────────────────────────────────────

def _proc_resumo(proc):
    return {
        "codigo":              proc.codigo,
        "codigo_formatado":    proc.codigo_formatado,
        "descricao":           proc.descricao,
        "grupo":               proc.grupo,
        "subgrupo":            proc.subgrupo,
        "complexidade":        proc.complexidade,
        "instrumento":         proc.instrumento_registro,
        "valor_total":         float(proc.valor_total),
        "valor_sh":            float(proc.valor_sh),
        "valor_sa":            float(proc.valor_sa),
        "valor_sp":            float(proc.valor_sp),
        "quantidade_maxima":   proc.quantidade_maxima,
        "exige_autorizacao":   proc.exige_autorizacao,
        "competencia":         proc.competencia,
    }
