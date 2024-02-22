"""Test the setup."""

from collections.abc import AsyncGenerator
from typing import Final
from unittest.mock import patch

from custom_components.ramses_cc import DOMAIN, RamsesBroker
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from tests.virtual_rf import VirtualRf

# patched constants
_CALL_LATER_DELAY: Final = 0  # from: custom_components.ramses_cc.broker.py

CONFIG = {
    "serial_port": "/dev/ttyACM0",
}


@pytest.fixture(scope="module")
async def rf() -> AsyncGenerator[VirtualRf, None]:
    """Utilize a virtual serial port."""

    rf = VirtualRf(1)
    rf.set_gateway(rf.ports[0], "18:000730")  # , fw_type=HgiFwTypes.HGI_80)

    try:
        yield rf
    finally:
        await rf.stop()


async def test_setup_entry(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test setup of ramses_cc via config entry."""

    rf = VirtualRf(1)  # TODO: fixture is not working!
    rf.set_gateway(rf.ports[0], "18:000730")  # , fw_type=HgiFwTypes.HGI_80)
    config = {"serial_port": {"port_name": rf.ports[0]}}

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0

    entry = MockConfigEntry(
        domain=DOMAIN,
        # data={DOMAIN: config},
        options=config,
    )
    entry.add_to_hass(hass)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    # mocked to avoid: Lingering timer after job <Job call_later 5...
    with patch(
        "custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        # await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    assert entry is entries[0]
    assert entry.state is ConfigEntryState.LOADED

    assert hass.data["setup_tasks"] == {}
    assert isinstance(hass.data[DOMAIN][entry.entry_id], RamsesBroker)

    # assert len(hass.states.async_entity_ids(SENSOR_DOMAIN)) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_remove(entry.entry_id)

    # hass.stop()  # not needed?
    # await hass.async_block_till_done()

    await rf.stop()


async def test_setup_import(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test setup of ramses_cc via importing a configuration."""

    rf = VirtualRf(1)  # TODO: fixture is not working!
    rf.set_gateway(rf.ports[0], "18:000730")  # , fw_type=HgiFwTypes.HGI_80)
    config = {"serial_port": {"port_name": rf.ports[0]}}

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0

    # mocked to avoid: Lingering timer after job <Job call_later 5...
    with patch(
        "custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY
    ):
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})  # True
        # await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    entry = entries[0]
    assert entry.state is ConfigEntryState.LOADED

    assert hass.data["setup_tasks"] == {}
    assert isinstance(hass.data[DOMAIN][entry.entry_id], RamsesBroker)

    # assert len(hass.states.async_entity_ids(SENSOR_DOMAIN)) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_remove(entry.entry_id)

    # hass.stop()  # not needed?
    # await hass.async_block_till_done()

    await rf.stop()
