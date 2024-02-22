"""Test the setup."""

from typing import Final
from unittest.mock import patch

from custom_components.ramses_cc import DOMAIN, RamsesBroker
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from tests.virtual_rf import VirtualRf

# patched constants
_CALL_LATER_DELAY: Final = 0  # from: custom_components.ramses_cc.broker.py


async def _test_setup_common(hass: HomeAssistant, entry: ConfigEntry = None) -> None:
    try:
        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1

        assert entry is None or entry is entries[0]

        entry = entries[0]
        assert entry.state is ConfigEntryState.LOADED

        assert hass.data["setup_tasks"] == {}
        assert isinstance(hass.data[DOMAIN][entry.entry_id], RamsesBroker)

        broker: RamsesBroker = hass.data[DOMAIN][entry.entry_id]
        assert len(broker._devices) == 1  # 18_000730

        assert (
            len(hass.states.async_entity_ids(Platform.BINARY_SENSOR)) == 1
        )  # binary_sensor.18_000730_status

        assert len(hass.services.async_services_for_domain(DOMAIN)) == 6

    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert await hass.config_entries.async_remove(entry.entry_id)


async def _test_setup_entry(hass: HomeAssistant, rf: VirtualRf) -> None:
    config = {"serial_port": {"port_name": rf.ports[0]}}

    entry = MockConfigEntry(domain=DOMAIN, options=config)
    entry.add_to_hass(hass)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    # mocked to avoid: Lingering timer after job <Job call_later 5...
    with patch(
        "custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        # await hass.async_block_till_done()

    await _test_setup_common(hass, entry=entry)


async def _test_setup_import(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test setup of ramses_cc via importing a configuration."""

    config = {"serial_port": {"port_name": rf.ports[0]}}

    # mocked to avoid: Lingering timer after job <Job call_later 5...
    with patch(
        "custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY
    ):
        assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})  # True
        # await hass.async_block_till_done()

    await _test_setup_common(hass)


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test setup of ramses_cc via config entry."""

    rf = VirtualRf(1)
    rf.set_gateway(rf.ports[0], "18:000730")  # , fw_type=HgiFwTypes.HGI_80)

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0

    try:
        await _test_setup_entry(hass, rf)

    finally:
        # hass.stop()  # not needed?
        # await hass.async_block_till_done()

        await rf.stop()  # prevent: Lingering task: VirtualRfBase._poll_ports_for_data()


async def test_setup_import(hass: HomeAssistant) -> None:
    """Test setup of ramses_cc via importing a configuration."""

    rf = VirtualRf(1)
    rf.set_gateway(rf.ports[0], "18:000730")  # , fw_type=HgiFwTypes.HGI_80)

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0

    try:
        await _test_setup_import(hass, rf)

    finally:
        # hass.stop()  # not needed?
        # await hass.async_block_till_done()

        await rf.stop()  # prevent: Lingering task: VirtualRfBase._poll_ports_for_data()
