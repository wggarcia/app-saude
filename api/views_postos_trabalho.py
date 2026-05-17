"""
Postos de Trabalho e Agentes Nocivos — base para geração do S-2240 (eSocial).
Cada posto representa uma função/atividade com exposição a agentes nocivos (físicos,
químicos ou biológicos). Os funcionários são vinculados a postos para compor o
inventário de riscos exigido pelo S-2240.
"""
import json
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    PostoTrabalho, AgenteNocivoPostoTrabalho, FuncionarioPostoTrabalho,
    FuncionarioSST, ConfiguracaoSST,
)
from .views_dashboard import _empresa_autenticada
from .access_control import requer_setor


def _empresa(request):
    e = _empresa_autenticada(request)
    if not e:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)
    return e, None


def _posto_dict(p, incluir_agentes=False, incluir_func=False):
    d = {
        "id": p.id,
        "nome": p.nome,
        "setor": p.setor,
        "descricao": p.descricao,
        "responsavel_tecnico": p.responsavel_tecnico,
        "responsavel_registro": p.responsavel_registro,
        "data_laudo": p.data_laudo.isoformat() if p.data_laudo else None,
        "vigencia_inicio": p.vigencia_inicio,
        "ativo": p.ativo,
        "total_agentes": p.agentes_nocivos.count(),
        "total_funcionarios": p.funcionarios_vinculados.filter(data_fim__isnull=True).count(),
    }
    if incluir_agentes:
        d["agentes"] = [_agente_dict(a) for a in p.agentes_nocivos.all()]
    if incluir_func:
        d["funcionarios"] = [
            {
                "id": v.id,
                "funcionario_id": v.funcionario_id,
                "funcionario_nome": v.funcionario.nome,
                "funcionario_cpf": v.funcionario.cpf,
                "data_inicio": v.data_inicio.isoformat(),
                "data_fim": v.data_fim.isoformat() if v.data_fim else None,
                "ativo": v.data_fim is None,
            }
            for v in p.funcionarios_vinculados.select_related("funcionario").order_by("-data_inicio")
        ]
    return d


def _agente_dict(a):
    return {
        "id": a.id,
        "tipo_agente": a.tipo_agente,
        "tipo_agente_label": a.get_tipo_agente_display(),
        "cod_agente": a.cod_agente,
        "cod_agente_label": a.get_cod_agente_display(),
        "dsc_agente": a.dsc_agente,
        "tec_medicao": a.tec_medicao,
        "intensidade": a.intensidade,
        "limite_tolerancia": a.limite_tolerancia,
        "epc_descricao": a.epc_descricao,
        "epc_eficaz": a.epc_eficaz,
        "epi_descricao": a.epi_descricao,
        "epi_ca": a.epi_ca,
        "epi_eficaz": a.epi_eficaz,
    }


# ── Página ─────────────────────────────────────────────────────────────────────

@requer_setor("empresa")
def sst_postos_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    return render(request, "sst_postos_trabalho.html", {"empresa_nome": empresa.nome})


