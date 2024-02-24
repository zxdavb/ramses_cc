"""Test the setup of ramses_cc with data (vanilla configuration)."""

from typing import Any, Final
from unittest.mock import patch

from custom_components.ramses_cc import DOMAIN
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ramses_rf.gateway import Gateway

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from tests.virtual_rf import VirtualRf

from .common import TEST_DIR, cast_packets_to_rf

# patched constants
_CALL_LATER_DELAY: Final = 0  # from: custom_components.ramses_cc.broker.py


TEST_CONFIG = {
    "serial_port": {"port_name": None},
    "ramses_rf": {"disable_discovery": True},
}


@pytest.fixture()  # add hass fixture to ensure hass/rf use same event loop
async def rf(hass: HomeAssistant):
    """Utilize a virtual evofw3-compatible gateway."""

    rf = VirtualRf(2)
    rf.set_gateway(rf.ports[0], "18:000730")

    with patch("ramses_tx.transport.comports", rf.comports):
        try:
            yield rf
        finally:
            await rf.stop()


async def _test_common(hass: HomeAssistant, entry: ConfigEntry, rf: VirtualRf) -> None:
    """The main tests are here."""

    gwy: Gateway = list(hass.data[DOMAIN].values())[0].client
    assert len(gwy.devices) == 1

    await cast_packets_to_rf(rf, f"{TEST_DIR}/system_1.log", gwy=gwy)
    assert len(gwy.devices) == 9

    assert len(hass.services.async_services_for_domain(DOMAIN)) == 6


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def test_services_entry_(
    hass: HomeAssistant, rf: VirtualRf, config: dict[str:Any] = TEST_CONFIG
) -> None:
    """Test ramses_cc via config entry."""

    config["serial_port"]["port_name"] = rf.ports[0]

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0
    entry = MockConfigEntry(domain=DOMAIN, options=config)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    # await hass.async_block_till_done()  # ?clear hass._tasks

    #
    try:
        await _test_common(hass, entry, rf)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def test_services_import(
    hass: HomeAssistant, rf: VirtualRf, config: dict[str:Any] = TEST_CONFIG
) -> None:
    """Test ramses_cc via importing a configuration."""

    config["serial_port"]["port_name"] = rf.ports[0]

    #
    #
    #

    assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})
    # await hass.async_block_till_done()  # ?clear hass._tasks

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    try:
        await _test_common(hass, entry, rf)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
