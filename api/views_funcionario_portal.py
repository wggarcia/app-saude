"""
Portal do Funcionário — SST
Autenticação via email + senha (criado pelo funcionário no app)
ou via CPF + data de nascimento (legado).
"""
import jwt
import json
import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import (
    FuncionarioSST, ASOOcupacional, TreinamentoNR, EntregaEPI,
    CredencialAppFuncionario, NotificacaoFuncionario, SolicitacaoExame,
)
from .middleware import _rls_set_empresa
from .services.employee_notifications import solicitacao_portal_dict


# Alias da conexão que BYPASSA o RLS (papel dono do banco). Usado apenas em
# lookups cross-tenant que ocorrem ANTES de termos o empresa_id — login do app,
# busca por CPF e registro. A conexão "default" usa o papel restrito e, sob RLS
# sem app.empresa_id, não enxerga nenhuma linha.
_OWNER_DB = "owner" if "owner" in settings.DATABASES else "default"


# ── FCM token ───────────────────────────────────────────────────────────────

@csrf_exempt
def funcionario_salvar_fcm_token(request):
    """
    POST /api/funcionario/fcm-token
    Header: Authorization: Bearer <jwt>
    Body:   { "fcm_token": "<token FCM do dispositivo>" }

    Salva o FCM token na CredencialAppFuncionario para envio de push notifications.
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    token_fcm = (dados.get("fcm_token") or "").strip()
    if not token_fcm:
        return JsonResponse({"erro": "fcm_token é obrigatório"}, status=400)

    try:
        cred = CredencialAppFuncionario.objects.get(funcionario=func, ativo=True)
        cred.fcm_token = token_fcm
        cred.save(update_fields=["fcm_token", "atualizado_em"])
        return JsonResponse({"status": "ok"})
    except CredencialAppFuncionario.DoesNotExist:
        return JsonResponse({"erro": "Credencial não encontrada"}, status=404)


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
        # As rotas /api/funcionario/ são "livres" no EmpresaMiddleware, então o
        # contexto RLS (app.empresa_id) NÃO foi setado para esta requisição. O
        # JWT já carrega o empresa_id do funcionário — usamos ele para escopar o
        # RLS antes de qualquer query, preservando o isolamento entre tenants e
        # permitindo que as tabelas protegidas (FuncionarioSST, Notificacao, ASO,
        # EPI, Treinamento...) fiquem visíveis apenas para a empresa do token.
        _rls_set_empresa(data["empresa_id"])
        return FuncionarioSST.objects.select_related("empresa").get(
            id=data["funcionario_id"],
            empresa_id=data["empresa_id"],
            ativo=True,
        )
    except Exception:
        return None


def _cpf_limpo(cpf):
    return "".join(c for c in (cpf or "") if c.isdigit())


# ── registro ───────────────────────────────────────────────────────────────

@csrf_exempt
def funcionario_buscar_cpf(request):
    """
    Etapa 1 do registro: retorna as empresas vinculadas ao CPF.
    POST { "cpf": "..." }
    Resposta:
      - 1 empresa  → { "status": "ok", "funcionario_id": X, "empresa_nome": "..." }
      - N empresas → { "status": "escolher_empresa", "opcoes": [{id, empresa_nome, cargo}] }
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cpf = _cpf_limpo(dados.get("cpf", ""))
    if not cpf:
        return JsonResponse({"erro": "CPF é obrigatório"}, status=400)

    funcs = list(
        FuncionarioSST.objects.using(_OWNER_DB)
        .filter(cpf__icontains=cpf, ativo=True)
        .select_related("empresa")
        .order_by("empresa__nome")
    )
    if not funcs:
        return JsonResponse({"erro": "CPF não encontrado. Solicite ao RH o seu cadastro."}, status=404)

    if len(funcs) == 1:
        return JsonResponse({
            "status": "ok",
            "funcionario_id": funcs[0].id,
            "nome": funcs[0].nome,
            "empresa_nome": funcs[0].empresa.nome,
            "cargo": funcs[0].cargo,
        })

    return JsonResponse({
        "status": "escolher_empresa",
        "nome": funcs[0].nome,
        "opcoes": [
            {"funcionario_id": f.id, "empresa_nome": f.empresa.nome, "cargo": f.cargo or ""}
            for f in funcs
        ],
    })


