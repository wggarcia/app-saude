from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.db.models import Count
from .utils import probabilidade_doenca

from .models import RegistroSintoma, Empresa, AlertaGovernamental, DispositivoPushPublico
from .utils_cidades import buscar_coordenada
from .utils import obter_localizacao
from django.conf import settings
from api.utils_ia import classificar_padrao
from api.utils_geo import obter_endereco
from api.utils_auth import validar_token
from api.models import Empresa, RegistroSintoma
from api.epidemiologia import _build_disease_probabilities
from django.db.models import Count, Avg, Q
from django.db.models.functions import TruncDate
from django.contrib.auth.hashers import make_password
from collections import defaultdict

# ============================
# 🧠 IA GLOBAL (MOVER PRA CIMA)
# ============================

historico = defaultdict(list)


def site_principal(request):
    host = request.get_host().split(":")[0].lower()
    if host.startswith("empresa."):
        return tela_login_empresa(request)
    if host.startswith("governo."):
        return tela_login_governo(request)
    if host.startswith("admin."):
        return redirect("/operacao-central/")
    return render(request, "site_principal.html")


def apresentacao_comercial(request):
    return render(request, "apresentacao.html")


LEGAL_DOCUMENTS = {
    "privacidade": {
        "title": "Politica de Privacidade",
        "subtitle": "Como o SolusCRT Saude trata dados no app populacional e na plataforma SaaS.",
        "sections": [
            ("Resumo executivo", "O SolusCRT Saude utiliza dados informados voluntariamente pela populacao, dados tecnicos do aparelho, localizacao necessaria para georreferenciar sinais de saude e informacoes de contas empresariais/governamentais. O objetivo e monitoramento epidemiologico, seguranca, operacao da plataforma e comunicacao publica."),
            ("Dados de saude e localizacao", "Sinais de sintomas e localizacao podem ser considerados dados sensiveis ou capazes de revelar informacoes sensiveis. Por isso, o produto deve operar com minimizacao, finalidade especifica, controle de acesso, anonimização ou agregacao sempre que possivel."),
            ("Categorias tratadas", "Podem ser tratados sintomas selecionados, coordenadas de localizacao atual, identificador tecnico do aparelho, data e hora do envio, regiao aproximada, tokens de notificacao, dados de conta corporativa e registros de auditoria."),
            ("Base e finalidade", "O tratamento ocorre para operacao do app, seguranca, prevencao a fraude, exibicao de radar local, emissao de alertas, inteligencia epidemiologica agregada, cumprimento contratual e atendimento a direitos dos titulares."),
            ("Uso dos dados", "Os dados colaborativos alimentam mapas de risco, indicadores agregados, alertas regionais e modelos de apoio a decisao. Eles nao substituem diagnostico medico, notificacao oficial ou avaliacao profissional."),
            ("Compartilhamento", "Empresas e governos visualizam informacoes conforme contrato, perfil de acesso e camada de permissao. A plataforma deve priorizar agregados territoriais e evitar exposicao de individuo identificavel."),
            ("Retencao e descarte", "Dados sao mantidos pelo tempo necessario para as finalidades declaradas, cumprimento contratual, auditoria, seguranca, defesa de direitos e obrigacoes legais ou regulatorias aplicaveis."),
            ("Direitos do titular", "Titulares podem solicitar informacoes, correcao, exclusao quando aplicavel e esclarecimentos sobre tratamento de dados pelos canais oficiais da SolusCRT."),
            ("Seguranca", "A plataforma utiliza segregacao de ambientes, controle de acesso, trilhas de auditoria, protecoes antifraude e boas praticas de seguranca para reduzir riscos de acesso indevido, manipulacao ou exposicao desnecessaria."),
        ],
    },
    "termos": {
        "title": "Termos de Uso",
        "subtitle": "Regras de uso do app, do site e dos ambientes privados.",
        "sections": [
            ("Natureza informativa", "O SolusCRT Saude oferece monitoramento e inteligencia epidemiologica. O app nao realiza diagnostico, prescricao, triagem medica individual ou substituicao de atendimento profissional."),
            ("Envio responsavel", "Usuarios devem enviar sintomas reais, de boa-fe e apenas quando houver relacao com sua condicao atual. Envios repetidos, automatizados ou fraudulentos podem ser filtrados ou bloqueados."),
            ("Ambientes privados", "Acessos empresariais, governamentais e administrativos sao exclusivos para clientes e operadores autorizados. Tentativas de acesso indevido podem ser registradas e bloqueadas."),
            ("Uso proibido", "E proibido tentar burlar controles de seguranca, automatizar envios indevidos, inserir informacoes falsas, acessar area contratual sem autorizacao, realizar engenharia reversa ou usar a plataforma para finalidade ilegal, discriminatoria ou abusiva."),
            ("Contas e credenciais", "Credenciais sao pessoais ou institucionais conforme contrato. O usuario ou cliente e responsavel por preservar senhas, dispositivos autorizados e politicas internas de acesso."),
            ("Disponibilidade", "A plataforma depende de internet, servicos de nuvem, APIs, fontes oficiais e permissao de localizacao. Podem ocorrer indisponibilidades temporarias ou degradacao de dados externos."),
            ("Responsabilidade", "Decisoes operacionais e institucionais devem considerar contexto tecnico, validacao humana e protocolos aplicaveis de saude publica."),
            ("Propriedade intelectual", "Marcas, interfaces, modelos, organizacao da plataforma, documentos, codigos, paineis e materiais do SolusCRT Saude pertencem aos seus titulares e sao licenciados nos limites contratados."),
            ("Contratacao B2B e B2G", "Planos empresariais, governamentais, limites de usuarios, dispositivos, suporte, integracoes, SLA e valores podem ser definidos em proposta, contrato, termo de adesao ou instrumento especifico."),
        ],
    },
    "seguranca-lgpd": {
        "title": "Seguranca, LGPD e Governanca",
        "subtitle": "Controles para proteger dados, acessos e confianca institucional.",
        "sections": [
            ("Principios", "A plataforma deve seguir finalidade, adequacao, necessidade, seguranca, prevencao, transparencia e responsabilizacao no tratamento de dados pessoais."),
            ("Segregacao de ambientes", "Empresa, governo e operacao administrativa sao separados por fluxo de login, permissao, sessao, auditoria e dominio/subdominio quando contratado."),
            ("Controles antifraude", "O app e o backend utilizam controles por aparelho, rede, repeticao, qualidade do sinal e localizacao atual para reduzir manipulacao de focos."),
            ("Protecao de acesso", "A plataforma adota controle de sessao, autorizacao por perfil, limite de dispositivos contratados, bloqueios de uso simultaneo quando aplicavel e revogacao de acessos."),
            ("Dados sensiveis", "Sinais de saude sao tratados com cautela, priorizando agregacao, minimizacao, separacao por finalidade e exibicao territorial adequada ao perfil autorizado."),
            ("Auditoria", "Acoes institucionais, alertas governamentais e operacoes administrativas devem ter rastreabilidade, usuario responsavel, data e contexto."),
            ("Incidentes", "Eventos de seguranca podem acionar processos de investigacao, mitigacao, registro, comunicacao a clientes e titulares quando aplicavel, e melhoria de controles."),
            ("Compromisso continuo", "A governanca do SolusCRT Saude e mantida como um processo permanente, com melhoria de controles, revisao de acessos, atualizacao documental e alinhamento aos requisitos aplicaveis de protecao de dados, saude digital e contratos institucionais."),
        ],
    },
    "metodologia": {
        "title": "Metodologia Epidemiologica",
        "subtitle": "Como o SolusCRT separa sinal precoce, fonte oficial e decisao operacional.",
        "sections": [
            ("Sinal colaborativo", "O app coleta sinais de sintomas em tempo real. Esses sinais indicam tendencia e risco territorial, mas nao equivalem a caso confirmado."),
            ("Fonte oficial", "Dados oficiais e institucionais, como bases publicas e sistemas de saude, devem ser tratados separadamente, preferencialmente em agregados, com data de coleta, fonte, versao e regra de processamento."),
            ("Indicadores", "A plataforma usa crescimento, incidencia por 100 mil habitantes, predominancia de sintomas, serie temporal e reducao gradual quando deixam de entrar novos sinais."),
            ("IA como apoio", "Modelos de IA apoiam classificacao e priorizacao, mas nao substituem equipe tecnica, vigilancia epidemiologica ou decisao institucional."),
            ("Transparencia", "Paineis devem indicar quando um dado e colaborativo, oficial, inferido ou indisponivel, evitando conclusoes falsas ou comunicacao alarmista."),
        ],
    },
}


