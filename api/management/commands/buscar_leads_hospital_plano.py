"""
buscar_leads_hospital_plano.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Varre cidades em todo o Brasil buscando HOSPITAIS e OPERADORAS DE PLANO DE
SAÚDE (segmentos enterprise) e salva como LeadProspeccao só os candidatos que
já vieram com email encontrado automaticamente no site (não inventa contato).

Mesma lógica do buscar_leads_empresas_sst, mas pros segmentos hospital e
plano_saude — a prospecção desses vai por venda consultiva (email com convite
pra conversa/demonstração, sem teste self-service).

Rodar em background na VPS (usa a Google Places API — custo por chamada):
  cd /opt/soluscrt && set -a && . ./.env && set +a && \
    nohup venv/bin/python -u manage.py buscar_leads_hospital_plano \
    >> /var/log/soluscrt/buscar_leads_hosp_plano.log 2>&1 &
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.db import IntegrityError

from api.lead_hunter import buscar_google_places
from api.management.commands.buscar_leads_empresas_sst import _CIDADES
from api.models import LeadProspeccao

# Hospitais existem em toda cidade; operadoras/cooperativas se concentram mais,
# mas o dedup por email cuida de repetição, então varremos as mesmas cidades.
_TIPOS_POR_SEGMENTO = {
    "hospital": ["hospital_geral", "hospital_especializado", "santa_casa"],
    "plano_saude": ["operadora_plano", "cooperativa_medica"],
}


class Command(BaseCommand):
    help = "Busca hospitais e operadoras de plano de saúde (com email no site) por todo o Brasil."

    def add_arguments(self, parser):
        parser.add_argument("--max-por-tipo", type=int, default=12,
                            help="Máx. de resultados por tipo por cidade (controla custo da API)")
        parser.add_argument("--pausa", type=float, default=1.5, help="Segundos entre chamadas")
        parser.add_argument("--so-hospital", action="store_true", help="Só busca hospitais")
        parser.add_argument("--so-plano", action="store_true", help="Só busca planos de saúde")

    def handle(self, *args, **options):
        max_r = options["max_por_tipo"]
        pausa = options["pausa"]

        segmentos = list(_TIPOS_POR_SEGMENTO.keys())
        if options["so_hospital"]:
            segmentos = ["hospital"]
        elif options["so_plano"]:
            segmentos = ["plano_saude"]

        total_cand = total_email = total_salvos = total_dup = total_erro = 0

        for cidade, estado in _CIDADES:
            self.stdout.write(f"\n=== {cidade}/{estado} ===")
            for segmento in segmentos:
                for tipo in _TIPOS_POR_SEGMENTO[segmento]:
                    try:
                        candidatos = buscar_google_places(tipo, cidade, estado, max_r)
                    except Exception as exc:
                        self.stdout.write(f"  ERRO ({segmento}/{tipo}): {exc}")
                        total_erro += 1
                        time.sleep(pausa)
                        continue

                    total_cand += len(candidatos)
                    com_email = [c for c in candidatos if c.get("email")]
                    total_email += len(com_email)
                    if com_email:
                        self.stdout.write(f"  [{segmento}/{tipo}] {len(candidatos)} achados, {len(com_email)} c/ email")

                    for c in com_email:
                        try:
                            LeadProspeccao.objects.create(
                                segmento=segmento,
                                tipo=tipo,
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
                            total_dup += 1
                            self.stdout.write(f"    DUPLICADO: {c['email']}")

                    time.sleep(pausa)

        self.stdout.write("\n=== RESUMO FINAL ===")
        self.stdout.write(f"Segmentos: {', '.join(segmentos)}")
        self.stdout.write(f"Cidades varridas: {len(_CIDADES)} (erros de busca: {total_erro})")
        self.stdout.write(f"Candidatos encontrados: {total_cand}")
        self.stdout.write(f"Com email no site: {total_email}")
        self.stdout.write(f"Salvos como lead novo: {total_salvos}")
        self.stdout.write(f"Duplicados (já existiam): {total_dup}")
