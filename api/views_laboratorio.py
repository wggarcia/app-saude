"""
Integração com Laboratórios — SolusCRT SST
Resultados de exames importados diretamente na plataforma.
Suporte a: HL7, FHIR, CSV, API REST parceiros.

Endpoints:
  GET  /api/sst/laboratorios/                          — lista laboratórios integrados
  POST /api/sst/laboratorios/registrar/                — cadastrar laboratório parceiro
  POST /api/sst/laboratorios/resultado/                — importar resultado de exame
  POST /api/sst/laboratorios/resultado/lote/           — importar lote CSV
  GET  /api/sst/laboratorios/resultados/               — listar resultados da empresa
  GET  /api/sst/laboratorios/resultados/<func_id>/     — resultados por funcionário
  GET  /api/sst/laboratorios/alertas/                  — resultados alterados
  GET  /api/sst/laboratorios/kpis/                     — painel de integração
"""
from datetime import date, timedelta
from django.http import JsonResponse
import json, csv, io


def _empresa(request):
    return getattr(request, "empresa", None)


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


EXAMES_PADRAO_SST = [
    "Hemograma completo", "Glicemia em jejum", "Colesterol total e frações",
    "Triglicerídeos", "Ureia e creatinina", "TGO / TGP (transaminases)",
    "Ácido úrico", "TSH / T4 livre", "EAS (urina tipo I)",
    "Audiometria tonal", "Espirometria", "Acuidade visual",
    "Eletrocardiograma", "Rx tórax PA", "Toxicológico urinário ampliado",
    "Colinesterase eritrocitária", "Chumbo sérico", "Benzeno urinário (ácido S-fenilmercaptúrico)",
    "Psicossocial (Hamilton/PHQ-9)", "Ergonômico funcional",
]


def _resultado_dict(r):
    return {
        "id": r.id,
        "funcionario_id": r.funcionario_id,
        "funcionario_nome": r.funcionario.nome,
        "laboratorio_nome": r.laboratorio_nome,
        "laboratorio_id": r.laboratorio_id,
        "exame": r.exame,
        "data_coleta": str(r.data_coleta),
        "data_resultado": str(r.data_resultado or ""),
        "resultado": r.resultado,
        "unidade": r.unidade,
        "valor_referencia": r.valor_referencia,
        "alterado": r.alterado,
        "criticidade": r.criticidade,        # normal / atencao / critico
        "medico_responsavel": r.medico_responsavel,
        "importado_via": r.importado_via,    # api / csv / manual / hl7 / fhir
        "vinculado_aso": r.vinculado_aso_id is not None,
        "vinculado_aso_id": r.vinculado_aso_id,
        "observacoes": r.observacoes,
        "criado_em": str(r.criado_em.date()),
    }


def _lab_dict(lab):
    return {
        "id": lab.id,
        "nome": lab.nome,
        "cnpj": lab.cnpj,
        "cidade": lab.cidade,
        "uf": lab.uf,
        "tipo_integracao": lab.tipo_integracao,  # api / hl7 / fhir / csv / manual
        "endpoint_api": lab.endpoint_api,
        "ativo": lab.ativo,
        "total_resultados_enviados": lab.total_resultados_enviados,
        "ultima_sincronizacao": str(lab.ultima_sincronizacao or ""),
    }


# ──────────────────────────────────────────────
# LABORATÓRIOS
# ──────────────────────────────────────────────

