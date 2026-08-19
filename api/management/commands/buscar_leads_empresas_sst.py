"""
buscar_leads_empresas_sst.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Varre cidades em todo o Brasil buscando empresas com força de trabalho em
campo (tipo='empresa_sesmt') — construção, transporte, indústria, agro,
offshore/embarcados, portuário, energia, etc. — e salva como LeadProspeccao
só os candidatos que já vieram com email encontrado automaticamente no
site (não inventa contato).

Complementa os leads já importados (que eram 100% clínica de medicina
ocupacional) com o público certo pro App Ocupacional: a empresa em si,
não a prestadora de serviço.

Rodar em background na VPS (pode levar bastante tempo — cada cidade faz
várias buscas no Google Places + tenta abrir o site de cada resultado):
  cd /opt/soluscrt && set -a && . ./.env && set +a && \
    nohup venv/bin/python manage.py buscar_leads_empresas_sst \
    >> /var/log/soluscrt/buscar_leads_sst.log 2>&1 &
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import IntegrityError

from api.lead_hunter import buscar_google_places
from api.models import LeadProspeccao

# Cobertura nacional: as 27 capitais + polos industriais/portuários/offshore/
# agro onde empresa com força de trabalho em campo se concentra de verdade.
_CIDADES = [
    # Capitais (26 estados + DF)
    ("Rio Branco", "AC"), ("Maceió", "AL"), ("Macapá", "AP"), ("Manaus", "AM"),
    ("Salvador", "BA"), ("Fortaleza", "CE"), ("Brasília", "DF"), ("Vitória", "ES"),
    ("Goiânia", "GO"), ("São Luís", "MA"), ("Cuiabá", "MT"), ("Campo Grande", "MS"),
    ("Belo Horizonte", "MG"), ("Belém", "PA"), ("João Pessoa", "PB"), ("Curitiba", "PR"),
    ("Recife", "PE"), ("Teresina", "PI"), ("Rio de Janeiro", "RJ"), ("Natal", "RN"),
    ("Porto Alegre", "RS"), ("Porto Velho", "RO"), ("Boa Vista", "RR"),
    ("Florianópolis", "SC"), ("São Paulo", "SP"), ("Aracaju", "SE"), ("Palmas", "TO"),
    # Offshore / portuário (NR-30, NR-37 — colaborador embarcado)
    ("Macaé", "RJ"), ("Rio das Ostras", "RJ"), ("Angra dos Reis", "RJ"),
    ("Santos", "SP"), ("Itajaí", "SC"), ("Rio Grande", "RS"), ("Suape", "PE"),
    ("São Gonçalo do Amarante", "CE"), ("Barcarena", "PA"),
    # Polos industriais/agro adicionais
    ("Campinas", "SP"), ("São José dos Campos", "SP"), ("Guarulhos", "SP"),
    ("Duque de Caxias", "RJ"), ("Camaçari", "BA"), ("Ipatinga", "MG"),
    ("Uberlândia", "MG"), ("Londrina", "PR"), ("Paranaguá", "PR"),
    ("Joinville", "SC"), ("Caxias do Sul", "RS"), ("Rondonópolis", "MT"),
    ("Anápolis", "GO"), ("Rio Verde", "GO"), ("Dourados", "MS"),
    ("Imperatriz", "MA"), ("Marabá", "PA"), ("Caruaru", "PE"),
]


class Command(BaseCommand):
    help = "Busca empresas (todo setor, inclusive offshore) com email real no site, em cidades por todo o Brasil."

    def add_arguments(self, parser):
        parser.add_argument("--max-por-cidade", type=int, default=20)
        parser.add_argument("--pausa", type=float, default=2.0, help="Segundos de pausa entre cidades")

    def handle(self, *args, **options):
        max_r = options["max_por_cidade"]
        pausa = options["pausa"]

        total_candidatos = 0
        total_com_email = 0
        total_salvos = 0
        total_duplicados = 0
        total_erro_cidade = 0

        for cidade, estado in _CIDADES:
            self.stdout.write(f"\n=== {cidade}/{estado} ===")
            try:
                candidatos = buscar_google_places("empresa_sesmt", cidade, estado, max_r)
            except Exception as exc:
                self.stdout.write(f"  ERRO na busca: {exc}")
                total_erro_cidade += 1
                time.sleep(pausa)
                continue

            total_candidatos += len(candidatos)
            com_email = [c for c in candidatos if c.get("email")]
            total_com_email += len(com_email)
            self.stdout.write(f"  {len(candidatos)} encontrados — {len(com_email)} com email no site")

            for c in com_email:
                try:
                    LeadProspeccao.objects.create(
                        segmento="sst",
                        tipo="empresa_sesmt",
                        nome=c["empresa"],
                        empresa=c["empresa"],
                        email=c["email"],
                        telefone=c.get("telefone", ""),
                        cidade=cidade,
                        estado=estado,
                        website=c.get("website", ""),
                        origem="google_places",
                        dados_adicionais=c.get("dados_adicionais", {}),
                    )
                    total_salvos += 1
                    self.stdout.write(f"    OK: {c['empresa']} <{c['email']}>")
                except IntegrityError:
                    total_duplicados += 1
                    self.stdout.write(f"    DUPLICADO (email já existe): {c['email']}")

            time.sleep(pausa)

        self.stdout.write("\n=== RESUMO FINAL ===")
        self.stdout.write(f"Cidades varridas: {len(_CIDADES)} (erro em {total_erro_cidade})")
        self.stdout.write(f"Candidatos encontrados: {total_candidatos}")
        self.stdout.write(f"Com email no site: {total_com_email}")
        self.stdout.write(f"Salvos como lead novo: {total_salvos}")
        self.stdout.write(f"Duplicados (já existiam): {total_duplicados}")
