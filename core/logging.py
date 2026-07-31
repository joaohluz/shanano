import logging
from typing import Optional

import structlog


def setup_logging(service_name: str = "shanano") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if logging.root.handlers
            and any(
                isinstance(h, logging.StreamHandler)
                for h in logging.root.handlers
            )
            else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        force=True,
    )


def get_logger(name: Optional[str] = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