def documento_publico(request, slug):
    documento = LEGAL_DOCUMENTS.get(slug)
    if not documento:
        return redirect("/")
    return render(request, "documento_publico.html", {"documento": documento})

STATE_ALIASES = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapa",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceara",
    "DF": "Distrito Federal",
    "ES": "Espirito Santo",
    "GO": "Goias",
    "MA": "Maranhao",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Para",
    "PB": "Paraiba",
    "PR": "Parana",
    "PE": "Pernambuco",
    "PI": "Piaui",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondonia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "Sao Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _state_terms(value):
    raw = (value or "").strip()
    if not raw:
        return []
    upper = raw.upper()
    terms = {raw, upper}
    alias = STATE_ALIASES.get(upper)
    if alias:
        terms.add(alias)
    for uf, name in STATE_ALIASES.items():
        if raw.lower() == name.lower():
            terms.add(uf)
            terms.add(name)
    return list(terms)


JANELA_ESTABILIDADE_FOCO_DIAS = 10
JANELA_DECAIMENTO_FOCO_DIAS = 30
PESO_MINIMO_FOCO_PUBLICO = 0.01


def _peso_temporal_publico(day, agora=None):
    agora = agora or timezone.now()
    if not day:
        return 1.0
    if hasattr(day, "date"):
        day = day.date()
    dias = max((agora.date() - day).days, 0)
    if dias <= JANELA_ESTABILIDADE_FOCO_DIAS:
        return 1.0
    if dias >= JANELA_DECAIMENTO_FOCO_DIAS:
        return PESO_MINIMO_FOCO_PUBLICO
    janela_queda = JANELA_DECAIMENTO_FOCO_DIAS - JANELA_ESTABILIDADE_FOCO_DIAS
    dias_em_queda = dias - JANELA_ESTABILIDADE_FOCO_DIAS
    queda = dias_em_queda / janela_queda
    return round(max(PESO_MINIMO_FOCO_PUBLICO, 1 - (queda * (1 - PESO_MINIMO_FOCO_PUBLICO))), 3)


def _indice_temporal_publico(queryset, agora=None):
    agora = agora or timezone.now()
    rows = (
        queryset.annotate(day=TruncDate("data_registro"))
        .values("day")
        .annotate(total=Count("id"))
    )
    return round(sum(item["total"] * _peso_temporal_publico(item["day"], agora) for item in rows), 2)


def _nivel_por_indice_publico(indice, crescimento=0):
    if indice >= 500 or crescimento >= 60:
        return "alto"
    if indice >= 180 or crescimento >= 25:
        return "moderado"
    if indice >= 60 or crescimento > 0:
        return "atencao"
    return "baixo"


def _nivel_local_por_indice_publico(indice, crescimento=0):
    if indice >= 45 or crescimento >= 60:
        return "alto"
    if indice >= 20 or crescimento >= 25:
        return "moderado"
    if indice >= 8 or crescimento > 0:
        return "atencao"
    return "baixo"

def calcular_previsao(cidade, estado, total):

    chave = f"{cidade}_{estado}"
    hist = historico[chave]

    # 🔥 SALVA O DADO ATUAL (ESSA LINHA FALTAVA)
    hist.append(total)

    # mantém últimos 5
    if len(hist) > 5:
        hist.pop(0)

    if len(hist) < 2:
        return "SEM DADOS", 0

    atual = hist[-1]
    anterior = hist[-2]

    if anterior == 0:
        return "ESTÁVEL", 0

    crescimento = ((atual - anterior) / anterior) * 100

    if crescimento > 70:
        return "EXPLOSÃO IMINENTE", crescimento
    elif crescimento > 30:
        return "FORTE CRESCIMENTO", crescimento
    elif crescimento > 10:
        return "TENDÊNCIA DE ALTA", crescimento
    elif crescimento < -10:
        return "QUEDA", crescimento
    else:
        return "ESTÁVEL", crescimento


import json
import uuid
import jwt
import random
from datetime import timedelta
from django.utils import timezone
from .utils import (
    calcular_risco,
    classificar_crescimento,
    analisar_doencas,
    risco_por_doenca
)




# ================= LOGIN =================

def tela_login(request):
    return render(request, 'login_empresa.html')


def tela_login_empresa(request):
    return render(request, 'login_empresa.html')


def tela_login_governo(request):
    return render(request, 'login_governo.html')


def verificar_acesso(request):
    token = request.headers.get("Authorization")
    if not token:
        return None

    try:
        token = token.replace("Bearer ", "")
        dados = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return Empresa.objects.get(id=dados["empresa_id"])
    except:
        return None


def dashboard(request):
    return render(request, "dashboard.html")


def dashboard_farmacia(request):
    return render(request, "dashboard_farmacia.html")


# ================= TOKEN =================

def validar_token(request):
    auth = request.headers.get("Authorization")

    if not auth:
        return None, JsonResponse({"erro": "não autorizado"}, status=403)

    try:
        token = auth.split(" ")[1]
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        return payload["empresa_id"], None
    except:
        return None, JsonResponse({"erro": "token inválido"}, status=403)


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _device_id_request(request):
    return (request.headers.get("X-Device-Id") or "").strip()[:120] or None


def _score_suspeita(empresa, request, dados):
    agora = timezone.now()
    ip = _client_ip(request)
    device_id = _device_id_request(request)
    janela_10m = agora - timedelta(minutes=10)
    janela_15m = agora - timedelta(minutes=15)
    filtros_recentes = RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=janela_10m)
    filtros_duplicados = RegistroSintoma.objects.filter(empresa=empresa, data_registro__gte=janela_15m)

    score = 1.0
    motivos = []

    if ip:
        volume_ip = filtros_recentes.filter(ip=ip).count()
        if volume_ip >= 20:
            score -= 0.55
            motivos.append("volume_ip_extremo")
        elif volume_ip >= 10:
            score -= 0.25
            motivos.append("volume_ip_alto")

    if device_id:
        volume_device = filtros_recentes.filter(device_id=device_id).count()
        if volume_device >= 18:
            score -= 0.45
            motivos.append("volume_device_extremo")
        elif volume_device >= 8:
            score -= 0.2
            motivos.append("volume_device_alto")

    duplicate_filters = {
        "latitude": dados.get("latitude"),
        "longitude": dados.get("longitude"),
        "febre": bool(dados.get("febre", False)),
        "tosse": bool(dados.get("tosse", False)),
        "dor_corpo": bool(dados.get("dor_corpo", False)),
        "cansaco": bool(dados.get("cansaco", False)),
        "falta_ar": bool(dados.get("falta_ar", False)),
    }
    if ip:
        duplicate_filters["ip"] = ip
    if device_id:
        duplicate_filters["device_id"] = device_id

    duplicados = filtros_duplicados.filter(**duplicate_filters).count()
    if duplicados >= 3:
        score -= 0.5
        motivos.append("duplicado_em_massa")
    elif duplicados >= 1:
        score -= 0.18
        motivos.append("duplicado_recente")

    return max(round(score, 2), 0.0), motivos, ip, device_id


