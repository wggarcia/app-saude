from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.utils import timezone

from api.models import Empresa, EmpresaUsuario, RBACAtribuicao, RBACPermissao
from api.planos import detalhes_pacote


SEVERITY_ORDER = {"critica": 0, "alta": 1, "media": 2, "baixa": 3}


@dataclass
class SegmentConfig:
    slug: str
    label: str
    pacote: str
    tipo_conta: str
    acesso_governo: bool
    login_endpoint: str
    admin_dashboard: str
    operacao_page: str
    ti_page: str
    own_api: str


SEGMENTS = [
    SegmentConfig(
        slug="sst",
        label="SST",
        pacote="empresa_profissional_25",
        tipo_conta=Empresa.TIPO_EMPRESA,
        acesso_governo=False,
        login_endpoint="/api/login",
        admin_dashboard="/dashboard-empresa/",
        operacao_page="/gestao/",
        ti_page="/ti/",
        own_api="/api/sst/dashboard",
    ),
    SegmentConfig(
        slug="farmacia",
        label="Farmacia",
        pacote="farmacia_rede_regional",
        tipo_conta=Empresa.TIPO_EMPRESA,
        acesso_governo=False,
        login_endpoint="/api/login",
        admin_dashboard="/dashboard-farmacia/",
        operacao_page="/farmacia/gestao/",
        ti_page="/ti/",
        own_api="/api/farmacia/dashboard",
    ),
    SegmentConfig(
        slug="hospital",
        label="Hospital",
        pacote="hospital_medio",
        tipo_conta=Empresa.TIPO_EMPRESA,
        acesso_governo=False,
        login_endpoint="/api/login",
        admin_dashboard="/dashboard-hospital/",
        operacao_page="/hospital/gestao/",
        ti_page="/ti/",
        own_api="/api/hospital/dashboard",
    ),
    SegmentConfig(
        slug="plano_saude",
        label="Plano de Saude",
        pacote="plano_saude_operadora",
        tipo_conta=Empresa.TIPO_EMPRESA,
        acesso_governo=False,
        login_endpoint="/api/login",
        admin_dashboard="/dashboard-plano-saude/",
        operacao_page="/plano-saude/gestao/",
        ti_page="/ti/",
        own_api="/api/plano-saude/dashboard",
    ),
    SegmentConfig(
        slug="governo",
        label="Governo",
        pacote="governo_municipio_pequeno",
        tipo_conta=Empresa.TIPO_GOVERNO,
        acesso_governo=True,
        login_endpoint="/api/login-governo",
        admin_dashboard="/dashboard-governo/",
        operacao_page="/governo/gestao/",
        ti_page="/governo/plataforma/",
        own_api="/api/governo/programas/",
    ),
]


FOREIGN_DASHBOARDS = [
    "/dashboard-empresa/",
    "/dashboard-farmacia/",
    "/dashboard-hospital/",
    "/dashboard-plano-saude/",
    "/dashboard-governo/",
]
FOREIGN_GESTAO_PAGES = [
    "/gestao/",
    "/farmacia/gestao/",
    "/hospital/gestao/",
    "/plano-saude/gestao/",
    "/governo/gestao/",
]
FOREIGN_APIS = [
    "/api/sst/dashboard",
    "/api/farmacia/dashboard",
    "/api/hospital/dashboard",
    "/api/plano-saude/dashboard",
    "/api/governo/programas/",
]

SEGMENT_MARKERS = {
    "sst": ["/sst/", "/gestao/", "/dashboard-empresa/"],
    "farmacia": ["/farmacia/", "/dashboard-farmacia/"],
    "hospital": ["/hospital/", "/dashboard-hospital/"],
    "plano_saude": ["/plano-saude/", "/dashboard-plano-saude/"],
    "governo": ["/governo/", "/dashboard-governo/", "/contrato-governo/"],
}


