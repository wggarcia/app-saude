"""
Helper para registrar acesso a dado clínico na trilha imutável (AuditoriaClinica).

Uso nas views clínicas:
    from api.services.auditoria_clinica import registrar_acesso_clinico
    registrar_acesso_clinico(request, "visualizar", "prontuario", prontuario.id,
                             paciente_ref=prontuario.paciente_nome)

Nunca deve derrubar a request: qualquer falha ao auditar é logada e engolida
(a ausência de um registro é preferível a negar atendimento clínico) — mas o
caminho feliz sempre grava.
"""
import logging

logger = logging.getLogger(__name__)


def _client_ip(request):
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return xff or request.META.get("REMOTE_ADDR") or None


def _principal_info(request):
    empresa = getattr(request, "empresa", None)
    principal = getattr(request, "principal", None) or empresa
    if principal is None:
        return empresa, "sistema", "", ""
    tipo = principal.__class__.__name__
    pid = str(getattr(principal, "id", "") or "")
    nome = (getattr(principal, "nome", "") or getattr(principal, "email", "") or "")
    return empresa, tipo, pid, nome


def registrar_acesso_clinico(request, acao, recurso, recurso_id="",
                             paciente_ref="", detalhes=None):
    """Grava um registro na trilha clínica imutável. Retorna o objeto ou None."""
    try:
        from api.models import AuditoriaClinica
        empresa, tipo, pid, nome = _principal_info(request)
        if empresa is None:
            return None
        return AuditoriaClinica.objects.create(
            empresa=empresa,
            principal_tipo=tipo,
            principal_id=pid,
            principal_nome=nome,
            acao=acao,
            recurso=recurso,
            recurso_id=str(recurso_id or ""),
            paciente_ref=str(paciente_ref or "")[:120],
            ip=_client_ip(request),
            user_agent=(request.headers.get("User-Agent") or "")[:1000],
            detalhes=detalhes or {},
        )
    except Exception as exc:  # nunca derruba a request clínica por causa da auditoria
        logger.warning("Falha ao registrar auditoria clínica (%s %s): %s", acao, recurso, exc)
        return None
