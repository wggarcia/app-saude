import uuid
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import Empresa, EmpresaUsuario, PasswordResetToken

logger = logging.getLogger(__name__)

_TOKEN_TTL_HOURS = 2


def _encontrar_por_email(email):
    """Returns (empresa_or_none, usuario_or_none) for the given email."""
    usuario = EmpresaUsuario.objects.filter(email__iexact=email, ativo=True).first()
    if usuario:
        return None, usuario
    empresa = Empresa.objects.filter(email__iexact=email).first()
    if empresa:
        return empresa, None
    return None, None


def _criar_token(empresa, usuario):
    expira_em = timezone.now() + timedelta(hours=_TOKEN_TTL_HOURS)
    return PasswordResetToken.objects.create(
        empresa=empresa,
        usuario=usuario,
        expira_em=expira_em,
    )


def _enviar_email_reset(email, nome, token_obj):
    link = f"{settings.PUBLIC_BASE_URL}/redefinir-senha/{token_obj.token}/"
    assunto = "Redefinição de senha — SolusCRT"
    corpo_text = (
        f"Olá, {nome}!\n\n"
        f"Recebemos uma solicitação para redefinir a senha da sua conta SolusCRT.\n\n"
        f"Clique no link abaixo para criar uma nova senha (válido por {_TOKEN_TTL_HOURS}h):\n"
        f"{link}\n\n"
        f"Se você não solicitou isso, ignore este e-mail — sua senha não será alterada.\n\n"
        f"Equipe SolusCRT"
    )
    corpo_html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:0 auto;color:#1a2840">
      <div style="background:linear-gradient(135deg,#03111d,#0e2840);padding:28px 32px;border-radius:16px 16px 0 0;text-align:center">
        <span style="font-size:1.5rem;font-weight:800;color:#50e0d0">SolusCRT</span>
      </div>
      <div style="background:#f7faff;padding:32px;border-radius:0 0 16px 16px;border:1px solid #dce8f5">
        <p style="margin:0 0 16px;font-size:1rem">Olá, <strong>{nome}</strong>!</p>
        <p style="margin:0 0 24px;color:#4a6080">
          Recebemos uma solicitação para redefinir a senha da sua conta SolusCRT.
          Clique no botão abaixo para criar uma nova senha.
        </p>
        <div style="text-align:center;margin:24px 0">
          <a href="{link}" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#50e0d0,#4d78ff);color:#04131f;font-weight:700;border-radius:999px;text-decoration:none;font-size:1rem">
            Redefinir minha senha
          </a>
        </div>
        <p style="font-size:0.82rem;color:#7a92aa;margin:24px 0 0">
          Este link expira em {_TOKEN_TTL_HOURS} horas. Se você não solicitou isso, ignore este e-mail.
        </p>
        <p style="font-size:0.8rem;color:#aabccc;margin:8px 0 0;word-break:break-all">{link}</p>
      </div>
    </div>
    """
    try:
        send_mail(assunto, corpo_text, settings.DEFAULT_FROM_EMAIL, [email], html_message=corpo_html)
    except Exception as e:
        logger.error("Falha ao enviar email de reset para %s: %s", email, e)


def solicitar_reset_senha(request):
    if request.method == "GET":
        return render(request, "solicitar_reset_senha.html")

    email = (request.POST.get("email") or "").strip().lower()
    if not email:
        return render(request, "solicitar_reset_senha.html", {"erro": "Informe seu e-mail."})

    empresa, usuario = _encontrar_por_email(email)

    if empresa or usuario:
        token_obj = _criar_token(empresa, usuario)
        nome = usuario.nome if usuario else empresa.nome
        _enviar_email_reset(email, nome, token_obj)

    # Always show the same page to prevent email enumeration
    return render(request, "verificar_email_reset.html", {"email": email})


def redefinir_senha(request, token_str):
    try:
        token_uuid = uuid.UUID(str(token_str))
        token_obj = PasswordResetToken.objects.select_related("empresa", "usuario").get(
            token=token_uuid,
            usado=False,
        )
    except (PasswordResetToken.DoesNotExist, ValueError):
        return render(request, "nova_senha.html", {"erro": "Link inválido ou já utilizado."})

    if timezone.now() > token_obj.expira_em:
        return render(request, "nova_senha.html", {"erro": "Este link expirou. Solicite um novo."})

    if request.method == "GET":
        return render(request, "nova_senha.html", {"token": token_str})

    senha1 = request.POST.get("senha", "")
    senha2 = request.POST.get("senha_confirm", "")

    if len(senha1) < 8:
        return render(request, "nova_senha.html", {"token": token_str, "erro": "A senha deve ter pelo menos 8 caracteres."})
    if senha1 != senha2:
        return render(request, "nova_senha.html", {"token": token_str, "erro": "As senhas não coincidem."})

    nova_senha = make_password(senha1)

    if token_obj.usuario:
        token_obj.usuario.senha = nova_senha
        token_obj.usuario.save(update_fields=["senha"])
    elif token_obj.empresa:
        token_obj.empresa.senha = nova_senha
        token_obj.empresa.save(update_fields=["senha"])

    token_obj.usado = True
    token_obj.save(update_fields=["usado"])

    return redirect("/reset-senha-sucesso/")


def reset_senha_sucesso(request):
    return render(request, "reset_senha_sucesso.html")
