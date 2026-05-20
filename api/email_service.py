"""
Email service — transactional emails sent by SolusCRT.
All calls are wrapped in try/except so email failures never break core flows.
"""
from django.conf import settings
from django.core.mail import send_mail


def _from():
    return getattr(settings, "DEFAULT_FROM_EMAIL", "SolusCRT <noreply@soluscrt.com.br>")


def enviar_email_boas_vindas(empresa):
    """Send welcome email immediately after empresa registration."""
    try:
        nome = empresa.nome
        email = empresa.email
        subject = "Bem-vindo ao SolusCRT — sua conta está pronta 🎉"
        body_html = f"""
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2eeff}}
.wrap{{max-width:600px;margin:0 auto;padding:32px 20px}}
.logo{{font-size:22px;font-weight:900;color:#00c9a7;letter-spacing:-0.5px;margin-bottom:32px}}
.card{{background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:32px}}
h1{{font-size:24px;font-weight:800;margin:0 0 8px}}
.sub{{color:#7b90b0;font-size:14px;margin-bottom:28px}}
.btn{{display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#00c9a7,#0077ff);
  color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;margin:20px 0}}
.steps{{margin:28px 0 0}}
.step{{display:flex;gap:14px;align-items:flex-start;margin-bottom:18px}}
.step-num{{width:28px;height:28px;background:rgba(0,201,167,.15);border:1px solid rgba(0,201,167,.3);
  border-radius:50%;display:flex;align-items:center;justify-content:center;
  color:#00c9a7;font-weight:800;font-size:13px;flex-shrink:0;margin-top:2px}}
.step-text{{font-size:14px;color:#e2eeff}}
.step-title{{font-weight:700;margin-bottom:3px}}
.step-desc{{color:#7b90b0;font-size:13px}}
.footer{{margin-top:28px;padding-top:20px;border-top:1px solid rgba(255,255,255,.07);
  font-size:12px;color:#7b90b0;text-align:center}}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">SolusCRT</div>
  <div class="card">
    <h1>Olá, {nome}! 👋</h1>
    <p class="sub">Sua conta SolusCRT está ativa e pronta para uso.</p>
    <p style="font-size:15px;line-height:1.6;color:#b0c4d8">
      Seja bem-vindo à plataforma de Saúde, Segurança do Trabalho e Inteligência Epidemiológica
      mais moderna do Brasil. Você está a poucos cliques de ter controle total sobre a saúde
      ocupacional da sua empresa.
    </p>
    <a href="https://app.soluscrt.com.br/login-empresa/" class="btn">Acessar minha conta →</a>
    <div class="steps">
      <p style="font-size:13px;font-weight:700;color:#7b90b0;text-transform:uppercase;letter-spacing:.08em;margin-bottom:16px">
        Primeiros passos recomendados
      </p>
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-text">
          <div class="step-title">Cadastre seus funcionários</div>
          <div class="step-desc">Adicione os dados de cada colaborador para começar a gestão de SST.</div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-text">
          <div class="step-title">Configure os ASOs e exames</div>
          <div class="step-desc">Registre os Atestados de Saúde Ocupacional e defina os prazos de validade.</div>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-text">
          <div class="step-title">Ative o monitoramento de eSocial</div>
          <div class="step-desc">Acompanhe o status dos eventos S-2210, S-2220 e S-2240 em tempo real.</div>
        </div>
      </div>
    </div>
  </div>
  <div class="footer">
    Precisa de ajuda? Entre em contato: <a href="mailto:suporte@soluscrt.com.br" style="color:#00c9a7">suporte@soluscrt.com.br</a><br>
    SolusCRT · Saúde Ocupacional e Inteligência Epidemiológica<br>
    <a href="https://soluscrt.com.br/privacidade/" style="color:#7b90b0">Política de Privacidade</a> ·
    <a href="https://soluscrt.com.br/termos/" style="color:#7b90b0">Termos de Uso</a>
  </div>
</div>
</body>
</html>
"""
        body_text = (
            f"Olá, {nome}!\n\n"
            "Sua conta SolusCRT está ativa e pronta para uso.\n\n"
            "Acesse: https://app.soluscrt.com.br/login-empresa/\n\n"
            "Primeiros passos:\n"
            "1. Cadastre seus funcionários\n"
            "2. Configure os ASOs e exames ocupacionais\n"
            "3. Ative o monitoramento de eSocial\n\n"
            "Suporte: suporte@soluscrt.com.br\n"
        )
        send_mail(
            subject=subject,
            message=body_text,
            from_email=_from(),
            recipient_list=[email],
            html_message=body_html,
            fail_silently=False,
        )
    except Exception:
        pass  # Email failure must never break registration


