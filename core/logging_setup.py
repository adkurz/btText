"""Configure bounded UTF-8 application logging for btText."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOGGER_NAME = "bttext"
LOG_MAX_BYTES = 1_048_576
LOG_BACKUP_COUNT = 3
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(log_file: str | Path) -> logging.Logger:
    """Configure and return the application logger for one writable file."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for handler in tuple(logger.handlers):
        if getattr(handler, "_bttext_file_handler", False):
            logger.removeHandler(handler)
            handler.close()

    handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler._bttext_file_handler = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    return logger
