"""Test the setup."""

from collections.abc import AsyncGenerator
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
from custom_components.ramses_cc.broker import RamsesBroker
from custom_components.ramses_cc.schemas import (
    SCH_PUT_CO2_LEVEL,
    SCH_PUT_DHW_TEMP,
    SCH_PUT_INDOOR_HUMIDITY,
    SCH_PUT_ROOM_TEMP,
    SCH_SET_SYSTEM_MODE,
    SVC_PUT_CO2_LEVEL,
    SVC_PUT_DHW_TEMP,
    SVC_PUT_INDOOR_HUMIDITY,
    SVC_PUT_ROOM_TEMP,
    SVC_RESET_SYSTEM_MODE,
    SVC_SET_SYSTEM_MODE,
)
import pytest
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)
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
        dict,  # data is like {"entity_id": "climate.01_145038}
    ),
    SVC_PUT_CO2_LEVEL: (
        "custom_components.ramses_cc.sensor.RamsesSensor.async_put_co2_level",
        SCH_PUT_CO2_LEVEL,
    ),
    SVC_PUT_DHW_TEMP: (
        "custom_components.ramses_cc.sensor.RamsesSensor.async_put_dhw_temp",
        SCH_PUT_DHW_TEMP,
    ),
    SVC_PUT_INDOOR_HUMIDITY: (
        "custom_components.ramses_cc.sensor.RamsesSensor.async_put_indoor_humidity",
        SCH_PUT_INDOOR_HUMIDITY,
    ),
    SVC_PUT_ROOM_TEMP: (
        "custom_components.ramses_cc.sensor.RamsesSensor.async_put_room_temp",
        SCH_PUT_ROOM_TEMP,
    ),
    SVC_SEND_PACKET: (
        "custom_components.ramses_cc.broker.RamsesBroker.async_send_packet",
        SCH_SEND_PACKET,
    ),
    SVC_RESET_SYSTEM_MODE: (
        "custom_components.ramses_cc.climate.RamsesController.async_reset_system_mode",
        dict,  # data is like {"entity_id": "climate.01_145038}
    ),
    SVC_SET_SYSTEM_MODE: (
        "custom_components.ramses_cc.climate.RamsesController.async_set_system_mode",
        SCH_SET_SYSTEM_MODE,
    ),
}


@pytest.fixture()  # add hass fixture to ensure hass/rf use same event loop
async def rf(hass: HomeAssistant) -> AsyncGenerator[Any, None]:
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
    assert len(gwy.devices) == 1  # the HGI status sensor

    await cast_packets_to_rf(rf, f"{TEST_DIR}/system_1.log", gwy=gwy)
    assert len(gwy.devices) == 11  # proxy for success of above

    assert len(hass.services.async_services_for_domain(DOMAIN)) == 7


async def _setup_testbed_via_entry_(
    hass: HomeAssistant, rf: VirtualRf, config: dict[str, Any] = TEST_CONFIG
) -> ConfigEntry:
    """Test ramses_cc via config entry."""

    config["serial_port"]["port_name"] = rf.ports[0]

    assert len(hass.config_entries.async_entries(DOMAIN)) == 0
    entry = MockConfigEntry(domain=DOMAIN, options=config)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    # await hass.async_block_till_done()  # ?clear hass._tasks

    #
    await _setup_testbed_heat(hass, rf)

    broker: RamsesBroker = list(hass.data[DOMAIN].values())[0]

    await broker.async_update()
    await hass.async_block_till_done()
    assert len(broker._entities) == 36  # proxy for success of above (HA entities)

    return entry


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def _test_entity_service_call(
    hass: HomeAssistant, rf: VirtualRf, service: str, data: dict[str, Any]
) -> None:
    """Test a service call."""

    # should check that the entity exists, and is available

    entry: ConfigEntry = await _setup_testbed_via_entry_(hass, rf, TEST_CONFIG)

    with patch(SERVICES[service][0]) as mock_method:
        try:
            _ = await hass.services.async_call(
                DOMAIN, service=service, service_data=data, blocking=True
            )
            # await hass.async_block_till_done()

            mock_method.assert_called_once()

            assert mock_method.call_args.kwargs == {
                k: v for k, v in SERVICES[service][1](data).items() if k != "entity_id"
            }

        finally:
            await hass.config_entries.async_unload(entry.entry_id)


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def _test_service_call(
    hass: HomeAssistant, rf: VirtualRf, service: str, data: dict[str, Any]
) -> None:
    """Test a service call."""

    entry: ConfigEntry = await _setup_testbed_via_entry_(hass, rf, TEST_CONFIG)

    with patch(SERVICES[service][0]) as mock_method:
        try:
            _ = await hass.services.async_call(
                DOMAIN, service=service, service_data=data, blocking=True
            )  # Referenced entities sensor.07_046947_temperature are missing...
            # await hass.async_block_till_done()

            mock_method.assert_called_once()

            service_call: ServiceCall = mock_method.call_args[0][0]
            assert service_call.data == SERVICES[service][1](data)

        finally:
            await hass.config_entries.async_unload(entry.entry_id)