@csrf_exempt
def funcionario_registrar(request):
    """
    Etapa 2 do registro: cria credencial com email + senha para o funcionario_id escolhido.
    POST { "funcionario_id": X, "email": "...", "senha": "..." }
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    funcionario_id = dados.get("funcionario_id")
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha", "")

    if not funcionario_id:
        return JsonResponse({"erro": "funcionario_id é obrigatório"}, status=400)
    if not email or "@" not in email:
        return JsonResponse({"erro": "E-mail inválido"}, status=400)
    if not senha or len(senha) < 6:
        return JsonResponse({"erro": "Senha deve ter pelo menos 6 caracteres"}, status=400)

    func = (
        FuncionarioSST.objects.using(_OWNER_DB)
        .filter(id=funcionario_id, ativo=True)
        .select_related("empresa")
        .first()
    )
    if not func:
        return JsonResponse({"erro": "Funcionário não encontrado."}, status=404)

    if CredencialAppFuncionario.objects.using(_OWNER_DB).filter(email=email).exists():
        return JsonResponse({"erro": "E-mail já cadastrado. Use outro ou recupere sua senha."}, status=409)

    if CredencialAppFuncionario.objects.using(_OWNER_DB).filter(funcionario=func).exists():
        return JsonResponse({"erro": "Conta já existe para este CPF. Faça login com seu e-mail."}, status=409)

    cred = CredencialAppFuncionario.objects.using(_OWNER_DB).create(
        funcionario=func,
        email=email,
        senha=make_password(senha),
    )

    token = _token_funcionario(func)
    return JsonResponse({
        "status": "ok",
        "token": token,
        "funcionario_id": func.id,
        "nome": func.nome,
        "cargo": func.cargo,
        "empresa_nome": func.empresa.nome,
        "email": cred.email,
    }, status=201)


# ── login ───────────────────────────────────────────────────────────────────

@csrf_exempt
def funcionario_login(request):
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha", "")

    # ── login por email + senha (novo) ──
    if email:
        if not senha:
            return JsonResponse({"erro": "Senha é obrigatória"}, status=400)
        try:
            cred = CredencialAppFuncionario.objects.using(_OWNER_DB).select_related(
                "funcionario__empresa"
            ).get(email=email, ativo=True)
        except CredencialAppFuncionario.DoesNotExist:
            return JsonResponse({"erro": "E-mail não encontrado"}, status=404)
        if not check_password(senha, cred.senha):
            return JsonResponse({"erro": "Senha incorreta"}, status=401)
        func = cred.funcionario
        if not func.ativo:
            return JsonResponse({"erro": "Conta desativada. Fale com o RH."}, status=403)
        token = _token_funcionario(func)
        return JsonResponse({
            "status": "ok",
            "token": token,
            "funcionario_id": func.id,
            "nome": func.nome,
            "cargo": func.cargo,
            "empresa_nome": func.empresa.nome,
            "email": email,
        })

    # ── login legado por CPF (fallback) ──
    cpf = _cpf_limpo(dados.get("cpf", ""))
    if not cpf:
        return JsonResponse({"erro": "E-mail ou CPF é obrigatório"}, status=400)

    func = (
        FuncionarioSST.objects.using(_OWNER_DB)
        .filter(cpf__icontains=cpf, ativo=True)
        .select_related("empresa")
        .order_by("-criado_em")
        .first()
    )
    if not func:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)

    nascimento = dados.get("data_nascimento", "")
    if func.data_nascimento and nascimento:
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


# ── notificações ────────────────────────────────────────────────────────────

@csrf_exempt
def funcionario_notificacoes(request):
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autorizado"}, status=401)

    nao_lidas = NotificacaoFuncionario.objects.filter(funcionario=func, lida=False).count()
    items = list(
        NotificacaoFuncionario.objects
        .filter(funcionario=func)
        .values("id", "tipo", "titulo", "mensagem", "lida", "criado_em", "referencia_id")
        [:30]
    )
    for i in items:
        i["criado_em"] = i["criado_em"].strftime("%d/%m/%Y %H:%M")

    return JsonResponse({"notificacoes": items, "nao_lidas": nao_lidas})


@csrf_exempt
def funcionario_notificacao_lida(request, notificacao_id):
    if request.method not in ("POST", "DELETE"):
        return JsonResponse({"erro": "Use POST ou DELETE"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autorizado"}, status=401)
    if request.method == "DELETE":
        # Só permite deletar notificações já lidas
        NotificacaoFuncionario.objects.filter(
            id=notificacao_id, funcionario=func, lida=True
        ).delete()
        return JsonResponse({"ok": True})
    NotificacaoFuncionario.objects.filter(id=notificacao_id, funcionario=func).update(lida=True)
    return JsonResponse({"ok": True})


@csrf_exempt
def funcionario_notificacoes_limpar_lidas(request):
    """DELETE /api/funcionario/notificacoes/limpar-lidas — apaga todas as lidas."""
    if request.method != "DELETE":
        return JsonResponse({"erro": "Use DELETE"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autorizado"}, status=401)
    deletadas, _ = NotificacaoFuncionario.objects.filter(funcionario=func, lida=True).delete()
    return JsonResponse({"ok": True, "deletadas": deletadas})


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
        funcionario=func, empresa=func.empresa
    ).order_by("-data_realizacao", "-criado_em")

    hoje = timezone.now().date()

    def t_dict(t):
        vencido = bool(t.data_validade and t.data_validade < hoje)
        return {
            "id": t.id,
            "nr": t.nr,
            "titulo": t.titulo,
            "carga_horaria": t.carga_horaria,
            "data_realizacao": str(t.data_realizacao) if t.data_realizacao else None,
            "data_validade": str(t.data_validade) if t.data_validade else None,
            "data_vencimento": str(t.data_validade) if t.data_validade else None,
            "instrutor": t.instrutor,
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
        entregas = EntregaEPI.objects.filter(
            funcionario=func, empresa=func.empresa
        ).select_related("epi").order_by("-data_entrega")

        def e_dict(e):
            return {
                "id": e.id,
                "epi_nome": e.epi.nome if e.epi else "—",
                "ca": e.epi.ca_numero if e.epi else "",
                "quantidade": e.quantidade,
                "data_entrega": str(e.data_entrega),
                "data_devolucao": str(e.data_devolucao) if e.data_devolucao else None,
                "devolvido": bool(e.data_devolucao),
            }
        return JsonResponse({"epis": [e_dict(e) for e in entregas]})
    except Exception:
        return JsonResponse({"epis": []})


def funcionario_minhas_solicitacoes(request):
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    solicitacoes = (
        SolicitacaoExame.objects
        .filter(funcionario=func, empresa=func.empresa)
        .select_related("clinica")
        .order_by("-data_solicitacao")[:30]
    )
    return JsonResponse({
        "solicitacoes": [solicitacao_portal_dict(item) for item in solicitacoes]
    })


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
        funcionario=func, empresa=func.empresa
    ).count()
    treinamentos_vencidos = TreinamentoNR.objects.filter(
        funcionario=func,
        empresa=func.empresa,
        data_validade__lt=hoje,
    ).count()
    solicitacoes_ativas = SolicitacaoExame.objects.filter(
        funcionario=func,
        empresa=func.empresa,
        status__in=["pendente", "agendado"],
    )
    proxima_solicitacao = (
        solicitacoes_ativas
        .exclude(data_agendamento__isnull=True)
        .order_by("data_agendamento")
        .first()
    )

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
        "solicitacoes_ativas": solicitacoes_ativas.count(),
        "proximo_agendamento_exame": proxima_solicitacao.data_agendamento.isoformat() if proxima_solicitacao and proxima_solicitacao.data_agendamento else None,
        # inclui contagem de notificações não lidas no dashboard
        "notificacoes_nao_lidas": NotificacaoFuncionario.objects.filter(
            funcionario=func, lida=False
        ).count(),
    })


# ── Comunicados SST ────────────────────────────────────────────────────────

def funcionario_comunicados(request):
    """GET /api/funcionario/comunicados — lista comunicados da empresa."""
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    from .models import ConteudoSSTPublicado

    comunicados = ConteudoSSTPublicado.objects.filter(
        empresa=func.empresa,
        tipo=ConteudoSSTPublicado.TIPO_COMUNICADO,
        ativo=True,
    ).order_by("-publicado_em")[:50]

    return JsonResponse({
        "comunicados": [
            {
                "id": c.id,
                "titulo": c.titulo,
                "corpo": c.descricao,
                "tipo": c.tipo,
                "link": c.url_conteudo or "",
                "remetente": c.publicado_por or "Empresa",
                "criado_em": c.publicado_em.strftime("%Y-%m-%d %H:%M"),
                # Comunicados do SaaS não têm campo lido por funcionário —
                # retornamos False e deixamos o app marcar localmente
                "lido": False,
            }
            for c in comunicados
        ]
    })


@csrf_exempt
def funcionario_comunicado_lido(request, comunicado_id):
    """POST /api/funcionario/comunicados/<id>/lido — marca como lido (sem-op, apenas confirma)."""
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)
    return JsonResponse({"ok": True})


# ── Psicossocial NR-01 — avaliação ativa ──────────────────────────────────

def funcionario_psicossocial_ativa(request):
    """GET /api/funcionario/psicossocial/ativa/ — retorna avaliação ativa + questões."""
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    from .models import AvaliacaoPsicossocial, QuestaoAvaliacaoPsicossocial, RespostaPsicossocial

    av = AvaliacaoPsicossocial.objects.filter(
        empresa=func.empresa, status="ativa"
    ).order_by("-data_inicio").first()

    if not av:
        return JsonResponse({"erro": "Nenhuma avaliação ativa"}, status=404)

    # Verifica se o funcionário já respondeu (por setor, se especificado)
    # Como é anônimo, verificamos por sessão/device — aqui retornamos flag
    # que o app controla localmente via SharedPreferences
    questoes = QuestaoAvaliacaoPsicossocial.objects.filter(
        avaliacao=av
    ).order_by("ordem", "id")

    return JsonResponse({
        "id": av.id,
        "titulo": av.titulo,
        "descricao": av.descricao,
        "link_token": av.link_token,
        "anonima": av.anonima,
        "setor_alvo": av.setor_alvo or "",
        "total_respondidos": av.total_respondidos,
        "ja_respondeu": False,  # controlado pelo app via SharedPreferences
        "questoes": [
            {
                "id": q.id,
                "texto": q.texto,
                "categoria": q.categoria,
                "obrigatoria": q.obrigatoria,
                "ordem": q.ordem,
            }
            for q in questoes
        ],
    })


# ── EPIs pendentes de confirmação biométrica ───────────────────────────────

def funcionario_epis_pendentes(request):
    """GET /api/funcionario/epis/pendentes-entrega — entregas sem confirmação biométrica."""
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    from .models import EntregaEPI

    pendentes = EntregaEPI.objects.filter(
        funcionario=func,
        empresa=func.empresa,
        biometria_confirmada=False,
    ).select_related("epi").order_by("-data_entrega")[:20]

    return JsonResponse({
        "pendentes": [
            {
                "id": e.id,
                "epi_nome": e.epi.nome,
                "data_entrega": str(e.data_entrega),
                "quantidade": e.quantidade,
                "biometria_confirmada": e.biometria_confirmada,
            }
            for e in pendentes
        ]
    })


def funcionario_meus_afastamentos(request):
    """GET /api/funcionario/meus-afastamentos — afastamentos do funcionário autenticado."""
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    from .models import AfastamentoSST

    MOTIVO_LABEL = {
        "acidente_trabalho":  "Acidente de Trabalho",
        "doenca_ocupacional": "Doença Ocupacional",
        "doenca_comum":       "Doença Comum",
        "licenca_maternidade":"Licença Maternidade",
        "licenca_paternidade":"Licença Paternidade",
        "outro":              "Outro",
    }
    STATUS_LABEL = {
        "ativo":               "Em afastamento",
        "retorno_programado":  "Retorno programado",
        "encerrado":           "Encerrado",
    }

    qs = AfastamentoSST.objects.filter(
        funcionario=func, empresa=func.empresa
    ).order_by("-data_inicio")[:30]

    return JsonResponse({
        "afastamentos": [
            {
                "id":                   a.id,
                "motivo":               a.motivo,
                "motivo_label":         MOTIVO_LABEL.get(a.motivo, a.motivo),
                "cid":                  a.cid or "",
                "data_inicio":          str(a.data_inicio),
                "data_prevista_retorno":str(a.data_prevista_retorno) if a.data_prevista_retorno else None,
                "data_retorno_real":    str(a.data_retorno_real) if a.data_retorno_real else None,
                "status":               a.status,
                "status_label":         STATUS_LABEL.get(a.status, a.status),
                "observacoes":          a.observacoes or "",
            }
            for a in qs
        ]
    })


def funcionario_minha_biometria(request):
    """GET /api/funcionario/minha-biometria — status da biometria do funcionário autenticado."""
    if request.method != "GET":
        return JsonResponse({"erro": "Use GET"}, status=405)
    func = _autenticar_funcionario(request)
    if not func:
        return JsonResponse({"erro": "não autenticado"}, status=401)

    from .models import BiometriaFuncionario

    try:
        bio = BiometriaFuncionario.objects.get(funcionario=func, ativo=True)
        return JsonResponse({
            "cadastrada": True,
            "hash_foto":  bio.hash_foto,
            "cadastrado_em":  str(bio.cadastrado_em.date()),
            "atualizado_em":  str(bio.atualizado_em.date()),
        })
    except BiometriaFuncionario.DoesNotExist:
        return JsonResponse({"cadastrada": False})
