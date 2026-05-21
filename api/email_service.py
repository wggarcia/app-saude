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


# ════════════════════════════════════════════════════════════════════════════════
#  PLANO DE SAÚDE — Emails transacionais enterprise
# ════════════════════════════════════════════════════════════════════════════════

def _html_base(conteudo_card: str, titulo_rodape: str = "SolusCRT · Plano de Saúde") -> str:
    """Wrapper HTML com design system dark-mode usado em todos os emails."""
    return f"""<!DOCTYPE html>
<html lang="pt-br">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;color:#e2eeff}}
.wrap{{max-width:600px;margin:0 auto;padding:32px 20px}}
.logo{{font-size:22px;font-weight:900;color:#00c9a7;letter-spacing:-.5px;margin-bottom:32px}}
.card{{background:#111827;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:32px}}
h1{{font-size:22px;font-weight:800;margin:0 0 8px;line-height:1.3}}
.sub{{color:#7b90b0;font-size:14px;margin-bottom:22px}}
.btn{{display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#00c9a7,#0077ff);
  color:#fff;text-decoration:none;border-radius:10px;font-weight:700;font-size:15px;margin:20px 0}}
.row{{display:flex;justify-content:space-between;padding:10px 0;
  border-bottom:1px solid rgba(255,255,255,.07);font-size:14px}}
.lbl{{color:#7b90b0}}
.badge-ok{{display:inline-block;padding:3px 12px;background:rgba(0,229,176,.12);
  color:#00e5b0;border-radius:20px;font-size:12px;font-weight:700}}
.badge-warn{{display:inline-block;padding:3px 12px;background:rgba(255,179,71,.12);
  color:#ffb347;border-radius:20px;font-size:12px;font-weight:700}}
.badge-err{{display:inline-block;padding:3px 12px;background:rgba(255,77,109,.12);
  color:#ff4d6d;border-radius:20px;font-size:12px;font-weight:700}}
.info-bar{{background:rgba(0,201,167,.08);border:1px solid rgba(0,201,167,.2);
  border-radius:10px;padding:14px 18px;margin:18px 0;font-size:14px;color:#a0dfd4;line-height:1.6}}
.warn-bar{{background:rgba(255,179,71,.08);border:1px solid rgba(255,179,71,.25);
  border-radius:10px;padding:14px 18px;margin:18px 0;font-size:14px;color:#ffd080;line-height:1.6}}
.err-bar{{background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.25);
  border-radius:10px;padding:14px 18px;margin:18px 0;font-size:14px;color:#ff8fa3;line-height:1.6}}
.tag{{display:inline-block;background:rgba(255,77,109,.1);color:#ff8fa3;
  border:1px solid rgba(255,77,109,.2);border-radius:20px;padding:2px 10px;
  font-size:12px;font-weight:700;margin:2px 3px}}
.footer{{margin-top:28px;padding-top:20px;border-top:1px solid rgba(255,255,255,.07);
  font-size:12px;color:#7b90b0;text-align:center;line-height:1.8}}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">SolusCRT</div>
  <div class="card">
    {conteudo_card}
  </div>
  <div class="footer">
    {titulo_rodape}<br>
    <a href="https://soluscrt.com.br/privacidade/" style="color:#7b90b0">Privacidade</a> ·
    <a href="https://soluscrt.com.br/termos/" style="color:#7b90b0">Termos</a> ·
    <a href="mailto:suporte@soluscrt.com.br" style="color:#00c9a7">suporte@soluscrt.com.br</a>
  </div>
</div>
</body>
</html>"""


def _send(subject: str, to: str, html: str, text: str) -> None:
    """Helper de envio. Falha silenciosamente para não quebrar fluxos."""
    try:
        send_mail(
            subject=subject,
            message=text,
            from_email=_from(),
            recipient_list=[to],
            html_message=html,
            fail_silently=False,
        )
    except Exception:
        pass


# ── 1. Novo Contrato Corporativo ──────────────────────────────────────────────

