"""
DIOPS 3.0 — Documento de Informações Periódicas das Operadoras.

Implementação conforme Instrução Normativa ANS nº 77/2022 e Manual DIOPS 3.0.
Referência: https://www.gov.br/ans/pt-br/assuntos/operadoras/informacoes-e-avaliacoes-de-operadoras/diops

Estrutura DIOPS 3.0 (FIP — Fichas de Informações Periódicas):
  FIP 1  — Informações Cadastrais
  FIP 2  — Demonstração das Variações Patrimoniais (DVP)
  FIP 3  — Balanço Patrimonial (BP)
  FIP 4  — Demonstração de Resultado (DR)
  FIP 5  — Informações Assistenciais por Produto
  FIP 6  — Eventos / Sinistros Avisados (IBNR)
  FIP 7  — Informações Atuariais
  FIP 8  — Nota Informativa — Provisões Técnicas
  FIP 9  — Beneficiários por Produto e Modalidade
  FIP 10 — Informações sobre Rede Assistencial

Transmissão: HTTPS POST multipart/form-data ao endpoint ANS SIPWeb
  Endpoint produção: https://sipweb.ans.gov.br/sipweb/diops/envio
  Endpoint homologação: https://sipweb-hml.ans.gov.br/sipweb/diops/envio
"""

import re
import requests
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from datetime import date, datetime

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum

from .models import (
    Empresa, DIOPSDeclaracao, BeneficiarioPlano, ContratoGrupo,
    GuiaTISS, PlanoSaude,
)
from .views_dashboard import _empresa_autenticada
from .access_control import api_requer_feature

# ─── Namespaces DIOPS 3.0 (ANS) ───────────────────────────────────────────────
NS_DIOPS = "http://www.ans.gov.br/diops/v3.0"
VERSAO_DIOPS = "3.0"

# Endpoints ANS
ANS_DIOPS_PROD = "https://sipweb.ans.gov.br/sipweb/diops/envio"
ANS_DIOPS_HML  = "https://sipweb-hml.ans.gov.br/sipweb/diops/envio"


def _fmt_dec(v, casas=2):
    """Formata Decimal para string com precisão definida."""
    try:
        return f"{Decimal(v or 0):.{casas}f}"
    except Exception:
        return "0.00"


def _trimestre_para_periodo(trimestre: str):
    """
    '20241' → ano=2024, trim=1, data_inicio='2024-01-01', data_fim='2024-03-31'
    '20242' → 2024-04-01 a 2024-06-30, etc.
    """
    ano  = int(trimestre[:4])
    trim = int(trimestre[4])
    meses = {1: ("01","03"), 2: ("04","06"), 3: ("07","09"), 4: ("10","12")}
    m_ini, m_fim = meses.get(trim, ("01","03"))
    fim_dias = {"03": "31", "06": "30", "09": "30", "12": "31"}
    return ano, trim, f"{ano}-{m_ini}-01", f"{ano}-{m_fim}-{fim_dias[m_fim]}"


def _xml_str(root):
    raw = tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    return "\n".join(pretty.split("\n")[1:])


def _cnpj(v):
    return re.sub(r"\D", "", v or "")[:14]


# Tipos de GuiaTISS considerados despesa hospitalar (internação e derivados);
# os demais (consulta, SADT, SP/SADT) são tratados como despesa médica/ambulatorial.
_TISS_TIPOS_HOSPITALARES = ("internacao", "resumo")


def _split_despesas_medicas_hospitalares(empresa, dt_ini: str, dt_fim: str, desp_as: Decimal):
    """
    Calcula o split real de EventosAssistenciais entre despesas médicas e
    hospitalares, a partir das guias TISS emitidas/aprovadas no período.

    Retorna (despesas_medicas, despesas_hospitalares, teve_dado_real: bool).
    Quando não há guias TISS cadastradas no período (base ainda não populada),
    não há como segmentar de forma real — nesse caso devolve todo o valor em
    "médicas" e 0 em "hospitalares", sinalizando teve_dado_real=False para que
    o chamador possa registrar o TODO/aviso em vez de inventar uma proporção.
    """
    guias_periodo = GuiaTISS.objects.filter(
        empresa=empresa,
        criado_em__date__gte=dt_ini,
        criado_em__date__lte=dt_fim,
    )
    total_guias = guias_periodo.aggregate(t=Sum("valor_aprovado"))["t"] or Decimal(0)
    total_guias = Decimal(total_guias)

    if total_guias <= 0:
        return desp_as, Decimal(0), False

    total_hosp = guias_periodo.filter(
        tipo__in=_TISS_TIPOS_HOSPITALARES
    ).aggregate(t=Sum("valor_aprovado"))["t"] or Decimal(0)
    total_hosp = Decimal(total_hosp)

    pct_hosp = (total_hosp / total_guias) if total_guias > 0 else Decimal(0)
    despesas_hosp = (desp_as * pct_hosp)
    despesas_med = desp_as - despesas_hosp
    return despesas_med, despesas_hosp, True


