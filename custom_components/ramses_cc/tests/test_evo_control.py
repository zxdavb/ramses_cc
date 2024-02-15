"""Test the compatibility of the interface with EvoControl."""

from pathlib import Path

from custom_components.ramses_cc.binary_sensor import BINARY_SENSOR_DESCRIPTIONS
from custom_components.ramses_cc.broker import RamsesBroker
from custom_components.ramses_cc.climate import CLIMATE_DESCRIPTIONS
from custom_components.ramses_cc.sensor import SENSOR_DESCRIPTIONS
from custom_components.ramses_cc.water_heater import WATER_HEATER_DESCRIPTIONS
from ramses_rf.gateway import Gateway
from ramses_rf.system import Evohome

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.climate import PRESET_ECO, ClimateEntity, HVACMode
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.water_heater import WaterHeaterEntity
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

TEST_DIR = Path(__file__).resolve().parent
INPUT_FILE = "evo_control.log"

SCHEMA = {
    "system": {"appliance_control": "13:120241"},
    "orphans": [],
    "stored_hotwater": {
        "sensor": "07:046947",
        "hotwater_valve": "13:120242",
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


async def instantiate_entities(
    hass: HomeAssistant,
) -> tuple[
    list[ClimateEntity],
    list[WaterHeaterEntity],
    list[BinarySensorEntity],
    list[SensorEntity],
]:
    with open(f"{TEST_DIR}/{INPUT_FILE}") as f:
        gwy: Gateway = Gateway(
            port_name=None, input_file=f, config={"disable_discovery": True}
        )
        await gwy.start()

    broker: RamsesBroker = MockRamsesBroker(hass)

    # climate entities (TCS, zones)
    rf_climates = [s for s in gwy.systems if isinstance(s, Evohome)]
    rf_climates += [z for s in gwy.systems for z in s.zones if isinstance(s, Evohome)]

    climates: list[ClimateEntity] = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_climates
        for description in CLIMATE_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
    ]

    # water_heater entities (DHW)
    rf_heaters = [s.dhw for s in gwy.systems if s.dhw if isinstance(s, Evohome)]

    water_heaters: list[WaterHeaterEntity] = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_heaters
        for description in WATER_HEATER_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
    ]

    # binary_sensors & sensors entities
    rf_devices = gwy.devices + rf_climates + rf_heaters

    binary_sensors: list[BinarySensorEntity] = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_devices
        for description in BINARY_SENSOR_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
        and hasattr(device, description.ramses_rf_attr)
    ]

    sensors: list[SensorEntity] = [
        description.ramses_cc_class(broker, device, description)
        for device in rf_devices
        for description in SENSOR_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
        and hasattr(device, description.ramses_rf_attr)
    ]

    return climates, water_heaters, binary_sensors, sensors


