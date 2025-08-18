import logging

import structlog
from .settings import settings
try:
    from .main import redact_pii
except Exception:  # pragma: no cover
    def redact_pii(v: str) -> str:
        return v


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))
    def _pii_redactor(logger, method_name, event_dict):
        if settings.pii_redaction_enabled:
            for k, v in list(event_dict.items()):
                if isinstance(v, str):
                    event_dict[k] = redact_pii(v)
        return event_dict

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="ISO"),
            _pii_redactor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
