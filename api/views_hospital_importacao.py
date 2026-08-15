"""
Importação/Migração de dados — segmento Hospital.

Fluxo: upload (CSV/XLSX) → detecta colunas → usuário mapeia coluna→campo →
prévia validada → processa (upsert em lote). Genérico via IMPORT_TARGETS.
"""
import csv
import io
import json
import logging

from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .access_control import (
    api_requer_feature, api_requer_permissao_modulo, get_setor,
    requer_feature_pacote, requer_operacao_page, requer_permissao_modulo,
    requer_setor,
)
from .services.importacao_hospital import (
    IMPORT_TARGETS, target_ou_none, validar_linha,
)

logger = logging.getLogger(__name__)

MAX_LINHAS = 20000        # teto de segurança por arquivo
AMOSTRA_N = 5


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _principal_nome(request, empresa):
    principal = getattr(request, "principal", None)
    return (getattr(principal, "nome", None) or getattr(principal, "email", None)
            or getattr(empresa, "nome", "") or "")


def _parse_planilha(arquivo):
    """Lê CSV ou XLSX. Retorna (colunas, linhas:list[dict], erro:str|None)."""
    nome = (arquivo.name or "").lower()
    conteudo = arquivo.read()
    if nome.endswith(".xlsx"):
        try:
            import openpyxl
        except ImportError:
            return None, None, ("Arquivos .xlsx não são suportados neste servidor. "
                                "Salve como CSV (UTF-8) e envie novamente.")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
            ws = wb.active
            linhas_iter = ws.iter_rows(values_only=True)
            cabecalho = next(linhas_iter, None)
            if not cabecalho:
                return None, None, "Planilha vazia."
            colunas = [str(c).strip() if c is not None else f"Coluna {i+1}"
                       for i, c in enumerate(cabecalho)]
            linhas = []
            for row in linhas_iter:
                if row is None or all(c is None or str(c).strip() == "" for c in row):
                    continue
                linhas.append({colunas[i]: (row[i] if i < len(row) else None)
                               for i in range(len(colunas))})
                if len(linhas) > MAX_LINHAS:
                    return None, None, f"Arquivo excede o limite de {MAX_LINHAS} linhas."
            return colunas, linhas, None
        except Exception as e:  # openpyxl lança vários tipos
            return None, None, f"Não foi possível ler o .xlsx: {e}"

    # CSV — detecta encoding e delimitador
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        return None, None, "Não foi possível decodificar o arquivo (use UTF-8)."
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=";,\t")
        delim = dialeto.delimiter
    except csv.Error:
        delim = ";" if texto[:4096].count(";") >= texto[:4096].count(",") else ","
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delim)
    colunas = [c.strip() for c in (leitor.fieldnames or []) if c is not None]
    if not colunas:
        return None, None, "Não foi possível identificar o cabeçalho do CSV."
    linhas = []
    for row in leitor:
        if all((v is None or str(v).strip() == "") for v in row.values()):
            continue
        linhas.append({k.strip(): v for k, v in row.items() if k is not None})
        if len(linhas) > MAX_LINHAS:
            return None, None, f"Arquivo excede o limite de {MAX_LINHAS} linhas."
    return colunas, linhas, None


def _sugerir_mapeamento(target, colunas):
    """Casa automaticamente campos↔colunas por similaridade de nome."""
    import unicodedata

    def norm(s):
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
        return "".join(ch for ch in s.lower() if ch.isalnum())

    cols_norm = {norm(c): c for c in colunas}
    mapa = {}
    for campo in target["campos"]:
        alvos = [campo["chave"], campo["rotulo"]]
        for a in alvos:
            n = norm(a)
            if n in cols_norm:
                mapa[campo["chave"]] = cols_norm[n]
                break
            # match parcial
            for cn, orig in cols_norm.items():
                if n and (n in cn or cn in n):
                    mapa[campo["chave"]] = orig
                    break
            if campo["chave"] in mapa:
                break
    return mapa


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.opme", "Importação")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_importacao_page(request):
    return render(request, "hospital_importacao.html")


