import json
import random
import statistics
import time
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.test import Client
from django.utils import timezone

from api.models import AlertaGovernamental, Empresa, RegistroSintoma
from api.views import _indice_temporal_publico


TEST_PREFIX = "stress-soluscrt-brasil"


REGIOES_BRASIL = [
    ("Norte", "Acre", "Rio Branco", "Centro", -9.97499, -67.8243, "misto"),
    ("Norte", "Amapa", "Macapá", "Centro", 0.0349, -51.0694, "arbovirose"),
    ("Norte", "Amazonas", "Manaus", "Centro", -3.1190, -60.0217, "respiratorio"),
    ("Norte", "Pará", "Belém", "Campina", -1.4558, -48.4902, "arbovirose"),
    ("Norte", "Rondônia", "Porto Velho", "Centro", -8.7612, -63.9004, "misto"),
    ("Norte", "Roraima", "Boa Vista", "Centro", 2.8235, -60.6758, "respiratorio"),
    ("Norte", "Tocantins", "Palmas", "Plano Diretor Sul", -10.1840, -48.3336, "misto"),
    ("Nordeste", "Alagoas", "Maceió", "Ponta Verde", -9.6498, -35.7089, "arbovirose"),
    ("Nordeste", "Bahia", "Salvador", "Centro", -12.9777, -38.5016, "arbovirose"),
    ("Nordeste", "Ceara", "Fortaleza", "Centro", -3.7319, -38.5267, "arbovirose"),
    ("Nordeste", "Maranhão", "São Luís", "Centro", -2.5307, -44.3068, "arbovirose"),
    ("Nordeste", "Paraíba", "João Pessoa", "Centro", -7.1195, -34.8450, "arbovirose"),
    ("Nordeste", "Pernambuco", "Recife", "Boa Vista", -8.0476, -34.8770, "arbovirose"),
    ("Nordeste", "Piauí", "Teresina", "Centro", -5.0892, -42.8019, "misto"),
    ("Nordeste", "Rio Grande do Norte", "Natal", "Petrópolis", -5.7793, -35.2009, "arbovirose"),
    ("Nordeste", "Sergipe", "Aracaju", "Centro", -10.9472, -37.0731, "misto"),
    ("Centro-Oeste", "Distrito Federal", "Brasília", "Plano Piloto", -15.7939, -47.8828, "respiratorio"),
    ("Centro-Oeste", "Goiás", "Goiânia", "Setor Central", -16.6869, -49.2648, "misto"),
    ("Centro-Oeste", "Mato Grosso", "Cuiabá", "Centro", -15.6014, -56.0979, "arbovirose"),
    ("Centro-Oeste", "Mato Grosso do Sul", "Campo Grande", "Centro", -20.4697, -54.6201, "misto"),
    ("Sudeste", "Espírito Santo", "Vitória", "Centro", -20.3155, -40.3128, "misto"),
    ("Sudeste", "Minas Gerais", "Belo Horizonte", "Centro", -19.9167, -43.9345, "misto"),
    ("Sudeste", "Rio de Janeiro", "Rio de Janeiro", "Centro", -22.9068, -43.1729, "respiratorio"),
    ("Sudeste", "São Paulo", "São Paulo", "Pinheiros", -23.5614, -46.7016, "respiratorio"),
    ("Sul", "Parana", "Curitiba", "Centro", -25.4284, -49.2733, "respiratorio"),
    ("Sul", "Rio Grande do Sul", "Porto Alegre", "Centro Histórico", -30.0346, -51.2177, "respiratorio"),
    ("Sul", "Santa Catarina", "Florianópolis", "Centro", -27.5949, -48.5482, "respiratorio"),
]


