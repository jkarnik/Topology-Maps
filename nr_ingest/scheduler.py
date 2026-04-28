import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

PUSH_INTERVAL = 300  # seconds


def _validate_env() -> None:
    missing = [v for v in ("NR_LICENSE_KEY", "NR_ACCOUNT_ID") if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def run_once() -> int:
    import push_all_devices
    return push_all_devices.main()


def main() -> None:
    _validate_env()
    log.info("NR ingest scheduler starting — push interval %ds", PUSH_INTERVAL)
    while True:
        log.info("Starting device push...")
        try:
            rc = run_once()
            if rc == 0:
                log.info("Push complete.")
            else:
                log.error("Push failed (exit code %d) — retrying in %ds", rc, PUSH_INTERVAL)
        except Exception as exc:
            log.error("Push raised exception: %s — retrying in %ds", exc, PUSH_INTERVAL)
        log.info("Sleeping %ds until next push...", PUSH_INTERVAL)
        time.sleep(PUSH_INTERVAL)


if __name__ == "__main__":
    main()
