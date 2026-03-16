"""Structured logger is the audit-log analogue: emits JSON-formatted log records for all KubeAI control-plane operations."""

import logging
import json
import time
import sys


class _JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # merge any extra kwargs passed via extra={}
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    """Configure root KubeAI logger with JSON handler on stderr."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    logger = logging.getLogger("kubeai")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the kubeai namespace."""
    return logging.getLogger(f"kubeai.{name}")