async def test_namespace(hass: HomeAssistant) -> None:
    """Test the namespace (i.e. entity_id) of entities used by EvoControl."""

    # The intention here is check the namespace used by EvoControl
    climates, water_heaters, binary_sensors, sensors = await instantiate_entities(hass)

    #
    # evo_control uses: binary_sensor.${cid}_status
    ctl_id = "01:145038"  # via a webform, from the user
    id = f"binary_sensor.{ctl_id}_status"

    binary: BinarySensorEntity = [e for e in binary_sensors if e.entity_id == id][0]
    assert binary.unique_id == f"{ctl_id}-status"
    assert binary.state in (STATE_ON, STATE_OFF, None)

    #
    # evo_control uses: the working_schema
    schema = binary.extra_state_attributes["working_schema"]
    assert schema["stored_hotwater"] == SCHEMA["stored_hotwater"]
    assert schema["zones"] == SCHEMA["zones"]

    #
    # evo_control uses: binary_sensor.${i}_battery_low
    for dev_id in (
        "04:056053",
        "07:046947",
        "22:140285",
        "34:092243",
    ):  # via walking the schema
        id = f"binary_sensor.{dev_id}_battery_low"

        binary = [e for e in binary_sensors if e.entity_id == id][0]
        assert binary.unique_id == f"{dev_id}-battery_low"
        assert binary.state in (STATE_ON, STATE_OFF, None)

        battery_level = binary.extra_state_attributes["battery_level"]
        assert battery_level is None or 0.0 < battery_level < 1.0  # FIXME

    #
    # evo_control uses: binary_sensor.${cid}_${haZid}_window_open
    for zon_idx in ("02", "0A"):  # via walking the schema
        id = f"binary_sensor.{ctl_id}_{zon_idx}_window_open"

        binary = [e for e in binary_sensors if e.entity_id == id][0]
        assert binary.unique_id == f"{ctl_id}_{zon_idx}-window_open"

        assert binary.state in (STATE_ON, STATE_OFF, None)

    #
    # evo_control uses: sensor.${cid}_heat_demand
    id = f"sensor.{ctl_id}_heat_demand"

    sensor: SensorEntity = [e for e in sensors if e.entity_id == id][0]
    assert sensor.unique_id == f"{ctl_id}-heat_demand"

    assert sensor.state is None or 0.0 <= sensor.state <= 100.0

    #
    # evo_control uses: sensor.${dhwRelayId}_relay_demand
    dhw_id = SCHEMA["stored_hotwater"]["hotwater_valve"]  # type: ignore[index]
    id = f"binary_sensor.{dhw_id}_active"

    binary = [e for e in binary_sensors if e.entity_id == id][0]
    assert binary.unique_id == f"{dhw_id}-active"

    assert binary.state in (STATE_ON, STATE_OFF, None)

    id = f"sensor.{dhw_id}_relay_demand"

    #
    sensor = [e for e in sensors if e.entity_id == id][0]
    assert sensor.unique_id == f"{dhw_id}-relay_demand"

    assert sensor.state is None or 0.0 <= sensor.state <= 100.0

    #
    # evo_control uses: sensor.${cid}_${haZid}_heat_demand
    for zon_idx in ("02", "0A", "HW"):  # via walking the schema
        id = f"sensor.{ctl_id}_{zon_idx}_heat_demand"

        sensor = [e for e in sensors if e.entity_id == id][0]
        assert sensor.unique_id == f"{ctl_id}_{zon_idx}-heat_demand"

        assert sensor.state is None or 0.0 <= sensor.state <= 100.0

    #
    # evo_control uses: climate.${cid}
    id = f"climate.{ctl_id}"  # via a webform, from the user

    climate: ClimateEntity = [e for e in climates if e.entity_id == id][0]
    assert climate.unique_id == ctl_id
    # assert climate.name is None or True  # FIXME

    assert climate.state == HVACMode.HEAT
    assert climate.preset_mode == PRESET_ECO
    assert climate.extra_state_attributes["system_mode"] == {
        "system_mode": "eco_boost",
        "until": "2022-03-06T14:44:00",
    }

    #
    # evo_control uses: climate.${cid}_${haZid}
    for zon_idx in ("02", "0A"):  # via walking the schema
        id = f"climate.{ctl_id}_{zon_idx}"

        climate = [e for e in climates if e.entity_id == id][0]
        assert climate.unique_id == f"{ctl_id}_{zon_idx}"
        # assert climate._device.name == SCHEMA["zones"][zon_idx]["_name"]  # FIXME

        assert isinstance(climate.current_temperature, float)
        assert zon_idx != "02" or climate.extra_state_attributes["mode"] == {
            "mode": "permanent_override",
            "setpoint": 5.0,
        }
        assert zon_idx != "0A" or climate.extra_state_attributes["mode"] == {
            "mode": "temporary_override",
            "setpoint": 20.0,
            "until": "2022-01-22T10:00:00",
        }

    #
    # evo_control uses: water_heater.${cid}_hw
    id = f"water_heater.{ctl_id}_HW"  # via walking the schema

    heater: WaterHeaterEntity = [e for e in water_heaters if e.entity_id == id][0]
    assert heater.unique_id == f"{ctl_id}_HW"
    # assert heater.name == "Stored HW"  # FIXME

    assert heater.current_temperature == 61.87
    assert heater.extra_state_attributes["mode"] == {
        "mode": "temporary_override",
        "active": True,
        "until": "2022-02-10T22:00:00",
    }

    assert True