@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_import_tipos(request):
    """GET — lista os alvos de importação e seus campos."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    return JsonResponse({
        "tipos": [
            {
                "chave": k,
                "label": t["label"],
                "descricao": t["descricao"],
                "icone": t["icone"],
                "campos": [
                    {"chave": c["chave"], "rotulo": c["rotulo"], "tipo": c["tipo"],
                     "obrigatorio": c["obrigatorio"], "ajuda": c.get("ajuda", "")}
                    for c in t["campos"]
                ],
            }
            for k, t in IMPORT_TARGETS.items()
        ],
    })


@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_import_modelo(request, destino):
    """GET — baixa um CSV modelo (só o cabeçalho) para o alvo."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    target = target_ou_none(destino)
    if not target:
        return JsonResponse({"erro": "Tipo de importação inválido"}, status=404)
    cabecalho = [c["rotulo"] for c in target["campos"]]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho)
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="modelo_{destino}.csv"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_import_upload(request):
    """POST multipart — recebe o arquivo, detecta colunas, sugere mapeamento."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    destino = request.POST.get("destino", "")
    target = target_ou_none(destino)
    if not target:
        return JsonResponse({"erro": "Tipo de importação inválido"}, status=400)
    arquivo = request.FILES.get("arquivo")
    if not arquivo:
        return JsonResponse({"erro": "Envie um arquivo CSV ou XLSX"}, status=400)
    if arquivo.size > 15 * 1024 * 1024:
        return JsonResponse({"erro": "Arquivo acima de 15 MB"}, status=400)

    colunas, linhas, erro = _parse_planilha(arquivo)
    if erro:
        return JsonResponse({"erro": erro}, status=400)
    if not linhas:
        return JsonResponse({"erro": "Nenhuma linha de dados encontrada"}, status=400)

    from .models import ImportacaoDados
    imp = ImportacaoDados.objects.create(
        empresa=empresa, destino=destino, arquivo_nome=arquivo.name[:255],
        colunas_arquivo=colunas, amostra=linhas[:AMOSTRA_N],
        linhas_brutas=linhas, total_linhas=len(linhas), status="mapeando",
        mapeamento=_sugerir_mapeamento(target, colunas),
        criado_por=_principal_nome(request, empresa),
    )
    return JsonResponse({
        "id": imp.id,
        "colunas": colunas,
        "amostra": imp.amostra,
        "total_linhas": imp.total_linhas,
        "mapeamento_sugerido": imp.mapeamento,
    }, status=201)


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_import_previa(request, imp_id):
    """POST {mapeamento} — valida as primeiras linhas e devolve a prévia."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    from .models import ImportacaoDados
    try:
        imp = ImportacaoDados.objects.get(id=imp_id, empresa=empresa)
    except ImportacaoDados.DoesNotExist:
        return JsonResponse({"erro": "Importação não encontrada"}, status=404)
    target = target_ou_none(imp.destino)
    if not target:
        return JsonResponse({"erro": "Tipo inválido"}, status=400)
    try:
        mapeamento = json.loads(request.body or b"{}").get("mapeamento", {})
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    imp.mapeamento = mapeamento
    imp.save(update_fields=["mapeamento"])

    obrig_sem_col = [c["rotulo"] for c in target["campos"]
                     if c["obrigatorio"] and not mapeamento.get(c["chave"])]

    previa, ok, erro = [], 0, 0
    for i, linha in enumerate(imp.linhas_brutas[:AMOSTRA_N * 2], start=1):
        dados, erros = validar_linha(target, linha, mapeamento)
        if erros:
            erro += 1
        else:
            ok += 1
        previa.append({"linha": i, "dados": {k: str(v) for k, v in dados.items()},
                       "erros": erros})
    return JsonResponse({
        "obrigatorios_sem_coluna": obrig_sem_col,
        "previa": previa,
        "previa_ok": ok,
        "previa_erro": erro,
        "total_linhas": imp.total_linhas,
    })


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_import_processar(request, imp_id):
    """POST — executa a importação (upsert em lote). Idempotente pela chave natural."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    from .models import ImportacaoDados
    try:
        imp = ImportacaoDados.objects.get(id=imp_id, empresa=empresa)
    except ImportacaoDados.DoesNotExist:
        return JsonResponse({"erro": "Importação não encontrada"}, status=404)
    if imp.status == "concluido":
        return JsonResponse({"erro": "Esta importação já foi processada"}, status=409)
    target = target_ou_none(imp.destino)
    if not target:
        return JsonResponse({"erro": "Tipo inválido"}, status=400)

    obrig_sem_col = [c["rotulo"] for c in target["campos"]
                     if c["obrigatorio"] and not imp.mapeamento.get(c["chave"])]
    if obrig_sem_col:
        return JsonResponse(
            {"erro": "Mapeie os campos obrigatórios: " + ", ".join(obrig_sem_col)}, status=400)

    ok, falhas, erros = 0, 0, []
    imp.status = "processando"
    imp.save(update_fields=["status"])
    for i, linha in enumerate(imp.linhas_brutas, start=1):
        dados, errs = validar_linha(target, linha, imp.mapeamento)
        if errs:
            falhas += 1
            if len(erros) < 200:
                erros.append({"linha": i, "mensagem": "; ".join(errs)})
            continue
        try:
            with transaction.atomic():
                target["salvar"](empresa, dados)
            ok += 1
        except Exception as e:
            falhas += 1
            if len(erros) < 200:
                erros.append({"linha": i, "mensagem": str(e)})

    imp.linhas_ok = ok
    imp.linhas_erro = falhas
    imp.erros = erros
    imp.status = "concluido" if ok > 0 else "erro"
    imp.processado_em = timezone.now()
    imp.linhas_brutas = []  # libera espaço — o arquivo já foi aplicado
    imp.save()
    return JsonResponse({
        "status": imp.status, "linhas_ok": ok, "linhas_erro": falhas,
        "erros": erros[:50], "destino": imp.destino,
    })


@require_http_methods(["GET"])
@api_requer_feature("hospital.opme")
@api_requer_permissao_modulo("hospital.clinico")
def api_import_historico(request):
    """GET — histórico de importações da empresa."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    from .models import ImportacaoDados
    qs = ImportacaoDados.objects.filter(empresa=empresa).order_by("-criado_em")[:50]
    return JsonResponse({
        "importacoes": [
            {
                "id": h.id, "destino": h.destino,
                "destino_label": (target_ou_none(h.destino) or {}).get("label", h.destino),
                "arquivo_nome": h.arquivo_nome, "status": h.status,
                "status_display": h.get_status_display(),
                "total_linhas": h.total_linhas, "linhas_ok": h.linhas_ok,
                "linhas_erro": h.linhas_erro, "criado_por": h.criado_por,
                "criado_em": h.criado_em.isoformat(),
                "erros": h.erros[:50],
            }
            for h in qs
        ],
    })
