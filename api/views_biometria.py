"""
Biometria Facial para confirmação de entrega de EPI — SolusCRT SST.
Implementado como "confirmação por foto" (captura + armazena), sem ML/face recognition.

Endpoints:
  POST /api/sst/biometria/cadastrar/                    — cadastra foto de referência
  GET  /api/sst/biometria/<funcionario_id>/             — status da biometria
  POST /api/sst/biometria/entregas/<entrega_id>/confirmar/ — confirma entrega com foto
  GET  /api/sst/biometria/kpis/                         — KPIs biometria
  GET  /sst/biometria/                                  — página biometria
"""
import hashlib
import json
from datetime import date

from django.http import JsonResponse
from django.utils import timezone

from .access_control import api_requer_feature, requer_permissao_modulo, requer_feature_pacote


# ── Helpers ──────────────────────────────────────────────────────────────────

def _empresa(request):
    empresa = getattr(request, "empresa", None)
    if empresa:
        return empresa
    try:
        from .views_dashboard import _empresa_autenticada
        return _empresa_autenticada(request)
    except Exception:
        return None


def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


def _sha256(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _biometria_dict(b):
    return {
        "id": b.id,
        "funcionario_id": b.funcionario_id,
        "funcionario_nome": b.funcionario.nome,
        "hash_foto": b.hash_foto,
        "cadastrado_em": str(b.cadastrado_em),
        "atualizado_em": str(b.atualizado_em),
        "ativo": b.ativo,
        # Não expõe foto_base64 no listing — somente nos endpoints específicos
    }


# ── Views ─────────────────────────────────────────────────────────────────────

@api_requer_feature("sst.biometria")
def api_biometria_cadastrar(request):
    """POST — cadastra ou atualiza foto de referência do funcionário."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        from .models import FuncionarioSST, BiometriaFuncionario

        data = _json(request)
        funcionario_id = data.get("funcionario_id")
        foto_base64 = data.get("foto_base64", "").strip()

        if not funcionario_id:
            return JsonResponse({"erro": "funcionario_id é obrigatório"}, status=400)
        if not foto_base64:
            return JsonResponse({"erro": "foto_base64 é obrigatório"}, status=400)

        # Validação básica de tamanho (~500KB em base64 ≈ 680.000 chars)
        if len(foto_base64) > 700_000:
            return JsonResponse({"erro": "Foto muito grande. Máximo 500KB."}, status=400)

        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)
        hash_foto = _sha256(foto_base64)

        bio, criado = BiometriaFuncionario.objects.update_or_create(
            funcionario=func,
            defaults={
                "foto_base64": foto_base64,
                "hash_foto": hash_foto,
                "ativo": True,
            }
        )

        return JsonResponse({
            "ok": True,
            "criado": criado,
            "data": _biometria_dict(bio),
        }, status=201 if criado else 200)

    except FuncionarioSST.DoesNotExist:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.biometria")
def api_biometria_detalhe(request, funcionario_id):
    """GET — retorna status da biometria do funcionário."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import FuncionarioSST, BiometriaFuncionario

        func = FuncionarioSST.objects.get(id=funcionario_id, empresa=empresa)

        try:
            bio = BiometriaFuncionario.objects.get(funcionario=func)
            return JsonResponse({
                "cadastrada": True,
                "ativo": bio.ativo,
                "hash_foto": bio.hash_foto,
                "cadastrado_em": str(bio.cadastrado_em),
                "atualizado_em": str(bio.atualizado_em),
                "funcionario_id": func.id,
                "funcionario_nome": func.nome,
            })
        except BiometriaFuncionario.DoesNotExist:
            return JsonResponse({
                "cadastrada": False,
                "funcionario_id": func.id,
                "funcionario_nome": func.nome,
            })

    except FuncionarioSST.DoesNotExist:
        return JsonResponse({"erro": "Funcionário não encontrado"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.biometria")
def api_biometria_confirmar_entrega(request, entrega_id):
    """POST — confirma entrega de EPI com biometria facial.
    Recebe {foto_base64} e salva foto_entrega + marca biometria_confirmada=True.
    """
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    try:
        from .models import EntregaEPI, BiometriaFuncionario

        data = _json(request)
        foto_base64 = data.get("foto_base64", "").strip()

        if not foto_base64:
            return JsonResponse({"erro": "foto_base64 é obrigatório"}, status=400)
        if len(foto_base64) > 700_000:
            return JsonResponse({"erro": "Foto muito grande. Máximo 500KB."}, status=400)

        entrega = EntregaEPI.objects.select_related("funcionario").get(
            id=entrega_id, empresa=empresa
        )

        if entrega.biometria_confirmada:
            return JsonResponse({"ok": True, "msg": "Entrega já confirmada anteriormente.", "ja_confirmada": True})

        # Verifica se o funcionário tem biometria cadastrada
        tem_biometria = BiometriaFuncionario.objects.filter(
            funcionario=entrega.funcionario, ativo=True
        ).exists()

        # Salva foto da entrega e confirma
        entrega.foto_entrega_base64 = foto_base64
        entrega.biometria_confirmada = True
        entrega.save(update_fields=["foto_entrega_base64", "biometria_confirmada"])

        return JsonResponse({
            "ok": True,
            "msg": "Entrega confirmada com biometria.",
            "entrega_id": entrega.id,
            "funcionario_nome": entrega.funcionario.nome,
            "epi_nome": entrega.epi.nome,
            "data_entrega": str(entrega.data_entrega),
            "biometria_referencia_cadastrada": tem_biometria,
        })

    except EntregaEPI.DoesNotExist:
        return JsonResponse({"erro": "Entrega não encontrada"}, status=404)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@api_requer_feature("sst.biometria")
def api_biometria_kpis(request):
    """GET — KPIs de biometria."""
    empresa = _empresa(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=403)

    try:
        from .models import FuncionarioSST, BiometriaFuncionario, EntregaEPI

        hoje = date.today()
        total_funcionarios = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()
        total_cadastrados = BiometriaFuncionario.objects.filter(
            funcionario__empresa=empresa, ativo=True
        ).count()
        total_sem_biometria = total_funcionarios - total_cadastrados

        entregas_com_bio_mes = EntregaEPI.objects.filter(
            empresa=empresa,
            biometria_confirmada=True,
            data_entrega__year=hoje.year,
            data_entrega__month=hoje.month,
        ).count()

        total_entregas_mes = EntregaEPI.objects.filter(
            empresa=empresa,
            data_entrega__year=hoje.year,
            data_entrega__month=hoje.month,
        ).count()

        cobertura_pct = round((total_cadastrados / total_funcionarios * 100), 1) if total_funcionarios > 0 else 0

        return JsonResponse({
            "total_funcionarios": total_funcionarios,
            "total_cadastrados": total_cadastrados,
            "total_sem_biometria": total_sem_biometria,
            "cobertura_pct": cobertura_pct,
            "entregas_com_biometria_mes": entregas_com_bio_mes,
            "total_entregas_mes": total_entregas_mes,
            "mes": hoje.month,
            "ano": hoje.year,
        })
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)


@requer_feature_pacote("sst.biometria", "Biometria EPI")
@requer_permissao_modulo("sst.gestao_conformidade")
def sst_biometria_page(request):
    """Página Biometria — renderiza template."""
    from django.shortcuts import render, redirect
    from .views_sst import _empresa_sst_autenticada

    empresa = _empresa_sst_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_biometria.html", {"empresa_nome": empresa.nome})
