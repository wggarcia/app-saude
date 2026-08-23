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
from datetime import datetime

import numpy as np
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import (
    BiometriaTotemPaciente,
    ConvenioPacienteTotem,
    Empresa,
    IdentidadePaciente,
    TotemCheckinLog,
    TotemDispositivo,
    TriagemManchesterPS,
)
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


def _buscar_por_embedding(embedding_novo: list[float], empresa_id: int):
    """
    Busca 1:N — compara embedding com todos os pacientes do hospital.
    Retorna (identidade, score) ou (None, 0.0).
    Performance: O(n) em numpy, adequado para até ~100k pacientes.
    """
    biometrias = BiometriaTotemPaciente.objects.filter(
        identidade__empresa_id=empresa_id,
        ativo=True,
    ).select_related("identidade")

    if not biometrias.exists():
        return None, 0.0

    emb_novo = np.array(embedding_novo, dtype=np.float32)
    melhor_score = 0.0
    melhor_bio = None

    for bio in biometrias:
        emb_salvo = np.array(bio.embedding_json, dtype=np.float32)
        score = float(np.dot(emb_novo, emb_salvo))  # Vetores já normalizados
        if score > melhor_score:
            melhor_score = score
            melhor_bio = bio

    if melhor_score >= LIMIAR_FACE_MATCH and melhor_bio:
        return melhor_bio.identidade, melhor_score
    return None, melhor_score


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


def _thumbnail(foto_base64: str, largura: int = 200) -> str:
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

    # Re-aprendizado do rosto (best-effort): atualiza o embedding, preserva a assinatura.
    reaprendido = False
    if foto_b64 and bio:
        try:
            bio.embedding_json = _extrair_embedding(foto_b64)
            bio.ativo = True
            thumb = _thumbnail(foto_b64)
            if thumb:
                bio.foto_thumb_base64 = thumb
            bio.save(update_fields=["embedding_json", "foto_thumb_base64", "ativo", "atualizado_em"])
            reaprendido = True
        except (ValueError, ImportError):
            pass  # face ruim nesta captura — check-in por CPF segue normalmente

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
        senha = _gerar_senha_atendimento(empresa)
        checkin = TotemCheckinLog.objects.create(
            empresa=empresa,
            identidade=identidade,
            score_similaridade=score,
            tipo_entrada=tipo_entrada,
            senha_atendimento=senha,
        )

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
            "mensagem":        f"Olá, {primeiro_nome}! Check-in confirmado. Aguarde ser chamado(a).",
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
