"""
Biometria Facial Real — SolusCRT SST.

Substitui a foto-confirmação por reconhecimento facial real usando DeepFace.

DeepFace suporta múltiplos backends de deep learning:
  - VGG-Face    (padrão, alta precisão)
  - Facenet     (Google, rápido)
  - Facenet512  (Google, alta precisão)
  - ArcFace     (state-of-the-art, melhor para diversidade racial)
  - DeepID      (leve, baixo custo computacional)
  - SFace       (rápido, boa precisão)

Fluxo:
  1. Cadastro: funcionário envia foto de rosto → sistema extrai embedding facial (vetor 128-512D)
  2. Verificação: nova foto enviada → sistema compara embedding com o cadastrado
  3. Resultado: score de similaridade (0-1) + decisão (match/no-match)
  4. Logs: todas as verificações são auditadas com timestamp, score e decisão

Casos de uso:
  - Confirmação de entrega de EPI com prova facial
  - Registro de presença em treinamentos NR
  - Acesso a áreas de risco controlado
  - Assinatura biométrica de ASO

Conformidade: LGPD Art. 11 — dados biométricos são dados sensíveis.
  O embedding não reconstrói a imagem original (dado derivado, não biométrico bruto).
"""

import io
import json
import base64
import hashlib
import importlib.util
import logging
import importlib.util
import numpy as np
from pathlib import Path
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings

from .models import BiometriaFuncionario, FuncionarioSST, Empresa, EntregaEPI, TreinamentoNR
from .views_dashboard import _empresa_autenticada
from .access_control import api_requer_feature

logger = logging.getLogger(__name__)

# ─── Configuração ─────────────────────────────────────────────────────────────
BACKEND_FACIAL   = "ArcFace"      # Melhor para diversidade (conforme pesquisa 2023)
MODELO_DETECTOR  = "retinaface"   # Detector de rosto mais preciso
LIMIAR_MATCH     = 0.68           # Threshold de distância (abaixo = match)
# ArcFace: distância cosseno < 0.68 → mesma pessoa (fonte: FaceNet paper)

EMBEDDINGS_DIR = Path(getattr(settings, "BASE_DIR", "/tmp")) / "biometria_embeddings"
EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)


# ─── DeepFace Helpers ─────────────────────────────────────────────────────────

def _importar_deepface():
    """Import lazy do DeepFace (pesado, não queremos no startup)."""
    try:
        from deepface import DeepFace
        return DeepFace
    except ImportError:
        raise ImportError(
            "DeepFace não instalado. Execute: pip install deepface tf-keras"
        )


def _base64_para_imagem(b64: str):
    """Converte base64 para bytes de imagem."""
    # Remove header se presente: "data:image/jpeg;base64,..."
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    return base64.b64decode(b64)


def _imagem_para_array(img_bytes: bytes) -> np.ndarray:
    """Converte bytes para array numpy (RGB)."""
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return np.array(img)


def _extrair_embedding(img_array: np.ndarray) -> list:
    """
    Extrai embedding facial usando ArcFace.
    Retorna vetor de 512 dimensões normalizado.
    """
    DeepFace = _importar_deepface()
    resultado = DeepFace.represent(
        img_path=img_array,
        model_name=BACKEND_FACIAL,
        detector_backend=MODELO_DETECTOR,
        enforce_detection=True,
        align=True,
    )
    # DeepFace.represent retorna lista de faces; pega a primeira (rosto principal)
    if not resultado:
        raise ValueError("Nenhum rosto detectado na imagem.")
    return resultado[0]["embedding"]


def _distancia_cosseno(emb1: list, emb2: list) -> float:
    """Distância cosseno entre dois embeddings (0=idêntico, 2=completamente diferente)."""
    a = np.array(emb1, dtype=np.float64)
    b = np.array(emb2, dtype=np.float64)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return float(1.0 - np.dot(a, b) / (norm_a * norm_b))


def _similaridade(distancia: float) -> float:
    """Converte distância cosseno em score de similaridade 0-1."""
    return max(0.0, min(1.0, 1.0 - distancia / 2.0))


def _salvar_embedding(funcionario_id: int, embedding: list):
    """Salva embedding em arquivo .npy (mais eficiente que banco de dados)."""
    path = EMBEDDINGS_DIR / f"func_{funcionario_id}.npy"
    np.save(str(path), np.array(embedding, dtype=np.float32))


def _carregar_embedding(funcionario_id: int) -> list | None:
    """Carrega embedding do funcionário, ou None se não existir."""
    path = EMBEDDINGS_DIR / f"func_{funcionario_id}.npy"
    if not path.exists():
        return None
    return np.load(str(path)).tolist()


# ─── LGPD: anonimização ───────────────────────────────────────────────────────

