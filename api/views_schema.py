"""
Schema Registry — contratos de dados versionados, validação de payload.
Endpoint: GET  /api/schema/contratos
          POST /api/schema/contratos
          GET  /api/schema/contratos/<id>
          GET  /api/schema/contratos/<id>/versoes
          POST /api/schema/contratos/<id>/versoes
          POST /api/schema/validar
Page:     GET  /schema-registry/
"""
import json
from datetime import date
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .views_dashboard import _empresa_autenticada


def _schema_to_dict(s, include_versoes=False):
    d = {
        "id": s.id,
        "nome": s.nome,
        "dominio": s.dominio,
        "descricao": s.descricao,
        "owner_equipe": s.owner_equipe,
        "compatibilidade": s.compatibilidade,
        "ativo": s.ativo,
        "total_versoes": s.versoes.count(),
        "criado_em": s.criado_em.strftime("%d/%m/%Y"),
        "atualizado_em": s.atualizado_em.strftime("%d/%m/%Y"),
    }
    if include_versoes:
        d["versoes"] = [_versao_to_dict(v) for v in s.versoes.all()]
    return d


def _versao_to_dict(v):
    return {
        "id": v.id,
        "versao": v.versao,
        "status": v.status,
        "schema_json": v.schema_json,
        "exemplo_payload": v.exemplo_payload,
        "changelog": v.changelog,
        "publicado_em": v.publicado_em.strftime("%d/%m/%Y") if v.publicado_em else None,
        "criado_em": v.criado_em.strftime("%d/%m/%Y"),
    }


def _validar_payload_contra_schema(payload, schema_json):
    """Validação básica de JSON Schema sem biblioteca externa."""
    erros = []
    required = schema_json.get("required", [])
    properties = schema_json.get("properties", {})

    for campo in required:
        if campo not in payload:
            erros.append(f"Campo obrigatório ausente: '{campo}'")

    for campo, spec in properties.items():
        if campo not in payload:
            continue
        valor = payload[campo]
        tipo_esperado = spec.get("type")
        if tipo_esperado:
            mapa = {
                "string": str, "integer": int, "number": (int, float),
                "boolean": bool, "array": list, "object": dict,
            }
            tipos = mapa.get(tipo_esperado)
            if tipos and not isinstance(valor, tipos):
                erros.append(f"'{campo}': esperado {tipo_esperado}, recebido {type(valor).__name__}")
        if "minLength" in spec and isinstance(valor, str) and len(valor) < spec["minLength"]:
            erros.append(f"'{campo}': comprimento mínimo {spec['minLength']}")
        if "maxLength" in spec and isinstance(valor, str) and len(valor) > spec["maxLength"]:
            erros.append(f"'{campo}': comprimento máximo {spec['maxLength']}")
        if "minimum" in spec and isinstance(valor, (int, float)) and valor < spec["minimum"]:
            erros.append(f"'{campo}': valor mínimo {spec['minimum']}")
        if "maximum" in spec and isinstance(valor, (int, float)) and valor > spec["maximum"]:
            erros.append(f"'{campo}': valor máximo {spec['maximum']}")
        if "enum" in spec and valor not in spec["enum"]:
            erros.append(f"'{campo}': deve ser um de {spec['enum']}")

    return erros