def enviar_email_trial_expirando(empresa, dias_restantes):
    """Send warning email 7 days (and 1 day) before trial expires."""
    try:
        base_url = _base_url()
        urgencia = "🔴 Urgente — " if dias_restantes <= 1 else "⏳ "
        subject = f"{urgencia}Seu trial SolusCRT expira em {dias_restantes} dia{'s' if dias_restantes != 1 else ''}"
        corpo_dias = (
            "Seu período de teste expira <strong>hoje</strong>."
            if dias_restantes <= 1
            else f"Seu período de teste expira em <strong>{dias_restantes} dias</strong>."
        )
        body_html = f"""
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2eeff}}
.wrap{{max-width:600px;margin:0 auto;padding:32px 20px}}
.logo{{font-size:22px;font-weight:900;color:#00c9a7;margin-bottom:32px}}
.card{{background:#111827;border:1px solid rgba(255,179,71,.3);border-radius:16px;padding:32px}}
.warn-bar{{background:rgba(255,179,71,.12);border:1px solid rgba(255,179,71,.3);border-radius:10px;
  padding:14px 18px;margin-bottom:24px;color:#ffd080;font-size:14px;font-weight:600}}
h1{{font-size:22px;font-weight:800;margin:0 0 12px}}
.btn{{display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#00c9a7,#0077ff);
  color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;margin:20px 0}}
.features{{margin:20px 0;display:flex;flex-direction:column;gap:8px}}
.feat{{display:flex;gap:10px;align-items:flex-start;font-size:14px;color:#b0c4d8}}
.feat-icon{{color:#00c9a7;font-size:16px;flex-shrink:0}}
.footer{{margin-top:24px;font-size:12px;color:#7b90b0;text-align:center}}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">SolusCRT</div>
  <div class="card">
    <div class="warn-bar">⏰ {corpo_dias}</div>
    <h1>Não perca o acesso, {empresa.nome}!</h1>
    <p style="font-size:14px;color:#b0c4d8;line-height:1.7;margin-bottom:16px">
      Você explorou o SolusCRT durante o período de teste. Para continuar com acesso completo
      à plataforma — EPIs, ASOs, eSocial, exames, dashboards e muito mais — ative sua assinatura agora.
    </p>
    <div class="features">
      <div class="feat"><span class="feat-icon">✓</span>Todos os módulos SST desbloqueados</div>
      <div class="feat"><span class="feat-icon">✓</span>Exportação de relatórios e eSocial</div>
      <div class="feat"><span class="feat-icon">✓</span>Suporte técnico incluso</div>
      <div class="feat"><span class="feat-icon">✓</span>Sem contratos longos — cancele quando quiser</div>
    </div>
    <a href="{base_url}/pagamento/" class="btn">Ativar minha assinatura →</a>
    <p style="font-size:13px;color:#7b90b0;margin-top:8px">
      Ou entre em contato: <a href="mailto:comercial@soluscrt.com.br" style="color:#00c9a7">comercial@soluscrt.com.br</a>
    </p>
  </div>
  <div class="footer">SolusCRT · <a href="mailto:suporte@soluscrt.com.br" style="color:#7b90b0">suporte@soluscrt.com.br</a></div>
</div>
</body>
</html>"""
        body_text = (
            f"SolusCRT — trial expira em {dias_restantes} dia(s)\n"
            f"Olá, {empresa.nome}!\n"
            f"Ative sua assinatura em: {base_url}/pagamento/\n"
            "Dúvidas: comercial@soluscrt.com.br\n"
        )
        send_mail(
            subject=subject,
            message=body_text,
            from_email=_from(),
            recipient_list=[empresa.email],
            html_message=body_html,
            fail_silently=False,
        )
    except Exception:
        pass


