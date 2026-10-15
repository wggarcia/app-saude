"""
Oncologia — Alta Complexidade
Protocolos quimioterápicos (PCDT/INCA), ciclos, APAC SUS faturamento e
toxicidade CTCAE v5.0.
"""
import json
import logging
import unicodedata
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.auth_session import empresa_autenticada_from_request as get_empresa
from .services.identidade_paciente import resolver_identidade
from .utils import validar_cpf_cadastro
from .access_control import (
    api_requer_feature, api_requer_permissao_modulo, get_setor, requer_setor,
    requer_feature_pacote, requer_operacao_page, requer_permissao_modulo,
)

logger = logging.getLogger(__name__)

# ── Segurança de dose ───────────────────────────────────────────────────────────
# Caps clínicos por droga. `max_abs_mg`: teto absoluto por administração
# (independe da superfície corporal). `max_cumulativa`: dose máxima acumulada ao
# longo da vida do paciente (cardiotoxicidade/fibrose). Fonte: bulas e protocolos
# INCA/PCDT. Sem esses limites, plugar o cálculo de dose nasceria sem barreira.
DOSE_CAPS = {
    "vincristina":   {"max_abs_mg": 2.0},
    "doxorrubicina": {"max_cumulativa": 450, "unidade_cumulativa": "mg/m²"},
    "bleomicina":    {"max_cumulativa": 400, "unidade_cumulativa": "UI"},
}

# Vocabulário CTCAE v5.0 — categorias mais frequentes em quimioterapia. Sem uma
# lista fechada, "Neutropenia"/"neutropenia"/"NEUTROPENIA" viram 3 categorias no KPI.
CTCAE_CATEGORIAS = [
    "Neutropenia", "Neutropenia febril", "Anemia", "Plaquetopenia", "Náusea",
    "Vômito", "Diarreia", "Mucosite", "Fadiga", "Neuropatia periférica",
    "Nefrotoxicidade", "Hepatotoxicidade", "Cardiotoxicidade", "Reação infusional",
    "Alopecia", "Rash cutâneo", "Outra",
]

GRAUS_CTCAE_VALIDOS = {1, 2, 3, 4, 5}

# Transições de status permitidas por entidade (impede status arbitrário via PUT).
TRANSICOES_CICLO = {
    "agendado":  {"em_curso", "cancelado", "suspenso"},
    "em_curso":  {"concluido", "suspenso", "cancelado"},
    "suspenso":  {"em_curso", "cancelado"},
    "concluido": set(),
    "cancelado": set(),
}
TRANSICOES_APAC = {
    "elaborando": {"submetida", "cancelada"},
    "submetida":  {"aprovada", "glosada", "cancelada"},
    "aprovada":   {"glosada", "cancelada"},
    "glosada":    {"submetida", "cancelada"},
    "cancelada":  set(),
}


def _hosp(request):
    emp = get_empresa(request)
    if emp and get_setor(emp) == "hospital":
        return emp
    return None


def _parse_json(request):
    """Parse seguro do corpo. Retorna (data, erro_response); um dos dois é None."""
    try:
        return json.loads(request.body or b"{}"), None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, JsonResponse({"erro": "JSON inválido no corpo da requisição"}, status=400)


def _norm(s):
    """Normaliza nome de droga: minúsculo, sem acento — para casar com DOSE_CAPS."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _num_positivo(valor):
    """Converte para float exigindo > 0 e finito. Retorna None se inválido."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")) or v <= 0:
        return None
    return v


@ensure_csrf_cookie
@requer_setor("hospital")
@requer_feature_pacote("hospital.oncologia", "Oncologia")
@requer_operacao_page
@requer_permissao_modulo("hospital.clinico")
def hospital_oncologia_page(request):
    return render(request, "hospital_oncologia.html")

