"""
Portal do Funcionário — SST
Autenticação via CPF + data de nascimento.
Funcionário vê apenas seus próprios dados.
"""
import jwt
import json
import secrets
from datetime import timedelta
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import FuncionarioSST, ASOOcupacional, TreinamentoNR, EPIEntrega


# ── helpers ────────────────────────────────────────────────────────────────

def _token_funcionario(funcionario):
    payload = {
        "funcionario_id": funcionario.id,
        "empresa_id": funcionario.empresa_id,
        "iat": int(timezone.now().timestamp()),
        "exp": int((timezone.now() + timedelta(days=30)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def _autenticar_funcionario(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return FuncionarioSST.objects.select_related("empresa").get(
            id=data["funcionario_id"],
            empresa_id=data["empresa_id"],
            ativo=True,
        )
    except Exception:
        return None


def _cpf_limpo(cpf):
    return "".join(c for c in (cpf or "") if c.isdigit())


# ── login ──────────────────────────────────────────────────────────────────

@csrf_exempt
def funcionario_login(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cpf = _cpf_limpo(dados.get("cpf", ""))
    nascimento = dados.get("data_nascimento", "")  # YYYY-MM-DD

    if not cpf or not nascimento:
        return JsonResponse({"erro": "CPF e data de nascimento obrigatórios"}, status=400)

    # busca pelo CPF (pode existir em mais de uma empresa; retorna o mais recente ativo)
    func = (
        FuncionarioSST.objects
        .filter(cpf__icontains=cpf, ativo=True)
        .select_related("empresa")
        .order_by("-criado_em")
        .first()
    )

    if not func:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

    if not func.data_nascimento:
        return JsonResponse({"erro": "Data de nascimento não cadastrada. Solicite ao RH."}, status=400)

    if str(func.data_nascimento) != nascimento:
        return JsonResponse({"erro": "Data de nascimento incorreta"}, status=401)

    token = _token_funcionario(func)
    return JsonResponse({
        "status": "ok",
        "token": token,
        "funcionario_id": func.id,
        "nome": func.nome,
        "cargo": func.cargo,
        "empresa_nome": func.empresa.nome,
    })


# ── perfil ─────────────────────────────────────────────────────────────────

def funcionario_meu_perfil(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    return JsonResponse({
        "id": func.id,
        "nome": func.nome,
        "cpf": func.cpf,
        "matricula": func.matricula,
        "cargo": func.cargo,
        "setor": func.setor,
        "sexo": func.sexo,
        "data_nascimento": str(func.data_nascimento) if func.data_nascimento else None,
        "data_admissao": str(func.data_admissao) if func.data_admissao else None,
        "classe_risco": func.classe_risco,
        "empresa_nome": func.empresa.nome,
    })


# ── meus ASOs ──────────────────────────────────────────────────────────────

def funcionario_meus_asos(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    asos = ASOOcupacional.objects.filter(
        funcionario=func, empresa=func.empresa
    ).order_by("-data_emissao")

    hoje = timezone.now().date()

    def aso_dict(a):
        vencido = a.data_validade and a.data_validade < hoje
        dias_vencer = (a.data_validade - hoje).days if a.data_validade else None
        return {
            "id": a.id,
            "tipo": a.tipo,
            "tipo_display": a.get_tipo_display(),
            "data_emissao": str(a.data_emissao),
            "data_validade": str(a.data_validade) if a.data_validade else None,
            "resultado": a.resultado,
            "resultado_display": a.get_resultado_display(),
            "medico_responsavel": a.medico_responsavel,
            "crm": a.crm,
            "restricoes": a.restricoes,
            "vencido": vencido,
            "dias_vencer": dias_vencer,
        }

    return JsonResponse({"asos": [aso_dict(a) for a in asos]})


# ── meus treinamentos ──────────────────────────────────────────────────────

def funcionario_meus_treinamentos(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    treinamentos = TreinamentoNR.objects.filter(
        funcionarios=func, empresa=func.empresa
    ).order_by("-data_realizacao")

    hoje = timezone.now().date()

    def t_dict(t):
        vencido = t.data_vencimento and t.data_vencimento < hoje
        return {
            "id": t.id,
            "nr": t.nr,
            "titulo": t.titulo,
            "carga_horaria": t.carga_horaria,
            "data_realizacao": str(t.data_realizacao) if t.data_realizacao else None,
            "data_vencimento": str(t.data_vencimento) if t.data_vencimento else None,
            "instrutor": t.instrutor,
            "local": t.local,
            "status": t.status,
            "vencido": vencido,
        }

    return JsonResponse({"treinamentos": [t_dict(t) for t in treinamentos]})


# ── meus EPIs ──────────────────────────────────────────────────────────────

def funcionario_meus_epis(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    try:
        entregas = EPIEntrega.objects.filter(
            funcionario=func
        ).select_related("item_epi").order_by("-data_entrega")

        def e_dict(e):
            return {
                "id": e.id,
                "epi_nome": e.item_epi.nome if e.item_epi else e.descricao_livre,
                "ca": e.item_epi.ca if e.item_epi else "",
                "quantidade": float(e.quantidade),
                "data_entrega": str(e.data_entrega),
                "data_devolucao": str(e.data_devolucao) if e.data_devolucao else None,
                "devolvido": bool(e.data_devolucao),
            }
        return JsonResponse({"epis": [e_dict(e) for e in entregas]})
    except Exception:
        return JsonResponse({"epis": []})


# ── dashboard resumo ───────────────────────────────────────────────────────

def funcionario_dashboard(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    hoje = timezone.now().date()

    # ASO mais recente
    aso = ASOOcupacional.objects.filter(
        funcionario=func, empresa=func.empresa
    ).order_by("-data_emissao").first()

    aso_status = "sem_aso"
    aso_validade = None
    aso_dias = None
    if aso:
        aso_validade = str(aso.data_validade) if aso.data_validade else None
        if aso.data_validade:
            aso_dias = (aso.data_validade - hoje).days
            aso_status = "vencido" if aso_dias < 0 else ("alerta" if aso_dias <= 30 else "ok")
        else:
            aso_status = "ok"

    # Treinamentos vencidos
    treinamentos_total = TreinamentoNR.objects.filter(
        funcionarios=func, empresa=func.empresa
    ).count()
    treinamentos_vencidos = TreinamentoNR.objects.filter(
        funcionarios=func, empresa=func.empresa,
        data_vencimento__lt=hoje,
    ).count()

    return JsonResponse({
        "nome": func.nome,
        "cargo": func.cargo,
        "empresa_nome": func.empresa.nome,
        "aso_status": aso_status,
        "aso_validade": aso_validade,
        "aso_dias_vencer": aso_dias,
        "aso_resultado": aso.get_resultado_display() if aso else None,
        "treinamentos_total": treinamentos_total,
        "treinamentos_vencidos": treinamentos_vencidos,
        "treinamentos_ok": treinamentos_total - treinamentos_vencidos,
    })
