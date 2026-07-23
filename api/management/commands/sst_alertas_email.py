"""
python manage.py sst_alertas_email

Envia alertas de vencimento por e-mail para empresas com alertas ativos.
Configurar como Render Cron Job: roda diariamente às 08:00.

Alertas disparados:
- ASOs vencendo dentro de X dias (padrão 30)
- Exames ocupacionais vencendo dentro de X dias (padrão 30)
- Treinamentos NR vencendo dentro de X dias (padrão 60)
"""
from datetime import date, timedelta

from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand

from api.models import (
    ASOOcupacional,
    ConfiguracaoSST,
    ExameOcupacional,
    TreinamentoNR,
)


class Command(BaseCommand):
    help = "Envia alertas de vencimento SST por e-mail para empresas configuradas"

    def handle(self, *args, **options):
        hoje = date.today()
        configs = ConfiguracaoSST.objects.filter(
            alertas_ativos=True
        ).exclude(email_alertas="").select_related("empresa")

        total_enviados = 0

        for config in configs:
            empresa  = config.empresa
            alertas  = []

            # ── ASOs vencendo ─────────────────────────────────────────
            limite_aso = hoje + timedelta(days=config.alerta_aso_dias)
            asos = ASOOcupacional.objects.filter(
                funcionario__empresa=empresa,
                data_validade__gte=hoje,
                data_validade__lte=limite_aso,
            ).select_related("funcionario").order_by("data_validade")

            if asos.exists():
                alertas.append({
                    "titulo": f"ASOs vencendo nos próximos {config.alerta_aso_dias} dias",
                    "icone": "📋",
                    "itens": [
                        {
                            "nome": a.funcionario.nome,
                            "cargo": a.funcionario.cargo or "—",
                            "vencimento": a.data_validade.strftime("%d/%m/%Y"),
                            "dias": (a.data_validade - hoje).days,
                        }
                        for a in asos
                    ],
                })

            # ── Exames vencendo ───────────────────────────────────────
            limite_ex = hoje + timedelta(days=config.alerta_exame_dias)
            exames = ExameOcupacional.objects.filter(
                funcionario__empresa=empresa,
                data_validade__gte=hoje,
                data_validade__lte=limite_ex,
            ).select_related("funcionario").order_by("data_validade")

            if exames.exists():
                alertas.append({
                    "titulo": f"Exames vencendo nos próximos {config.alerta_exame_dias} dias",
                    "icone": "🔬",
                    "itens": [
                        {
                            "nome": e.funcionario.nome,
                            "cargo": e.tipo_exame,
                            "vencimento": e.data_validade.strftime("%d/%m/%Y"),
                            "dias": (e.data_validade - hoje).days,
                        }
                        for e in exames
                    ],
                })

            # ── Treinamentos vencendo ─────────────────────────────────
            limite_tr = hoje + timedelta(days=config.alerta_treinamento_dias)
            treinamentos = TreinamentoNR.objects.filter(
                empresa=empresa,
                data_validade__gte=hoje,
                data_validade__lte=limite_tr,
            ).select_related("funcionario").order_by("data_validade")

            if treinamentos.exists():
                alertas.append({
                    "titulo": f"Treinamentos NR vencendo nos próximos {config.alerta_treinamento_dias} dias",
                    "icone": "🎓",
                    "itens": [
                        {
                            "nome": t.funcionario.nome,
                            "cargo": t.nr,
                            "vencimento": t.data_validade.strftime("%d/%m/%Y"),
                            "dias": (t.data_validade - hoje).days,
                        }
                        for t in treinamentos
                    ],
                })

            if not alertas:
                continue

            # ── Montar e enviar e-mail ────────────────────────────────
            total_itens = sum(len(a["itens"]) for a in alertas)
            assunto = f"[SoloCRT] {total_itens} vencimento{'s' if total_itens > 1 else ''} SST — {empresa.nome}"

            texto_puro, html = _montar_email(empresa.nome, alertas, hoje)

            msg = EmailMultiAlternatives(
                subject=assunto,
                body=texto_puro,
                to=[config.email_alertas],
            )
            msg.attach_alternative(html, "text/html")

            try:
                msg.send()
                total_enviados += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  ✓ {empresa.nome} → {config.email_alertas} ({total_itens} itens)"
                ))
            except Exception as exc:
                self.stderr.write(f"  ✗ {empresa.nome}: {exc}")

        self.stdout.write(self.style.SUCCESS(
            f"\nConcluído: {total_enviados} e-mail(s) enviado(s) de {configs.count()} empresa(s) ativa(s)."
        ))