# Protocolos PCDT/INCA mais prevalentes para seed
# Pré-medicação e suporte por protocolo. Um esquema sem antiemético e sem
# hidratação não é um esquema — é metade da prescrição. `momento` diz quando
# administrar em relação à quimioterapia.
_SUPORTE_SEED = {
    "FOLFOX-6": [
        {"droga": "Ondansetrona", "dose": 8, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Dexametasona", "dose": 10, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
    ],
    "FOLFIRI": [
        {"droga": "Ondansetrona", "dose": 8, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Dexametasona", "dose": 10, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Atropina", "dose": 0.25, "unidade": "mg", "via": "SC",
         "momento": "se síndrome colinérgica aguda da irinotecana"},
    ],
    "AC-T": [
        {"droga": "Ondansetrona", "dose": 8, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Dexametasona", "dose": 10, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Aprepitanto", "dose": 125, "unidade": "mg", "via": "VO",
         "momento": "1 h antes (ciclos com doxorrubicina — alto poder emetogênico)"},
        {"droga": "Difenidramina", "dose": 50, "unidade": "mg", "via": "EV",
         "momento": "30 min antes do paclitaxel (prevenção de hipersensibilidade)"},
    ],
    "BEP": [
        {"droga": "Ondansetrona", "dose": 8, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Dexametasona", "dose": 10, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Soro fisiológico 0,9%", "dose": 1000, "unidade": "mL", "via": "EV",
         "momento": "hiper-hidratação antes e depois da cisplatina (nefroproteção)"},
    ],
    "CHOP": [
        {"droga": "Ondansetrona", "dose": 8, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
        {"droga": "Dexametasona", "dose": 10, "unidade": "mg", "via": "EV", "momento": "30 min antes"},
    ],
}

# Critérios de aptidão específicos. BEP carrega cisplatina: função renal manda.
_CRITERIOS_SEED = {
    "BEP": {"clearance_min": 60},
}

_PROTOCOLOS_SEED = [
    ("FOLFOX-6",   "C18", "EV", 12, 14, [
        {"droga": "Oxaliplatina", "dose": 85, "unidade": "mg/m²", "dia": 1},
        {"droga": "Leucovorina",  "dose": 400, "unidade": "mg/m²", "dia": 1},
        {"droga": "Fluorouracila","dose": 400, "unidade": "mg/m²", "dia": 1, "modo": "bolus"},
        {"droga": "Fluorouracila","dose": 2400, "unidade": "mg/m²", "dia": "1-2", "modo": "CI 46h"},
    ]),
    ("FOLFIRI",    "C18", "EV", 12, 14, [
        {"droga": "Irinotecana",  "dose": 180, "unidade": "mg/m²", "dia": 1},
        {"droga": "Leucovorina",  "dose": 400, "unidade": "mg/m²", "dia": 1},
        {"droga": "Fluorouracila","dose": 400, "unidade": "mg/m²", "dia": 1, "modo": "bolus"},
        {"droga": "Fluorouracila","dose": 2400, "unidade": "mg/m²", "dia": "1-2", "modo": "CI 46h"},
    ]),
    ("AC-T",       "C50", "EV", 8, 21, [
        {"droga": "Doxorrubicina","dose": 60, "unidade": "mg/m²", "dia": 1, "ciclos": "1-4"},
        {"droga": "Ciclofosfamida","dose": 600,"unidade": "mg/m²", "dia": 1, "ciclos": "1-4"},
        {"droga": "Paclitaxel",  "dose": 175, "unidade": "mg/m²", "dia": 1, "ciclos": "5-8"},
    ]),
    ("BEP",        "C62", "EV", 3, 21, [
        {"droga": "Bleomicina",  "dose": 30, "unidade": "UI", "dia": "1,8,15"},
        {"droga": "Etoposida",   "dose": 100,"unidade": "mg/m²", "dia": "1-5"},
        {"droga": "Cisplatina",  "dose": 20, "unidade": "mg/m²", "dia": "1-5"},
    ]),
    ("CHOP",       "C83", "EV", 6, 21, [
        {"droga": "Ciclofosfamida","dose": 750,"unidade": "mg/m²", "dia": 1},
        {"droga": "Doxorrubicina","dose": 50, "unidade": "mg/m²", "dia": 1},
        {"droga": "Vincristina", "dose": 1.4, "unidade": "mg/m²", "dia": 1},
        {"droga": "Prednisona",  "dose": 100,"unidade": "mg/dia",  "dia": "1-5"},
    ]),
]


def _get_onco_models():
    from .models import ProtocoloOncologico, CicloQuimioterapia, APACOncologia, ToxicidadeQuimio
    return ProtocoloOncologico, CicloQuimioterapia, APACOncologia, ToxicidadeQuimio


# ── Resposta ao tratamento (RECIST 1.1) ────────────────────────────────────────
# Limiares do critério RECIST 1.1. A progressão é medida contra o NADIR (a menor
# soma já registrada), não contra a basal — é o detalhe que separa uma régua de
# verdade de uma conta de padaria: um tumor que encolheu muito e voltou a crescer
# ainda pode estar abaixo da basal e já ser progressão.
RECIST_REDUCAO_RP = 30.0     # % de redução vs basal para resposta parcial
RECIST_AUMENTO_DP = 20.0     # % de aumento vs nadir para progressão
RECIST_AUMENTO_ABSOLUTO_DP_MM = 5.0   # exige também 5 mm de aumento absoluto


def _classificar_recist(soma_atual, soma_basal, soma_nadir,
                        lesoes_novas=False, desaparecimento_total=False):
    """Classifica a resposta pelo RECIST 1.1.

    Devolve (resposta, variacao_vs_basal_pct, variacao_vs_nadir_pct).
    A ordem importa: lesão nova é progressão independentemente da medida.
    """
    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    atual, basal, nadir = _f(soma_atual), _f(soma_basal), _f(soma_nadir)

    var_basal = var_nadir = None
    if atual is not None and basal:
        var_basal = round((atual - basal) / basal * 100.0, 1)
    if atual is not None and nadir:
        var_nadir = round((atual - nadir) / nadir * 100.0, 1)

    # Lesão nova é progressão, não importa o que a soma diga.
    if lesoes_novas:
        return "dp", var_basal, var_nadir
    if desaparecimento_total:
        return "rc", var_basal, var_nadir
    if atual is None or basal is None:
        return "ne", var_basal, var_nadir
    if atual == 0:
        return "rc", var_basal, var_nadir

    # Progressão: ≥20% acima do nadir E ≥5 mm de aumento absoluto.
    if nadir:
        if (var_nadir is not None and var_nadir >= RECIST_AUMENTO_DP
                and (atual - nadir) >= RECIST_AUMENTO_ABSOLUTO_DP_MM):
            return "dp", var_basal, var_nadir
    # Resposta parcial: ≥30% de redução vs basal.
    if var_basal is not None and var_basal <= -RECIST_REDUCAO_RP:
        return "rp", var_basal, var_nadir
    return "de", var_basal, var_nadir


def _historico_resposta(empresa, cpf, nome, Modelo):
    """Basal e nadir do paciente, base de qualquer classificação posterior."""
    qs = Modelo.objects.filter(empresa=empresa)
    qs = qs.filter(cpf_paciente=cpf) if cpf else qs.filter(paciente_nome__iexact=nome)
    basal_obj = qs.filter(basal=True).order_by("data_avaliacao").first()
    basal = float(basal_obj.soma_lesoes_mm) if (
        basal_obj and basal_obj.soma_lesoes_mm is not None) else None
    somas = [float(a.soma_lesoes_mm) for a in qs
             if a.soma_lesoes_mm is not None]
    nadir = min(somas) if somas else None
    return basal, nadir


# ── Relógio regulatório da autorização ─────────────────────────────────────────
# A ANS exige resposta em terapias oncológicas em até 5 dias úteis (RN 623/2024).
# Feriados NÃO são considerados: contá-los como dias úteis faz o alerta disparar
# ANTES do prazo real, que é o erro seguro para quem precisa responder a tempo.
def _dias_uteis_entre(inicio, fim):
    """Dias úteis decorridos entre duas datas (exclui o dia da solicitação)."""
    if not inicio or not fim or fim < inicio:
        return 0
    dias = 0
    atual = inicio
    while atual < fim:
        atual += timedelta(days=1)
        if atual.weekday() < 5:          # 0=segunda … 4=sexta
            dias += 1
    return dias


def _prazo_resposta_guia(guia, hoje=None):
    """Situação da guia frente ao prazo regulatório de resposta.

    Devolve dict com dias úteis decorridos, restantes e se estourou. Só se aplica
    enquanto a guia está em análise — depois de respondida, mede o que levou.
    """
    hoje = hoje or date.today()
    prazo = guia.prazo_resposta_dias_uteis or 5
    if not guia.data_solicitacao:
        return {"aplicavel": False, "prazo_dias_uteis": prazo}
    referencia = guia.data_resposta or hoje
    decorridos = _dias_uteis_entre(guia.data_solicitacao, referencia)
    restantes = prazo - decorridos
    respondida = guia.data_resposta is not None
    return {
        "aplicavel": True,
        "prazo_dias_uteis": prazo,
        "data_solicitacao": guia.data_solicitacao.isoformat(),
        "data_resposta": guia.data_resposta.isoformat() if respondida else None,
        "respondida": respondida,
        "dias_uteis_decorridos": decorridos,
        "dias_uteis_restantes": max(restantes, 0),
        "estourado": decorridos > prazo,
        "vence_hoje": (not respondida) and restantes == 0,
    }


def _sync_status_guia(guia):
    """Atualiza o status da guia conforme validade e ciclos consumidos."""
    hoje = date.today()
    # Em análise ou negada são decisões de autorização, não de vigência: o
    # relógio de validade só corre depois que a guia é concedida.
    if guia.status in ("cancelada", "em_analise", "negada"):
        return guia.status
    if guia.ciclos_autorizados and guia.ciclos_utilizados >= guia.ciclos_autorizados:
        novo = "esgotada"
    elif guia.data_validade < hoje:
        novo = "vencida"
    else:
        novo = "vigente"
    if novo != guia.status:
        guia.status = novo
        guia.save(update_fields=["status"])
    return novo


def _sc_dubois(peso_kg, altura_cm):
    """Superfície corporal DuBois & DuBois (m²). Valida faixa fisiológica para
    não estourar (entrada negativa gerava complex→TypeError→500; valores absurdos
    estouravam o DecimalField)."""
    peso = _num_positivo(peso_kg)
    altura = _num_positivo(altura_cm)
    if peso is None or altura is None:
        return None
    # Faixa fisiológica plausível — fora disso é erro de digitação.
    if not (0.5 <= peso <= 400) or not (20 <= altura <= 260):
        return None
    return round(0.20247 * (altura / 100) ** 0.725 * peso ** 0.425, 4)


def _calcular_doses(drogas, sc_m2, auc_alvo=None, clearance=None):
    """Calcula a dose de cada droga do protocolo.

    Três caminhos, nesta ordem:
      • unidade com AUC  → fórmula de Calvert (carboplatina), usando o clearance;
      • unidade com m²   → multiplica pela superfície corporal e aplica teto absoluto;
      • demais           → dose fixa (UI, mg/dia), sem multiplicar.
    """
    resultado = []
    for d in (drogas or []):
        nome = d.get("droga")
        dose_ref = d.get("dose")
        unidade = (d.get("unidade") or "")
        item = {
            "droga": nome,
            "dose_referencia": dose_ref,
            "unidade": unidade,
            "dia": d.get("dia"),
            "dose_calculada": None,
            "unidade_calculada": None,
            "cap_aplicado": False,
        }
        try:
            dose_ref_f = float(dose_ref) if dose_ref is not None else None
        except (TypeError, ValueError):
            dose_ref_f = None

        # Carboplatina e afins: a dose vem do AUC, não da superfície corporal.
        if "auc" in unidade.lower():
            alvo = auc_alvo if auc_alvo not in (None, "") else dose_ref_f
            dose_calc, tfg_usada, teto = _dose_carboplatina_calvert(alvo, clearance)
            item["auc_alvo"] = float(alvo) if alvo not in (None, "") else None
            item["tfg_utilizada"] = tfg_usada
            item["formula"] = "Calvert (AUC × [TFG + 25])"
            if dose_calc is None:
                item["erro"] = ("Carboplatina exige AUC alvo e clearance de creatinina "
                                "para calcular a dose pela fórmula de Calvert.")
            else:
                item["dose_calculada"] = dose_calc
                item["unidade_calculada"] = "mg"
                item["cap_aplicado"] = teto
                if teto:
                    item["observacao"] = (
                        f"TFG limitada a {CALVERT_TFG_MAXIMA:.0f} mL/min no cálculo "
                        f"(teto fisiológico) para não superestimar a dose.")
            resultado.append(item)
            continue

        if dose_ref_f is not None and sc_m2 and "m²" in unidade:
            dose_calc = round(dose_ref_f * float(sc_m2), 2)
            cap = DOSE_CAPS.get(_norm(nome), {}).get("max_abs_mg")
            if cap and dose_calc > cap:
                dose_calc = cap
                item["cap_aplicado"] = True
            item["dose_calculada"] = dose_calc
            item["unidade_calculada"] = "mg"
        elif dose_ref_f is not None:
            # dose fixa (não depende de SC)
            item["dose_calculada"] = dose_ref_f
            item["unidade_calculada"] = unidade.replace("/m²", "").strip() or "mg"
        resultado.append(item)
    return resultado


def _alertas_dose_cumulativa(empresa, cpf_paciente, protocolo, doses_novas, CicloModel):
    """Soma a dose acumulada de drogas com teto cumulativo (Doxorrubicina,
    Bleomicina) nos ciclos anteriores do MESMO paciente e alerta se ultrapassar."""
    if not cpf_paciente:
        return []
    alertas = []
    # drogas com cap cumulativo presentes neste protocolo
    caps_relevantes = {
        _norm(dd["droga"]): DOSE_CAPS[_norm(dd["droga"])]
        for dd in doses_novas
        if _norm(dd.get("droga")) in DOSE_CAPS
        and "max_cumulativa" in DOSE_CAPS[_norm(dd["droga"])]
    }
    if not caps_relevantes:
        return []
    anteriores = CicloModel.objects.filter(
        empresa=empresa, cpf_paciente=cpf_paciente
    ).exclude(status="cancelado")
    for norm_nome, cap in caps_relevantes.items():
        acumulado = 0.0
        for c in anteriores:
            for dd in (c.doses_calculadas or []):
                if _norm(dd.get("droga")) == norm_nome and dd.get("dose_calculada"):
                    acumulado += float(dd["dose_calculada"])
        # soma a dose deste ciclo
        for dd in doses_novas:
            if _norm(dd.get("droga")) == norm_nome and dd.get("dose_calculada"):
                acumulado += float(dd["dose_calculada"])
        if acumulado >= cap["max_cumulativa"]:
            alertas.append(
                f"⚠️ Dose cumulativa de {norm_nome.title()} = {round(acumulado,1)} "
                f"{cap.get('unidade_cumulativa','')} atinge/ultrapassa o teto de "
                f"{cap['max_cumulativa']} — risco de toxicidade cumulativa."
            )
    return alertas


# ── Aptidão clínica para infundir (hold parameters) ─────────────────────────────
# Antes de qualquer ciclo, a diretriz manda conferir medula, função renal e
# hepática. Estes são os limiares padrão usados na maioria dos esquemas; cada
# protocolo pode sobrescrevê-los em `criterios_aptidao`.
APTIDAO_PADRAO = {
    "neutrofilos_min": 1500,    # /mm³
    "plaquetas_min":   100000,  # /mm³
    "clearance_min":   50,      # mL/min
    "bilirrubina_max": 1.5,     # mg/dL
}
# Margem acima do limiar que ainda acende ressalva (limítrofe).
APTIDAO_MARGEM_RESSALVA = 0.20

# Ajuste de dose por função orgânica. O sistema SINALIZA — nunca altera a dose
# sozinho. Quem ajusta é o oncologista; o papel do software é não deixar passar.
AJUSTE_DOSE_FUNCAO = {
    "cisplatina":   {"clearance_min": 60,
                     "alerta": "nefrotóxica — a maioria dos protocolos contraindica "
                               "abaixo de 60 mL/min ou exige troca por carboplatina"},
    "metotrexato":  {"clearance_min": 60,
                     "alerta": "eliminação renal — risco de toxicidade grave com "
                               "clearance reduzido"},
    "doxorrubicina": {"bilirrubina_max": 1.5,
                      "alerta": "metabolismo hepático — reduzir dose conforme bilirrubina"},
    "paclitaxel":   {"bilirrubina_max": 1.5,
                     "alerta": "metabolismo hepático — reduzir dose conforme bilirrubina"},
    "docetaxel":    {"bilirrubina_max": 1.5,
                     "alerta": "metabolismo hepático — reduzir ou suspender conforme bilirrubina"},
    "irinotecano":  {"bilirrubina_max": 1.5,
                     "alerta": "metabolismo hepático — reduzir dose conforme bilirrubina"},
    "vincristina":  {"bilirrubina_max": 1.5,
                     "alerta": "metabolismo hepático — reduzir dose conforme bilirrubina"},
}

# Teto fisiológico da taxa de filtração usada na fórmula de Calvert. Sem ele, um
# clearance superestimado vira dose excessiva de carboplatina.
CALVERT_TFG_MAXIMA = 125.0


def _limiares_aptidao(protocolo):
    """Limiares do protocolo sobre o padrão seguro. Valores inválidos são ignorados."""
    limiares = dict(APTIDAO_PADRAO)
    custom = getattr(protocolo, "criterios_aptidao", None) or {}
    if isinstance(custom, dict):
        for chave, valor in custom.items():
            if chave in limiares:
                try:
                    limiares[chave] = float(valor)
                except (TypeError, ValueError):
                    continue
    return limiares


def _avaliar_aptidao_ciclo(protocolo, neutrofilos, plaquetas, clearance, bilirrubina):
    """Decide se o paciente está apto a receber o ciclo HOJE.

    Devolve (status, bloqueios). NUNCA impede o registro: o ciclo é gravado do
    mesmo jeito e a decisão continua do oncologista — o que muda é que a ressalva
    fica registrada, e não perdida numa tela de leitura.
    """
    lim = _limiares_aptidao(protocolo)
    bloqueios, ressalvas = [], []

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    neutro, plaq = _f(neutrofilos), _f(plaquetas)
    clear, bili = _f(clearance), _f(bilirrubina)

    # Sem medula avaliada não há como julgar — honesto, como a adequação clínica.
    if neutro is None or plaq is None:
        return "nao_avaliado", [
            "Hemograma do ciclo não informado (neutrófilos e plaquetas) — "
            "aptidão não avaliada."
        ]

    if neutro < lim["neutrofilos_min"]:
        bloqueios.append(
            f"Neutrófilos {int(neutro)}/mm³ abaixo do mínimo de "
            f"{int(lim['neutrofilos_min'])}/mm³ — risco de neutropenia febril.")
    elif neutro < lim["neutrofilos_min"] * (1 + APTIDAO_MARGEM_RESSALVA):
        ressalvas.append(
            f"Neutrófilos {int(neutro)}/mm³ no limite inferior "
            f"(mínimo {int(lim['neutrofilos_min'])}/mm³).")

    if plaq < lim["plaquetas_min"]:
        bloqueios.append(
            f"Plaquetas {int(plaq)}/mm³ abaixo do mínimo de "
            f"{int(lim['plaquetas_min'])}/mm³ — risco hemorrágico.")
    elif plaq < lim["plaquetas_min"] * (1 + APTIDAO_MARGEM_RESSALVA):
        ressalvas.append(
            f"Plaquetas {int(plaq)}/mm³ no limite inferior "
            f"(mínimo {int(lim['plaquetas_min'])}/mm³).")

    if clear is not None and clear < lim["clearance_min"]:
        bloqueios.append(
            f"Clearance de creatinina {clear:.0f} mL/min abaixo de "
            f"{lim['clearance_min']:.0f} mL/min — revisar dose e nefrotoxicidade.")
    if bili is not None and bili > lim["bilirrubina_max"]:
        bloqueios.append(
            f"Bilirrubina {bili:.2f} mg/dL acima de "
            f"{lim['bilirrubina_max']:.2f} mg/dL — revisar dose de drogas hepáticas.")

    if bloqueios:
        return "inapto", bloqueios + ressalvas
    if ressalvas:
        return "apto_ressalva", ressalvas
    return "apto", []


def _alertas_funcao_organica(drogas, clearance, bilirrubina):
    """Sinaliza drogas do protocolo que exigem ajuste pela função renal/hepática.
    Não altera dose — apenas não deixa passar em silêncio."""
    alertas = []

    def _f(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    clear, bili = _f(clearance), _f(bilirrubina)
    for d in (drogas or []):
        regra = AJUSTE_DOSE_FUNCAO.get(_norm(d.get("droga")))
        if not regra:
            continue
        nome = (d.get("droga") or "").strip()
        if (clear is not None and "clearance_min" in regra
                and clear < regra["clearance_min"]):
            alertas.append(
                f"⚠️ {nome}: clearance {clear:.0f} mL/min — {regra['alerta']}.")
        if (bili is not None and "bilirrubina_max" in regra
                and bili > regra["bilirrubina_max"]):
            alertas.append(
                f"⚠️ {nome}: bilirrubina {bili:.2f} mg/dL — {regra['alerta']}.")
    return alertas


def _dose_carboplatina_calvert(auc_alvo, clearance_ml_min):
    """Fórmula de Calvert: dose (mg) = AUC × (TFG + 25).

    Carboplatina NÃO é dosada por superfície corporal. Sem isto, o cálculo do
    módulo errava a dose de um dos quimioterápicos mais usados do mundo.
    Devolve (dose_mg, tfg_usada, teto_aplicado) ou (None, None, False).
    """
    try:
        auc = float(auc_alvo)
        tfg = float(clearance_ml_min)
    except (TypeError, ValueError):
        return None, None, False
    if auc <= 0 or tfg <= 0:
        return None, None, False
    teto = tfg > CALVERT_TFG_MAXIMA
    if teto:
        tfg = CALVERT_TFG_MAXIMA
    return round(auc * (tfg + 25.0), 2), tfg, teto


def _elementos_obrigatorios_primeira_dose(ciclo_numero, protocolo, confirmacao_patologica,
                                          estadiamento, cid10, intencao):
    """Checklist do que precisa estar no prontuário ANTES da primeira dose de um
    esquema novo (padrão ASCO/ONS). Só se aplica ao ciclo 1."""
    if ciclo_numero != 1:
        return []
    faltando = []
    if getattr(protocolo, "exige_confirmacao_patologica", True) and not confirmacao_patologica:
        faltando.append("confirmação patológica do diagnóstico")
    if not (estadiamento or "").strip():
        faltando.append("estadiamento no início do tratamento")
    if not (cid10 or "").strip():
        faltando.append("diagnóstico (CID-10)")
    if not (intencao or "").strip():
        faltando.append("intenção do tratamento (curativo/paliativo/adjuvante/neoadjuvante)")
    return faltando


# ── Protocolos ─────────────────────────────────────────────────────────────────

def _seed_protocolos(empresa, ProtocoloOncologico):
    """Popula os protocolos PCDT/INCA de referência. Idempotente (get_or_create)."""
    with transaction.atomic():
        for nome, cid, via, ciclos, intervalo, drogas in _PROTOCOLOS_SEED:
            p, _criado = ProtocoloOncologico.objects.get_or_create(
                empresa=empresa, codigo=nome,
                defaults={
                    "nome": nome,
                    "indicacao_cid": cid,
                    "via": via,
                    "ciclos_total": ciclos,
                    "intervalo_dias": intervalo,
                    "drogas": drogas,
                    "drogas_suporte": _SUPORTE_SEED.get(nome, []),
                    "criterios_aptidao": _CRITERIOS_SEED.get(nome, {}),
                    "ativo": True,
                },
            )
            # Protocolos semeados antes do suporte existir ficam completos aqui,
            # sem sobrescrever o que o hospital tenha ajustado à mão.
            campos = []
            if not p.drogas_suporte and _SUPORTE_SEED.get(nome):
                p.drogas_suporte = _SUPORTE_SEED[nome]; campos.append("drogas_suporte")
            if not p.criterios_aptidao and _CRITERIOS_SEED.get(nome):
                p.criterios_aptidao = _CRITERIOS_SEED[nome]; campos.append("criterios_aptidao")
            if campos:
                p.save(update_fields=campos)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_protocolos(request):
    """GET/POST /api/hospital/oncologia/protocolos/ — catálogo (seed PCDT + próprios)."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProtocoloOncologico, *_ = _get_onco_models()

    # POST: cadastra protocolo próprio do hospital.
    if request.method == "POST":
        data, erro = _parse_json(request)
        if erro:
            return erro
        codigo = (data.get("codigo") or "").strip()
        nome = (data.get("nome") or "").strip()
        if not codigo or not nome:
            return JsonResponse({"erro": "Código e nome são obrigatórios"}, status=400)
        drogas = data.get("drogas", [])
        if not isinstance(drogas, list):
            return JsonResponse({"erro": "drogas deve ser uma lista"}, status=400)
        suporte = data.get("drogas_suporte", [])
        if not isinstance(suporte, list):
            return JsonResponse({"erro": "drogas_suporte deve ser uma lista"}, status=400)
        criterios = data.get("criterios_aptidao", {})
        if not isinstance(criterios, dict):
            return JsonResponse({"erro": "criterios_aptidao deve ser um objeto"}, status=400)
        if ProtocoloOncologico.objects.filter(empresa=empresa, codigo=codigo).exists():
            return JsonResponse({"erro": f"Já existe protocolo com o código '{codigo}'"}, status=400)
        p = ProtocoloOncologico.objects.create(
            empresa=empresa, codigo=codigo, nome=nome,
            indicacao_cid=data.get("indicacao_cid", ""),
            via=data.get("via", ""),
            ciclos_total=data.get("ciclos_total") or None,
            intervalo_dias=data.get("intervalo_dias") or None,
            drogas=drogas,
            drogas_suporte=suporte,
            criterios_aptidao=criterios,
            exige_confirmacao_patologica=bool(
                data.get("exige_confirmacao_patologica", True)),
            obs=data.get("obs", ""),
            ativo=True,
        )
        return JsonResponse({"id": p.id, "codigo": p.codigo}, status=201)

    # Seed de referência na primeira visualização (idempotente, transacional).
    if not ProtocoloOncologico.objects.filter(empresa=empresa).exists():
        _seed_protocolos(empresa, ProtocoloOncologico)

    qs = ProtocoloOncologico.objects.filter(empresa=empresa, ativo=True)
    cid_f = request.GET.get("cid")
    q     = request.GET.get("q")

    if cid_f:
        qs = qs.filter(indicacao_cid__icontains=cid_f)
    if q:
        qs = qs.filter(Q(nome__icontains=q) | Q(codigo__icontains=q))

    return JsonResponse({
        "total": qs.count(),
        "protocolos": [
            {
                "id": p.id,
                "codigo": p.codigo,
                "nome": p.nome,
                "indicacao_cid": p.indicacao_cid,
                "via": p.via,
                "ciclos_total": p.ciclos_total,
                "intervalo_dias": p.intervalo_dias,
                "drogas": p.drogas,
                "drogas_suporte": p.drogas_suporte,
                "criterios_aptidao": p.criterios_aptidao or APTIDAO_PADRAO,
                "criterios_sao_padrao": not bool(p.criterios_aptidao),
                "exige_confirmacao_patologica": p.exige_confirmacao_patologica,
            }
            for p in qs.order_by("nome")
        ],
    })


# ── Ciclos ─────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_ciclos(request):
    """GET/POST /api/hospital/oncologia/ciclos/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    ProtocoloOncologico, CicloQuimioterapia, *_ = _get_onco_models()

    if request.method == "GET":
        qs = CicloQuimioterapia.objects.filter(empresa=empresa).select_related("protocolo")
        status_f = request.GET.get("status")
        q        = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(cpf_paciente=q))

        hoje = date.today()
        total = qs.count()
        ciclos_pag = list(qs.order_by("-data_inicio")[:200])

        def _atrasado(c):
            # Ciclo agendado/em curso cuja data prevista já passou.
            return bool(c.data_prevista and c.data_prevista < hoje
                        and c.status in ("agendado", "em_curso"))

        return JsonResponse({
            "total": total,
            "exibidos": len(ciclos_pag),
            "ciclos": [
                {
                    "id": c.id,
                    "protocolo": c.protocolo.codigo,
                    "paciente_nome": c.paciente_nome,
                    "cpf_paciente": c.cpf_paciente,
                    "cid10_principal": c.cid10_principal,
                    "numero_ciclo": c.numero_ciclo,
                    "ciclos_total": c.protocolo.ciclos_total,
                    "data_inicio": c.data_inicio.isoformat(),
                    "data_prevista": c.data_prevista.isoformat() if c.data_prevista else None,
                    "data_fim": c.data_fim.isoformat() if c.data_fim else None,
                    "atrasado": _atrasado(c),
                    "status": c.status,
                    "status_display": c.get_status_display(),
                    "sc_m2": float(c.sc_m2) if c.sc_m2 else None,
                    "aptidao_status": c.aptidao_status,
                }
                for c in ciclos_pag
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    paciente_nome = (data.get("paciente_nome") or "").strip()
    cid10 = (data.get("cid10_principal") or "").strip()
    data_inicio = data.get("data_inicio")
    if not paciente_nome or not cid10 or not data_inicio:
        return JsonResponse(
            {"erro": "Paciente, CID-10 principal e data de início são obrigatórios"}, status=400)

    try:
        protocolo = ProtocoloOncologico.objects.get(
            id=data.get("protocolo_id"), empresa=empresa)
    except (ProtocoloOncologico.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"erro": "Protocolo não encontrado"}, status=404)

    # Peso e altura são obrigatórios — sem eles não há superfície corporal e o
    # ciclo seria salvo sem base de dose (risco assistencial silencioso).
    peso = _num_positivo(data.get("peso_kg"))
    altura = _num_positivo(data.get("altura_cm"))
    if peso is None or altura is None:
        return JsonResponse(
            {"erro": "Peso (kg) e altura (cm) são obrigatórios e devem ser válidos "
                     "para o cálculo da superfície corporal."}, status=400)
    sc_m2 = _sc_dubois(peso, altura)
    if sc_m2 is None:
        return JsonResponse(
            {"erro": "Peso/altura fora da faixa fisiológica — verifique os valores."}, status=400)

    # Número do ciclo dentro do total do protocolo.
    try:
        numero_ciclo = int(data.get("numero_ciclo", 1))
    except (TypeError, ValueError):
        return JsonResponse({"erro": "Número do ciclo inválido"}, status=400)
    if numero_ciclo < 1:
        return JsonResponse({"erro": "Número do ciclo deve ser ≥ 1"}, status=400)
    if protocolo.ciclos_total and numero_ciclo > protocolo.ciclos_total:
        return JsonResponse(
            {"erro": f"Número do ciclo ({numero_ciclo}) excede o total do protocolo "
                     f"({protocolo.ciclos_total})."}, status=400)

    # Doses calculadas (com caps absolutos) + data prevista do próximo ciclo.
    auc_alvo = _num_positivo(data.get("auc_alvo"))
    clearance_informado = _num_positivo(data.get("clearance_creatinina"))
    doses = _calcular_doses(protocolo.drogas, sc_m2,
                            auc_alvo=auc_alvo, clearance=clearance_informado)
    data_prevista = None
    try:
        di = datetime.strptime(str(data_inicio)[:10], "%Y-%m-%d").date()
        if protocolo.intervalo_dias:
            data_prevista = di + timedelta(days=protocolo.intervalo_dias)
    except (ValueError, TypeError):
        return JsonResponse({"erro": "Data de início inválida (use AAAA-MM-DD)"}, status=400)

    cpf_paciente = data.get("cpf_paciente", "")
    ok_cpf, erro_cpf = validar_cpf_cadastro(cpf_paciente, empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)

    # Guia opcional — validada por tenant, validade e ciclos disponíveis.
    guia = None
    guia_id = data.get("guia_id")
    alertas_guia = []
    if guia_id:
        from .models import GuiaOncologica
        guia = GuiaOncologica.objects.filter(id=guia_id, empresa=empresa).first()
        if guia is None:
            return JsonResponse({"erro": "Guia não encontrada nesta empresa"}, status=400)
        _sync_status_guia(guia)
        if guia.status == "vencida":
            alertas_guia.append(
                f"⚠️ Guia {guia.numero_guia} VENCIDA em {guia.data_validade.strftime('%d/%m/%Y')}.")
        elif guia.status == "esgotada":
            alertas_guia.append(
                f"⚠️ Guia {guia.numero_guia} já consumiu todos os ciclos autorizados.")
        elif guia.dias_para_vencer() <= 15:
            alertas_guia.append(
                f"⚠️ Guia {guia.numero_guia} vence em {guia.dias_para_vencer()} dia(s).")

    alertas_cum = _alertas_dose_cumulativa(
        empresa, "".join(filter(str.isdigit, cpf_paciente)), protocolo, doses,
        CicloQuimioterapia)

    # ── Aptidão clínica: a medula e os órgãos aguentam este ciclo hoje? ──────
    neutrofilos_in = data.get("neutrofilos") or None
    plaquetas_in   = data.get("plaquetas") or None
    bilirrubina_in = _num_positivo(data.get("bilirrubina_mg_dl"))
    aptidao_status, aptidao_bloqueios = _avaliar_aptidao_ciclo(
        protocolo, neutrofilos_in, plaquetas_in, clearance_informado, bilirrubina_in)

    # Drogas que pedem ajuste por função renal/hepática — sinaliza, não ajusta.
    alertas_orgao = _alertas_funcao_organica(
        protocolo.drogas, clearance_informado, bilirrubina_in)

    # Elementos que precisam estar no prontuário antes da 1ª dose (ASCO/ONS).
    confirmacao_pat = bool(data.get("confirmacao_patologica"))
    estadiamento_in = (data.get("estadiamento") or "").strip()[:12]
    intencao_in     = (data.get("intencao_tratamento") or "").strip()[:12]
    faltando_1a = _elementos_obrigatorios_primeira_dose(
        numero_ciclo, protocolo, confirmacao_pat, estadiamento_in, cid10, intencao_in)

    # Liberação médica quando inapto: registra quem assumiu e por quê (nunca
    # bloqueia — a decisão clínica continua do oncologista, como no resto do sistema).
    liberado_por = (data.get("aptidao_liberada_por") or "").strip()[:150]
    justificativa_apt = (data.get("aptidao_justificativa") or "").strip()

    with transaction.atomic():
        identidade = resolver_identidade(
            empresa, nome=paciente_nome, cpf=cpf_paciente,
        )
        ciclo = CicloQuimioterapia.objects.create(
            empresa=empresa,
            protocolo=protocolo,
            paciente_nome=paciente_nome,
            cpf_paciente=cpf_paciente,
            cns_paciente=data.get("cns_paciente", ""),
            identidade=identidade,
            cid10_principal=cid10,
            numero_ciclo=numero_ciclo,
            data_inicio=data_inicio,
            data_prevista=data_prevista,
            data_fim=data.get("data_fim"),
            medico_oncologista=data.get("medico_oncologista", ""),
            crm=data.get("crm", ""),
            peso_kg=peso,
            altura_cm=altura,
            sc_m2=sc_m2,
            doses_calculadas=doses,
            creatinina_mg_dl=_num_positivo(data.get("creatinina_mg_dl")),
            clearance_creatinina=_num_positivo(data.get("clearance_creatinina")),
            bilirrubina_mg_dl=_num_positivo(data.get("bilirrubina_mg_dl")),
            neutrofilos=neutrofilos_in,
            plaquetas=plaquetas_in,
            aptidao_status=aptidao_status,
            aptidao_bloqueios=aptidao_bloqueios,
            aptidao_liberada_por=liberado_por,
            aptidao_justificativa=justificativa_apt,
            auc_alvo=auc_alvo,
            confirmacao_patologica=confirmacao_pat,
            estadiamento=estadiamento_in,
            intencao_tratamento=intencao_in,
            guia=guia,
            obs=data.get("obs", ""),
        )
        if guia is not None:
            guia.ciclos_utilizados = guia.ciclos.count()
            guia.save(update_fields=["ciclos_utilizados"])
            _sync_status_guia(guia)
    caps = [d["droga"] for d in doses if d.get("cap_aplicado")]
    alertas_aptidao = []
    if aptidao_status == "inapto":
        alertas_aptidao.append(
            "🛑 Paciente INAPTO para este ciclo hoje: "
            + " ".join(aptidao_bloqueios)
            + (f" Liberado por {liberado_por}." if liberado_por else
               " Registre a liberação médica e a justificativa para prosseguir."))
    elif aptidao_status == "apto_ressalva":
        alertas_aptidao.append("⚠️ Apto com ressalva: " + " ".join(aptidao_bloqueios))
    elif aptidao_status == "nao_avaliado":
        alertas_aptidao.append("ℹ️ " + " ".join(aptidao_bloqueios))
    if faltando_1a:
        alertas_aptidao.append(
            "📋 Primeira dose do esquema sem: " + ", ".join(faltando_1a)
            + " (padrão ASCO/ONS para início de tratamento).")
    return JsonResponse({
        "id": ciclo.id,
        "sc_m2": sc_m2,
        "doses_calculadas": doses,
        "pre_medicacao": protocolo.drogas_suporte or [],
        "caps_aplicados": caps,
        "aptidao": {
            "status": aptidao_status,
            "bloqueios": aptidao_bloqueios,
            "liberada_por": liberado_por,
        },
        "elementos_faltando_1a_dose": faltando_1a,
        "alertas": alertas_aptidao + alertas_orgao + alertas_cum + alertas_guia,
    }, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_ciclo_detalhe(request, ciclo_id):
    """GET/PUT /api/hospital/oncologia/ciclos/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, _, ToxicidadeQuimio = _get_onco_models()
    try:
        ciclo = CicloQuimioterapia.objects.get(id=ciclo_id, empresa=empresa)
    except CicloQuimioterapia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "GET":
        toxs = ToxicidadeQuimio.objects.filter(ciclo=ciclo).order_by("-data_registro")
        return JsonResponse({
            "id": ciclo.id,
            "protocolo": {"id": ciclo.protocolo.id, "codigo": ciclo.protocolo.codigo,
                          "nome": ciclo.protocolo.nome, "drogas": ciclo.protocolo.drogas,
                          # A pré-medicação é metade da prescrição: sem ela a tela
                          # mostra o quimioterápico e esconde o antiemético.
                          "drogas_suporte": ciclo.protocolo.drogas_suporte or [],
                          "ciclos_total": ciclo.protocolo.ciclos_total},
            "paciente_nome": ciclo.paciente_nome,
            "cpf_paciente": ciclo.cpf_paciente,
            "cid10_principal": ciclo.cid10_principal,
            "numero_ciclo": ciclo.numero_ciclo,
            "data_inicio": ciclo.data_inicio.isoformat(),
            "data_prevista": ciclo.data_prevista.isoformat() if ciclo.data_prevista else None,
            "data_fim": ciclo.data_fim.isoformat() if ciclo.data_fim else None,
            "status": ciclo.status,
            "status_display": ciclo.get_status_display(),
            "peso_kg": float(ciclo.peso_kg) if ciclo.peso_kg else None,
            "altura_cm": float(ciclo.altura_cm) if ciclo.altura_cm else None,
            "sc_m2": float(ciclo.sc_m2) if ciclo.sc_m2 else None,
            "doses_calculadas": ciclo.doses_calculadas or [],
            "creatinina_mg_dl": float(ciclo.creatinina_mg_dl) if ciclo.creatinina_mg_dl else None,
            "clearance_creatinina": float(ciclo.clearance_creatinina) if ciclo.clearance_creatinina else None,
            "bilirrubina_mg_dl": float(ciclo.bilirrubina_mg_dl) if ciclo.bilirrubina_mg_dl else None,
            "neutrofilos": ciclo.neutrofilos,
            "plaquetas": ciclo.plaquetas,
            "aptidao_status": ciclo.aptidao_status,
            "aptidao_status_display": ciclo.get_aptidao_status_display(),
            "aptidao_bloqueios": ciclo.aptidao_bloqueios,
            "aptidao_liberada_por": ciclo.aptidao_liberada_por,
            "aptidao_justificativa": ciclo.aptidao_justificativa,
            "auc_alvo": float(ciclo.auc_alvo) if ciclo.auc_alvo else None,
            "confirmacao_patologica": ciclo.confirmacao_patologica,
            "estadiamento": ciclo.estadiamento,
            "intencao_tratamento": ciclo.intencao_tratamento,
            "medico_oncologista": ciclo.medico_oncologista,
            "obs": ciclo.obs,
            "toxicidades": [
                {
                    "id": t.id,
                    "categoria": t.categoria,
                    "grau": t.grau,
                    "grau_display": t.get_grau_display(),
                    "data_registro": t.data_registro.isoformat(),
                    "conduta": t.conduta,
                    "dose_reduzida": t.dose_reduzida,
                    "ciclo_suspenso": t.ciclo_suspenso,
                }
                for t in toxs
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    # Transição de status validada (impede status arbitrário via PUT).
    if "status" in data and data["status"] != ciclo.status:
        novo = data["status"]
        permitidos = TRANSICOES_CICLO.get(ciclo.status, set())
        if novo not in permitidos:
            return JsonResponse({
                "erro": f"Transição inválida: '{ciclo.get_status_display()}' → '{novo}'.",
                "status_atual": ciclo.status,
                "transicoes_validas": sorted(permitidos),
            }, status=409)
        # Adiar exige motivo estruturado.
        if novo == "suspenso":
            motivo = (data.get("motivo_adiamento") or "").strip()
            if motivo not in ("clinico", "administrativo", "logistico"):
                return JsonResponse(
                    {"erro": "Adiamento exige motivo: clinico, administrativo ou logistico."},
                    status=400)
            ciclo.motivo_adiamento = motivo
        ciclo.status = novo

    if "data_fim" in data:
        ciclo.data_fim = data["data_fim"] or None
    if "obs" in data:
        ciclo.obs = data["obs"]
    ciclo.save()
    return JsonResponse({"ok": True, "status": ciclo.status})


# ── Toxicidade ─────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_toxicidade(request, ciclo_id):
    """GET/POST /api/hospital/oncologia/ciclos/<id>/toxicidade/ — toxicidade CTCAE."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, _, ToxicidadeQuimio = _get_onco_models()
    try:
        ciclo = CicloQuimioterapia.objects.get(id=ciclo_id, empresa=empresa)
    except CicloQuimioterapia.DoesNotExist:
        return JsonResponse({"erro": "Ciclo não encontrado"}, status=404)

    if request.method == "GET":
        # Expõe o vocabulário CTCAE para a UI montar o select.
        return JsonResponse({"categorias_ctcae": CTCAE_CATEGORIAS})

    data, erro = _parse_json(request)
    if erro:
        return erro

    categoria = (data.get("categoria") or "").strip()
    if not categoria:
        return JsonResponse({"erro": "Categoria CTCAE é obrigatória"}, status=400)

    try:
        grau = int(data.get("grau"))
    except (TypeError, ValueError):
        return JsonResponse({"erro": "Grau deve ser um número de 1 a 5"}, status=400)
    if grau not in GRAUS_CTCAE_VALIDOS:
        return JsonResponse({"erro": "Grau CTCAE deve estar entre 1 e 5"}, status=400)

    data_reg = data.get("data_registro") or date.today().isoformat()

    with transaction.atomic():
        tox = ToxicidadeQuimio.objects.create(
            empresa=empresa,
            ciclo=ciclo,
            categoria=categoria,
            grau=grau,
            data_registro=data_reg,
            conduta=data.get("conduta", ""),
            dose_reduzida=bool(data.get("dose_reduzida", False)),
            ciclo_suspenso=bool(data.get("ciclo_suspenso", False)),
        )
        # Suspende o ciclo se marcado como suspenso por toxicidade.
        if tox.ciclo_suspenso and ciclo.status in ("agendado", "em_curso"):
            ciclo.status = "suspenso"
            ciclo.motivo_adiamento = "clinico"
            ciclo.save(update_fields=["status", "motivo_adiamento"])

    alerta = None
    if grau >= 3:
        alerta = (f"⚠️ Toxicidade CTCAE Grau {grau} — {categoria} — "
                  f"avalie suspensão/redução de dose no próximo ciclo")

    return JsonResponse({"id": tox.id, "alerta": alerta}, status=201)


# ── APACs ──────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_apacs(request):
    """GET/POST /api/hospital/oncologia/apacs/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, APACOncologia, _ = _get_onco_models()

    if request.method == "GET":
        qs = APACOncologia.objects.filter(empresa=empresa)
        status_f     = request.GET.get("status")
        competencia_f = request.GET.get("competencia")
        q            = request.GET.get("q")

        if status_f:
            qs = qs.filter(status=status_f)
        if competencia_f:
            qs = qs.filter(competencia=competencia_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(numero_apac__icontains=q)
                           | Q(cns_paciente=q))

        total = qs.count()
        try:
            limite = max(1, min(int(request.GET.get("limit", 100)), 500))
        except (TypeError, ValueError):
            limite = 100
        try:
            offset = max(0, int(request.GET.get("offset", 0)))
        except (TypeError, ValueError):
            offset = 0
        return JsonResponse({
            "total": total,
            "offset": offset,
            "limite": limite,
            "valor_total_solicitado": float(
                qs.filter(status__in=["submetida", "aprovada"])
                  .aggregate(v=Sum("valor_solicitado"))["v"] or 0
            ),
            "valor_total_aprovado": float(
                qs.filter(status="aprovada")
                  .aggregate(v=Sum("valor_aprovado"))["v"] or 0
            ),
            "apacs": [
                {
                    "id": a.id,
                    "numero_apac": a.numero_apac,
                    "paciente_nome": a.paciente_nome,
                    "cid10_principal": a.cid10_principal,
                    "procedimento_principal": a.procedimento_principal,
                    "competencia": a.competencia,
                    "competencia_final": a.competencia_final,
                    "valor_solicitado": float(a.valor_solicitado) if a.valor_solicitado else None,
                    "valor_aprovado": float(a.valor_aprovado) if a.valor_aprovado else None,
                    "status": a.status,
                    "status_display": a.get_status_display(),
                }
                for a in qs.order_by("-competencia")[offset:offset + limite]
            ],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    paciente_nome = (data.get("paciente_nome") or "").strip()
    cid10 = (data.get("cid10_principal") or "").strip()
    if not paciente_nome or not cid10:
        return JsonResponse(
            {"erro": "Nome do paciente e CID-10 principal são obrigatórios"}, status=400)

    competencia = str(data.get("competencia") or date.today().strftime("%Y%m")).strip()
    if not (competencia.isdigit() and len(competencia) == 6):
        return JsonResponse(
            {"erro": "Competência deve estar no formato AAAAMM (ex.: 202608)"}, status=400)
    mes = int(competencia[4:6])
    if not (1 <= mes <= 12):
        return JsonResponse({"erro": "Mês da competência inválido (01-12)"}, status=400)

    # APAC vale por até 3 competências — calcula a competência final.
    ano_i, mes_i = int(competencia[:4]), mes
    total_meses = (ano_i * 12 + (mes_i - 1)) + 2
    competencia_final = f"{total_meses // 12:04d}{(total_meses % 12) + 1:02d}"

    # Valida que o ciclo referenciado pertence a ESTA empresa antes de vincular —
    # senão a APAC poderia apontar para um ciclo de outro tenant (ciclo_id vinha
    # cru do payload, sem checagem de posse).
    ciclo_ref = None
    ciclo_id = data.get("ciclo_id")
    if ciclo_id:
        ciclo_ref = CicloQuimioterapia.objects.filter(id=ciclo_id, empresa=empresa).first()
        if ciclo_ref is None:
            return JsonResponse({"erro": "Ciclo de quimioterapia não encontrado para esta empresa"}, status=400)

    ok_cpf, erro_cpf = validar_cpf_cadastro(data.get("cpf_paciente", ""), empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)

    with transaction.atomic():
        identidade = resolver_identidade(
            empresa, nome=paciente_nome, cpf=data.get("cpf_paciente", ""),
        )
        apac = APACOncologia.objects.create(
            empresa=empresa,
            numero_apac=data.get("numero_apac", ""),
            paciente_nome=paciente_nome,
            cpf_paciente=data.get("cpf_paciente", ""),
            cns_paciente=data.get("cns_paciente", ""),
            identidade=identidade,
            cid10_principal=cid10,
            cid10_secundario=data.get("cid10_secundario", ""),
            procedimento_principal=data.get("procedimento_principal", ""),
            ciclo_referencia=ciclo_ref,
            competencia=competencia,
            competencia_final=competencia_final,
            cnes_solicitante=data.get("cnes_solicitante", ""),
            cnes_executante=data.get("cnes_executante", ""),
            carater_atendimento=data.get("carater_atendimento", "1"),
            data_solicitacao=data.get("data_solicitacao") or date.today().isoformat(),
            valor_solicitado=data.get("valor_solicitado"),
        )
        # Número interno de controle quando não informado (rastreável, único por PK).
        if not apac.numero_apac:
            apac.numero_apac = f"APAC-{competencia}-{apac.pk:06d}"
            apac.save(update_fields=["numero_apac"])
    return JsonResponse({"id": apac.id, "numero_apac": apac.numero_apac}, status=201)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_apac_detalhe(request, apac_id):
    """GET/PUT /api/hospital/oncologia/apacs/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, _, APACOncologia, _ = _get_onco_models()
    try:
        apac = APACOncologia.objects.get(id=apac_id, empresa=empresa)
    except APACOncologia.DoesNotExist:
        return JsonResponse({"erro": "Não encontrada"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "id": apac.id,
            "numero_apac": apac.numero_apac,
            "paciente_nome": apac.paciente_nome,
            "cpf_paciente": apac.cpf_paciente,
            "cns_paciente": apac.cns_paciente,
            "cid10_principal": apac.cid10_principal,
            "cid10_secundario": apac.cid10_secundario,
            "procedimento_principal": apac.procedimento_principal,
            "competencia": apac.competencia,
            "competencia_final": apac.competencia_final,
            "cnes_solicitante": apac.cnes_solicitante,
            "cnes_executante": apac.cnes_executante,
            "carater_atendimento": apac.carater_atendimento,
            "carater_display": apac.get_carater_atendimento_display(),
            "data_solicitacao": apac.data_solicitacao.isoformat() if apac.data_solicitacao else None,
            "data_autorizacao": apac.data_autorizacao.isoformat() if apac.data_autorizacao else None,
            "autorizador_nome": apac.autorizador_nome,
            "valor_solicitado": float(apac.valor_solicitado) if apac.valor_solicitado else None,
            "valor_aprovado": float(apac.valor_aprovado) if apac.valor_aprovado else None,
            "status": apac.status,
            "status_display": apac.get_status_display(),
            "motivo_glosa": apac.motivo_glosa,
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    # Transição de status validada.
    if "status" in data and data["status"] != apac.status:
        novo = data["status"]
        permitidos = TRANSICOES_APAC.get(apac.status, set())
        if novo not in permitidos:
            return JsonResponse({
                "erro": f"Transição inválida: '{apac.get_status_display()}' → '{novo}'.",
                "status_atual": apac.status,
                "transicoes_validas": sorted(permitidos),
            }, status=409)
        if novo == "glosada" and not (data.get("motivo_glosa") or apac.motivo_glosa).strip():
            return JsonResponse({"erro": "Glosa exige o motivo."}, status=400)
        apac.status = novo
        # Ao aprovar, carimba a data de autorização (compliance SIA-SUS).
        if novo == "aprovada" and not apac.data_autorizacao:
            apac.data_autorizacao = date.today()

    # Valor aprovado não pode exceder o solicitado.
    if "valor_aprovado" in data and data["valor_aprovado"] not in (None, ""):
        try:
            va = float(data["valor_aprovado"])
        except (TypeError, ValueError):
            return JsonResponse({"erro": "Valor aprovado inválido"}, status=400)
        if va < 0:
            return JsonResponse({"erro": "Valor aprovado não pode ser negativo"}, status=400)
        if apac.valor_solicitado and va > float(apac.valor_solicitado):
            return JsonResponse(
                {"erro": f"Valor aprovado (R$ {va}) excede o solicitado "
                         f"(R$ {apac.valor_solicitado})."}, status=400)
        apac.valor_aprovado = va

    for c in ("numero_apac", "motivo_glosa", "procedimento_principal",
              "cnes_solicitante", "cnes_executante", "carater_atendimento",
              "autorizador_nome"):
        if c in data:
            setattr(apac, c, data[c])
    apac.save()
    return JsonResponse({"ok": True, "status": apac.status})


# ── KPIs ───────────────────────────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_kpis(request):
    """GET /api/hospital/oncologia/kpis/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, CicloQuimioterapia, APACOncologia, ToxicidadeQuimio = _get_onco_models()

    hoje    = date.today()
    mes_ini = hoje.replace(day=1)
    # início do mês seguinte, para limitar a janela superior do KPI mensal
    mes_fim = (mes_ini + timedelta(days=32)).replace(day=1)
    comp    = hoje.strftime("%Y%m")

    ciclos_ativos = CicloQuimioterapia.objects.filter(
        empresa=empresa, status__in=["agendado", "em_curso"]
    ).count()
    por_status = dict(
        CicloQuimioterapia.objects.filter(empresa=empresa)
        .values_list("status").annotate(n=Count("id")).order_by()
    )
    # Ciclos atrasados: data prevista passou e ainda não concluídos/cancelados.
    ciclos_atrasados = CicloQuimioterapia.objects.filter(
        empresa=empresa, data_prevista__lt=hoje,
        status__in=["agendado", "em_curso"],
    ).count()
    tox_graves_mes = ToxicidadeQuimio.objects.filter(
        empresa=empresa,
        grau__gte=3,
        data_registro__gte=mes_ini,
        data_registro__lt=mes_fim,
    ).count()

    apac_mes    = APACOncologia.objects.filter(empresa=empresa, competencia=comp)
    apac_glosa  = apac_mes.filter(status="glosada").count()
    val_aprovado = float(
        apac_mes.filter(status="aprovada")
                .aggregate(v=Sum("valor_aprovado"))["v"] or 0
    )

    # Guias vencendo (≤30 dias) e vencidas — alerta de vencimento de guia.
    from .models import GuiaOncologica
    guias_ativas = GuiaOncologica.objects.filter(empresa=empresa).exclude(status="cancelada")
    limite_guia = hoje + timedelta(days=30)
    guias_vencidas = 0
    guias_vencendo = 0
    prazo_estourado = prazo_limite = aguardando = 0
    for g in guias_ativas:
        _sync_status_guia(g)
        if g.status == "vencida":
            guias_vencidas += 1
        elif g.status == "vigente" and g.data_validade <= limite_guia:
            guias_vencendo += 1
        p = _prazo_resposta_guia(g, hoje)
        if p["aplicavel"] and not p["respondida"]:
            aguardando += 1
            if p["estourado"]:
                prazo_estourado += 1
            elif p["dias_uteis_restantes"] <= 1:
                prazo_limite += 1

    # Cadeia fechada: o que está parado na farmácia e o que deu errado na veia.
    from .models import (AgendamentoInfusao, PreparoQuimioterapia,
                         AdministracaoQuimioterapia)
    inicio_mes = hoje.replace(day=1)
    fila_farmacia = PreparoQuimioterapia.objects.filter(
        empresa=empresa, status__in=("pendente", "em_preparo", "pronto")).count()
    preparos_aguardando_conferencia = PreparoQuimioterapia.objects.filter(
        empresa=empresa, status="pronto").count()
    intercorrencias_mes = AdministracaoQuimioterapia.objects.filter(
        empresa=empresa, inicio__date__gte=inicio_mes).exclude(
        intercorrencia="nenhuma").count()
    extravasamentos_mes = AdministracaoQuimioterapia.objects.filter(
        empresa=empresa, inicio__date__gte=inicio_mes,
        intercorrencia="extravasamento").count()
    infusoes_hoje = AgendamentoInfusao.objects.filter(
        empresa=empresa, data=hoje).exclude(
        status__in=("cancelado", "faltou")).count()

    return JsonResponse({
        "ciclos_ativos": ciclos_ativos,
        "ciclos_por_status": por_status,
        "fila_farmacia": fila_farmacia,
        "preparos_aguardando_conferencia": preparos_aguardando_conferencia,
        "intercorrencias_mes": intercorrencias_mes,
        "extravasamentos_mes": extravasamentos_mes,
        "infusoes_agendadas_hoje": infusoes_hoje,
        "ciclos_atrasados": ciclos_atrasados,
        "toxicidades_grau3_mais_mes": tox_graves_mes,
        "apac_glosas_mes": apac_glosa,
        "valor_aprovado_mes": val_aprovado,
        "guias_vencendo_30d": guias_vencendo,
        "guias_vencidas": guias_vencidas,
        "autorizacoes_prazo_estourado": prazo_estourado,
        "autorizacoes_no_limite_prazo": prazo_limite,
        "autorizacoes_aguardando_resposta": aguardando,
    })


# ── Jornada Oncológica Unificada ────────────────────────────────────────────────

@require_http_methods(["GET"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_jornada(request):
    """GET /api/hospital/oncologia/jornada/?cpf=...  (ou ?identidade_id=...)

    Linha do tempo única do paciente oncológico cruzando quimioterapia,
    radioterapia, RHC e APAC pela identidade única (MPI). Responde ao desafio
    "visão única da jornada, da guia ao desfecho".
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import (
        IdentidadePaciente, SessaoRadioterapia, RegistroHospitalarCancer,
    )
    _, CicloQuimioterapia, APACOncologia, _ = _get_onco_models()

    cpf = "".join(filter(str.isdigit, request.GET.get("cpf", "")))[:11]
    identidade_id = request.GET.get("identidade_id")
    nome_q = (request.GET.get("nome") or "").strip()

    # Resolve a identidade do paciente
    identidade = None
    if identidade_id:
        identidade = IdentidadePaciente.objects.filter(
            empresa=empresa, id=identidade_id).first()
    elif cpf:
        identidade = IdentidadePaciente.objects.filter(
            empresa=empresa, cpf=cpf).order_by("-id").first()
    elif nome_q:
        identidade = IdentidadePaciente.objects.filter(
            empresa=empresa, nome__iexact=nome_q).order_by("-id").first()

    if not identidade and not cpf and not nome_q:
        return JsonResponse(
            {"erro": "Informe cpf, identidade_id ou nome do paciente"}, status=400)

    # Filtros: prioriza identidade (MPI); cai para CPF/nome como rede de segurança
    # para registros ainda não vinculados ao MPI.
    def _filtro(model, tem_cpf=True):
        if identidade:
            q = Q(identidade=identidade)
            if cpf and tem_cpf:
                q |= Q(cpf_paciente=cpf)
            return model.objects.filter(empresa=empresa).filter(q)
        if cpf and tem_cpf:
            return model.objects.filter(empresa=empresa, cpf_paciente=cpf)
        # Último recurso, busca só por nome. Os modelos desta jornada divergem no
        # nome do campo (RHC usa `nome_paciente`; ciclo, APAC, resposta e oral usam
        # `paciente_nome`), então fixar um só derruba a busca por nome com 500.
        campos = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
        campo_nome = "nome_paciente" if "nome_paciente" in campos else "paciente_nome"
        return model.objects.filter(empresa=empresa,
                                    **{f"{campo_nome}__iexact": nome_q})

    eventos = []

    # Quimioterapia
    for c in _filtro(CicloQuimioterapia).select_related("protocolo"):
        eventos.append({
            "tipo": "quimioterapia",
            "data": c.data_inicio.isoformat(),
            "titulo": f"Ciclo {c.numero_ciclo}"
                      + (f"/{c.protocolo.ciclos_total}" if c.protocolo.ciclos_total else "")
                      + f" — {c.protocolo.codigo}",
            "status": c.get_status_display(),
            "detalhe": {
                "id": c.id, "cid10": c.cid10_principal,
                "sc_m2": float(c.sc_m2) if c.sc_m2 else None,
                "data_prevista": c.data_prevista.isoformat() if c.data_prevista else None,
            },
        })

    # Administração à beira do leito — o que de fato entrou na veia. Liga-se ao
    # paciente pelo ciclo, não por CPF próprio, por isso fica fora de _filtro().
    from .models import AdministracaoQuimioterapia
    ciclos_ids = list(_filtro(CicloQuimioterapia).values_list("id", flat=True))
    if ciclos_ids:
        for adm in AdministracaoQuimioterapia.objects.filter(
                empresa=empresa, ciclo_id__in=ciclos_ids).select_related("preparo"):
            local = timezone.localtime(adm.inicio)
            eventos.append({
                "tipo": "administracao",
                "data": local.date().isoformat(),
                "titulo": f"{adm.preparo.droga} administrado"
                          + (f" ({adm.get_via_display()})" if adm.via else ""),
                "status": (adm.get_intercorrencia_display()
                           if adm.intercorrencia != "nenhuma" else "Sem intercorrência"),
                "detalhe": {
                    "id": adm.id, "ciclo_id": adm.ciclo_id,
                    "hora": local.strftime("%H:%M"),
                    "dose": float(adm.dose_administrada) if adm.dose_administrada is not None else None,
                    "unidade": adm.preparo.unidade,
                    "administrado_por": adm.administrado_por,
                    "checado_por": adm.checado_por,
                    "intercorrencia": adm.intercorrencia,
                    "conduta": adm.intercorrencia_conduta,
                    "lote": adm.preparo.lote,
                },
            })

    # Quimioterapia oral — o tratamento que acontece fora do hospital e que,
    # sem isto, não deixa rastro nenhum na linha do tempo do paciente.
    from .models import PrescricaoQuimioOral
    for po in _filtro(PrescricaoQuimioOral).prefetch_related("dispensacoes"):
        info = _prescricao_oral_dict(po)
        eventos.append({
            "tipo": "quimio_oral",
            "data": po.data_inicio.isoformat(),
            "titulo": f"{po.droga} por via oral — {info['esquema']}",
            "status": po.get_status_display(),
            "detalhe": {
                "id": po.id,
                "posologia": po.posologia,
                "adesao_media_pct": info["adesao_media_pct"],
                "adesao_baixa": info["adesao_baixa"],
                "retiradas": info["total_dispensacoes"],
                "retirada_atrasada": bool(info["retirada"].get("atrasado")),
            },
        })

    # Radioterapia
    for s in _filtro(SessaoRadioterapia):
        data_ref = s.data_inicio or (s.criado_em.date() if s.criado_em else None)
        eventos.append({
            "tipo": "radioterapia",
            "data": data_ref.isoformat() if data_ref else None,
            "titulo": f"Radioterapia {s.tecnica or ''} — {s.numero_fracoes_realizadas}/"
                      f"{s.numero_fracoes_total or '?'} frações",
            "status": s.get_status_display(),
            "detalhe": {
                "id": s.id, "cid": s.cid,
                "dose_prescrita_gy": float(s.dose_prescrita_gy) if s.dose_prescrita_gy else None,
            },
        })

    # RHC (marco de registro/diagnóstico)
    for r in _filtro(RegistroHospitalarCancer):
        eventos.append({
            "tipo": "rhc",
            "data": (r.data_diagnostico or r.data_primeiro_atendimento).isoformat(),
            "titulo": f"RHC — {r.cid_topografia} (Estádio {r.estadiamento})",
            "status": r.get_status_paciente_display(),
            "detalhe": {"id": r.id, "estadiamento": r.estadiamento,
                        "notificado_inca": r.notificado_inca},
        })

    # APAC (faturamento)
    for a in _filtro(APACOncologia):
        eventos.append({
            "tipo": "apac",
            "data": f"{a.competencia[:4]}-{a.competencia[4:6]}-01" if len(a.competencia) == 6 else None,
            "titulo": f"APAC {a.numero_apac or ''} — {a.procedimento_principal or 's/ proc'}",
            "status": a.get_status_display(),
            "detalhe": {
                "id": a.id, "competencia": a.competencia,
                "valor_solicitado": float(a.valor_solicitado) if a.valor_solicitado else None,
                "valor_aprovado": float(a.valor_aprovado) if a.valor_aprovado else None,
            },
        })

    # Desfecho: é o que fecha a frase "da guia ao desfecho clínico".
    from .models import AvaliacaoRespostaOncologica
    for a in _filtro(AvaliacaoRespostaOncologica):
        eventos.append({
            "tipo": "resposta",
            "data": a.data_avaliacao.isoformat(),
            "titulo": ("Avaliação basal (antes do tratamento)" if a.basal
                       else f"Resposta: {a.get_resposta_display()}"),
            "status": a.get_resposta_display(),
            "detalhe": {
                "id": a.id,
                "metodo": a.get_metodo_display(),
                "basal": a.basal,
                "soma_lesoes_mm": (float(a.soma_lesoes_mm)
                                   if a.soma_lesoes_mm is not None else None),
                "variacao_vs_basal_pct": (float(a.variacao_vs_basal_pct)
                                          if a.variacao_vs_basal_pct is not None else None),
                "lesoes_novas": a.lesoes_novas,
                "automatica": a.resposta_automatica,
            },
        })

    # Ordena a linha do tempo (eventos sem data vão para o fim)
    eventos.sort(key=lambda e: (e["data"] is None, e["data"] or ""))

    return JsonResponse({
        "paciente": {
            "identidade_id": identidade.id if identidade else None,
            "nome": identidade.nome if identidade else (nome_q or None),
            "cpf": identidade.cpf if identidade else (cpf or None),
            "cns": identidade.cns if identidade else None,
        },
        "resumo": {
            "quimioterapia": sum(1 for e in eventos if e["tipo"] == "quimioterapia"),
            "radioterapia": sum(1 for e in eventos if e["tipo"] == "radioterapia"),
            "rhc": sum(1 for e in eventos if e["tipo"] == "rhc"),
            "apac": sum(1 for e in eventos if e["tipo"] == "apac"),
            "administracao": sum(1 for e in eventos if e["tipo"] == "administracao"),
            "quimio_oral": sum(1 for e in eventos if e["tipo"] == "quimio_oral"),
            "resposta": sum(1 for e in eventos if e["tipo"] == "resposta"),
        },
        # Desfecho mais recente do paciente (ignora a basal, que é ponto de partida).
        "desfecho_atual": next(
            (e["status"] for e in reversed(eventos)
             if e["tipo"] == "resposta" and not e["detalhe"].get("basal")), None),
        "total_eventos": len(eventos),
        "timeline": eventos,
    })


# ── Resposta ao tratamento ─────────────────────────────────────────────────────

def _resposta_dict(a):
    return {
        "id": a.id,
        "paciente_nome": a.paciente_nome,
        "cpf_paciente": a.cpf_paciente,
        "ciclo_id": a.ciclo_id,
        "data_avaliacao": a.data_avaliacao.isoformat(),
        "metodo": a.metodo,
        "metodo_display": a.get_metodo_display(),
        "basal": a.basal,
        "soma_lesoes_mm": float(a.soma_lesoes_mm) if a.soma_lesoes_mm is not None else None,
        "lesoes_novas": a.lesoes_novas,
        "desaparecimento_total": a.desaparecimento_total,
        "resposta": a.resposta,
        "resposta_display": a.get_resposta_display(),
        "resposta_automatica": a.resposta_automatica,
        "variacao_vs_basal_pct": (float(a.variacao_vs_basal_pct)
                                  if a.variacao_vs_basal_pct is not None else None),
        "variacao_vs_nadir_pct": (float(a.variacao_vs_nadir_pct)
                                  if a.variacao_vs_nadir_pct is not None else None),
        "avaliador": a.avaliador,
        "justificativa": a.justificativa,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_respostas(request):
    """GET/POST /api/hospital/oncologia/respostas/ — avaliação RECIST 1.1."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import AvaliacaoRespostaOncologica, CicloQuimioterapia

    if request.method == "GET":
        qs = AvaliacaoRespostaOncologica.objects.filter(empresa=empresa)
        cpf = "".join(filter(str.isdigit, request.GET.get("cpf", "")))[:11]
        if cpf:
            qs = qs.filter(cpf_paciente=cpf)
        resposta_f = request.GET.get("resposta")
        if resposta_f:
            qs = qs.filter(resposta=resposta_f)
        itens = list(qs.order_by("-data_avaliacao")[:300])
        return JsonResponse({"total": qs.count(),
                             "avaliacoes": [_resposta_dict(a) for a in itens]})

    data, erro = _parse_json(request)
    if erro:
        return erro

    paciente = (data.get("paciente_nome") or "").strip()
    if not paciente:
        return JsonResponse({"erro": "Nome do paciente é obrigatório"}, status=400)
    try:
        d_aval = datetime.strptime(
            str(data.get("data_avaliacao") or date.today().isoformat())[:10],
            "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"erro": "data_avaliacao inválida (use AAAA-MM-DD)"}, status=400)

    cpf_raw = data.get("cpf_paciente", "")
    ok_cpf, erro_cpf = validar_cpf_cadastro(cpf_raw, empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    cpf = "".join(filter(str.isdigit, cpf_raw))[:11]

    metodo = (data.get("metodo") or "tc").strip()
    if metodo not in dict(AvaliacaoRespostaOncologica.METODO):
        return JsonResponse(
            {"erro": "metodo inválido",
             "validos": [m[0] for m in AvaliacaoRespostaOncologica.METODO]}, status=400)

    soma = data.get("soma_lesoes_mm")
    if soma not in (None, ""):
        soma = _num_positivo(soma)
        if soma is None:
            return JsonResponse(
                {"erro": "soma_lesoes_mm deve ser um número ≥ 0"}, status=400)
    else:
        soma = None

    ciclo = None
    if data.get("ciclo_id"):
        ciclo = CicloQuimioterapia.objects.filter(
            id=data["ciclo_id"], empresa=empresa).first()
        if ciclo is None:
            return JsonResponse({"erro": "Ciclo não encontrado nesta empresa"}, status=400)

    eh_basal = bool(data.get("basal"))
    lesoes_novas = bool(data.get("lesoes_novas"))
    sumiu_tudo = bool(data.get("desaparecimento_total"))

    if eh_basal:
        # A basal é o ponto de partida: não se classifica contra si mesma.
        resposta, var_basal, var_nadir = "ne", None, None
    else:
        basal, nadir = _historico_resposta(
            empresa, cpf, paciente, AvaliacaoRespostaOncologica)
        if basal is None:
            return JsonResponse(
                {"erro": "Não há avaliação basal para este paciente. Registre a basal "
                         "antes de classificar a resposta.",
                 "codigo": "sem_basal"}, status=400)
        resposta, var_basal, var_nadir = _classificar_recist(
            soma, basal, nadir, lesoes_novas, sumiu_tudo)

    # Sobrescrita médica: o avaliador pode discordar da régua, mas tem de dizer
    # por quê — e fica registrado que a classificação não foi a automática.
    resposta_manual = (data.get("resposta") or "").strip()
    automatica = True
    if resposta_manual and resposta_manual != resposta:
        if resposta_manual not in dict(AvaliacaoRespostaOncologica.RESPOSTA):
            return JsonResponse(
                {"erro": "resposta inválida",
                 "validos": [r[0] for r in AvaliacaoRespostaOncologica.RESPOSTA]}, status=400)
        if not (data.get("justificativa") or "").strip():
            return JsonResponse(
                {"erro": "Para classificar diferente do RECIST calculado, informe a "
                         "justificativa clínica.",
                 "codigo": "override_sem_justificativa",
                 "resposta_calculada": resposta}, status=400)
        resposta = resposta_manual
        automatica = False

    identidade = resolver_identidade(empresa, nome=paciente, cpf=cpf_raw)
    a = AvaliacaoRespostaOncologica.objects.create(
        empresa=empresa, paciente_nome=paciente, cpf_paciente=cpf,
        identidade=identidade, ciclo=ciclo, data_avaliacao=d_aval, metodo=metodo,
        basal=eh_basal, soma_lesoes_mm=soma, lesoes_novas=lesoes_novas,
        desaparecimento_total=sumiu_tudo, resposta=resposta,
        resposta_automatica=automatica,
        variacao_vs_basal_pct=var_basal, variacao_vs_nadir_pct=var_nadir,
        justificativa=(data.get("justificativa") or "").strip(),
        avaliador=(data.get("avaliador") or "").strip()[:150])
    return JsonResponse({"id": a.id, "avaliacao": _resposta_dict(a)}, status=201)


# ── Guias oncológicas (autorização + alerta de vencimento) ──────────────────────

def _guia_dict(g):
    return {
        "id": g.id,
        "numero_guia": g.numero_guia,
        "paciente_nome": g.paciente_nome,
        "cpf_paciente": g.cpf_paciente,
        "tipo": g.tipo,
        "tipo_display": g.get_tipo_display(),
        "operadora": g.operadora,
        "data_emissao": g.data_emissao.isoformat(),
        "data_validade": g.data_validade.isoformat(),
        "dias_para_vencer": g.dias_para_vencer(),
        "ciclos_autorizados": g.ciclos_autorizados,
        "ciclos_utilizados": g.ciclos_utilizados,
        "status": g.status,
        "status_display": g.get_status_display(),
        "motivo_negativa": g.motivo_negativa,
        "motivo_negativa_display": g.get_motivo_negativa_display() if g.motivo_negativa else "",
        "motivo_negativa_detalhe": g.motivo_negativa_detalhe,
        "prazo_resposta": _prazo_resposta_guia(g),
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_guias(request):
    """GET/POST /api/hospital/oncologia/guias/ — guias com alerta de vencimento."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import GuiaOncologica

    if request.method == "GET":
        qs = GuiaOncologica.objects.filter(empresa=empresa)
        status_f = request.GET.get("status")
        q = request.GET.get("q")
        if status_f:
            qs = qs.filter(status=status_f)
        if q:
            qs = qs.filter(Q(paciente_nome__icontains=q) | Q(numero_guia__icontains=q)
                           | Q(cpf_paciente="".join(filter(str.isdigit, q))))
        guias = list(qs.order_by("data_validade")[:300])
        for g in guias:  # mantém status coerente com validade/consumo
            _sync_status_guia(g)
        return JsonResponse({"total": qs.count(), "guias": [_guia_dict(g) for g in guias]})

    data, erro = _parse_json(request)
    if erro:
        return erro
    numero = (data.get("numero_guia") or "").strip()
    paciente = (data.get("paciente_nome") or "").strip()
    emissao = data.get("data_emissao")
    validade = data.get("data_validade")
    if not numero or not paciente or not emissao or not validade:
        return JsonResponse(
            {"erro": "Número da guia, paciente, data de emissão e validade são obrigatórios"},
            status=400)
    try:
        d_em = datetime.strptime(str(emissao)[:10], "%Y-%m-%d").date()
        d_val = datetime.strptime(str(validade)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"erro": "Datas inválidas (use AAAA-MM-DD)"}, status=400)
    if d_val < d_em:
        return JsonResponse({"erro": "Validade não pode ser anterior à emissão"}, status=400)

    cpf = data.get("cpf_paciente", "")
    ok_cpf, erro_cpf = validar_cpf_cadastro(cpf, empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)

    ident = resolver_identidade(empresa, nome=paciente, cpf=cpf, cns=data.get("cns_paciente", ""))
    guia = GuiaOncologica.objects.create(
        empresa=empresa, numero_guia=numero, paciente_nome=paciente,
        cpf_paciente=cpf, cns_paciente=data.get("cns_paciente", ""), identidade=ident,
        tipo=data.get("tipo", "quimioterapia"), operadora=data.get("operadora", ""),
        data_emissao=d_em, data_validade=d_val,
        ciclos_autorizados=int(data.get("ciclos_autorizados", 0) or 0),
        obs=data.get("obs", ""))
    # Relógio regulatório: quando a solicitação entrou e, se já houve, a resposta.
    campos_prazo = []
    for campo in ("data_solicitacao", "data_resposta"):
        valor = data.get(campo)
        if valor:
            try:
                setattr(guia, campo,
                        datetime.strptime(str(valor)[:10], "%Y-%m-%d").date())
                campos_prazo.append(campo)
            except (ValueError, TypeError):
                return JsonResponse(
                    {"erro": f"{campo} inválida (use AAAA-MM-DD)"}, status=400)
    prazo_custom = data.get("prazo_resposta_dias_uteis")
    if prazo_custom not in (None, ""):
        try:
            guia.prazo_resposta_dias_uteis = max(1, min(int(prazo_custom), 60))
            campos_prazo.append("prazo_resposta_dias_uteis")
        except (TypeError, ValueError):
            return JsonResponse({"erro": "prazo_resposta_dias_uteis inválido"}, status=400)
    status_in = (data.get("status") or "").strip()
    if status_in in dict(GuiaOncologica.STATUS):
        guia.status = status_in
        campos_prazo.append("status")
    motivo = (data.get("motivo_negativa") or "").strip()
    if motivo:
        if motivo not in dict(GuiaOncologica.MOTIVO_NEGATIVA):
            return JsonResponse(
                {"erro": "motivo_negativa inválido",
                 "validos": [m[0] for m in GuiaOncologica.MOTIVO_NEGATIVA]}, status=400)
        guia.motivo_negativa = motivo
        guia.motivo_negativa_detalhe = (data.get("motivo_negativa_detalhe") or "").strip()
        campos_prazo += ["motivo_negativa", "motivo_negativa_detalhe"]
    if campos_prazo:
        guia.save(update_fields=list(dict.fromkeys(campos_prazo)))
    _sync_status_guia(guia)
    return JsonResponse({"id": guia.id, "guia": _guia_dict(guia)}, status=201)


@require_http_methods(["GET"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_guias_alertas(request):
    """GET /api/hospital/oncologia/guias/alertas/?dias=30 — guias vencendo/vencidas."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    from .models import GuiaOncologica
    try:
        dias = max(1, min(int(request.GET.get("dias", 30)), 180))
    except (TypeError, ValueError):
        dias = 30
    hoje = date.today()
    limite = hoje + timedelta(days=dias)

    ativas = GuiaOncologica.objects.filter(
        empresa=empresa).exclude(status="cancelada")
    vencidas, vencendo = [], []
    prazo_estourado, prazo_vencendo = [], []
    for g in ativas:
        _sync_status_guia(g)
        if g.status == "vencida":
            vencidas.append(_guia_dict(g))
        elif g.status == "vigente" and g.data_validade <= limite:
            vencendo.append(_guia_dict(g))
        # Relógio de resposta: só vale enquanto ninguém respondeu.
        p = _prazo_resposta_guia(g)
        if p["aplicavel"] and not p["respondida"]:
            if p["estourado"]:
                prazo_estourado.append(_guia_dict(g))
            elif p["dias_uteis_restantes"] <= 1:
                prazo_vencendo.append(_guia_dict(g))
    return JsonResponse({
        "janela_dias": dias,
        "total_vencidas": len(vencidas),
        "total_vencendo": len(vencendo),
        "vencidas": vencidas,
        "vencendo": sorted(vencendo, key=lambda x: x["dias_para_vencer"]),
        # Prazo regulatório de RESPOSTA (ANS RN 623/2024 — 5 dias úteis)
        "total_prazo_resposta_estourado": len(prazo_estourado),
        "total_prazo_resposta_no_limite": len(prazo_vencendo),
        "prazo_resposta_estourado": sorted(
            prazo_estourado,
            key=lambda x: -x["prazo_resposta"]["dias_uteis_decorridos"]),
        "prazo_resposta_no_limite": prazo_vencendo,
    })


# ── Cadeia fechada: agenda → preparo → administração ───────────────────────────
# Três elos que hoje vivem em papel e planilha. O ponto não é registrar cada um:
# é que um não acontece sem o anterior. Sem a cadeia, o sistema sabe que o ciclo
# foi "concluído" e não sabe o que entrou na veia do paciente, nem quem conferiu.

def _get_cadeia_models():
    from .models import (AgendamentoInfusao, PreparoQuimioterapia,
                         AdministracaoQuimioterapia)
    return AgendamentoInfusao, PreparoQuimioterapia, AdministracaoQuimioterapia


def _hhmm(valor):
    """Converte 'HH:MM' em time. Retorna None se inválido."""
    try:
        return datetime.strptime(str(valor)[:5], "%H:%M").time()
    except (ValueError, TypeError):
        return None


def _janela_minutos(hora, duracao_min):
    """Janela [início, fim) em minutos desde a meia-noite."""
    inicio = hora.hour * 60 + hora.minute
    return inicio, inicio + max(int(duracao_min or 0), 1)


def _ciclo_liberado_para_infusao(ciclo):
    """Um ciclo inapto só segue para preparo se alguém assumiu a liberação.

    Devolve (ok, motivo). É a trava que impede a farmácia de manipular droga
    para um paciente que o hemograma do dia reprovou.
    """
    if ciclo.aptidao_status == "inapto" and not ciclo.aptidao_liberada_por:
        return False, (
            "Ciclo marcado como INAPTO e sem liberação médica registrada. "
            + " ".join(ciclo.aptidao_bloqueios or [])
        )
    if ciclo.status in ("cancelado", "suspenso"):
        return False, f"Ciclo está '{ciclo.get_status_display()}'."
    return True, ""


def _agendamento_dict(a):
    fim_min = _janela_minutos(a.hora_inicio, a.duracao_min)[1]
    return {
        "id": a.id,
        "ciclo_id": a.ciclo_id,
        "paciente_nome": a.ciclo.paciente_nome,
        "protocolo": a.ciclo.protocolo.codigo,
        "numero_ciclo": a.ciclo.numero_ciclo,
        "data": a.data.isoformat(),
        "hora_inicio": a.hora_inicio.strftime("%H:%M"),
        "hora_fim_prevista": f"{(fim_min // 60) % 24:02d}:{fim_min % 60:02d}",
        "duracao_min": a.duracao_min,
        "cadeira": a.cadeira,
        "status": a.status,
        "status_display": a.get_status_display(),
        "agendado_por": a.agendado_por,
        "observacao": a.observacao,
        "aptidao_status": a.ciclo.aptidao_status,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_agenda_infusao(request):
    """GET/POST /api/hospital/oncologia/agenda-infusao/ — cadeiras da central."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgendamentoInfusao, _, _ = _get_cadeia_models()
    _, CicloQuimioterapia, _, _ = _get_onco_models()

    if request.method == "GET":
        qs = AgendamentoInfusao.objects.filter(empresa=empresa).select_related(
            "ciclo", "ciclo__protocolo")
        try:
            dia = datetime.strptime(
                str(request.GET.get("data") or date.today().isoformat())[:10],
                "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return JsonResponse({"erro": "data inválida (use AAAA-MM-DD)"}, status=400)
        qs = qs.filter(data=dia)
        cadeira = (request.GET.get("cadeira") or "").strip()
        if cadeira:
            qs = qs.filter(cadeira=cadeira)
        itens = list(qs.order_by("cadeira", "hora_inicio"))
        ocupacao = {}
        for a in itens:
            if a.status in ("cancelado", "faltou"):
                continue
            ocupacao[a.cadeira] = ocupacao.get(a.cadeira, 0) + a.duracao_min
        return JsonResponse({
            "data": dia.isoformat(),
            "total": len(itens),
            "agendamentos": [_agendamento_dict(a) for a in itens],
            # Minutos ocupados por cadeira no dia — é o que mostra se a central
            # está no limite antes de alguém ligar para o paciente.
            "ocupacao_min_por_cadeira": ocupacao,
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    ciclo = CicloQuimioterapia.objects.filter(
        id=data.get("ciclo_id"), empresa=empresa).first()
    if ciclo is None:
        return JsonResponse({"erro": "Ciclo não encontrado nesta empresa"}, status=400)

    try:
        dia = datetime.strptime(str(data.get("data") or "")[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"erro": "data é obrigatória (AAAA-MM-DD)"}, status=400)

    hora = _hhmm(data.get("hora_inicio"))
    if hora is None:
        return JsonResponse({"erro": "hora_inicio é obrigatória (HH:MM)"}, status=400)

    cadeira = (data.get("cadeira") or "").strip()[:40]
    if not cadeira:
        return JsonResponse({"erro": "cadeira é obrigatória"}, status=400)

    try:
        duracao = int(data.get("duracao_min") or 180)
    except (TypeError, ValueError):
        return JsonResponse({"erro": "duracao_min inválida"}, status=400)
    if not (15 <= duracao <= 1440):
        return JsonResponse(
            {"erro": "duracao_min deve estar entre 15 e 1440 minutos"}, status=400)

    ini_novo, fim_novo = _janela_minutos(hora, duracao)
    # Choque de cadeira: duas infusões no mesmo assento ao mesmo tempo é um erro
    # operacional que só aparece no dia se o sistema não checar agora.
    for a in AgendamentoInfusao.objects.filter(
            empresa=empresa, data=dia, cadeira=cadeira).exclude(
            status__in=("cancelado", "faltou")):
        ini, fim = _janela_minutos(a.hora_inicio, a.duracao_min)
        if ini_novo < fim and ini < fim_novo:
            return JsonResponse({
                "erro": f"Cadeira '{cadeira}' já ocupada das "
                        f"{a.hora_inicio.strftime('%H:%M')} por {a.duracao_min} min.",
                "codigo": "cadeira_ocupada",
                "conflito": _agendamento_dict(a),
            }, status=409)

    ag = AgendamentoInfusao.objects.create(
        empresa=empresa, ciclo=ciclo, data=dia, hora_inicio=hora,
        duracao_min=duracao, cadeira=cadeira,
        agendado_por=(data.get("agendado_por") or "").strip()[:150],
        observacao=(data.get("observacao") or "").strip())

    # Agendar não é liberar: avisa, mas não bloqueia — quem decide é o médico.
    ok_apt, motivo_apt = _ciclo_liberado_para_infusao(ciclo)
    return JsonResponse({
        "id": ag.id,
        "agendamento": _agendamento_dict(ag),
        "alerta_aptidao": None if ok_apt else motivo_apt,
    }, status=201)


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_agenda_infusao_detalhe(request, agendamento_id):
    """PUT/DELETE /api/hospital/oncologia/agenda-infusao/<id>/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    AgendamentoInfusao, _, _ = _get_cadeia_models()
    ag = AgendamentoInfusao.objects.filter(
        id=agendamento_id, empresa=empresa).select_related(
        "ciclo", "ciclo__protocolo").first()
    if ag is None:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    if request.method == "DELETE":
        ag.status = "cancelado"
        ag.save(update_fields=["status"])
        return JsonResponse({"ok": True, "agendamento": _agendamento_dict(ag)})

    data, erro = _parse_json(request)
    if erro:
        return erro

    novo = (data.get("status") or "").strip()
    if novo:
        validos = dict(AgendamentoInfusao.STATUS)
        if novo not in validos:
            return JsonResponse(
                {"erro": "status inválido", "validos": sorted(validos)}, status=400)
        ag.status = novo
    if "observacao" in data:
        ag.observacao = (data.get("observacao") or "").strip()
    ag.save(update_fields=["status", "observacao"])
    return JsonResponse({"ok": True, "agendamento": _agendamento_dict(ag)})


def _preparo_dict(p):
    adm = getattr(p, "administracao", None)
    return {
        "id": p.id,
        "ciclo_id": p.ciclo_id,
        "paciente_nome": p.ciclo.paciente_nome,
        "numero_ciclo": p.ciclo.numero_ciclo,
        "droga": p.droga,
        "dose_prescrita": float(p.dose_prescrita) if p.dose_prescrita is not None else None,
        "dose_preparada": float(p.dose_preparada) if p.dose_preparada is not None else None,
        "unidade": p.unidade,
        "lote": p.lote,
        "validade_lote": p.validade_lote.isoformat() if p.validade_lote else None,
        "diluente": p.diluente,
        "volume_final_ml": p.volume_final_ml,
        "status": p.status,
        "status_display": p.get_status_display(),
        "preparado_por": p.preparado_por,
        "conferido_por": p.conferido_por,
        "preparado_em": p.preparado_em.isoformat() if p.preparado_em else None,
        "conferido_em": p.conferido_em.isoformat() if p.conferido_em else None,
        "motivo_descarte": p.motivo_descarte,
        "administrado": adm is not None,
        "administracao_id": adm.id if adm else None,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_preparos(request):
    """GET/POST /api/hospital/oncologia/preparos/ — farmácia oncológica.

    O POST sem `droga` gera a lista de preparos a partir das doses já calculadas
    do ciclo: a farmácia não redigita a prescrição, recebe o que o médico assinou.
    """
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, PreparoQuimioterapia, _ = _get_cadeia_models()
    _, CicloQuimioterapia, _, _ = _get_onco_models()

    if request.method == "GET":
        qs = PreparoQuimioterapia.objects.filter(empresa=empresa).select_related(
            "ciclo", "administracao")
        status_f = (request.GET.get("status") or "").strip()
        if status_f:
            qs = qs.filter(status=status_f)
        ciclo_f = request.GET.get("ciclo_id")
        if ciclo_f:
            qs = qs.filter(ciclo_id=ciclo_f)
        itens = list(qs.order_by("-criado_em")[:300])
        return JsonResponse({
            "total": qs.count(),
            "preparos": [_preparo_dict(p) for p in itens],
            "fila_pendente": qs.filter(
                status__in=("pendente", "em_preparo", "pronto")).count(),
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    ciclo = CicloQuimioterapia.objects.filter(
        id=data.get("ciclo_id"), empresa=empresa).select_related("protocolo").first()
    if ciclo is None:
        return JsonResponse({"erro": "Ciclo não encontrado nesta empresa"}, status=400)

    ok_apt, motivo_apt = _ciclo_liberado_para_infusao(ciclo)
    if not ok_apt:
        return JsonResponse(
            {"erro": "Preparo bloqueado. " + motivo_apt,
             "codigo": "ciclo_nao_liberado"}, status=409)

    droga_unica = (data.get("droga") or "").strip()
    if droga_unica:
        linhas = [{"droga": droga_unica[:120],
                   "dose": data.get("dose_prescrita"),
                   "unidade": (data.get("unidade") or "mg")[:20]}]
    else:
        # Deriva da prescrição calculada do ciclo. Sem doses calculadas não há
        # o que preparar — é sinal de que o ciclo nunca foi dosado.
        doses = ciclo.doses_calculadas or []
        linhas = [{"droga": str(d.get("droga") or "")[:120],
                   "dose": d.get("dose_calculada"),
                   "unidade": str(d.get("unidade_calculada") or d.get("unidade") or "mg")[:20]}
                  for d in doses if d.get("droga")]
        if not linhas:
            return JsonResponse(
                {"erro": "Ciclo sem doses calculadas: informe peso/altura no ciclo "
                         "ou envie 'droga' e 'dose_prescrita' manualmente.",
                 "codigo": "sem_doses"}, status=400)

    criados = []
    with transaction.atomic():
        for linha in linhas:
            dose = linha.get("dose")
            try:
                dose = float(dose) if dose not in (None, "") else None
            except (TypeError, ValueError):
                dose = None
            criados.append(PreparoQuimioterapia.objects.create(
                empresa=empresa, ciclo=ciclo, droga=linha["droga"],
                dose_prescrita=dose, unidade=linha["unidade"]))
    return JsonResponse({
        "total": len(criados),
        "preparos": [_preparo_dict(p) for p in criados],
    }, status=201)


# Caminhos válidos na farmácia. Descarte pode vir de qualquer ponto antes da
# dispensação; voltar atrás não pode, porque o frasco já foi manipulado.
TRANSICOES_PREPARO = {
    "pendente":   {"em_preparo", "descartado"},
    "em_preparo": {"pronto", "descartado"},
    "pronto":     {"conferido", "descartado"},
    "conferido":  {"dispensado", "descartado"},
    "dispensado": set(),
    "descartado": set(),
}


@csrf_exempt
@require_http_methods(["PUT"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_preparo_detalhe(request, preparo_id):
    """PUT /api/hospital/oncologia/preparos/<id>/ — avança um elo da cadeia."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, PreparoQuimioterapia, _ = _get_cadeia_models()
    p = PreparoQuimioterapia.objects.filter(
        id=preparo_id, empresa=empresa).select_related("ciclo").first()
    if p is None:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    data, erro = _parse_json(request)
    if erro:
        return erro

    campos = []
    for campo, limite in (("lote", 60), ("diluente", 80),
                          ("preparado_por", 150), ("motivo_descarte", 0)):
        if campo in data:
            valor = (data.get(campo) or "").strip()
            setattr(p, campo, valor[:limite] if limite else valor)
            campos.append(campo)

    if "validade_lote" in data:
        bruto = data.get("validade_lote")
        if bruto in (None, ""):
            p.validade_lote = None
        else:
            try:
                p.validade_lote = datetime.strptime(str(bruto)[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return JsonResponse(
                    {"erro": "validade_lote inválida (use AAAA-MM-DD)"}, status=400)
        campos.append("validade_lote")

    for campo in ("dose_preparada", "volume_final_ml"):
        if campo in data and data.get(campo) not in (None, ""):
            valor = _num_positivo(data.get(campo))
            if valor is None:
                return JsonResponse(
                    {"erro": f"{campo} deve ser um número maior que zero"}, status=400)
            setattr(p, campo, valor if campo == "dose_preparada" else int(valor))
            campos.append(campo)

    novo = (data.get("status") or "").strip()
    if novo and novo != p.status:
        permitidos = TRANSICOES_PREPARO.get(p.status, set())
        if novo not in permitidos:
            return JsonResponse({
                "erro": f"Transição inválida: '{p.get_status_display()}' → '{novo}'.",
                "status_atual": p.status,
                "transicoes_validas": sorted(permitidos),
            }, status=409)

        if novo == "descartado" and not (p.motivo_descarte or "").strip():
            return JsonResponse(
                {"erro": "Descarte de quimioterápico exige motivo registrado.",
                 "codigo": "descarte_sem_motivo"}, status=400)

        if novo == "pronto":
            if not (p.preparado_por or "").strip():
                return JsonResponse(
                    {"erro": "Informe quem preparou antes de marcar como pronto.",
                     "codigo": "sem_preparador"}, status=400)
            if p.dose_preparada is None:
                return JsonResponse(
                    {"erro": "Informe a dose efetivamente preparada.",
                     "codigo": "sem_dose_preparada"}, status=400)
            p.preparado_em = timezone.now()
            campos.append("preparado_em")

        if novo == "conferido":
            conferente = (data.get("conferido_por") or p.conferido_por or "").strip()
            if not conferente:
                return JsonResponse(
                    {"erro": "Conferência exige o nome do segundo profissional.",
                     "codigo": "sem_conferente"}, status=400)
            # Dupla checagem de verdade: conferir o próprio preparo não é conferência.
            if _norm(conferente) == _norm(p.preparado_por):
                return JsonResponse(
                    {"erro": "A conferência precisa ser feita por um profissional "
                             "diferente de quem preparou.",
                     "codigo": "dupla_checagem_mesma_pessoa"}, status=400)
            if p.validade_lote and p.validade_lote < date.today():
                return JsonResponse(
                    {"erro": f"Lote vencido em {p.validade_lote.strftime('%d/%m/%Y')}: "
                             "não pode ser liberado.",
                     "codigo": "lote_vencido"}, status=409)
            p.conferido_por = conferente[:150]
            p.conferido_em = timezone.now()
            campos += ["conferido_por", "conferido_em"]

        p.status = novo
        campos.append("status")

    if campos:
        p.save(update_fields=list(dict.fromkeys(campos)))
    return JsonResponse({"ok": True, "preparo": _preparo_dict(p)})


def _administracao_dict(a):
    return {
        "id": a.id,
        "preparo_id": a.preparo_id,
        "ciclo_id": a.ciclo_id,
        "paciente_nome": a.ciclo.paciente_nome,
        "droga": a.preparo.droga,
        "via": a.via,
        "via_display": a.get_via_display(),
        "inicio": a.inicio.isoformat(),
        "fim": a.fim.isoformat() if a.fim else None,
        "dose_administrada": (float(a.dose_administrada)
                              if a.dose_administrada is not None else None),
        "unidade": a.preparo.unidade,
        "administrado_por": a.administrado_por,
        "checado_por": a.checado_por,
        "intercorrencia": a.intercorrencia,
        "intercorrencia_display": a.get_intercorrencia_display(),
        "intercorrencia_conduta": a.intercorrencia_conduta,
        "observacao": a.observacao,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_administracoes(request):
    """GET/POST /api/hospital/oncologia/administracoes/ — beira do leito."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    _, PreparoQuimioterapia, AdministracaoQuimioterapia = _get_cadeia_models()

    if request.method == "GET":
        qs = AdministracaoQuimioterapia.objects.filter(
            empresa=empresa).select_related("preparo", "ciclo")
        ciclo_f = request.GET.get("ciclo_id")
        if ciclo_f:
            qs = qs.filter(ciclo_id=ciclo_f)
        inter = (request.GET.get("intercorrencia") or "").strip()
        if inter:
            qs = qs.filter(intercorrencia=inter)
        itens = list(qs.order_by("-inicio")[:300])
        return JsonResponse({
            "total": qs.count(),
            "administracoes": [_administracao_dict(a) for a in itens],
            "com_intercorrencia": qs.exclude(intercorrencia="nenhuma").count(),
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    p = PreparoQuimioterapia.objects.filter(
        id=data.get("preparo_id"), empresa=empresa).select_related("ciclo").first()
    if p is None:
        return JsonResponse({"erro": "Preparo não encontrado nesta empresa"}, status=400)

    # O elo que fecha a cadeia: só entra na veia o que a farmácia conferiu.
    if p.status not in ("conferido", "dispensado"):
        return JsonResponse({
            "erro": f"Preparo está '{p.get_status_display()}'. Só é possível "
                    "administrar após a conferência da farmácia.",
            "codigo": "preparo_nao_conferido",
            "status_preparo": p.status,
        }, status=409)
    if AdministracaoQuimioterapia.objects.filter(preparo=p).exists():
        return JsonResponse(
            {"erro": "Este preparo já foi administrado.",
             "codigo": "preparo_ja_administrado"}, status=409)

    administrador = (data.get("administrado_por") or "").strip()
    checador = (data.get("checado_por") or "").strip()
    if not administrador or not checador:
        return JsonResponse(
            {"erro": "Administração exige dois profissionais: quem administra "
                     "e quem checa à beira do leito.",
             "codigo": "dupla_checagem_incompleta"}, status=400)
    if _norm(administrador) == _norm(checador):
        return JsonResponse(
            {"erro": "A checagem à beira do leito precisa ser de um profissional "
                     "diferente de quem administra.",
             "codigo": "dupla_checagem_mesma_pessoa"}, status=400)

    via = (data.get("via") or "periferico").strip()
    if via not in dict(AdministracaoQuimioterapia.VIA):
        return JsonResponse(
            {"erro": "via inválida",
             "validos": [v[0] for v in AdministracaoQuimioterapia.VIA]}, status=400)

    inter = (data.get("intercorrencia") or "nenhuma").strip()
    if inter not in dict(AdministracaoQuimioterapia.INTERCORRENCIA):
        return JsonResponse(
            {"erro": "intercorrencia inválida",
             "validos": [i[0] for i in AdministracaoQuimioterapia.INTERCORRENCIA]},
            status=400)
    conduta = (data.get("intercorrencia_conduta") or "").strip()
    # Extravasamento sem conduta registrada é o caso clássico que some do
    # prontuário e reaparece como processo.
    if inter != "nenhuma" and not conduta:
        return JsonResponse(
            {"erro": "Intercorrência exige a conduta adotada.",
             "codigo": "intercorrencia_sem_conduta"}, status=400)

    def _dt(valor):
        """Converte 'AAAA-MM-DDTHH:MM' em datetime com fuso — gravar ingênuo com
        USE_TZ ativo desloca o horário da infusão em produção."""
        try:
            bruto = datetime.strptime(str(valor)[:16], "%Y-%m-%dT%H:%M")
        except (ValueError, TypeError):
            return None
        return timezone.make_aware(bruto, timezone.get_current_timezone())

    inicio = _dt(data.get("inicio")) or timezone.now()
    fim = _dt(data.get("fim")) if data.get("fim") else None
    if fim and fim < inicio:
        return JsonResponse(
            {"erro": "O fim da infusão não pode ser anterior ao início."}, status=400)

    dose = data.get("dose_administrada")
    if dose in (None, ""):
        dose = p.dose_preparada
    else:
        dose = _num_positivo(dose)
        if dose is None:
            return JsonResponse(
                {"erro": "dose_administrada deve ser um número maior que zero"},
                status=400)

    with transaction.atomic():
        a = AdministracaoQuimioterapia.objects.create(
            empresa=empresa, preparo=p, ciclo=p.ciclo, via=via,
            inicio=inicio, fim=fim, dose_administrada=dose,
            administrado_por=administrador[:150], checado_por=checador[:150],
            intercorrencia=inter, intercorrencia_conduta=conduta,
            observacao=(data.get("observacao") or "").strip())
        if p.status == "conferido":
            p.status = "dispensado"
            p.save(update_fields=["status"])

    return JsonResponse({"id": a.id, "administracao": _administracao_dict(a)},
                        status=201)


# ── Quimioterapia oral: o paciente que não senta na cadeira ────────────────────
# A infusão é vigiada porque acontece dentro do hospital. A oral acontece na
# cozinha do paciente — e é por isso que a não-adesão só aparece depois, disfarçada
# de "o tratamento não respondeu". A contagem de comprimidos é o único dado
# objetivo disponível na prática: entregue − devolvido, contra o esperado no
# intervalo entre duas retiradas.

ADESAO_LIMITE_BAIXA = 80.0    # % — abaixo disto, a literatura já associa perda de eficácia
ATRASO_RETIRADA_ALERTA = 3    # dias de atraso que acendem o alerta


def _get_oral_models():
    from .models import PrescricaoQuimioOral, DispensacaoQuimioOral
    return PrescricaoQuimioOral, DispensacaoQuimioOral


def _dias_de_uso_no_intervalo(prescricao, inicio, fim):
    """Quantos dias de USO caem entre duas datas, respeitando o esquema cíclico.

    Capecitabina 14+7 não é "tomar todo dia": contar dias corridos superestima o
    esperado e faz todo paciente parecer não-aderente.
    """
    uso = max(int(prescricao.dias_uso or 0), 0)
    pausa = max(int(prescricao.dias_pausa or 0), 0)
    periodo = uso + pausa
    if uso == 0:
        return 0
    if periodo == 0 or pausa == 0:
        return max((fim - inicio).days, 0)
    dias = 0
    atual = inicio
    while atual < fim:
        # Posição do dia dentro do ciclo, contada a partir do início da prescrição.
        pos = (atual - prescricao.data_inicio).days % periodo
        if 0 <= pos < uso:
            dias += 1
        atual += timedelta(days=1)
    return dias


def _calcular_adesao(prescricao, dispensacao_anterior, data_atual, devolvidas):
    """Adesão do intervalo pela contagem de comprimidos.

    Devolve (adesao_pct, esperado, tomado) ou (None, ...) quando não há retirada
    anterior — a primeira dispensação não mede nada, só entrega.
    """
    if dispensacao_anterior is None:
        return None, None, None
    esperado = (_dias_de_uso_no_intervalo(
        prescricao, dispensacao_anterior.data, data_atual)
        * max(int(prescricao.unidades_por_dia or 0), 0))
    if esperado <= 0:
        return None, esperado, None
    tomado = max(int(dispensacao_anterior.unidades_dispensadas) - int(devolvidas), 0)
    # Teto em 100%: tomar mais que o prescrito não é "mais aderente"; vira
    # observação clínica, não um número acima de 100 no painel.
    pct = min(round(tomado / esperado * 100, 1), 100.0)
    return pct, esperado, tomado


def _situacao_retirada(prescricao, ultima):
    """Se o paciente está atrasado para voltar buscar a próxima caixa."""
    if prescricao.status != "ativa" or ultima is None or not ultima.proxima_retirada:
        return {"aplicavel": False}
    atraso = (date.today() - ultima.proxima_retirada).days
    return {
        "aplicavel": True,
        "proxima_retirada": ultima.proxima_retirada.isoformat(),
        "dias_atraso": max(atraso, 0),
        "atrasado": atraso >= ATRASO_RETIRADA_ALERTA,
    }


def _prescricao_oral_dict(p):
    disp = list(p.dispensacoes.all().order_by("-data"))
    ultima = disp[0] if disp else None
    medidas = [float(d.adesao_pct) for d in disp if d.adesao_pct is not None]
    media = round(sum(medidas) / len(medidas), 1) if medidas else None
    return {
        "id": p.id,
        "paciente_nome": p.paciente_nome,
        "cpf_paciente": p.cpf_paciente,
        "ciclo_id": p.ciclo_id,
        "droga": p.droga,
        "dose_por_tomada": (float(p.dose_por_tomada)
                            if p.dose_por_tomada is not None else None),
        "unidade": p.unidade,
        "unidades_por_dia": p.unidades_por_dia,
        "posologia": p.posologia,
        "dias_uso": p.dias_uso,
        "dias_pausa": p.dias_pausa,
        "esquema": f"{p.dias_uso} dias de uso + {p.dias_pausa} de pausa"
                   if p.dias_pausa else "uso contínuo",
        "data_inicio": p.data_inicio.isoformat(),
        "data_fim_prevista": (p.data_fim_prevista.isoformat()
                              if p.data_fim_prevista else None),
        "status": p.status,
        "status_display": p.get_status_display(),
        "medico": p.medico,
        "observacao": p.observacao,
        "total_dispensacoes": len(disp),
        "adesao_media_pct": media,
        "adesao_baixa": (media is not None and media < ADESAO_LIMITE_BAIXA),
        "ultima_adesao_pct": (float(ultima.adesao_pct)
                              if ultima and ultima.adesao_pct is not None else None),
        "retirada": _situacao_retirada(p, ultima),
    }


def _dispensacao_dict(d):
    return {
        "id": d.id,
        "prescricao_id": d.prescricao_id,
        "data": d.data.isoformat(),
        "unidades_dispensadas": d.unidades_dispensadas,
        "unidades_devolvidas": d.unidades_devolvidas,
        "adesao_pct": float(d.adesao_pct) if d.adesao_pct is not None else None,
        "proxima_retirada": (d.proxima_retirada.isoformat()
                             if d.proxima_retirada else None),
        "dispensado_por": d.dispensado_por,
        "observacao": d.observacao,
    }


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_quimio_oral(request):
    """GET/POST /api/hospital/oncologia/quimio-oral/ — prescrições orais."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    PrescricaoQuimioOral, _ = _get_oral_models()
    _, CicloQuimioterapia, _, _ = _get_onco_models()

    if request.method == "GET":
        qs = PrescricaoQuimioOral.objects.filter(empresa=empresa).prefetch_related(
            "dispensacoes")
        status_f = (request.GET.get("status") or "").strip()
        if status_f:
            qs = qs.filter(status=status_f)
        cpf = "".join(filter(str.isdigit, request.GET.get("cpf", "")))[:11]
        if cpf:
            qs = qs.filter(cpf_paciente=cpf)
        itens = [_prescricao_oral_dict(p) for p in qs.order_by("-data_inicio")[:300]]
        return JsonResponse({
            "total": qs.count(),
            "prescricoes": itens,
            # Os dois números que importam: quem não voltou buscar e quem está
            # tomando menos do que deveria.
            "atrasados_retirada": sum(
                1 for i in itens if i["retirada"].get("atrasado")),
            "adesao_baixa": sum(1 for i in itens if i["adesao_baixa"]),
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    paciente = (data.get("paciente_nome") or "").strip()
    droga = (data.get("droga") or "").strip()
    if not paciente or not droga:
        return JsonResponse(
            {"erro": "Paciente e droga são obrigatórios"}, status=400)

    try:
        inicio = datetime.strptime(
            str(data.get("data_inicio") or date.today().isoformat())[:10],
            "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"erro": "data_inicio inválida (use AAAA-MM-DD)"}, status=400)

    cpf_raw = data.get("cpf_paciente", "")
    ok_cpf, erro_cpf = validar_cpf_cadastro(cpf_raw, empresa)
    if not ok_cpf:
        return JsonResponse({"erro": erro_cpf}, status=400)
    cpf = "".join(filter(str.isdigit, cpf_raw))[:11]

    try:
        por_dia = int(data.get("unidades_por_dia") or 2)
        dias_uso = int(data.get("dias_uso") or 14)
        dias_pausa = int(data.get("dias_pausa") or 7)
    except (TypeError, ValueError):
        return JsonResponse(
            {"erro": "unidades_por_dia, dias_uso e dias_pausa devem ser inteiros"},
            status=400)
    if por_dia < 1 or dias_uso < 1 or dias_pausa < 0:
        return JsonResponse(
            {"erro": "Esquema inválido: unidades_por_dia e dias_uso ≥ 1, "
                     "dias_pausa ≥ 0."}, status=400)

    ciclo = None
    if data.get("ciclo_id"):
        ciclo = CicloQuimioterapia.objects.filter(
            id=data["ciclo_id"], empresa=empresa).first()
        if ciclo is None:
            return JsonResponse({"erro": "Ciclo não encontrado nesta empresa"}, status=400)

    fim = None
    if data.get("data_fim_prevista"):
        try:
            fim = datetime.strptime(
                str(data["data_fim_prevista"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return JsonResponse(
                {"erro": "data_fim_prevista inválida (use AAAA-MM-DD)"}, status=400)
        if fim < inicio:
            return JsonResponse(
                {"erro": "data_fim_prevista não pode ser anterior ao início"}, status=400)

    dose = data.get("dose_por_tomada")
    if dose not in (None, ""):
        dose = _num_positivo(dose)
        if dose is None:
            return JsonResponse(
                {"erro": "dose_por_tomada deve ser um número maior que zero"}, status=400)
    else:
        dose = None

    p = PrescricaoQuimioOral.objects.create(
        empresa=empresa, paciente_nome=paciente, cpf_paciente=cpf,
        identidade=resolver_identidade(empresa, nome=paciente, cpf=cpf_raw),
        ciclo=ciclo, droga=droga[:120], dose_por_tomada=dose,
        unidade=(data.get("unidade") or "mg")[:20], unidades_por_dia=por_dia,
        posologia=(data.get("posologia") or "").strip()[:200],
        dias_uso=dias_uso, dias_pausa=dias_pausa,
        data_inicio=inicio, data_fim_prevista=fim,
        medico=(data.get("medico") or "").strip()[:150],
        observacao=(data.get("observacao") or "").strip())
    return JsonResponse({"id": p.id, "prescricao": _prescricao_oral_dict(p)},
                        status=201)


@csrf_exempt
@require_http_methods(["PUT"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_quimio_oral_detalhe(request, prescricao_id):
    """PUT /api/hospital/oncologia/quimio-oral/<id>/ — suspender, retomar, encerrar."""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    PrescricaoQuimioOral, _ = _get_oral_models()
    p = PrescricaoQuimioOral.objects.filter(
        id=prescricao_id, empresa=empresa).prefetch_related("dispensacoes").first()
    if p is None:
        return JsonResponse({"erro": "Não encontrado"}, status=404)

    data, erro = _parse_json(request)
    if erro:
        return erro

    campos = []
    novo = (data.get("status") or "").strip()
    if novo and novo != p.status:
        if novo not in dict(PrescricaoQuimioOral.STATUS):
            return JsonResponse(
                {"erro": "status inválido",
                 "validos": [x[0] for x in PrescricaoQuimioOral.STATUS]}, status=400)
        if p.status in ("concluida", "cancelada"):
            return JsonResponse(
                {"erro": f"Prescrição já está '{p.get_status_display()}'.",
                 "status_atual": p.status}, status=409)
        p.status = novo
        campos.append("status")
    for campo, limite in (("posologia", 200), ("medico", 150), ("observacao", 0)):
        if campo in data:
            valor = (data.get(campo) or "").strip()
            setattr(p, campo, valor[:limite] if limite else valor)
            campos.append(campo)
    if campos:
        p.save(update_fields=campos)
    return JsonResponse({"ok": True, "prescricao": _prescricao_oral_dict(p)})


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_requer_feature("hospital.oncologia")
@api_requer_permissao_modulo("hospital.clinico")
def api_onco_quimio_oral_dispensacoes(request, prescricao_id):
    """GET/POST /api/hospital/oncologia/quimio-oral/<id>/dispensacoes/"""
    empresa = _hosp(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    PrescricaoQuimioOral, DispensacaoQuimioOral = _get_oral_models()
    p = PrescricaoQuimioOral.objects.filter(
        id=prescricao_id, empresa=empresa).first()
    if p is None:
        return JsonResponse({"erro": "Prescrição não encontrada"}, status=404)

    if request.method == "GET":
        itens = list(p.dispensacoes.all().order_by("-data"))
        return JsonResponse({
            "prescricao_id": p.id,
            "total": len(itens),
            "dispensacoes": [_dispensacao_dict(d) for d in itens],
        })

    data, erro = _parse_json(request)
    if erro:
        return erro

    if p.status != "ativa":
        return JsonResponse(
            {"erro": f"Prescrição está '{p.get_status_display()}': não há o que "
                     "dispensar.", "codigo": "prescricao_inativa"}, status=409)

    try:
        d_dia = datetime.strptime(
            str(data.get("data") or date.today().isoformat())[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"erro": "data inválida (use AAAA-MM-DD)"}, status=400)

    try:
        entregues = int(data.get("unidades_dispensadas"))
        devolvidas = int(data.get("unidades_devolvidas") or 0)
    except (TypeError, ValueError):
        return JsonResponse(
            {"erro": "unidades_dispensadas é obrigatória (inteiro) e "
                     "unidades_devolvidas deve ser inteira"}, status=400)
    if entregues < 1 or devolvidas < 0:
        return JsonResponse(
            {"erro": "unidades_dispensadas ≥ 1 e unidades_devolvidas ≥ 0"}, status=400)

    anterior = p.dispensacoes.order_by("-data").first()
    if anterior and d_dia < anterior.data:
        return JsonResponse(
            {"erro": f"Já existe retirada em {anterior.data.strftime('%d/%m/%Y')}; "
                     "a nova não pode ser anterior.",
             "codigo": "retirada_retroativa"}, status=400)
    # Devolver mais do que foi entregue é erro de contagem, não adesão perfeita.
    if anterior and devolvidas > anterior.unidades_dispensadas:
        return JsonResponse(
            {"erro": f"Devolvidas ({devolvidas}) excedem as "
                     f"{anterior.unidades_dispensadas} entregues na retirada anterior.",
             "codigo": "devolucao_maior_que_entrega"}, status=400)
    if anterior is None and devolvidas:
        return JsonResponse(
            {"erro": "Não há retirada anterior: não existem unidades a devolver.",
             "codigo": "devolucao_sem_retirada_anterior"}, status=400)

    adesao, esperado, tomado = _calcular_adesao(p, anterior, d_dia, devolvidas)

    proxima = None
    if data.get("proxima_retirada"):
        try:
            proxima = datetime.strptime(
                str(data["proxima_retirada"])[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return JsonResponse(
                {"erro": "proxima_retirada inválida (use AAAA-MM-DD)"}, status=400)
    else:
        # Sem data informada, agenda para o fim do ciclo de uso em curso.
        periodo = (p.dias_uso or 0) + (p.dias_pausa or 0)
        proxima = d_dia + timedelta(days=periodo or 28)

    d = DispensacaoQuimioOral.objects.create(
        empresa=empresa, prescricao=p, data=d_dia,
        unidades_dispensadas=entregues, unidades_devolvidas=devolvidas,
        adesao_pct=adesao, proxima_retirada=proxima,
        dispensado_por=(data.get("dispensado_por") or "").strip()[:150],
        observacao=(data.get("observacao") or "").strip())

    return JsonResponse({
        "id": d.id,
        "dispensacao": _dispensacao_dict(d),
        "adesao_intervalo": {
            "adesao_pct": adesao,
            "unidades_esperadas": esperado,
            "unidades_tomadas": tomado,
            "baixa": (adesao is not None and adesao < ADESAO_LIMITE_BAIXA),
        },
        "alerta": ("Adesão abaixo de "
                   f"{ADESAO_LIMITE_BAIXA:.0f}% no intervalo — conversar com o "
                   "paciente antes de atribuir falha ao tratamento."
                   if adesao is not None and adesao < ADESAO_LIMITE_BAIXA else None),
    }, status=201)
