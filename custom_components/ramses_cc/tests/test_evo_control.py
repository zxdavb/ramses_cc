"""Test the compatibility of the interface with EvoControl."""

from pathlib import Path

from custom_components.ramses_cc.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.ramses_cc.broker import RamsesBroker
from custom_components.ramses_cc.climate import CLIMATE_DESCRIPTIONS
from custom_components.ramses_cc.sensor import SENSOR_DESCRIPTIONS
from custom_components.ramses_cc.water_heater import WATER_HEATER_DESCRIPTIONS
from ramses_rf.gateway import Gateway
from ramses_rf.system import Evohome

from homeassistant.core import HomeAssistant

TEST_DIR = Path(__file__).resolve().parent
INPUT_FILE = "evo_control.log"


SCHEMA = {
    "system": {"appliance_control": None},
    "orphans": [],
    "stored_hotwater": {
        "sensor": "07:046947",
        "hotwater_valve": None,
        "heating_valve": None,
    },
    "underfloor_heating": {},
    "zones": {
        "02": {
            "_name": "Kitchen",
            "class": "radiator_valve",
            "sensor": "34:092243",
            "actuators": ["04:056053"],
        },
        "0A": {
            "_name": "Office",
            "class": "radiator_valve",
            "sensor": "22:140285",
            "actuators": ["04:189082"],
        },
    },
}


class MockRamsesBroker:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass


async def test_binary_sensors(hass: HomeAssistant) -> None:
    """Test the namespace (i.e. entity_id) of entities used by EvoControl."""

    with open(f"{TEST_DIR}/{INPUT_FILE}") as f:
        gwy: Gateway = Gateway(
            port_name=None, input_file=f, config={"disable_discovery": True}
        )
        await gwy.start()

    assert gwy.devices

    broker: RamsesBroker = MockRamsesBroker(hass)

    # climate entities (TCS, zones)
    rf_climates = [s for s in gwy.systems if isinstance(s, Evohome)]
    rf_climates += [z for s in gwy.systems for z in s.zones if isinstance(s, Evohome)]

    # water_heater entities (DHW)
    rf_heaters = [s.dhw for s in gwy.systems if s.dhw if isinstance(s, Evohome)]

    # binary_sensors & sensors entities
    rf_devices = gwy.devices + rf_climates + rf_heaters

    climates = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_climates
        for description in CLIMATE_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
    ]

    water_heaters = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_heaters
        for description in WATER_HEATER_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
    ]

    binary_sensors = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_devices
        for description in BINARY_SENSOR_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
        and hasattr(device, description.ramses_rf_attr)
    ]

    sensors = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_devices
        for description in SENSOR_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
        and hasattr(device, description.ramses_rf_attr)
    ]

    # The intention here is check the namespace used by EvoControl

    # binary_sensor.${cid}_status
    id = "binary_sensor.01:145038_status"
    evo = [e for e in binary_sensors if e.entity_id == id][0]

    # the working schema
    schema = evo.extra_state_attributes["working_schema"]
    assert schema["stored_hotwater"] == SCHEMA["stored_hotwater"]
    assert schema["zones"] == SCHEMA["zones"]

    # binary_sensor.${i}_battery_low
    for id in ("binary_sensor.34:092243_battery_low",):
        assert [e for e in binary_sensors if e.entity_id == id]

    # binary_sensor.${cid}_${haZid}_window_open
    for id in (
        "binary_sensor.01:145038_02_window_open",
        "binary_sensor.01:145038_0A_window_open",
    ):
        assert [e for e in binary_sensors if e.entity_id == id]

    # sensor.${cid}_heat_demand
    for id in ("sensor.01:145038_heat_demand",):
        assert [e for e in sensors if e.entity_id == id]

    # sensor.${dhwRelayId}_relay_demand
    for id in ("sensor.01:145038_HW_heat_demand",):
        assert [e for e in sensors if e.entity_id == id]

    # sensor.${cid}_${haZid}_heat_demand
    for id in (
        "sensor.01:145038_0A_heat_demand",
        "sensor.01:145038_0A_heat_demand",
    ):
        assert [e for e in sensors if e.entity_id == id]

    # climate.${cid}
    for id in ("climate.01:145038",):
        assert [e for e in climates if e.entity_id == id]

    # climate.${cid}_${haZid}
    for id in ("climate.01:145038_02", "climate.01:145038_0A"):
        assert [e for e in climates if e.entity_id == id]

    # water_heater.${cid}_hw
    for id in ("water_heater.01:145038_HW",):
        assert [e for e in water_heaters if e.entity_id == id]
