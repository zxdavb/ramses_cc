"""Test the setup."""

from collections.abc import AsyncGenerator
from typing import Any, Final
from unittest.mock import patch

from custom_components.ramses_cc import (
    DOMAIN,
    SCH_BIND_DEVICE,
    SCH_NO_SVC_PARAMS,
    SCH_SEND_PACKET,
    SVC_BIND_DEVICE,
    SVC_FORCE_UPDATE,
    SVC_SEND_PACKET,
)
from custom_components.ramses_cc.broker import RamsesBroker
from custom_components.ramses_cc.schemas import (
    SCH_NO_ENTITY_SVC_PARAMS,
    SCH_PUT_CO2_LEVEL,
    SCH_PUT_DHW_TEMP,
    SCH_PUT_INDOOR_HUMIDITY,
    SCH_PUT_ROOM_TEMP,
    SCH_SET_DHW_MODE,
    SCH_SET_DHW_PARAMS,
    SCH_SET_DHW_SCHEDULE,
    SCH_SET_SYSTEM_MODE,
    SCH_SET_ZONE_CONFIG,
    SCH_SET_ZONE_MODE,
    SCH_SET_ZONE_SCHEDULE,
    SVC_FAKE_DHW_TEMP,
    SVC_FAKE_ZONE_TEMP,
    SVC_GET_DHW_SCHEDULE,
    SVC_GET_ZONE_SCHEDULE,
    SVC_PUT_CO2_LEVEL,
    SVC_PUT_DHW_TEMP,
    SVC_PUT_INDOOR_HUMIDITY,
    SVC_PUT_ROOM_TEMP,
    SVC_RESET_DHW_MODE,
    SVC_RESET_DHW_PARAMS,
    SVC_RESET_SYSTEM_MODE,
    SVC_RESET_ZONE_CONFIG,
    SVC_RESET_ZONE_MODE,
    SVC_SET_DHW_BOOST,
    SVC_SET_DHW_MODE,
    SVC_SET_DHW_PARAMS,
    SVC_SET_DHW_SCHEDULE,
    SVC_SET_SYSTEM_MODE,
    SVC_SET_ZONE_CONFIG,
    SVC_SET_ZONE_MODE,
    SVC_SET_ZONE_SCHEDULE,
    SVCS_RAMSES_CLIMATE,  # SVCS_RAMSES_REMOTE,
    SVCS_RAMSES_SENSOR,
    SVCS_RAMSES_WATER_HEATER,
)
import pytest
from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped]
    MockConfigEntry,
)
from ramses_rf.gateway import Gateway
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .common import TEST_DIR, cast_packets_to_rf
from .virtual_rf import VirtualRf

# patched constants
_CALL_LATER_DELAY: Final = 0  # from: custom_components.ramses_cc.broker.py


NUM_DEVS_BEFORE = 2  # HGI, faked THM (before casting packets to RF)
NUM_DEVS_AFTER = 14  # proxy for success of cast_packets_to_rf()
NUM_SVCS_AFTER = 7  # proxy for success
NUM_ENTS_AFTER = 43  # proxy for success


TEST_CONFIG = {
    "serial_port": {"port_name": None},
    "ramses_rf": {"disable_discovery": True},
    "advanced_features": {"send_packet": True},
    "known_list": {
        "03:123456": {"class": "THM", "faked": True},
        "32:097710": {"class": "CO2"},
        "32:139773": {"class": "HUM"},
    },
}


