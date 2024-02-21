"""Test the setup."""

import asyncio
from collections.abc import AsyncGenerator

from custom_components.ramses_cc import DOMAIN, RamsesBroker
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from tests.virtual_rf import VirtualRf

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

    # mocked to cut out serial/MQTT
    # th patch("custom_components.ramses_cc.RamsesBroker", return_value=AsyncMock()):
    # with patch.object(RamsesBroker, "_create_client", return_value=23):
    result = await hass.config_entries.async_setup(entry.entry_id)
    assert result  # False if SETUP_ERROR

    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED  # or: SETUP_ERROR

    # assert len(hass.states.async_entity_ids(SENSOR_DOMAIN)) == 1

    assert hass.data["setup_tasks"] == {}
    assert isinstance(hass.data[DOMAIN][entry.entry_id], RamsesBroker)

    assert isinstance(hass.data[DOMAIN][entry.entry_id], RamsesBroker)

    await hass.async_block_till_done()  # TODO: not quiescing (why?)...
    await asyncio.sleep(5)  # #           TODO: workaround

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    # hass.stop()  # not needed?
    # await hass.async_block_till_done()

    await rf.stop()


async def test_setup_import(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test setup of ramses_cc via config file."""

    rf = VirtualRf(1)  # TODO: fixture is not working!
    rf.set_gateway(rf.ports[0], "18:000730")  # , fw_type=HgiFwTypes.HGI_80)

    config = {"serial_port": rf.ports[0]}

    # mocked to cut out serial/MQTT
    # with patch("ramses_rf.gateway.is_hgi80", return_value=None):
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})  # True

    # Setup failed for 'ramses_cc': Integration not found.
    # assert hass.data["setup_tasks"][DOMAIN].done()
    # assert hass.data["setup_tasks"][DOMAIN].result() is True
    # hass.data["persistent_notification"]["invalid_config"]["message"]

    # custom_components.ramses_cc.broker:broker.py:75 Config = {'ramses_rf': {}, 'serial_port': {'port_name': '/dev/ttyACM0'}, 'schema': {}}
    # custom_components.ramses_cc.broker:broker.py:99 Storage = {}
    # homeassistant.config_entries:config_entries.py:485 Config entry 'RAMSES RF' for ramses_cc integration not ready yet:
    #   There is a problem with the serial port: Unable to find /dev/ttyACM0; Retrying in 10 seconds

    # await hass.async_block_till_done()  # not needed?
    # if not hass.data[DOMAIN]:  # in ramses_cc.async_setup_entry()
    #     pass  # something went wrong

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1

    entry = entries[0]
    assert isinstance(hass.data[DOMAIN][entry.entry_id], RamsesBroker)

    await hass.async_block_till_done()  # TODO: not quiescing (why?)...
    await asyncio.sleep(5)  # #           TODO: workaround

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    # hass.stop()  # not needed?
    # await hass.async_block_till_done()

    await rf.stop()
