"""
Antifraude de Cadastro Social cross-município — CRAS / CadÚnico.

Cada município é um tenant isolado por RLS (empresa_id): por padrão nenhum
município enxerga o cadastro social de outro. Este módulo é a ÚNICA exceção
deliberada a essa regra, e é estreita de propósito: mantém um índice central
(IndiceCadastroSocial, sem empresa_id — por isso fora do alcance do RLS) que
guarda só CPF/NIS + qual empresa está com o cadastro ATIVO hoje.

Comportamento (especificado pelo usuário):
  1. Uma pessoa pode sempre se cadastrar num novo município — nunca bloqueia.
  2. Se a mesma pessoa (CPF, senão NIS) já tiver cadastro ATIVO em OUTRA
     empresa, o cadastro antigo é suspenso automaticamente (nunca apagado —
     fica com situacao="suspensa" + motivo_suspensao, histórico preservado).
  3. Os dois gestores são notificados (AlertaAntifraudeSocial).
  4. O gestor antigo pode contestar/reativar (ver `contestar_suspensao`).

Limitação conhecida: cruza só entre tenants do próprio SoloCRT. Não há
integração ao vivo com CadÚnico/CadSUS federal — e o fluxo de IMPORTAÇÃO EM
LOTE do CadÚnico (api_cadunico_importar_lote) não passa por aqui ainda; só o
cadastro interativo de FamiliaCRAS é coberto nesta primeira versão.

NUNCA exponha IndiceCadastroSocial via API pública ou por tenant — só este
módulo deve tocar nele, sempre pela conexão "owner" (bypassa RLS).
"""
import logging

from django.db.models import Q

from ..models import AlertaAntifraudeSocial, Empresa, FamiliaCRAS, IndiceCadastroSocial

logger = logging.getLogger(__name__)

_OWNER_CACHE = {"checked": False, "ok": True}


def _owner_ok():
    """Mesmo padrão de fallback usado em api/epidemiologia.py: prefere a
    conexão "owner" (bypassa RLS); cai pra "default" se o papel do banco não
    tiver privilégio nela (ex.: VPS sem GRANT)."""
    if _OWNER_CACHE["checked"]:
        return _OWNER_CACHE["ok"]
    ok = True
    try:
        IndiceCadastroSocial.objects.using("owner").exists()
    except Exception:
        ok = False
    _OWNER_CACHE["checked"] = True
    _OWNER_CACHE["ok"] = ok
    return ok


def _idx_manager():
    return IndiceCadastroSocial.objects.using("owner") if _owner_ok() else IndiceCadastroSocial.objects


def _familia_manager():
    return FamiliaCRAS.objects.using("owner") if _owner_ok() else FamiliaCRAS.objects


def _empresa_manager():
    return Empresa.objects.using("owner") if _owner_ok() else Empresa.objects


def _alerta_manager():
    return AlertaAntifraudeSocial.objects.using("owner") if _owner_ok() else AlertaAntifraudeSocial.objects


def registrar_e_verificar_cadastro_social(*, cpf, nis, empresa, familia_id, nome_pessoa,
                                           modelo_origem="familia_cras"):
    """Chamar logo após criar um novo cadastro social (hoje: FamiliaCRAS).

    Nunca bloqueia o novo cadastro. Se a mesma pessoa já tiver um cadastro
    ATIVO em outra empresa, suspende o antigo e notifica os dois gestores.
    Sem efeito se não houver CPF nem NIS (nada pra cruzar).
    """
    cpf = (cpf or "").strip()
    nis = (nis or "").strip()
    if not cpf and not nis:
        return

    filtro = Q()
    if cpf:
        filtro |= Q(cpf=cpf)
    if nis:
        filtro |= Q(nis=nis)

    existente = _idx_manager().filter(filtro).order_by("-atualizado_em").first()
    agora = _tz_now()
    nome_municipio_novo = empresa.cidade or empresa.nome

    historico = list(existente.historico) if existente else []

    if existente and existente.empresa_ativa_id and existente.empresa_ativa_id != empresa.id:
        _suspender_registro_antigo(existente, nova_empresa=empresa,
                                    nome_municipio_novo=nome_municipio_novo, agora=agora)
        historico.append({
            "empresa_id": existente.empresa_ativa_id,
            "evento": "suspenso_por_recadastro",
            "data": agora.isoformat(),
        })

    historico.append({
        "empresa_id": empresa.id,
        "nome_municipio": nome_municipio_novo,
        "evento": "ativado",
        "data": agora.isoformat(),
    })

    if existente:
        existente.cpf = cpf or existente.cpf
        existente.nis = nis or existente.nis
        existente.nome_pessoa = nome_pessoa or existente.nome_pessoa
        existente.empresa_ativa_id = empresa.id
        existente.modelo_origem = modelo_origem
        existente.registro_ativo_id = familia_id
        existente.data_ativacao = agora
        existente.historico = historico
        existente.save(using="owner" if _owner_ok() else "default")
    else:
        _idx_manager().create(
            cpf=cpf, nis=nis, nome_pessoa=nome_pessoa, empresa_ativa_id=empresa.id,
            modelo_origem=modelo_origem, registro_ativo_id=familia_id,
            data_ativacao=agora, historico=historico,
        )


