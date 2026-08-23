"""
views_plano_portal_facial.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Portal do Beneficiário com login por rosto (VITA OS — Plano de Saúde)

Uma ÚNICA URL pública por operadora (token) serve:
  • ao TOTEM na operadora (kiosk) e
  • ao QR CODE que o beneficiário lê no celular.

O beneficiário olha para a câmera → reconhecido entre os beneficiários DAQUELA
operadora → vê seus dados (carteirinha, plano, situação). Primeiro acesso:
informa a carteirinha/CPF e cadastra o rosto.

Isolamento: o token identifica a operadora; a busca facial é escopada aos
beneficiários dela (RLS setado pelo token). Não cruza segmento.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import secrets

import numpy as np
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .middleware import _rls_set_empresa
from .models import BeneficiarioPlano, PortalFacialOperadora
from .views_hospital_totem import _extrair_embedding, _thumbnail, LIMIAR_FACE_MATCH
from .views_plano_saude import _ps_auth


def _operadora_por_token(token):
    cfg = (PortalFacialOperadora.objects
           .filter(token=token, ativo=True)
           .select_related("empresa").first())
    if not cfg or not cfg.empresa or not cfg.empresa.ativo:
        return None
    _rls_set_empresa(cfg.empresa_id)   # escopa as queries à operadora
    return cfg.empresa


def _buscar_beneficiario_por_rosto(embedding, empresa):
    """Busca 1:N entre os beneficiários ativos da operadora com rosto cadastrado."""
    qs = (BeneficiarioPlano.objects
          .filter(plano__empresa=empresa, situacao="ativo", face_embedding__isnull=False)
          .select_related("plano"))
    emb = np.array(embedding, dtype=np.float32)
    melhor, melhor_score = None, 0.0
    for b in qs:
        try:
            score = float(np.dot(emb, np.array(b.face_embedding, dtype=np.float32)))
        except Exception:
            continue
        if score > melhor_score:
            melhor_score, melhor = score, b
    if melhor_score >= LIMIAR_FACE_MATCH and melhor:
        return melhor, melhor_score
    return None, melhor_score


def _dados_beneficiario(b):
    return {
        "nome":         b.nome,
        "carteirinha":  b.numero_carteirinha,
        "plano":        b.plano.nome if b.plano_id else "",
        "situacao":     b.get_situacao_display(),
        "vinculo":      b.get_tipo_vinculo_display(),
        "acomodacao":   b.acomodacao,
        "vigencia_fim": b.data_fim_vigencia.strftime("%d/%m/%Y") if b.data_fim_vigencia else "",
        "foto":         b.face_thumb_base64 or "",
        "dependentes":  b.dependentes.count() if b.tipo_vinculo == "titular" else 0,
    }


# ─── Páginas públicas (totem + QR) ────────────────────────────────────────────

def portal_facial_page(request, token):
    empresa = _operadora_por_token(token)
    if not empresa:
        return render(request, "plano_portal_facial.html", {"invalido": True})
    return render(request, "plano_portal_facial.html", {
        "token": token,
        "empresa_nome": empresa.nome,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_portal_facial_login(request, token):
    empresa = _operadora_por_token(token)
    if not empresa:
        return JsonResponse({"erro": "Acesso inválido."}, status=404)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)
    foto = data.get("foto_base64", "")
    if not foto:
        return JsonResponse({"erro": "Foto obrigatória."}, status=400)
    try:
        embedding = _extrair_embedding(foto)
    except (ValueError, ImportError) as exc:
        return JsonResponse({"reconhecido": False, "erro": str(exc)}, status=422)

    benef, score = _buscar_beneficiario_por_rosto(embedding, empresa)
    if not benef:
        return JsonResponse({
            "reconhecido": False,
            "score_max": round(score, 4),
            "mensagem": "Rosto não encontrado. Faça o primeiro acesso com sua carteirinha.",
        })
    return JsonResponse({
        "reconhecido": True,
        "score": round(score, 4),
        "beneficiario": _dados_beneficiario(benef),
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_portal_facial_enrolar(request, token):
    """Primeiro acesso: identifica pelo nº da carteirinha ou CPF e cadastra o rosto."""
    empresa = _operadora_por_token(token)
    if not empresa:
        return JsonResponse({"erro": "Acesso inválido."}, status=404)
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"erro": "JSON inválido."}, status=400)

    carteirinha = (data.get("carteirinha") or "").strip()
    cpf = "".join(c for c in (data.get("cpf") or "") if c.isdigit())
    foto = data.get("foto_base64", "")
    if not (carteirinha or cpf):
        return JsonResponse({"erro": "Informe a carteirinha ou o CPF."}, status=400)
    if not foto:
        return JsonResponse({"erro": "Foto obrigatória."}, status=400)

    qs = BeneficiarioPlano.objects.filter(plano__empresa=empresa, situacao="ativo")
    benef = None
    if carteirinha:
        benef = qs.filter(numero_carteirinha=carteirinha).first()
    if not benef and cpf:
        benef = qs.filter(cpf=cpf).first() or qs.filter(cpf=data.get("cpf", "")).first()
    if not benef:
        return JsonResponse({"erro": "Beneficiário não encontrado ou inativo."}, status=404)

    try:
        embedding = _extrair_embedding(foto)
    except (ValueError, ImportError) as exc:
        return JsonResponse({"erro": str(exc)}, status=422)

    benef.face_embedding = embedding
    benef.face_thumb_base64 = _thumbnail(foto)
    benef.save(update_fields=["face_embedding", "face_thumb_base64"])
    return JsonResponse({
        "ok": True,
        "beneficiario": _dados_beneficiario(benef),
        "mensagem": "Rosto cadastrado! Da próxima vez, é só olhar para a câmera.",
    }, status=201)


# ─── Config (operadora logada) — gera o token + URL/QR ────────────────────────

@require_http_methods(["GET"])
def api_portal_facial_config(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    cfg, _ = PortalFacialOperadora.objects.get_or_create(
        empresa=empresa, defaults={"token": secrets.token_urlsafe(24)}
    )
    url = f"/plano-saude/acesso/{cfg.token}/"
    total = BeneficiarioPlano.objects.filter(plano__empresa=empresa, situacao="ativo").count()
    com_rosto = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa, situacao="ativo", face_embedding__isnull=False
    ).count()
    return JsonResponse({
        "ativo": cfg.ativo,
        "url": url,
        "beneficiarios_ativos": total,
        "com_rosto_cadastrado": com_rosto,
    })


def portal_facial_admin_page(request):
    """Página de config (operadora): mostra a URL de acesso, o QR e estatísticas."""
    empresa, err = _ps_auth(request)
    if err:
        return render(request, "plano_portal_facial_admin.html", {"sem_acesso": True})
    return render(request, "plano_portal_facial_admin.html", {
        "empresa_nome": empresa.nome, "empresa_id": empresa.id,
    })


# ─── Enrolamento em massa (operadora sobe fotos nomeadas por carteirinha/CPF) ──

@csrf_exempt
@require_http_methods(["POST"])
def api_portal_facial_enrolar_massa(request):
    """
    POST multipart, campo 'fotos' = várias imagens. O NOME de cada arquivo
    identifica o beneficiário (nº da carteirinha ou CPF, ex.: 'REDE-77.jpg').
    Cadastra o rosto de cada um. Retorna relatório por arquivo.
    """
    import base64 as _b64
    empresa, err = _ps_auth(request)
    if err:
        return err

    arquivos = request.FILES.getlist("fotos")
    if not arquivos:
        return JsonResponse({"erro": "Nenhuma foto enviada (campo 'fotos')."}, status=400)
    if len(arquivos) > 100:
        return JsonResponse({"erro": "Máximo de 100 fotos por lote."}, status=400)

    qs = BeneficiarioPlano.objects.filter(plano__empresa=empresa, situacao="ativo")
    resultados, ok, falhas = [], 0, 0
    for f in arquivos:
        nome_arq = f.name
        chave = nome_arq.rsplit(".", 1)[0].strip()        # tira a extensão
        so_digitos = "".join(c for c in chave if c.isdigit())
        benef = qs.filter(numero_carteirinha=chave).first()
        if not benef and so_digitos:
            benef = qs.filter(cpf=so_digitos).first() or qs.filter(numero_carteirinha=so_digitos).first()
        if not benef:
            falhas += 1
            resultados.append({"arquivo": nome_arq, "status": "erro", "motivo": "beneficiário não encontrado"})
            continue
        try:
            data_uri = "data:image/jpeg;base64," + _b64.b64encode(f.read()).decode("ascii")
            embedding = _extrair_embedding(data_uri)
        except (ValueError, ImportError):
            falhas += 1
            resultados.append({"arquivo": nome_arq, "status": "erro", "motivo": "nenhum rosto detectado"})
            continue
        benef.face_embedding = embedding
        benef.face_thumb_base64 = _thumbnail(data_uri)
        benef.save(update_fields=["face_embedding", "face_thumb_base64"])
        ok += 1
        resultados.append({"arquivo": nome_arq, "status": "ok", "beneficiario": benef.nome})

    return JsonResponse({"ok": True, "cadastrados": ok, "falhas": falhas, "resultados": resultados})