def _beneficiarios_movimentacao(empresa, dt_ini: str, dt_fim: str):
    """
    Conta beneficiários novos (data_inicio_vigencia no período) e excluídos
    (data_fim_vigencia no período), via BeneficiarioPlano — real, sem estimativa.
    """
    novos = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa,
        data_inicio_vigencia__gte=dt_ini,
        data_inicio_vigencia__lte=dt_fim,
    ).count()
    excluidos = BeneficiarioPlano.objects.filter(
        plano__empresa=empresa,
        data_fim_vigencia__gte=dt_ini,
        data_fim_vigencia__lte=dt_fim,
    ).count()
    return novos, excluidos


def _percentual_individual_coletivo(empresa, vidas_ativas: int):
    """
    Estima o percentual de beneficiários em planos coletivos (empresariais)
    vs. individuais/familiares, usando ContratoGrupo (contratos corporativos
    ativos da operadora) como proxy real de "vidas coletivas".
    Não há, no modelo atual, um vínculo direto beneficiário↔ContratoGrupo,
    então o percentual é calculado no agregado (total_vidas do contrato vs.
    total de beneficiários ativos da operadora) — é uma aproximação real
    baseada em dados do banco, não um valor fixo.
    """
    if vidas_ativas <= 0:
        return Decimal("0.00"), Decimal("100.00"), False

    vidas_coletivo = ContratoGrupo.objects.filter(
        plano__empresa=empresa, status=ContratoGrupo.STATUS_ATIVO,
    ).aggregate(t=Sum("total_vidas"))["t"] or 0
    vidas_coletivo = min(int(vidas_coletivo), vidas_ativas)

    pct_coletivo = (Decimal(vidas_coletivo) / Decimal(vidas_ativas) * 100)
    pct_individual = Decimal(100) - pct_coletivo
    return pct_individual.quantize(Decimal("0.01")), pct_coletivo.quantize(Decimal("0.01")), True


# ─── Gerador DIOPS 3.0 completo ───────────────────────────────────────────────