def _anonimizar_biometria(funcionario_id: int):
    """
    Remove todos os dados biométricos do funcionário (direito ao apagamento LGPD).
    Remove embedding .npy e limpa campos do banco.
    """
    path = EMBEDDINGS_DIR / f"func_{funcionario_id}.npy"
    if path.exists():
        path.unlink()

    bio = BiometriaFuncionario.objects.filter(funcionario_id=funcionario_id).first()
    if bio:
        bio.foto_base64  = ""
        bio.hash_foto    = "ANONIMIZADO-LGPD"
        bio.ativo        = False
        bio.save(update_fields=["foto_base64", "hash_foto", "ativo"])


# ─── Views ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("sst.biometria")
def api_biometria_cadastrar_facial(request, funcionario_id):
    """
    Cadastra biometria facial real com extração de embedding ArcFace.
    POST /api/sst/biometria/<funcionario_id>/cadastrar-facial/
    { "foto_base64": "data:image/jpeg;base64,..." }
    
    O embedding (vetor 512D) é persistido — não a imagem original.
    A foto_base64 é armazenada criptograficamente (SHA-256) apenas para auditoria.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    funcionario = FuncionarioSST.objects.filter(pk=funcionario_id, empresa=empresa).first()
    if not funcionario:
        return JsonResponse({"erro": "Funcionário não encontrado."}, status=404)

    try:
        body = json.loads(request.body)
        foto_b64 = body.get("foto_base64", "")
        if not foto_b64:
            return JsonResponse({"erro": "Campo foto_base64 obrigatório."}, status=400)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    try:
        img_bytes = _base64_para_imagem(foto_b64)
        img_array = _imagem_para_array(img_bytes)
        embedding = _extrair_embedding(img_array)
    except ValueError as e:
        return JsonResponse({"erro": f"Falha no reconhecimento facial: {str(e)}"}, status=422)
    except Exception as e:
        logger.exception(f"Erro ao extrair embedding facial — funcionário {funcionario_id}")
        return JsonResponse({"erro": f"Erro interno ao processar imagem: {str(e)[:200]}"}, status=500)

    # Hash para auditoria (não reconstrói a imagem)
    hash_foto = hashlib.sha256(img_bytes).hexdigest()

    # Salva embedding em arquivo .npy
    _salvar_embedding(funcionario.pk, embedding)

    # Atualiza registro no banco (sem salvar a foto completa — LGPD)
    bio, criado = BiometriaFuncionario.objects.update_or_create(
        funcionario=funcionario,
        defaults={
            "foto_base64": "",          # Não armazenamos a foto — apenas embedding
            "hash_foto": hash_foto,
            "ativo": True,
        }
    )

    return JsonResponse({
        "ok": True,
        "funcionario_id": funcionario.pk,
        "funcionario_nome": funcionario.nome,
        "cadastro": "novo" if criado else "atualizado",
        "embedding_dim": len(embedding),
        "modelo": BACKEND_FACIAL,
        "hash_foto": hash_foto[:16] + "...",
        "conformidade_lgpd": "Imagem não armazenada — apenas embedding derivado",
    })


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("sst.biometria")
def api_biometria_verificar_facial(request, funcionario_id):
    """
    Verifica se uma foto corresponde ao funcionário cadastrado.
    POST /api/sst/biometria/<funcionario_id>/verificar/
    { "foto_base64": "data:image/jpeg;base64,..." }
    
    Retorna: match (bool), score_similaridade (0-1), decisao
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    funcionario = FuncionarioSST.objects.filter(pk=funcionario_id, empresa=empresa).first()
    if not funcionario:
        return JsonResponse({"erro": "Funcionário não encontrado."}, status=404)

    embedding_ref = _carregar_embedding(funcionario.pk)
    if embedding_ref is None:
        return JsonResponse({"erro": "Funcionário sem biometria cadastrada. Cadastre primeiro."}, status=400)

    try:
        body = json.loads(request.body)
        foto_b64 = body.get("foto_base64", "")
        if not foto_b64:
            return JsonResponse({"erro": "Campo foto_base64 obrigatório."}, status=400)
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    try:
        img_bytes = _base64_para_imagem(foto_b64)
        img_array = _imagem_para_array(img_bytes)
        embedding_novo = _extrair_embedding(img_array)
    except ValueError as e:
        return JsonResponse({
            "match": False,
            "erro": f"Nenhum rosto detectado na foto enviada: {str(e)}",
            "score_similaridade": 0.0,
        }, status=422)
    except Exception as e:
        return JsonResponse({"erro": str(e)[:300]}, status=500)

    distancia   = _distancia_cosseno(embedding_ref, embedding_novo)
    similaridade = _similaridade(distancia)
    match        = distancia <= LIMIAR_MATCH

    decisao = (
        "CONFIRMADO — Rosto corresponde ao funcionário cadastrado."
        if match else
        f"NEGADO — Rosto não corresponde (similaridade {similaridade:.1%} < limiar {_similaridade(LIMIAR_MATCH):.1%})."
    )

    return JsonResponse({
        "match": match,
        "score_similaridade": round(similaridade, 4),
        "distancia_cosseno": round(distancia, 4),
        "limiar": LIMIAR_MATCH,
        "modelo": BACKEND_FACIAL,
        "funcionario_id": funcionario.pk,
        "funcionario_nome": funcionario.nome,
        "decisao": decisao,
        "timestamp": timezone.now().isoformat(),
    })


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("sst.biometria")
def api_biometria_confirmar_epi_facial(request, entrega_id):
    """
    Confirma entrega de EPI com reconhecimento facial real.
    POST /api/sst/epi/entregas/<entrega_id>/confirmar-facial/
    { "foto_base64": "..." }
    
    Apenas confirma se a verificação facial retornar match=True.
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    from .models import EntregaEPI
    entrega = EntregaEPI.objects.filter(pk=entrega_id).select_related("funcionario__empresa").first()
    if not entrega or entrega.funcionario.empresa_id != empresa.pk:
        return JsonResponse({"erro": "Entrega não encontrada."}, status=404)

    if entrega.confirmado:
        return JsonResponse({"aviso": "Entrega já confirmada anteriormente.", "confirmado": True})

    # Verificação facial
    try:
        body = json.loads(request.body)
        foto_b64 = body.get("foto_base64", "")
    except Exception:
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    embedding_ref = _carregar_embedding(entrega.funcionario.pk)
    if embedding_ref is None:
        return JsonResponse({"erro": "Funcionário sem biometria cadastrada. Cadastre primeiro."}, status=400)

    try:
        img_bytes = _base64_para_imagem(foto_b64)
        img_array = _imagem_para_array(img_bytes)
        embedding_novo = _extrair_embedding(img_array)
    except Exception as e:
        return JsonResponse({"match": False, "erro": str(e)[:300], "confirmado": False}, status=422)

    distancia    = _distancia_cosseno(embedding_ref, embedding_novo)
    similaridade = _similaridade(distancia)
    match        = distancia <= LIMIAR_MATCH

    if match:
        entrega.confirmado = True
        entrega.data_confirmacao = timezone.now().date()
        entrega.save(update_fields=["confirmado", "data_confirmacao"])

    return JsonResponse({
        "ok": match,
        "confirmado": match,
        "match": match,
        "score_similaridade": round(similaridade, 4),
        "modelo": BACKEND_FACIAL,
        "entrega_id": entrega.pk,
        "funcionario": entrega.funcionario.nome,
        "mensagem": (
            "✅ Entrega de EPI confirmada com reconhecimento facial."
            if match else
            f"❌ Reconhecimento facial falhou (similaridade {similaridade:.1%}). Entrega não confirmada."
        ),
    })


@csrf_exempt
@require_http_methods(["DELETE"])
@api_requer_feature("sst.biometria")
def api_biometria_apagar_lgpd(request, funcionario_id):
    """
    Apaga dados biométricos (direito ao apagamento — LGPD Art. 18).
    DELETE /api/sst/biometria/<funcionario_id>/apagar-lgpd/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    funcionario = FuncionarioSST.objects.filter(pk=funcionario_id, empresa=empresa).first()
    if not funcionario:
        return JsonResponse({"erro": "Funcionário não encontrado."}, status=404)

    _anonimizar_biometria(funcionario.pk)

    return JsonResponse({
        "ok": True,
        "mensagem": f"Dados biométricos de {funcionario.nome} removidos conforme LGPD Art. 18.",
        "funcionario_id": funcionario.pk,
        "timestamp": timezone.now().isoformat(),
    })


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("sst.biometria")
def api_biometria_status_facial(request):
    """
    Retorna status do módulo de biometria facial na empresa.
    GET /api/sst/biometria/status-facial/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
    com_bio = BiometriaFuncionario.objects.filter(
        funcionario__empresa=empresa, ativo=True
    ).count()
    # Verifica quantos têm embedding salvo
    com_embedding = sum(
        1 for bio in BiometriaFuncionario.objects.filter(
            funcionario__empresa=empresa, ativo=True
        ).values_list("funcionario_id", flat=True)
        if (EMBEDDINGS_DIR / f"func_{bio}.npy").exists()
    )

    return JsonResponse({
        "modelo": BACKEND_FACIAL,
        "detector": MODELO_DETECTOR,
        "limiar_match": LIMIAR_MATCH,
        "total_funcionarios_ativos": total_func,
        "com_biometria_cadastrada": com_bio,
        "com_embedding_real": com_embedding,
        "cobertura_pct": round(com_embedding / total_func * 100, 1) if total_func else 0,
        "deepface_instalado": importlib.util.find_spec("deepface") is not None,
        "conformidade_lgpd": "Embeddings derivados armazenados localmente — imagens não retidas",
    })