########################################################################################


async def _test_put_co2_level(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the put_room_co2_level service call."""

    data = {
        "entity_id": "sensor.07_046947_co2_level",
        "co2_level": 600,
    }

    await _test_entity_service_call(hass, rf, SVC_PUT_CO2_LEVEL, data)


async def test_put_dhw_temp(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the put_dhe_temp service call."""

    data = {
        "entity_id": "sensor.07_046947_temperature",
        "temperature": 56.3,
    }

    await _test_entity_service_call(hass, rf, SVC_PUT_DHW_TEMP, data)


async def _test_put_indoor_humidity(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the put_indoor_humidity service call."""

    data = {
        "entity_id": "sensor.07_046947_humidity",
        "humidity": 56.3,
    }

    await _test_entity_service_call(hass, rf, SVC_PUT_INDOOR_HUMIDITY, data)


async def test_put_room_temp(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the put_room_temp service call."""

    data = {
        "entity_id": "sensor.34_092243_temperature",
        "temperature": 21.3,
    }

    await _test_entity_service_call(hass, rf, SVC_PUT_ROOM_TEMP, data)


async def _test_fake_dhw_temp(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_fake_zone_temp(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_get_dhw_schedule(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_get_zone_schedule(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_reset_dhw_mode(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_reset_dhw_params(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def test_reset_system_mode(hass: HomeAssistant, rf: VirtualRf) -> None:
    data = {"entity_id": "climate.01_145038"}

    await _test_entity_service_call(hass, rf, SVC_RESET_SYSTEM_MODE, data)


async def _test_reset_zone_config(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_reset_zone_mode(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_set_dhw_boost(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_set_dhw_mode(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_set_dhw_params(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_set_dhw_schedule(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


TESTS_SET_SYSTEM_MODE: dict[str, dict[str, Any]] = {
    "00": {"mode": "auto"},
    "01": {"mode": "eco_boost"},
    "02": {"mode": "day_off", "period": {"days": 3}},
    "03": {"mode": "eco_boost", "duration": {"hours": 3, "minutes": 30}},
}


@pytest.mark.parametrize("index", TESTS_SET_SYSTEM_MODE)
async def test_set_system_mode(
    hass: HomeAssistant,
    rf: VirtualRf,
    index: str,
    tests: dict[str, Any] = TESTS_SET_SYSTEM_MODE,
) -> None:
    data = {
        "entity_id": "climate.01_145038",
        **TESTS_SET_SYSTEM_MODE[index],
    }

    await _test_entity_service_call(hass, rf, SVC_SET_SYSTEM_MODE, data)


async def _test_set_zone_config(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_set_zone_mode(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def _test_set_zone_schedule(hass: HomeAssistant, rf: VirtualRf) -> None:
    pass


async def test_svc_bind_device(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the service call."""

    data = {
        "device_id": "22:140285",
        "offer": {"30C9": "00"},
    }

    await _test_service_call(hass, rf, SVC_BIND_DEVICE, data)


async def test_svc_force_update(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Test the service call."""

    data: dict[str, Any] = {}

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