# ── CRUD Postos ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_postos_trabalho(request):
    empresa, err = _empresa(request)
    if err:
        return err

    if request.method == "GET":
        qs = PostoTrabalho.objects.filter(empresa=empresa).prefetch_related("agentes_nocivos", "funcionarios_vinculados")
        apenas_ativos = request.GET.get("ativo", "").lower() != "false"
        if apenas_ativos:
            qs = qs.filter(ativo=True)
        return JsonResponse({"postos": [_posto_dict(p) for p in qs]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = (data.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Nome do posto é obrigatório"}, status=400)
        from datetime import date as ddate
        def parse_date(s):
            try:
                from datetime import datetime
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        posto = PostoTrabalho.objects.create(
            empresa=empresa,
            nome=nome,
            setor=data.get("setor", ""),
            descricao=data.get("descricao", ""),
            responsavel_tecnico=data.get("responsavel_tecnico", ""),
            responsavel_registro=data.get("responsavel_registro", ""),
            data_laudo=parse_date(data.get("data_laudo")),
            vigencia_inicio=data.get("vigencia_inicio", ""),
        )
        return JsonResponse(_posto_dict(posto), status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_posto_detalhe(request, posto_id):
    empresa, err = _empresa(request)
    if err:
        return err

    posto = PostoTrabalho.objects.filter(id=posto_id, empresa=empresa).prefetch_related(
        "agentes_nocivos", "funcionarios_vinculados__funcionario"
    ).first()
    if not posto:
        return JsonResponse({"erro": "Posto não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_posto_dict(posto, incluir_agentes=True, incluir_func=True))

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        def parse_date(s):
            try:
                from datetime import datetime
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None
        campos = ["nome", "setor", "descricao", "responsavel_tecnico", "responsavel_registro", "vigencia_inicio"]
        for c in campos:
            if c in data:
                setattr(posto, c, data[c])
        if "data_laudo" in data:
            posto.data_laudo = parse_date(data["data_laudo"])
        if "ativo" in data:
            posto.ativo = bool(data["ativo"])
        posto.save()
        return JsonResponse(_posto_dict(posto, incluir_agentes=True))

    if request.method == "DELETE":
        posto.delete()
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── CRUD Agentes Nocivos ────────────────────────────────────────────────────────

@csrf_exempt
def api_agentes_nocivos(request, posto_id):
    empresa, err = _empresa(request)
    if err:
        return err

    posto = PostoTrabalho.objects.filter(id=posto_id, empresa=empresa).first()
    if not posto:
        return JsonResponse({"erro": "Posto não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse({"agentes": [_agente_dict(a) for a in posto.agentes_nocivos.all()]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        cod = (data.get("cod_agente") or "").strip()
        if not cod:
            return JsonResponse({"erro": "Código do agente é obrigatório"}, status=400)
        agente = AgenteNocivoPostoTrabalho.objects.create(
            posto=posto,
            tipo_agente=data.get("tipo_agente", "fisico"),
            cod_agente=cod,
            dsc_agente=data.get("dsc_agente", ""),
            tec_medicao=data.get("tec_medicao", ""),
            intensidade=data.get("intensidade", ""),
            limite_tolerancia=data.get("limite_tolerancia", ""),
            epc_descricao=data.get("epc_descricao", ""),
            epc_eficaz=bool(data.get("epc_eficaz", False)),
            epi_descricao=data.get("epi_descricao", ""),
            epi_ca=data.get("epi_ca", ""),
            epi_eficaz=bool(data.get("epi_eficaz", False)),
        )
        return JsonResponse(_agente_dict(agente), status=201)

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_agente_detalhe(request, posto_id, agente_id):
    empresa, err = _empresa(request)
    if err:
        return err

    agente = AgenteNocivoPostoTrabalho.objects.filter(
        id=agente_id, posto__id=posto_id, posto__empresa=empresa
    ).first()
    if not agente:
        return JsonResponse({"erro": "Agente não encontrado"}, status=404)

    if request.method == "DELETE":
        agente.delete()
        return JsonResponse({"ok": True})

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        campos = ["tipo_agente", "cod_agente", "dsc_agente", "tec_medicao", "intensidade",
                  "limite_tolerancia", "epc_descricao", "epi_descricao", "epi_ca"]
        for c in campos:
            if c in data:
                setattr(agente, c, data[c])
        if "epc_eficaz" in data:
            agente.epc_eficaz = bool(data["epc_eficaz"])
        if "epi_eficaz" in data:
            agente.epi_eficaz = bool(data["epi_eficaz"])
        agente.save()
        return JsonResponse(_agente_dict(agente))

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Vínculo Funcionário ↔ Posto ─────────────────────────────────────────────────

@csrf_exempt
def api_posto_funcionarios(request, posto_id):
    empresa, err = _empresa(request)
    if err:
        return err

    posto = PostoTrabalho.objects.filter(id=posto_id, empresa=empresa).first()
    if not posto:
        return JsonResponse({"erro": "Posto não encontrado"}, status=404)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        func_id = data.get("funcionario_id")
        if not func_id:
            return JsonResponse({"erro": "funcionario_id é obrigatório"}, status=400)
        func = FuncionarioSST.objects.filter(id=func_id, empresa=empresa).first()
        if not func:
            return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
        from datetime import date
        def parse_date(s):
            try:
                from datetime import datetime
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return date.today()
        vinculo, criado = FuncionarioPostoTrabalho.objects.get_or_create(
            funcionario=func, posto=posto, data_fim__isnull=True,
            defaults={"data_inicio": parse_date(data.get("data_inicio"))}
        )
        return JsonResponse({"id": vinculo.id, "criado": criado}, status=201 if criado else 200)

    if request.method == "DELETE":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        vinculo_id = data.get("vinculo_id")
        FuncionarioPostoTrabalho.objects.filter(id=vinculo_id, posto=posto).update(
            data_fim=timezone.now().date()
        )
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Gerar XML S-2240 ────────────────────────────────────────────────────────────

def api_posto_xml_s2240(request, posto_id):
    empresa, err = _empresa(request)
    if err:
        return err

    posto = PostoTrabalho.objects.filter(id=posto_id, empresa=empresa).prefetch_related(
        "agentes_nocivos", "funcionarios_vinculados__funcionario"
    ).first()
    if not posto:
        return JsonResponse({"erro": "Posto não encontrado"}, status=404)

    agentes = posto.agentes_nocivos.count()
    if agentes == 0:
        return JsonResponse({"erro": "Cadastre pelo menos um agente nocivo antes de gerar o S-2240"}, status=400)

    func_ativos = posto.funcionarios_vinculados.filter(data_fim__isnull=True).count()
    if func_ativos == 0:
        return JsonResponse({"erro": "Vincule pelo menos um funcionário ao posto antes de gerar o S-2240"}, status=400)

    cfg = ConfiguracaoSST.objects.filter(empresa=empresa).first()
    periodo = request.GET.get("periodo") or timezone.now().strftime("%Y-%m")

    from .views_esocial_sst import _gerar_xml_s2240
    xml = _gerar_xml_s2240(empresa, cfg, periodo=periodo, posto=posto)

    return JsonResponse({"xml": xml, "posto": posto.nome, "periodo": periodo})
