"""Fixtures and helpers for the ramses_cc tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: pytest.fixture):  # type: ignore[no-untyped-def]
    yield


@pytest.fixture(autouse=True)
def patches_for_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    # try:
    monkeypatch.setattr("ramses_tx.protocol._DBG_DISABLE_IMPERSONATION_ALERTS", True)
    # nkeypatch.setattr("ramses_tx.protocol._DBG_DISABLE_QOS", True)
    # nkeypatch.setattr("ramses_tx.protocol._DBG_FORCE_LOG_PACKETS", True)
    monkeypatch.setattr("ramses_tx.transport._DBG_DISABLE_DUTY_CYCLE_LIMIT", True)
    monkeypatch.setattr("ramses_tx.transport._DBG_DISABLE_REGEX_WARNINGS", True)
    # nkeypatch.setattr("ramses_tx.transport._DBG_FORCE_FRAME_LOGGING", True)
    monkeypatch.setattr("ramses_tx.transport.MIN_INTER_WRITE_GAP", 0)

    # except AttributeError:
    #     monkeypatch.setattr("ramses_tx.protocol._GAP_BETWEEN_WRITES", 0)
