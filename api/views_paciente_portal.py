"""
Portal do Paciente Hospitalar — o "MyChart brasileiro".

SÓ segmento Hospital. Página web dedicada (paciente_portal.html) onde o próprio
paciente acessa os dados dele: por enquanto (Onda 1) resultados de exames, com
uma IA que traduz o laudo para linguagem simples.

Autenticação de PESSOA FÍSICA, isolada do login da empresa — clonada do Portal
do Funcionário (SST): CPF + data de nascimento provam a identidade, o paciente
cria e-mail/senha, e recebe um JWT próprio. Ancorada no MPI (IdentidadePaciente).

Nada aqui altera dados clínicos — tudo é SOMENTE LEITURA. Resultados sensíveis
(crítico) e ainda sem laudo (pendente) NÃO aparecem em detalhe: o paciente vê
que existe um resultado e é orientado a conversar com a equipe, evitando que
descubra algo grave sozinho num PDF.
"""
import hashlib
import hmac
import json
import logging
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    CredencialAppPaciente, IdentidadePaciente, PacienteInternado, ResultadoExame,
    AgendamentoPaciente, MensagemPacientePortal,
)
from .middleware import _rls_set_empresa
from .access_control import get_setor
from .services.identidade_paciente import resolver_identidade
from .utils import cpf_digitos

logger = logging.getLogger(__name__)

# Alias da conexão que BYPASSA o RLS (papel dono do banco). Usado só nos lookups
# cross-tenant ANTES de termos empresa_id — busca por CPF e registro. Mesmo
# padrão do Portal do Funcionário.
_OWNER_DB = "owner" if "owner" in settings.DATABASES else "default"

_REGISTRO_TOKEN_TTL = timedelta(minutes=15)
_REGISTRO_PURPOSE = "registro_paciente_v1"

# Regra de liberação clínica (Onda 1, sem migração): o que o paciente vê sozinho.
# 'critico' e 'pendente' ficam ocultos em detalhe — o paciente é orientado a
# procurar a equipe. Uma liberação explícita por médico entra numa fase seguinte.
_INTERPRETACAO_VISIVEL = ("normal", "alterado")


# ── helpers de identidade / CPF ──────────────────────────────────────────────