def _empresa_app_publico():
    empresa, _ = Empresa.objects.get_or_create(
        email="populacao@soluscrt.com",
        defaults={
            "nome": "SolusCRT Populacao",
            "senha": make_password("publico_app"),
            "ativo": True,
            "plano": "publico",
            "pacote_codigo": "governo_estado",
            "max_usuarios": 1000,
            "max_dispositivos": 1000,
        },
    )
    if empresa.pacote_codigo != "governo_estado":
        empresa.pacote_codigo = "governo_estado"
        empresa.save(update_fields=["pacote_codigo"])
    return empresa


def _bloqueio_envio_publico(empresa, ip, device_id, dados=None, geo=None):
    agora = timezone.now()
    janela_curta = agora - timedelta(hours=6)
    janela_longa = agora - timedelta(hours=24)
    dados = dados or {}
    geo = geo or {}

    if ip:
        duplicado_contextual = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_curta,
            cidade=geo.get("cidade"),
            estado=geo.get("estado"),
            febre=bool(dados.get("febre", False)),
            tosse=bool(dados.get("tosse", False)),
            dor_corpo=bool(dados.get("dor_corpo", False)),
            cansaco=bool(dados.get("cansaco", False)),
            falta_ar=bool(dados.get("falta_ar", False)),
        ).exists()
        if duplicado_contextual:
            return False, "Sinal semelhante ja considerado recentemente nesta rede e territorio."

        envios_ip_6h = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_curta,
        ).count()
        if envios_ip_6h >= 12:
            return False, "Volume recente alto nesta rede. Tente novamente mais tarde."

        envios_ip_24h = RegistroSintoma.objects.filter(
            empresa=empresa,
            ip=ip,
            data_registro__gte=janela_longa,
        ).count()
        if envios_ip_24h >= 35:
            return False, "Limite diario de envios desta rede atingido."

    if device_id:
        envios_device_6h = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id=device_id,
            data_registro__gte=janela_curta,
        ).count()
        if envios_device_6h >= 1:
            return False, "Ja recebemos um envio recente deste aparelho. Tente novamente mais tarde."

        envios_device_24h = RegistroSintoma.objects.filter(
            empresa=empresa,
            device_id=device_id,
            data_registro__gte=janela_longa,
        ).count()
        if envios_device_24h >= 3:
            return False, "Limite diario de envios deste aparelho atingido."

    return True, None


def _semaforo_publico(nivel):
    mapa = {
        "baixo": {
            "faixa": "Verde",
            "cor": "#1DD1A1",
            "descricao": "Sinais sob monitoramento, sem pressao relevante no momento.",
        },
        "atencao": {
            "faixa": "Amarelo",
            "cor": "#FFD166",
            "descricao": "Oscilacao perceptivel de sinais, com necessidade de atencao local.",
        },
        "moderado": {
            "faixa": "Laranja",
            "cor": "#FF9B54",
            "descricao": "Crescimento consistente de sinais na regiao, com foco reforcado de vigilancia.",
        },
        "alto": {
            "faixa": "Vermelho",
            "cor": "#FF6B6B",
            "descricao": "Alta concentracao de sinais e crescimento acima do esperado para a area.",
        },
    }
    return mapa.get(nivel, mapa["baixo"])


def _orientacao_publica(nivel, grupo_top=None):
    if nivel == "alto":
        return {
            "titulo": "Momento de cautela reforcada",
            "resumo": "Reduza exposicao desnecessaria, acompanhe sinais respiratorios ou febris e procure atendimento se houver piora.",
            "acoes": [
                "Evite exposicoes prolongadas em locais fechados e muito cheios.",
                "Acompanhe febre persistente, falta de ar ou agravamento rapido.",
                "Busque avaliacao profissional diante de sinais de alerta.",
            ],
        }
    if nivel == "moderado":
        return {
            "titulo": "Atencao preventiva na regiao",
            "resumo": "Ha crescimento relevante de sinais locais. Mantenha observacao ativa da sua saude e das pessoas proximas.",
            "acoes": [
                "Observe evolucao de sintomas nas proximas 24 a 48 horas.",
                "Reforce medidas basicas de higiene e ventilacao.",
                "Se houver pessoas vulneraveis em casa, redobre a atencao.",
            ],
        }
    if nivel == "atencao":
        return {
            "titulo": "Sinais em observacao",
            "resumo": "O territorio apresenta variacao acima do habitual, mas ainda sem pressao alta.",
            "acoes": [
                "Monitore como os sintomas evoluem ao longo do dia.",
                "Evite automedicacao inadequada.",
                "Consulte orientacao profissional se o quadro persistir.",
            ],
        }
    grupo = grupo_top or "monitoramento geral"
    return {
        "titulo": "Cenario estavel no momento",
        "resumo": f"A regiao segue em observacao publica, com predominio recente de {grupo.lower()}.",
        "acoes": [
            "Mantenha cuidados basicos de saude e hidratação.",
            "Use o app para acompanhar mudancas no seu territorio.",
            "Se surgirem sintomas, registre apenas uma vez por periodo.",
        ],
    }


def _alerta_publico(nivel, crescimento, grupo_top=None):
    if nivel == "alto":
        return {
            "titulo": "Alerta elevado na sua area",
            "mensagem": f"Crescimento de {crescimento}% com concentracao relevante de sinais recentes.",
            "gravidade": "critica",
        }
    if nivel == "moderado":
        return {
            "titulo": "Atencao reforcada para a sua area",
            "mensagem": f"A regiao apresenta crescimento de {crescimento}% e exige observacao preventiva.",
            "gravidade": "alta",
        }
    if nivel == "atencao":
        return {
            "titulo": "Mudanca detectada no territorio",
            "mensagem": "Ha oscilacao de sinais locais. Continue acompanhando o radar da sua regiao.",
            "gravidade": "moderada",
        }
    grupo = grupo_top or "sinais gerais"
    return {
        "titulo": "Situacao sob controle",
        "mensagem": f"Nao ha alerta elevado no momento. O principal sinal recente e {grupo.lower()}.",
        "gravidade": "leve",
    }


# ================= REGISTRO =================

@csrf_exempt
def registrar_sintoma(request):

    # 🔐 valida token
    empresa_id, erro = validar_token(request)
    if erro:
        return erro

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({"erro": "empresa não encontrada"}, status=404)

    try:
        dados = json.loads(request.body or "{}")
    except:
        return JsonResponse({"erro": "json inválido"}, status=400)

    # 📍 coordenadas
    latitude = dados.get("latitude")
    longitude = dados.get("longitude")

    if not latitude or not longitude:
        return JsonResponse({"erro": "latitude/longitude obrigatórios"}, status=400)

    # 🌎 GEOLOCALIZAÇÃO (BRASIL INTEIRO)
    geo = obter_endereco(latitude, longitude)

    # 🧠 classificação
    grupo, classificacao = classificar_padrao(dados)
    confianca, motivos_suspeita, ip, device_id = _score_suspeita(empresa, request, dados)

    if confianca <= 0.3:
        return JsonResponse({
            "erro": "envio bloqueado por protecao antifraude",
            "motivos": motivos_suspeita,
        }, status=429)

    # 💾 salvar
    RegistroSintoma.objects.create(
        id_anonimo=uuid.uuid4(),
        febre=dados.get("febre", False),
        tosse=dados.get("tosse", False),
        dor_corpo=dados.get("dor_corpo", False),
        cansaco=dados.get("cansaco", False),
        falta_ar=dados.get("falta_ar", False),

        latitude=latitude,
        longitude=longitude,

        pais=geo.get("pais"),
        estado=geo.get("estado"),
        cidade=geo.get("cidade"),
        bairro=geo.get("bairro") or "Centro",
        condado=geo.get("condado"),

        empresa=empresa,

        grupo=grupo,
        classificacao=classificacao,
        ip=ip,
        device_id=device_id,
        confianca=confianca,
        suspeito=confianca < 0.75,
    )

    return JsonResponse({
        "status": "ok",
        "grupo": grupo,
        "classificacao": classificacao,
        "confianca": confianca,
        "suspeito": confianca < 0.75,
        "local": {
            "bairro": geo.get("bairro"),
            "cidade": geo.get("cidade"),
            "estado": geo.get("estado")
        }
    })


