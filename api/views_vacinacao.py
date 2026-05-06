import json
from datetime import date

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import CampanhaVacinacao, FuncionarioSST, RegistroVacinacao
from .views_dashboard import _empresa_autenticada


def _json_body(request):
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _campanha_to_dict(campanha, incluir_registros=False):
    hoje = date.today()
    cobertura = round(campanha.doses_aplicadas / campanha.meta_doses * 100, 1) if campanha.meta_doses else None
    data = {
        "id": campanha.id,
        "nome": campanha.nome,
        "vacina": campanha.vacina,
        "descricao": campanha.descricao,
        "data_inicio": str(campanha.data_inicio),
        "data_fim": str(campanha.data_fim) if campanha.data_fim else None,
        "meta_doses": campanha.meta_doses,
        "doses_aplicadas": campanha.doses_aplicadas,
        "cobertura_pct": cobertura,
        "local": campanha.local,
        "responsavel": campanha.responsavel,
        "status": campanha.status,
        "status_label": campanha.get_status_display(),
        "observacoes": campanha.observacoes,
        "em_andamento": campanha.status == "em_andamento",
        "encerrada": campanha.data_fim and campanha.data_fim < hoje,
        "criado_em": campanha.criado_em.strftime("%d/%m/%Y"),
    }
    if incluir_registros:
        data["registros"] = [
            _registro_to_dict(registro)
            for registro in campanha.registros.select_related("funcionario")
        ]
    return data


def _registro_to_dict(registro):
    return {
        "id": registro.id,
        "campanha_id": registro.campanha_id,
        "campanha_nome": registro.campanha.nome,
        "campanha_vacina": registro.campanha.vacina,
        "funcionario_id": registro.funcionario_id,
        "funcionario_nome": registro.funcionario.nome,
        "funcionario_cargo": registro.funcionario.cargo or "",
        "data_aplicacao": str(registro.data_aplicacao),
        "dose": registro.dose,
        "dose_label": registro.get_dose_display(),
        "lote_vacina": registro.lote_vacina,
        "aplicador": registro.aplicador,
        "observacoes": registro.observacoes,
    }


