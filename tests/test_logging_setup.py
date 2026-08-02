import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.logging_setup import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    LOGGER_NAME,
    configure_logging,
)


class LoggingSetupTestCase(unittest.TestCase):
    def _close_handlers(self):
        logger = logging.getLogger(LOGGER_NAME)
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def tearDown(self):
        self._close_handlers()

    def test_configures_bounded_utf8_file_logging(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_file = Path(temporary_directory) / "logs" / "btText.log"

            try:
                logger = configure_logging(log_file)
                logger.error("diagnostic message")

                handlers = [
                    handler
                    for handler in logger.handlers
                    if isinstance(handler, RotatingFileHandler)
                ]
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0].maxBytes, LOG_MAX_BYTES)
                self.assertEqual(handlers[0].backupCount, LOG_BACKUP_COUNT)
                self.assertIn(
                    "diagnostic message",
                    log_file.read_text(encoding="utf-8"),
                )
            finally:
                self._close_handlers()

    def test_reconfiguration_replaces_the_previous_file_handler(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)

            try:
                logger = configure_logging(directory / "first.log")
                configure_logging(directory / "second.log")

                self.assertEqual(len(logger.handlers), 1)
            finally:
                self._close_handlers()