SERVICES = {
    SVC_BIND_DEVICE: (
        "custom_components.ramses_cc.broker.RamsesBroker.async_bind_device",
        SCH_BIND_DEVICE,
    ),
    SVC_FAKE_DHW_TEMP: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_fake_dhw_temp",
        SCH_PUT_DHW_TEMP,
    ),
    SVC_FAKE_ZONE_TEMP: (
        "custom_components.ramses_cc.climate.RamsesZone.async_fake_zone_temp",
        SCH_PUT_ROOM_TEMP,
    ),
    SVC_FORCE_UPDATE: (
        "custom_components.ramses_cc.broker.RamsesBroker.async_force_update",
        SCH_NO_SVC_PARAMS,
    ),
    SVC_GET_DHW_SCHEDULE: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_get_dhw_schedule",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_GET_ZONE_SCHEDULE: (
        "custom_components.ramses_cc.climate.RamsesZone.async_get_zone_schedule",
        SCH_NO_ENTITY_SVC_PARAMS,
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
    SVC_RESET_DHW_MODE: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_reset_dhw_mode",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_RESET_DHW_PARAMS: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_reset_dhw_params",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_RESET_SYSTEM_MODE: (
        "custom_components.ramses_cc.climate.RamsesController.async_reset_system_mode",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_RESET_ZONE_CONFIG: (
        "custom_components.ramses_cc.climate.RamsesZone.async_reset_zone_config",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_RESET_ZONE_MODE: (
        "custom_components.ramses_cc.climate.RamsesZone.async_reset_zone_mode",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_SET_DHW_BOOST: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_set_dhw_boost",
        SCH_NO_ENTITY_SVC_PARAMS,
    ),
    SVC_SET_DHW_MODE: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_set_dhw_mode",
        SCH_SET_DHW_MODE,
    ),
    SVC_SET_DHW_PARAMS: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_set_dhw_params",
        SCH_SET_DHW_PARAMS,
    ),
    SVC_SET_DHW_SCHEDULE: (
        "custom_components.ramses_cc.water_heater.RamsesWaterHeater.async_set_dhw_schedule",
        SCH_SET_DHW_SCHEDULE,
    ),
    SVC_SET_SYSTEM_MODE: (
        "custom_components.ramses_cc.climate.RamsesController.async_set_system_mode",
        SCH_SET_SYSTEM_MODE,
    ),
    SVC_SET_ZONE_CONFIG: (
        "custom_components.ramses_cc.climate.RamsesZone.async_set_zone_config",
        SCH_SET_ZONE_CONFIG,
    ),
    SVC_SET_ZONE_MODE: (
        "custom_components.ramses_cc.climate.RamsesZone.async_set_zone_mode",
        SCH_SET_ZONE_MODE,
    ),
    SVC_SET_ZONE_SCHEDULE: (
        "custom_components.ramses_cc.climate.RamsesZone.async_set_zone_schedule",
        SCH_SET_ZONE_SCHEDULE,
    ),
}


async def _cast_packets_to_rf(hass: HomeAssistant, rf: VirtualRf) -> None:
    """Load packets from a CH/DHW system."""

    gwy: Gateway = list(hass.data[DOMAIN].values())[0].client
    assert len(gwy.devices) == NUM_DEVS_BEFORE

    await cast_packets_to_rf(rf, f"{TEST_DIR}/system_1.log", gwy=gwy)
    assert len(gwy.devices) == NUM_DEVS_AFTER  # proxy for success of above

    assert len(hass.services.async_services_for_domain(DOMAIN)) == NUM_SVCS_AFTER


