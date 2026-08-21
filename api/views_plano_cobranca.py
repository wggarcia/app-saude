"""
views_plano_cobranca.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COBRANÇA DE MENSALIDADE — boleto (CNAB 240) + PIX + conciliação.

Gera a fatura mensal do beneficiário (mensalidade do núcleo familiar +
coparticipação consolidada), emite a cobrança e concilia o retorno:
  • PIX — BR Code EMV completo com CRC16 (copia-e-cola pronto pra pagar);
  • Boleto — linha digitável e código de barras Febraban com DVs corretos
    (mod10/mod11) e fator de vencimento;
  • Remessa CNAB 240 e conciliação do arquivo de retorno (baixa automática).

PIX é usável em produção com qualquer chave. O boleto traz a estrutura
Febraban válida; o campo livre do banco entra na homologação bancária.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    contexto_navegacao_setorial, requer_operacao_page, requer_permissao_modulo,
    requer_setor,
)
from .models import (
    BeneficiarioPlano, FaturamentoBeneficiario, PlanoSaude, RemessaCNAB,
)
from .views_dashboard import _empresa_autenticada
from .views_plano_saude import _ps_auth

CENT = Decimal("0.01")
_FATOR_BASE = date(1997, 10, 7)  # base Febraban do fator de vencimento


def _dec(v):
    try:
        return Decimal(str(v).replace(",", ".")).quantize(CENT)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _f(v):
    return float(v or 0)


def _comp_valida(c):
    try:
        a, m = c.split("-")
        return len(a) == 4 and 1 <= int(m) <= 12
    except (ValueError, AttributeError):
        return False


# ══════════ PIX — BR Code EMV + CRC16 ══════════
def _crc16(payload: str) -> str:
    crc = 0xFFFF
    for b in payload.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _tlv(idv: str, value: str) -> str:
    return f"{idv}{len(value):02d}{value}"


def _sanit(txt: str, n: int) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode()
    return t.upper()[:n].strip()


def gerar_pix_copia_cola(chave: str, nome: str, cidade: str, valor: Decimal, txid: str) -> str:
    nome = _sanit(nome, 25) or "RECEBEDOR"
    cidade = _sanit(cidade, 15) or "SAO PAULO"
    txid = (txid or "***")[:25]
    mai = _tlv("00", "br.gov.bcb.pix") + _tlv("01", chave)
    payload = (
        _tlv("00", "01") +
        _tlv("26", mai) +
        _tlv("52", "0000") +
        _tlv("53", "986") +
        (_tlv("54", f"{valor:.2f}") if valor and valor > 0 else "") +
        _tlv("58", "BR") +
        _tlv("59", nome) +
        _tlv("60", cidade) +
        _tlv("62", _tlv("05", txid))
    )
    payload += "6304"
    return payload + _crc16(payload)


# ══════════ Boleto Febraban — código de barras + linha digitável ══════════
def _mod10(num: str) -> int:
    soma, peso = 0, 2
    for d in reversed(num):
        p = int(d) * peso
        soma += p if p < 10 else p - 9
        peso = 1 if peso == 2 else 2
    resto = soma % 10
    return (10 - resto) % 10


def _mod11_barcode(num: str) -> int:
    soma, peso = 0, 2
    for d in reversed(num):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - (soma % 11)
    return 1 if dv in (0, 10, 11) else dv


def _fator_vencimento(venc: date) -> str:
    dias = (venc - _FATOR_BASE).days
    if dias > 9999:  # rollover Febraban (2025)
        dias -= 9000
    return f"{dias:04d}"[-4:]


def gerar_boleto(codigo_banco: str, venc: date, valor: Decimal, campo_livre25: str):
    banco = (codigo_banco or "000").zfill(3)[:3]
    moeda = "9"
    fator = _fator_vencimento(venc)
    valor_cent = f"{int((valor * 100).to_integral_value()):010d}"[-10:]
    campo_livre = (campo_livre25 or "").zfill(25)[:25]
    sem_dv = banco + moeda + fator + valor_cent + campo_livre  # 43 dígitos
    dv = _mod11_barcode(sem_dv)
    barcode = banco + moeda + str(dv) + fator + valor_cent + campo_livre  # 44
    # linha digitável
    c1 = barcode[0:4] + barcode[19:24]
    c2 = barcode[24:34]
    c3 = barcode[34:44]
    campo1 = c1 + str(_mod10(c1))
    campo2 = c2 + str(_mod10(c2))
    campo3 = c3 + str(_mod10(c3))
    campo4 = barcode[4]  # DV geral
    campo5 = barcode[5:19]  # fator + valor
    linha = (f"{campo1[:5]}.{campo1[5:]} {campo2[:5]}.{campo2[5:]} "
             f"{campo3[:5]}.{campo3[5:]} {campo4} {campo5}")
    return barcode, linha


# ══════════ Faturas da competência ══════════
def gerar_faturas_competencia(empresa, competencia, dia_vencimento=10):
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    try:
        venc = date(ano, mes, min(dia_vencimento, 28))
    except ValueError:
        venc = date(ano, mes, 10)
    titulares = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa, situacao=BeneficiarioPlano.SITUACAO_ATIVO,
        tipo_vinculo=BeneficiarioPlano.VINCULO_TITULAR,
    ).select_related("plano")
    geradas = []
    for tit in titulares:
        mensalidade = _dec(tit.valor_mensalidade)
        deps = tit.dependentes.filter(situacao=BeneficiarioPlano.SITUACAO_ATIVO)
        mensalidade += sum((_dec(d.valor_mensalidade) for d in deps), Decimal("0"))
        fatura, _c = FaturamentoBeneficiario.objects.get_or_create(
            empresa=empresa, beneficiario=tit, competencia=competencia,
            defaults={"plano": tit.plano},
        )
        # preserva coparticipação já consolidada (módulo #4)
        copart = _dec(fatura.valor_coparticipacao)
        fatura.valor_mensalidade = mensalidade
        fatura.valor_total = mensalidade + copart
        fatura.vencimento = venc
        if fatura.status == FaturamentoBeneficiario.STATUS_CANCELADO:
            fatura.status = FaturamentoBeneficiario.STATUS_PENDENTE
        fatura.save()
        geradas.append(fatura)
    return geradas


def emitir_cobranca(fatura, forma, *, chave_pix="", nome_recebedor="", cidade="",
                    codigo_banco="000", agencia="0000", conta="00000000"):
    """Popula os campos de cobrança da fatura (PIX e/ou boleto)."""
    venc = fatura.vencimento or timezone.now().date()
    valor = _dec(fatura.valor_total)
    nosso = f"{fatura.id:011d}"
    fatura.nosso_numero = nosso
    if forma in ("pix", "ambos"):
        txid = f"MENS{fatura.competencia.replace('-', '')}{fatura.id}"
        fatura.pix_txid = txid[:25]
        fatura.pix_copia_cola = gerar_pix_copia_cola(
            chave_pix or "chave-nao-configurada", nome_recebedor or "OPERADORA",
            cidade or "SAO PAULO", valor, txid)
    if forma in ("boleto", "ambos"):
        campo_livre = (agencia.zfill(4) + conta.zfill(8) + nosso[-11:] + "00")[:25]
        barcode, linha = gerar_boleto(codigo_banco, venc, valor, campo_livre)
        fatura.codigo_barras = barcode
        fatura.linha_digitavel = linha
    fatura.forma_cobranca = forma
    fatura.save(update_fields=["nosso_numero", "pix_txid", "pix_copia_cola",
                               "codigo_barras", "linha_digitavel", "forma_cobranca"])
    return fatura


# ══════════ CNAB 240 — remessa + conciliação ══════════
def _linha240(*campos):
    return ("".join(campos))[:240].ljust(240)


def gerar_remessa_cnab240(empresa, faturas, banco="000"):
    banco = (banco or "000").zfill(3)
    linhas = []
    linhas.append(_linha240(banco, "0000", "0", " " * 8, "REMESSA MENSALIDADE",
                            _sanit(empresa.nome, 30)))            # header arquivo
    linhas.append(_linha240(banco, "0001", "1", "R", "01", "MENSALIDADE"))  # header lote
    total = Decimal("0")
    for i, f in enumerate(faturas, 1):
        seq = f"{i:05d}"
        nn = (f.nosso_numero or f"{f.id:011d}")[:20]
        val = f"{int((_dec(f.valor_total) * 100).to_integral_value()):015d}"
        venc = f.vencimento.strftime("%d%m%Y") if f.vencimento else "00000000"
        # Segmento P (título)
        linhas.append(_linha240(banco, "0001", "3", seq, "P", " ", nn.ljust(20),
                                venc, val, "0000000"))
        # Segmento Q (sacado)
        nome = _sanit(f.beneficiario.nome, 40).ljust(40)
        linhas.append(_linha240(banco, "0001", "3", seq, "Q", " ", nome))
        total += _dec(f.valor_total)
    linhas.append(_linha240(banco, "0001", "5", f"{len(faturas):06d}"))  # trailer lote
    linhas.append(_linha240(banco, "9999", "9", f"{len(faturas)+4:06d}"))  # trailer arquivo
    return "\r\n".join(linhas), total


def gerar_retorno_cnab240(empresa, faturas, banco="000", ocorrencia="06"):
    """Gera um arquivo de RETORNO CNAB 240 (segmento T) — ocorrência '06'=Liquidação.
    Usado para homologação/sandbox e simétrico ao parser de conciliação."""
    banco = (banco or "000").zfill(3)
    linhas = [_linha240(banco, "0000", "0", " " * 8, "RETORNO MENSALIDADE")]
    for i, f in enumerate(faturas, 1):
        nn = (f.nosso_numero or f"{f.id:011d}")[:20].ljust(20)
        linhas.append(_linha240(banco, "0001", "3", f"{i:05d}", "T", " ", nn,
                                ocorrencia, "LIQUIDADO"))
    linhas.append(_linha240(banco, "9999", "9", f"{len(faturas)+2:06d}"))
    return "\r\n".join(linhas)


def conciliar_retorno_cnab(empresa, texto, competencia=""):
    """Lê retorno CNAB 240 (segmento T); dá baixa nas faturas pelo nosso_número
    quando a ocorrência é '06' (liquidação/pagamento)."""
    pagos = 0
    faturas_idx = {}
    qs = FaturamentoBeneficiario.objects.filter(empresa=empresa)
    if competencia:
        qs = qs.filter(competencia=competencia)
    for f in qs:
        if f.nosso_numero:
            faturas_idx[f.nosso_numero.strip()] = f
    for linha in texto.replace("\r", "").split("\n"):
        if len(linha) < 40 or linha[7:8] != "3" or linha[13:14] != "T":
            continue
        nn = linha[15:35].strip()
        ocorrencia = linha[35:37]
        f = faturas_idx.get(nn)
        if f and ocorrencia == "06" and f.status != FaturamentoBeneficiario.STATUS_PAGO:
            f.status = FaturamentoBeneficiario.STATUS_PAGO
            f.pago_em = timezone.now().date()
            f.save(update_fields=["status", "pago_em", "atualizado_em"])
            pagos += 1
    return pagos


# ═══════════════════ APIs ═══════════════════
def _fatura_dict(f):
    return {
        "id": f.id, "beneficiario": f.beneficiario.nome, "competencia": f.competencia,
        "mensalidade": _f(f.valor_mensalidade), "coparticipacao": _f(f.valor_coparticipacao),
        "total": _f(f.valor_total), "status": f.status,
        "vencimento": f.vencimento.strftime("%d/%m/%Y") if f.vencimento else None,
        "forma_cobranca": f.forma_cobranca, "nosso_numero": f.nosso_numero,
        "linha_digitavel": f.linha_digitavel, "pix_copia_cola": f.pix_copia_cola,
    }


@csrf_exempt
@require_http_methods(["POST"])
def api_cob_gerar_faturas(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    competencia = b.get("competencia")
    if not _comp_valida(competencia):
        return JsonResponse({"erro": "competencia inválida (YYYY-MM)"}, status=400)
    dia = int(b.get("dia_vencimento", 10) or 10)
    faturas = gerar_faturas_competencia(empresa, competencia, dia)
    return JsonResponse({"ok": True, "geradas": len(faturas),
                         "total": _f(sum((f.valor_total for f in faturas), Decimal("0")))})


@require_http_methods(["GET"])
def api_cob_faturas(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    competencia = request.GET.get("competencia") or timezone.now().strftime("%Y-%m")
    qs = FaturamentoBeneficiario.objects.filter(empresa=empresa, competencia=competencia).select_related("beneficiario")
    st = request.GET.get("status")
    if st:
        qs = qs.filter(status=st)
    faturas = list(qs[:500])
    resumo = {
        "total": _f(sum((f.valor_total for f in faturas), Decimal("0"))),
        "pago": _f(sum((f.valor_total for f in faturas if f.status == "pago"), Decimal("0"))),
        "pendente": len([f for f in faturas if f.status == "pendente"]),
        "qtd": len(faturas),
    }
    return JsonResponse({"competencia": competencia, "resumo": resumo,
                         "faturas": [_fatura_dict(f) for f in faturas]})


@csrf_exempt
@require_http_methods(["POST"])
def api_cob_emitir(request, fatura_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        fatura = FaturamentoBeneficiario.objects.get(id=fatura_id, empresa=empresa)
    except FaturamentoBeneficiario.DoesNotExist:
        return JsonResponse({"erro": "Fatura não encontrada"}, status=404)
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    forma = b.get("forma", "ambos")
    if forma not in ("pix", "boleto", "ambos"):
        return JsonResponse({"erro": "forma inválida (pix/boleto/ambos)"}, status=400)
    emitir_cobranca(
        fatura, forma,
        chave_pix=b.get("chave_pix", ""), nome_recebedor=b.get("nome_recebedor", empresa.nome),
        cidade=b.get("cidade", ""), codigo_banco=b.get("codigo_banco", "000"),
        agencia=b.get("agencia", "0000"), conta=b.get("conta", "00000000"),
    )
    return JsonResponse({"ok": True, "fatura": _fatura_dict(fatura)})


@csrf_exempt
@require_http_methods(["POST"])
def api_cob_remessa(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        b = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    competencia = b.get("competencia")
    if not _comp_valida(competencia):
        return JsonResponse({"erro": "competencia inválida"}, status=400)
    banco = b.get("banco", "000")
    faturas = list(FaturamentoBeneficiario.objects.filter(
        empresa=empresa, competencia=competencia, status="pendente").select_related("beneficiario"))
    if not faturas:
        return JsonResponse({"erro": "Nenhuma fatura pendente na competência."}, status=400)
    for f in faturas:
        if not f.nosso_numero:
            emitir_cobranca(f, "boleto", codigo_banco=banco)
    texto, total = gerar_remessa_cnab240(empresa, faturas, banco)
    rem = RemessaCNAB.objects.create(
        empresa=empresa, tipo="remessa", competencia=competencia, banco=banco,
        qtd_titulos=len(faturas), valor_total=total, arquivo=texto)
    return JsonResponse({"ok": True, "remessa_id": rem.id, "qtd_titulos": len(faturas),
                         "valor_total": _f(total)})


@require_http_methods(["GET"])
def api_cob_remessa_download(request, remessa_id):
    empresa, err = _ps_auth(request)
    if err:
        return err
    try:
        rem = RemessaCNAB.objects.get(id=remessa_id, empresa=empresa)
    except RemessaCNAB.DoesNotExist:
        return JsonResponse({"erro": "Remessa não encontrada"}, status=404)
    from django.http import HttpResponse
    resp = HttpResponse(rem.arquivo, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="remessa_{rem.competencia}_{rem.id}.rem"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def api_cob_conciliar(request):
    empresa, err = _ps_auth(request)
    if err:
        return err
    texto = request.body.decode("utf-8", "ignore") if request.body else ""
    if len(texto) < 20:
        return JsonResponse({"erro": "Arquivo de retorno vazio ou inválido"}, status=400)
    competencia = request.GET.get("competencia", "")
    pagos = conciliar_retorno_cnab(empresa, texto, competencia)
    RemessaCNAB.objects.create(empresa=empresa, tipo="retorno", competencia=competencia,
                               qtd_titulos=0, conciliados=pagos, arquivo=texto[:100000])
    return JsonResponse({"ok": True, "conciliados": pagos})


# ── page ─────────────────────────────────────────────────────────────────────
@ensure_csrf_cookie
@requer_setor("plano_saude")
@requer_operacao_page
@requer_permissao_modulo("plano.autorizacao")
def plano_cobranca_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/")
    ctx = contexto_navegacao_setorial(request, "plano_saude")
    ctx["empresa_id"] = str(empresa.id)
    return render(request, "plano_cobranca.html", ctx)
