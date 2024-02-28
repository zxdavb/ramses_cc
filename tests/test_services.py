"""Test the setup."""

from typing import Any, Final
from unittest.mock import patch

from custom_components.ramses_cc import (
    DOMAIN,
    SCH_BIND_DEVICE,
    SCH_SEND_PACKET,
    SVC_BIND_DEVICE,
    SVC_FORCE_UPDATE,
    SVC_SEND_PACKET,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ramses_rf.gateway import Gateway

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from tests.virtual_rf import VirtualRf

from .common import TEST_DIR, cast_packets_to_rf

# patched constants
_CALL_LATER_DELAY: Final = 0  # from: custom_components.ramses_cc.broker.py


TEST_CONFIG = {
    "serial_port": {"port_name": None},
    "ramses_rf": {"disable_discovery": True},
    "advanced_features": {"send_packet": True},
}


SERVICES = {
    SVC_BIND_DEVICE: (
        "custom_components.ramses_cc.broker.RamsesBroker.async_bind_device",
        SCH_BIND_DEVICE,
    ),
    SVC_FORCE_UPDATE: (
        "custom_components.ramses_cc.broker.RamsesBroker.async_force_update",
        dict,  # data is '{}'
    ),
    SVC_SEND_PACKET: (
        "custom_components.ramses_cc.broker.RamsesBroker.async_send_packet",
        SCH_SEND_PACKET,
    ),
}

SZ_SERVICE: Final = "service"
SZ_SERVICE_DATA: Final = "service_data"


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


async def _setup_testbed_heat(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Load packets from a CH/DHW system."""

    gwy: Gateway = list(hass.data[DOMAIN].values())[0].client
    assert len(gwy.devices) == 1

    await cast_packets_to_rf(rf, f"{TEST_DIR}/system_1.log", gwy=gwy)
    assert len(gwy.devices) == 9  # proxy for success of above

    assert len(hass.services.async_services_for_domain(DOMAIN)) == 7


async def _setup_testbed_via_entry_(
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
    await _setup_testbed_heat(hass, rf)
    return entry


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def _test_service_call(
    hass: HomeAssistant, rf: VirtualRf, service: str, data: dict[str, Any]
) -> None:
    """Test a service call."""

    entry: ConfigEntry = await _setup_testbed_via_entry_(hass, rf, TEST_CONFIG)

    with patch(SERVICES[service][0]) as mock_method:
        _ = await hass.services.async_call(
            DOMAIN, service=service, service_data=data, blocking=True
        )
        try:
            mock_method.assert_called_once()
            service_call: ServiceCall = mock_method.call_args[0][0]

            assert service_call.data == SERVICES[service][1](data)

        finally:
            await hass.config_entries.async_unload(entry.entry_id)


async def test_svc_bind_device(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the service call."""

    data = {
        "device_id": "22:140285",
        "offer": {"30C9": "00"},
    }

    await _test_service_call(hass, rf, SVC_BIND_DEVICE, data)


async def test_svc_force_update(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the service call."""

    data = {}

    await _test_service_call(hass, rf, SVC_FORCE_UPDATE, data)


async def test_svc_send_packet(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the service call."""

    data = {
        "device_id": "18:000730",
        "verb": " I",
        "code": "1FC9",
        "payload": "00",
    }

    await _test_service_call(hass, rf, SVC_SEND_PACKET, data)


async def test_put_co2_level(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def test_put_dhw_temp(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def test_put_indoor_humidity(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def test_put_room_temp(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass
