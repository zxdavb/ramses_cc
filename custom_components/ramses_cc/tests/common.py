"""Common methods used across all RAMSES II tests."""

# from unittest.mock import patch
from custom_components.ramses_cc import DOMAIN as RAMSES_DOMAIN
from tests.common import MockConfigEntry  # type: ignore[import-untyped]

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


async def setup_platform(hass: HomeAssistant, platform: str) -> MockConfigEntry:
    """Set up the RAMSES_CC platform."""

    mock_entry = MockConfigEntry(
        domain=RAMSES_DOMAIN,
        data={
            "serial_port": "/dev/ttyMOCK",
        },
    )
    mock_entry.add_to_hass(hass)

    # with patch("homeassistant.components.abode.PLATFORMS", [platform]), patch(
    #     "xxxxxx.abode.event_controller.sio"
    # ):
    assert await async_setup_component(hass, RAMSES_DOMAIN, {})

    await hass.async_block_till_done()

    return mock_entry
