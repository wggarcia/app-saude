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


def api_soc2_controles(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "POST":
        import json as _json
        data = _json.loads(request.body)
        from .models import SOC2Controle
        controle = SOC2Controle.objects.create(
            empresa=empresa,
            codigo=data.get("codigo", ""),
            categoria=data.get("categoria", "CC"),
            titulo=data.get("titulo", ""),
            descricao=data.get("descricao", ""),
            responsavel=data.get("responsavel", ""),
            data_prevista=data.get("data_prevista") or None,
        )
        return JsonResponse({"id": controle.id, "codigo": controle.codigo, "status": controle.status})

    try:
        from .models import SOC2Controle
        from django.db.models import Count
        qs = SOC2Controle.objects.filter(empresa=empresa)
        categoria_q = request.GET.get("categoria")
        if categoria_q:
            qs = qs.filter(categoria=categoria_q)

        resumo_status = dict(
            qs.values("status").annotate(total=Count("id")).values_list("status", "total")
        )
        total = qs.count()
        implementados = resumo_status.get("implementado", 0) + resumo_status.get("auditado", 0)
        score_soc2 = round(implementados / total * 100, 1) if total > 0 else 0

        controles = list(qs.values(
            "id", "codigo", "categoria", "titulo", "status",
            "responsavel", "data_prevista", "data_implementacao",
        ))
        return JsonResponse({
            "empresa": empresa.nome,
            "score_soc2_pct": score_soc2,
            "total_controles": total,
            "resumo_status": resumo_status,
            "controles": controles,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_soc2_evidencias(request, controle_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import SOC2Controle, EvidenciaControle
        controle = SOC2Controle.objects.filter(empresa=empresa, id=controle_id).first()
        if not controle:
            return JsonResponse({"erro": "Controle não encontrado"}, status=404)

        if request.method == "POST":
            import json as _json
            data = _json.loads(request.body)
            ev = EvidenciaControle.objects.create(
                controle=controle,
                tipo=data.get("tipo", "documento"),
                titulo=data.get("titulo", ""),
                descricao=data.get("descricao", ""),
                arquivo_url=data.get("arquivo_url", ""),
                coletado_por=data.get("coletado_por", ""),
                valido_ate=data.get("valido_ate") or None,
            )
            return JsonResponse({"id": ev.id, "titulo": ev.titulo, "criado_em": ev.criado_em.isoformat()})

        evidencias = list(controle.evidencias.values(
            "id", "tipo", "titulo", "descricao", "arquivo_url",
            "coletado_por", "data_coleta", "valido_ate",
        ))
        return JsonResponse({"controle": controle.codigo, "evidencias": evidencias})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_rbac_permissoes(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import RBACPermissao, RBACAtribuicao
        permissoes = list(RBACPermissao.objects.values("id", "codigo", "descricao", "modulo"))
        atribuicoes = list(
            RBACAtribuicao.objects.filter(empresa=empresa, ativo=True)
            .values("usuario__email", "permissao__codigo", "concedido_por", "criado_em")
        )
        return JsonResponse({"permissoes": permissoes, "atribuicoes": atribuicoes})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_rbac_atribuir(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        import json as _json
        data = _json.loads(request.body)
        from .models import RBACPermissao, RBACAtribuicao, EmpresaUsuario
        permissao = RBACPermissao.objects.filter(codigo=data.get("permissao_codigo")).first()
        usuario = EmpresaUsuario.objects.filter(empresa=empresa, id=data.get("usuario_id")).first()
        if not permissao or not usuario:
            return JsonResponse({"erro": "Permissão ou usuário não encontrado"}, status=404)
        at, criado = RBACAtribuicao.objects.get_or_create(
            empresa=empresa, usuario=usuario, permissao=permissao,
            defaults={"concedido_por": data.get("concedido_por", "admin"), "ativo": True},
        )
        if not criado:
            at.ativo = True
            at.save(update_fields=["ativo", "atualizado_em"])
        return JsonResponse({"atribuido": True, "id": at.id})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def compliance_page(request):
    from django.shortcuts import render, redirect
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "compliance.html")
