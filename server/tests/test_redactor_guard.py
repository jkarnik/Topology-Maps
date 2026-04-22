"""Regex-guard tests: fail the build if any secret-looking field escapes redaction.

Scans every recorded Meraki response fixture, runs it through the redactor
for its corresponding config_area, and walks the redacted payload for any
key whose name suggests a secret but whose value is not a sentinel.

This is the fail-safe that keeps the redaction catalog current as Meraki
evolves its API.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from server.config_collector.redactor import redact, SENTINEL_KEY

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "meraki"

# Maps fixture filename → config_area used in the redaction catalog
FIXTURE_AREA_MAP = {
    "wireless_ssids_sample.json": "wireless_ssids",
    "appliance_site_to_site_vpn_sample.json": "appliance_site_to_site_vpn",
    "network_snmp_sample.json": "network_snmp",
}

SECRET_KEY_PATTERN = re.compile(
    r"(?i)(psk|passphrase|password|secret|shared[-_]?key|community[-_]?string|token|api[-_]?key)"
)


def _walk(node, path=""):
    """Yield (path, key, value) for every key-value pair in nested structures."""
    if isinstance(node, dict):
        # If node itself is a redacted sentinel, skip — it is by definition masked
        if node.get(SENTINEL_KEY) is True:
            return
        for k, v in node.items():
            yield (path, k, v)
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _walk(item, f"{path}[{i}]")


@pytest.mark.parametrize("fixture_name,config_area", sorted(FIXTURE_AREA_MAP.items()))
def test_no_secret_field_escapes_redaction(fixture_name, config_area):
    """No field matching SECRET_KEY_PATTERN may have a non-null, non-sentinel value."""
    raw = json.loads((FIXTURES_DIR / fixture_name).read_text())
    redacted_str, _, _, _ = redact(raw, config_area)
    redacted = json.loads(redacted_str)

    violations: list[str] = []
    for parent_path, key, value in _walk(redacted):
        if not SECRET_KEY_PATTERN.search(key):
            continue
        if value is None or value == "":
            continue
        if isinstance(value, dict) and value.get(SENTINEL_KEY) is True:
            continue
        violations.append(f"{parent_path}.{key} = {value!r}")

    assert not violations, (
        f"Secret-looking fields escaped redaction in {fixture_name} "
        f"(config_area={config_area}):\n  " + "\n  ".join(violations) +
        "\n\nFix: add the missing path to REDACTION_PATHS in server/config_collector/redaction_catalog.py"
    )
