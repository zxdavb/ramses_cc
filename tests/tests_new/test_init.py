"""Tests for the ramses_cc tests."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from syrupy import SnapshotAssertion

from custom_components.ramses_cc import DOMAIN

from ..virtual_rf import VirtualRf
from .common import configuration_fixture, storage_fixture
from .const import TEST_SYSTEMS


@pytest.mark.parametrize("instance", TEST_SYSTEMS)
async def test_entities(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    instance: str,
    rf: VirtualRf,
    snapshot: SnapshotAssertion,
) -> None:
    """Test State after setup of an instance of the integration."""

    hass_storage[DOMAIN] = storage_fixture(instance)

    config = configuration_fixture(instance)
    config[DOMAIN]["serial_port"] = rf.ports[0]

    assert await async_setup_component(hass, DOMAIN, config)
    await hass.async_block_till_done()

    try:
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        assert entry.state == ConfigEntryState.LOADED

        assert hass.states.async_all(domain_filter=DOMAIN) == snapshot

    finally:  # Prevent non-useful errors in teardown
        assert await hass.config_entries.async_unload(entry.entry_id)