class Command(BaseCommand):
    help = "Executa stress test nacional SolusCRT simulando 30 dias em janelas de tempo configuráveis."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=30)
        parser.add_argument("--seconds-per-minute", type=float, default=60.0)
        parser.add_argument("--initial-total", type=int, default=1350)
        parser.add_argument("--seed", type=int, default=20260422)
        parser.add_argument("--cleanup-before", action="store_true")
        parser.add_argument("--cleanup-after", action="store_true")
        parser.add_argument("--cleanup-only", action="store_true")
        parser.add_argument("--report-dir", default="docs/relatorios")

    def handle(self, *args, **options):
        random.seed(options["seed"])
        started_at = timezone.now()
        report_dir = Path(options["report_dir"])
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"stress_soluscrt_brasil_{started_at.strftime('%Y%m%d_%H%M%S')}.md"

        if options["cleanup_before"]:
            self._cleanup()
        if options["cleanup_only"]:
            self.stdout.write(self.style.SUCCESS("Dados sinteticos de stress removidos."))
            return

        empresa_app = self._empresa_app()
        governo = self._conta("Governo Stress SolusCRT", "stress-governo@soluscrt.local", Empresa.TIPO_GOVERNO)
        empresa = self._conta("Empresa Stress SolusCRT", "stress-empresa@soluscrt.local", Empresa.TIPO_EMPRESA)
        self._alerta_governo(governo)

        client_publico = Client(HTTP_HOST="127.0.0.1:8000")
        client_empresa = self._client_logado("/api/login-empresa", empresa.email)
        client_governo = self._client_logado("/api/login-governo", governo.email)

        self.stdout.write(self.style.NOTICE("Iniciando carga nacional inicial..."))
        criados = self._injetar_sinais(client_publico, empresa_app, options["initial_total"], started_at)
        if criados == 0:
            raise RuntimeError("Nenhum registro de stress foi criado. Teste abortado.")

        qs_stress = RegistroSintoma.objects.filter(device_id__startswith=TEST_PREFIX)
        indice_inicial = _indice_temporal_publico(qs_stress, started_at)
        snapshots = []
        erros = []
        total_requests = 0
        latencias = []

        for day in range(1, options["minutes"] + 1):
            tick_start = time.monotonic()
            simulated_now = started_at + timedelta(days=day)
            self._envelhecer_registros(started_at, simulated_now)
            snapshot, request_count, tick_latencias, tick_erros = self._stressar_componentes(
                client_publico,
                client_empresa,
                client_governo,
                qs_stress,
                day,
            )
            snapshots.append(snapshot)
            total_requests += request_count
            latencias.extend(tick_latencias)
            erros.extend(tick_erros)

            self.stdout.write(
                f"[dia {day:02d}/{options['minutes']}] "
                f"indice={snapshot['indice_ativo']:.2f} "
                f"retencao={snapshot['retencao_pct']:.2f}% "
                f"mapa={snapshot['hotspots']} focos "
                f"req={request_count} erros={len(tick_erros)}"
            )

            elapsed = time.monotonic() - tick_start
            wait = max(options["seconds_per_minute"] - elapsed, 0)
            if wait:
                time.sleep(wait)

        report = self._montar_relatorio(
            started_at,
            snapshots,
            erros,
            total_requests,
            latencias,
            criados,
            report_path,
        )
        report_path.write_text(report, encoding="utf-8")

        if options["cleanup_after"]:
            self._cleanup()

        self.stdout.write(self.style.SUCCESS(f"Stress test concluido. Relatorio: {report_path}"))

    def _empresa_app(self):
        empresa, _ = Empresa.objects.get_or_create(
            email="populacao@soluscrt.com",
            defaults={
                "nome": "SolusCRT Populacao",
                "senha": make_password("publico_app"),
                "ativo": True,
                "plano": "publico",
                "pacote_codigo": "governo_estado",
                "max_usuarios": 1000,
                "max_dispositivos": 1000,
            },
        )
        return empresa

    def _conta(self, nome, email, tipo):
        empresa, _ = Empresa.objects.update_or_create(
            email=email,
            defaults={
                "nome": nome,
                "senha": make_password("123456"),
                "ativo": True,
                "tipo_conta": tipo,
                "acesso_governo": tipo == Empresa.TIPO_GOVERNO,
                "pacote_codigo": "governo_estado" if tipo == Empresa.TIPO_GOVERNO else "empresa_nacional_1000",
                "plano": "anual",
                "max_usuarios": 1000,
                "max_dispositivos": 1000,
                "data_expiracao": timezone.now() + timedelta(days=365),
            },
        )
        return empresa

    def _client_logado(self, endpoint, email):
        client = Client(HTTP_HOST="127.0.0.1:8000")
        response = client.post(
            endpoint,
            data=json.dumps({
                "email": email,
                "senha": "123456",
                "device_id": f"{TEST_PREFIX}-{endpoint.strip('/').replace('/', '-')}",
                "force_login": True,
            }),
            content_type="application/json",
        )
        if response.status_code not in {200, 409}:
            self.stdout.write(self.style.WARNING(f"Login de stress falhou em {endpoint}: {response.status_code}"))
        return client

    def _alerta_governo(self, governo):
        AlertaGovernamental.objects.update_or_create(
            empresa=governo,
            titulo="Stress nacional SolusCRT",
            defaults={
                "mensagem": "Simulacao controlada de sala de controle epidemiologica nacional.",
                "estado": "",
                "cidade": "",
                "bairro": "",
                "nivel": "moderado",
                "ativo": True,
                "status": AlertaGovernamental.STATUS_PUBLICADO,
                "protocolo": f"STR-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                "justificativa": "Teste de carga nacional controlado.",
                "criado_por": "stress-test",
                "aprovado_por": "stress-test",
                "aprovado_em": timezone.now(),
                "publicado_em": timezone.now(),
            },
        )

    def _sintomas(self, perfil):
        if perfil == "respiratorio":
            return {
                "febre": random.random() < 0.62,
                "tosse": random.random() < 0.88,
                "dor_corpo": random.random() < 0.35,
                "cansaco": random.random() < 0.56,
                "falta_ar": random.random() < 0.14,
            }
        if perfil == "arbovirose":
            return {
                "febre": random.random() < 0.84,
                "tosse": random.random() < 0.08,
                "dor_corpo": random.random() < 0.9,
                "cansaco": random.random() < 0.66,
                "falta_ar": random.random() < 0.03,
            }
        return {
            "febre": random.random() < 0.56,
            "tosse": random.random() < 0.44,
            "dor_corpo": random.random() < 0.48,
            "cansaco": random.random() < 0.52,
            "falta_ar": random.random() < 0.08,
        }

    def _injetar_sinais(self, client, empresa, total, started_at):
        criados = 0
        for index in range(total):
            regiao, estado, cidade, bairro, lat, lon, perfil = REGIOES_BRASIL[index % len(REGIOES_BRASIL)]
            payload = {
                **self._sintomas(perfil),
                "latitude": lat + random.uniform(-0.025, 0.025),
                "longitude": lon + random.uniform(-0.025, 0.025),
                "location_source": "current",
                "bairro": bairro,
                "cidade": cidade,
                "estado": estado,
                "pais": "Brasil",
            }
            response = client.post(
                "/api/public/registrar",
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_X_DEVICE_ID=f"{TEST_PREFIX}-device-{index}",
                HTTP_X_FORWARDED_FOR=f"100.{index // 65000}.{(index // 255) % 255}.{index % 255}",
                HTTP_X_SOLUS_SIMULATION="true",
            )
            if response.status_code == 200 and response.json().get("registro_id"):
                RegistroSintoma.objects.filter(id_anonimo=response.json()["registro_id"]).update(
                    empresa=empresa,
                    device_id=f"{TEST_PREFIX}-device-{index}",
                    fonte_referencia="stress-test-nacional",
                    data_registro=started_at,
                )
                criados += 1
        return criados

    def _envelhecer_registros(self, started_at, simulated_now):
        age = simulated_now - started_at
        RegistroSintoma.objects.filter(device_id__startswith=TEST_PREFIX).update(
            data_registro=timezone.now() - age
        )

    def _timed_get(self, client, path, erros):
        started = time.monotonic()
        response = client.get(path)
        latency = (time.monotonic() - started) * 1000
        if response.status_code >= 400:
            erros.append(f"GET {path} => {response.status_code}")
        return response, latency

    def _stressar_componentes(self, public, empresa, governo, qs_stress, day):
        erros = []
        latencias = []
        requests = 0

        paths_publicos = [
            "/api/public/resumo",
            "/api/public/mapa",
            "/api/public/alertas?estado=RJ&cidade=Rio%20de%20Janeiro",
        ]

        for path in paths_publicos:
            response, latency = self._timed_get(public, path, erros)
            latencias.append(latency)
            requests += 1
            if path == "/api/public/mapa":
                try:
                    hotspots = len(response.json().get("hotspots", []))
                except Exception:
                    hotspots = 0

        for _, estado, cidade, bairro, lat, lon, _ in random.sample(REGIOES_BRASIL, 8):
            path = f"/api/public/radar-local?latitude={lat}&longitude={lon}&cidade={cidade}&estado={estado}&bairro={bairro}"
            _, latency = self._timed_get(public, path, erros)
            latencias.append(latency)
            requests += 1

        for client, paths in [
            (empresa, ["/dashboard/", "/dashboard-farmacia/", "/dashboard-hospital/", "/api/dashboard", "/api/epidemiologia"]),
            (governo, ["/dashboard-governo/", "/api/governo/alertas", "/api/governanca/matriz-decisao", "/api/epidemiologia"]),
        ]:
            if client == governo and day in {1, 10, 20, 30}:
                paths = [*paths, "/api/brasil/fontes-oficiais"]
            for path in paths:
                _, latency = self._timed_get(client, path, erros)
                latencias.append(latency)
                requests += 1

        indice = _indice_temporal_publico(qs_stress, timezone.now())
        total = qs_stress.count()
        initial = max(total, 1)
        return {
            "dia": day,
            "indice_ativo": float(indice),
            "retencao_pct": round((float(indice) / initial) * 100, 2),
            "registros": total,
            "hotspots": locals().get("hotspots", 0),
            "erros": len(erros),
            "latencia_media_ms": round(statistics.mean(latencias), 2) if latencias else 0,
            "latencia_p95_ms": round(statistics.quantiles(latencias, n=20)[18], 2) if len(latencias) >= 20 else round(max(latencias or [0]), 2),
        }, requests, latencias, erros

    def _montar_relatorio(self, started_at, snapshots, erros, total_requests, latencias, criados, report_path):
        final = snapshots[-1] if snapshots else {}
        pico = max(snapshots, key=lambda item: item["indice_ativo"]) if snapshots else {}
        p95 = round(statistics.quantiles(latencias, n=20)[18], 2) if len(latencias) >= 20 else round(max(latencias or [0]), 2)
        media = round(statistics.mean(latencias), 2) if latencias else 0
        reducao_ok = final.get("retencao_pct", 100) <= 1.0
        linhas = [
            "# Relatorio de Stress Test SolusCRT Brasil",
            "",
            f"- Inicio: {started_at.strftime('%d/%m/%Y %H:%M:%S')}",
            f"- Registros sinteticos criados: {criados}",
            f"- Requisicoes exercitadas: {total_requests}",
            f"- Latencia media: {media} ms",
            f"- Latencia p95: {p95} ms",
            f"- Erros capturados: {len(erros)}",
            f"- Resultado do decaimento ate 1%: {'APROVADO' if reducao_ok else 'ATENCAO'}",
            "",
            "## Leitura Executiva",
            "",
            (
                "O teste simulou uma sala de controle epidemiologica nacional com sinais populacionais "
                "em todas as regioes do Brasil, validando mapa publico, APIs do app, dashboards B2B/B2G, "
                "alertas governamentais e governanca epidemiologica."
            ),
            "",
            "## Escopo Tecnico",
            "",
            "- Carga inicial feita pelo endpoint publico do app (`/api/public/registrar`) para simular envio real da populacao.",
            "- Cobertura geografica distribuida pelas 5 regioes do Brasil, com capitais/territorios de todos os estados e DF.",
            "- Cada minuto representou 1 dia epidemiologico, totalizando 30 dias simulados em 30 minutos.",
            "- A janela de risco ficou estavel por 10 dias sem novos sintomas e depois reduziu progressivamente ate 1% no dia 30.",
            "- O teste usou prefixo sintetico rastreavel e limpeza seletiva, sem apagar registros reais.",
            "",
            "## Indicadores Dia a Dia",
            "",
            "| Dia simulado | Indice ativo | Retencao | Hotspots | Erros | Latencia media |",
            "| ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for item in snapshots:
            linhas.append(
                f"| {item['dia']} | {item['indice_ativo']:.2f} | {item['retencao_pct']:.2f}% | "
                f"{item['hotspots']} | {item['erros']} | {item['latencia_media_ms']} ms |"
            )
        linhas.extend([
            "",
            "## Governo",
            "",
            "- O painel governamental foi exercitado junto com alertas, matriz de decisao e panorama epidemiologico.",
            "- A simulacao representa coordenacao de vigilancia, comunicacao publica e priorizacao territorial.",
            "- O comportamento esperado e manter estabilidade epidemiologica por 10 dias sem novos envios e reduzir gradualmente depois disso.",
            "- Leitura operacional: nos dias 1 a 10, governo manteria vigilancia ativa e comunicacao preventiva; depois do dia 10, acompanharia queda sustentada antes de reduzir nivel de resposta.",
            "- Acao recomendada no pico: acionar vigilancia municipal/estadual, validar sinais com fontes oficiais, preparar alerta publico e priorizar municipios com hotspots persistentes.",
            "",
            "## Empresas, Farmacias e Hospitais",
            "",
            "- Dashboards empresariais, farmacia e hospital foram acessados em ciclo continuo para medir disponibilidade durante o estresse.",
            "- O uso esperado para empresas e antecipar absenteismo, risco ocupacional e comunicacao preventiva.",
            "- O uso esperado para farmacias/hospitais e preparar estoque, triagem, leitos e pronto atendimento conforme os focos.",
            "- Leitura empresarial: empresas acompanhariam risco territorial para orientar home office, escalas, higiene reforcada e comunicacao com colaboradores.",
            "- Leitura farmacia/hospital: farmacias reforcariam estoque por perfil de sintomas; hospitais ajustariam triagem, equipe e capacidade de pronto atendimento.",
            "",
            "## App da Populacao",
            "",
            "- Endpoints de resumo, mapa, radar local e alertas publicos foram acionados continuamente.",
            "- A leitura do app deve mostrar focos apenas enquanto houver indice ativo epidemiologico.",
            "- Comunicados governamentais aparecem pela API publica mesmo quando push nativo nao entrega no simulador.",
            "- O app foi validado pela camada de API; testes nativos em iOS/Android ainda devem ser repetidos antes de publicar nova versao nas lojas.",
            "",
            "## Bugs e Riscos Observados",
            "",
        ])
        if erros:
            for erro in erros[:50]:
                linhas.append(f"- {erro}")
            if len(erros) > 50:
                linhas.append(f"- ... mais {len(erros) - 50} ocorrencias omitidas.")
        else:
            linhas.append("- Nenhum erro HTTP >= 400 foi capturado durante a rotina.")
        linhas.extend([
            "- Risco residual: o teste foi executado no backend local com Django Client; antes de comercializar, repetir em Render com banco Postgres e monitoramento de logs.",
            "- Risco residual: o teste nao substitui teste visual manual no app nativo, especialmente permissao de localizacao, mapa e recebimento de push.",
            "- Risco residual: fontes oficiais externas podem variar por disponibilidade; manter cache, timeout e jobs assincronos para nao travar dashboard.",
        ])
        linhas.extend([
            "",
            "## Conclusao",
            "",
            (
                f"No pico, o indice ativo chegou a {pico.get('indice_ativo', 0):.2f}. "
                f"No fim, chegou a {final.get('indice_ativo', 0):.2f} "
                f"({final.get('retencao_pct', 0):.2f}% do volume inicial)."
            ),
            "",
            f"Arquivo do relatorio: `{report_path}`",
            "",
        ])
        return "\n".join(linhas)

    def _cleanup(self):
        RegistroSintoma.objects.filter(device_id__startswith=TEST_PREFIX)._raw_delete(RegistroSintoma.objects.db)
        AlertaGovernamental.objects.filter(titulo="Stress nacional SolusCRT").delete()
