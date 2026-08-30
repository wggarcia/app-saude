"""
Logging estruturado (JSON) para produção — sem dependência externa.

Emite uma linha JSON por evento, pronta para agregadores (Render logs, Loki,
Datadog...). Inclui timestamp ISO, nível, logger, mensagem e stack de exceção.
Campos extras passados via `logger.info(msg, extra={...})` são incorporados.
"""
import json
import logging


_RESERVADOS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message", "asctime", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record):
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Campos extras (extra={...}) que não sejam atributos padrão do LogRecord
        for k, v in record.__dict__.items():
            if k not in _RESERVADOS and not k.startswith("_"):
                try:
                    json.dumps(v)
                    base[k] = v
                except (TypeError, ValueError):
                    base[k] = str(v)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False, default=str)