@csrf_exempt
def registrar_sintoma_publico(request):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    latitude = dados.get("latitude")
    longitude = dados.get("longitude")
    location_source = (dados.get("location_source") or "current").strip()
    if latitude in [None, ""] or longitude in [None, ""]:
        return JsonResponse({"erro": "latitude/longitude obrigatórios"}, status=400)
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return JsonResponse({"erro": "latitude/longitude inválidos"}, status=400)

    simulacao_autorizada = settings.DEBUG and request.headers.get("X-Solus-Simulation") == "true"
    if location_source != "current" and not simulacao_autorizada:
        return JsonResponse({
            "erro": "envio exige GPS atual confirmado pelo aparelho",
            "codigo": "gps_atual_obrigatorio",
        }, status=400)

    empresa = _empresa_app_publico()
    if simulacao_autorizada:
        geo = {
            "bairro": (dados.get("bairro") or "Centro").strip(),
            "cidade": (dados.get("cidade") or "Rio de Janeiro").strip(),
            "estado": (dados.get("estado") or "Rio de Janeiro").strip(),
            "pais": (dados.get("pais") or "Brasil").strip(),
        }
    else:
        geo = obter_endereco(latitude, longitude)
    grupo, classificacao = classificar_padrao(dados)
    confianca, motivos_suspeita, ip, device_id = _score_suspeita(empresa, request, dados)
    permitido, motivo_bloqueio = _bloqueio_envio_publico(
        empresa,
        ip,
        device_id,
        dados=dados,
        geo=geo,
    )

    if not permitido:
        return JsonResponse({
            "status": "ja_considerado",
            "mensagem": "Seu envio recente ja foi considerado no monitoramento regional.",
            "grupo": grupo,
            "classificacao": classificacao,
            "confianca": 1,
            "suspeito": False,
            "motivos_suspeita": [],
            "local": {
                "bairro": geo.get("bairro"),
                "cidade": geo.get("cidade"),
                "estado": geo.get("estado"),
            },
            "erro": motivo_bloqueio,
            "codigo": "rate_limit_publico",
        })

    if confianca <= 0.3:
        return JsonResponse({
            "erro": "envio bloqueado por proteção antifraude",
            "motivos": motivos_suspeita,
        }, status=429)

    registro = RegistroSintoma.objects.create(
        id_anonimo=uuid.uuid4(),
        empresa=empresa,
        febre=bool(dados.get("febre", False)),
        tosse=bool(dados.get("tosse", False)),
        dor_corpo=bool(dados.get("dor_corpo", False)),
        cansaco=bool(dados.get("cansaco", False)),
        falta_ar=bool(dados.get("falta_ar", False)),
        latitude=latitude,
        longitude=longitude,
        pais=geo.get("pais"),
        estado=geo.get("estado"),
        cidade=geo.get("cidade"),
        bairro=geo.get("bairro") or "Centro",
        condado=geo.get("condado"),
        grupo=grupo,
        classificacao=classificacao,
        ip=ip,
        device_id=device_id,
        confianca=confianca,
        suspeito=confianca < 0.75,
    )

    return JsonResponse({
        "status": "ok",
        "registro_id": str(registro.id_anonimo),
        "grupo": grupo,
        "classificacao": classificacao,
        "confianca": confianca,
        "suspeito": confianca < 0.75,
        "motivos_suspeita": motivos_suspeita,
        "local": {
            "bairro": registro.bairro,
            "cidade": registro.cidade,
            "estado": registro.estado,
        },
        "coordenadas_recebidas": {
            "latitude": registro.latitude,
            "longitude": registro.longitude,
            "fonte": location_source,
        },
    })

def listar_sintomas(request):
    empresa_id, erro = validar_token(request)
    if erro:
        return erro

    dados = RegistroSintoma.objects.filter(empresa_id=empresa_id)

    return JsonResponse([
        {
            "latitude": d.latitude,
            "longitude": d.longitude,
            "estado": d.estado,
            "cidade": d.cidade
        }
        for d in dados
    ], safe=False)


# ================= RESUMOS =================

def resumo_municipios(request):

    dados = RegistroSintoma.objects.values("cidade", "estado", "grupo").annotate(total=Count("id"))

    resultado = []

    for d in dados:

        cidade = d.get("cidade")
        estado = d.get("estado")

        if not cidade or not estado:
            continue

        lat, lon = buscar_coordenada(cidade, estado)

        if lat is None or lon is None:
            continue

        resultado.append({
            "cidade": cidade,
            "estado": estado,
            "grupo": d.get("grupo"),
            "total": d.get("total"),
            "latitude": lat,
            "longitude": lon
        })

    return JsonResponse(resultado, safe=False)
# ================= SURTOS =================

from django.db.models import Sum
from django.db.models import Count, Q

def detectar_surtos(request):

    dados = RegistroSintoma.objects.values("cidade", "estado").annotate(

        total=Count("id"),

        # 🧠 SINTOMAS
        febre=Count("id", filter=Q(febre=True)),
        tosse=Count("id", filter=Q(tosse=True)),
        falta_ar=Count("id", filter=Q(falta_ar=True)),
        dor_corpo=Count("id", filter=Q(dor_corpo=True)),
        cansaco=Count("id", filter=Q(cansaco=True)),

        # 🦠 DOENÇAS
        # 🦠 DOENÇAS (CERTO BASEADO NO SEU MODEL)
        dengue=Count("id", filter=Q(grupo__icontains="dengue")),
        covid=Count("id", filter=Q(grupo__icontains="covid")),
        influenza=Count("id", filter=Q(grupo__icontains="influenza")),
        zika=Count("id", filter=Q(grupo__icontains="zika")),
        chikungunya=Count("id", filter=Q(grupo__icontains="chikungunya")),
        srag=Count("id", filter=Q(grupo__icontains="srag")),
        gastro=Count("id", filter=Q(grupo__icontains="gastro")),
    )

    resposta = []

    for d in dados:

        cidade = d["cidade"]
        estado = d["estado"]
        total = d["total"] or 0

        lat, lon = buscar_coordenada(cidade, estado)

        # 🧠 IA
        previsao, crescimento = calcular_previsao(cidade, estado, total)

        nivel = calcular_risco(total, crescimento)

        resposta.append({
            "cidade": cidade,
            "estado": estado,
            "total": total,

            "crescimento": round(crescimento, 2),
            "previsao": previsao,
            "nivel": nivel,

            "latitude": lat,
            "longitude": lon,

            # 🧠 sintomas
            "febre": d["febre"],
            "tosse": d["tosse"],
            "falta_ar": d["falta_ar"],
            "dor_corpo": d["dor_corpo"],
            "cansaco": d["cansaco"],

            # 🦠 doenças
            "dengue": d["dengue"],
            "covid": d["covid"],
            "influenza": d["influenza"],
            "zika": d["zika"],
            "chikungunya": d["chikungunya"],
            "srag": d["srag"],
            "gastro": d["gastro"],
        })

    return JsonResponse(resposta, safe=False)

# ================= PREVISÃO =================

