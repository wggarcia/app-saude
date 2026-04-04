from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.db.models import Count
from .utils import probabilidade_doenca

from .models import RegistroSintoma, Empresa
from .utils_cidades import buscar_coordenada
from .utils import obter_localizacao

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

SECRET_KEY = "chave_super_segura_123456789_abc"


# ================= LOGIN =================

def tela_login(request):
    return render(request, 'login.html')


def verificar_acesso(request):
    token = request.headers.get("Authorization")
    if not token:
        return None

    try:
        token = token.replace("Bearer ", "")
        dados = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return Empresa.objects.get(id=dados["empresa_id"])
    except:
        return None


def dashboard(request):
    empresa = verificar_acesso(request)

    if not empresa:
        return redirect("/")

    if not empresa.ativo:
        return redirect("/pagamento/")

    return render(request, "dashboard.html")


# ================= TOKEN =================

def validar_token(request):
    auth = request.headers.get("Authorization")

    if not auth:
        return None, JsonResponse({"erro": "não autorizado"}, status=403)

    try:
        token = auth.split(" ")[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["empresa_id"], None
    except:
        return None, JsonResponse({"erro": "token inválido"}, status=403)


# ================= REGISTRO =================

@csrf_exempt
def registrar_sintoma(request):

    empresa_id, erro = validar_token(request)
    if erro:
        return erro

    empresa = Empresa.objects.get(id=empresa_id)

    dados = json.loads(request.body or "{}")

    latitude = dados.get("latitude")
    longitude = dados.get("longitude")

    local = obter_localizacao(latitude, longitude)

    # 🔥 CORREÇÃO AQUI (ANTES DO CREATE)
    mapa_estados = {
        "Rio de Janeiro": "RJ",
        "São Paulo": "SP",
        "Minas Gerais": "MG",
        "Bahia": "BA",
        "Rio Grande do Sul": "RS"
    }

    estado_raw = local.get("estado")
    estado = mapa_estados.get(estado_raw, estado_raw)
    grupo, classificacao = classificar_padrao(dados)

    # 🔥 CREATE LIMPO
    RegistroSintoma.objects.create(
    id_anonimo=str(uuid.uuid4()),
    febre=dados.get("febre", False),
    tosse=dados.get("tosse", False),
    dor_corpo=dados.get("dor_corpo", False),
    cansaco=dados.get("cansaco", False),
    falta_ar=dados.get("falta_ar", False),
    latitude=latitude,
    longitude=longitude,
    pais=local.get("pais"),
    estado=local.get("estado"),
    cidade=local.get("cidade"),
    bairro=local.get("bairro"),
    condado=local.get("condado"),
    empresa=empresa,

    # 👇 NOVO
    grupo=grupo,
    classificacao=classificacao
)

    return JsonResponse({
    "status": "ok",
    "grupo": grupo,
    "classificacao": classificacao
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

        total = d.get("total")
        grupo = d.get("grupo")

        nivel, mensagem = gerar_alerta(total, grupo)

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
    "grupo": grupo,
    "total": total,
    "nivel": nivel,
    "mensagem": mensagem,
    "latitude": lat,
    "longitude": lon
})

    return JsonResponse(resultado, safe=False)
# ================= SURTOS =================

def detectar_surtos(request):

    dados = RegistroSintoma.objects.values("cidade", "estado").annotate(total=Count("id"))

    resultado = []

    for d in dados:

        lat, lon = buscar_coordenada(d["cidade"], d["estado"])

        crescimento = "ESTAVEL"  # pode evoluir depois

        nivel = calcular_risco(d["total"], crescimento)

        resultado.append({
            "cidade": d["cidade"],
            "estado": d["estado"],
            "total": d["total"],
            "nivel": nivel,
            "latitude": lat,
            "longitude": lon
        })

    return JsonResponse(resultado, safe=False)


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
        anterior = mapa_48h.get((d["cidade"], d["estado"]), 1)
        crescimento = d["total"] / anterior

        risco = "NORMAL"
        if crescimento > 1.5:
            risco = "ALERTA"
        if crescimento > 2:
            risco = "CRITICO"

        resultado.append({
            "cidade": d["cidade"],
            "estado": d["estado"],
            "total": d["total"],
            "crescimento": round(crescimento, 2),
            "risco": risco
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


# ================= PAINEL =================

def painel_geral(request):
    return JsonResponse({
        "estados": list(
            RegistroSintoma.objects.values("estado").annotate(total=Count("id"))
        ),
        "municipios": list(
            RegistroSintoma.objects.values("cidade", "estado").annotate(total=Count("id"))
        ),
    })


def clusters(request):
    dados = RegistroSintoma.objects.values("cidade", "estado").annotate(total=Count("id"))
    return JsonResponse(list(dados), safe=False)


# ================= ALERTAS =================

def alertas(request):
    return JsonResponse([
        {"mensagem": "🚨 Sistema ativo - monitorando surtos"}
    ], safe=False)


# ================= PAGAMENTO =================

def tela_pagamento(request):
    return render(request, "pagamento.html")


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

@api_view(['POST'])
def ativar_plano(request, empresa_id):
    try:
        empresa = Empresa.objects.get(id=empresa_id)
        empresa.plano = "premium"
        empresa.ativo = True
        empresa.save()

        return Response({"status": "Plano ativado"})
    except Empresa.DoesNotExist:
        return Response({"erro": "Empresa não encontrada"}, status=404)
    

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


@csrf_exempt
def registrar_sintoma_app(request):

    dados = json.loads(request.body or "{}")

    lat = dados.get("latitude")
    lon = dados.get("longitude")

    local = obter_localizacao(lat, lon)

    empresa = Empresa.objects.first()

    grupo, classificacao = classificar_padrao(dados)

    RegistroSintoma.objects.create(
    id_anonimo=str(uuid.uuid4()),
    febre=dados.get("febre", False),
    tosse=dados.get("tosse", False),
    dor_corpo=dados.get("dor_corpo", False),
    cansaco=dados.get("cansaco", False),
    falta_ar=dados.get("falta_ar", False),
    latitude=lat,
    longitude=lon,
    pais=local.get("pais"),
    estado=local.get("estado"),
    cidade=local.get("cidade"),
    bairro=local.get("bairro"),
    condado=local.get("condado"),
    empresa=empresa,

    grupo=grupo,
    classificacao=classificacao
)

    return JsonResponse({
    "status": "ok",
    "grupo": grupo,
    "classificacao": classificacao
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

from django.db.utils import OperationalError

def criar_admin_automatico():
    try:
        from .models import Empresa

        if not Empresa.objects.exists():
            Empresa.objects.create(
                nome="Admin",
                email="admin@admin.com",
                senha="123456",
                ativo=True,
                plano="premium"
            )
            print("✅ Admin criado automaticamente")
    except OperationalError:
        pass


criar_admin_automatico()

from django.http import JsonResponse
from api.models import RegistroSintoma

def limpar_casos(request):
    total = RegistroSintoma.objects.count()
    RegistroSintoma.objects.all().delete()
    return JsonResponse({"apagados": total})