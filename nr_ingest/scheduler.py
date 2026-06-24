import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

PUSH_INTERVAL = 60   # seconds between pushes — keeps entities inside NR's map-freshness window
RETRY_INTERVAL = 10  # seconds to wait before retrying after a failed push (fast retry, not a full cycle)
REL_REASSERT_EVERY = 60  # re-assert relationships every N successful pushes (~hourly at 60s)

# New Relic background-task instrumentation. The agent is started by
# `newrelic-admin run-program` in the container; locally (and in tests)
# the package is absent, so fall back to a no-op decorator.
try:
    import newrelic.agent

    background_task = newrelic.agent.background_task
except ImportError:  # pragma: no cover - exercised only in the container
    def background_task(*args, **kwargs):
        def _decorator(func):
            return func

        return _decorator


def _validate_env() -> None:
    missing = [v for v in ("NR_LICENSE_KEY", "NR_ACCOUNT_ID") if not os.environ.get(v)]
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


@background_task()
def run_once() -> int:
    import push_all_devices
    return push_all_devices.main()


@background_task()
def run_relationships() -> int:
    import create_relationships
    return create_relationships.main()


def main() -> None:
    _validate_env()
    rel_enabled = bool(os.environ.get("NR_USER_API_KEY"))
    log.info(
        "NR ingest scheduler starting — push interval %ds, relationship re-assert %s",
        PUSH_INTERVAL,
        f"every {REL_REASSERT_EVERY} pushes" if rel_enabled
        else "DISABLED (NR_USER_API_KEY not set)",
    )
    pushes_since_rel = 0
    while True:
        log.info("Starting device push...")
        try:
            rc = run_once()
        except Exception as exc:
            log.error("Push raised exception: %s — retrying in %ds", exc, RETRY_INTERVAL)
            time.sleep(RETRY_INTERVAL)
            continue
        if rc != 0:
            log.error("Push failed (exit code %d) — retrying in %ds", rc, RETRY_INTERVAL)
            time.sleep(RETRY_INTERVAL)
            continue

        log.info("Push complete.")
        pushes_since_rel += 1

        # Periodically re-assert user-defined relationships so the Workload map
        # self-heals if an entity ever expired and dropped its edges.
        if rel_enabled and pushes_since_rel >= REL_REASSERT_EVERY:
            log.info("Re-asserting entity relationships...")
            try:
                rrc = run_relationships()
                if rrc == 0:
                    log.info("Relationship re-assert complete.")
                else:
                    log.error("Relationship re-assert failed (exit code %s).", rrc)
            except Exception as exc:
                log.error("Relationship re-assert raised exception: %s", exc)
            pushes_since_rel = 0

        log.info("Sleeping %ds until next push...", PUSH_INTERVAL)
        time.sleep(PUSH_INTERVAL)


if __name__ == "__main__":
    main()