def prever_surtos(request):

    agora = timezone.now()
    h24 = agora - timedelta(hours=24)
    h48 = agora - timedelta(hours=48)

    ultimas_24h = RegistroSintoma.objects.filter(
        data_registro__gte=h24
    ).values("cidade", "estado").annotate(total=Count("id"))

    ultimas_48h = RegistroSintoma.objects.filter(
        data_registro__gte=h48,
        data_registro__lt=h24
    ).values("cidade", "estado").annotate(total=Count("id"))

    mapa_48h = {(d["cidade"], d["estado"]): d["total"] for d in ultimas_48h}

    resultado = []

    for d in ultimas_24h:

        cidade = d["cidade"]
        estado = d["estado"]
        atual = d["total"]

        anterior = mapa_48h.get((cidade, estado), 0)

        # 🔥 CRESCIMENTO REAL (%)
        if anterior > 0:
            crescimento = ((atual - anterior) / anterior) * 100
        else:
            crescimento = 100  # novo surto

        # ============================
        # 🧠 IA DE DECISÃO
        # ============================

        risco = "BAIXO"
        previsao = "ESTÁVEL"
        interpretacao = "Situação sob controle"

        if crescimento > 100 and atual > 50:
            risco = "CRITICO"
            previsao = "EXPLOSÃO IMINENTE"
            interpretacao = "Alta probabilidade de surto grave nas próximas horas"

        elif crescimento > 50:
            risco = "ALTO"
            previsao = "FORTE CRESCIMENTO"
            interpretacao = "Disseminação acelerada detectada"

        elif crescimento > 20:
            risco = "MEDIO"
            previsao = "TENDÊNCIA DE ALTA"
            interpretacao = "Aumento consistente de casos"

        elif crescimento < -20:
            risco = "BAIXO"
            previsao = "QUEDA"
            interpretacao = "Redução de casos"

        resultado.append({
            "cidade": cidade,
            "estado": estado,
            "total": atual,
            "crescimento": round(crescimento, 2),
            "risco": risco,
            "previsao": previsao,
            "interpretacao": interpretacao
        })

    return JsonResponse(resultado, safe=False)

# ================= IA =================

@csrf_exempt
def analisar_tosse(request):
    return JsonResponse(random.choice([
        {"risco": "baixo", "possivel": "Resfriado"},
        {"risco": "medio", "possivel": "Dengue"},
        {"risco": "alto", "possivel": "COVID"}
    ]))




# ================= ALERTAS =================

def alertas(request):
    return JsonResponse([
        {"mensagem": "🚨 Sistema ativo - monitorando surtos"}
    ], safe=False)


# ================= PAGAMENTO =================

def tela_pagamento(request):
    from .planos import pacotes_por_setor
    return render(request, "pagamento.html", {
        "pacotes": pacotes_por_setor(incluir_governo=False),
    })


def sucesso(request):
    return HttpResponse("Pagamento aprovado")


def erro(request):
    return HttpResponse("Pagamento recusado")


def pendente(request):
    return HttpResponse("Pagamento pendente")


# ================= RELATÓRIOS =================

def relatorio_regioes(request):
    return JsonResponse([], safe=False)


def relatorio_municipios(request):
    dados = RegistroSintoma.objects.values(
        "cidade", "estado"
    ).annotate(total=Count("id"))

    return JsonResponse(list(dados), safe=False)

from rest_framework.decorators import api_view
from rest_framework.response import Response

    

def calcular_risco(total, crescimento):
    total = int(total)
    def safe_float(valor):
     try:
         return float(valor)
     except:
        return 0

    crescimento = safe_float(crescimento)

    if total > 50 or crescimento > 2:
        return "ALTO"
    elif total > 20:
        return "MÉDIO"
    else:
        return "BAIXO"


def resumo_doencas(request):

    registros = RegistroSintoma.objects.all()

    dados = analisar_doencas(registros)

    resultado = []

    for doenca, total in dados.items():

        risco = risco_por_doenca(doenca, total)

        resultado.append({
            "doenca": doenca,
            "total": total,
            "risco": risco
        })

    return JsonResponse(resultado, safe=False)

def diagnostico_ia(request):

    dados = json.loads(request.body or "{}")

    probs = probabilidade_doenca(dados)

    # pega a mais provável
    principal = max(probs, key=probs.get)

    return JsonResponse({
        "probabilidades": probs,
        "mais_provavel": principal
    })

from .utils import treinar_modelo, prever_com_aprendizado

def diagnostico_ia_avancado(request):

    dados = json.loads(request.body or "{}")

    registros = RegistroSintoma.objects.all()

    modelo = treinar_modelo(registros)

    resultado = prever_com_aprendizado(dados, modelo)

    if not resultado:
        return JsonResponse({"erro": "sem dados suficientes"})

    principal = max(resultado, key=resultado.get)

    return JsonResponse({
        "probabilidades": resultado,
        "mais_provavel": principal
    })



def classificar_padrao(dados):

    score_respiratorio = 0
    score_arbovirose = 0
    score_alerta = 0

    if dados.get("febre"):
        score_respiratorio += 1
        score_arbovirose += 2

    if dados.get("tosse"):
        score_respiratorio += 2

    if dados.get("falta_ar"):
        score_respiratorio += 3
        score_alerta += 3

    if dados.get("dor_corpo"):
        score_arbovirose += 2

    if dados.get("cansaco"):
        score_respiratorio += 1
        score_arbovirose += 1

    # 🔥 decisão baseada em pontuação
    if score_alerta >= 3:
        return "Alerta", "Sinais que merecem atenção médica imediata"

    if score_respiratorio >= 3:
        return "Respiratório", "Padrão compatível com infecção respiratória viral"

    if score_arbovirose >= 3:
        return "Arbovirose", "Padrão compatível com dengue ou vírus similar"

    return "Leve", "Sintomas inespecíficos de baixo risco"

def resumo_estados(request):
    dados = RegistroSintoma.objects.values("estado").annotate(total=Count("id"))
    return JsonResponse(list(dados), safe=False)

def gerar_alerta(total, grupo):

    if total >= 50:
        return "ALTO", f"Possível surto de {grupo}"
    
    elif total >= 20:
        return "MODERADO", f"Aumento de casos de {grupo}"
    
    elif total >= 10:
        return "ATENCAO", f"Crescimento leve de {grupo}"
    
    return "NORMAL", "Situação controlada"

def mapa_casos(request):

    dados = RegistroSintoma.objects.all()

    resultado = []

    for d in dados:

        if not d.latitude or not d.longitude:
            continue

        resultado.append({
            "latitude": d.latitude,
            "longitude": d.longitude,
            "grupo": d.grupo,
            "cidade": d.cidade,
        })

    return JsonResponse(resultado, safe=False)


