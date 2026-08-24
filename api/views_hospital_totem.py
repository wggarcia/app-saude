"""
views_hospital_totem.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VITA OS — Biometria de Totem Hospitalar

Fluxo completo:
  1. Primeiro acesso: CPF + foto + assinatura → perfil biométrico criado
  2. Visitas seguintes: foto → match ArcFace → dados do paciente + plano
  3. Guia gerada automaticamente com assinatura armazenada → TISS
  4. PS: câmera passiva tenta match → ID temporário se falhar → triagem Manchester
  5. Triagem: enfermeira classifica sintomas → cor Manchester → notificação

Reutiliza DeepFace/ArcFace já configurado em views_biometria_facial.py.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import base64
import io
import json
import logging
import random
import secrets
import string
from datetime import datetime, timedelta

import numpy as np
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    BiometriaTotemPaciente,
    ChegadaPS,
    ConvenioPacienteTotem,
    Empresa,
    IdentidadePaciente,
    PedidoExameVita,
    TotemCheckinLog,
    TotemDispositivo,
    TriagemManchesterPS,
)
from .biometria_token import gerar_token as _gerar_selo_biometrico
from .views_dashboard import _empresa_autenticada

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────
LIMIAR_FACE_MATCH = 0.68   # Similaridade cosseno mínima (ArcFace)
BACKEND_FACIAL    = "ArcFace"
MODELO_DETECTOR   = "retinaface"


# ─── Face Engine (reutiliza DeepFace já instalado) ───────────────────────────

def _extrair_embedding(foto_base64: str) -> list[float]:
    """
    Recebe foto em base64 (PNG ou JPEG), retorna embedding ArcFace 512D.
    Lança ValueError se nenhum rosto for detectado.
    """
    try:
        from deepface import DeepFace
        import cv2
        import numpy as np

        # Decode base64 → imagem OpenCV
        if "," in foto_base64:
            foto_base64 = foto_base64.split(",", 1)[1]
        img_bytes = base64.b64decode(foto_base64)
        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Imagem inválida — não foi possível decodificar.")

        resultado = DeepFace.represent(
            img_path=img,
            model_name=BACKEND_FACIAL,
            detector_backend=MODELO_DETECTOR,
            enforce_detection=True,
            align=True,
        )
        if not resultado:
            raise ValueError("Nenhum rosto detectado na imagem.")

        emb = resultado[0]["embedding"]
        # Normalizar para unitário (necessário para similaridade cosseno)
        arr = np.array(emb, dtype=np.float32)
        norma = np.linalg.norm(arr)
        if norma > 0:
            arr = arr / norma
        return arr.tolist()

    except ImportError:
        raise ImportError("DeepFace não disponível. Verifique a instalação.")
    except Exception as exc:
        raise ValueError(f"Erro ao processar imagem: {exc}")


MAX_EMBEDDINGS_POR_PESSOA = 5   # principal + até 4 extras (câmeras/ângulos diferentes)


def _todos_embeddings(bio) -> list:
    """Lista de todos os embeddings de um paciente: principal + extras."""
    embs = [bio.embedding_json] if bio.embedding_json else []
    extras = bio.embeddings_extra or []
    if isinstance(extras, list):
        embs.extend(extras)
    return embs


def _buscar_por_embedding(embedding_novo: list[float], empresa_id: int):
    """
    Busca 1:N — compara o embedding com TODOS os vetores de cada paciente
    (principal + extras de outras câmeras). Retorna (identidade, score) ou (None, score_max).
    Performance: O(n·k) em numpy, adequado para até ~100k pacientes.
    """
    biometrias = BiometriaTotemPaciente.objects.filter(
        identidade__empresa_id=empresa_id,
        ativo=True,
    ).select_related("identidade")

    emb_novo = np.array(embedding_novo, dtype=np.float32)
    melhor_score = 0.0
    melhor_bio = None

    for bio in biometrias:
        for emb in _todos_embeddings(bio):
            try:
                score = float(np.dot(emb_novo, np.array(emb, dtype=np.float32)))
            except Exception:
                continue
            if score > melhor_score:
                melhor_score = score
                melhor_bio = bio

    if melhor_score >= LIMIAR_FACE_MATCH and melhor_bio:
        return melhor_bio.identidade, melhor_score
    return None, melhor_score


def _registrar_embedding_extra(bio, emb_novo: list[float]):
    """
    Aprende um novo ângulo/câmera: adiciona o embedding aos extras se ele for
    suficientemente diferente dos já guardados (evita duplicar quase-iguais).
    Mantém no máximo MAX_EMBEDDINGS_POR_PESSOA (descarta o mais antigo).
    """
    try:
        novo = np.array(emb_novo, dtype=np.float32)
        existentes = _todos_embeddings(bio)
        for e in existentes:
            if float(np.dot(novo, np.array(e, dtype=np.float32))) >= 0.92:
                return False  # já temos um vetor muito parecido — não precisa
        extras = list(bio.embeddings_extra or [])
        extras.append(emb_novo)
        # cap: principal conta como 1, então extras no máx. (MAX-1)
        if len(extras) > MAX_EMBEDDINGS_POR_PESSOA - 1:
            extras = extras[-(MAX_EMBEDDINGS_POR_PESSOA - 1):]
        bio.embeddings_extra = extras
        bio.save(update_fields=["embeddings_extra", "atualizado_em"])
        return True
    except Exception:
        return False


def _checkin_recente(empresa, identidade, minutos: int = 10):
    """
    Anti-duplicação: retorna um check-in do mesmo paciente feito nos últimos
    `minutos` (mesmo dia), se existir — para reaproveitar a senha em vez de
    gerar outra quando a pessoa escaneia/entra de novo em seguida.
    """
    if not identidade:
        return None
    limite = timezone.now() - timedelta(minutes=minutos)
    return (TotemCheckinLog.objects
            .filter(empresa=empresa, identidade=identidade, checkin_em__gte=limite)
            .exclude(senha_atendimento="")
            .order_by("-checkin_em")
            .first())


def _gerar_id_temp(empresa_id: int) -> str:
    """Gera ID temporário único para emergência: PS-2026-XXXX."""
    sufixo = "".join(random.choices(string.digits, k=4))
    ano = datetime.now().year
    return f"PS-{ano}-{sufixo}"


def _gerar_senha_atendimento(empresa) -> str:
    """
    Gera a próxima senha de atendimento (fila) do dia para o hospital.
    Formato: A001, A002, ... reiniciando a cada dia. Baixo volume no totem,
    então a contagem sequencial diária é suficiente.
    """
    hoje = timezone.now().date()
    usadas = (TotemCheckinLog.objects
              .filter(empresa=empresa, checkin_em__date=hoje)
              .exclude(senha_atendimento="")
              .count())
    return f"A{usadas + 1:03d}"


def _thumbnail(foto_base64: str, largura: int = 360) -> str:
    """
    Gera uma miniatura JPEG (base64 data URI) do rosto para exibição no painel.
    Reduz o tamanho para não pesar no banco. Best-effort: se falhar, retorna "".
    """
    try:
        import cv2
        import numpy as np
        b64 = foto_base64.split(",", 1)[1] if "," in foto_base64 else foto_base64
        arr = np.frombuffer(base64.b64decode(b64), dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return ""
        h, w = img.shape[:2]
        if w > largura:
            nova_h = int(h * (largura / w))
            img = cv2.resize(img, (largura, nova_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return ""
        return "data:image/jpeg;base64," + base64.b64encode(buf).decode("ascii")
    except Exception:
        return ""


def _dados_convenio(identidade) -> dict:
    """Retorna os dados do plano do paciente para exibição no check-in."""
    conv = ConvenioPacienteTotem.objects.filter(identidade=identidade).first()
    if not conv:
        return {"tem_plano": False}
    return {
        "tem_plano":   bool(conv.operadora or conv.numero_carteirinha),
        "operadora":   conv.operadora,
        "plano_nome":  conv.plano_nome,
        "carteirinha": conv.numero_carteirinha,
        "validade":    conv.validade.isoformat() if conv.validade else "",
    }


# ─── Classificação Manchester ─────────────────────────────────────────────────

def _classificar_manchester(dados: dict) -> tuple[str, str]:
    """
    Classifica cor do Protocolo de Manchester baseado nos sintomas.
    Retorna (cor, justificativa).
    """
    # Vermelho — risco imediato de vida
    if (dados.get("alteracao_consciencia") or dados.get("convulsao") or
            dados.get("dificuldade_respirar") and dados.get("saturacao_o2", 100) < 90 or
            dados.get("sangramento_ativo") and dados.get("dor_intensa")):
        return "vermelho", "Sinais de risco imediato de vida detectados."

    # Laranja — muito urgente
    if (dados.get("dor_toracica") or dados.get("dificuldade_respirar") or
            dados.get("sangramento_ativo") or
            dados.get("freq_cardiaca", 0) > 120 or dados.get("freq_cardiaca", 999) < 50 or
            dados.get("pa_sistolica", 120) < 90 or dados.get("pa_sistolica", 120) > 180 or
            dados.get("saturacao_o2", 100) < 94):
        return "laranja", "Sinais vitais alterados ou sintoma de alta urgência."

    # Amarelo — urgente
    if (dados.get("dor_intensa") or dados.get("febre_alta") or
            dados.get("trauma") or dados.get("gestante") or
            dados.get("crianca_menor_2") or
            dados.get("temperatura", 0) and float(dados.get("temperatura", 0)) > 38.5):
        return "amarelo", "Dor intensa, febre ou grupo de risco."

    # Verde
    if dados.get("febre_alta") or dados.get("dor_intensa"):
        return "verde", "Sintomas presentes mas sem sinais de urgência imediata."

    return "azul", "Sem sinais de urgência identificados."


# ─── Views HTML ───────────────────────────────────────────────────────────────

def totem_interface(request):
    """Tela do totem — fullscreen, sem login necessário (totem é dispositivo dedicado)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return render(request, "hospital_totem.html", {"empresa_nome": "Hospital"})
    return render(request, "hospital_totem.html", {
        "empresa_nome": empresa.nome,
        "empresa_id": empresa.id,
    })


