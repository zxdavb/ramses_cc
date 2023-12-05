"""Support for RAMSES sensors."""
from __future__ import annotations

from dataclasses import dataclass
import logging
from types import UnionType
from typing import Any

from ramses_rf.device.base import Entity as RamsesRFEntity
import voluptuous as vol

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesController, RamsesEntity, RamsesEntityDescription
from .const import (
    ATTR_CO2_LEVEL,
    ATTR_INDOOR_HUMIDITY,
    ATTR_SETPOINT,
    CONTROLLER,
    DOMAIN,
    SERVICE_PUT_CO2_LEVEL,
    SERVICE_PUT_INDOOR_HUMIDITY,
    UnitOfVolumeFlowRate,
)


@dataclass(kw_only=True)
class RamsesSensorEntityDescription(RamsesEntityDescription, SensorEntityDescription):
    """Class describing Ramses binary sensor entities."""

    attr: str | None = None
    entity_class: RamsesSensor | None = None
    rf_entity_class: type | UnionType | None = RamsesRFEntity
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    icon_off: str | None = None
    has_entity_name = True

    def __post_init__(self):
        """Defaults entity attr to key."""
        self.attr = self.attr or self.key


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Ramses sensors."""
    controller: RamsesController = hass.data[DOMAIN][CONTROLLER]
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_PUT_CO2_LEVEL,
        {
            vol.Required(ATTR_CO2_LEVEL): vol.All(
                cv.positive_int,
                vol.Range(min=0, max=16384),
            ),
        },
        "async_put_co2_level",
    )

    platform.async_register_entity_service(
        SERVICE_PUT_INDOOR_HUMIDITY,
        {
            vol.Required(ATTR_INDOOR_HUMIDITY): vol.All(
                cv.positive_float,
                vol.Range(min=0, max=100),
            ),
        },
        "async_put_indoor_humidity",
    )

    sensor_types: tuple[RamsesSensorEntityDescription, ...] = (
        RamsesSensorEntityDescription(
            key="temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            entity_category=None,
            extra_attributes={
                ATTR_SETPOINT: "setpoint",
            },
        ),
        RamsesSensorEntityDescription(
            key="heat_demand",
            name="Heat demand",
            icon="mdi:radiator",
            icon_off="mdi:radiator-off",
        ),
        RamsesSensorEntityDescription(
            key="relay_demand",
            name="Relay demand",
            icon="mdi:power-plug",
            icon_off="mdi:power-plug-off",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="relay_demand_fa",
            name="Relay demand (FA)",
            icon="mdi:power-plug",
            icon_off="mdi:power-plug-off",
            native_unit_of_measurement=PERCENTAGE,
            entity_registry_enabled_default=False,
        ),
        RamsesSensorEntityDescription(
            key="boiler_output_temp",
            name="Boiler output temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="boiler_return_temp",
            name="Boiler return temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="boiler_setpoint",
            name="Boiler setpoint",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="ch_setpoint",
            name="CH setpoint",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="ch_max_setpoint",
            name="CH max setpoint",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="ch_water_pressure",
            name="CH water pressure",
            device_class=SensorDeviceClass.PRESSURE,
            native_unit_of_measurement=UnitOfPressure.BAR,
        ),
        RamsesSensorEntityDescription(
            key="dhw_flow_rate",
            name="DHW flow rate",
            native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        ),
        RamsesSensorEntityDescription(
            key="dhw_setpoint",
            name="DHW setpoint",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="dhw_temp",
            name="DHW temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="outside_temp",
            name="Outside temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="max_rel_modulation",
            name="Max relative modulation level",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="rel_modulation_level",
            name="Relative modulation level",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="indoor_humidity",
            name="Indoor humidiity",
            device_class=SensorDeviceClass.HUMIDITY,
            native_unit_of_measurement=PERCENTAGE,
            entity_category=None,
        ),
        RamsesSensorEntityDescription(
            key="co2_level",
            device_class=SensorDeviceClass.CO2,
            native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
            entity_category=None,
        ),
        RamsesSensorEntityDescription(
            key="indoor_temperature",
            attr="indoor_temp",
            name="Indoor temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            entity_category=None,
        ),
        RamsesSensorEntityDescription(
            key="air_quality",
            name="Air quality",
            native_unit_of_measurement=PERCENTAGE,
            entity_category=None,
        ),
        RamsesSensorEntityDescription(
            key="outdoor_temperature",
            attr="outdoor_temp",
            name="Outdoor temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="air_quality_basis",
            name="Air quality basis",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="exhaust_fan_speed",
            name="Exhaust fan speed",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="exhaust_temp",
            name="Exhaust temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        RamsesSensorEntityDescription(
            key="fan_info",
            name="Fan info",
            state_class=None,
        ),
        RamsesSensorEntityDescription(
            key="filter_remaining",
            name="Filter remaining",
            native_unit_of_measurement=UnitOfTime.DAYS,
        ),
        RamsesSensorEntityDescription(
            key="post_heat",
            name="Post heat",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="pre_heat",
            name="Pre heat",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="remaining_time",
            attr="remaining_mins",
            name="Remaining time",
            native_unit_of_measurement=UnitOfTime.MINUTES,
        ),
        RamsesSensorEntityDescription(
            key="speed_cap",
            name="Speed cap",
            native_unit_of_measurement="units",
        ),
        RamsesSensorEntityDescription(
            key="supply_fan_speed",
            name="Suply fan speed",
            native_unit_of_measurement=PERCENTAGE,
        ),
        RamsesSensorEntityDescription(
            key="supply_flow",
            name="Supply flow",
            native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_SECOND,
        ),
        RamsesSensorEntityDescription(
            key="supply_temperature",
            attr="supply_temp",
            name="Supply temperature",
            device_class=SensorDeviceClass.TEMPERATURE,
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ),
        # Special projects
        RamsesSensorEntityDescription(
            key="oem_code",
            name="OEM code",
            state_class=None,
            entity_registry_enabled_default=False,
        ),
        RamsesSensorEntityDescription(
            key="percent",
            name="Percent",
            icon="mdi:power-plug",
            icon_off="mdi:power-plug-off",
            native_unit_of_measurement=PERCENTAGE,
            entity_registry_enabled_default=False,
        ),
        RamsesSensorEntityDescription(
            key="value",
            name="Value",
            native_unit_of_measurement="units",
            entity_registry_enabled_default=False,
        ),
    )

    async def async_add_new_entity(entity: RamsesRFEntity) -> None:
        entities = [
            (description.entity_class or RamsesSensor)(controller, entity, description)
            for description in sensor_types
            if isinstance(entity, description.rf_entity_class)
            and hasattr(entity, description.key)
        ]
        async_add_entities(entities)

    controller.async_register_platform(platform, async_add_new_entity)


class RamsesSensor(RamsesEntity, SensorEntity):
    """Representation of a generic sensor."""

    entity_description: RamsesSensorEntityDescription

    def __init__(
        self, controller, device, entity_description: RamsesEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(controller, device, entity_description)

        self.entity_id = ENTITY_ID_FORMAT.format(
            f"{device.id}_{entity_description.attr}"
        )
        self._attr_unique_id = f"{device.id}-{entity_description.key}"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.state is not None

    @property
    def native_value(self) -> Any | None:
        """Return the native value of the sensor."""
        val = getattr(self.rf_entity, self.entity_description.attr)
        if self.native_unit_of_measurement == PERCENTAGE:
            return None if val is None else val * 100
        return val

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        if self.entity_description.icon_off and not self.native_value:
            return self.entity_description.icon_off
        return super().icon

    # TODO: Remove this when we have config entries and devices.
    @property
    def name(self) -> str:
        """Return name temporarily prefixed with device ID."""
        return f"{self.rf_entity.id} {super().name}"

    async def async_put_co2_level(self, co2_level: int = None) -> None:
        """Set the CO2 level."""
        self.rf_entity.co2_level = co2_level

    async def async_put_indoor_humidity(self, indoor_humidity: float = None) -> None:
        """Set the indoor humidity level."""
        self.rf_entity.indoor_humidity = indoor_humidity / 100