def app_resumo_publico(request):
    agora = timezone.now()
    ultimas_24h = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(hours=24))
    ultimos_7d = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(days=7))
    ativos_30d = RegistroSintoma.objects.filter(data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS))
    dias_anteriores = RegistroSintoma.objects.filter(
        data_registro__gte=agora - timedelta(days=14),
        data_registro__lt=agora - timedelta(days=7),
    )

    total_7d = ultimos_7d.count()
    total_30d = ativos_30d.count()
    indice_ativo_30d = _indice_temporal_publico(ativos_30d, agora)
    base_anterior = dias_anteriores.count()
    crescimento = 0.0
    if base_anterior:
        crescimento = round(((total_7d - base_anterior) / base_anterior) * 100, 2)

    doencas = (
        ativos_30d.exclude(grupo__isnull=True).exclude(grupo="")
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    top_grupo = doencas[0]["grupo"] if doencas else "monitoramento geral"
    nivel_nacional = _nivel_por_indice_publico(indice_ativo_30d, crescimento)

    return JsonResponse({
        "resumo": {
            "registros_24h": ultimas_24h.count(),
            "registros_7d": total_7d,
            "registros_30d": total_30d,
            "indice_ativo_7d": indice_ativo_30d,
            "indice_ativo_30d": indice_ativo_30d,
            "crescimento_7d": crescimento,
            "suspeitos_24h": ultimas_24h.filter(suspeito=True).count(),
            "nivel_nacional": nivel_nacional,
            "decaimento_temporal": "indice ativo fica estavel por 10 dias sem novos envios e depois reduz gradualmente ate 1% em 30 dias, evitando falsa queda precoce",
        },
        "semaforo": _semaforo_publico(nivel_nacional),
        "alerta_publico": _alerta_publico(nivel_nacional, crescimento, top_grupo),
        "orientacao_publica": _orientacao_publica(nivel_nacional, top_grupo),
        "doencas_top": [
            {
                "grupo": item["grupo"],
                "total": item["total"],
                "percentual": round((item["total"] / max(total_30d, 1)) * 100, 2),
            }
            for item in doencas
        ],
    })


def app_radar_local(request):
    latitude = request.GET.get("latitude")
    longitude = request.GET.get("longitude")
    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")
    bairro = request.GET.get("bairro")

    geo = {}
    if latitude and longitude and not (cidade and estado and bairro):
        geo = obter_endereco(latitude, longitude)
        cidade = cidade or geo.get("cidade")
        estado = estado or geo.get("estado")
        bairro = bairro or geo.get("bairro")

    if not cidade or not estado:
        return JsonResponse({"erro": "cidade/estado ou latitude/longitude obrigatórios"}, status=400)

    agora = timezone.now()
    atuais = RegistroSintoma.objects.filter(
        cidade=cidade,
        estado=estado,
        data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS),
    )
    atuais_7d = atuais.filter(data_registro__gte=agora - timedelta(days=7))
    anteriores = RegistroSintoma.objects.filter(
        cidade=cidade,
        estado=estado,
        data_registro__gte=agora - timedelta(days=14),
        data_registro__lt=agora - timedelta(days=7),
    )

    if bairro:
        atuais_bairro = atuais.filter(bairro=bairro)
        atuais_bairro_7d = atuais_7d.filter(bairro=bairro)
    else:
        atuais_bairro = atuais.none()
        atuais_bairro_7d = atuais_7d.none()

    total_atuais = atuais_7d.count()
    total_ativos = atuais.count()
    indice_ativo = _indice_temporal_publico(atuais, agora)
    total_anteriores = anteriores.count()
    crescimento = 0.0
    if total_anteriores:
        crescimento = round(((total_atuais - total_anteriores) / total_anteriores) * 100, 2)

    nivel = _nivel_local_por_indice_publico(indice_ativo, crescimento)

    doencas = (
        atuais.exclude(grupo__isnull=True).exclude(grupo="")
        .values("grupo")
        .annotate(total=Count("id"))
        .order_by("-total")[:6]
    )
    grupo_top = doencas[0]["grupo"] if doencas else "monitoramento geral"

    sintomas = {
        "febre": atuais.filter(febre=True).count(),
        "tosse": atuais.filter(tosse=True).count(),
        "dor_corpo": atuais.filter(dor_corpo=True).count(),
        "cansaco": atuais.filter(cansaco=True).count(),
        "falta_ar": atuais.filter(falta_ar=True).count(),
    }
    doencas_provaveis = _build_disease_probabilities(sintomas, total_ativos)

    return JsonResponse({
        "local": {
            "bairro": bairro or geo.get("bairro"),
            "cidade": cidade,
            "estado": estado,
        },
        "radar": {
            "nivel": nivel,
            "registros_7d": total_atuais,
            "registros_30d": total_ativos,
            "indice_ativo_7d": indice_ativo,
            "indice_ativo_30d": indice_ativo,
            "crescimento_7d": crescimento,
            "suspeitos_7d": atuais_7d.filter(suspeito=True).count(),
            "bairro_registros_7d": atuais_bairro_7d.count(),
            "bairro_registros_30d": atuais_bairro.count(),
            "grupo_top": grupo_top,
            "decaimento_temporal": "sem novos envios, o indice local permanece estavel por 10 dias e depois cai de forma gradual ate 1% em 30 dias para evitar conclusoes falsas",
        },
        "semaforo": _semaforo_publico(nivel),
        "alerta_publico": _alerta_publico(nivel, crescimento, grupo_top),
        "orientacao_publica": _orientacao_publica(nivel, grupo_top),
        "doencas": [
            {
                "grupo": item["grupo"],
                "total": item["total"],
                "percentual": round((item["total"] / max(total_ativos, 1)) * 100, 2),
            }
            for item in doencas
        ],
        "doencas_provaveis": doencas_provaveis,
        "sintomas": sintomas,
    })


def app_mapa_publico(request):
    agora = timezone.now()
    base = RegistroSintoma.objects.filter(
        data_registro__gte=agora - timedelta(days=JANELA_DECAIMENTO_FOCO_DIAS),
        latitude__isnull=False,
        longitude__isnull=False,
    )
    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")
    if cidade:
        base = base.filter(cidade=cidade)
    if estado:
        base = base.filter(estado__in=_state_terms(estado))

    hotspots_por_dia = (
        base.annotate(day=TruncDate("data_registro"))
        .values("cidade", "estado", "bairro", "day")
        .annotate(total=Count("id"), latitude_media=Avg("latitude"), longitude_media=Avg("longitude"))
    )

    areas = {}
    for row in hotspots_por_dia:
        key = (row["cidade"], row["estado"], row["bairro"])
        peso = _peso_temporal_publico(row["day"], agora)
        area = areas.setdefault(key, {
            "cidade": row["cidade"],
            "estado": row["estado"],
            "bairro": row["bairro"],
            "total": 0,
            "indice_ativo": 0.0,
            "latitude_soma": 0.0,
            "longitude_soma": 0.0,
            "peso_geo": 0,
        })
        total = row["total"] or 0
        area["total"] += total
        area["indice_ativo"] += total * peso
        area["latitude_soma"] += float(row["latitude_media"]) * total
        area["longitude_soma"] += float(row["longitude_media"]) * total
        area["peso_geo"] += total

    hotspots = sorted(areas.values(), key=lambda item: item["indice_ativo"], reverse=True)[:250]
    total_indice_mapa = sum(item["indice_ativo"] for item in hotspots) or 1

    resultado = []
    for item in hotspots:
        area_queryset = base.filter(
            cidade=item["cidade"],
            estado=item["estado"],
            bairro=item["bairro"],
        )
        grupo_top = (
            area_queryset
            .exclude(grupo__isnull=True)
            .exclude(grupo="")
            .values("grupo")
            .annotate(total=Count("id"))
            .order_by("-total")
            .first()
        )
        sintomas_area = {
            "febre": area_queryset.filter(febre=True).count(),
            "tosse": area_queryset.filter(tosse=True).count(),
            "dor_corpo": area_queryset.filter(dor_corpo=True).count(),
            "cansaco": area_queryset.filter(cansaco=True).count(),
            "falta_ar": area_queryset.filter(falta_ar=True).count(),
        }
        doencas_provaveis = _build_disease_probabilities(sintomas_area, item["total"])
        doenca_top = doencas_provaveis[0]["name"] if doencas_provaveis else None
        indice_ativo = round(item["indice_ativo"], 2)
        nivel = "alto" if indice_ativo >= 45 else "moderado" if indice_ativo >= 20 else "atencao" if indice_ativo >= 8 else "baixo"
        peso_geo = max(item["peso_geo"], 1)
        resultado.append({
            "cidade": item["cidade"],
            "estado": item["estado"],
            "bairro": item["bairro"],
            "total": item["total"],
            "indice_ativo": indice_ativo,
            "percentual_ativo": round((indice_ativo / total_indice_mapa) * 100, 2),
            "latitude": round(item["latitude_soma"] / peso_geo, 6),
            "longitude": round(item["longitude_soma"] / peso_geo, 6),
            "grupo_dominante": doenca_top or (grupo_top["grupo"] if grupo_top else "Monitoramento geral"),
            "perfil_sindromico": grupo_top["grupo"] if grupo_top else "Monitoramento geral",
            "doenca_dominante": doenca_top,
            "doencas_provaveis": doencas_provaveis[:5],
            "semaforo": _semaforo_publico(nivel),
            "decaimento_temporal": "foco preservado por 10 dias sem novos envios; depois a intensidade reduz gradualmente ate 30 dias",
        })

    return JsonResponse({"hotspots": resultado}, safe=False)


