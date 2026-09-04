import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import structlog

from app.config import settings
from app.observability import setup_logging
from app.outbox.dispatcher import dispatch_outbox_events


setup_logging()
logger = structlog.get_logger()


def main():
    logger.info(
        "outbox_dispatcher_started",
        batch_size=settings.outbox_dispatch_batch_size,
        interval_seconds=settings.outbox_dispatch_interval_seconds,
    )

    while True:
        try:
            dispatched = dispatch_outbox_events()

            if dispatched > 0:
                logger.info(
                    "outbox_dispatch_batch_complete",
                    dispatched=dispatched,
                )
                continue

            time.sleep(settings.outbox_dispatch_interval_seconds)

        except KeyboardInterrupt:
            logger.info("outbox_dispatcher_stopped_by_user")
            break

        except Exception:
            logger.exception("outbox_dispatcher_error")
            time.sleep(settings.outbox_dispatch_interval_seconds)


if __name__ == "__main__":
    main()
