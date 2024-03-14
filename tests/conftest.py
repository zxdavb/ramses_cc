"""Fixtures for testing."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: pytest.fixture):  # type: ignore[no-untyped-def]
    yield


@pytest.fixture(autouse=True)
def patches_for_tests(monkeypatch: pytest.MonkeyPatch):
    try:
        # refactored protocol / transport modules
        monkeypatch.setattr(
            "ramses_tx.protocol._DBG_DISABLE_IMPERSONATION_ALERTS", True
        )
        monkeypatch.setattr("ramses_tx.transport._DBG_DISABLE_DUTY_CYCLE_LIMIT", True)
        monkeypatch.setattr("ramses_tx.transport._GAP_BETWEEN_WRITES", 0)
    except AttributeError:
        # original protocol / transport modules
        monkeypatch.setattr(
            "ramses_tx.protocol._DBG_DISABLE_IMPERSONATION_ALERTS", True
        )
        monkeypatch.setattr("ramses_tx.protocol._DBG_DISABLE_DUTY_CYCLE_LIMIT", True)
        monkeypatch.setattr("ramses_tx.protocol._GAP_BETWEEN_WRITES", 0)