async def _setup_via_entry_(
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
    await _cast_packets_to_rf(hass, rf)

    broker: RamsesBroker = list(hass.data[DOMAIN].values())[0]

    await broker.async_update()
    await hass.async_block_till_done()
    assert len(broker._entities) == NUM_ENTS_AFTER  # proxy for success of above

    return entry


@pytest.fixture()  # need hass fixture to ensure hass/rf use same event loop
async def entry(hass: HomeAssistant) -> AsyncGenerator[ConfigEntry, None]:
    """Set up the test bed."""

    # Utilize a virtual evofw3-compatible gateway
    rf = VirtualRf(2)
    rf.set_gateway(rf.ports[0], "18:000730")

    with patch(
        "custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY
    ):
        entry: ConfigEntry = None
        try:
            entry = await _setup_via_entry_(hass, rf, TEST_CONFIG)
            yield entry

        finally:
            if entry:
                await hass.config_entries.async_unload(entry.entry_id)
                # await hass.async_block_till_done()
            await rf.stop()


async def _test_entity_service_call(
    hass: HomeAssistant, service: str, data: dict[str, Any], schema: vol.Schema
) -> None:
    """Test an entity service call."""

    # should check that the entity exists, and is available

    assert schema == SERVICES[service][1]

    with patch(SERVICES[service][0]) as mock_method:
        _ = await hass.services.async_call(
            DOMAIN, service=service, service_data=data, blocking=True
        )

        mock_method.assert_called_once()

        assert mock_method.call_args.kwargs == {
            k: v for k, v in SERVICES[service][1](data).items() if k != "entity_id"
        }


async def _test_service_call(
    hass: HomeAssistant, service: str, data: dict[str, Any], schema: vol.Schema
) -> None:
    """Test a service call."""

    # should check that referenced entity, if any, exists and is available

    assert schema == SERVICES[service][1]

    with patch(SERVICES[service][0]) as mock_method:
        _ = await hass.services.async_call(
            DOMAIN, service=service, service_data=data, blocking=True
        )

        mock_method.assert_called_once()

        service_call: ServiceCall = mock_method.call_args[0][0]
        assert service_call.data == SERVICES[service][1](data)


########################################################################################


async def test_put_co2_level(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the put_room_co2_level service call."""

    data = {
        "entity_id": "sensor.32_097710_co2_level",
        "co2_level": 600,
    }

    service = SVC_PUT_CO2_LEVEL
    schema = SVCS_RAMSES_SENSOR[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_put_dhw_temp(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the put_dhe_temp service call."""

    data = {
        "entity_id": "sensor.07_046947_temperature",
        "temperature": 56.3,
    }

    service = SVC_PUT_DHW_TEMP
    schema = SVCS_RAMSES_SENSOR[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_put_indoor_humidity(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the put_indoor_humidity service call."""

    data = {
        "entity_id": "sensor.32_139773_indoor_humidity",
        "indoor_humidity": 56.3,
    }

    service = SVC_PUT_INDOOR_HUMIDITY
    schema = SVCS_RAMSES_SENSOR[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_put_room_temp(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the put_room_temp service call."""

    data = {
        "entity_id": "sensor.34_092243_temperature",
        "temperature": 21.3,
    }

    service = SVC_PUT_ROOM_TEMP
    schema = SVCS_RAMSES_SENSOR[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_fake_dhw_temp(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "water_heater.01_145038_hw",
        "temperature": 51.3,
    }

    await _test_entity_service_call(hass, SVC_FAKE_DHW_TEMP, data, SCH_PUT_DHW_TEMP)


async def test_fake_zone_temp(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "climate.01_145038_02",
        "temperature": 21.3,
    }

    await _test_entity_service_call(hass, SVC_FAKE_ZONE_TEMP, data, SCH_PUT_ROOM_TEMP)


async def test_get_dhw_schedule(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "water_heater.01_145038_hw"}

    service = SVC_GET_DHW_SCHEDULE
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_get_zone_schedule(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "climate.01_145038_02"}

    service = SVC_GET_ZONE_SCHEDULE
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_reset_dhw_mode(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "water_heater.01_145038_hw"}

    service = SVC_RESET_DHW_MODE
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_reset_dhw_params(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "water_heater.01_145038_hw"}

    service = SVC_RESET_DHW_PARAMS
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_reset_system_mode(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "climate.01_145038"}

    service = SVC_RESET_SYSTEM_MODE
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_reset_zone_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "climate.01_145038_02",
    }

    service = SVC_RESET_ZONE_CONFIG
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_reset_zone_mode(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "climate.01_145038_02"}

    service = SVC_RESET_ZONE_MODE
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_set_dhw_boost(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {"entity_id": "water_heater.01_145038_hw"}

    service = SVC_SET_DHW_BOOST
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


TESTS_SET_DHW_MODE = {
    "00": {"mode": "follow_schedule"},
    "01": {"mode": "permanent_override", "active": True},
    "02": {"mode": "temporary_override", "active": True, "duration": {"minutes": 90}},
    "03": {"mode": "temporary_override", "active": True, "duration": {"hours": 3}},
}


@pytest.mark.parametrize("idx", TESTS_SET_DHW_MODE)
async def test_set_dhw_mode(hass: HomeAssistant, entry: ConfigEntry, idx: str) -> None:
    data = {
        "entity_id": "water_heater.01_145038_hw",
        **TESTS_SET_DHW_MODE[idx],
    }

    service = SVC_SET_DHW_MODE
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


async def _test_set_dhw_params(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "water_heater.01_145038_hw",
    }

    service = SVC_SET_DHW_PARAMS
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


async def _test_set_dhw_schedule(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "water_heater.01_145038_hw",
    }

    service = SVC_SET_DHW_SCHEDULE
    schema = SVCS_RAMSES_WATER_HEATER[service]

    await _test_entity_service_call(hass, service, data, schema)


TESTS_SET_SYSTEM_MODE: dict[str, dict[str, Any]] = {
    "00": {"mode": "auto"},
    "01": {"mode": "eco_boost"},
    "02": {"mode": "day_off", "period": {"days": 3}},
    "03": {"mode": "eco_boost", "duration": {"hours": 3, "minutes": 30}},
}


@pytest.mark.parametrize("idx", TESTS_SET_SYSTEM_MODE)
async def test_set_system_mode(
    hass: HomeAssistant, entry: ConfigEntry, idx: str
) -> None:
    data = {
        "entity_id": "climate.01_145038",
        **TESTS_SET_SYSTEM_MODE[idx],
    }

    service = SVC_SET_SYSTEM_MODE
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


async def _test_set_zone_config(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "climate.01_145038_02",
    }

    service = SVC_SET_ZONE_CONFIG
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


TESTS_SET_ZONE_MODE: dict[str, dict[str, Any]] = {
    "00": {"mode": "follow_schedule"},
    "01": {"mode": "permanent_override", "setpoint": 18.5},
    "02": {"mode": "temporary_override", "setpoint": 20.5, "duration": {"minutes": 90}},
    "03": {"mode": "temporary_override", "setpoint": 21.5, "duration": {"hours": 3}},
    "09": {"mode": "advanced_override", "setpoint": 19.5},
}  # need to add until...


@pytest.mark.parametrize("idx", TESTS_SET_ZONE_MODE)
async def test_set_zone_mode(hass: HomeAssistant, entry: ConfigEntry, idx: str) -> None:
    data = {
        "entity_id": "climate.01_145038_02",
        **TESTS_SET_ZONE_MODE[idx],
    }

    service = SVC_SET_ZONE_MODE
    schema = SVCS_RAMSES_CLIMATE[SVC_SET_ZONE_MODE]

    await _test_entity_service_call(hass, service, data, schema)


async def _test_set_zone_schedule(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = {
        "entity_id": "climate.01_145038_02",
    }

    service = SVC_SET_ZONE_SCHEDULE
    schema = SVCS_RAMSES_CLIMATE[service]

    await _test_entity_service_call(hass, service, data, schema)


async def test_svc_bind_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the service call."""

    data = {
        "device_id": "22:140285",
        "offer": {"30C9": "00"},
    }

    await _test_service_call(hass, SVC_BIND_DEVICE, data, SCH_BIND_DEVICE)


async def test_svc_force_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the service call."""

    data: dict[str, Any] = {}

    await _test_service_call(hass, SVC_FORCE_UPDATE, data, SCH_NO_SVC_PARAMS)


async def test_svc_send_packet(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Test the service call."""

    data = {
        "device_id": "18:000730",
        "verb": " I",
        "code": "1FC9",
        "payload": "00",
    }

    await _test_service_call(hass, SVC_SEND_PACKET, data, SCH_SEND_PACKET)