def vita_hub_interface(request):
    """
    Central de operação do VITA OS — painel do operador/recepção com câmera
    de reconhecimento ao vivo, fila de check-ins do dia e fila de triagem do PS.
    Diferente do totem (autoatendimento do paciente), este é o painel de STAFF.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return render(request, "hospital_vita_hub.html", {"empresa_nome": "Hospital"})
    return render(request, "hospital_vita_hub.html", {
        "empresa_nome": empresa.nome,
        "empresa_id": empresa.id,
    })


def ps_triagem_interface(request):
    """Tela de triagem Manchester para a enfermagem do PS."""
    empresa = _empresa_autenticada(request)
    ctx = {"empresa_nome": "Hospital"}
    if empresa:
        ctx["empresa_nome"] = empresa.nome
        ctx["empresa_id"] = empresa.id
    return render(request, "hospital_ps_triagem.html", ctx)


# ─── API: Buscar paciente por CPF ─────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_totem_buscar_cpf(request):
    """POST {cpf} → dados do paciente se encontrado."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    cpf = "".join(c for c in data.get("cpf", "") if c.isdigit())
    if len(cpf) != 11:
        return JsonResponse({"erro": "CPF inválido."}, status=400)

    identidade = IdentidadePaciente.objects.filter(empresa=empresa, cpf=cpf).first()
    if not identidade:
        return JsonResponse({"encontrado": False, "cpf": cpf})

    tem_biometria = BiometriaTotemPaciente.objects.filter(identidade=identidade, ativo=True).exists()

    return JsonResponse({
        "encontrado":    True,
        "identidade_id": identidade.id,
        "nome":          identidade.nome,
        "cpf":           identidade.cpf,
        "cns":           identidade.cns,
        "tem_biometria": tem_biometria,
    })