def enviar_email_novo_contrato(contrato) -> None:
    """Email para a operadora quando um contrato corporativo é cadastrado.

    Args:
        contrato: instância de ContratoGrupo
    """
    base_url = _base_url()
    empresa = contrato.empresa_operadora
    dias_renovacao = (contrato.data_renovacao - __import__('datetime').date.today()).days

    card = f"""
    <h1>📑 Novo contrato corporativo cadastrado</h1>
    <p class="sub">O contrato foi registrado com sucesso na plataforma.</p>
    <div class="row"><span class="lbl">Empresa cliente</span><strong>{contrato.razao_social}</strong></div>
    <div class="row"><span class="lbl">CNPJ</span><span>{contrato.cnpj or '—'}</span></div>
    <div class="row"><span class="lbl">Plano contratado</span><span>{contrato.plano.nome}</span></div>
    <div class="row"><span class="lbl">Total de vidas</span><strong>{contrato.total_vidas}</strong></div>
    <div class="row"><span class="lbl">Mensalidade</span><strong>R$ {float(contrato.mensalidade_total):,.2f}</strong></div>
    <div class="row"><span class="lbl">Início</span><span>{contrato.data_inicio.strftime('%d/%m/%Y')}</span></div>
    <div class="row"><span class="lbl">Renovação</span>
      <span style="color:{'#ffb347' if dias_renovacao < 90 else '#00e5b0'}">
        {contrato.data_renovacao.strftime('%d/%m/%Y')} ({dias_renovacao}d)
      </span>
    </div>
    <div class="row"><span class="lbl">Status</span><span class="badge-ok">Ativo</span></div>
    <div class="info-bar">
      💡 Lembre-se de cadastrar os beneficiários desta empresa na aba
      <strong>Beneficiários</strong> para que eles possam utilizar o plano imediatamente.
    </div>
    <a href="{base_url}/plano-saude/gestao/" class="btn">Ver no painel →</a>
    """
    html = _html_base(card, f"SolusCRT · Operadora — {empresa.nome}")
    text = (
        f"Novo contrato corporativo cadastrado\n"
        f"Empresa: {contrato.razao_social}\n"
        f"Plano: {contrato.plano.nome}\n"
        f"Vidas: {contrato.total_vidas}\n"
        f"Mensalidade: R$ {float(contrato.mensalidade_total):,.2f}\n"
        f"Renovação: {contrato.data_renovacao.strftime('%d/%m/%Y')}\n"
        f"Painel: {base_url}/plano-saude/gestao/\n"
    )
    _send(
        subject=f"📑 Contrato corporativo cadastrado — {contrato.razao_social}",
        to=empresa.email,
        html=html,
        text=text,
    )


# ── 2. Teleconsulta Autorizada ────────────────────────────────────────────────

def enviar_email_teleconsulta_autorizada(tele) -> None:
    """Email para o beneficiário quando a teleconsulta é autorizada.

    Args:
        tele: instância de TeleconsultaAutorizacao
    """
    beneficiario = tele.beneficiario
    email_dest = beneficiario.email
    if not email_dest:
        return

    plat_labels = {
        "conexa": "Conexa Saúde",
        "iclinic": "iClinic Telemedicina",
        "drconsulta": "Dr. Consulta",
        "outro": "Plataforma de vídeo",
    }
    plat = plat_labels.get(tele.plataforma, tele.plataforma)
    data_str = (
        tele.data_agendada.strftime("%d/%m/%Y às %H:%M")
        if tele.data_agendada else "A definir — aguarde contato da clínica"
    )
    link_html = (
        f'<a href="{tele.link_consulta}" class="btn">Entrar na consulta →</a>'
        if tele.link_consulta
        else '<p style="color:#7b90b0;font-size:13px">O link da consulta será enviado em breve.</p>'
    )

    card = f"""
    <h1>📱 Sua teleconsulta foi autorizada!</h1>
    <p class="sub">Você já pode realizar sua consulta online. Veja os detalhes abaixo.</p>
    <div class="row"><span class="lbl">Beneficiário</span><strong>{beneficiario.nome}</strong></div>
    <div class="row"><span class="lbl">Especialidade</span><span>{tele.especialidade}</span></div>
    <div class="row"><span class="lbl">Plataforma</span><span>{plat}</span></div>
    <div class="row"><span class="lbl">Data/Hora</span><span>{data_str}</span></div>
    <div class="row"><span class="lbl">Status</span><span class="badge-ok">Autorizado</span></div>
    <div class="info-bar">
      🎥 Você precisará de câmera e microfone funcionando. Entre no link alguns minutos antes
      do horário agendado para testar a conexão.
    </div>
    {link_html}
    <p style="font-size:13px;color:#7b90b0;margin-top:8px">
      Dúvidas? Entre em contato com nossa central:
      <a href="mailto:suporte@soluscrt.com.br" style="color:#00c9a7">suporte@soluscrt.com.br</a>
    </p>
    """
    html = _html_base(card, "SolusCRT · Plano de Saúde — Telemedicina")
    text = (
        f"Teleconsulta autorizada!\n"
        f"Beneficiário: {beneficiario.nome}\n"
        f"Especialidade: {tele.especialidade}\n"
        f"Plataforma: {plat}\n"
        f"Data: {data_str}\n"
        + (f"Link: {tele.link_consulta}\n" if tele.link_consulta else "")
    )
    _send(
        subject=f"📱 Teleconsulta autorizada — {tele.especialidade}",
        to=email_dest,
        html=html,
        text=text,
    )


