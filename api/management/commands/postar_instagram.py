"""
Management command: postar_instagram

Roda periodicamente (sugestão: 3x por semana, alternando segmento):
  0 10 * * 1,3,5 cd /opt/soluscrt && source venv/bin/activate && python manage.py postar_instagram --segmento sst
  0 10 * * 2,4,6 cd /opt/soluscrt && source venv/bin/activate && python manage.py postar_instagram --segmento farmacia

Gera conteúdo educativo (Claude) + imagem (Pillow) + publica na conta
Instagram da SoloCRT Saúde via Graph API. Não manda mensagem pra ninguém —
é conteúdo orgânico na própria conta, pra atrair lead.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Gera e publica um post de conteúdo educativo no Instagram (SST ou Farmácia)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--segmento", choices=["sst", "farmacia"], required=True,
            help="Segmento do conteúdo do post",
        )
        parser.add_argument("--dry-run", action="store_true", help="Gera tudo mas não publica")

    def handle(self, *args, **options):
        from api.instagram_service import gerar_conteudo_post, gerar_imagem_post, publicar_instagram

        segmento = options["segmento"]
        dry_run = options["dry_run"]

        self.stdout.write(f"[postar_instagram] gerando conteúdo pro segmento={segmento}…")
        try:
            conteudo = gerar_conteudo_post(segmento)
        except Exception as exc:
            raise CommandError(f"Erro ao gerar conteúdo: {exc}")

        self.stdout.write(f"  título: {conteudo['titulo']}")
        self.stdout.write(f"  legenda: {conteudo['legenda'][:120]}…")

        nome_arquivo = gerar_imagem_post(conteudo["titulo"], segmento)
        base_url = getattr(settings, "PUBLIC_BASE_URL", "https://app.solocrt.com.br").rstrip("/")
        imagem_url = f"{base_url}/api/comercial/social/imagem/{nome_arquivo}/"
        self.stdout.write(f"  imagem: {imagem_url}")

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — não publicado."))
            return

        sucesso, resultado = publicar_instagram(imagem_url, conteudo["legenda"])
        if sucesso:
            self.stdout.write(self.style.SUCCESS(f"✓ Publicado! media_id={resultado}"))
        else:
            raise CommandError(f"Erro ao publicar: {resultado}")