# ─── API: Check-in por CPF (fallback quando a face não casa) ──────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_totem_checkin_cpf(request):
    """
    POST {cpf, foto_base64?}

    Fallback de identificação: o paciente já é cadastrado mas o reconhecimento
    facial não casou (câmera/luz/ângulo diferentes). Confirma a identidade pelo
    CPF e, se uma foto for enviada, RE-APRENDE o rosto daquela câmera (atualiza
    o embedding SEM apagar a assinatura). Registra o check-in.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    cpf = "".join(c for c in data.get("cpf", "") if c.isdigit())
    foto_b64 = data.get("foto_base64", "")
    if len(cpf) != 11:
        return JsonResponse({"erro": "CPF inválido."}, status=400)

    identidade = IdentidadePaciente.objects.filter(empresa=empresa, cpf=cpf).first()
    if not identidade:
        return JsonResponse({"encontrado": False, "erro": "Paciente não encontrado."}, status=404)

    bio = BiometriaTotemPaciente.objects.filter(identidade=identidade).first()

    # Re-aprendizado do rosto (best-effort): ADICIONA este ângulo/câmera aos
    # extras (sem apagar o principal nem a assinatura) — melhora o match futuro.
    reaprendido = False
    if foto_b64 and bio:
        try:
            emb = _extrair_embedding(foto_b64)
            bio.ativo = True
            thumb = _thumbnail(foto_b64)
            campos = ["ativo", "atualizado_em"]
            if thumb:
                bio.foto_thumb_base64 = thumb
                campos.append("foto_thumb_base64")
            bio.save(update_fields=campos)
            _registrar_embedding_extra(bio, emb)   # acumula câmera nova
            reaprendido = True
        except (ValueError, ImportError):
            pass  # face ruim nesta captura — check-in por CPF segue normalmente

    # Anti-duplicação: reaproveita a senha se já entrou nos últimos 10 min.
    recente = _checkin_recente(empresa, identidade)
    if recente:
        senha = recente.senha_atendimento
        checkin = recente
    else:
        senha = _gerar_senha_atendimento(empresa)
        checkin = TotemCheckinLog.objects.create(
            empresa=empresa,
            identidade=identidade,
            score_similaridade=0.0,
            tipo_entrada="eletivo",
            senha_atendimento=senha,
        )

    primeiro_nome = (identidade.nome or "").split(" ")[0] or "paciente"
    return JsonResponse({
        "reconhecido":    True,
        "via":            "cpf",
        "identidade_id":  identidade.id,
        "nome":           identidade.nome,
        "cpf":            identidade.cpf,
        "cns":            identidade.cns,
        "tem_assinatura": bool(bio and bio.assinatura_base64),
        "face_reaprendida": reaprendido,
        "checkin_id":     checkin.id,
        "agendamento":    _buscar_agendamento_hoje(identidade),
        "senha":          senha,
        "mensagem":       f"Olá, {primeiro_nome}! Check-in confirmado pelo CPF. Aguarde ser chamado(a).",
        "plano":          _dados_convenio(identidade),
        "proximo_passo":  "validar_plano",
    })


# ─── API: Cadastrar biometria (primeiro acesso) ───────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_totem_cadastrar(request):
    """
    POST {cpf, foto_base64, assinatura_base64, consentimento_lgpd: true}

    Fluxo:
      1. Valida CPF → busca ou cria IdentidadePaciente
      2. Extrai embedding ArcFace da foto
      3. Armazena embedding + assinatura
      4. Registra consentimento LGPD
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    cpf = "".join(c for c in data.get("cpf", "") if c.isdigit())
    foto_b64 = data.get("foto_base64", "")
    assinatura_b64 = data.get("assinatura_base64", "")
    consentimento = data.get("consentimento_lgpd", False)
    nome = data.get("nome", "").strip()
    # Dados do plano de saúde (opcionais)
    operadora   = (data.get("operadora") or "").strip()
    plano_nome  = (data.get("plano_nome") or "").strip()
    carteirinha = (data.get("carteirinha") or "").strip()
    validade    = (data.get("validade") or "").strip()  # "AAAA-MM-DD" ou ""

    if len(cpf) != 11:
        return JsonResponse({"erro": "CPF inválido."}, status=400)
    if not nome:
        return JsonResponse({"erro": "Nome é obrigatório."}, status=400)
    if not foto_b64:
        return JsonResponse({"erro": "Foto obrigatória."}, status=400)
    if not consentimento:
        return JsonResponse({"erro": "Consentimento LGPD obrigatório."}, status=400)

    # Extrair embedding
    try:
        embedding = _extrair_embedding(foto_b64)
    except (ValueError, ImportError) as exc:
        return JsonResponse({"erro": str(exc)}, status=422)

    with transaction.atomic():
        # Buscar ou criar identidade
        identidade, criada = IdentidadePaciente.objects.get_or_create(
            empresa=empresa, cpf=cpf,
            defaults={"nome": nome or f"Paciente CPF {cpf}"},
        )
        if nome and identidade.nome != nome:
            identidade.nome = nome
            identidade.save(update_fields=["nome"])

        # Criar ou atualizar biometria
        bio, _ = BiometriaTotemPaciente.objects.update_or_create(
            identidade=identidade,
            defaults={
                "embedding_json":    embedding,
                "assinatura_base64": assinatura_b64,
                "foto_thumb_base64": _thumbnail(foto_b64),
                "consentimento_lgpd": True,
                "consentimento_em":   timezone.now(),
                "ativo":              True,
            },
        )

        # Dados do plano (se informados)
        if operadora or carteirinha:
            validade_dt = None
            if validade:
                try:
                    validade_dt = datetime.strptime(validade[:10], "%Y-%m-%d").date()
                except ValueError:
                    validade_dt = None
            ConvenioPacienteTotem.objects.update_or_create(
                identidade=identidade,
                defaults={
                    "operadora":          operadora,
                    "plano_nome":         plano_nome,
                    "numero_carteirinha": carteirinha,
                    "validade":           validade_dt,
                },
            )

        # Senha de atendimento (fila) + log de check-in
        senha = _gerar_senha_atendimento(empresa)
        checkin = TotemCheckinLog.objects.create(
            empresa=empresa,
            identidade=identidade,
            score_similaridade=1.0,
            tipo_entrada="novo_cadastro",
            senha_atendimento=senha,
        )
        # Selo biométrico (cadastro = rosto capturado e verificado)
        checkin.biometria_token = _gerar_selo_biometrico(checkin.id, empresa.id, identidade.cpf, 1.0)
        checkin.save(update_fields=["biometria_token"])

    primeiro_nome = (identidade.nome or "").split(" ")[0] or "paciente"
    return JsonResponse({
        "ok":            True,
        "identidade_id": identidade.id,
        "nome":          identidade.nome,
        "cpf":           identidade.cpf,
        "cadastro":      "criado" if criada else "atualizado",
        "checkin_id":    checkin.id,
        "senha":         senha,
        "mensagem":      f"Bem-vindo(a), {primeiro_nome}! Cadastro concluído. Guarde sua senha e aguarde ser chamado(a).",
        "plano":         _dados_convenio(identidade),
    }, status=201)