# ── 3. Guia Odonto Aprovada ───────────────────────────────────────────────────

def enviar_email_guia_odonto_aprovada(guia) -> None:
    """Email para beneficiário quando guia odontológica é autorizada.

    Args:
        guia: instância de GuiaOdonto
    """
    email_dest = guia.beneficiario.email
    if not email_dest:
        return

    card = f"""
    <h1>🦷 Guia odontológica autorizada!</h1>
    <p class="sub">Seu procedimento foi aprovado. Confira os detalhes e agende com seu dentista.</p>
    <div class="row"><span class="lbl">Beneficiário</span><strong>{guia.beneficiario.nome}</strong></div>
    <div class="row"><span class="lbl">Procedimento</span><strong>{guia.procedimento}</strong></div>
    {'<div class="row"><span class="lbl">Código TUSS</span><span>' + guia.codigo_tuss + '</span></div>' if guia.codigo_tuss else ''}
    {'<div class="row"><span class="lbl">Dentista</span><span>' + guia.dentista + '</span></div>' if guia.dentista else ''}
    {'<div class="row"><span class="lbl">Clínica</span><span>' + guia.clinica + '</span></div>' if guia.clinica else ''}
    <div class="row"><span class="lbl">Valor estimado</span><span>R$ {float(guia.valor_estimado):,.2f}</span></div>
    <div class="row"><span class="lbl">Status</span><span class="badge-ok">Autorizado</span></div>
    <div class="info-bar">
      ✅ Apresente esta autorização ao dentista na hora do atendimento.
      A guia tem validade de <strong>30 dias</strong> a partir desta data.
    </div>
    """
    html = _html_base(card, "SolusCRT · Plano de Saúde — Odontologia")
    text = (
        f"Guia odontológica autorizada\n"
        f"Beneficiário: {guia.beneficiario.nome}\n"
        f"Procedimento: {guia.procedimento}\n"
        f"Valor estimado: R$ {float(guia.valor_estimado):,.2f}\n"
        "Apresente esta confirmação ao dentista.\n"
    )
    _send(
        subject=f"🦷 Guia autorizada — {guia.procedimento}",
        to=email_dest,
        html=html,
        text=text,
    )


# ── 4. Guia Odonto Negada ─────────────────────────────────────────────────────

def enviar_email_guia_odonto_negada(guia) -> None:
    """Email para beneficiário quando guia odontológica é negada.

    Args:
        guia: instância de GuiaOdonto
    """
    email_dest = guia.beneficiario.email
    if not email_dest:
        return

    justif = guia.justificativa_negacao or "Não atende aos critérios de cobertura do plano."
    card = f"""
    <h1>⚠️ Guia odontológica não autorizada</h1>
    <p class="sub">Sua solicitação foi analisada. Veja abaixo o motivo e como recorrer.</p>
    <div class="row"><span class="lbl">Beneficiário</span><strong>{guia.beneficiario.nome}</strong></div>
    <div class="row"><span class="lbl">Procedimento</span><strong>{guia.procedimento}</strong></div>
    <div class="row"><span class="lbl">Status</span><span class="badge-err">Não autorizado</span></div>
    <div class="err-bar">
      <strong>Motivo:</strong> {justif}
    </div>
    <div class="warn-bar">
      📋 <strong>Como recorrer:</strong> Você pode solicitar uma revisão enviando documentação
      complementar (laudos, receituários, justificativa médica) para a central da operadora.
      O prazo de resposta é de <strong>30 dias</strong> conforme RN ANS 395.
    </div>
    <p style="font-size:14px;color:#b0c4d8;margin-top:16px">
      Entre em contato com nossa central de autorização:<br>
      <a href="mailto:autorizacao@soluscrt.com.br" style="color:#00c9a7">autorizacao@soluscrt.com.br</a>
    </p>
    """
    html = _html_base(card, "SolusCRT · Plano de Saúde — Odontologia")
    text = (
        f"Guia odontológica não autorizada\n"
        f"Beneficiário: {guia.beneficiario.nome}\n"
        f"Procedimento: {guia.procedimento}\n"
        f"Motivo: {justif}\n"
        "Para recurso: autorizacao@soluscrt.com.br\n"
    )
    _send(
        subject=f"⚠️ Guia não autorizada — {guia.procedimento}",
        to=email_dest,
        html=html,
        text=text,
    )


