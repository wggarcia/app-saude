"""
Hospital — Radioterapia com integração HL7 (Varian Aria / Halcyon)

O sistema Varian envia mensagens HL7 v2.5 para o HIS via HTTP.
Implementa recepção de ORM^O01, gestão de SessaoRadioterapia e KPIs.

POST /api/hospital/radioterapia/hl7/receber          — recebe HL7, retorna ACK
GET  /api/hospital/radioterapia/sessoes              — lista (filtros: status, sistema)
POST /api/hospital/radioterapia/sessoes              — cria sessão manual
GET  /api/hospital/radioterapia/sessoes/<pk>         — detalhe
PATCH /api/hospital/radioterapia/sessoes/<pk>        — atualiza progresso/status
GET  /api/hospital/radioterapia/kpis                 — métricas resumidas
"""
import json
import logging
from datetime import date, datetime

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .access_control import (
    api_requer_feature,
    get_setor,
    requer_feature_pacote,
    requer_operacao_page,
    requer_permissao_modulo,
    requer_setor,
)
from .services.auth_session import empresa_autenticada_from_request

logger = logging.getLogger(__name__)


# ─── Auth helper ──────────────────────────────────────────────────────────────

def _hosp(request):
    """Valida sessão hospital para o módulo de Radioterapia."""
    emp = empresa_autenticada_from_request(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


# ─── HL7 v2.5 parser (sem biblioteca externa) ─────────────────────────────────

def _parse_hl7(raw: str) -> dict:
    """
    Parseia mensagem HL7 v2.5 delimitada por CR (\\r) e pipe (|).
    Retorna dicionário com segmentos MSH, PID, ORC, ORM extraídos.

    Campos extraídos:
      msh_9        — MSH-9  (tipo da mensagem, ex.: ORM^O01)
      msh_10       — MSH-10 (message control ID)
      msh_sending  — MSH-3  (sistema de origem, ex.: ARIA)
      pid_3        — PID-3  (patient ID / prontuário)
      pid_5        — PID-5  (nome do paciente)
      pid_11_zip   — PID-11 (endereço — não usado; mantido para futuro)
      orc_1        — ORC-1  (tipo de ordem: NW/CA/DC/RP...)
      obr_4        — OBR-4  (serviço solicitado / plano)
      obr_7        — OBR-7  (data/hora de início)
    """
    segments = {}
    for line in raw.replace("\r\n", "\r").replace("\n", "\r").split("\r"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        seg_name = parts[0]
        segments.setdefault(seg_name, parts)

    def _field(seg_name, index, default=""):
        parts = segments.get(seg_name, [])
        try:
            value = parts[index]
        except IndexError:
            return default
        # HL7 sub-componentes: retorna o primeiro elemento antes de "^"
        return value.split("^")[0].strip() if value else default

    return {
        "raw_segments": segments,
        "msh_9":        "|".join(segments.get("MSH", [""] * 10)[9:10]).strip() if segments.get("MSH") else "",
        "msh_10":       _field("MSH", 10),
        "msh_sending":  _field("MSH", 3),
        "pid_3":        _field("PID", 3),
        "pid_5":        _field("PID", 5),
        "orc_1":        _field("ORC", 1),
        "obr_4":        _field("OBR", 4),
        "obr_7":        _field("OBR", 7),
    }


def _build_ack(msh_parts: list, ack_code: str = "AA", error_msg: str = "") -> str:
    """
    Constrói mensagem ACK HL7 v2.5 (MSH + MSA).
    ack_code: AA = Accept Acknowledgment | AE = Application Error
    """
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    # Usa o mesmo campo separador do MSH original, ou padrão
    field_sep = msh_parts[1] if len(msh_parts) > 1 else "|"
    encoding  = msh_parts[2] if len(msh_parts) > 2 else "^~\\&"
    sending_app = msh_parts[3] if len(msh_parts) > 3 else ""
    sending_fac = msh_parts[4] if len(msh_parts) > 4 else ""
    recv_app    = msh_parts[5] if len(msh_parts) > 5 else ""
    recv_fac    = msh_parts[6] if len(msh_parts) > 6 else ""
    msg_ctrl_id = msh_parts[10] if len(msh_parts) > 10 else "0"
    proc_id     = msh_parts[11] if len(msh_parts) > 11 else "P"
    version     = msh_parts[12] if len(msh_parts) > 12 else "2.5"

    sep = field_sep
    msh_ack = sep.join([
        "MSH",
        encoding,
        recv_app,   # resposta: inversão sending ↔ receiving
        recv_fac,
        sending_app,
        sending_fac,
        now_str,
        "",
        "ACK",
        f"ACK-{now_str}",
        proc_id,
        version,
    ])
    msa = sep.join(["MSA", ack_code, msg_ctrl_id, error_msg])
    return f"{msh_ack}\r{msa}\r"


# ─── Serializer ───────────────────────────────────────────────────────────────

def _sessao_to_dict(s) -> dict:
    return {
        "id":                       s.id,
        "paciente":                 s.paciente,
        "cid":                      s.cid,
        "sistema_radioterapia":     s.sistema_radioterapia,
        "numero_plano":             s.numero_plano,
        "dose_prescrita_gy":        float(s.dose_prescrita_gy) if s.dose_prescrita_gy is not None else None,
        "dose_fracao_gy":           float(s.dose_fracao_gy) if s.dose_fracao_gy is not None else None,
        "numero_fracoes_total":     s.numero_fracoes_total,
        "numero_fracoes_realizadas":s.numero_fracoes_realizadas,
        "tecnica":                  s.tecnica,
        "data_inicio":              s.data_inicio.isoformat() if s.data_inicio else None,
        "data_ultima_sessao":       s.data_ultima_sessao.isoformat() if s.data_ultima_sessao else None,
        "status":                   s.status,
        "hl7_mensagem_id":          s.hl7_mensagem_id,
        "sincronizado_hl7":         s.sincronizado_hl7,
        "criado_em":                s.criado_em.strftime("%d/%m/%Y %H:%M"),
    }


# ─── Page view ────────────────────────────────────────────────────────────────

@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.oncologia", "Radioterapia")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_radioterapia_page(request):
    return render(request, "hospital_radioterapia.html")


# ─── POST /api/hospital/radioterapia/hl7/receber ─────────────────────────────

@csrf_exempt
@api_requer_feature("hospital.oncologia")
def api_radioterapia_hl7_receber(request):
    """
    Recebe mensagem HL7 v2.5 do sistema Varian (Aria/Halcyon).
    Content-Type aceito: text/plain ou application/hl7-v2.
    Cria ou atualiza SessaoRadioterapia com base em ORM^O01.
    Retorna ACK HL7 (MSH + MSA^AA).
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    content_type = request.content_type or ""
    if not any(ct in content_type for ct in ("text/plain", "application/hl7-v2", "text/")):
        # Tolerante: aceita qualquer body de texto mesmo sem Content-Type correto
        pass

    try:
        raw = request.body.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("HL7 decode error: %s", exc)
        return HttpResponse("MSH|^~\\&|SOLUS|||VARIAN|||ACK|ERR001|P|2.5\rMSA|AE|0|Erro de encoding\r",
                            content_type="text/plain; charset=utf-8", status=400)

    if not raw.strip():
        return HttpResponse(
            "MSH|^~\\&|SOLUS|||VARIAN|||ACK|ERR002|P|2.5\rMSA|AE|0|Mensagem vazia\r",
            content_type="text/plain; charset=utf-8", status=400,
        )

    parsed = _parse_hl7(raw)
    msh_parts = parsed["raw_segments"].get("MSH", [])

    # Valida tipo da mensagem
    msg_type = parsed.get("msh_9", "")
    if "ORM" not in msg_type and "ORU" not in msg_type and "ADT" not in msg_type:
        ack_err = _build_ack(msh_parts, "AE", f"Tipo de mensagem nao suportado: {msg_type}")
        return HttpResponse(ack_err, content_type="text/plain; charset=utf-8", status=422)

    # Processa ORM^O01 — nova ordem de radioterapia
    try:
        from .models import SessaoRadioterapia

        paciente_nome = parsed["pid_5"] or "Paciente HL7"
        numero_plano  = parsed["obr_4"] or parsed["orc_1"] or ""
        msg_ctrl_id   = parsed["msh_10"]

        # Sistema de origem: Aria ou Halcyon
        sending_app = parsed["msh_sending"].lower()
        if "halcyon" in sending_app:
            sistema = "halcyon"
        else:
            sistema = "aria"  # padrão Varian

        # Data de início a partir de OBR-7 (formato HL7: YYYYMMDDHHMMSS)
        data_inicio = None
        obr_7 = parsed["obr_7"]
        if obr_7 and len(obr_7) >= 8:
            try:
                data_inicio = datetime.strptime(obr_7[:8], "%Y%m%d").date()
            except ValueError:
                data_inicio = None

        # Ação da ordem (ORC-1): NW=Nova, CA=Cancelar, DC=Descontinuar, RP=Reprogramar
        orc_action = parsed["orc_1"].upper()

        if orc_action == "CA":
            # Cancela/suspende sessão existente pelo msg_ctrl_id anterior
            try:
                sessao = SessaoRadioterapia.objects.get(
                    empresa=empresa,
                    hl7_mensagem_id=msg_ctrl_id,
                )
                sessao.status = "suspenso"
                sessao.save(update_fields=["status"])
            except SessaoRadioterapia.DoesNotExist:
                pass  # Não encontrou — ACK normal mesmo assim
        elif orc_action in ("NW", "RP", ""):
            # Cria ou atualiza pelo numero_plano + empresa
            defaults = {
                "paciente":           paciente_nome,
                "sistema_radioterapia": sistema,
                "hl7_mensagem_id":    msg_ctrl_id,
                "sincronizado_hl7":   True,
                "status":             "em_andamento",
            }
            if data_inicio:
                defaults["data_inicio"] = data_inicio
            if numero_plano:
                defaults["numero_plano"] = numero_plano

            if numero_plano:
                sessao, created = SessaoRadioterapia.objects.update_or_create(
                    empresa=empresa,
                    numero_plano=numero_plano,
                    defaults=defaults,
                )
            else:
                sessao = SessaoRadioterapia.objects.create(
                    empresa=empresa,
                    **defaults,
                )
                created = True

            logger.info(
                "HL7 ORM^O01 %s: sessao_id=%s paciente=%s plano=%s",
                "criada" if created else "atualizada",
                sessao.id, paciente_nome, numero_plano,
            )

    except Exception as exc:
        logger.exception("Erro ao processar HL7 ORM: %s", exc)
        ack_err = _build_ack(msh_parts, "AE", "Erro interno ao processar ORM")
        return HttpResponse(ack_err, content_type="text/plain; charset=utf-8", status=500)

    ack_ok = _build_ack(msh_parts, "AA")
    return HttpResponse(ack_ok, content_type="text/plain; charset=utf-8", status=200)


# ─── GET/POST /api/hospital/radioterapia/sessoes ─────────────────────────────

@api_requer_feature("hospital.oncologia")
@csrf_exempt
def api_radioterapia_sessoes(request):
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    if request.method == "GET":
        return _sessoes_lista(request, empresa)
    if request.method == "POST":
        return _sessoes_criar(request, empresa)
    return JsonResponse({"erro": "Método não permitido"}, status=405)


def _sessoes_lista(request, empresa):
    """Lista SessaoRadioterapia com filtros opcionais."""
    try:
        from .models import SessaoRadioterapia

        qs = SessaoRadioterapia.objects.filter(empresa=empresa)

        status_filtro = request.GET.get("status", "").strip()
        if status_filtro:
            qs = qs.filter(status=status_filtro)

        sistema_filtro = request.GET.get("sistema_radioterapia", "").strip()
        if sistema_filtro:
            qs = qs.filter(sistema_radioterapia=sistema_filtro)

        q = (request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(paciente__icontains=q)

        try:
            limit  = min(max(int(request.GET.get("limit", 50)), 1), 500)
            offset = max(int(request.GET.get("offset", 0)), 0)
        except (ValueError, TypeError):
            limit, offset = 50, 0

        total = qs.count()
        sessoes = qs[offset: offset + limit]

        return JsonResponse({
            "sessoes":  [_sessao_to_dict(s) for s in sessoes],
            "total":    total,
            "limit":    limit,
            "offset":   offset,
            "has_more": (offset + limit) < total,
        })

    except Exception as exc:
        logger.exception("Erro ao listar sessões de radioterapia: %s", exc)
        return JsonResponse({"erro": "Erro interno"}, status=500)


def _sessoes_criar(request, empresa):
    """Cria sessão de radioterapia manualmente."""
    try:
        from .models import SessaoRadioterapia

        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        paciente = (data.get("paciente") or "").strip()
        if not paciente:
            return JsonResponse({"erro": "Campo obrigatório: paciente"}, status=400)

        sistema = (data.get("sistema_radioterapia") or "aria").strip()
        sistemas_validos = [s[0] for s in SessaoRadioterapia.SISTEMA_CHOICES]
        if sistema not in sistemas_validos:
            return JsonResponse(
                {"erro": f"sistema_radioterapia deve ser um de: {sistemas_validos}"},
                status=400,
            )

        # data_inicio opcional
        data_inicio = None
        data_inicio_str = (data.get("data_inicio") or "").strip()
        if data_inicio_str:
            try:
                data_inicio = date.fromisoformat(data_inicio_str)
            except ValueError:
                return JsonResponse({"erro": "data_inicio inválida (use YYYY-MM-DD)"}, status=400)

        # dose_prescrita_gy opcional
        dose_prescrita = None
        if data.get("dose_prescrita_gy") is not None:
            try:
                dose_prescrita = float(data["dose_prescrita_gy"])
                if dose_prescrita <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return JsonResponse({"erro": "dose_prescrita_gy deve ser número positivo"}, status=400)

        # numero_fracoes_total opcional
        num_fracoes = None
        if data.get("numero_fracoes_total") is not None:
            try:
                num_fracoes = int(data["numero_fracoes_total"])
                if num_fracoes <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                return JsonResponse({"erro": "numero_fracoes_total deve ser inteiro positivo"}, status=400)

        sessao = SessaoRadioterapia.objects.create(
            empresa=empresa,
            paciente=paciente,
            cid=(data.get("cid") or "").strip(),
            sistema_radioterapia=sistema,
            numero_plano=(data.get("numero_plano") or "").strip(),
            dose_prescrita_gy=dose_prescrita,
            numero_fracoes_total=num_fracoes,
            data_inicio=data_inicio,
            status="planejado",
            sincronizado_hl7=False,
        )

        return JsonResponse({"sessao": _sessao_to_dict(sessao)}, status=201)

    except Exception as exc:
        logger.exception("Erro ao criar sessão de radioterapia: %s", exc)
        return JsonResponse({"erro": "Erro interno"}, status=500)


# ─── GET /api/hospital/radioterapia/sessoes/<pk> ──────────────────────────────

@api_requer_feature("hospital.oncologia")
def api_radioterapia_sessao_detalhe(request, pk: int):
    """Detalhe de uma sessão de radioterapia."""
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    try:
        from .models import SessaoRadioterapia
        try:
            sessao = SessaoRadioterapia.objects.get(pk=pk, empresa=empresa)
        except SessaoRadioterapia.DoesNotExist:
            return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

        return JsonResponse({"sessao": _sessao_to_dict(sessao)})

    except Exception as exc:
        logger.exception("Erro ao recuperar sessão de radioterapia pk=%s: %s", pk, exc)
        return JsonResponse({"erro": "Erro interno"}, status=500)


# ─── PATCH /api/hospital/radioterapia/sessoes/<pk> ────────────────────────────

@api_requer_feature("hospital.oncologia")
@csrf_exempt
def api_radioterapia_sessao_atualizar(request, pk: int):
    """
    Atualiza numero_fracoes_realizadas, status e/ou data_ultima_sessao
    de uma sessão de radioterapia existente.
    """
    if request.method != "PATCH":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    try:
        from .models import SessaoRadioterapia

        try:
            sessao = SessaoRadioterapia.objects.get(pk=pk, empresa=empresa)
        except SessaoRadioterapia.DoesNotExist:
            return JsonResponse({"erro": "Sessão não encontrada"}, status=404)

        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"erro": "JSON inválido"}, status=400)

        campos_atualizados = []

        # numero_fracoes_realizadas
        if "numero_fracoes_realizadas" in data:
            try:
                fracoes = int(data["numero_fracoes_realizadas"])
                if fracoes < 0:
                    raise ValueError
                sessao.numero_fracoes_realizadas = fracoes
                campos_atualizados.append("numero_fracoes_realizadas")
            except (ValueError, TypeError):
                return JsonResponse(
                    {"erro": "numero_fracoes_realizadas deve ser inteiro não-negativo"},
                    status=400,
                )

        # status
        if "status" in data:
            status_val = (data["status"] or "").strip()
            status_validos = [s[0] for s in SessaoRadioterapia.STATUS_CHOICES]
            if status_val not in status_validos:
                return JsonResponse(
                    {"erro": f"status deve ser um de: {status_validos}"},
                    status=400,
                )
            sessao.status = status_val
            campos_atualizados.append("status")

        # data_ultima_sessao
        if "data_ultima_sessao" in data:
            val = (data["data_ultima_sessao"] or "").strip()
            if val:
                try:
                    sessao.data_ultima_sessao = date.fromisoformat(val)
                    campos_atualizados.append("data_ultima_sessao")
                except ValueError:
                    return JsonResponse(
                        {"erro": "data_ultima_sessao inválida (use YYYY-MM-DD)"},
                        status=400,
                    )
            else:
                sessao.data_ultima_sessao = None
                campos_atualizados.append("data_ultima_sessao")

        if campos_atualizados:
            sessao.save(update_fields=campos_atualizados)

        return JsonResponse({"sessao": _sessao_to_dict(sessao)})

    except Exception as exc:
        logger.exception("Erro ao atualizar sessão de radioterapia pk=%s: %s", pk, exc)
        return JsonResponse({"erro": "Erro interno"}, status=500)


# ─── GET /api/hospital/radioterapia/kpis ─────────────────────────────────────

@api_requer_feature("hospital.oncologia")
def api_radioterapia_kpis(request):
    """
    KPIs resumidos de Radioterapia:
      em_andamento       — sessões com status em_andamento
      concluidos_mes     — sessões concluídas no mês corrente
      fracoes_hoje       — frações realizadas cuja data_ultima_sessao é hoje
      sincronizados_hl7  — sessões originadas via HL7
    """
    if request.method != "GET":
        return JsonResponse({"erro": "Método não permitido"}, status=405)

    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Acesso restrito ao módulo Hospital"}, status=403)

    try:
        from .models import SessaoRadioterapia

        hoje = timezone.now().date()
        primeiro_dia_mes = hoje.replace(day=1)

        base_qs = SessaoRadioterapia.objects.filter(empresa=empresa)

        em_andamento = base_qs.filter(status="em_andamento").count()

        concluidos_mes = base_qs.filter(
            status="concluido",
            data_ultima_sessao__gte=primeiro_dia_mes,
            data_ultima_sessao__lte=hoje,
        ).count()

        # fracoes_hoje: soma de numero_fracoes_realizadas das sessões com data_ultima_sessao hoje
        from django.db.models import Sum
        agg = base_qs.filter(data_ultima_sessao=hoje).aggregate(
            total_fracoes=Sum("numero_fracoes_realizadas")
        )
        fracoes_hoje = agg["total_fracoes"] or 0

        sincronizados_hl7 = base_qs.filter(sincronizado_hl7=True).count()

        return JsonResponse({
            "em_andamento":      em_andamento,
            "concluidos_mes":    concluidos_mes,
            "fracoes_hoje":      fracoes_hoje,
            "sincronizados_hl7": sincronizados_hl7,
        })

    except Exception as exc:
        logger.exception("Erro ao calcular KPIs de radioterapia: %s", exc)
        return JsonResponse({"erro": "Erro interno"}, status=500)
