from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.db.models import Count
from .utils import probabilidade_doenca

from .models import RegistroSintoma, Empresa
from .utils_cidades import buscar_coordenada
from .utils import obter_localizacao
from django.conf import settings


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
    return render(request, 'login.html')


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
    return JsonResponse({"status": "ok"})


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

  <div class="footer" onclick="window.location.href='/'">
    Já tenho conta
  </div>

</div>

<script>
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
      body: JSON.stringify({ nome, email, senha })
    });

    const data = await res.json();

    loading.style.display = "none";

    if(data.token){
      localStorage.setItem("token", data.token);

      // 🔥 FLUXO PROFISSIONAL
      window.location.href = "/pagamento/";
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

    # 🔍 DEBUG DO HEADER
    auth_header = request.headers.get("Authorization")

    print("HEADER COMPLETO:", auth_header)

    if not auth_header:
        return JsonResponse({"erro": "Token não enviado"}, status=401)

    if not auth_header.startswith("Bearer "):
        return JsonResponse({"erro": "Formato inválido"}, status=401)

    token = auth_header.split(" ")[1]

    print("TOKEN RECEBIDO:", token)
    print("TAMANHO TOKEN:", len(token))

    # 🔐 DECODE
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"]
        )

        print("PAYLOAD:", payload)

    except Exception as e:
        print("ERRO REAL:", str(e))
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

    except Exception as e:
        print("ERRO:", str(e))
        return JsonResponse({"erro": "Token inválido"}, status=401)

    return JsonResponse({
        "status": "ok",
        "empresa_id": empresa_id
    })