# ── 5. SLA Breach Crítico ─────────────────────────────────────────────────────

def enviar_email_sla_breach_critico(empresa, breaches: list) -> None:
    """Email de alerta para a operadora quando há guias com SLA violado.

    Args:
        empresa: instância de Empresa (operadora)
        breaches: lista de dicts com chaves id, beneficiario, tipo, prazo, aberto_ha, prestador
    """
    if not breaches:
        return

    base_url = _base_url()
    qtd = len(breaches)

    linhas_tabela = "".join(
        f"""<div class="row">
          <span class="lbl">{b['id']}</span>
          <span style="flex:1;padding:0 12px">{b['beneficiario']} · {b['tipo']}</span>
          <span style="color:#ff4d6d;font-weight:700">{b['aberto_ha']}</span>
        </div>"""
        for b in breaches[:10]
    )
    mais = f'<p style="color:#7b90b0;font-size:13px;margin-top:8px">+ {qtd-10} guias adicionais no painel.</p>' if qtd > 10 else ""

    card = f"""
    <h1>🚨 {qtd} guia{'s' if qtd > 1 else ''} com SLA violado — ação necessária</h1>
    <p class="sub">Guias fora do prazo ANS (RN 395/452) exigem resolução imediata para evitar penalidades.</p>
    <div class="err-bar">
      ⏱ As guias abaixo ultrapassaram o prazo regulatório. O descumprimento de SLA
      pode resultar em <strong>advertência e multa ANS</strong>.
    </div>
    <div style="margin:18px 0">
      <div class="row" style="font-size:12px;font-weight:700;color:#7b90b0;text-transform:uppercase">
        <span class="lbl">Guia</span>
        <span style="flex:1;padding:0 12px">Beneficiário · Tipo</span>
        <span>Tempo em atraso</span>
      </div>
      {linhas_tabela}
    </div>
    {mais}
    <a href="{base_url}/plano-saude/gestao/" class="btn">Resolver agora →</a>
    <p style="font-size:13px;color:#7b90b0;margin-top:8px">
      Acesse a aba <strong>Regulação &amp; SLA</strong> no painel para ver todas as guias e tomar ação.
    </p>
    """
    html = _html_base(card, f"SolusCRT · Operadora — {empresa.nome}")
    text = (
        f"ALERTA SLA — {qtd} guia(s) com prazo ANS violado\n"
        f"Operadora: {empresa.nome}\n\n"
        + "\n".join(f"• {b['id']} | {b['beneficiario']} | {b['tipo']} | {b['aberto_ha']}" for b in breaches[:10])
        + f"\n\nResolver: {base_url}/plano-saude/gestao/\n"
    )
    _send(
        subject=f"🚨 SLA violado — {qtd} guia{'s' if qtd > 1 else ''} fora do prazo ANS",
        to=empresa.email,
        html=html,
        text=text,
    )


# ── 6. Alerta de Auditoria (Risco de Fraude) ─────────────────────────────────

