"""
Step-up de 2FA na entrada do console de TI.

O 2FA continua opt-in: quem NÃO ativou não é afetado em nada — nem no login,
nem no console. Quem ativou precisa confirmar um código do app autenticador
(ou um backup code) ao entrar no console de TI, não no login global.

A confirmação vale 12h e vive num cookie assinado (HMAC com a SECRET_KEY),
httponly, amarrado à sessão ativa do principal: novo login, logout ou
revogação de dispositivo derrubam o step-up junto. O cookie não guarda
segredo nenhum — só a identidade assinada de quem confirmou.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.utils import timezone

COOKIE = "ti_stepup"
SALT = "soluscrt.ti.stepup.v1"
VALIDADE = 12 * 60 * 60  # segundos
LIMITE_FALHAS = 5
BLOQUEIO = timedelta(minutes=5)


def principal_2fa(request):
    """(empresa, usuario|None) do principal logado. usuario=None => conta principal."""
    empresa = getattr(request, "empresa", None)
    principal = getattr(request, "principal", None)
    usuario = principal if (principal is not None and principal.__class__.__name__ == "EmpresaUsuario") else None
    return empresa, usuario


def config_ativa(empresa, usuario):
    """Configuração de 2FA ATIVA do principal, ou None."""
    from ..models import TwoFactorTOTP
    if not empresa:
        return None
    return TwoFactorTOTP.objects.filter(empresa=empresa, usuario=usuario, ativo=True).first()


def _identidade(request, empresa, usuario):
    """Valor assinado no cookie: empresa + usuário + marca da sessão ativa."""
    principal = getattr(request, "principal", None) or empresa
    chave_sessao = getattr(principal, "sessao_ativa_chave", "") or ""
    marca = hashlib.sha256(chave_sessao.encode()).hexdigest()[:16] if chave_sessao else "sem-sessao"
    return f"{getattr(empresa, 'id', 0)}:{getattr(usuario, 'id', 0) or 0}:{marca}"


def confirmado(request, empresa, usuario):
    bruto = request.COOKIES.get(COOKIE)
    if not bruto:
        return False
    try:
        valor = signing.loads(bruto, salt=SALT, max_age=VALIDADE)
    except signing.BadSignature:
        return False
    return valor == _identidade(request, empresa, usuario)


def pendente(request):
    """True só quando o principal ativou o 2FA e ainda não confirmou nesta sessão."""
    empresa, usuario = principal_2fa(request)
    if not empresa:
        return False
    if not config_ativa(empresa, usuario):
        return False
    return not confirmado(request, empresa, usuario)


def marcar(response, request, empresa, usuario):
    """Registra o step-up confirmado na resposta."""
    response.set_cookie(
        COOKIE,
        signing.dumps(_identidade(request, empresa, usuario), salt=SALT),
        max_age=VALIDADE,
        httponly=True,
        samesite="Lax",
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
    )
    return response


def limpar(response):
    response.delete_cookie(COOKIE)
    return response


# ── Anti-força-bruta ──────────────────────────────────────────────────────────
#
# 6 dígitos são 1 em 1 milhão por tentativa: sem throttling o código cai por
# força bruta. A RFC 4226 §7.3 exige o limite. 5 falhas => 5 min de bloqueio.

def bloqueio_restante(cfg) -> int:
    """Segundos restantes de bloqueio (0 = liberado)."""
    if not cfg or not cfg.bloqueado_ate:
        return 0
    restante = (cfg.bloqueado_ate - timezone.now()).total_seconds()
    return int(restante) if restante > 0 else 0


def registrar_falha(cfg) -> int:
    """Conta a falha e bloqueia no limite. Devolve os segundos de bloqueio."""
    cfg.falhas_2fa = (cfg.falhas_2fa or 0) + 1
    campos = ["falhas_2fa", "atualizado_em"]
    if cfg.falhas_2fa >= LIMITE_FALHAS:
        cfg.bloqueado_ate = timezone.now() + BLOQUEIO
        cfg.falhas_2fa = 0
        campos.append("bloqueado_ate")
    cfg.save(update_fields=campos)
    return bloqueio_restante(cfg)


def registrar_sucesso(cfg) -> None:
    cfg.falhas_2fa = 0
    cfg.bloqueado_ate = None
    cfg.save(update_fields=["falhas_2fa", "bloqueado_ate", "atualizado_em"])
