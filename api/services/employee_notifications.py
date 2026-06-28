import logging
from collections import defaultdict

from django.utils import timezone

from api.models import NotificacaoFuncionario

logger = logging.getLogger(__name__)


def criar_notificacao_funcionario(funcionario, empresa, tipo, titulo, mensagem, referencia_id=None):
    try:
        return NotificacaoFuncionario.objects.create(
            funcionario=funcionario,
            empresa=empresa,
            tipo=tipo,
            titulo=titulo[:200],
            mensagem=mensagem.strip(),
            referencia_id=referencia_id,
        )
    except Exception:
        logger.exception(
            "Falha ao criar notificacao do funcionario %s para referencia %s",
            getattr(funcionario, "id", None),
            referencia_id,
        )
        return None


def notificar_assinatura_sst(assinatura):
    funcionario = assinatura.funcionario
    if not funcionario:
        return None

    tipo_label = assinatura.get_tipo_documento_display()
    finalidade = assinatura.finalidade_assinatura or ""
    if finalidade == "entrega_documento":
        titulo = f"{tipo_label} disponível para download"
        mensagem = (
            f"A {assinatura.empresa.nome} disponibilizou seu {assinatura.titulo}. "
            "Abra o link para baixar o PDF com seu histórico completo de SST."
        )
    elif finalidade == "ciencia_trabalhador":
        titulo = f"{tipo_label} aguardando sua ciência"
        mensagem = (
            f"A {assinatura.empresa.nome} enviou {assinatura.titulo} para sua ciência. "
            "Abra pelo app, confira os dados e assine eletronicamente."
        )
    else:
        titulo = f"{tipo_label} aguardando assinatura"
        mensagem = (
            f"A {assinatura.empresa.nome} enviou {assinatura.titulo} para assinatura eletrônica. "
            "Abra pelo app, confira os dados e conclua o aceite."
        )

    return criar_notificacao_funcionario(
        funcionario,
        assinatura.empresa,
        NotificacaoFuncionario.TIPO_ASSINATURA_SST,
        titulo,
        mensagem,
        referencia_id=assinatura.id,
    )


def notificar_solicitacao_exame(solicitacao, evento):
    funcionario = solicitacao.funcionario
    empresa = solicitacao.empresa
    clinica_nome = (
        solicitacao.clinica.nome
        if getattr(solicitacao, "clinica", None)
        else solicitacao.clinica_nome_externo or "clínica ocupacional"
    )
    tipo_label = solicitacao.get_tipo_aso_display()

    if evento == "criada":
        mensagem = (
            f"Seu pedido de exame {tipo_label.lower()} foi aberto pela {empresa.nome}. "
            f"Destino: {clinica_nome}. Acompanhe o status no app."
        )
        return criar_notificacao_funcionario(
            funcionario,
            empresa,
            "exame",
            "Pedido de exame criado",
            mensagem,
            referencia_id=solicitacao.id,
        )

    if evento == "agendado":
        data_txt = solicitacao.data_agendamento.strftime("%d/%m/%Y") if solicitacao.data_agendamento else "data em definição"
        mensagem = (
            f"Seu exame {tipo_label.lower()} foi agendado para {data_txt} em {clinica_nome}. "
            f"{(solicitacao.resposta_clinica or '').strip()}".strip()
        )
        return criar_notificacao_funcionario(
            funcionario,
            empresa,
            "exame",
            "Exame agendado",
            mensagem,
            referencia_id=solicitacao.id,
        )

    if evento == "realizado":
        data_txt = solicitacao.data_realizacao.strftime("%d/%m/%Y") if solicitacao.data_realizacao else timezone.localdate().strftime("%d/%m/%Y")
        mensagem = (
            f"Seu exame {tipo_label.lower()} foi marcado como realizado em {data_txt}. "
            f"A empresa será avisada para concluir o ciclo ocupacional."
        )
        return criar_notificacao_funcionario(
            funcionario,
            empresa,
            "exame",
            "Exame realizado",
            mensagem,
            referencia_id=solicitacao.id,
        )

    if evento == "cancelado":
        mensagem = (
            f"Seu pedido de exame {tipo_label.lower()} foi cancelado. "
            f"{(solicitacao.resposta_clinica or '').strip()}".strip()
        )
        return criar_notificacao_funcionario(
            funcionario,
            empresa,
            "exame",
            "Pedido de exame cancelado",
            mensagem,
            referencia_id=solicitacao.id,
        )

    return None


def status_notificacoes_por_referencia(empresa, referencia_ids, tipo="exame"):
    status = defaultdict(lambda: {"app_notificado": False, "app_notificacoes": 0, "app_ultimo_envio": None})
    if not referencia_ids:
        return status

    notificacoes = (
        NotificacaoFuncionario.objects
        .filter(empresa=empresa, tipo=tipo, referencia_id__in=referencia_ids)
        .values("referencia_id", "criado_em")
        .order_by("criado_em")
    )
    for item in notificacoes:
        ref = item["referencia_id"]
        status[ref]["app_notificado"] = True
        status[ref]["app_notificacoes"] += 1
        status[ref]["app_ultimo_envio"] = timezone.localtime(item["criado_em"]).strftime("%d/%m/%Y %H:%M")
    return status


def solicitacao_portal_dict(solicitacao):
    clinica_nome = (
        solicitacao.clinica.nome
        if getattr(solicitacao, "clinica", None)
        else solicitacao.clinica_nome_externo or "Clínica ocupacional"
    )
    exames = []
    try:
        import json
        exames = json.loads(solicitacao.exames) if solicitacao.exames else []
    except Exception:
        exames = []

    return {
        "id": solicitacao.id,
        "tipo_aso": solicitacao.tipo_aso,
        "tipo_aso_label": solicitacao.get_tipo_aso_display(),
        "clinica_nome": clinica_nome,
        "status": solicitacao.status,
        "status_label": solicitacao.get_status_display(),
        "data_solicitacao": timezone.localtime(solicitacao.data_solicitacao).isoformat() if solicitacao.data_solicitacao else None,
        "data_agendamento": solicitacao.data_agendamento.isoformat() if solicitacao.data_agendamento else None,
        "data_realizacao": solicitacao.data_realizacao.isoformat() if solicitacao.data_realizacao else None,
        "urgente": solicitacao.urgente,
        "exames": exames,
        "observacoes": solicitacao.observacoes,
        "email_enviado": solicitacao.email_enviado,
        "resposta_clinica": solicitacao.resposta_clinica,
    }
