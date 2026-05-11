"""
Compliance & Auditoria — trilha de auditoria, painel LGPD, log de dispositivos.
Endpoint: GET /api/compliance/resumo
          GET /api/compliance/trilha     (paginado, filtrável)
          GET /api/compliance/dispositivos
          GET /api/compliance/exportar   (JSON/CSV)
Page:     GET /compliance/
"""
import csv
import json
from datetime import date, timedelta, datetime
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from .views_dashboard import _empresa_autenticada


def _trilha_to_dict(r):
    return {
        "id": r.id,
        "principal_tipo": r.principal_tipo,
        "principal_nome": r.principal_nome or "sistema",
        "acao": r.acao,
        "objeto_tipo": r.objeto_tipo or "",
        "objeto_id": r.objeto_id or "",
        "ip": r.ip or "",
        "detalhes": r.detalhes or {},
        "criado_em": r.criado_em.isoformat(),
        "criado_em_fmt": r.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


def api_compliance_resumo(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    agora = timezone.now()
    ultimos_30 = agora - timedelta(days=30)
    ultimas_24h = agora - timedelta(hours=24)

    try:
        from .models import (
            AuditoriaInstitucional, DispositivoAutorizado,
            ColaboradorAliasCorporativo, EmpresaUsuario
        )

        qs = AuditoriaInstitucional.objects.filter(empresa=empresa)
        total_eventos = qs.count()
        eventos_24h = qs.filter(criado_em__gte=ultimas_24h).count()
        eventos_30d = qs.filter(criado_em__gte=ultimos_30).count()

        # Distinct actors
        atores = qs.values("principal_nome").distinct().count()

        # Most frequent actions
        from django.db.models import Count
        top_acoes = list(
            qs.filter(criado_em__gte=ultimos_30)
            .values("acao")
            .annotate(total=Count("id"))
            .order_by("-total")[:8]
        )

        # IPs distintos
        ips_distintos = qs.exclude(ip__isnull=True).exclude(ip="").values("ip").distinct().count()

        # Devices
        devs = DispositivoAutorizado.objects.filter(empresa=empresa)
        devs_ativos = devs.filter(ativo=True).count()
        devs_total = devs.count()
        ultimo_acesso = devs.order_by("-ultimo_acesso").first()

        # LGPD data subjects
        try:
            titulares = ColaboradorAliasCorporativo.objects.filter(empresa=empresa, ativo=True).count()
        except Exception:
            titulares = 0
        try:
            usuarios = EmpresaUsuario.objects.filter(empresa=empresa, ativo=True).count()
        except Exception:
            usuarios = 0

        # Retention info — based on oldest audit record
        mais_antigo = qs.order_by("criado_em").first()
        retencao_desde = mais_antigo.criado_em.strftime("%d/%m/%Y") if mais_antigo else None

    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({
        "empresa": empresa.nome,
        "data": str(hoje),
        "auditoria": {
            "total_eventos": total_eventos,
            "eventos_24h": eventos_24h,
            "eventos_30d": eventos_30d,
            "atores_distintos": atores,
            "ips_distintos": ips_distintos,
            "top_acoes": top_acoes,
        },
        "dispositivos": {
            "ativos": devs_ativos,
            "total": devs_total,
            "ultimo_acesso": ultimo_acesso.ultimo_acesso.isoformat() if ultimo_acesso and ultimo_acesso.ultimo_acesso else None,
        },
        "lgpd": {
            "titulares_ativos": titulares,
            "usuarios_sistema": usuarios,
            "retencao_desde": retencao_desde,
            "base_legal": "Contrato / legítimo interesse (Art. 7º, V e IX - LGPD)",
            "finalidade": "Monitoramento de saúde ocupacional e epidemiológica",
            "periodo_retencao_anos": 5,
            "responsavel": empresa.nome,
        },
    })


def api_compliance_trilha(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import AuditoriaInstitucional

        qs = AuditoriaInstitucional.objects.filter(empresa=empresa)

        # Filters
        acao_q = request.GET.get("acao", "").strip()
        ator_q = request.GET.get("ator", "").strip()
        objeto_q = request.GET.get("objeto_tipo", "").strip()
        desde = request.GET.get("desde", "")
        ate = request.GET.get("ate", "")

        if acao_q:
            qs = qs.filter(acao__icontains=acao_q)
        if ator_q:
            qs = qs.filter(principal_nome__icontains=ator_q)
        if objeto_q:
            qs = qs.filter(objeto_tipo__icontains=objeto_q)
        if desde:
            qs = qs.filter(criado_em__date__gte=desde)
        if ate:
            qs = qs.filter(criado_em__date__lte=ate)

        # Pagination
        limit = min(int(request.GET.get("limit", 50)), 200)
        offset = max(int(request.GET.get("offset", 0)), 0)
        total = qs.count()
        registros = qs[offset:offset + limit]

    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({
        "total": total,
        "offset": offset,
        "limit": limit,
        "registros": [_trilha_to_dict(r) for r in registros],
    })


def api_compliance_dispositivos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import DispositivoAutorizado
        devs = DispositivoAutorizado.objects.filter(empresa=empresa).order_by("-ultimo_acesso")[:100]
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)

    return JsonResponse({
        "dispositivos": [
            {
                "id": d.id,
                "device_id": d.device_id[:20] + "..." if len(d.device_id) > 20 else d.device_id,
                "apelido": d.apelido or "",
                "ip": d.ip or "",
                "ativo": d.ativo,
                "ultimo_acesso": d.ultimo_acesso.isoformat() if d.ultimo_acesso else None,
                "ultimo_acesso_fmt": d.ultimo_acesso.strftime("%d/%m/%Y %H:%M") if d.ultimo_acesso else "—",
                "user_agent_curto": (d.user_agent or "")[:80],
            }
            for d in devs
        ]
    })


def api_compliance_exportar(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    fmt = request.GET.get("formato", "json")

    try:
        from .models import AuditoriaInstitucional
        qs = AuditoriaInstitucional.objects.filter(empresa=empresa).order_by("-criado_em")[:1000]
        registros = [_trilha_to_dict(r) for r in qs]
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)

    if fmt == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="auditoria_{empresa.id}_{date.today()}.csv"'
        response.write('﻿')  # BOM for Excel
        writer = csv.writer(response)
        writer.writerow(["id", "data_hora", "ator", "tipo_ator", "acao", "objeto_tipo", "objeto_id", "ip"])
        for r in registros:
            writer.writerow([
                r["id"], r["criado_em_fmt"], r["principal_nome"],
                r["principal_tipo"], r["acao"], r["objeto_tipo"], r["objeto_id"], r["ip"]
            ])
        return response

    response = HttpResponse(
        json.dumps({"empresa": empresa.nome, "exportado_em": datetime.now().isoformat(), "registros": registros},
                   ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8"
    )
    response["Content-Disposition"] = f'attachment; filename="auditoria_{empresa.id}_{date.today()}.json"'
    return response


def compliance_page(request):
    from django.shortcuts import render
    return render(request, "compliance.html")
