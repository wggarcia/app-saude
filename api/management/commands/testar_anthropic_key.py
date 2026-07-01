"""
Diagnóstico rápido da ANTHROPIC_API_KEY.

Faz uma chamada mínima ao Claude Haiku (10 tokens de saída) e reporta
se a chave está configurada e válida, ou qual erro foi retornado.
Não lê nem escreve nada no banco de dados.

Uso:
    python manage.py testar_anthropic_key
"""

import os

from django.core.management.base import BaseCommand

MODEL_ID = "claude-haiku-4-5"


class Command(BaseCommand):
    help = "Diagnóstico rápido: testa se ANTHROPIC_API_KEY está válida fazendo uma chamada mínima."

    def handle(self, *args, **options):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            self.stdout.write(
                self.style.ERROR("ANTHROPIC_API_KEY não encontrada no ambiente.")
            )
            return

        self.stdout.write(f"Chave encontrada: {api_key[:8]}...{api_key[-4:]}")
        self.stdout.write(f"Testando conexão com {MODEL_ID}...")

        try:
            import anthropic
        except ImportError:
            self.stdout.write(self.style.ERROR("Pacote 'anthropic' não instalado."))
            return

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=MODEL_ID,
                max_tokens=10,
                messages=[{"role": "user", "content": "Responda apenas: OK"}],
            )
            resposta = response.content[0].text.strip()
            self.stdout.write(
                self.style.SUCCESS(
                    f"ANTHROPIC_API_KEY OK — resposta do modelo: '{resposta}'"
                )
            )
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Falha na chamada à API: {exc}"))