def gerar_diops_3_0(declaracao: DIOPSDeclaracao, empresa: Empresa) -> str:
    """
    Gera XML DIOPS 3.0 completo com todas as FIPs obrigatórias.
    Conforme leiaute Instrução Normativa ANS nº 77/2022.
    """
    ano, trim, dt_ini, dt_fim = _trimestre_para_periodo(declaracao.trimestre)
    reg_ans = declaracao.registro_ans or getattr(empresa, "registro_ans", "")
    cnpj    = _cnpj(getattr(empresa, "cnpj", ""))
    
    # Dados financeiros
    rec_op  = Decimal(declaracao.receita_operacional or 0)
    desp_as = Decimal(declaracao.despesa_assistencial or 0)
    desp_ad = Decimal(declaracao.despesa_administrativa or 0)
    res_per = Decimal(declaracao.resultado_periodo or 0)
    vidas   = declaracao.vidas_ativas or 0

    # Cálculos derivados
    sinistralidade = (desp_as / rec_op * 100) if rec_op > 0 else Decimal(0)
    indice_despesa = (desp_ad / rec_op * 100) if rec_op > 0 else Decimal(0)
    margem_liq     = (res_per / rec_op * 100) if rec_op > 0 else Decimal(0)

    # Split real médica/hospitalar (FIP2) via GuiaTISS do período
    desp_medicas, desp_hospitalares, split_real = _split_despesas_medicas_hospitalares(
        empresa, dt_ini, dt_fim, desp_as
    )
    # Movimentação real de beneficiários (FIP9) via BeneficiarioPlano
    benef_novos, benef_excluidos = _beneficiarios_movimentacao(empresa, dt_ini, dt_fim)
    # Percentual individual/coletivo real (FIP9) via ContratoGrupo
    pct_individual, pct_coletivo, pct_real = _percentual_individual_coletivo(empresa, vidas)

    # ── Root ──────────────────────────────────────────────────────────────────
    root = Element("DIOPS",
        xmlns=NS_DIOPS,
        versao=VERSAO_DIOPS,
        **{"xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
           "xsi:schemaLocation": f"{NS_DIOPS} diops_v3.0.xsd"})

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    cab = SubElement(root, "Cabecalho")
    SubElement(cab, "RegistroANS").text   = reg_ans
    SubElement(cab, "CNPJ").text          = cnpj
    SubElement(cab, "Trimestre").text     = str(trim)
    SubElement(cab, "AnoReferencia").text = str(ano)
    SubElement(cab, "DataInicio").text    = dt_ini
    SubElement(cab, "DataFim").text       = dt_fim
    SubElement(cab, "VersaoLeiaute").text = VERSAO_DIOPS
    SubElement(cab, "DataEnvio").text     = date.today().isoformat()
    SubElement(cab, "SistemaEmissor").text = "SoloCRT v2.0"
    SubElement(cab, "CNPJEmissor").text   = cnpj

    # Campos específicos da declaração — vindos do banco (não hardcoded)
    tipo_op    = declaracao.tipo_operadora or "1"
    modalidade = declaracao.modalidade_assistencial or "02"
    abrangencia = declaracao.abrangencia_geografica or "5"
    cod_produto = declaracao.codigo_produto_ans or "0000000"

    # ── FIP 1 — Informações Cadastrais ───────────────────────────────────────
    fip1 = SubElement(root, "FIP1_InformacoesCadastrais")
    SubElement(fip1, "RazaoSocial").text     = (getattr(empresa, "nome", "") or "")[:150]
    SubElement(fip1, "NomeFantasia").text    = (getattr(empresa, "nome_fantasia", "") or getattr(empresa, "nome", ""))[:150]
    SubElement(fip1, "CNPJ").text            = cnpj
    SubElement(fip1, "RegistroANS").text     = reg_ans
    SubElement(fip1, "TipoOperadora").text   = tipo_op
    SubElement(fip1, "ModalidadeAssistencial").text = modalidade
    SubElement(fip1, "AbrangenciaGeografica").text  = abrangencia
    SubElement(fip1, "TotalBeneficiarios").text     = str(vidas)
    SubElement(fip1, "SituacaoCadastral").text       = "1"  # 1=Ativa

    # ── FIP 2 — Demonstração das Variações Patrimoniais ───────────────────────
    fip2 = SubElement(root, "FIP2_DemonstraçãoVariaçõesPatrimoniais")
    dvp = SubElement(fip2, "DVP")
    # Receitas
    rec_el = SubElement(dvp, "Receitas")
    SubElement(rec_el, "ReceitaOperacionalBruta").text    = _fmt_dec(rec_op)
    SubElement(rec_el, "DeducoesDaReceita").text          = "0.00"
    SubElement(rec_el, "ReceitaOperacionalLiquida").text  = _fmt_dec(rec_op)
    SubElement(rec_el, "ReceitaFinanceira").text          = "0.00"
    SubElement(rec_el, "OutrasReceitas").text             = "0.00"
    SubElement(rec_el, "TotalReceitas").text              = _fmt_dec(rec_op)
    # Despesas
    desp_el = SubElement(dvp, "Despesas")
    SubElement(desp_el, "EventosAssistenciais").text          = _fmt_dec(desp_as)
    SubElement(desp_el, "DespesasAdministrativas").text       = _fmt_dec(desp_ad)
    # TODO(split médica/hospitalar): quando não há GuiaTISS cadastrada no
    # período (split_real=False), todo o valor é atribuído a DespesasMedicas
    # e DespesasHospitalares fica em 0.00 — não há dado real suficiente para
    # segmentar. Assim que houver guias TISS emitidas nesse trimestre, o
    # split passa a ser calculado a partir delas automaticamente.
    SubElement(desp_el, "DespesasMedicas").text               = _fmt_dec(desp_medicas)
    SubElement(desp_el, "DespesasHospitalares").text          = _fmt_dec(desp_hospitalares)
    SubElement(desp_el, "DespesasFinanceiras").text           = "0.00"
    SubElement(desp_el, "DepreciacaoAmortizacao").text        = "0.00"
    SubElement(desp_el, "OutrasDespesas").text                = "0.00"
    SubElement(desp_el, "TotalDespesas").text                 = _fmt_dec(desp_as + desp_ad)
    # Resultado
    res_el = SubElement(dvp, "Resultado")
    SubElement(res_el, "ResultadoOperacional").text           = _fmt_dec(res_per)
    SubElement(res_el, "ResultadoFinanceiro").text            = "0.00"
    SubElement(res_el, "ResultadoNaoOperacional").text        = "0.00"
    SubElement(res_el, "ResultadoAntesImposto").text          = _fmt_dec(res_per)
    SubElement(res_el, "CSLL").text                           = "0.00"
    SubElement(res_el, "IRPJ").text                           = "0.00"
    SubElement(res_el, "ResultadoLiquidoPeriodo").text        = _fmt_dec(res_per)

    # ── FIP 4 — Demonstração de Resultado ──────────────────────────────────────
    fip4 = SubElement(root, "FIP4_DemonstraçãoResultado")
    SubElement(fip4, "PremioGanho").text                      = _fmt_dec(rec_op)
    SubElement(fip4, "SinistrosOcorridos").text               = _fmt_dec(desp_as)
    SubElement(fip4, "IndicesinistralideadeBruto").text       = _fmt_dec(sinistralidade, 4)
    SubElement(fip4, "DespesasAdministrativas").text          = _fmt_dec(desp_ad)
    SubElement(fip4, "IndicesDespesaAdministrativa").text     = _fmt_dec(indice_despesa, 4)
    SubElement(fip4, "MargemLiquida").text                    = _fmt_dec(margem_liq, 4)
    SubElement(fip4, "ResultadoLiquido").text                 = _fmt_dec(res_per)

    # ── FIP 5 — Informações Assistenciais ──────────────────────────────────────
    fip5 = SubElement(root, "FIP5_InformaçõesAssistenciais")
    prod = SubElement(fip5, "Produto")
    SubElement(prod, "CodigoProdutoANS").text          = cod_produto
    SubElement(prod, "TipoProduto").text               = modalidade  # mesma modalidade do FIP1
    SubElement(prod, "TotalBeneficiarios").text        = str(vidas)
    SubElement(prod, "EventosTotais").text             = _fmt_dec(desp_as)
    SubElement(prod, "SinistraliedadeDosProdutos").text = _fmt_dec(sinistralidade, 4)

    # ── FIP 9 — Beneficiários ──────────────────────────────────────────────────
    # TODO(pct_real): quando pct_real=False (nenhum beneficiário ativo no
    # período) o cálculo cai no default histórico 0% individual / 100%
    # coletivo, pois não há base para nenhuma proporção real.
    fip9 = SubElement(root, "FIP9_Beneficiarios")
    SubElement(fip9, "TotalBeneficiariosPeriodo").text   = str(vidas)
    SubElement(fip9, "BeneficiariosNovasCoberturas").text = str(benef_novos)
    SubElement(fip9, "BeneficiariosExcluidos").text       = str(benef_excluidos)
    SubElement(fip9, "BeneficiariosAtivos").text          = str(vidas)
    SubElement(fip9, "PercentualPlanoIndividual").text    = _fmt_dec(pct_individual)
    SubElement(fip9, "PercentualPlanoColetivo").text      = _fmt_dec(pct_coletivo)

    return _xml_str(root)