class Command(BaseCommand):
    help = (
        "Robo de auditoria funcional multiambiente. "
        "Simula cliente ativo, testa isolamento entre segmentos/perfis e gera relatorio."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-path",
            default="",
            help="Caminho do relatorio Markdown. Default: docs/auditorias/ROBO_AUDITORIA_AMBIENTES_<timestamp>.md",
        )
        parser.add_argument(
            "--json-path",
            default="",
            help="Caminho opcional para salvar o resultado em JSON.",
        )
        parser.add_argument(
            "--keep-fixtures",
            action="store_true",
            help="Nao remove contas de teste criadas pelo robo ao final.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Retorna erro (exit 1) se houver achados de severidade critica/alta.",
        )

    def handle(self, *args, **options):
        ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        run_tag = f"robo-auditoria-{ts}"

        report_path = options["report_path"] or f"docs/auditorias/ROBO_AUDITORIA_AMBIENTES_{ts}.md"
        json_path = options["json_path"] or ""
        keep_fixtures = bool(options["keep_fixtures"])
        strict_mode = bool(options["strict"])

        checks: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        fixtures: list[Empresa] = []

        self.stdout.write(self.style.MIGRATE_HEADING("[ROBO] Auditoria funcional de ambientes"))
        self.stdout.write(f"Execucao: {run_tag}")

        try:
            for segment in SEGMENTS:
                fixture = self._provision_segment(segment, run_tag)
                fixtures.append(fixture["empresa"])
                self._run_segment_audit(segment, fixture, checks, findings)

            report = self._build_report(run_tag, checks, findings)
            self._write_outputs(report_path, json_path, report)

            self.stdout.write(self.style.SUCCESS("[ROBO] Auditoria concluida"))
            self.stdout.write(f"Relatorio: {report_path}")
            if json_path:
                self.stdout.write(f"JSON: {json_path}")

            summary = report["summary"]
            self.stdout.write(
                "Resumo -> "
                f"checks: {summary['checks_total']} | "
                f"ok: {summary['checks_ok']} | "
                f"falhas: {summary['checks_fail']} | "
                f"critica: {summary['severity']['critica']} | "
                f"alta: {summary['severity']['alta']} | "
                f"media: {summary['severity']['media']} | "
                f"baixa: {summary['severity']['baixa']}"
            )

            if strict_mode and (summary["severity"]["critica"] > 0 or summary["severity"]["alta"] > 0):
                raise CommandError("Robo encontrou achados criticos/altos (strict mode).")

        finally:
            if not keep_fixtures:
                for empresa in fixtures:
                    Empresa.objects.filter(id=empresa.id).delete()
                self.stdout.write("Fixtures temporarias removidas.")
            else:
                self.stdout.write(self.style.WARNING("Fixtures mantidas por --keep-fixtures."))

    def _provision_segment(self, cfg: SegmentConfig, run_tag: str) -> dict[str, Any]:
        suffix = cfg.slug.replace("_", "-")
        senha = "SenhaRobo123!"
        pacote = detalhes_pacote(cfg.pacote)

        empresa = Empresa.objects.create(
            nome=f"Robo {cfg.label} {run_tag}",
            email=f"{run_tag}-{suffix}@soluscrt.local",
            senha=make_password(senha),
            ativo=True,
            tipo_conta=cfg.tipo_conta,
            acesso_governo=cfg.acesso_governo,
            pacote_codigo=cfg.pacote,
            plano="anual" if cfg.tipo_conta == Empresa.TIPO_GOVERNO else "mensal",
            max_dispositivos=pacote["dispositivos"],
            max_usuarios=pacote["usuarios"],
        )

        usuarios = {
            "operacao": EmpresaUsuario.objects.create(
                empresa=empresa,
                nome=f"Operacao {cfg.label}",
                email=f"op-{run_tag}-{suffix}@soluscrt.local",
                senha=make_password(senha),
                cargo="Operacao",
                ativo=True,
            ),
            "rh": EmpresaUsuario.objects.create(
                empresa=empresa,
                nome=f"RH {cfg.label}",
                email=f"rh-{run_tag}-{suffix}@soluscrt.local",
                senha=make_password(senha),
                cargo="RH",
                ativo=True,
            ),
            "gerencia": EmpresaUsuario.objects.create(
                empresa=empresa,
                nome=f"Gerencia {cfg.label}",
                email=f"ger-{run_tag}-{suffix}@soluscrt.local",
                senha=make_password(senha),
                cargo="Gerente Operacional",
                ativo=True,
            ),
            "ti": EmpresaUsuario.objects.create(
                empresa=empresa,
                nome=f"TI {cfg.label}",
                email=f"ti-{run_tag}-{suffix}@soluscrt.local",
                senha=make_password(senha),
                cargo="TI",
                ativo=True,
            ),
        }

        permissao, _ = RBACPermissao.objects.get_or_create(
            codigo="plataforma_ti",
            defaults={
                "descricao": "Acesso exclusivo a Plataforma TI",
                "modulo": "ti",
            },
        )
        RBACAtribuicao.objects.update_or_create(
            empresa=empresa,
            usuario=usuarios["ti"],
            permissao=permissao,
            defaults={"ativo": True, "concedido_por": f"{run_tag}-setup"},
        )

        return {
            "empresa": empresa,
            "senha": senha,
            "usuarios": usuarios,
        }

    def _run_segment_audit(
        self,
        cfg: SegmentConfig,
        fixture: dict[str, Any],
        checks: list[dict[str, Any]],
        findings: list[dict[str, Any]],
    ):
        self.stdout.write(f"- Auditando {cfg.label}...")

        empresa = fixture["empresa"]
        senha = fixture["senha"]
        users = fixture["usuarios"]

        admin_client = Client()
        login = self._login(admin_client, cfg.login_endpoint, empresa.email, senha, f"admin-{cfg.slug}")
        self._assert_check(
            checks,
            findings,
            segment=cfg.slug,
            kind="auth",
            title="Login administrador",
            path=cfg.login_endpoint,
            ok=login["status"] == 200,
            expected="HTTP 200",
            observed=f"HTTP {login['status']}",
            severity="critica",
            evidence=login.get("body", ""),
        )

        destination = login.get("json", {}).get("destination") if login.get("json") else None
        self._assert_check(
            checks,
            findings,
            segment=cfg.slug,
            kind="auth",
            title="Destino de login administrador",
            path=cfg.login_endpoint,
            ok=destination == cfg.admin_dashboard,
            expected=cfg.admin_dashboard,
            observed=str(destination),
            severity="alta",
            evidence=login.get("body", ""),
        )

        resp_dashboard = admin_client.get("/dashboard/")
        location = resp_dashboard.get("Location", "")
        self._assert_check(
            checks,
            findings,
            segment=cfg.slug,
            kind="navigation",
            title="/dashboard/ redireciona para o ambiente correto",
            path="/dashboard/",
            ok=resp_dashboard.status_code == 302 and location == cfg.admin_dashboard,
            expected=f"302 -> {cfg.admin_dashboard}",
            observed=f"{resp_dashboard.status_code} -> {location}",
            severity="alta",
        )

        own_pages = [cfg.admin_dashboard, cfg.operacao_page]
        if cfg.slug == "sst":
            own_pages.append("/sst/")
        for path in own_pages:
            resp = admin_client.get(path)
            ok = resp.status_code in {200, 302}
            severity = "critica" if resp.status_code >= 500 else "alta"
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="own_page",
                title=f"Pagina propria acessivel ({path})",
                path=path,
                ok=ok,
                expected="HTTP 200/302",
                observed=f"HTTP {resp.status_code}",
                severity=severity,
                evidence=resp.get("Location", ""),
            )

        own_api_resp = admin_client.get(cfg.own_api)
        self._assert_check(
            checks,
            findings,
            segment=cfg.slug,
            kind="own_api",
            title=f"API propria acessivel ({cfg.own_api})",
            path=cfg.own_api,
            ok=own_api_resp.status_code == 200,
            expected="HTTP 200",
            observed=f"HTTP {own_api_resp.status_code}",
            severity="critica" if own_api_resp.status_code >= 500 else "alta",
        )

        blocked_pages = [p for p in (FOREIGN_DASHBOARDS + FOREIGN_GESTAO_PAGES) if p not in {cfg.admin_dashboard, cfg.operacao_page}]
        if cfg.slug == "sst":
            blocked_pages = [p for p in blocked_pages if p != "/gestao/"]
        for path in blocked_pages:
            resp = admin_client.get(path)
            ok = resp.status_code != 200
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="cross_page",
                title=f"Bloqueio pagina cruzada ({path})",
                path=path,
                ok=ok,
                expected="Nao retornar 200",
                observed=f"HTTP {resp.status_code}",
                severity="critica",
                evidence=resp.get("Location", ""),
            )

        blocked_apis = [p for p in FOREIGN_APIS if p != cfg.own_api]
        for path in blocked_apis:
            resp = admin_client.get(path)
            ok = resp.status_code in {401, 403}
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="cross_api",
                title=f"Bloqueio API cruzada ({path})",
                path=path,
                ok=ok,
                expected="HTTP 401/403",
                observed=f"HTTP {resp.status_code}",
                severity="critica",
            )

        html_pages = [cfg.admin_dashboard, cfg.operacao_page]
        if cfg.slug == "sst":
            html_pages.append("/dashboard-empresa/")
        for page in html_pages:
            links = self._extract_links(admin_client, page)
            mixed = self._foreign_links_for_segment(cfg.slug, links)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="link_mix",
                title=f"Sem links misturados em {page}",
                path=page,
                ok=len(mixed) == 0,
                expected="0 links para outros segmentos",
                observed=f"{len(mixed)} link(s) suspeito(s)",
                severity="alta",
                evidence=", ".join(mixed[:12]),
            )

        role_expect_destination = {
            "operacao": cfg.admin_dashboard if cfg.slug in {"sst", "governo"} else cfg.operacao_page,
            "rh": "/rh/",
            "gerencia": "/gerencia/",
            "ti": cfg.ti_page,
        }

        clients: dict[str, Client] = {}
        for role, user in users.items():
            client = Client()
            clients[role] = client
            login_resp = self._login(client, cfg.login_endpoint, user.email, senha, f"{role}-{cfg.slug}")
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_auth",
                title=f"Login perfil {role}",
                path=cfg.login_endpoint,
                ok=login_resp["status"] == 200,
                expected="HTTP 200",
                observed=f"HTTP {login_resp['status']}",
                severity="alta",
                evidence=login_resp.get("body", ""),
            )
            destination_role = login_resp.get("json", {}).get("destination") if login_resp.get("json") else None
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_auth",
                title=f"Destino perfil {role}",
                path=cfg.login_endpoint,
                ok=destination_role == role_expect_destination[role],
                expected=role_expect_destination[role],
                observed=str(destination_role),
                severity="alta",
            )

        for role in ["operacao", "gerencia"]:
            resp = clients[role].get(cfg.operacao_page)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_access",
                title=f"{role} acessa pagina operacional",
                path=cfg.operacao_page,
                ok=resp.status_code == 200,
                expected="HTTP 200",
                observed=f"HTTP {resp.status_code}",
                severity="alta",
            )
        for role in ["rh", "ti"]:
            resp = clients[role].get(cfg.operacao_page)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_access",
                title=f"{role} bloqueado na pagina operacional",
                path=cfg.operacao_page,
                ok=resp.status_code != 200,
                expected="Nao retornar 200",
                observed=f"HTTP {resp.status_code}",
                severity="alta",
                evidence=resp.get("Location", ""),
            )

        for role in ["ti", "gerencia"]:
            resp = clients[role].get(cfg.ti_page)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_access",
                title=f"{role} acessa portal TI",
                path=cfg.ti_page,
                ok=resp.status_code == 200,
                expected="HTTP 200",
                observed=f"HTTP {resp.status_code}",
                severity="alta",
            )
        for role in ["operacao", "rh"]:
            resp = clients[role].get(cfg.ti_page)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_access",
                title=f"{role} bloqueado no portal TI",
                path=cfg.ti_page,
                ok=resp.status_code != 200,
                expected="Nao retornar 200",
                observed=f"HTTP {resp.status_code}",
                severity="alta",
                evidence=resp.get("Location", ""),
            )

        for role in ["operacao", "gerencia"]:
            resp = clients[role].get(cfg.own_api)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_api",
                title=f"{role} acessa API operacional",
                path=cfg.own_api,
                ok=resp.status_code == 200,
                expected="HTTP 200",
                observed=f"HTTP {resp.status_code}",
                severity="alta",
            )
        for role in ["rh", "ti"]:
            resp = clients[role].get(cfg.own_api)
            self._assert_check(
                checks,
                findings,
                segment=cfg.slug,
                kind="role_api",
                title=f"{role} bloqueado na API operacional",
                path=cfg.own_api,
                ok=resp.status_code in {401, 403},
                expected="HTTP 401/403",
                observed=f"HTTP {resp.status_code}",
                severity="alta",
            )

    def _login(self, client: Client, endpoint: str, email: str, senha: str, device_id: str) -> dict[str, Any]:
        payload = {
            "email": email,
            "senha": senha,
            "device_id": device_id,
            "device_name": "Robo Auditoria",
        }
        resp = client.post(endpoint, data=json.dumps(payload), content_type="application/json")
        if resp.status_code == 409:
            try:
                data = resp.json()
            except Exception:
                data = {}
            if data.get("acao") == "force_login":
                payload["force_login"] = True
                resp = client.post(endpoint, data=json.dumps(payload), content_type="application/json")

        try:
            data = resp.json()
        except Exception:
            data = None

        return {
            "status": resp.status_code,
            "json": data,
            "body": getattr(resp, "content", b"")[:1000].decode("utf-8", errors="ignore"),
        }

    def _assert_check(
        self,
        checks: list[dict[str, Any]],
        findings: list[dict[str, Any]],
        *,
        segment: str,
        kind: str,
        title: str,
        path: str,
        ok: bool,
        expected: str,
        observed: str,
        severity: str,
        evidence: str = "",
    ):
        item = {
            "segment": segment,
            "kind": kind,
            "title": title,
            "path": path,
            "ok": ok,
            "expected": expected,
            "observed": observed,
            "severity": severity,
            "evidence": evidence,
        }
        checks.append(item)
        if not ok:
            findings.append(item)

    def _extract_links(self, client: Client, path: str) -> list[str]:
        resp = client.get(path, follow=True)
        if resp.status_code != 200:
            return []
        html = getattr(resp, "content", b"").decode("utf-8", errors="ignore")
        links = re.findall(r"href=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
        return [link.strip() for link in links if link.strip()]

    def _foreign_links_for_segment(self, segment_slug: str, links: list[str]) -> list[str]:
        own_markers = SEGMENT_MARKERS[segment_slug]
        mixed = []

        for link in links:
            if link.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            if not link.startswith("/"):
                continue
            if any(link.startswith(prefix) for prefix in ("/static/", "/media/", "/api/", "/logout", "/sair", "/usuarios/", "/rh/", "/gerencia/", "/ti/", "/governo/plataforma/", "/command-ai/", "/sala-decisao-ia/")):
                continue

            if any(link.startswith(mk) for mk in own_markers):
                continue

            for other_segment, markers in SEGMENT_MARKERS.items():
                if other_segment == segment_slug:
                    continue
                if any(link.startswith(mk) for mk in markers):
                    mixed.append(link)
                    break

        return sorted(set(mixed))

    def _build_report(self, run_tag: str, checks: list[dict[str, Any]], findings: list[dict[str, Any]]) -> dict[str, Any]:
        checks_total = len(checks)
        checks_ok = sum(1 for c in checks if c["ok"])
        checks_fail = checks_total - checks_ok

        severity_count = {"critica": 0, "alta": 0, "media": 0, "baixa": 0}
        for f in findings:
            severity_count[f["severity"]] = severity_count.get(f["severity"], 0) + 1

        findings_sorted = sorted(
            findings,
            key=lambda f: (SEVERITY_ORDER.get(f["severity"], 99), f["segment"], f["title"]),
        )

        by_segment: dict[str, dict[str, Any]] = {}
        for segment in [cfg.slug for cfg in SEGMENTS]:
            by_segment[segment] = {
                "checks_total": 0,
                "checks_ok": 0,
                "checks_fail": 0,
                "severity": {"critica": 0, "alta": 0, "media": 0, "baixa": 0},
            }

        for check in checks:
            slot = by_segment[check["segment"]]
            slot["checks_total"] += 1
            if check["ok"]:
                slot["checks_ok"] += 1
            else:
                slot["checks_fail"] += 1
                slot["severity"][check["severity"]] += 1

        markdown = self._build_markdown(run_tag, checks_total, checks_ok, checks_fail, severity_count, by_segment, findings_sorted)

        return {
            "meta": {
                "run_tag": run_tag,
                "generated_at": timezone.localtime().isoformat(),
            },
            "summary": {
                "checks_total": checks_total,
                "checks_ok": checks_ok,
                "checks_fail": checks_fail,
                "severity": severity_count,
            },
            "segments": by_segment,
            "findings": findings_sorted,
            "checks": checks,
            "markdown": markdown,
        }

    def _build_markdown(
        self,
        run_tag: str,
        checks_total: int,
        checks_ok: int,
        checks_fail: int,
        severity_count: dict[str, int],
        by_segment: dict[str, dict[str, Any]],
        findings_sorted: list[dict[str, Any]],
    ) -> str:
        lines: list[str] = []
        lines.append("# Relatorio do Robo de Auditoria de Ambientes")
        lines.append("")
        lines.append(f"Execucao: `{run_tag}`")
        lines.append(f"Gerado em: `{timezone.localtime().strftime('%Y-%m-%d %H:%M:%S %Z')}`")
        lines.append("")
        lines.append("## Resumo Executivo")
        lines.append(f"- Checks totais: **{checks_total}**")
        lines.append(f"- Checks OK: **{checks_ok}**")
        lines.append(f"- Checks com falha: **{checks_fail}**")
        lines.append(f"- Critica: **{severity_count['critica']}**")
        lines.append(f"- Alta: **{severity_count['alta']}**")
        lines.append(f"- Media: **{severity_count['media']}**")
        lines.append(f"- Baixa: **{severity_count['baixa']}**")
        lines.append("")

        lines.append("## Resultado por Ambiente")
        lines.append("| Ambiente | OK/Total | Falhas | Critica | Alta | Media | Baixa |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        label_map = {cfg.slug: cfg.label for cfg in SEGMENTS}
        for slug in [cfg.slug for cfg in SEGMENTS]:
            slot = by_segment[slug]
            lines.append(
                "| "
                f"{label_map[slug]} | "
                f"{slot['checks_ok']}/{slot['checks_total']} | "
                f"{slot['checks_fail']} | "
                f"{slot['severity']['critica']} | "
                f"{slot['severity']['alta']} | "
                f"{slot['severity']['media']} | "
                f"{slot['severity']['baixa']} |"
            )
        lines.append("")

        lines.append("## Achados Priorizados")
        if not findings_sorted:
            lines.append("Nenhum achado. Todos os checks passaram.")
        else:
            for idx, finding in enumerate(findings_sorted, start=1):
                lines.append(
                    f"{idx}. [{finding['severity'].upper()}] [{finding['segment']}] {finding['title']}"
                )
                lines.append(f"Caminho: `{finding['path']}`")
                lines.append(f"Esperado: {finding['expected']}")
                lines.append(f"Obtido: {finding['observed']}")
                if finding.get("evidence"):
                    lines.append(f"Evidencia: `{finding['evidence']}`")
                lines.append("")

        lines.append("## Recomendacoes de Correcao")
        lines.append("1. Corrigir primeiro todos os achados CRITICA (acesso cruzado 200, API propria fora do ar, login/destino quebrado).")
        lines.append("2. Depois tratar os achados ALTA (links misturados, regras de perfil inconsistentes, redirecionamentos incorretos).")
        lines.append("3. Reexecutar este robo apos cada lote de ajustes para validar regressao zero.")
        lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _write_outputs(self, report_path: str, json_path: str, report: dict[str, Any]):
        path_md = Path(report_path)
        path_md.parent.mkdir(parents=True, exist_ok=True)
        path_md.write_text(report["markdown"], encoding="utf-8")

        if json_path:
            path_json = Path(json_path)
            path_json.parent.mkdir(parents=True, exist_ok=True)
            payload = {k: v for k, v in report.items() if k != "markdown"}
            path_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