def app_alertas_publicos(request):
    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")
    bairro = request.GET.get("bairro")
    incluir_gerais = request.GET.get("incluir_gerais", "1").lower() not in {"0", "false", "nao", "não"}

    alertas = AlertaGovernamental.objects.filter(
        ativo=True,
        status=AlertaGovernamental.STATUS_PUBLICADO,
    ).order_by("-criado_em")
    if estado:
        estado_filter = Q(estado__in=_state_terms(estado))
        if incluir_gerais:
            estado_filter |= Q(estado__isnull=True) | Q(estado="")
        alertas = alertas.filter(estado_filter)
    if cidade:
        cidade_filter = Q(cidade=cidade)
        if incluir_gerais:
            cidade_filter |= Q(cidade__isnull=True) | Q(cidade="")
        alertas = alertas.filter(cidade_filter)
    if bairro:
        bairro_filter = Q(bairro=bairro)
        if incluir_gerais:
            bairro_filter |= Q(bairro__isnull=True) | Q(bairro="")
        alertas = alertas.filter(bairro_filter)

    return JsonResponse({
        "alertas": [
            {
                "id": alerta.id,
                "titulo": alerta.titulo,
                "mensagem": alerta.mensagem,
                "estado": alerta.estado,
                "cidade": alerta.cidade,
                "bairro": alerta.bairro,
                "nivel": alerta.nivel,
                "criado_em": alerta.criado_em.isoformat(),
            }
            for alerta in alertas[:12]
        ]
    })


@csrf_exempt
def registrar_push_publico(request):
    if request.method != "POST":
        return JsonResponse({"erro": "use POST"}, status=405)

    try:
        dados = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"erro": "json inválido"}, status=400)

    token = (dados.get("token") or "").strip()
    device_id = (dados.get("device_id") or "").strip()
    if not token or not device_id:
        return JsonResponse({"erro": "token e device_id são obrigatórios"}, status=400)

    registro, _ = DispositivoPushPublico.objects.update_or_create(
        token=token,
        defaults={
            "device_id": device_id[:120],
            "plataforma": (dados.get("plataforma") or "unknown")[:20],
            "estado": (dados.get("estado") or "").strip() or None,
            "cidade": (dados.get("cidade") or "").strip() or None,
            "bairro": (dados.get("bairro") or "").strip() or None,
            "ativo": True,
        },
    )
    return JsonResponse({"status": "ok", "push_id": registro.id})

@csrf_exempt
def analisar_audio(request):

    if request.method == "POST":
        audio_file = request.FILES.get("audio")

        if not audio_file:
            return JsonResponse({"erro": "sem áudio"})

        # 🔥 versão simplificada (sem numpy / soundfile)
        tamanho = audio_file.size

        if tamanho > 500000:
            return JsonResponse({
                "classificacao": "Tosse forte",
                "nivel": "ALTO"
            })

        elif tamanho > 100000:
            return JsonResponse({
                "classificacao": "Tosse moderada",
                "nivel": "MODERADO"
            })

        else:
            return JsonResponse({
                "classificacao": "Som leve",
                "nivel": "NORMAL"
            })

    return JsonResponse({"erro": "método inválido"})

from api.models import RegistroSintoma

def limpar_casos(request):
    total = RegistroSintoma.objects.count()
    RegistroSintoma.objects.all().delete()
    return JsonResponse({"apagados": total})


def insights_nacional(request):

    dados = RegistroSintoma.objects.values(
        "estado", "cidade", "grupo"
    ).annotate(total=Count("id"))

    def sugestao_estoque(grupo):
        if grupo == "Respiratório":
            return "Comprar: Antigripais, Xaropes, Vitamina C"
        if grupo == "Dengue":
            return "Comprar: Paracetamol, Soro, Repelente"
        return "Estoque básico"

    resultado = []

    for d in dados:

        total = d["total"]
        grupo = d["grupo"]
        cidade = d["cidade"]
        estado = d["estado"]

        if total > 50:
            nivel = "ALTO"
        elif total > 20:
            nivel = "MODERADO"
        else:
            nivel = "BAIXO"

        recomendacao = sugestao_estoque(grupo)

        resultado.append({
            "estado": estado,
            "cidade": cidade,
            "doenca": grupo,
            "total": total,
            "nivel": nivel,
            "recomendacao": recomendacao
        })

    return JsonResponse(resultado, safe=False)



def insights_farmacia(request):

    dados = RegistroSintoma.objects.values(
        "cidade", "estado", "grupo"
    ).annotate(total=Count("id"))

    resultado = []

    for d in dados:

        total = d["total"]
        grupo = d["grupo"] or "Geral"

        # 🎯 NÍVEL
        nivel = "BAIXO"
        if total > 50:
            nivel = "MODERADO"
        if total > 100:
            nivel = "ALTO"

        # 💊 RECOMENDAÇÃO INTELIGENTE
        recomendacao = "Estoque normal"

        if grupo == "Dengue":
            recomendacao = "💊 Paracetamol + Repelente"

        elif grupo == "Respiratório":
            recomendacao = "💊 Antigripais + Vitamina C"

        elif grupo == "COVID":
            recomendacao = "💊 Antigripais + Máscaras"

        resultado.append({
            "cidade": d["cidade"],
            "estado": d["estado"],
            "doenca": grupo,
            "total": total,
            "nivel": nivel,
            "recomendacao": recomendacao
        })

    return JsonResponse(resultado, safe=False)



from django.http import HttpResponse

def tela_cadastro(request):
    return HttpResponse("""
<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="UTF-8">
<title>Solus CRT Saúde • Criar Conta</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">

<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',sans-serif;}

body{
  height:100vh;
  background:#020617;
  color:white;
  display:flex;
  align-items:center;
  justify-content:center;
}

/* 🔥 FUNDO */
.bg{
  position:absolute;
  width:100%;
  height:100%;
  background:
    radial-gradient(circle at 20% 20%, rgba(56,189,248,0.15), transparent 40%),
    radial-gradient(circle at 80% 80%, rgba(99,102,241,0.15), transparent 40%),
    #020617;
}

/* 🔥 CARD */
.card{
  position:relative;
  z-index:2;
  width:420px;
  padding:40px;
  border-radius:20px;
  background:rgba(255,255,255,0.04);
  backdrop-filter:blur(25px);
  border:1px solid rgba(255,255,255,0.08);
  box-shadow:0 20px 80px rgba(0,0,0,0.7);
}

/* LOGO */
.logo{
  font-size:22px;
  font-weight:600;
  margin-bottom:20px;
}
.logo span{color:#38bdf8}

/* TITULO */
h2{
  font-size:20px;
  margin-bottom:5px;
}

p{
  font-size:13px;
  color:#94a3b8;
  margin-bottom:25px;
}

/* INPUT */
.input{
  width:100%;
  padding:14px;
  margin-bottom:14px;
  border-radius:10px;
  border:1px solid rgba(255,255,255,0.08);
  background:rgba(255,255,255,0.03);
  color:white;
  outline:none;
  transition:0.3s;
}

.input:focus{
  border-color:#38bdf8;
  box-shadow:0 0 10px rgba(56,189,248,0.3);
}

/* BOTÃO */
.btn{
  width:100%;
  padding:14px;
  border:none;
  border-radius:10px;
  background:linear-gradient(135deg,#38bdf8,#2563eb);
  font-weight:600;
  color:white;
  cursor:pointer;
  transition:0.3s;
}

.btn:hover{
  transform:translateY(-2px);
  box-shadow:0 10px 30px rgba(56,189,248,0.4);
}

/* LOADING */
.loading{
  display:none;
  text-align:center;
  margin-top:10px;
  font-size:13px;
  color:#38bdf8;
}

/* ERRO */
.erro{
  margin-top:10px;
  color:#f87171;
  display:none;
  font-size:13px;
}

/* FOOTER */
.footer{
  margin-top:20px;
  text-align:center;
  font-size:13px;
  color:#94a3b8;
  cursor:pointer;
}

.footer:hover{
  color:#38bdf8;
}
</style>
</head>

<body>

<div class="bg"></div>

<div class="card">

  <div class="logo">Solus <span>CRT</span> Saúde</div>

  <h2>Criar Conta</h2>
  <p>Ative inteligência epidemiológica em minutos</p>

  <input id="nome" class="input" placeholder="Nome da empresa">
  <input id="email" class="input" placeholder="Email corporativo">
  <input id="senha" type="password" class="input" placeholder="Senha segura">

  <button class="btn" onclick="cadastrar()">Criar Conta</button>

  <div id="loading" class="loading">Criando conta...</div>
  <div id="erro" class="erro"></div>

  <div class="footer" onclick="window.location.href='/login-empresa/'">
    Já tenho conta
  </div>

</div>

<script>
function getDeviceId(){
  let deviceId = localStorage.getItem("device_id");
  if(!deviceId){
    deviceId = "dev-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("device_id", deviceId);
  }
  return deviceId;
}

async function cadastrar(){

  const nome = document.getElementById("nome").value;
  const email = document.getElementById("email").value;
  const senha = document.getElementById("senha").value;
  const erro = document.getElementById("erro");
  const loading = document.getElementById("loading");

  erro.style.display = "none";

  // 🔥 VALIDAÇÃO PROFISSIONAL
  if(!nome || !email || !senha){
    erro.innerText = "Preencha todos os campos";
    erro.style.display = "block";
    return;
  }

  if(senha.length < 6){
    erro.innerText = "Senha deve ter no mínimo 6 caracteres";
    erro.style.display = "block";
    return;
  }

  loading.style.display = "block";

  try{
    const res = await fetch("/api/registrar_empresa", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        nome,
        email,
        senha,
        device_id: getDeviceId(),
        device_name: navigator.platform || "Computador"
      })
    });

    const data = await res.json();

    loading.style.display = "none";

    if(data.token){
      localStorage.setItem("token", data.token);
      if(data.device_id){
        localStorage.setItem("device_id", data.device_id);
      }

      window.location.href = data.destination || "/pagamento/";
    }else{
      erro.innerText = data.erro || "Erro ao criar conta";
      erro.style.display = "block";
    }

  }catch(e){
    loading.style.display = "none";
    erro.innerText = "Erro de conexão";
    erro.style.display = "block";
  }
}
</script>

</body>
</html>
""", content_type="text/html")