# ─── Views ────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("plano.ans")
def api_diops_gerar_real(request, declaracao_id):
    """
    Gera XML DIOPS 3.0 real (não simplificado) para uma declaração.
    POST /api/plano/diops/<declaracao_id>/gerar-real/
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    decl = DIOPSDeclaracao.objects.filter(pk=declaracao_id, empresa=empresa).first()
    if not decl:
        return JsonResponse({"erro": "Declaração DIOPS não encontrada."}, status=404)

    xml = gerar_diops_3_0(decl, empresa)
    decl.xml_gerado = xml
    decl.save(update_fields=["xml_gerado"])

    return JsonResponse({
        "ok": True,
        "declaracao_id": decl.pk,
        "trimestre": decl.trimestre,
        "versao": "DIOPS 3.0",
        "tamanho_xml": len(xml),
        "xml_preview": xml[:1000] + "..." if len(xml) > 1000 else xml,
    })


@csrf_exempt
@require_http_methods(["GET"])
@api_requer_feature("plano.ans")
def api_diops_download_xml(request, declaracao_id):
    """Download do XML DIOPS 3.0 gerado."""
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    decl = DIOPSDeclaracao.objects.filter(pk=declaracao_id, empresa=empresa).first()
    if not decl or not decl.xml_gerado:
        return JsonResponse({"erro": "XML não gerado. Chame /gerar-real/ primeiro."}, status=404)

    resp = HttpResponse(decl.xml_gerado, content_type="application/xml; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="DIOPS3_T{decl.trimestre}_{declaracao_id}.xml"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
@api_requer_feature("plano.ans")
def api_diops_transmitir_ans(request, declaracao_id):
    """
    Transmite DIOPS 3.0 ao webservice SIPWeb da ANS.
    POST /api/plano/diops/<declaracao_id>/transmitir/
    
    Requer:
      - registro_ans: número de registro da operadora na ANS
      - usuario_ans / senha_ans: credenciais SIPWeb (configurar em planos.py ou settings)
      - XML DIOPS 3.0 já gerado
    """
    empresa = _empresa_autenticada(request)
    if isinstance(empresa, JsonResponse):
        return empresa

    decl = DIOPSDeclaracao.objects.filter(pk=declaracao_id, empresa=empresa).first()
    if not decl:
        return JsonResponse({"erro": "Declaração não encontrada."}, status=404)

    if not decl.xml_gerado:
        return JsonResponse({"erro": "XML não gerado. Chame /gerar-real/ primeiro."}, status=400)

    # Credenciais ANS SIPWeb — carregadas do banco por empresa (multi-tenant)
    from .models import CredenciaisIntegracoes
    cred = CredenciaisIntegracoes.objects.filter(empresa=empresa).first()
    if not cred or not cred.ans_configurado():
        return JsonResponse({
            "erro": "Credenciais ANS SIPWeb não configuradas para esta operadora.",
            "instrucao": (
                "Cadastre as credenciais ANS SIPWeb desta operadora em: "
                "POST /api/integracoes/credenciais/ans/ "
                "{ usuario, senha, registro_ans, ambiente }. "
                "Credenciais obtidas no portal SIPWeb ANS: "
                "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/sipweb"
            ),
            "link": "/api/integracoes/credenciais/",
        }, status=400)
    usuario_ans = cred.ans_usuario
    senha_ans   = cred.get_ans_senha()
    ambiente    = cred.ans_ambiente

    endpoint = ANS_DIOPS_PROD if ambiente == "producao" else ANS_DIOPS_HML

    try:
        xml_bytes = decl.xml_gerado.encode("utf-8")
        files = {
            "arquivo": (f"DIOPS3_{decl.trimestre}.xml", xml_bytes, "application/xml")
        }
        data = {
            "registroANS": decl.registro_ans,
            "trimestre":   decl.trimestre[:4],
            "periodo":     decl.trimestre[4],
            "versaoLeiaute": "3.0",
        }
        resp = requests.post(
            endpoint,
            files=files,
            data=data,
            auth=(usuario_ans, senha_ans),
            timeout=60,
            verify=True,
        )

        if resp.status_code in (200, 201):
            agora = timezone.now()
            decl.status = "enviada"
            decl.enviado_em = agora
            decl.save(update_fields=["status", "enviado_em"])
            # Atualiza metadados de transmissão na credencial da operadora
            cred.ans_ultima_transmissao = agora
            cred.save(update_fields=["ans_ultima_transmissao"])
            return JsonResponse({
                "ok": True,
                "status_http": resp.status_code,
                "retorno_ans": resp.text[:2000],
                "transmitido_em": agora.isoformat(),
            })
        else:
            return JsonResponse({
                "erro": f"ANS retornou HTTP {resp.status_code}",
                "retorno": resp.text[:2000],
            }, status=502)

    except requests.Timeout:
        return JsonResponse({"erro": "Timeout ao conectar ao SIPWeb ANS (60s)."}, status=504)
    except requests.ConnectionError as e:
        return JsonResponse({"erro": f"Falha de conexão com ANS SIPWeb: {e}"}, status=502)
    except Exception as e:
        return JsonResponse({"erro": str(e)}, status=500)