def enviar_email_trial_expirado(empresa):
    """Send email when trial has just expired."""
    try:
        base_url = _base_url()
        subject = "🔒 Seu acesso SolusCRT foi suspenso — reative agora"
        body_html = f"""
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2eeff}}
.wrap{{max-width:600px;margin:0 auto;padding:32px 20px}}
.logo{{font-size:22px;font-weight:900;color:#00c9a7;margin-bottom:32px}}
.card{{background:#111827;border:1px solid rgba(255,77,109,.3);border-radius:16px;padding:32px}}
.danger-bar{{background:rgba(255,77,109,.1);border:1px solid rgba(255,77,109,.3);border-radius:10px;
  padding:14px 18px;margin-bottom:24px;color:#ff8fa3;font-size:14px;font-weight:600}}
h1{{font-size:22px;font-weight:800;margin:0 0 12px}}
.btn{{display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#00c9a7,#0077ff);
  color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;margin:20px 0}}
.note{{font-size:13px;color:#7b90b0;margin-top:12px;line-height:1.6}}
.footer{{margin-top:24px;font-size:12px;color:#7b90b0;text-align:center}}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">SolusCRT</div>
  <div class="card">
    <div class="danger-bar">🔒 Período de trial encerrado — acesso suspenso</div>
    <h1>Seus dados estão seguros, {empresa.nome}</h1>
    <p style="font-size:14px;color:#b0c4d8;line-height:1.7">
      Seu período de avaliação gratuita do SolusCRT encerrou. Seus dados continuam armazenados
      e seguros — basta reativar a assinatura para retomar o acesso imediatamente.
    </p>
    <a href="{base_url}/pagamento/" class="btn">Reativar minha conta →</a>
    <p class="note">
      Seus dados ficam disponíveis por <strong>30 dias</strong> após o encerramento do trial.
      Após esse prazo, a conta pode ser encerrada definitivamente.<br><br>
      Quer conversar antes de decidir?
      <a href="mailto:comercial@soluscrt.com.br" style="color:#00c9a7">comercial@soluscrt.com.br</a>
    </p>
  </div>
  <div class="footer">SolusCRT · <a href="mailto:suporte@soluscrt.com.br" style="color:#7b90b0">suporte@soluscrt.com.br</a></div>
</div>
</body>
</html>"""
        body_text = (
            f"SolusCRT — trial expirado\n"
            f"Olá, {empresa.nome}!\n"
            "Seu período de avaliação encerrou. Seus dados estão seguros por 30 dias.\n"
            f"Reative em: {base_url}/pagamento/\n"
            "Dúvidas: comercial@soluscrt.com.br\n"
        )
        send_mail(
            subject=subject,
            message=body_text,
            from_email=_from(),
            recipient_list=[empresa.email],
            html_message=body_html,
            fail_silently=False,
        )
    except Exception:
        pass


def _base_url():
    from django.conf import settings
    return getattr(settings, "PUBLIC_BASE_URL", "https://app.soluscrt.com.br").rstrip("/")


def enviar_email_confirmacao_pagamento(empresa, plano_nome, valor):
    """Send payment confirmation after successful subscription activation."""
    try:
        subject = f"Confirmação de pagamento — {plano_nome}"
        body_html = f"""
<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="UTF-8">
<style>
body{{margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2eeff}}
.wrap{{max-width:600px;margin:0 auto;padding:32px 20px}}
.logo{{font-size:22px;font-weight:900;color:#00c9a7;margin-bottom:32px}}
.card{{background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:32px}}
h1{{font-size:22px;font-weight:800;margin:0 0 8px}}
.amount{{font-size:36px;font-weight:900;color:#00c9a7;margin:20px 0}}
.row{{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.07);font-size:14px}}
.label{{color:#7b90b0}}
.footer{{margin-top:28px;font-size:12px;color:#7b90b0;text-align:center}}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">SolusCRT</div>
  <div class="card">
    <h1>✅ Pagamento confirmado</h1>
    <p style="color:#7b90b0;font-size:14px;margin-bottom:20px">Sua assinatura está ativa.</p>
    <div class="amount">R$ {valor:,.2f}</div>
    <div class="row"><span class="label">Empresa</span><span>{empresa.nome}</span></div>
    <div class="row"><span class="label">Plano</span><span>{plano_nome}</span></div>
    <div class="row"><span class="label">Status</span><span style="color:#00c9a7">✓ Ativo</span></div>
    <p style="margin-top:24px;font-size:14px;color:#b0c4d8">
      Sua conta está ativa. Acesse o painel em
      <a href="https://app.soluscrt.com.br/login-empresa/" style="color:#00c9a7">app.soluscrt.com.br</a>.
    </p>
  </div>
  <div class="footer">Dúvidas? <a href="mailto:suporte@soluscrt.com.br" style="color:#00c9a7">suporte@soluscrt.com.br</a></div>
</div>
</body>
</html>
"""
        body_text = (
            f"Pagamento confirmado — {plano_nome}\n"
            f"Empresa: {empresa.nome}\n"
            f"Valor: R$ {valor:,.2f}\n"
            "Sua conta está ativa.\n"
            "Acesse: https://app.soluscrt.com.br/login-empresa/\n"
        )
        send_mail(
            subject=subject,
            message=body_text,
            from_email=_from(),
            recipient_list=[empresa.email],
            html_message=body_html,
            fail_silently=False,
        )
    except Exception:
        pass