def login(request):
    body = json.loads(request.body)

    email = body.get("email")
    senha = body.get("senha")

    empresa = Empresa.objects.filter(email=email).first()

    if not empresa:
        return JsonResponse({"erro": "Empresa não encontrada"}, status=401)

    # 🔥 IGNORA SENHA TEMPORARIAMENTE
    token = jwt.encode(
        {"empresa_id": empresa.id},
        settings.JWT_SECRET_KEY,
        algorithm="HS256"
    )

    return JsonResponse({
        "status": "ok",
        "token": token,
        "empresa_id": empresa.id
    })


def pagamento(request):

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return JsonResponse({"erro": "Token não enviado"}, status=401)

    if not auth_header.startswith("Bearer "):
        return JsonResponse({"erro": "Formato inválido"}, status=401)

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

    except Exception as e:
        return JsonResponse({"erro": "Token inválido"}, status=401)

    return JsonResponse({
        "status": "ok",
        "empresa_id": payload["empresa_id"]
    })

def pagamento(request):

    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return JsonResponse({"erro": "não autorizado"}, status=401)

    token = auth_header.split(" ")[1]

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        empresa_id = payload["empresa_id"]

    except Exception:
        return JsonResponse({"erro": "Token inválido"}, status=401)

    return JsonResponse({
        "status": "ok",
        "empresa_id": empresa_id
    })



def painel(request):

    empresa_id = request.GET.get("empresa_id")

    if not empresa_id:
        return JsonResponse({"erro": "sem empresa"}, status=400)

    dados = RegistroSintoma.objects.filter(empresa_id=empresa_id)

    total = dados.count()

    risco = "Alto" if total > 2 else "Baixo"
    crescimento = "Subindo" if total > 1 else "Estável"

    alerta = None
    if total > 2:
        alerta = "Possível surto na região"

    insight = "Aumento de sintomas detectado" if total > 0 else "Sem registros"

    return JsonResponse({
        "total": total,
        "risco": risco,
        "crescimento": crescimento,
        "alerta": alerta,
        "insight": insight
    })


def casos_por_regiao(request):

    empresa_id = request.GET.get("empresa_id")

    dados = (
        RegistroSintoma.objects
        .filter(empresa_id=empresa_id)
        .values("bairro", "cidade", "estado")
        .annotate(
            total=Count("id"),
            lat=Avg("latitude"),
            lng=Avg("longitude"),

            # sintomas
            febre=Count("id", filter=Q(febre=True)),
            tosse=Count("id", filter=Q(tosse=True)),
            falta_ar=Count("id", filter=Q(falta_ar=True)),
            dor_corpo=Count("id", filter=Q(dor_corpo=True)),
            cansaco=Count("id", filter=Q(cansaco=True)),

            # doenças (nível OMS)
            covid=Count("id", filter=Q(grupo="COVID-19")),
            influenza=Count("id", filter=Q(grupo="Influenza")),
            dengue=Count("id", filter=Q(grupo="Dengue")),
            zika=Count("id", filter=Q(grupo="Zika")),
            chikungunya=Count("id", filter=Q(grupo="Chikungunya")),
            srag=Count("id", filter=Q(grupo="SRAG")),
            gastro=Count("id", filter=Q(grupo="Gastroviral")),
        )
    )

    resultado = []

    for d in dados:

        total = d["total"]

        if total >= 10:
            risco = "alto"
        elif total >= 5:
            risco = "medio"
        else:
            risco = "baixo"

        # dominante
        tipos = {
            "COVID-19": d["covid"],
            "Influenza": d["influenza"],
            "Dengue": d["dengue"],
            "Zika": d["zika"],
            "Chikungunya": d["chikungunya"],
            "SRAG": d["srag"],
            "Gastroviral": d["gastro"],
        }

        dominante = max(tipos, key=tipos.get) if total > 0 else "N/D"

        resultado.append({
            "regiao": f"{d['bairro']} - {d['cidade']}/{d['estado']}",
            "total": total,
            "lat": d["lat"],
            "lng": d["lng"],
            "risco": risco,

            # sintomas
            "febre": d["febre"],
            "tosse": d["tosse"],
            "falta_ar": d["falta_ar"],
            "dor_corpo": d["dor_corpo"],
            "cansaco": d["cansaco"],

            # doenças
            "covid": d["covid"],
            "influenza": d["influenza"],
            "dengue": d["dengue"],
            "zika": d["zika"],
            "chikungunya": d["chikungunya"],
            "srag": d["srag"],
            "gastro": d["gastro"],

            "dominante": dominante
        })

    return JsonResponse(resultado, safe=False)


def mapa_risco(request):

    dados = (
        RegistroSintoma.objects
        .values("bairro", "latitude", "longitude")
        .annotate(total=Count("id"))
    )

    resultado = []

    for d in dados:

        total = d["total"]

        if total > 5:
            risco = "alto"
            cor = "red"
        elif total > 2:
            risco = "medio"
            cor = "orange"
        else:
            risco = "baixo"
            cor = "green"

        resultado.append({
            "bairro": d["bairro"],
            "lat": d["latitude"],
            "lng": d["longitude"],
            "total": total,
            "risco": risco,
            "cor": cor
        })

    return JsonResponse(resultado, safe=False)


def bairros_por_cidade(request):

    cidade = request.GET.get("cidade")
    estado = request.GET.get("estado")

    if not cidade or not estado:
        return JsonResponse([], safe=False)

    dados = RegistroSintoma.objects.filter(
        cidade=cidade,
        estado=estado
    ).values("bairro").annotate(
        total=Count("id")
    ).order_by("-total")

    return JsonResponse(list(dados), safe=False)