# ─── API: Reconhecer rosto ────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_totem_reconhecer(request):
    """
    POST {foto_base64, tipo_entrada: 'eletivo'|'emergencia'}

    Fluxo:
      1. Extrai embedding da foto
      2. Busca 1:N no banco do hospital
      3. Se match: retorna dados do paciente + inicia validação TISS
      4. Se não match: cria ID temporário (emergência) ou pede CPF (eletivo)
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    foto_b64 = data.get("foto_base64", "")
    tipo_entrada = data.get("tipo_entrada", "eletivo")

    if not foto_b64:
        return JsonResponse({"erro": "Foto obrigatória."}, status=400)

    # Extrair embedding
    try:
        embedding = _extrair_embedding(foto_b64)
    except (ValueError, ImportError) as exc:
        return JsonResponse({"reconhecido": False, "erro": str(exc)}, status=422)

    # Buscar match
    identidade, score = _buscar_por_embedding(embedding, empresa.id)

    if identidade:
        # ✅ Paciente reconhecido
        bio = identidade.biometria_totem
        # Atualiza a miniatura do rosto (identificação visual no painel).
        if bio and not bio.foto_thumb_base64:
            thumb = _thumbnail(foto_b64)
            if thumb:
                bio.foto_thumb_base64 = thumb
                bio.save(update_fields=["foto_thumb_base64", "atualizado_em"])
        # Aprende esta câmera/ângulo se o match não foi quase-perfeito
        # (score < 0.92 sugere condição de captura diferente das já guardadas).
        if bio and score < 0.92:
            _registrar_embedding_extra(bio, embedding)

        # Anti-duplicação: se já entrou nos últimos 10 min, reaproveita a senha.
        recente = _checkin_recente(empresa, identidade)
        if recente:
            senha = recente.senha_atendimento
            checkin = recente
            duplicado = True
        else:
            senha = _gerar_senha_atendimento(empresa)
            checkin = TotemCheckinLog.objects.create(
                empresa=empresa,
                identidade=identidade,
                score_similaridade=score,
                tipo_entrada=tipo_entrada,
                senha_atendimento=senha,
            )
            # Selo biométrico (paciente verificado por rosto) — viaja com a guia TISS
            checkin.biometria_token = _gerar_selo_biometrico(checkin.id, empresa.id, identidade.cpf, score)
            checkin.save(update_fields=["biometria_token"])
            duplicado = False

        # Buscar agendamento do dia
        agendamento = _buscar_agendamento_hoje(identidade)
        primeiro_nome = (identidade.nome or "").split(" ")[0] or "paciente"

        return JsonResponse({
            "reconhecido":     True,
            "score":           round(score, 4),
            "identidade_id":   identidade.id,
            "nome":            identidade.nome,
            "cpf":             identidade.cpf,
            "cns":             identidade.cns,
            "tem_assinatura":  bool(bio.assinatura_base64),
            "checkin_id":      checkin.id,
            "agendamento":     agendamento,
            "senha":           senha,
            "duplicado":       duplicado,
            "mensagem":        (f"Olá, {primeiro_nome}! Você já fez check-in — sua senha é {senha}. Aguarde ser chamado(a)."
                                if duplicado else
                                f"Olá, {primeiro_nome}! Check-in confirmado. Aguarde ser chamado(a)."),
            "plano":           _dados_convenio(identidade),
            "proximo_passo":   "validar_plano",
        })

    else:
        # ❌ Não reconhecido
        if tipo_entrada == "emergencia":
            id_temp = _gerar_id_temp(empresa.id)
            checkin = TotemCheckinLog.objects.create(
                empresa=empresa,
                id_temporario=id_temp,
                score_similaridade=score,
                tipo_entrada="emergencia",
            )
            return JsonResponse({
                "reconhecido":   False,
                "id_temporario": id_temp,
                "checkin_id":    checkin.id,
                "proximo_passo": "triagem_manchester",
                "mensagem":      "Paciente não identificado. ID temporário gerado. Encaminhar para triagem.",
            })
        else:
            return JsonResponse({
                "reconhecido":   False,
                "score_max":     round(score, 4),
                "proximo_passo": "solicitar_cpf",
                "mensagem":      "Rosto não encontrado. Por favor, informe seu CPF.",
            })


def _buscar_agendamento_hoje(identidade: IdentidadePaciente) -> dict | None:
    """Busca agendamento do dia para o paciente."""
    from django.utils import timezone as tz
    hoje = tz.now().date()
    try:
        from .models import AgendamentoPaciente
        ag = AgendamentoPaciente.objects.filter(
            identidade=identidade,
            data_consulta=hoje,
            status="agendado",
        ).select_related("identidade").first()
        if ag:
            return {
                "id":           ag.id,
                "medico":       ag.medico_nome,
                "especialidade": ag.especialidade,
                "horario":      ag.horario.strftime("%H:%M") if ag.horario else "",
                "sala":         getattr(ag, "sala", ""),
            }
    except Exception:
        pass
    return None


# ─── API: Triagem Manchester ──────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_ps_triagem_classificar(request):
    """
    POST {checkin_id?, id_temporario?, nome_paciente, queixa_principal,
          dor_intensa, alteracao_consciencia, dificuldade_respirar,
          sangramento_ativo, febre_alta, convulsao, dor_toracica,
          trauma, gestante, crianca_menor_2,
          pa_sistolica?, pa_diastolica?, freq_cardiaca?,
          freq_respiratoria?, saturacao_o2?, temperatura?,
          enfermeiro?}

    Classifica cor Manchester e registra a triagem.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    nome = data.get("nome_paciente", "").strip()
    queixa = data.get("queixa_principal", "").strip()
    if not nome or not queixa:
        return JsonResponse({"erro": "nome_paciente e queixa_principal obrigatórios."}, status=400)

    # Classificar
    cor, justificativa = _classificar_manchester(data)

    # Recuperar checkin e identidade
    checkin = None
    identidade = None
    if data.get("checkin_id"):
        try:
            checkin = TotemCheckinLog.objects.get(pk=data["checkin_id"], empresa=empresa)
            identidade = checkin.identidade
        except TotemCheckinLog.DoesNotExist:
            pass

    id_temp = data.get("id_temporario", "") or (checkin.id_temporario if checkin else "")

    with transaction.atomic():
        triagem = TriagemManchesterPS.objects.create(
            empresa=empresa,
            checkin=checkin,
            identidade=identidade,
            id_temporario=id_temp,
            nome_paciente=nome,
            queixa_principal=queixa,
            dor_intensa=data.get("dor_intensa", False),
            alteracao_consciencia=data.get("alteracao_consciencia", False),
            dificuldade_respirar=data.get("dificuldade_respirar", False),
            sangramento_ativo=data.get("sangramento_ativo", False),
            febre_alta=data.get("febre_alta", False),
            convulsao=data.get("convulsao", False),
            dor_toracica=data.get("dor_toracica", False),
            trauma=data.get("trauma", False),
            gestante=data.get("gestante", False),
            crianca_menor_2=data.get("crianca_menor_2", False),
            pa_sistolica=data.get("pa_sistolica") or None,
            pa_diastolica=data.get("pa_diastolica") or None,
            freq_cardiaca=data.get("freq_cardiaca") or None,
            freq_respiratoria=data.get("freq_respiratoria") or None,
            saturacao_o2=data.get("saturacao_o2") or None,
            temperatura=data.get("temperatura") or None,
            cor_classificacao=cor,
            justificativa_ia=justificativa,
            enfermeiro=data.get("enfermeiro", ""),
        )

    _COR_LABEL = {
        "vermelho": "🔴 EMERGÊNCIA — Atendimento imediato",
        "laranja":  "🟠 MUITO URGENTE — Até 10 minutos",
        "amarelo":  "🟡 URGENTE — Até 30 minutos",
        "verde":    "🟢 POUCO URGENTE — Até 120 minutos",
        "azul":     "🔵 NÃO URGENTE",
    }

    return JsonResponse({
        "ok":             True,
        "triagem_id":     triagem.id,
        "cor":            cor,
        "cor_label":      _COR_LABEL[cor],
        "justificativa":  justificativa,
        "nome_paciente":  nome,
        "id_temporario":  id_temp,
        "triado_em":      triagem.triado_em.isoformat(),
    }, status=201)


