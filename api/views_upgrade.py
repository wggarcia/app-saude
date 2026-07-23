"""
Upgrade de plano self-service — SoloCRT
A gerência pode fazer upgrade diretamente pela plataforma, sem ligar para o suporte.

Endpoints:
  GET  /api/plano/upgrade/opcoes   — planos disponíveis para upgrade (filtrado por setor)
  POST /api/plano/upgrade/checkout — cria cobrança Asaas e retorna URL de pagamento
"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .access_control import api_requer_gerencia
from .planos import PACOTES_SAAS, detalhes_pacote, normalizar_codigo_pacote


# ── Mapeamento de features legíveis por plano ─────────────────────────────────

_FEATURES_LABEL = {
    "empresa_starter_5": {
        "included": [
            "ASO / Exames médicos ocupacionais",
            "Gestão de EPIs com rastreabilidade",
            "Treinamentos NR (controle e vencimentos)",
            "eSocial S-2220 / S-2240 / S-2210",
            "CAT — Comunicação de Acidente de Trabalho",
            "Afastamentos e controle de licenças",
            "App do funcionário (iOS + Android)",
            "Relatórios SST básicos",
        ],
        "excluded": [
            "PGR gerado automaticamente",
            "PCMSO gerado automaticamente",
            "CIPA — Módulo dedicado NR-5",
            "Biometria facial para entrega de EPI",
            "Psicossocial NR-01",
            "Multi-unidade / filiais",
            "Analytics avançado",
        ],
    },
    "empresa_profissional_25": {
        "included": [
            "Tudo do Starter",
            "PGR gerado automaticamente",
            "PCMSO gerado automaticamente",
            "CIPA — eleições, atas, reuniões (NR-5)",
            "Biometria facial para entrega de EPI",
            "Psicossocial NR-01 (questionários anônimos)",
            "Até 250 funcionários",
            "25 usuários simultâneos",
        ],
        "excluded": [
            "Multi-unidade / filiais",
            "Analytics corporativo",
        ],
    },
    "empresa_enterprise_100": {
        "included": [
            "Tudo do Profissional",
            "Multi-unidade (até 5 filiais)",
            "100 usuários simultâneos",
            "Até 1.000 funcionários",
            "Analytics e dashboards avançados",
            "Gestão FAP / LTCAT",
            "Conformidade NR consolidada",
        ],
        "excluded": [],
    },
    "empresa_corporativo_250": {
        "included": [
            "Tudo do Enterprise",
            "Até 20 unidades / filiais",
            "250 usuários",
            "Até 5.000 funcionários",
            "Dashboards corporativos consolidados",
            "Suporte prioritário",
        ],
        "excluded": [],
    },
    "empresa_nacional_500": {
        "included": [
            "Tudo do Corporativo",
            "Operação nacional — até 50 unidades",
            "500 usuários",
            "Até 10.000 funcionários",
            "Gerente de conta dedicado",
        ],
        "excluded": [],
    },
}

def _plano_index(codigo):
    """
    Posição do plano dentro da ordem crescente de preço do seu setor.
    Genérico por setor (não hardcoded por código) — funciona para qualquer
    setor (empresa, hospital, farmacia, governo, plano_saude, rede) e para
    novos pacotes adicionados a PACOTES_SAAS sem precisar atualizar este arquivo.
    """
    codigo = normalizar_codigo_pacote(codigo)
    pacote = PACOTES_SAAS.get(codigo)
    if not pacote:
        return -1
    setor = pacote.get("setor")
    ordenados = sorted(
        (c for c, p in PACOTES_SAAS.items() if p.get("setor") == setor),
        key=lambda c: PACOTES_SAAS[c]["mensal"],
    )
    try:
        return ordenados.index(codigo)
    except ValueError:
        return -1


# ── Views ─────────────────────────────────────────────────────────────────────

@api_requer_gerencia
def api_upgrade_opcoes(request):
    """
    GET /api/plano/upgrade/opcoes
    Retorna os planos disponíveis para upgrade da empresa autenticada.
    Inclui o plano atual marcado e somente planos superiores habilitados.
    """
    empresa = request.empresa
    plano_atual = normalizar_codigo_pacote(empresa.pacote_codigo)
    pacote_atual = detalhes_pacote(plano_atual)
    setor_atual = pacote_atual.get("setor", "empresa")
    idx_atual = _plano_index(plano_atual)

    opcoes = []
    for codigo, pacote in PACOTES_SAAS.items():
        if pacote.get("setor") != setor_atual:
            continue
        idx = _plano_index(normalizar_codigo_pacote(codigo))
        if idx <= idx_atual:
            continue  # não mostra downgrades nem plano atual
        features = _FEATURES_LABEL.get(codigo, {})
        opcoes.append({
            "codigo": codigo,
            "label": pacote["label"],
            "descricao": pacote.get("descricao", ""),
            "usuarios": pacote["usuarios"],
            "funcionarios": pacote.get("limites", {}).get("max_funcionarios", "ilimitado"),
            "mensal": pacote["mensal"],
            "anual": pacote["anual"],
            "ciclos": pacote.get("ciclos", ["mensal", "anual"]),
            "features_incluidas": features.get("included", []),
            "features_nao_incluidas": features.get("excluded", []),
            "destaque": idx == idx_atual + 1,  # marca o próximo plano como recomendado
        })

    return JsonResponse({
        "plano_atual": {
            "codigo": plano_atual,
            "label": pacote_atual.get("label", plano_atual),
            "mensal": pacote_atual.get("mensal", 0),
        },
        "opcoes": opcoes,
    })


@csrf_exempt
@api_requer_gerencia
def api_upgrade_checkout(request):
    """
    POST /api/plano/upgrade/checkout
    Body: { "pacote_codigo": "empresa_profissional_25", "ciclo": "mensal", "cpf_cnpj": "12345678000100" }
    Cria cobrança no Asaas e retorna URL de checkout.
    """
    if request.method != "POST":
        return JsonResponse({"erro": "Use POST"}, status=405)

    empresa = request.empresa

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)

    pacote_codigo = (data.get("pacote_codigo") or "").strip()
    ciclo = (data.get("ciclo") or "mensal").strip().lower()
    cpf_cnpj = (data.get("cpf_cnpj") or "").strip().replace(".", "").replace("/", "").replace("-", "")

    # ── Validações ──────────────────────────────────────────────────────────
    if not pacote_codigo:
        return JsonResponse({"erro": "Informe o plano desejado."}, status=400)

    pacote = PACOTES_SAAS.get(pacote_codigo)
    if not pacote:
        return JsonResponse({"erro": "Plano não encontrado."}, status=404)

    pacote_atual = detalhes_pacote(empresa.pacote_codigo)
    if pacote.get("setor") != pacote_atual.get("setor"):
        return JsonResponse({"erro": "Plano de setor diferente do atual."}, status=400)

    idx_novo = _plano_index(pacote_codigo)
    idx_atual = _plano_index(empresa.pacote_codigo)
    if idx_novo <= idx_atual:
        return JsonResponse({"erro": "Selecione um plano superior ao atual."}, status=400)

    if ciclo not in ("mensal", "anual"):
        return JsonResponse({"erro": "Ciclo deve ser 'mensal' ou 'anual'."}, status=400)

    valor = pacote.get("anual" if ciclo == "anual" else "mensal", 0)
    if not valor or valor <= 0:
        return JsonResponse({"erro": "Valor não configurado para este plano/ciclo."}, status=400)

    if len(cpf_cnpj) not in (11, 14):
        return JsonResponse({"erro": "Informe CPF (11 dígitos) ou CNPJ (14 dígitos) válido do responsável financeiro."}, status=400)

    # ── Cria cobrança Asaas via infraestrutura existente ─────────────────────
    try:
        from .views_pagamento import (
            _asaas_criar_pagamento,
            _atualizar_contrato_empresa,
            _registrar_evento_financeiro,
        )

        _atualizar_contrato_empresa(empresa, pacote_codigo, ciclo, pacote)
        _registrar_evento_financeiro(
            empresa, "upgrade_checkout_iniciado", "pendente", valor,
            f"Upgrade para {pacote['label']} — {ciclo.upper()} (self-service)"
        )

        payment_id, checkout_url = _asaas_criar_pagamento(
            empresa,
            valor,
            f"SoloCRT — {pacote['label']} ({ciclo.upper()})",
            cpf_cnpj,
        )

        _registrar_evento_financeiro(
            empresa, "upgrade_checkout_criado", "pendente", valor,
            f"Asaas payment_id={payment_id}"
        )

        return JsonResponse({
            "ok": True,
            "checkout_url": checkout_url,
            "payment_id": payment_id,
            "plano": pacote["label"],
            "valor": valor,
            "ciclo": ciclo,
        })

    except Exception as exc:
        try:
            _registrar_evento_financeiro(
                empresa, "upgrade_checkout_erro", "erro", valor,
                f"Asaas: {str(exc)[:800]}"
            )
        except Exception:
            pass
        return JsonResponse({"erro": f"Erro ao processar pagamento: {exc}"}, status=500)