def api_laboratorios_lista(request):
    try:
        from .models import LaboratorioIntegrado
        qs = LaboratorioIntegrado.objects.filter(ativo=True)
        empresa = _empresa(request)
        if empresa:
            qs = qs.filter(empresas_vinculadas=empresa)
        return JsonResponse({"total": qs.count(), "laboratorios": [_lab_dict(l) for l in qs]})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_laboratorio_registrar(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    data = _json(request)
    campos_obrig = ["nome", "cnpj", "tipo_integracao"]
    for c in campos_obrig:
        if not data.get(c):
            return JsonResponse({"erro": f"Campo obrigatório: {c}"}, status=400)
    try:
        from .models import LaboratorioIntegrado
        lab, criado = LaboratorioIntegrado.objects.get_or_create(
            cnpj=data["cnpj"],
            defaults={
                "nome": data["nome"],
                "cidade": data.get("cidade", ""),
                "uf": data.get("uf", ""),
                "tipo_integracao": data["tipo_integracao"],
                "endpoint_api": data.get("endpoint_api", ""),
                "token_api": data.get("token_api", ""),
                "ativo": True,
                "total_resultados_enviados": 0,
            }
        )
        empresa = _empresa(request)
        if empresa and criado:
            lab.empresas_vinculadas.add(empresa)
        return JsonResponse({"sucesso": True, "id": lab.id, "criado": criado}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


# ──────────────────────────────────────────────
# RESULTADOS
# ──────────────────────────────────────────────

def _determinar_criticidade(resultado_str, valor_ref_str):
    """Heurística simples de criticidade."""
    if not resultado_str or not valor_ref_str:
        return "normal"
    res_lower = resultado_str.lower()
    if any(k in res_lower for k in ["critico", "crítico", "alto risco", "indetectável"]):
        return "critico"
    if any(k in res_lower for k in ["alterado", "aumentado", "diminuído", "anormal", "elevado"]):
        return "atencao"
    return "normal"


def api_resultado_importar(request):
    """Importa um único resultado de exame laboratorial."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    data = _json(request)

    campos_obrig = ["funcionario_id", "exame", "resultado", "data_coleta", "laboratorio_nome"]
    for c in campos_obrig:
        if not data.get(c):
            return JsonResponse({"erro": f"Campo obrigatório: {c}"}, status=400)
    try:
        from .models import FuncionarioSST, ResultadoExameLaboratorio, LaboratorioIntegrado
        func = FuncionarioSST.objects.get(id=data["funcionario_id"], empresa=empresa)

        lab = None
        if data.get("laboratorio_id"):
            lab = LaboratorioIntegrado.objects.filter(id=data["laboratorio_id"]).first()

        alterado = data.get("alterado", False)
        criticidade = data.get("criticidade") or _determinar_criticidade(
            data["resultado"], data.get("valor_referencia", "")
        )

        resultado = ResultadoExameLaboratorio.objects.create(
            empresa=empresa,
            funcionario=func,
            laboratorio=lab,
            laboratorio_nome=data["laboratorio_nome"],
            exame=data["exame"],
            data_coleta=data["data_coleta"],
            data_resultado=data.get("data_resultado") or date.today(),
            resultado=data["resultado"],
            unidade=data.get("unidade", ""),
            valor_referencia=data.get("valor_referencia", ""),
            alterado=alterado,
            criticidade=criticidade,
            medico_responsavel=data.get("medico_responsavel", ""),
            importado_via=data.get("importado_via", "manual"),
            vinculado_aso_id=data.get("vinculado_aso_id"),
            observacoes=data.get("observacoes", ""),
        )

        # Atualiza contador do laboratório
        if lab:
            lab.total_resultados_enviados += 1
            lab.ultima_sincronizacao = date.today()
            lab.save(update_fields=["total_resultados_enviados", "ultima_sincronizacao"])

        return JsonResponse({"sucesso": True, "resultado": _resultado_dict(resultado)}, status=201)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_resultado_lote_csv(request):
    """Importa resultados em lote via CSV.
    Colunas esperadas: funcionario_cpf, exame, resultado, unidade, valor_referencia,
                       data_coleta, laboratorio_nome, alterado, medico_responsavel
    """
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        from .models import FuncionarioSST, ResultadoExameLaboratorio
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return JsonResponse({"erro": "Envie o arquivo CSV no campo 'arquivo'"}, status=400)

        conteudo = arquivo.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(conteudo))
        importados, erros = 0, []

        for i, row in enumerate(reader, 1):
            try:
                cpf = row.get("funcionario_cpf", "").strip()
                func = FuncionarioSST.objects.filter(empresa=empresa, cpf=cpf).first()
                if not func:
                    erros.append(f"Linha {i}: CPF {cpf} não encontrado")
                    continue

                alterado = str(row.get("alterado", "0")).strip().lower() in ("1", "sim", "true", "s")
                ResultadoExameLaboratorio.objects.create(
                    empresa=empresa,
                    funcionario=func,
                    laboratorio_nome=row.get("laboratorio_nome", "Importação CSV"),
                    exame=row.get("exame", ""),
                    data_coleta=row.get("data_coleta") or str(date.today()),
                    resultado=row.get("resultado", ""),
                    unidade=row.get("unidade", ""),
                    valor_referencia=row.get("valor_referencia", ""),
                    alterado=alterado,
                    criticidade=_determinar_criticidade(row.get("resultado", ""), row.get("valor_referencia", "")),
                    medico_responsavel=row.get("medico_responsavel", ""),
                    importado_via="csv",
                )
                importados += 1
            except Exception as ex:
                erros.append(f"Linha {i}: {ex}")

        return JsonResponse({
            "sucesso": True,
            "importados": importados,
            "erros": erros,
            "total_linhas": importados + len(erros),
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_resultados_empresa(request):
    """Lista resultados de exames da empresa com filtros."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import ResultadoExameLaboratorio
        qs = ResultadoExameLaboratorio.objects.filter(empresa=empresa).select_related("funcionario")

        func_id = request.GET.get("funcionario_id")
        if func_id:
            qs = qs.filter(funcionario_id=func_id)

        exame = request.GET.get("exame")
        if exame:
            qs = qs.filter(exame__icontains=exame)

        alterado = request.GET.get("alterado")
        if alterado == "true":
            qs = qs.filter(alterado=True)

        criticidade = request.GET.get("criticidade")
        if criticidade:
            qs = qs.filter(criticidade=criticidade)

        desde = request.GET.get("desde")
        if desde:
            qs = qs.filter(data_coleta__gte=desde)

        return JsonResponse({
            "total": qs.count(),
            "resultados": [_resultado_dict(r) for r in qs.order_by("-data_coleta")[:500]],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_resultados_funcionario(request, funcionario_id):
    """Todos os resultados de um funcionário específico."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import ResultadoExameLaboratorio, FuncionarioSST
        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)
        qs = ResultadoExameLaboratorio.objects.filter(funcionario=func).order_by("-data_coleta")
        return JsonResponse({
            "funcionario": {"id": func.id, "nome": func.nome, "cpf": func.cpf, "cargo": func.cargo},
            "total_exames": qs.count(),
            "alterados": qs.filter(alterado=True).count(),
            "resultados": [_resultado_dict(r) for r in qs[:200]],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=404)


def api_resultados_alertas(request):
    """Resultados alterados ou críticos — painel de atenção médica."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import ResultadoExameLaboratorio
        hoje = date.today()
        janela = hoje - timedelta(days=90)

        criticos = ResultadoExameLaboratorio.objects.filter(
            empresa=empresa, criticidade="critico", data_coleta__gte=janela
        ).select_related("funcionario")

        atencao = ResultadoExameLaboratorio.objects.filter(
            empresa=empresa, criticidade="atencao", data_coleta__gte=janela
        ).select_related("funcionario")

        return JsonResponse({
            "periodo": "últimos 90 dias",
            "criticos": {
                "total": criticos.count(),
                "resultados": [_resultado_dict(r) for r in criticos[:50]],
            },
            "atencao": {
                "total": atencao.count(),
                "resultados": [_resultado_dict(r) for r in atencao[:50]],
            },
            "recomendacao": "Encaminhe resultados críticos ao médico do trabalho em até 24h." if criticos.count() > 0 else "Nenhum resultado crítico no período.",
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_laboratorio_kpis(request):
    """Painel de integração laboratorial."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    try:
        from .models import ResultadoExameLaboratorio, LaboratorioIntegrado, FuncionarioSST
        hoje = date.today()
        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        resultados = ResultadoExameLaboratorio.objects.filter(empresa=empresa)
        total_res = resultados.count()
        func_com_exame = resultados.values("funcionario").distinct().count()
        sem_exame = total_func - func_com_exame
        alterados = resultados.filter(alterado=True).count()
        criticos = resultados.filter(criticidade="critico").count()

        # Exames mais realizados
        from django.db.models import Count
        top_exames = list(
            resultados.values("exame").annotate(total=Count("id")).order_by("-total")[:10]
        )

        return JsonResponse({
            "total_funcionarios": total_func,
            "funcionarios_com_exame": func_com_exame,
            "funcionarios_sem_exame_laboratorial": sem_exame,
            "cobertura_pct": round(func_com_exame / total_func * 100, 1) if total_func > 0 else 0,
            "total_resultados": total_res,
            "resultados_alterados": alterados,
            "resultados_criticos": criticos,
            "top_exames": top_exames,
            "exames_padrao_sst": EXAMES_PADRAO_SST,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)