def _montar_email(empresa_nome, alertas, hoje):
    """Retorna (texto_puro, html)."""
    data_str = hoje.strftime("%d/%m/%Y")

    # ── HTML ─────────────────────────────────────────────────────────────────
    secoes_html = ""
    for a in alertas:
        rows = ""
        for item in a["itens"]:
            cor = "#f87171" if item["dias"] <= 7 else ("#f0bf6b" if item["dias"] <= 30 else "#4ade80")
            rows += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #e8f4f1">{item['nome']}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #e8f4f1;color:#7a9fa0">{item['cargo']}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #e8f4f1">{item['vencimento']}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #e8f4f1">
                <span style="background:{cor}20;color:{cor};padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px">
                  {item['dias']}d
                </span>
              </td>
            </tr>"""
        secoes_html += f"""
        <div style="margin-bottom:24px">
          <h3 style="color:#041018;font-size:14px;margin:0 0 8px;font-weight:700">
            {a['icone']} {a['titulo']}
          </h3>
          <table style="width:100%;border-collapse:collapse;font-size:13px">
            <thead>
              <tr style="background:#f4f8f7">
                <th style="padding:8px 12px;text-align:left;color:#7a9fa0;font-size:11px;text-transform:uppercase">Funcionário</th>
                <th style="padding:8px 12px;text-align:left;color:#7a9fa0;font-size:11px;text-transform:uppercase">Cargo / Tipo</th>
                <th style="padding:8px 12px;text-align:left;color:#7a9fa0;font-size:11px;text-transform:uppercase">Vencimento</th>
                <th style="padding:8px 12px;text-align:left;color:#7a9fa0;font-size:11px;text-transform:uppercase">Dias restantes</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f8f7;font-family:'Segoe UI',Helvetica,Arial,sans-serif">
  <div style="max-width:640px;margin:24px auto;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,.08)">
    <!-- Header -->
    <div style="background:#041018;padding:24px 32px">
      <p style="color:#00c9a7;font-size:20px;font-weight:800;margin:0">SoloCRT</p>
      <p style="color:#7a9fa0;font-size:13px;margin:4px 0 0">Alerta de Vencimentos SST · {data_str}</p>
    </div>
    <!-- Body -->
    <div style="padding:28px 32px">
      <h2 style="color:#041018;font-size:18px;margin:0 0 4px;font-weight:800">
        Atenção: vencimentos próximos
      </h2>
      <p style="color:#7a9fa0;font-size:13px;margin:0 0 24px">
        Os itens abaixo requerem ação para manter a conformidade SST de <strong>{empresa_nome}</strong>.
      </p>
      {secoes_html}
      <div style="margin-top:24px;padding:16px;background:#f0f9ff;border-radius:8px;border-left:4px solid #00c9a7">
        <p style="margin:0;font-size:13px;color:#041018">
          Acesse o <a href="https://empresa.solocrt.com.br/dashboard-empresa/" style="color:#00c9a7;font-weight:700">painel SST</a>
          para gerenciar vencimentos, agendar exames e emitir documentos.
        </p>
      </div>
    </div>
    <!-- Footer -->
    <div style="padding:16px 32px;background:#f4f8f7;border-top:1px solid #e8f4f1">
      <p style="margin:0;font-size:11px;color:#7a9fa0;text-align:center">
        SoloCRT · Plataforma de Saúde e Segurança do Trabalho ·
        <a href="https://empresa.solocrt.com.br/sst/configuracoes/" style="color:#7a9fa0">Gerenciar alertas</a>
      </p>
    </div>
  </div>
</body>
</html>"""

    # ── Texto puro ────────────────────────────────────────────────────────────
    linhas = [f"SoloCRT — Alertas SST {empresa_nome} · {data_str}\n"]
    for a in alertas:
        linhas.append(f"\n{a['icone']} {a['titulo']}")
        for item in a["itens"]:
            linhas.append(f"  • {item['nome']} ({item['cargo']}) — vence {item['vencimento']} ({item['dias']} dias)")
    linhas.append("\nAcesse: https://empresa.solocrt.com.br/dashboard-empresa/")
    return "\n".join(linhas), html