def _suspender_registro_antigo(indice, *, nova_empresa, nome_municipio_novo, agora):
    empresa_antiga_id = indice.empresa_ativa_id
    empresa_antiga = _empresa_manager().filter(id=empresa_antiga_id).first()
    motivo = f"Recadastrado em {nome_municipio_novo} em {agora.strftime('%d/%m/%Y')}."

    if not _owner_ok():
        logger.warning(
            "antifraude_residencia: conexão 'owner' indisponível — suspensão do registro %s "
            "da empresa %s roda pela 'default' (RLS) e pode não alcançar o outro município.",
            indice.registro_ativo_id, empresa_antiga_id,
        )

    if indice.modelo_origem == "familia_cras" and indice.registro_ativo_id:
        atualizados = _familia_manager().filter(
            id=indice.registro_ativo_id, empresa_id=empresa_antiga_id,
        ).update(situacao="suspensa", motivo_suspensao=motivo, suspenso_em=agora)
        if atualizados == 0:
            logger.warning(
                "antifraude_residencia: suspensão não aplicada — FamiliaCRAS %s da empresa %s "
                "não encontrada (owner=%s). Cadastro antigo segue ativo.",
                indice.registro_ativo_id, empresa_antiga_id, _owner_ok(),
            )

    nome_pessoa = indice.nome_pessoa or "Um cidadão"
    if empresa_antiga:
        _alerta_manager().create(
            empresa=empresa_antiga,
            tipo="suspensao_registro",
            titulo="Cadastro social suspenso — recadastro em outro município",
            mensagem=(
                f"O cadastro de {nome_pessoa} foi suspenso automaticamente porque a "
                f"pessoa se cadastrou em {nome_municipio_novo} em {agora.strftime('%d/%m/%Y')}. "
                "Se isso for engano (ex.: CPF/NIS duplicado por erro de digitação), "
                "use o botão Reativar na lista de Famílias do CRAS."
            ),
            cpf=indice.cpf, nis=indice.nis, registro_id=indice.registro_ativo_id,
        )

    nome_municipio_antigo = (empresa_antiga.cidade or empresa_antiga.nome) if empresa_antiga else "outro município"
    _alerta_manager().create(
        empresa=nova_empresa,
        tipo="registro_anterior_detectado",
        titulo="Cidadão com cadastro anterior em outro município",
        mensagem=(
            f"{nome_pessoa} tinha um cadastro social ativo em {nome_municipio_antigo} "
            f"até {agora.strftime('%d/%m/%Y')} — o registro antigo foi suspenso automaticamente."
        ),
        cpf=indice.cpf, nis=indice.nis, registro_id=indice.registro_ativo_id,
    )


def contestar_suspensao(*, familia, revisado_por=""):
    """Reativa um cadastro suspenso automaticamente por recadastro em outro
    município — usado quando o gestor confirma que foi engano (CPF/NIS
    colidiu por erro de digitação) ou um caso legítimo de duas residências.

    Opera só no tenant do próprio gestor (sem conexão "owner" — a família já
    pertence à empresa autenticada). Não mexe no índice nacional nem no
    cadastro da outra empresa.
    """
    agora = _tz_now()
    familia.situacao = "em_acompanhamento"
    familia.contestado_em = agora
    familia.contestado_por = revisado_por or ""
    familia.save(update_fields=["situacao", "contestado_em", "contestado_por"])
    return familia


def alerta_dict(a):
    return {
        "id": a.id,
        "tipo": a.tipo,
        "titulo": a.titulo,
        "mensagem": a.mensagem,
        "registro_id": a.registro_id,
        "lida": a.lida,
        "criado_em": a.criado_em.isoformat() if a.criado_em else None,
    }


def listar_alertas(empresa, incluir_lidas=False):
    qs = AlertaAntifraudeSocial.objects.filter(empresa=empresa)
    if not incluir_lidas:
        qs = qs.filter(lida=False)
    return [alerta_dict(a) for a in qs.order_by("-criado_em")[:100]]


def marcar_alerta_lido(empresa, alerta_id):
    return AlertaAntifraudeSocial.objects.filter(empresa=empresa, id=alerta_id).update(lida=True)


def _tz_now():
    from django.utils import timezone
    return timezone.now()
