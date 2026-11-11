import logging
import os

logging.disable(logging.CRITICAL)

import structlog

structlog.configure(
    processors=[structlog.dev.ConsoleRenderer()],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(file=open(os.devnull, "w")),
)

from gamdl.api.apple_music import AppleMusicApi  # noqa: E402

COOKIES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "gamdl", "cookies.txt")


def format_artwork(url_template: str, size: int = 200) -> str:
    return url_template.replace("{w}", str(size)).replace("{h}", str(size))