# ─── API: Check-ins recentes do totem (com foto) ──────────────────────────────

@require_http_methods(["GET"])
def api_totem_checkins_recentes(request):
    """
    GET — últimos check-ins do totem do dia (recepção/eletivo + novos cadastros),
    com nome, senha de atendimento, foto (miniatura), como foi identificado e hora.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    hoje = timezone.now().date()
    checkins = (TotemCheckinLog.objects
                .filter(empresa=empresa, checkin_em__date=hoje)
                .exclude(tipo_entrada="emergencia")   # emergência aparece no painel do PS
                .select_related("identidade", "identidade__biometria_totem")
                .order_by("-checkin_em")[:20])

    lista = []
    for c in checkins:
        ident = c.identidade
        bio = getattr(ident, "biometria_totem", None) if ident else None
        if c.tipo_entrada == "novo_cadastro":
            via = "Novo cadastro"
        elif c.score_similaridade and c.score_similaridade >= LIMIAR_FACE_MATCH:
            via = "Reconhecimento facial"
        else:
            via = "CPF"
        lista.append({
            "id":       c.id,
            "nome":     ident.nome if ident else "—",
            "cpf":      ident.cpf if ident else "",
            "senha":    c.senha_atendimento,
            "via":      via,
            "hora":     c.checkin_em.strftime("%H:%M"),
            "foto":     (bio.foto_thumb_base64 if bio else "") or "",
            "score":    round(c.score_similaridade, 3) if c.score_similaridade else None,
        })

    return JsonResponse({"checkins": lista, "total": len(lista)})


# ─── API: Painel do PS ────────────────────────────────────────────────────────

@require_http_methods(["GET"])
def api_ps_painel(request):
    """GET — lista triagens ativas do dia no PS, ordenadas por urgência."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    hoje = timezone.now().date()
    triagens = TriagemManchesterPS.objects.filter(
        empresa=empresa,
        triado_em__date=hoje,
    ).order_by("triado_em")

    _ORDEM_COR = {"vermelho": 0, "laranja": 1, "amarelo": 2, "verde": 3, "azul": 4}

    lista = sorted([
        {
            "id":            t.id,
            "nome":          t.nome_paciente,
            "id_temp":       t.id_temporario,
            "cor":           t.cor_classificacao,
            "cor_label":     t.get_cor_classificacao_display(),
            "queixa":        t.queixa_principal,
            "triado_em":     t.triado_em.strftime("%H:%M"),
            "enfermeiro":    t.enfermeiro,
            "sinais_vitais": {
                "pa":  f"{t.pa_sistolica}/{t.pa_diastolica}" if t.pa_sistolica else None,
                "fc":  t.freq_cardiaca,
                "fr":  t.freq_respiratoria,
                "spo2": t.saturacao_o2,
                "temp": str(t.temperatura) if t.temperatura else None,
            },
        }
        for t in triagens
    ], key=lambda x: _ORDEM_COR.get(x["cor"], 9))

    resumo = {cor: 0 for cor in ["vermelho", "laranja", "amarelo", "verde", "azul"]}
    for t in lista:
        resumo[t["cor"]] = resumo.get(t["cor"], 0) + 1

    return JsonResponse({"triagens": lista, "resumo": resumo, "total": len(lista)})


