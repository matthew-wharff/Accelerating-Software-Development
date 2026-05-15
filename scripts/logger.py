import logging
from pathlib import Path

from scripts.redaction import redact_string

LOG_FILE = Path(__file__).parent / "logs" / "pipeline.log"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class _RedactionFilter(logging.Filter):
    """Mutate ``LogRecord.msg`` through ``redact_string`` before emit.

    Installed on the logger (not on each handler) so a single pass is
    applied regardless of how many handlers are attached. The filter
    interpolates ``record.args`` into ``record.msg`` via
    ``record.getMessage()``, runs the result through the redaction
    patterns, and assigns the redacted text back. ``record.args`` is
    cleared so the formatter does not try to re-interpolate.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the message in place; always returns ``True``.

        Args:
            record: The log record being emitted.

        Returns:
            Always ``True`` so the record is never dropped.
        """
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = redact_string(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        if record.exc_text:
            record.exc_text = redact_string(record.exc_text)
        return True


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Return a logger with a StreamHandler and a FileHandler.

    Both handlers share the same formatter. The file handler appends to
    logs/pipeline.log; the stream handler writes to stdout. A redaction
    filter is attached to the logger itself so credential-shaped
    substrings are masked before either handler formats the record.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.addFilter(_RedactionFilter())

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FMT)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

    return logger