def enviar_email_auditoria_alerta(empresa, nome_benef: str, score: int, fatores: list) -> None:
    """Email para a operadora quando um beneficiário atinge score de risco alto/crítico.

    Args:
        empresa: instância de Empresa (operadora)
        nome_benef: nome do beneficiário de alto risco
        score: score de risco 0-100
        fatores: lista de strings descrevendo os fatores de risco
    """
    base_url = _base_url()
    nivel = "Crítico" if score >= 90 else "Alto"
    cor_nivel = "#ff4d6d" if score >= 90 else "#ffb347"
    bar_class = "err-bar" if score >= 90 else "warn-bar"
    emoji = "🔴" if score >= 90 else "🟡"

    tags_html = "".join(f'<span class="tag">{f}</span>' for f in fatores)

    card = f"""
    <h1>{emoji} Alerta de auditoria — risco {nivel.lower()}</h1>
    <p class="sub">O motor de auditoria identificou padrões anômalos que requerem revisão manual.</p>
    <div class="row"><span class="lbl">Beneficiário</span><strong>{nome_benef}</strong></div>
    <div class="row"><span class="lbl">Score de risco</span>
      <strong style="color:{cor_nivel};font-size:20px">{score}/100</strong>
    </div>
    <div class="row"><span class="lbl">Nível</span>
      <span class="badge-{'err' if score >= 90 else 'warn'}">{nivel}</span>
    </div>
    <div class="{bar_class}">
      <strong>Fatores detectados:</strong><br>
      <div style="margin-top:8px">{tags_html if tags_html else '—'}</div>
    </div>
    <div class="info-bar">
      📋 <strong>Ação recomendada:</strong> Revise o histórico de sinistros dos últimos 90 dias
      para este beneficiário. Em caso de confirmação de fraude ou abuso, acione o
      departamento jurídico conforme RN ANS 137.
    </div>
    <a href="{base_url}/plano-saude/gestao/" class="btn">Abrir auditoria →</a>
    <p style="font-size:13px;color:#7b90b0;margin-top:8px">
      Acesse a aba <strong>Auditoria Médica IA</strong> para ver o dossiê completo.
    </p>
    """
    html = _html_base(card, f"SolusCRT · Operadora — {empresa.nome}")
    text = (
        f"ALERTA AUDITORIA — Risco {nivel}\n"
        f"Operadora: {empresa.nome}\n"
        f"Beneficiário: {nome_benef}\n"
        f"Score: {score}/100\n"
        f"Fatores: {', '.join(fatores)}\n"
        f"Revisar: {base_url}/plano-saude/gestao/\n"
    )
    _send(
        subject=f"{emoji} Auditoria — risco {nivel.lower()}: {nome_benef} (score {score})",
        to=empresa.email,
        html=html,
        text=text,
    )


# ── 7. Novo Beneficiário Cadastrado ──────────────────────────────────────────

def enviar_email_novo_beneficiario(empresa, beneficiario) -> None:
    """Email de confirmação para o beneficiário recém-cadastrado no plano.

    Args:
        empresa: instância de Empresa (operadora)
        beneficiario: instância de BeneficiarioPlano
    """
    email_dest = beneficiario.email
    if not email_dest:
        return

    base_url = _base_url()
    vigencia_str = (
        beneficiario.data_inicio_vigencia.strftime("%d/%m/%Y")
        if beneficiario.data_inicio_vigencia else "—"
    )
    carteirinha_str = beneficiario.numero_carteirinha or "Será enviada em breve"

    card = f"""
    <h1>🎉 Bem-vindo ao plano de saúde, {beneficiario.nome.split()[0]}!</h1>
    <p class="sub">Seu cadastro foi realizado com sucesso. Guarde os dados abaixo.</p>
    <div class="row"><span class="lbl">Nome completo</span><strong>{beneficiario.nome}</strong></div>
    <div class="row"><span class="lbl">Plano</span><strong>{beneficiario.plano.nome}</strong></div>
    <div class="row"><span class="lbl">N° da carteirinha</span><span>{carteirinha_str}</span></div>
    <div class="row"><span class="lbl">Início da vigência</span><span>{vigencia_str}</span></div>
    <div class="row"><span class="lbl">Acomodação</span><span style="text-transform:capitalize">{beneficiario.acomodacao}</span></div>
    <div class="row"><span class="lbl">Status</span><span class="badge-ok">Ativo</span></div>
    <div class="info-bar">
      ℹ️ <strong>Período de carência:</strong> alguns procedimentos podem estar sujeitos a carência
      conforme RN ANS 162. Consulte sua operadora para verificar quais coberturas já estão liberadas.
    </div>
    <div class="warn-bar">
      📱 Baixe o aplicativo ou acesse o portal do beneficiário para agendar consultas,
      emitir guias e verificar sua rede credenciada.
    </div>
    <p style="font-size:13px;color:#7b90b0;margin-top:8px">
      Dúvidas? Fale com a operadora: <a href="mailto:{empresa.email}" style="color:#00c9a7">{empresa.email}</a>
    </p>
    """
    html = _html_base(card, f"SolusCRT · {empresa.nome} — Plano de Saúde")
    text = (
        f"Bem-vindo ao plano de saúde!\n"
        f"Nome: {beneficiario.nome}\n"
        f"Plano: {beneficiario.plano.nome}\n"
        f"Carteirinha: {carteirinha_str}\n"
        f"Vigência: {vigencia_str}\n"
        f"Dúvidas: {empresa.email}\n"
    )
    _send(
        subject=f"🎉 Cadastro confirmado — {beneficiario.plano.nome}",
        to=email_dest,
        html=html,
        text=text,
    )