def api_schema_contratos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
            from .models import SchemaContrato
            sc = SchemaContrato.objects.create(
                empresa=empresa,
                nome=body.get("nome", "").strip(),
                dominio=body.get("dominio", "").strip(),
                descricao=body.get("descricao", ""),
                owner_equipe=body.get("owner_equipe", ""),
                compatibilidade=body.get("compatibilidade", "backward"),
            )
            return JsonResponse(_schema_to_dict(sc), status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    try:
        from .models import SchemaContrato
        dominio_q = request.GET.get("dominio", "").strip()
        qs = SchemaContrato.objects.filter(empresa=empresa, ativo=True).prefetch_related("versoes")
        if dominio_q:
            qs = qs.filter(dominio__icontains=dominio_q)

        dominios = list(qs.values_list("dominio", flat=True).distinct())
        return JsonResponse({
            "total": qs.count(),
            "dominios": sorted(set(dominios)),
            "contratos": [_schema_to_dict(s) for s in qs],
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def api_schema_contrato_detalhe(request, contrato_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import SchemaContrato
        sc = SchemaContrato.objects.prefetch_related("versoes").get(id=contrato_id, empresa=empresa)
        return JsonResponse(_schema_to_dict(sc, include_versoes=True))
    except SchemaContrato.DoesNotExist:
        return JsonResponse({"erro": "Contrato não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@csrf_exempt
def api_schema_versoes(request, contrato_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        from .models import SchemaContrato, VersaoSchema
        sc = SchemaContrato.objects.get(id=contrato_id, empresa=empresa)
    except SchemaContrato.DoesNotExist:
        return JsonResponse({"erro": "Contrato não encontrado"}, status=404)

    if request.method == "POST":
        try:
            body = json.loads(request.body)
            ultima = sc.versoes.first()
            nova_versao_num = (ultima.versao + 1) if ultima else 1
            status = body.get("status", "rascunho")
            v = VersaoSchema.objects.create(
                schema=sc,
                versao=nova_versao_num,
                schema_json=body.get("schema_json", {}),
                exemplo_payload=body.get("exemplo_payload", {}),
                changelog=body.get("changelog", ""),
                status=status,
                publicado_em=timezone.now() if status == "publicado" else None,
            )
            return JsonResponse(_versao_to_dict(v), status=201)
        except Exception as e:
            return JsonResponse({"erro": str(e)}, status=500)

    versoes = sc.versoes.all()
    return JsonResponse({"versoes": [_versao_to_dict(v) for v in versoes]})


@csrf_exempt
def api_schema_validar(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    try:
        body = json.loads(request.body)
        nome_contrato = body.get("contrato", "").strip()
        versao_num = body.get("versao")
        payload = body.get("payload", {})
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    try:
        from .models import SchemaContrato, VersaoSchema
        sc = SchemaContrato.objects.get(nome=nome_contrato, empresa=empresa)
        if versao_num:
            versao = VersaoSchema.objects.get(schema=sc, versao=versao_num)
        else:
            versao = sc.versoes.filter(status="publicado").first()
            if not versao:
                versao = sc.versoes.first()

        if not versao:
            return JsonResponse({"erro": "Nenhuma versão disponível para este contrato"}, status=404)

        erros = _validar_payload_contra_schema(payload, versao.schema_json)
        return JsonResponse({
            "valido": len(erros) == 0,
            "contrato": sc.nome,
            "versao": versao.versao,
            "erros": erros,
            "total_erros": len(erros),
        })
    except SchemaContrato.DoesNotExist:
        return JsonResponse({"erro": f"Contrato '{nome_contrato}' não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def _criar_schemas_padrao(empresa):
    """Semeia schemas padrão da plataforma para uma empresa."""
    from .models import SchemaContrato, VersaoSchema

    schemas_padrao = [
        {
            "nome": "sst.exame.vencido",
            "dominio": "sst",
            "descricao": "Exame médico ocupacional vencido",
            "owner_equipe": "SST",
            "schema_json": {
                "type": "object",
                "required": ["funcionario_id", "tipo_exame", "vencimento"],
                "properties": {
                    "funcionario_id": {"type": "integer"},
                    "tipo_exame": {"type": "string", "enum": ["admissional", "periodico", "demissional", "retorno", "mudanca_funcao"]},
                    "vencimento": {"type": "string", "minLength": 10},
                    "dias_vencido": {"type": "integer", "minimum": 0},
                },
            },
            "exemplo_payload": {"funcionario_id": 42, "tipo_exame": "periodico", "vencimento": "2024-01-15", "dias_vencido": 30},
        },
        {
            "nome": "farmacia.lote.vencendo",
            "dominio": "farmacia",
            "descricao": "Lote de medicamento próximo ao vencimento",
            "owner_equipe": "Farmácia",
            "schema_json": {
                "type": "object",
                "required": ["lote_id", "medicamento", "validade", "quantidade"],
                "properties": {
                    "lote_id": {"type": "integer"},
                    "medicamento": {"type": "string"},
                    "validade": {"type": "string"},
                    "quantidade": {"type": "number", "minimum": 0},
                    "dias_para_vencer": {"type": "integer"},
                },
            },
            "exemplo_payload": {"lote_id": 7, "medicamento": "Dipirona 500mg", "validade": "2024-02-28", "quantidade": 50, "dias_para_vencer": 14},
        },
        {
            "nome": "saude.burnout.alerta",
            "dominio": "saude_ocupacional",
            "descricao": "Risco elevado de burnout detectado por IA",
            "owner_equipe": "Saúde Ocupacional",
            "schema_json": {
                "type": "object",
                "required": ["empresa_id", "score_burnout", "periodo"],
                "properties": {
                    "empresa_id": {"type": "integer"},
                    "score_burnout": {"type": "number", "minimum": 0, "maximum": 5},
                    "periodo": {"type": "string"},
                    "total_colaboradores": {"type": "integer"},
                },
            },
            "exemplo_payload": {"empresa_id": 1, "score_burnout": 3.8, "periodo": "2024-01", "total_colaboradores": 120},
        },
        {
            "nome": "hospital.leito.ocupacao_critica",
            "dominio": "hospital",
            "descricao": "Taxa de ocupação hospitalar acima do limiar crítico",
            "owner_equipe": "Hospital",
            "schema_json": {
                "type": "object",
                "required": ["taxa_ocupacao", "leitos_total", "leitos_ocupados"],
                "properties": {
                    "taxa_ocupacao": {"type": "number", "minimum": 0, "maximum": 100},
                    "leitos_total": {"type": "integer"},
                    "leitos_ocupados": {"type": "integer"},
                    "limiar_critico": {"type": "number"},
                },
            },
            "exemplo_payload": {"taxa_ocupacao": 95.5, "leitos_total": 20, "leitos_ocupados": 19, "limiar_critico": 85},
        },
    ]

    criados = 0
    for s in schemas_padrao:
        sc, created = SchemaContrato.objects.get_or_create(
            empresa=empresa,
            nome=s["nome"],
            defaults={
                "dominio": s["dominio"],
                "descricao": s["descricao"],
                "owner_equipe": s["owner_equipe"],
                "compatibilidade": "backward",
            },
        )
        if created:
            VersaoSchema.objects.create(
                schema=sc,
                versao=1,
                schema_json=s["schema_json"],
                exemplo_payload=s["exemplo_payload"],
                status="publicado",
                publicado_em=timezone.now(),
                changelog="Versão inicial do schema padrão da plataforma",
            )
            criados += 1
    return criados


def api_schema_seed(request):
    """Semeia schemas padrão para a empresa autenticada."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    try:
        criados = _criar_schemas_padrao(empresa)
        return JsonResponse({"criados": criados, "mensagem": f"{criados} schema(s) padrão criados"})
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


def schema_registry_page(request):
    from django.shortcuts import render
    return render(request, "schema_registry.html")
