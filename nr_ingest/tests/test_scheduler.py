import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import scheduler


def test_validate_env_missing_both(monkeypatch):
    monkeypatch.delenv("NR_LICENSE_KEY", raising=False)
    monkeypatch.delenv("NR_ACCOUNT_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        scheduler._validate_env()
    assert exc.value.code == 1


def test_validate_env_missing_one(monkeypatch):
    monkeypatch.setenv("NR_LICENSE_KEY", "test-key")
    monkeypatch.delenv("NR_ACCOUNT_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        scheduler._validate_env()
    assert exc.value.code == 1


def test_validate_env_ok(monkeypatch):
    monkeypatch.setenv("NR_LICENSE_KEY", "test-key")
    monkeypatch.setenv("NR_ACCOUNT_ID", "12345")
    scheduler._validate_env()  # must not raise or exit


def test_run_once_success(monkeypatch):
    mock_module = MagicMock()
    mock_module.main.return_value = 0
    monkeypatch.setitem(sys.modules, "push_all_devices", mock_module)
    rc = scheduler.run_once()
    assert rc == 0
    mock_module.main.assert_called_once()


def test_run_once_failure(monkeypatch):
    mock_module = MagicMock()
    mock_module.main.return_value = 1
    monkeypatch.setitem(sys.modules, "push_all_devices", mock_module)
    rc = scheduler.run_once()
    assert rc == 1