@csrf_exempt
def api_campanhas_vacinacao(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    if request.method == "GET":
        campanhas = CampanhaVacinacao.objects.filter(empresa=empresa)
        status = request.GET.get("status")
        if status:
            campanhas = campanhas.filter(status=status)
        incluir_registros = request.GET.get("registros") == "1"
        return JsonResponse({
            "campanhas": [_campanha_to_dict(campanha, incluir_registros) for campanha in campanhas],
        })

    if request.method == "POST":
        data = _json_body(request)
        if not data.get("nome"):
            return JsonResponse({"erro": "nome obrigatorio"}, status=400)
        if not data.get("vacina"):
            return JsonResponse({"erro": "vacina obrigatoria"}, status=400)
        if not data.get("data_inicio"):
            return JsonResponse({"erro": "data_inicio obrigatoria"}, status=400)

        campanha = CampanhaVacinacao.objects.create(
            empresa=empresa,
            nome=data["nome"],
            vacina=data["vacina"],
            descricao=data.get("descricao", ""),
            data_inicio=data["data_inicio"],
            data_fim=data.get("data_fim") or None,
            meta_doses=int(data.get("meta_doses", 0)),
            local=data.get("local", ""),
            responsavel=data.get("responsavel", ""),
            status=data.get("status", "planejada"),
            observacoes=data.get("observacoes", ""),
        )
        return JsonResponse({"campanha": _campanha_to_dict(campanha)}, status=201)

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


@csrf_exempt
def api_campanha_detalhe(request, campanha_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    try:
        campanha = CampanhaVacinacao.objects.get(id=campanha_id, empresa=empresa)
    except CampanhaVacinacao.DoesNotExist:
        return JsonResponse({"erro": "Campanha nao encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({"campanha": _campanha_to_dict(campanha, incluir_registros=True)})

    if request.method in ("PUT", "PATCH"):
        data = _json_body(request)
        campos = ["nome", "vacina", "descricao", "local", "responsavel", "status", "observacoes"]
        for campo in campos:
            if campo in data:
                setattr(campanha, campo, data[campo])
        for campo_data in ["data_inicio", "data_fim"]:
            if campo_data in data:
                setattr(campanha, campo_data, data[campo_data] or None)
        if "meta_doses" in data:
            campanha.meta_doses = int(data["meta_doses"] or 0)
        campanha.save()
        return JsonResponse({"campanha": _campanha_to_dict(campanha)})

    if request.method == "DELETE":
        campanha.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


@csrf_exempt
def api_registros_vacinacao(request, campanha_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    try:
        campanha = CampanhaVacinacao.objects.get(id=campanha_id, empresa=empresa)
    except CampanhaVacinacao.DoesNotExist:
        return JsonResponse({"erro": "Campanha nao encontrada"}, status=404)

    if request.method == "GET":
        registros = campanha.registros.select_related("funcionario")
        return JsonResponse({"registros": [_registro_to_dict(registro) for registro in registros]})

    if request.method == "POST":
        data = _json_body(request)
        if "registros" in data:
            criados = 0
            erros = []
            for item in data["registros"]:
                try:
                    funcionario = FuncionarioSST.objects.get(id=item["funcionario_id"], empresa=empresa)
                    _, created = RegistroVacinacao.objects.get_or_create(
                        campanha=campanha,
                        funcionario=funcionario,
                        dose=item.get("dose", "dose_unica"),
                        defaults={
                            "data_aplicacao": item.get("data_aplicacao", str(date.today())),
                            "lote_vacina": item.get("lote_vacina", ""),
                            "aplicador": item.get("aplicador", ""),
                            "observacoes": item.get("observacoes", ""),
                        },
                    )
                    if created:
                        criados += 1
                except Exception as exc:
                    erros.append(str(exc))
            campanha.doses_aplicadas = campanha.registros.count()
            campanha.save(update_fields=["doses_aplicadas"])
            return JsonResponse({"criados": criados, "erros": erros}, status=201)

        funcionario_id = data.get("funcionario_id")
        if not funcionario_id:
            return JsonResponse({"erro": "funcionario_id obrigatorio"}, status=400)

        try:
            funcionario = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)
        except FuncionarioSST.DoesNotExist:
            return JsonResponse({"erro": "Funcionario nao encontrado"}, status=404)

        registro, created = RegistroVacinacao.objects.get_or_create(
            campanha=campanha,
            funcionario=funcionario,
            dose=data.get("dose", "dose_unica"),
            defaults={
                "data_aplicacao": data.get("data_aplicacao", str(date.today())),
                "lote_vacina": data.get("lote_vacina", ""),
                "aplicador": data.get("aplicador", ""),
                "observacoes": data.get("observacoes", ""),
            },
        )
        if not created:
            registro.data_aplicacao = data.get("data_aplicacao", str(registro.data_aplicacao))
            registro.lote_vacina = data.get("lote_vacina", registro.lote_vacina)
            registro.aplicador = data.get("aplicador", registro.aplicador)
            registro.observacoes = data.get("observacoes", registro.observacoes)
            registro.save()

        campanha.doses_aplicadas = campanha.registros.count()
        campanha.save(update_fields=["doses_aplicadas"])
        return JsonResponse({"registro": _registro_to_dict(registro)}, status=201)

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


@csrf_exempt
def api_registro_vacinacao_detalhe(request, reg_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    try:
        registro = RegistroVacinacao.objects.get(id=reg_id, campanha__empresa=empresa)
    except RegistroVacinacao.DoesNotExist:
        return JsonResponse({"erro": "Registro nao encontrado"}, status=404)

    if request.method == "DELETE":
        campanha = registro.campanha
        registro.delete()
        campanha.doses_aplicadas = campanha.registros.count()
        campanha.save(update_fields=["doses_aplicadas"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "Metodo nao suportado"}, status=405)


def api_vacinacao_kpis(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Nao autenticado"}, status=401)

    campanhas = CampanhaVacinacao.objects.filter(empresa=empresa)
    total_funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
    total_doses = sum(campanha.doses_aplicadas for campanha in campanhas)
    cobertura_geral = round(total_doses / total_funcionarios * 100, 1) if total_funcionarios else 0
    vacinados_ids = RegistroVacinacao.objects.filter(campanha__empresa=empresa).values_list("funcionario_id", flat=True)
    sem_vacina = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).exclude(id__in=vacinados_ids).count()

    return JsonResponse({
        "kpis": {
            "total_campanhas": campanhas.count(),
            "campanhas_ativas": campanhas.filter(status="em_andamento").count(),
            "total_doses": total_doses,
            "cobertura_geral_pct": cobertura_geral,
            "funcionarios_sem_vacina": sem_vacina,
            "total_funcionarios": total_funcionarios,
        },
        "campanhas_recentes": [
            _campanha_to_dict(campanha)
            for campanha in campanhas.order_by("-data_inicio")[:5]
        ],
    })