# ─── API: Estatísticas do Totem ───────────────────────────────────────────────

@require_http_methods(["GET"])
def api_totem_stats(request):
    """GET — estatísticas de uso do totem no dia."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    hoje = timezone.now().date()
    checkins_hoje = TotemCheckinLog.objects.filter(empresa=empresa, checkin_em__date=hoje)
    total_biometrias = BiometriaTotemPaciente.objects.filter(identidade__empresa=empresa, ativo=True).count()

    return JsonResponse({
        "hoje": {
            "total_checkins":    checkins_hoje.count(),
            "reconhecidos":      checkins_hoje.filter(tipo_entrada="eletivo").count(),
            "emergencias":       checkins_hoje.filter(tipo_entrada="emergencia").count(),
            "novos_cadastros":   checkins_hoje.filter(tipo_entrada="novo_cadastro").count(),
            "nao_reconhecidos":  checkins_hoje.filter(tipo_entrada="nao_reconhecido").count(),
        },
        "total_pacientes_cadastrados": total_biometrias,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Gestão de Dispositivos de Kiosk (pareamento)
# Estas rotas exigem LOGIN DE OPERADOR (não token de dispositivo).
# ═══════════════════════════════════════════════════════════════════════════════

def _serializar_dispositivo(d, incluir_token=False):
    dados = {
        "id":            d.id,
        "nome":          d.nome,
        "tipo":          d.tipo,
        "tipo_label":    d.get_tipo_display(),
        "ativo":         d.ativo,
        "ultimo_acesso": d.ultimo_acesso.isoformat() if d.ultimo_acesso else None,
        "criado_em":     d.criado_em.isoformat(),
    }
    if incluir_token:
        rota = "/hospital/ps/triagem/" if d.tipo == "ps" else "/hospital/totem/"
        dados["token"] = d.token
        dados["kiosk_url"] = f"{rota}?totem_token={d.token}"
    return dados


@require_http_methods(["GET"])
def api_totem_dispositivos_listar(request):
    """GET — lista os dispositivos de kiosk do hospital (sem expor o token)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    disps = TotemDispositivo.objects.filter(empresa=empresa)
    return JsonResponse({
        "dispositivos": [_serializar_dispositivo(d) for d in disps]
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_totem_dispositivo_criar(request):
    """
    POST {nome, tipo:'totem'|'ps'} → cria um dispositivo e retorna o token +
    a URL do kiosk (o token só é exibido nesta resposta de criação).
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    nome = (data.get("nome") or "").strip()
    tipo = data.get("tipo", "totem")
    if not nome:
        return JsonResponse({"erro": "Nome do dispositivo é obrigatório."}, status=400)
    if tipo not in ("totem", "ps"):
        tipo = "totem"

    disp = TotemDispositivo.objects.create(
        empresa=empresa,
        nome=nome,
        tipo=tipo,
        token=secrets.token_urlsafe(32),
    )
    return JsonResponse({
        "ok": True,
        "dispositivo": _serializar_dispositivo(disp, incluir_token=True),
    }, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def api_totem_dispositivo_revogar(request):
    """POST {id} → revoga (desativa) um dispositivo. O token deixa de funcionar."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)

    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    disp = TotemDispositivo.objects.filter(pk=data.get("id"), empresa=empresa).first()
    if not disp:
        return JsonResponse({"erro": "Dispositivo não encontrado."}, status=404)

    disp.ativo = False
    disp.save(update_fields=["ativo"])
    return JsonResponse({"ok": True, "id": disp.id})


# ═══════════════════════════════════════════════════════════════════════════════
# Fluxo pós-consulta — Pedido de exame + Estação de exame (reconhecimento facial)
# ═══════════════════════════════════════════════════════════════════════════════

_STATUS_EXAME_ATIVO = ("solicitado", "autorizado", "aguardando", "em_atendimento")


def _serializar_pedido_exame(p):
    return {
        "id":        p.id,
        "tipo":      p.tipo,
        "tipo_label": p.get_tipo_display(),
        "exames":    p.exames or [],
        "estacao":   p.estacao,
        "status":    p.status,
        "status_label": p.get_status_display(),
        "medico":    p.medico_solicitante,
        "autorizado": p.status not in ("solicitado",),
        "observacoes": p.observacoes,
        "paciente":  p.identidade.nome if p.identidade_id else "",
        "resultado_laudo": p.resultado_laudo,
        "resultado_interpretacao": p.resultado_interpretacao,
        "resultado_interpretacao_label": p.get_resultado_interpretacao_display() if p.resultado_interpretacao else "",
        "resultado_por": p.resultado_por,
        "resultado_em": p.resultado_em.strftime("%d/%m %H:%M") if p.resultado_em else "",
        "resultado_visto": p.resultado_visto,
        "criado_em": p.criado_em.strftime("%d/%m %H:%M"),
    }


def estacao_exame_interface(request):
    """Tela da estação de exame (lab/imagem) — kiosk com reconhecimento facial."""
    empresa = _empresa_autenticada(request)
    ctx = {"empresa_nome": empresa.nome if empresa else "Hospital"}
    if empresa:
        ctx["empresa_id"] = empresa.id
    return render(request, "hospital_estacao_exame.html", ctx)


@csrf_exempt
@require_http_methods(["POST"])
def api_exame_criar(request):
    """
    POST {identidade_id | cpf, tipo, exames:[{nome,codigo_tuss}], estacao,
          medico_solicitante, observacoes, checkin_id?}
    Cria o pedido de exame pós-consulta. Se o paciente tem plano, gera o selo
    biométrico e marca a autorização como solicitada (auto-autorização).
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    ident = None
    if data.get("identidade_id"):
        ident = IdentidadePaciente.objects.filter(pk=data["identidade_id"], empresa=empresa).first()
    if not ident and data.get("cpf"):
        cpf = "".join(c for c in data["cpf"] if c.isdigit())
        ident = IdentidadePaciente.objects.filter(empresa=empresa, cpf=cpf).first()
    if not ident:
        return JsonResponse({"erro": "Paciente não encontrado."}, status=404)

    exames = data.get("exames") or []
    if isinstance(exames, str):
        exames = [{"nome": e.strip()} for e in exames.split(",") if e.strip()]
    if not exames:
        return JsonResponse({"erro": "Informe ao menos um exame."}, status=400)

    tem_plano = ConvenioPacienteTotem.objects.filter(identidade=ident).exists()
    checkin = None
    if data.get("checkin_id"):
        checkin = TotemCheckinLog.objects.filter(pk=data["checkin_id"], empresa=empresa).first()

    pedido = PedidoExameVita.objects.create(
        empresa=empresa,
        identidade=ident,
        checkin=checkin,
        tipo=data.get("tipo", "laboratorio"),
        exames=exames,
        estacao=data.get("estacao", ""),
        medico_solicitante=data.get("medico_solicitante", ""),
        observacoes=data.get("observacoes", ""),
    )
    # Auto-autorização: paciente com plano → gera selo e marca solicitada
    if tem_plano:
        pedido.biometria_token = _gerar_selo_biometrico(pedido.checkin_id or pedido.id, empresa.id, ident.cpf, 1.0)
        pedido.autorizacao_solicitada = True
        pedido.status = "autorizado"
        pedido.save(update_fields=["biometria_token", "autorizacao_solicitada", "status"])

    return JsonResponse({
        "ok": True,
        "pedido": _serializar_pedido_exame(pedido),
        "autorizacao": "solicitada ao plano" if tem_plano else "paciente sem plano cadastrado",
    }, status=201)


@csrf_exempt
@require_http_methods(["POST"])
def api_estacao_reconhecer(request):
    """
    POST {foto_base64}
    Reconhece o paciente na estação de exame e retorna os exames pendentes dele.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    foto_b64 = data.get("foto_base64", "")
    if not foto_b64:
        return JsonResponse({"erro": "Foto obrigatória."}, status=400)

    try:
        embedding = _extrair_embedding(foto_b64)
    except (ValueError, ImportError) as exc:
        return JsonResponse({"reconhecido": False, "erro": str(exc)}, status=422)

    identidade, score = _buscar_por_embedding(embedding, empresa.id)
    if not identidade:
        return JsonResponse({
            "reconhecido": False,
            "score_max": round(score, 4),
            "mensagem": "Rosto não encontrado. Procure a recepção.",
        })

    pendentes = PedidoExameVita.objects.filter(
        empresa=empresa, identidade=identidade, status__in=_STATUS_EXAME_ATIVO,
    ).order_by("criado_em")

    bio = getattr(identidade, "biometria_totem", None)
    return JsonResponse({
        "reconhecido": True,
        "score": round(score, 4),
        "identidade_id": identidade.id,
        "nome": identidade.nome,
        "foto": (bio.foto_thumb_base64 if bio else "") or "",
        "exames": [_serializar_pedido_exame(p) for p in pendentes],
        "sem_exames": not pendentes.exists(),
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_exame_avancar(request):
    """POST {pedido_id, novo_status} — avança o status do exame na estação."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    pedido = PedidoExameVita.objects.filter(pk=data.get("pedido_id"), empresa=empresa).first()
    if not pedido:
        return JsonResponse({"erro": "Pedido não encontrado."}, status=404)

    novo = data.get("novo_status", "")
    validos = {s[0] for s in PedidoExameVita.STATUS}
    if novo not in validos:
        return JsonResponse({"erro": "Status inválido."}, status=400)
    pedido.status = novo
    pedido.save(update_fields=["status", "atualizado_em"])
    return JsonResponse({"ok": True, "pedido": _serializar_pedido_exame(pedido)})


@require_http_methods(["GET"])
def api_exames_paciente(request):
    """GET ?identidade_id= | ?cpf= — lista pedidos de exame de um paciente."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    ident = None
    if request.GET.get("identidade_id"):
        ident = IdentidadePaciente.objects.filter(pk=request.GET["identidade_id"], empresa=empresa).first()
    if not ident and request.GET.get("cpf"):
        cpf = "".join(c for c in request.GET["cpf"] if c.isdigit())
        ident = IdentidadePaciente.objects.filter(empresa=empresa, cpf=cpf).first()
    if not ident:
        return JsonResponse({"erro": "Paciente não encontrado."}, status=404)
    pedidos = PedidoExameVita.objects.filter(empresa=empresa, identidade=ident).order_by("-criado_em")[:50]
    return JsonResponse({
        "identidade_id": ident.id, "nome": ident.nome,
        "pedidos": [_serializar_pedido_exame(p) for p in pedidos],
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PS — Câmera passiva na entrada (detecta chegada antes do balcão)
# ═══════════════════════════════════════════════════════════════════════════════

def ps_entrada_interface(request):
    """Tela da entrada do PS: câmera passiva + feed de chegadas pra enfermagem."""
    empresa = _empresa_autenticada(request)
    ctx = {"empresa_nome": empresa.nome if empresa else "Hospital"}
    if empresa:
        ctx["empresa_id"] = empresa.id
    return render(request, "hospital_ps_entrada.html", ctx)


@csrf_exempt
@require_http_methods(["POST"])
def api_ps_entrada_detectar(request):
    """
    POST {foto_base64}
    Detecção passiva: reconhece o rosto na entrada do PS. Se reconhecer e não
    houver detecção recente do mesmo paciente (5 min), registra a chegada e
    devolve os dados pra tela da enfermagem. Não reconhecido → não cria nada
    (evita poluir; o desconhecido é tratado na triagem).
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    foto_b64 = data.get("foto_base64", "")
    if not foto_b64:
        return JsonResponse({"erro": "Foto obrigatória."}, status=400)

    try:
        embedding = _extrair_embedding(foto_b64)
    except (ValueError, ImportError):
        return JsonResponse({"reconhecido": False})  # sem rosto no frame — silencioso

    identidade, score = _buscar_por_embedding(embedding, empresa.id)
    if not identidade:
        return JsonResponse({"reconhecido": False, "score_max": round(score, 4)})

    # Dedup: já detectado nos últimos 5 min?
    limite = timezone.now() - timedelta(minutes=5)
    ja = ChegadaPS.objects.filter(empresa=empresa, identidade=identidade, detectado_em__gte=limite).first()
    nova = not ja
    if nova:
        ChegadaPS.objects.create(empresa=empresa, identidade=identidade, score=score)

    return JsonResponse({
        "reconhecido": True,
        "nova": nova,
        "nome": identidade.nome,
        "identidade_id": identidade.id,
    })


def _resumo_paciente_ps(identidade):
    """Dados rápidos do paciente pra tela da enfermagem (prontuário resumido)."""
    bio = getattr(identidade, "biometria_totem", None)
    conv = ConvenioPacienteTotem.objects.filter(identidade=identidade).first()
    ultima_triagem = (TriagemManchesterPS.objects
                      .filter(empresa=identidade.empresa, identidade=identidade)
                      .order_by("-triado_em").first())
    return {
        "identidade_id": identidade.id,
        "nome": identidade.nome,
        "cpf": identidade.cpf,
        "foto": (bio.foto_thumb_base64 if bio else "") or "",
        "plano": (conv.operadora if conv else ""),
        "carteirinha": (conv.numero_carteirinha if conv else ""),
        "ultima_triagem": (ultima_triagem.get_cor_classificacao_display() if ultima_triagem else ""),
        "ultima_triagem_em": (ultima_triagem.triado_em.strftime("%d/%m/%Y") if ultima_triagem else ""),
    }


@require_http_methods(["GET"])
def api_ps_chegadas(request):
    """GET — chegadas detectadas hoje na entrada do PS (feed da enfermagem)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    # Janela móvel (últimas 12h) em vez de "data de hoje" — evita o corte de
    # data/fuso (servidor em UTC) que escondia chegadas recentes no feed do PS.
    desde = timezone.now() - timedelta(hours=12)
    chegadas = (ChegadaPS.objects
                .filter(empresa=empresa, detectado_em__gte=desde)
                .select_related("identidade", "identidade__biometria_totem")
                .order_by("-detectado_em")[:30])
    lista = []
    for c in chegadas:
        if not c.identidade:
            continue
        item = _resumo_paciente_ps(c.identidade)
        item.update({
            "chegada_id": c.id,
            "atendido": c.atendido,
            "hora": c.detectado_em.strftime("%H:%M"),
            "score": round(c.score, 3),
        })
        lista.append(item)
    return JsonResponse({"chegadas": lista, "total": len(lista)})


@csrf_exempt
@require_http_methods(["POST"])
def api_ps_chegada_atender(request):
    """POST {chegada_id} — marca a chegada como atendida (some do topo do feed)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)
    c = ChegadaPS.objects.filter(pk=data.get("chegada_id"), empresa=empresa).first()
    if not c:
        return JsonResponse({"erro": "Chegada não encontrada."}, status=404)
    c.atendido = True
    c.save(update_fields=["atendido"])
    return JsonResponse({"ok": True})


# ─── Resultado de exame (laudo de volta ao médico) ────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_exame_resultado(request):
    """
    POST {pedido_id, laudo, interpretacao, resultado_por?}
    Lança o resultado/laudo do exame → status 'concluido' → fica disponível
    pro médico solicitante no painel de resultados.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    pedido = PedidoExameVita.objects.filter(pk=data.get("pedido_id"), empresa=empresa).first()
    if not pedido:
        return JsonResponse({"erro": "Pedido não encontrado."}, status=404)

    laudo = (data.get("laudo") or "").strip()
    if not laudo:
        return JsonResponse({"erro": "Informe o laudo/resultado."}, status=400)
    interp = data.get("interpretacao", "")
    validas = {"normal", "alterado", "critico", "inconclusivo"}
    if interp and interp not in validas:
        interp = ""

    pedido.resultado_laudo = laudo
    pedido.resultado_interpretacao = interp
    pedido.resultado_por = data.get("resultado_por", "")
    pedido.resultado_em = timezone.now()
    pedido.resultado_visto = False
    pedido.status = "concluido"
    pedido.save(update_fields=[
        "resultado_laudo", "resultado_interpretacao", "resultado_por",
        "resultado_em", "resultado_visto", "status", "atualizado_em",
    ])
    return JsonResponse({"ok": True, "pedido": _serializar_pedido_exame(pedido)})


@require_http_methods(["GET"])
def api_exames_resultados(request):
    """
    GET — resultados de exame prontos (concluídos), pro médico ver.
    ?novos=1 mostra só os ainda não vistos.
    """
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    qs = (PedidoExameVita.objects
          .filter(empresa=empresa, status="concluido")
          .exclude(resultado_laudo="")
          .select_related("identidade")
          .order_by("-resultado_em"))
    if request.GET.get("novos") == "1":
        qs = qs.filter(resultado_visto=False)
    resultados = [_serializar_pedido_exame(p) for p in qs[:50]]
    nao_vistos = PedidoExameVita.objects.filter(
        empresa=empresa, status="concluido", resultado_visto=False
    ).exclude(resultado_laudo="").count()
    # Exames já realizados que ainda aguardam o lançamento do laudo
    aguardando = PedidoExameVita.objects.filter(
        empresa=empresa, status="realizado",
    ).select_related("identidade").order_by("-atualizado_em")[:50]
    return JsonResponse({
        "resultados": resultados,
        "nao_vistos": nao_vistos,
        "aguardando_resultado": [_serializar_pedido_exame(p) for p in aguardando],
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_exame_marcar_visto(request):
    """POST {pedido_id} — médico marca o resultado como visto."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado."}, status=401)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)
    pedido = PedidoExameVita.objects.filter(pk=data.get("pedido_id"), empresa=empresa).first()
    if not pedido:
        return JsonResponse({"erro": "Pedido não encontrado."}, status=404)
    pedido.resultado_visto = True
    pedido.save(update_fields=["resultado_visto"])
    return JsonResponse({"ok": True})
