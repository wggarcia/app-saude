import logging
import unicodedata
from functools import wraps
from django.shortcuts import redirect, render
from django.http import JsonResponse
from .planos import detalhes_pacote
from .services.auth_session import dono_autenticado_from_request

logger = logging.getLogger(__name__)

TODOS_SETORES = ("empresa", "farmacia", "hospital", "governo", "plano_saude")


# ─── Feature gating ──────────────────────────────────────────────────────────
#
# Uso em views:
#   @api_requer_feature("sst.esocial")
#   def minha_view(request): ...
#
# Verificação programática:
#   if empresa_tem_feature(request.empresa, "plano.coparticipacao"):
#       ...
#
# Verificação de limite:
#   if not dentro_do_limite(request.empresa, "max_unidades", unidades_atuais):
#       return JsonResponse({"erro": "Limite de unidades atingido"}, status=403)

def get_features(empresa) -> set:
    """Retorna o conjunto de features habilitadas para o plano desta empresa."""
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return set(pacote.get("features", []))


def get_limites(empresa) -> dict:
    """Retorna os limites numéricos do plano desta empresa."""
    pacote = detalhes_pacote(empresa.pacote_codigo)
    return pacote.get("limites", {})


def empresa_tem_feature(empresa, feature: str) -> bool:
    """Verifica se a empresa tem acesso à feature pelo seu plano ativo."""
    return feature in get_features(empresa)


def dentro_do_limite(empresa, chave: str, valor_atual: int) -> bool:
    """
    Verifica se um valor está dentro do limite do plano.
    Retorna True se não houver limite definido (ilimitado).
    Exemplos de chave: 'max_usuarios', 'max_unidades', 'max_funcionarios'.
    """
    limite = get_limites(empresa).get(chave)
    if limite is None:
        return True  # sem limite declarado → ilimitado
    return valor_atual < limite