def _cpf_variantes(cpf):
    """Formatos possíveis de armazenamento do CPF (dígitos e mascarado)."""
    d = cpf_digitos(cpf)[:11]
    if len(d) != 11:
        return [c for c in [cpf] if c]
    return [d, f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"]


def _cpf_hash(cpf):
    return hmac.new(
        settings.JWT_SECRET_KEY.encode(), cpf_digitos(cpf).encode(), hashlib.sha256
    ).hexdigest()


def _empresa_eh_hospital(empresa):
    try:
        return get_setor(empresa) == "hospital"
    except Exception:
        return False


def _internacoes_por_cpf_dob(cpf, data_nascimento):
    """PacienteInternado (em hospitais) que batem CPF + data de nascimento.
    Match exato de CPF (nunca substring — evita enumeração). Cross-tenant via
    _OWNER_DB porque ainda não há empresa no contexto."""
    variantes = _cpf_variantes(cpf)
    if not variantes:
        return []
    filtro = Q()
    for v in variantes:
        filtro |= Q(cpf=v)
    qs = (
        PacienteInternado.objects.using(_OWNER_DB)
        .filter(filtro, data_nascimento=data_nascimento)
        .select_related("empresa")
    )
    return [p for p in qs if _empresa_eh_hospital(p.empresa)]


# ── tokens ───────────────────────────────────────────────────────────────────

def _token_paciente(identidade):
    payload = {
        "identidade_id": identidade.id,
        "empresa_id": identidade.empresa_id,
        "iat": int(timezone.now().timestamp()),
        "exp": int((timezone.now() + timedelta(days=30)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def _registro_token(identidade, cpf):
    payload = {
        "purpose": _REGISTRO_PURPOSE,
        "identidade_id": identidade.id,
        "empresa_id": identidade.empresa_id,
        "cpf_hash": _cpf_hash(cpf),
        "iat": int(timezone.now().timestamp()),
        "exp": int((timezone.now() + _REGISTRO_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def _verificar_registro_token(token):
    if not token:
        return None
    try:
        data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None
    if data.get("purpose") != _REGISTRO_PURPOSE:
        return None
    if not data.get("identidade_id") or not data.get("empresa_id") or not data.get("cpf_hash"):
        return None
    return data


def _autenticar_paciente(request):
    """Valida o Bearer JWT do paciente e devolve o IdentidadePaciente.
    As rotas /api/paciente/ são livres no EmpresaMiddleware, então setamos o
    RLS pelo empresa_id do token antes de qualquer query — preservando o
    isolamento por hospital."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if data.get("purpose") == _REGISTRO_PURPOSE:
            return None  # token de registro não vale como sessão
        _rls_set_empresa(data["empresa_id"])
        return IdentidadePaciente.objects.select_related("empresa").get(
            id=data["identidade_id"], empresa_id=data["empresa_id"],
        )
    except Exception:
        return None


# ── página ────────────────────────────────────────────────────────────────────

def paciente_portal_page(request):
    """GET /paciente/ — a página do portal (login + meus exames). Toda a
    autenticação é via Bearer no fetch; a página em si é pública."""
    return render(request, "paciente_portal.html")


# ── acesso (etapa 1): CPF + data de nascimento ────────────────────────────────

@csrf_exempt
def paciente_acessar(request):
    """POST /api/paciente/acessar  {cpf, data_nascimento}
    Confere CPF + data de nascimento contra as internações de hospitais.
    Devolve um registro_token por hospital encontrado (o paciente escolhe se
    tiver mais de um). NÃO revela dado clínico aqui."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "unknown")
    )
    rl_key = f"paciente_acessar_rl:{ip}"
    tentativas = cache.get(rl_key, 0)
    if tentativas >= 10:
        return JsonResponse({"erro": "Muitas tentativas. Aguarde 1 minuto."}, status=429)
    cache.set(rl_key, tentativas + 1, timeout=60)

    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    cpf = cpf_digitos(dados.get("cpf", ""))
    data_nascimento = (dados.get("data_nascimento") or "").strip()
    if len(cpf) != 11:
        return JsonResponse({"erro": "Informe um CPF válido (11 dígitos)."}, status=400)
    if not data_nascimento:
        return JsonResponse({"erro": "Informe a data de nascimento."}, status=400)

    internacoes = _internacoes_por_cpf_dob(cpf, data_nascimento)
    if not internacoes:
        return JsonResponse(
            {"erro": "Não encontramos um cadastro com esse CPF e data de nascimento. "
                     "Procure a recepção do hospital."},
            status=404,
        )

    # Resolve o MPI por hospital (dedup por CPF no serviço) — um registro_token
    # por hospital distinto.
    por_empresa = {}
    for p in internacoes:
        if p.empresa_id in por_empresa:
            continue
        identidade = resolver_identidade(
            p.empresa, nome=p.nome, cpf=cpf,
            data_nascimento=p.data_nascimento, criar=True,
        )
        if identidade:
            por_empresa[p.empresa_id] = (p, identidade)

    opcoes = [
        {
            "registro_token": _registro_token(identidade, cpf),
            "hospital_nome": p.empresa.nome,
            "nome": p.nome,
            # já tem login?
            "tem_conta": CredencialAppPaciente.objects.using(_OWNER_DB)
            .filter(identidade=identidade, ativo=True).exists(),
        }
        for (p, identidade) in por_empresa.values()
    ]
    return JsonResponse({"status": "ok", "opcoes": opcoes})


# ── registro (etapa 2): cria e-mail + senha ───────────────────────────────────

@csrf_exempt
def paciente_registrar(request):
    """POST /api/paciente/registrar  {registro_token, email, senha}"""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    prova = _verificar_registro_token(dados.get("registro_token"))
    if not prova:
        return JsonResponse(
            {"erro": "Sessão de acesso expirada. Refaça a verificação por CPF."}, status=401
        )
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha", "")
    if not email or "@" not in email:
        return JsonResponse({"erro": "E-mail inválido"}, status=400)
    if not senha or len(senha) < 6:
        return JsonResponse({"erro": "A senha deve ter pelo menos 6 caracteres"}, status=400)

    identidade = (
        IdentidadePaciente.objects.using(_OWNER_DB)
        .select_related("empresa")
        .filter(id=prova["identidade_id"], empresa_id=prova["empresa_id"])
        .first()
    )
    if not identidade:
        return JsonResponse({"erro": "Cadastro não encontrado."}, status=404)
    # Revalida o vínculo com o CPF provado na etapa 1.
    if not hmac.compare_digest(_cpf_hash(identidade.cpf), prova["cpf_hash"]):
        return JsonResponse(
            {"erro": "Sessão de acesso inválida. Refaça a verificação por CPF."}, status=401
        )

    if CredencialAppPaciente.objects.using(_OWNER_DB).filter(email=email).exists():
        return JsonResponse(
            {"erro": "E-mail já cadastrado. Faça login ou use outro."}, status=409
        )
    if CredencialAppPaciente.objects.using(_OWNER_DB).filter(identidade=identidade).exists():
        return JsonResponse(
            {"erro": "Você já tem uma conta. Faça login com seu e-mail."}, status=409
        )

    cred = CredencialAppPaciente.objects.using(_OWNER_DB).create(
        identidade=identidade, email=email, senha=make_password(senha),
        ultimo_login=timezone.now(),
    )
    return JsonResponse({
        "status": "ok",
        "token": _token_paciente(identidade),
        "nome": identidade.nome,
        "hospital_nome": identidade.empresa.nome,
        "email": cred.email,
    }, status=201)


# ── login ─────────────────────────────────────────────────────────────────────

@csrf_exempt
def paciente_login(request):
    """POST /api/paciente/login  {email, senha}"""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    try:
        dados = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha", "")
    if not email or not senha:
        return JsonResponse({"erro": "E-mail e senha são obrigatórios"}, status=400)

    cred = (
        CredencialAppPaciente.objects.using(_OWNER_DB)
        .select_related("identidade__empresa")
        .filter(email=email, ativo=True)
        .first()
    )
    if not cred or not check_password(senha, cred.senha):
        return JsonResponse({"erro": "E-mail ou senha incorretos"}, status=401)

    cred.ultimo_login = timezone.now()
    cred.save(update_fields=["ultimo_login", "atualizado_em"])
    identidade = cred.identidade
    return JsonResponse({
        "status": "ok",
        "token": _token_paciente(identidade),
        "nome": identidade.nome,
        "hospital_nome": identidade.empresa.nome,
        "email": cred.email,
    })


# ── dados clínicos (somente leitura) ──────────────────────────────────────────

def _pacientes_do(identidade):
    """Internações do paciente neste hospital — por FK do MPI ou por CPF."""
    filtro = Q(identidade=identidade)
    for v in _cpf_variantes(identidade.cpf):
        filtro |= Q(cpf=v)
    return PacienteInternado.objects.filter(filtro, empresa_id=identidade.empresa_id)


def _medicacoes_de(internacao):
    """Extrai nomes de medicação de prescricao_atual (JSON de forma variável)."""
    if not internacao:
        return []
    pa = internacao.prescricao_atual
    itens = []
    if isinstance(pa, dict):
        itens = pa.get("medicamentos") or pa.get("itens") or pa.get("medicacoes") or []
    elif isinstance(pa, list):
        itens = pa
    nomes = []
    for it in itens if isinstance(itens, list) else []:
        if isinstance(it, dict):
            n = it.get("nome") or it.get("medicamento") or it.get("descricao")
            dose = it.get("dose") or it.get("posologia") or ""
            if n:
                nomes.append((n + (" — " + dose if dose else "")).strip())
        elif isinstance(it, str):
            nomes.append(it)
    return nomes[:20]


@csrf_exempt
def paciente_resumo(request):
    """GET /api/paciente/resumo — dados do painel inicial e da aba Minha Saúde:
    identificação, resumo clínico da internação mais recente e contagem de exames.
    Somente leitura."""
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    pacientes = list(_pacientes_do(identidade).order_by("-data_internacao"))
    internacao = pacientes[0] if pacientes else None

    disponiveis = reservados = 0
    if pacientes:
        for r in ResultadoExame.objects.filter(paciente__in=pacientes).only("interpretacao"):
            if r.interpretacao in _INTERPRETACAO_VISIVEL:
                disponiveis += 1
            else:
                reservados += 1

    saude = None
    if internacao:
        saude = {
            "diagnostico_cid": internacao.diagnostico_cid or "",
            "diagnostico_descricao": internacao.diagnostico_descricao or "",
            "alergias": internacao.alergias or "",
            "tipo_sanguineo": internacao.tipo_sanguineo or "",
            "medico_responsavel": internacao.medico_responsavel or "",
            "status": internacao.get_status_display(),
            "data_internacao": internacao.data_internacao.strftime("%d/%m/%Y") if internacao.data_internacao else "",
            "medicacoes": _medicacoes_de(internacao),
        }

    return JsonResponse({
        "nome": identidade.nome,
        "hospital_nome": identidade.empresa.nome,
        "stats": {"exames_disponiveis": disponiveis, "exames_reservados": reservados},
        "saude": saude,
        "perfil": {
            "nome": identidade.nome,
            "cpf_mascarado": _mascara_cpf(identidade.cpf),
            "data_nascimento": identidade.data_nascimento.strftime("%d/%m/%Y") if identidade.data_nascimento else "",
            "hospital_nome": identidade.empresa.nome,
        },
    })


def _mascara_cpf(cpf):
    d = cpf_digitos(cpf)
    if len(d) != 11:
        return "—"
    return "•••.•••.•••-" + d[-2:]


def _exame_nomes(resultado):
    nomes = []
    try:
        for item in (resultado.resultados_json or []):
            n = (item or {}).get("exame")
            if n:
                nomes.append(n)
    except Exception:
        pass
    if not nomes:
        try:
            for item in (resultado.pedido.exames or []):
                n = (item or {}).get("nome")
                if n:
                    nomes.append(n)
        except Exception:
            pass
    return nomes


@csrf_exempt
def paciente_meus_exames(request):
    """GET /api/paciente/meus-exames — resultados de exame do próprio paciente."""
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    pacientes = list(_pacientes_do(identidade))
    if not pacientes:
        return JsonResponse({"exames": [], "aviso_oculto": 0})

    resultados = (
        ResultadoExame.objects
        .filter(paciente__in=pacientes)
        .select_related("pedido")
        .order_by("-data_resultado")[:100]
    )

    exames, ocultos = [], 0
    for r in resultados:
        visivel = r.interpretacao in _INTERPRETACAO_VISIVEL
        item = {
            "id": r.id,
            # Em resultado reservado NÃO expomos nem o nome do exame — o nome de
            # um marcador (ex.: tumoral) já pode assustar o paciente sozinho.
            "exames": _exame_nomes(r) if visivel else [],
            "data": r.data_resultado.strftime("%d/%m/%Y") if r.data_resultado else "",
            "interpretacao": r.interpretacao,
            "visivel": visivel,
        }
        if visivel:
            item["laudo"] = r.laudo or ""
            item["responsavel"] = r.responsavel_laudo or ""
            item["valores"] = r.resultados_json or []
            try:
                item["arquivo_laudo_url"] = r.arquivo_laudo.url if r.arquivo_laudo else ""
            except Exception:
                item["arquivo_laudo_url"] = ""
            item["pode_explicar"] = bool(r.laudo or r.resultados_json)
        else:
            ocultos += 1
            item["mensagem"] = (
                "Há um resultado que precisa ser conversado com seu médico. "
                "Entre em contato com a equipe do hospital."
            )
        exames.append(item)

    return JsonResponse({"exames": exames, "aviso_oculto": ocultos})


def _explicar_fallback(nomes, laudo, valores):
    """Explicação simples determinística — quando não há chave de IA. Nunca falha."""
    partes = []
    if nomes:
        partes.append("Este exame avaliou: " + ", ".join(nomes) + ".")
    alterados = [
        v.get("exame") for v in (valores or [])
        if str(v.get("status", "")).lower() in ("alterado", "alto", "baixo", "anormal")
    ]
    if alterados:
        partes.append(
            "Alguns valores apareceram fora da faixa de referência (" +
            ", ".join(n for n in alterados if n) +
            "). Isso nem sempre indica problema — muitos fatores influenciam."
        )
    else:
        partes.append("Os valores medidos vieram, em geral, dentro do esperado.")
    partes.append(
        "Esta é uma explicação geral e NÃO substitui a avaliação do seu médico. "
        "Leve este resultado à sua próxima consulta para a interpretação correta."
    )
    return {"explicacao": " ".join(partes), "fonte": "regras"}


@csrf_exempt
def paciente_exame_explicar(request, pk):
    """POST /api/paciente/exames/<pk>/explicar — IA traduz o laudo para linguagem
    simples. Só para exames visíveis ao paciente. Fallback determinístico."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    pacientes = list(_pacientes_do(identidade))
    try:
        r = ResultadoExame.objects.select_related("pedido").get(
            id=pk, paciente__in=pacientes
        )
    except ResultadoExame.DoesNotExist:
        return JsonResponse({"erro": "Resultado não encontrado"}, status=404)

    if r.interpretacao not in _INTERPRETACAO_VISIVEL:
        return JsonResponse(
            {"erro": "Este resultado precisa ser conversado com seu médico."}, status=403
        )

    nomes = _exame_nomes(r)
    api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
    if not api_key:
        return JsonResponse(_explicar_fallback(nomes, r.laudo, r.resultados_json))

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        system = (
            "Você explica resultados de exame para o PRÓPRIO paciente, em português "
            "do Brasil simples, acolhedor e sem jargão. Regras: NÃO dê diagnóstico "
            "nem prescreva; explique o que o exame mede e o que os valores sugerem em "
            "linguagem leiga; seja tranquilizador mas honesto; SEMPRE termine dizendo "
            "que isto não substitui a consulta com o médico. Máximo 2 parágrafos curtos. "
            "Responda apenas com o texto da explicação, sem título."
        )
        user_msg = (
            f"Exames: {', '.join(nomes) or 'exame'}\n"
            f"Valores: {json.dumps(r.resultados_json or [], ensure_ascii=False)}\n"
            f"Laudo do médico: {r.laudo or '—'}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=600,
            system=system, messages=[{"role": "user", "content": user_msg}],
        )
        texto = (resp.content[0].text or "").strip()
        if not texto:
            return JsonResponse(_explicar_fallback(nomes, r.laudo, r.resultados_json))
        return JsonResponse({"explicacao": texto, "fonte": "ia"})
    except Exception:
        logger.exception("IA explicar exame paciente pk=%s — fallback por regras", pk)
        return JsonResponse(_explicar_fallback(nomes, r.laudo, r.resultados_json))


# ── LGPD: exportar dados / excluir conta ──────────────────────────────────────

@csrf_exempt
def paciente_exportar(request):
    """GET /api/paciente/exportar — portabilidade LGPD: baixa em JSON os dados do
    paciente no portal (perfil + exames visíveis). Somente leitura."""
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    pacientes = list(_pacientes_do(identidade))
    exames = []
    for r in (ResultadoExame.objects.filter(paciente__in=pacientes)
              .select_related("pedido").order_by("-data_resultado")[:300]):
        visivel = r.interpretacao in _INTERPRETACAO_VISIVEL
        exames.append({
            "exames": _exame_nomes(r),
            "data": r.data_resultado.strftime("%d/%m/%Y") if r.data_resultado else "",
            "interpretacao": r.interpretacao,
            "valores": r.resultados_json if visivel else "reservado ao médico",
            "laudo": r.laudo if visivel else "reservado ao médico",
        })

    payload = {
        "gerado_em": timezone.now().strftime("%d/%m/%Y %H:%M"),
        "titular": {
            "nome": identidade.nome,
            "cpf_mascarado": _mascara_cpf(identidade.cpf),
            "data_nascimento": identidade.data_nascimento.strftime("%d/%m/%Y") if identidade.data_nascimento else "",
        },
        "hospital": identidade.empresa.nome,
        "exames": exames,
        "aviso": ("Exportação de dados do Portal do Paciente conforme a LGPD (Lei 13.709/2018). "
                  "O prontuário médico completo permanece sob guarda do hospital, conforme exigência legal."),
    }
    resp = JsonResponse(payload, json_dumps_params={"ensure_ascii": False, "indent": 2})
    resp["Content-Disposition"] = 'attachment; filename="meus-dados-solocrt.json"'
    return resp


@csrf_exempt
def paciente_excluir_conta(request):
    """POST /api/paciente/excluir-conta — remove SOMENTE a credencial de acesso ao
    portal (o prontuário médico é mantido pelo hospital por obrigação legal)."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)
    CredencialAppPaciente.objects.using(_OWNER_DB).filter(identidade=identidade).delete()
    return JsonResponse({
        "status": "ok",
        "mensagem": ("Sua conta de acesso ao portal foi excluída. Seu prontuário médico "
                     "permanece sob guarda do hospital, conforme a legislação."),
    })


# ── Compartilhar exame (link temporário para o médico) ────────────────────────

_SHARE_PURPOSE = "share_exame_v1"
_SHARE_TTL = timedelta(days=7)


def _share_token(resultado, identidade):
    payload = {
        "purpose": _SHARE_PURPOSE,
        "resultado_id": resultado.id,
        "empresa_id": identidade.empresa_id,
        "iat": int(timezone.now().timestamp()),
        "exp": int((timezone.now() + _SHARE_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


@csrf_exempt
def paciente_compartilhar_exame(request, pk):
    """POST /api/paciente/exames/<pk>/compartilhar — gera um link temporário
    (7 dias) e somente-leitura de UM resultado, para o paciente mostrar ao médico.
    Só exames visíveis ao paciente."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    pacientes = list(_pacientes_do(identidade))
    try:
        r = ResultadoExame.objects.get(id=pk, paciente__in=pacientes)
    except ResultadoExame.DoesNotExist:
        return JsonResponse({"erro": "Resultado não encontrado"}, status=404)
    if r.interpretacao not in _INTERPRETACAO_VISIVEL:
        return JsonResponse({"erro": "Este resultado precisa ser conversado com seu médico."}, status=403)

    base = getattr(settings, "PUBLIC_BASE_URL", "").rstrip("/")
    url = base + "/exame-compartilhado/" + _share_token(r, identidade)
    return JsonResponse({"url": url, "expira_em": "7 dias"})


def exame_compartilhado_page(request, token):
    """GET /exame-compartilhado/<token> — página pública (sem login) que mostra UM
    resultado compartilhado pelo paciente. Valida o token assinado e a expiração."""
    ctx = {"valido": False, "resultado": None}
    try:
        data = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        if data.get("purpose") == _SHARE_PURPOSE and data.get("resultado_id"):
            _rls_set_empresa(data["empresa_id"])
            r = (ResultadoExame.objects.select_related("pedido", "paciente")
                 .filter(id=data["resultado_id"]).first())
            if r and r.interpretacao in _INTERPRETACAO_VISIVEL:
                primeiro_nome = (r.paciente.nome or "").split(" ")[0]
                ctx = {
                    "valido": True,
                    "paciente_nome": primeiro_nome,
                    "exames": _exame_nomes(r),
                    "data": r.data_resultado.strftime("%d/%m/%Y") if r.data_resultado else "",
                    "valores": r.resultados_json or [],
                    "laudo": r.laudo or "",
                    "responsavel": r.responsavel_laudo or "",
                    "hospital": r.paciente.empresa.nome,
                }
    except Exception:
        pass
    return render(request, "paciente_exame_compartilhado.html", ctx)


# ══════════════════════════════════════════════════════════════════════════════
# AGENDA / CONSULTAS
# ══════════════════════════════════════════════════════════════════════════════

def _agendamento_dict(a):
    return {
        "id": a.id,
        "tipo": a.tipo,
        "tipo_display": a.get_tipo_display(),
        "especialidade": a.especialidade,
        "profissional": a.profissional,
        "local": a.local,
        "data": a.data_hora.strftime("%d/%m/%Y"),
        "hora": a.data_hora.strftime("%H:%M"),
        "data_iso": a.data_hora.isoformat(),
        "status": a.status,
        "status_display": a.get_status_display(),
        "observacoes": a.observacoes,
    }


@csrf_exempt
def paciente_agenda(request):
    """GET /api/paciente/agenda — próximos agendamentos e histórico do paciente."""
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    agora = timezone.now()
    qs = AgendamentoPaciente.objects.filter(empresa_id=identidade.empresa_id, identidade=identidade)
    proximas, historico = [], []
    for a in qs:
        d = _agendamento_dict(a)
        futuro = a.data_hora >= agora and a.status in ("agendado", "confirmado")
        (proximas if futuro else historico).append(d)
    proximas.sort(key=lambda x: x["data_iso"])
    historico.sort(key=lambda x: x["data_iso"], reverse=True)
    return JsonResponse({"proximas": proximas, "historico": historico})


@csrf_exempt
def paciente_agenda_confirmar(request, pk):
    """POST /api/paciente/agenda/<pk>/confirmar — paciente confirma presença."""
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)
    try:
        a = AgendamentoPaciente.objects.get(id=pk, empresa_id=identidade.empresa_id, identidade=identidade)
    except AgendamentoPaciente.DoesNotExist:
        return JsonResponse({"erro": "Agendamento não encontrado"}, status=404)
    if a.status != "agendado":
        return JsonResponse({"erro": "Este agendamento não pode ser confirmado."}, status=400)
    a.status = "confirmado"
    a.save(update_fields=["status", "atualizado_em"])
    return JsonResponse({"status": "ok", "agendamento": _agendamento_dict(a)})


# ══════════════════════════════════════════════════════════════════════════════
# MENSAGENS (paciente ↔ equipe)
# ══════════════════════════════════════════════════════════════════════════════

def _mensagem_dict(m):
    return {
        "id": m.id,
        "autor": m.autor,
        "autor_nome": m.autor_nome or ("Você" if m.autor == "paciente" else "Equipe"),
        "texto": m.texto,
        "data": m.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


@csrf_exempt
def paciente_mensagens(request):
    """GET /api/paciente/mensagens — histórico da conversa; marca as da equipe como lidas.
    POST /api/paciente/mensagens {texto} — paciente envia mensagem."""
    identidade = _autenticar_paciente(request)
    if not identidade:
        return JsonResponse({"erro": "Não autorizado"}, status=401)

    if request.method == "POST":
        try:
            texto = (json.loads(request.body or "{}").get("texto") or "").strip()
        except Exception:
            texto = ""
        if not texto:
            return JsonResponse({"erro": "Escreva uma mensagem."}, status=400)
        if len(texto) > 2000:
            texto = texto[:2000]
        m = MensagemPacientePortal.objects.create(
            empresa_id=identidade.empresa_id, identidade=identidade,
            autor="paciente", autor_nome=identidade.nome, texto=texto,
            lida_paciente=True,
        )
        return JsonResponse({"status": "ok", "mensagem": _mensagem_dict(m)}, status=201)

    qs = list(MensagemPacientePortal.objects.filter(
        empresa_id=identidade.empresa_id, identidade=identidade))
    # marca as mensagens da equipe como lidas pelo paciente
    nao_lidas = [m.id for m in qs if m.autor == "equipe" and not m.lida_paciente]
    if nao_lidas:
        MensagemPacientePortal.objects.filter(id__in=nao_lidas).update(lida_paciente=True)
    return JsonResponse({"mensagens": [_mensagem_dict(m) for m in qs]})


# ══════════════════════════════════════════════════════════════════════════════
# LADO HOSPITAL (equipe) — alimenta a agenda e responde mensagens
# Sob /api/hospital/ → exige setor hospital + login da empresa (fluxo normal).
# ══════════════════════════════════════════════════════════════════════════════

from .access_control import (  # noqa: E402
    requer_setor, api_requer_feature, api_requer_permissao_modulo,
    requer_operacao_page, requer_permissao_modulo,
)
from django.views.decorators.http import require_http_methods  # noqa: E402
from django.views.decorators.csrf import ensure_csrf_cookie  # noqa: E402


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_operacao_page
@requer_permissao_modulo("hospital.administrativo")
def hospital_portal_paciente_page(request):
    """Tela do cockpit hospitalar para a equipe gerir o Portal do Paciente:
    criar/gerir agendamentos e responder as mensagens dos pacientes."""
    return render(request, "hospital_portal_paciente.html")


def _hosp_empresa(request):
    from .services.auth_session import empresa_autenticada_from_request
    emp = empresa_autenticada_from_request(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _identidade_para(empresa, identidade_id):
    return IdentidadePaciente.objects.filter(id=identidade_id, empresa=empresa).first()


@csrf_exempt
@require_http_methods(["GET", "POST"])
def hospital_agenda(request):
    """GET  /api/hospital/paciente-agenda — a equipe lista os agendamentos.
    POST /api/hospital/paciente-agenda — a equipe cria um agendamento (aparece no
    portal do paciente). Body: identidade_id, tipo, data_hora, especialidade…"""
    emp = _hosp_empresa(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)

    if request.method == "GET":
        qs = AgendamentoPaciente.objects.filter(empresa=emp).select_related("identidade")
        ident_id = request.GET.get("identidade_id")
        if ident_id:
            qs = qs.filter(identidade_id=ident_id)
        agora = timezone.now()
        items = []
        for a in qs.order_by("-data_hora")[:300]:
            d = _agendamento_dict(a)
            d["paciente_nome"] = a.identidade.nome
            d["identidade_id"] = a.identidade_id
            d["futuro"] = a.data_hora >= agora and a.status in ("agendado", "confirmado")
            items.append(d)
        return JsonResponse({"agendamentos": items})

    try:
        b = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    ident = _identidade_para(emp, b.get("identidade_id"))
    if not ident:
        return JsonResponse({"erro": "Paciente (identidade) não encontrado"}, status=404)
    dh = b.get("data_hora")
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(dh) if dh else None
    if dt is None:
        return JsonResponse({"erro": "data_hora inválida (ISO)"}, status=400)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    a = AgendamentoPaciente.objects.create(
        empresa=emp, identidade=ident,
        tipo=b.get("tipo", "consulta"), especialidade=b.get("especialidade", ""),
        profissional=b.get("profissional", ""), local=b.get("local", ""),
        data_hora=dt, observacoes=b.get("observacoes", ""),
    )
    return JsonResponse({"status": "ok", "id": a.id}, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def hospital_agenda_status(request, pk):
    """POST /api/hospital/paciente-agenda/<pk>/status {status} — realizar/cancelar."""
    emp = _hosp_empresa(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    try:
        novo = (json.loads(request.body or "{}").get("status") or "").strip()
    except Exception:
        novo = ""
    if novo not in ("realizado", "cancelado", "agendado", "confirmado"):
        return JsonResponse({"erro": "status inválido"}, status=400)
    n = AgendamentoPaciente.objects.filter(id=pk, empresa=emp).update(status=novo)
    if not n:
        return JsonResponse({"erro": "Agendamento não encontrado"}, status=404)
    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_http_methods(["GET"])
def hospital_pacientes_busca(request):
    """GET /api/hospital/pacientes-busca?q= — busca identidades do hospital por
    nome/CPF, para a equipe escolher ao criar um agendamento."""
    emp = _hosp_empresa(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    q = (request.GET.get("q") or "").strip()
    qs = IdentidadePaciente.objects.filter(empresa=emp)
    if q:
        qd = cpf_digitos(q)
        cond = Q(nome__icontains=q)
        if qd:
            cond |= Q(cpf__startswith=qd)
        qs = qs.filter(cond)
    itens = [{"id": i.id, "nome": i.nome, "cpf_mascarado": _mascara_cpf(i.cpf)}
             for i in qs.order_by("nome")[:20]]
    return JsonResponse({"pacientes": itens})


@csrf_exempt
@require_http_methods(["GET"])
def hospital_mensagens_threads(request):
    """GET /api/hospital/paciente-mensagens — caixa de entrada: um item por
    paciente que tem conversa, com a última mensagem e quantas não lidas."""
    emp = _hosp_empresa(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    threads = {}
    qs = (MensagemPacientePortal.objects.filter(empresa=emp)
          .select_related("identidade").order_by("criado_em"))
    for m in qs:
        t = threads.setdefault(m.identidade_id, {
            "identidade_id": m.identidade_id, "paciente_nome": m.identidade.nome,
            "ultima": "", "data": "", "nao_lidas": 0,
        })
        t["ultima"] = ("Você: " if m.autor == "equipe" else "") + m.texto[:60]
        t["data"] = m.criado_em.strftime("%d/%m/%Y %H:%M")
        if m.autor == "paciente" and not m.lida_equipe:
            t["nao_lidas"] += 1
    ordered = sorted(threads.values(), key=lambda x: (x["nao_lidas"] == 0, x["data"]), reverse=True)
    return JsonResponse({"threads": ordered})


@csrf_exempt
@require_http_methods(["GET"])
def hospital_mensagens_thread(request, identidade_id):
    """GET /api/hospital/paciente-mensagens/<identidade_id> — conversa completa de
    um paciente; marca as mensagens do paciente como lidas pela equipe."""
    emp = _hosp_empresa(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    ident = _identidade_para(emp, identidade_id)
    if not ident:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)
    qs = list(MensagemPacientePortal.objects.filter(empresa=emp, identidade=ident).order_by("criado_em"))
    nao_lidas = [m.id for m in qs if m.autor == "paciente" and not m.lida_equipe]
    if nao_lidas:
        MensagemPacientePortal.objects.filter(id__in=nao_lidas).update(lida_equipe=True)
    return JsonResponse({
        "paciente_nome": ident.nome,
        "mensagens": [_mensagem_dict(m) for m in qs],
    })


@csrf_exempt
@require_http_methods(["POST"])
def hospital_paciente_responder(request, identidade_id):
    """POST /api/hospital/paciente-mensagens/<identidade_id>/responder — a equipe
    responde a mensagem do paciente. Body: texto, autor_nome."""
    emp = _hosp_empresa(request)
    if not emp:
        return JsonResponse({"erro": "Não autenticado ou setor incorreto"}, status=401)
    ident = _identidade_para(emp, identidade_id)
    if not ident:
        return JsonResponse({"erro": "Paciente não encontrado"}, status=404)
    try:
        b = json.loads(request.body or "{}")
    except Exception:
        b = {}
    texto = (b.get("texto") or "").strip()
    if not texto:
        return JsonResponse({"erro": "Texto obrigatório"}, status=400)
    m = MensagemPacientePortal.objects.create(
        empresa=emp, identidade=ident, autor="equipe",
        autor_nome=b.get("autor_nome", "") or "Equipe do hospital",
        texto=texto[:2000], lida_equipe=True,
    )
    return JsonResponse({"status": "ok", "id": m.id}, status=201)
