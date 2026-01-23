"""Structured JSON logging configuration for Cloud Logging compatibility."""

import json
import logging
import sys
from datetime import datetime
from typing import Any

from app.settings import settings


class ContextFilter(logging.Filter):
    """Filter that adds request and tenant context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add context variables to the log record."""
        # Import here to avoid circular imports
        from app.core.tenant_context import get_tenant_context

        # Try to get request_id from middleware context
        try:
            from app.api.middleware import get_current_request_id
            record.request_id = get_current_request_id() or ""
        except Exception:
            record.request_id = ""

        # Get tenant_id from tenant context
        try:
            record.tenant_id = get_tenant_context() or ""
        except Exception:
            record.tenant_id = ""

        return True


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add context fields (populated by ContextFilter)
        if hasattr(record, "request_id") and record.request_id:
            log_data["request_id"] = record.request_id
        if hasattr(record, "tenant_id") and record.tenant_id:
            log_data["tenant_id"] = record.tenant_id
        if hasattr(record, "user_id") and record.user_id:
            log_data["user_id"] = record.user_id

        # Add any extra fields passed via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in log_data and not key.startswith("_") and key not in (
                "name", "msg", "args", "created", "filename", "funcName", "levelname",
                "levelno", "lineno", "module", "msecs", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "exc_info", "exc_text",
                "thread", "threadName", "request_id", "tenant_id", "user_id", "message"
            ):
                log_data[key] = value

        return json.dumps(log_data)


def setup_logging() -> None:
    """Configure application logging."""
    # Get log level from settings
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create console handler with JSON formatter and context filter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(JSONFormatter())
    console_handler.addFilter(ContextFilter())  # Add context (request_id, tenant_id)

    root_logger.addHandler(console_handler)

    # Set levels for third-party loggers
    # Note: In production, consider enabling uvicorn.access for HTTP traffic visibility
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO if settings.environment == "production" else logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name."""
    return logging.getLogger(name)