def api_requer_feature(feature: str):
    """
    Decorator para views de API. Retorna 403 se a feature não estiver no plano.
    Inclui detalhes no response para o frontend mostrar modal de upgrade.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            if not empresa_tem_feature(empresa, feature):
                pacote = detalhes_pacote(empresa.pacote_codigo)
                return JsonResponse({
                    "erro": "Funcionalidade não disponível no seu plano atual.",
                    "feature_requerida": feature,
                    "plano_atual": pacote.get("label", empresa.pacote_codigo),
                    "setor": pacote.get("setor", ""),
                    "upgrade_necessario": True,
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requer_feature_pacote(feature: str, modulo_label: str = ""):
    """
    Decorator para views de página (HTML). Renderiza tela de upgrade se a
    feature não estiver no plano da empresa, em vez de retornar JSON.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return redirect("/login-empresa/")
            if not empresa_tem_feature(empresa, feature):
                pacote_atual = detalhes_pacote(empresa.pacote_codigo)
                return render(request, "upgrade_necessario.html", {
                    "modulo_label": modulo_label or feature,
                    "plano_atual": pacote_atual.get("label", empresa.pacote_codigo),
                    "feature_requerida": feature,
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def get_setor(empresa):
    """Return the sector/module for this empresa based on its plan."""
    setor = detalhes_pacote(empresa.pacote_codigo).get("setor", "empresa")
    # Safety fallback: TIPO_GOVERNO accounts must never land on empresa sector
    if setor == "empresa" and getattr(empresa, "tipo_conta", "empresa") == "governo":
        return "governo"
    return setor


def _destino_correto(setor):
    destinos = {
        "farmacia": "/farmacia/gestao/",
        "hospital": "/hospital/gestao/",
        "governo": "/dashboard-governo/",
        "plano_saude": "/plano-saude/gestao/",
    }
    return destinos.get(setor, "/dashboard-empresa/")


def requer_setor(*setores):
    """Decorator for page views. Redirects to correct home if wrong module."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return redirect("/login-empresa/")
            setor = get_setor(empresa)
            if setor not in setores:
                return redirect(_destino_correto(setor))
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def api_requer_setor(*setores):
    """Decorator for API views. Returns 403 JSON if wrong module."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            setor = get_setor(empresa)
            if setor not in setores:
                return JsonResponse(
                    {"erro": f"Módulo não disponível para este plano. Seu módulo: {setor}"},
                    status=403
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def requer_dono(view_func):
    """Decorator for operator-only page views. Requires DonoSaaS auth (owner_token cookie)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        dono = dono_autenticado_from_request(request)
        if not dono:
            empresa = getattr(request, "empresa", None)
            if empresa:
                return redirect(_destino_correto(get_setor(empresa)))
            return redirect("/operacao-central/")
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_dono(view_func):
    """Decorator for operator-only API views. Returns 403 for tenant requests."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        dono = dono_autenticado_from_request(request)
        if not dono:
            return JsonResponse({"erro": "Acesso restrito ao operador da plataforma"}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def _texto_normalizado(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    return texto.encode("ascii", "ignore").decode("ascii").lower().strip()


def _garantir_permissao_ti():
    try:
        from .models import RBACPermissao
        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo="plataforma_ti",
            defaults={
                "descricao": "Acesso exclusivo à Plataforma TI",
                "modulo": "ti",
            },
        )
        return permissao
    except Exception:
        return None


def _cargo_tem_marcador_rh(cargo):
    texto = _texto_normalizado(cargo)
    if not texto:
        return False
    palavras = set(texto.replace("/", " ").replace("-", " ").split())
    if "rh" in palavras:
        return True
    return any(
        trecho in texto
        for trecho in (
            "recursos humanos",
            "departamento pessoal",
            "gestao de pessoas",
            "gente e gestao",
            "people",
            "talentos",
        )
    )


def _principal_tem_permissao(empresa, principal, permissao):
    if not empresa or not principal:
        return False
    if principal.__class__.__name__ != "EmpresaUsuario":
        return False
    try:
        from .models import RBACAtribuicao
        return RBACAtribuicao.objects.filter(
            empresa=empresa,
            usuario_id=principal.id,
            permissao__codigo=permissao,
            ativo=True,
        ).exists()
    except Exception:
        return False


def _empresa_tem_responsavel_ti(empresa):
    if not empresa:
        return False
    try:
        from .models import RBACAtribuicao
        return RBACAtribuicao.objects.filter(
            empresa=empresa,
            permissao__codigo="plataforma_ti",
            ativo=True,
            usuario__ativo=True,
        ).exists()
    except Exception:
        return False


def pode_acessar_plataforma_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False

    principal = getattr(request, "principal", None) or empresa
    return principal_tem_acesso_ti(empresa, principal)


def principal_tem_acesso_ti(empresa, principal):
    return _principal_tem_permissao(empresa, principal, "plataforma_ti")


def acesso_plataforma_ti_em_bootstrap(request):
    return False


def requer_plataforma_ti_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not (pode_acessar_plataforma_ti(request) or _gerencia_usuario_empresa(request)):
            setor = get_setor(empresa)
            return render(
                request,
                "plataforma_ti_restrita.html",
                {
                    "empresa_nome": empresa.nome,
                    "return_url": _destino_correto(setor),
                    "return_label": {
                        "farmacia": "Gestão Farmácia",
                        "hospital": "Gestão Hospitalar",
                        "plano_saude": "Gestão Operadora",
                        "governo": "Painel Governo",
                    }.get(setor, "Central SST"),
                },
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_plataforma_ti(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not (pode_acessar_plataforma_ti(request) or _gerencia_usuario_empresa(request)):
            return JsonResponse({
                "erro": "Acesso restrito à Plataforma TI. Entre com um usuário de TI ou gerência autorizada.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── Acesso por módulo interno (credencial própria por área operacional) ─────
#
# Cada segmento é dividido em "módulos" (ex: Hospital = operacional/clínico/rede).
# Reaproveita o mesmo RBACPermissao/RBACAtribuicao já usado para "plataforma_ti",
# só que com um código por módulo em vez de um único código fixo.

MODULOS_POR_SETOR = {
    "hospital": [
        {"codigo": "hospital.operacional", "label": "Operacional",
         "funcao": "Enfermagem, Recepção, Faturamento",
         "area": "Leitos, Internações, Triagem, Prescrições, UTI, Alta, Faturamento, Farmácia Hospitalar, TISS"},
        {"codigo": "hospital.clinico", "label": "Clínico",
         "funcao": "Médico, Enfermagem Clínica, Laboratório, Imagem",
         "area": "Prontuário Eletrônico, Laboratório (LIS), Imagem (RIS/PACS), Bloco Cirúrgico"},
        {"codigo": "hospital.rede", "label": "Rede de Gestão",
         "funcao": "Gestão multi-unidade",
         "area": "Gestão de rede entre unidades hospitalares"},
    ],
    "farmacia": [
        {"codigo": "farmacia.pdv", "label": "PDV / Caixa",
         "funcao": "Atendente de balcão / Operador de caixa",
         "area": "Ponto de venda, abertura e fechamento de caixa"},
        {"codigo": "farmacia.gestao", "label": "Gestão / Farmacêutico",
         "funcao": "Farmacêutico responsável, Gerente",
         "area": "Estoque, Financeiro/DRE, Magistral, SNGPC, PBM, E-commerce/Delivery"},
        {"codigo": "farmacia.rede", "label": "Rede de Gestão",
         "funcao": "Gestão multi-loja",
         "area": "Gestão de rede entre lojas"},
    ],
    "empresa": [  # setor "empresa" = SST
        {"codigo": "sst.operacional", "label": "Operacional",
         "funcao": "Técnico de Segurança (SESMT), Auxiliar Administrativo",
         "area": "Agendamento de exames, ASOs, cadastro de funcionários, documentos, comunicação, bem-estar"},
        {"codigo": "sst.clinico", "label": "Clínico",
         "funcao": "Médico do Trabalho",
         "area": "Prontuário ocupacional, laudos técnicos, PPP, psicossocial, laboratório, rede credenciada"},
        {"codigo": "sst.gestao_conformidade", "label": "Gestão / Conformidade",
         "funcao": "RH, Gestor de SST",
         "area": "Relatórios, conformidade, eSocial, afastamentos, CAT, FAP, treinamentos, normas, EPI, riscos, PGR, CIPA, biometria"},
        {"codigo": "sst.administracao", "label": "Administração",
         "funcao": "Administrador, TI",
         "area": "Configurações do sistema"},
    ],
    "governo": [
        {"codigo": "governo.administrativo", "label": "Administrativo",
         "funcao": "Gestor Público, Planejamento",
         "area": "Programas, indicadores, planos de ação, orçamento, atos normativos, contratos"},
        {"codigo": "governo.vigilancia_acs", "label": "Vigilância / ACS",
         "funcao": "Agente de Vigilância, Agente Comunitário de Saúde",
         "area": "Vigilância epidemiológica e sanitária, visitas domiciliares, combate a endemias"},
        {"codigo": "governo.atencao_clinica", "label": "Atenção Clínica",
         "funcao": "Profissional de Saúde, Recepção UBS",
         "area": "Prontuário Eletrônico do Cidadão, e-SUS, Farmácia Básica, Faturamento SUS, Teleconsulta"},
        {"codigo": "governo.regulacao_urgencia", "label": "Regulação / Urgência",
         "funcao": "Regulador de Leitos, Equipe SAMU",
         "area": "Regulação de leitos, Urgência/SAMU, Produção, Previne Brasil"},
        {"codigo": "governo.secretaria_agendamento", "label": "Secretaria / Recepção",
         "funcao": "Secretário(a), Recepcionista, Auxiliar Administrativo",
         "area": "Agendamento de teleconsultas, painel de senha/chamada, reuniões institucionais, gestão de documentos"},
        {"codigo": "governo.epidemiologia", "label": "Epidemiologia",
         "funcao": "Epidemiologista, Analista de Vigilância em Saúde",
         "area": "Sala de situação, surtos, notificações compulsórias, panorama de diagnósticos, alertas ao cidadão"},
        {"codigo": "governo.farmacia", "label": "Farmácia",
         "funcao": "Farmacêutico Responsável",
         "area": "Farmácia Básica UBS, medicamentos de alto custo, almoxarifado farmacêutico"},
        {"codigo": "governo.laboratorio", "label": "Laboratório",
         "funcao": "Técnico de Laboratório, Biomédico",
         "area": "Solicitações e resultados de exames laboratoriais"},
    ],
    "plano_saude": [
        {"codigo": "plano.autorizacao", "label": "Autorização / Sinistro",
         "funcao": "Analista de Autorização",
         "area": "Autorização de guias com IA, análise de sinistro"},
        {"codigo": "plano.rede_credenciada", "label": "Rede Credenciada",
         "funcao": "Gestor de Rede Credenciada",
         "area": "Prestadores e credenciamento"},
        {"codigo": "plano.comercial", "label": "Comercial / Corretores",
         "funcao": "Corretor, Comercial",
         "area": "Corretoras e comissões"},
        {"codigo": "plano.compliance_ans", "label": "Compliance ANS",
         "funcao": "Compliance, Regulatório",
         "area": "Obrigações ANS, DIOPS, SIB"},
    ],
}

MODULOS_LABEL = {
    m["codigo"]: m["label"]
    for modulos in MODULOS_POR_SETOR.values()
    for m in modulos
}

MODULOS_INFO = {
    m["codigo"]: m
    for modulos in MODULOS_POR_SETOR.values()
    for m in modulos
}


def _garantir_permissao_modulo(codigo):
    try:
        from .models import RBACPermissao
        modulo = codigo.split(".", 1)[0]
        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo=codigo,
            defaults={"descricao": MODULOS_LABEL.get(codigo, codigo), "modulo": modulo},
        )
        return permissao
    except Exception:
        return None


def _modulo_sem_rbac_configurado(empresa, codigo_modulo):
    """Mesma lógica de graceful-degrade do meus_modulos(): se a empresa ainda
    não configurou NENHUMA atribuição granular pro setor desse código, trata
    como "RBAC ainda não configurado" e libera, em vez de bloquear a tela real
    de quem nunca recebeu (nem precisava receber) uma RBACAtribuicao explícita."""
    setor = None
    for setor_key, modulos in MODULOS_POR_SETOR.items():
        if any(m["codigo"] == codigo_modulo for m in modulos):
            setor = setor_key
            break
    if setor is None:
        return False
    codigos_setor = [m["codigo"] for m in MODULOS_POR_SETOR.get(setor, [])]
    return not _setor_tem_rbac_configurado(empresa, codigos_setor)


def principal_tem_modulo(empresa, principal, codigo_modulo):
    if principal is None or principal == empresa or principal_e_gerencia_principal(principal):
        return True
    if _principal_tem_permissao(empresa, principal, codigo_modulo):
        return True
    return _modulo_sem_rbac_configurado(empresa, codigo_modulo)


def principal_tem_algum_modulo(empresa, principal, codigos_modulo):
    """Igual a principal_tem_modulo, mas aceita uma lista de códigos (OR) —
    usado quando uma mesma tela pode ser liberada por mais de um módulo
    (ex: código amplo legado E código granular novo)."""
    if principal is None or principal == empresa or principal_e_gerencia_principal(principal):
        return True
    if any(_principal_tem_permissao(empresa, principal, codigo) for codigo in codigos_modulo):
        return True
    return any(_modulo_sem_rbac_configurado(empresa, codigo) for codigo in codigos_modulo)


def principal_e_gerencia_principal(principal):
    """Versão sem request: gerência é EmpresaUsuario com perfil 'admin'/'gestor',
    is_admin, ou (quando o perfil granular não está definido) inferência pelo
    cargo — mesmo fallback usado por principal_e_gerencia(request)."""
    if principal is None:
        return False
    if principal.__class__.__name__ != "EmpresaUsuario":
        return True  # é a conta principal da Empresa
    if getattr(principal, "is_admin", False):
        return True
    perfil = _perfil_usuario(principal)
    if perfil in ("admin", "gestor"):
        return True
    if perfil is not None:
        return False  # perfil definido explicitamente e não é gerência
    return _cargo_indica_gerencia(getattr(principal, "cargo", ""))


def requer_permissao_modulo(*codigos):
    """
    Decorator para views de página: se a sessão atual não tiver a permissão de
    NENHUM dos módulos informados (e não for gerência), renderiza a tela de
    credencial em vez do conteúdo — sem fricção quando já autorizado, igual ao
    padrão de requer_plataforma_ti_page.

    Aceita múltiplos códigos (OR) para permitir liberar a mesma tela tanto
    pelo código amplo legado quanto por um código granular mais novo, sem
    revogar nenhum acesso já concedido.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return redirect("/login-empresa/")
            principal = getattr(request, "principal", None) or empresa
            if principal_tem_algum_modulo(empresa, principal, codigos):
                return view_func(request, *args, **kwargs)
            codigo_principal = codigos[0]
            info = MODULOS_INFO.get(codigo_principal, {})
            return render(request, "modulo_credencial.html", {
                "codigo_modulo": codigo_principal,
                "modulo_label": info.get("label", codigo_principal),
                "modulo_funcao": info.get("funcao", ""),
                "modulo_area": info.get("area", ""),
                "return_url": request.path,
            }, status=403)
        return wrapper
    return decorator


def api_requer_permissao_modulo(*codigos):
    """Decorator para views de API: 403 JSON em vez de tela de credencial.
    Aceita múltiplos códigos (OR) — ver requer_permissao_modulo."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            principal = getattr(request, "principal", None) or empresa
            if not principal_tem_algum_modulo(empresa, principal, codigos):
                codigo_principal = codigos[0]
                return JsonResponse({
                    "erro": "Acesso restrito a este módulo.",
                    "codigo_modulo": codigo_principal,
                    "modulo_label": MODULOS_LABEL.get(codigo_principal, codigo_principal),
                }, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def meus_modulos(request):
    """Lista de códigos de módulo que o principal atual já tem acesso, para o gate client-side de abas."""
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return []
    setor = get_setor(empresa)
    codigos_setor = [m["codigo"] for m in MODULOS_POR_SETOR.get(setor, [])]
    principal = getattr(request, "principal", None) or empresa
    if principal_e_gerencia_principal(principal):
        return codigos_setor
    if codigos_setor and not _setor_tem_rbac_configurado(empresa, codigos_setor):
        # Ninguém na empresa recebeu ainda nenhuma atribuição granular pra esse
        # setor — trata como "RBAC granular ainda não configurado" e libera
        # tudo, em vez de esconder o menu inteiro por engano.
        return codigos_setor
    return [
        codigo for codigo in codigos_setor
        if _principal_tem_permissao(empresa, principal, codigo)
    ]


def _setor_tem_rbac_configurado(empresa, codigos_setor):
    try:
        from .models import RBACAtribuicao
        return RBACAtribuicao.objects.filter(
            empresa=empresa,
            permissao__codigo__in=codigos_setor,
            ativo=True,
        ).exists()
    except Exception:
        return False


def api_meus_modulos(request):
    """GET /api/permissoes/meus-modulos — usado pelo gate client-side de abas (ex: governo_gestao.html)."""
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    return JsonResponse({"modulos": meus_modulos(request)})


def _principal_gestor_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    principal = getattr(request, "principal", None) or empresa
    if principal == empresa:
        return True
    if principal.__class__.__name__ != "EmpresaUsuario":
        return False
    if getattr(principal, "is_admin", False):
        return True

    return _cargo_tem_marcador_rh(getattr(principal, "cargo", ""))


def _cargo_indica_gerencia(cargo):
    """Inferência de gerência pelo cargo (texto livre) — fallback quando o
    perfil granular do EmpresaUsuario não está definido. Compartilhada por
    principal_e_gerencia_principal() e principal_e_gerencia() para que as
    duas nunca divirjam sobre quem é gerência."""
    texto = _texto_normalizado(cargo)
    if not texto:
        return False
    palavras = set(texto.replace("/", " ").replace("-", " ").split())
    marcadores = {
        "gerencia", "gerente", "gestor", "coordenador", "supervisor",
        "diretor", "diretoria", "lider", "lideranca", "administrador",
    }
    if palavras & marcadores:
        return True
    return any(
        trecho in texto
        for trecho in ("gerente", "gestor", "diretor", "lider de", "head",
                       "chief", "coordenacao", "supervisao")
    )


def _perfil_usuario(principal) -> str | None:
    """Retorna o perfil granular do EmpresaUsuario, ou None se não aplicável."""
    if principal.__class__.__name__ != "EmpresaUsuario":
        return None
    return getattr(principal, "perfil", None) or None


def principal_e_gerencia(request):
    """
    Perfil de gerência:
      - conta principal da empresa
      - perfil admin ou gestor (campo granular)
      - is_admin legacy
      - fallback: inferência pelo cargo (texto)
    """
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False

    principal = getattr(request, "principal", None) or empresa
    if principal == empresa:
        return True
    if getattr(principal, "is_admin", False):
        return True

    perfil = _perfil_usuario(principal)
    if perfil in ("admin", "gestor"):
        return True
    if perfil is not None:
        return False  # perfil definido explicitamente e não é gerência

    # Fallback legacy: inferência pelo cargo (texto livre)
    return _cargo_indica_gerencia(getattr(principal, "cargo", ""))


def principal_e_rh(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False

    principal = getattr(request, "principal", None) or empresa
    if principal == empresa:
        return False
    if getattr(principal, "is_admin", False):
        return False
    if principal.__class__.__name__ != "EmpresaUsuario":
        return False

    perfil = _perfil_usuario(principal)
    if perfil == "rh":
        return True
    if perfil is not None:
        return False  # perfil definido explicitamente e não é RH

    if principal_e_gerencia(request):
        return False
    return _cargo_tem_marcador_rh(getattr(principal, "cargo", ""))


def principal_e_ti(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    principal = getattr(request, "principal", None) or empresa

    perfil = _perfil_usuario(principal)
    if perfil in ("admin", "ti"):
        return True
    if perfil is not None:
        return principal_tem_acesso_ti(empresa, principal)  # RBAC ainda vale

    return principal_tem_acesso_ti(empresa, principal)


def principal_e_operacao(request):
    empresa = getattr(request, "empresa", None)
    if not empresa:
        return False
    principal = getattr(request, "principal", None) or empresa

    perfil = _perfil_usuario(principal)
    if perfil in ("medico", "tecnico_sesmt", "auxiliar"):
        return True
    if perfil in ("admin", "gestor", "rh", "ti"):
        return False

    # Fallback legacy
    if principal_e_gerencia(request):
        return False
    if principal_e_rh(request):
        return False
    if principal_e_ti(request):
        return False
    return True


def principal_pode_operacao_setorial(request):
    """
    Acesso operacional setorial:
      - Operação (usuário de linha) pode operar o setor
      - Gerência pode operar e supervisionar o setor
    RH e TI ficam fora da operação por padrão (least privilege).
    """
    return principal_e_operacao(request) or principal_e_gerencia(request)


def _destino_ti_por_setor(setor):
    if setor == "governo":
        return "/governo/plataforma/"
    return "/ti/"


def _gerencia_usuario_empresa(request):
    if not principal_e_gerencia(request):
        return False
    principal = getattr(request, "principal", None)
    return bool(principal and principal.__class__.__name__ == "EmpresaUsuario")


def perfil_principal(request):
    principal = getattr(request, "principal", None)
    perfil = _perfil_usuario(principal) if principal else None
    if perfil:
        return perfil  # retorna o perfil granular diretamente
    # Fallback legacy
    if principal_e_gerencia(request):
        return "gerencia"
    if principal_e_rh(request):
        return "rh"
    if principal_e_ti(request):
        return "ti"
    return "operacao"


def destino_por_perfil(request, empresa=None):
    empresa_resolvida = empresa or getattr(request, "empresa", None)
    if not empresa_resolvida:
        return "/login-empresa/"
    setor = get_setor(empresa_resolvida)
    perfil = perfil_principal(request)
    if perfil == "gerencia":
        principal = getattr(request, "principal", None) or empresa_resolvida
        if principal == empresa_resolvida:
            return _destino_correto(setor)
        return "/gerencia/"
    if perfil == "rh":
        return "/rh/"
    if perfil == "ti":
        return _destino_ti_por_setor(setor)
    return _destino_correto(setor)


def principal_pode_configurar_ti(request):
    """
    RH/Gerência pode cadastrar e gerenciar credenciais TI.
    """
    return _principal_gestor_ti(request) or principal_e_gerencia(request) or principal_e_ti(request)


def modulos_governo_visibilidade(request, setor_resolvido=None):
    """
    Flags de visibilidade do menu do setor governo, por módulo (RBAC granular).
    Sempre True para gerência/conta principal (mesmo comportamento de hoje —
    ninguém perde acesso). Para sub-usuários com perfil restrito, só fica True
    o que estiver de fato concedido via RBACAtribuicao — usado para que cada
    ambiente (médico, secretaria, epidemiologia, farmácia, etc.) veja só o
    seu próprio menu, ao estilo dos concorrentes (TOTVS/Tasy).
    """
    empresa = getattr(request, "empresa", None)
    setor = setor_resolvido or (get_setor(empresa) if empresa else None)
    flags = {
        "gov_ver_administrativo": True,
        "gov_ver_vigilancia_acs": True,
        "gov_ver_atencao_clinica": True,
        "gov_ver_regulacao_urgencia": True,
        "gov_ver_secretaria": True,
        "gov_ver_epidemiologia": True,
        "gov_ver_farmacia": True,
        "gov_ver_laboratorio": True,
    }
    if not empresa or setor != "governo":
        return flags
    try:
        ativos = set(meus_modulos(request))
        flags = {
            "gov_ver_administrativo": "governo.administrativo" in ativos,
            "gov_ver_vigilancia_acs": "governo.vigilancia_acs" in ativos,
            "gov_ver_atencao_clinica": "governo.atencao_clinica" in ativos,
            "gov_ver_regulacao_urgencia": "governo.regulacao_urgencia" in ativos,
            "gov_ver_secretaria": "governo.secretaria_agendamento" in ativos,
            "gov_ver_epidemiologia": "governo.epidemiologia" in ativos,
            "gov_ver_farmacia": "governo.farmacia" in ativos,
            "gov_ver_laboratorio": "governo.laboratorio" in ativos,
        }
    except Exception:
        logger.exception("Falha ao calcular visibilidade de módulos do governo")
    return flags


def modulos_hospital_visibilidade(request, setor_resolvido=None):
    """Flags de visibilidade do menu do setor hospital, por módulo (RBAC granular).
    Mesmo padrão de modulos_governo_visibilidade — ver docstring lá."""
    empresa = getattr(request, "empresa", None)
    setor = setor_resolvido or (get_setor(empresa) if empresa else None)
    flags = {
        "hosp_ver_operacional": True,
        "hosp_ver_clinico": True,
        "hosp_ver_rede": True,
    }
    if not empresa or setor != "hospital":
        return flags
    try:
        ativos = set(meus_modulos(request))
        flags = {
            "hosp_ver_operacional": "hospital.operacional" in ativos,
            "hosp_ver_clinico": "hospital.clinico" in ativos,
            "hosp_ver_rede": "hospital.rede" in ativos,
        }
    except Exception:
        logger.exception("Falha ao calcular visibilidade de módulos do hospital")
    return flags


def modulos_farmacia_visibilidade(request, setor_resolvido=None):
    """Flags de visibilidade do menu do setor farmácia, por módulo (RBAC granular).
    Mesmo padrão de modulos_governo_visibilidade — ver docstring lá."""
    empresa = getattr(request, "empresa", None)
    setor = setor_resolvido or (get_setor(empresa) if empresa else None)
    flags = {
        "farm_ver_pdv": True,
        "farm_ver_gestao": True,
        "farm_ver_rede": True,
    }
    if not empresa or setor != "farmacia":
        return flags
    try:
        ativos = set(meus_modulos(request))
        flags = {
            "farm_ver_pdv": "farmacia.pdv" in ativos,
            "farm_ver_gestao": "farmacia.gestao" in ativos,
            "farm_ver_rede": "farmacia.rede" in ativos,
        }
    except Exception:
        logger.exception("Falha ao calcular visibilidade de módulos da farmácia")
    return flags


def modulos_plano_saude_visibilidade(request, setor_resolvido=None):
    """Flags de visibilidade do menu do setor plano_saude, por módulo (RBAC granular).
    Mesmo padrão de modulos_governo_visibilidade — ver docstring lá."""
    empresa = getattr(request, "empresa", None)
    setor = setor_resolvido or (get_setor(empresa) if empresa else None)
    flags = {
        "ps_ver_autorizacao": True,
        "ps_ver_rede_credenciada": True,
        "ps_ver_comercial": True,
        "ps_ver_compliance_ans": True,
    }
    if not empresa or setor != "plano_saude":
        return flags
    try:
        ativos = set(meus_modulos(request))
        flags = {
            "ps_ver_autorizacao": "plano.autorizacao" in ativos,
            "ps_ver_rede_credenciada": "plano.rede_credenciada" in ativos,
            "ps_ver_comercial": "plano.comercial" in ativos,
            "ps_ver_compliance_ans": "plano.compliance_ans" in ativos,
        }
    except Exception:
        logger.exception("Falha ao calcular visibilidade de módulos do plano de saúde")
    return flags


def contexto_navegacao_setorial(request, setor=None):
    """
    Contexto padrão de navegação por perfil para templates setoriais.
    """
    empresa = getattr(request, "empresa", None)
    setor_resolvido = setor or (get_setor(empresa) if empresa else "empresa")

    acesso_ti = principal_e_ti(request)
    acesso_gerencia = principal_e_gerencia(request)
    acesso_rh = principal_e_rh(request) or acesso_gerencia

    ctx = {
        "setor_atual": setor_resolvido,
        "perfil_principal": perfil_principal(request),
        "acesso_ti": acesso_ti,
        "acesso_gerencia": acesso_gerencia,
        "acesso_rh": acesso_rh,
        "acesso_operacao": principal_e_operacao(request),
        "mostrar_link_ti": acesso_ti or acesso_gerencia,
        "mostrar_link_rh": acesso_rh,
        "mostrar_aba_gerencia": acesso_gerencia,
        "portal_ti_url": _destino_ti_por_setor(setor_resolvido),
        "gerencia_url": "/gerencia/",
        "rh_url": "/rh/",
    }
    if setor_resolvido == "governo":
        ctx.update(modulos_governo_visibilidade(request, setor_resolvido))
    elif setor_resolvido == "hospital":
        ctx.update(modulos_hospital_visibilidade(request, setor_resolvido))
    elif setor_resolvido == "farmacia":
        ctx.update(modulos_farmacia_visibilidade(request, setor_resolvido))
    elif setor_resolvido == "plano_saude":
        ctx.update(modulos_plano_saude_visibilidade(request, setor_resolvido))
    return ctx


def requer_gerencia_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not principal_e_gerencia(request):
            return redirect(destino_por_perfil(request, empresa))
        return view_func(request, *args, **kwargs)
    return wrapper


def requer_rh_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")
        if not (principal_e_rh(request) or principal_e_gerencia(request)):
            return redirect(destino_por_perfil(request, empresa))
        return view_func(request, *args, **kwargs)
    return wrapper


def requer_operacao_page(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return redirect("/login-empresa/")

        if principal_e_gerencia(request) or principal_e_operacao(request):
            return view_func(request, *args, **kwargs)

        return redirect(destino_por_perfil(request, empresa))
    return wrapper


def api_requer_gerencia(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not principal_e_gerencia(request):
            return JsonResponse({
                "erro": "Acesso restrito à gerência.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_operacao_ou_gerencia(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not principal_pode_operacao_setorial(request):
            return JsonResponse({
                "erro": "Acesso restrito à operação/gerência.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def api_requer_plataforma_ti_ou_gestor(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = getattr(request, "empresa", None)
        if not empresa:
            return JsonResponse({"erro": "Não autenticado"}, status=401)
        if not (pode_acessar_plataforma_ti(request) or _principal_gestor_ti(request) or _gerencia_usuario_empresa(request)):
            return JsonResponse({
                "erro": "Acesso restrito à TI ou gestão autorizada.",
            }, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def requer_permissao(permissao):
    """RBAC decorator — checks RBACAtribuicao for the authenticated principal."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            empresa = getattr(request, "empresa", None)
            if not empresa:
                return JsonResponse({"erro": "Não autenticado"}, status=401)
            principal = getattr(request, "principal", None)
            if principal:
                try:
                    from .models import RBACAtribuicao
                    tem = RBACAtribuicao.objects.filter(
                        empresa=empresa,
                        usuario_id=principal.id,
                        permissao__codigo=permissao,
                        ativo=True,
                    ).exists()
                    if not tem:
                        return JsonResponse({"erro": f"Permissão necessária: {permissao}"}, status=403)
                except Exception as exc:
                    from django.db import ProgrammingError
                    if isinstance(exc.__cause__, ProgrammingError) or isinstance(exc, ProgrammingError):
                        # Tabela RBAC ainda não existe (migration incompleta) — deixa passar
                        pass
                    else:
                        logger.error("RBAC check falhou permissao=%s: %s", permissao, exc)
                        return JsonResponse({"erro": "Erro ao verificar permissão"}, status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
