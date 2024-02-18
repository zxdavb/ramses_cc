"""Test the setup."""

from custom_components.ramses_cc import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

CONFIG = {
    "serial_port": "/dev/ttyACM0",
}


async def test_setup_entry(hass: HomeAssistant) -> None:
    """Test setup of ramses via config entry."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=CONFIG,
    )
    entry.add_to_hass(hass)

    # mocked to cut out serial/MQTT
    # with patch("custom_components.ramses_cc") as mocked_cc:

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    assert entries[0] is entry

    # assert len(hass.states.async_entity_ids(SENSOR_DOMAIN)) == 1

    pass


async def test_setup_import(hass: HomeAssistant) -> None:
    """Test setup of ramses via config file."""

    # mocked to cut out serial/MQTT
    # with patch("custom_components.ramses_cc") as mocked_cc:

    assert await async_setup_component(hass, DOMAIN, {DOMAIN: CONFIG})
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    assert hass.data[DOMAIN] == {}

    pass
