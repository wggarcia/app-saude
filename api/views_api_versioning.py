"""
API Versioning + Rate Limiting + Circuit Breaker.
Middleware e decoradores para engenharia de escala enterprise.

- /api/v1/  → versão estável (alias para endpoints atuais)
- /api/v2/  → versão com response envelope { data, meta, version }
- Rate limiting por empresa (sliding window em memória)
- Circuit breaker por domínio (trip após 5 falhas em 60s)
- Request ID + latência no header de resposta
"""
import time
import uuid
import functools
from collections import defaultdict, deque
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from .views_dashboard import _empresa_autenticada


# ─── Rate Limiter (sliding window, in-process) ────────────────────────────────
# Para produção real: usar Redis. Aqui é por processo (suficiente para Render single-instance).

class _RateLimiter:
    def __init__(self):
        self._windows: dict[str, deque] = defaultdict(deque)
        self._limits = {
            "default":    (300, 60),   # 300 req / 60s
            "basico":     (200, 60),
            "profissional":(500, 60),
            "enterprise": (2000, 60),
            "governo":    (1000, 60),
            "hospital":   (1000, 60),
        }

    def check(self, key: str, plano: str = "default") -> tuple[bool, int, int]:
        """Retorna (permitido, restante, reset_em_segundos)."""
        limit, window = self._limits.get(plano, self._limits["default"])
        now = time.monotonic()
        dq = self._windows[key]
        cutoff = now - window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            oldest = dq[0]
            reset_in = int(window - (now - oldest)) + 1
            return False, 0, reset_in
        dq.append(now)
        return True, limit - len(dq), window


_rate_limiter = _RateLimiter()


# ─── Circuit Breaker ──────────────────────────────────────────────────────────

class _CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, threshold=5, timeout=60, half_open_max=2):
        self._states: dict[str, str] = {}
        self._failures: dict[str, list] = defaultdict(list)
        self._opened_at: dict[str, float] = {}
        self._half_open_calls: dict[str, int] = defaultdict(int)
        self.threshold = threshold
        self.timeout = timeout
        self.half_open_max = half_open_max

    def state(self, circuit: str) -> str:
        st = self._states.get(circuit, self.CLOSED)
        if st == self.OPEN:
            if time.monotonic() - self._opened_at.get(circuit, 0) > self.timeout:
                self._states[circuit] = self.HALF_OPEN
                self._half_open_calls[circuit] = 0
                return self.HALF_OPEN
        return st

    def record_success(self, circuit: str):
        self._states[circuit] = self.CLOSED
        self._failures[circuit] = []
        self._half_open_calls[circuit] = 0

    def record_failure(self, circuit: str):
        now = time.monotonic()
        failures = self._failures[circuit]
        failures = [t for t in failures if now - t < self.timeout]
        failures.append(now)
        self._failures[circuit] = failures
        if len(failures) >= self.threshold:
            self._states[circuit] = self.OPEN
            self._opened_at[circuit] = now

    def allow_request(self, circuit: str) -> bool:
        st = self.state(circuit)
        if st == self.CLOSED:
            return True
        if st == self.HALF_OPEN:
            if self._half_open_calls[circuit] < self.half_open_max:
                self._half_open_calls[circuit] += 1
                return True
            return False
        return False  # OPEN

    def status_all(self) -> dict:
        circuits = set(self._states.keys()) | set(self._failures.keys())
        return {
            c: {
                "estado": self.state(c),
                "falhas_recentes": len([t for t in self._failures.get(c, []) if time.monotonic() - t < self.timeout]),
            }
            for c in circuits
        }


_circuit_breaker = _CircuitBreaker()


# ─── Middleware ───────────────────────────────────────────────────────────────

class EnterpriseAPIMiddleware(MiddlewareMixin):
    """Adiciona Request-ID, X-Response-Time e Rate-Limit headers."""

    API_PATHS = ("/api/",)

    def process_request(self, request):
        request._start_time = time.monotonic()
        request._request_id = str(uuid.uuid4())[:8]

    def process_response(self, request, response):
        if not any(request.path.startswith(p) for p in self.API_PATHS):
            return response

        elapsed = round((time.monotonic() - getattr(request, "_start_time", time.monotonic())) * 1000, 1)
        response["X-Request-ID"] = getattr(request, "_request_id", "—")
        response["X-Response-Time-Ms"] = str(elapsed)
        response["X-API-Version"] = "2.0"
        return response


# ─── Decoradores ──────────────────────────────────────────────────────────────

def rate_limit(view_func):
    """Decorator: aplica rate limiting por empresa."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        empresa = _empresa_autenticada(request)
        if empresa:
            key = f"empresa:{empresa.id}"
            plano = empresa.pacote_codigo or "default"
            allowed, remaining, reset_in = _rate_limiter.check(key, plano)
            if not allowed:
                resp = JsonResponse({
                    "erro": "Rate limit excedido",
                    "retry_after_segundos": reset_in,
                }, status=429)
                resp["Retry-After"] = str(reset_in)
                resp["X-RateLimit-Remaining"] = "0"
                return resp
        return view_func(request, *args, **kwargs)
    return wrapper


def circuit_breaker(circuit_name):
    """Decorator: protege um endpoint com circuit breaker."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not _circuit_breaker.allow_request(circuit_name):
                return JsonResponse({
                    "erro": f"Serviço '{circuit_name}' temporariamente indisponível (circuit open)",
                    "retry_after_segundos": _circuit_breaker.timeout,
                }, status=503)
            try:
                response = view_func(request, *args, **kwargs)
                if response.status_code < 500:
                    _circuit_breaker.record_success(circuit_name)
                else:
                    _circuit_breaker.record_failure(circuit_name)
                return response
            except Exception as e:
                _circuit_breaker.record_failure(circuit_name)
                raise
        return wrapper
    return decorator


def v2_envelope(view_func):
    """Decorator: envolve resposta JSON em envelope v2 { data, meta, version }."""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        import json as _json
        t0 = time.monotonic()
        response = view_func(request, *args, **kwargs)
        if not getattr(response, "content_type", "").startswith("application/json"):
            return response
        if response.status_code >= 400:
            return response
        try:
            data = _json.loads(response.content)
        except Exception:
            return response
        elapsed = round((time.monotonic() - t0) * 1000, 1)
        envelope = {
            "version": "2.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "latencia_ms": elapsed,
            "data": data,
        }
        return JsonResponse(envelope, status=response.status_code)
    return wrapper


# ─── Endpoints de status ──────────────────────────────────────────────────────

def api_circuit_breaker_status(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    return JsonResponse({
        "circuitos": _circuit_breaker.status_all(),
        "threshold": _circuit_breaker.threshold,
        "timeout_segundos": _circuit_breaker.timeout,
    })


def api_rate_limit_status(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)
    plano = empresa.pacote_codigo or "default"
    limit, window = _rate_limiter._limits.get(plano, _rate_limiter._limits["default"])
    key = f"empresa:{empresa.id}"
    dq = _rate_limiter._windows.get(key, [])
    now = time.monotonic()
    recentes = [t for t in dq if now - t < window]
    return JsonResponse({
        "empresa": empresa.nome,
        "plano": plano,
        "limite": limit,
        "janela_segundos": window,
        "usadas_janela": len(recentes),
        "restantes": max(0, limit - len(recentes)),
    })
