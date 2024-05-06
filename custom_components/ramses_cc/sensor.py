"""Support for RAMSES sensors."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import UnionType
from typing import Any

from homeassistant.components.sensor import (
    DOMAIN as PLATFORM,
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    EntityPlatform,
    async_get_current_platform,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from ramses_rf.const import (
    SZ_AIR_QUALITY,
    SZ_AIR_QUALITY_BASIS,
    SZ_CO2_LEVEL,
    SZ_EXHAUST_FAN_SPEED,
    SZ_EXHAUST_FLOW,
    SZ_EXHAUST_TEMP,
    SZ_FAN_INFO,
    SZ_FILTER_REMAINING,
    SZ_INDOOR_HUMIDITY,
    SZ_INDOOR_TEMP,
    SZ_OUTDOOR_HUMIDITY,
    SZ_OUTDOOR_TEMP,
    SZ_POST_HEAT,
    SZ_PRE_HEAT,
    SZ_REMAINING_MINS,
    SZ_SPEED_CAPABILITIES,
    SZ_SUPPLY_FAN_SPEED,
    SZ_SUPPLY_FLOW,
    SZ_SUPPLY_TEMP,
)
from ramses_rf.device import Fakeable
from ramses_rf.device.heat import (
    SZ_BOILER_OUTPUT_TEMP,
    SZ_BOILER_RETURN_TEMP,
    SZ_BOILER_SETPOINT,
    SZ_CH_MAX_SETPOINT,
    SZ_CH_SETPOINT,
    SZ_CH_WATER_PRESSURE,
    SZ_DHW_FLOW_RATE,
    SZ_DHW_SETPOINT,
    SZ_DHW_TEMP,
    SZ_MAX_REL_MODULATION,
    SZ_OEM_CODE,
    SZ_OUTSIDE_TEMP,
    SZ_REL_MODULATION_LEVEL,
    DhwSensor,
    OtbGateway,
    OutSensor,
    Thermostat,
    TrvActuator,
    UfhController,
)
from ramses_rf.device.hvac import HvacCarbonDioxideSensor, HvacHumiditySensor
from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_rf.system.heat import System
from ramses_rf.system.zones import ZoneBase
from ramses_tx.const import (
    SZ_DEWPOINT_TEMP,
    SZ_HEAT_DEMAND,
    SZ_RELAY_DEMAND,
    SZ_SETPOINT,
    SZ_TEMPERATURE,
)

from . import RamsesEntity, RamsesEntityDescription
from .broker import RamsesBroker
from .const import ATTR_SETPOINT, BROKER, DOMAIN, UnitOfVolumeFlowRate
from .schemas import SVCS_RAMSES_SENSOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create sensors for CH/DHW (heat) & HVAC."""

    if discovery_info is None:
        return

    broker: RamsesBroker = hass.data[DOMAIN][BROKER]

    if not broker._services.get(PLATFORM):
        broker._services[PLATFORM] = True
        platform: EntityPlatform = async_get_current_platform()

        for k, v in SVCS_RAMSES_SENSOR.items():
            platform.async_register_entity_service(k, v, f"async_{k}")

    entities = [
        description.ramses_cc_class(broker, device, description)
        for device in discovery_info["devices"]
        for description in SENSOR_DESCRIPTIONS
        if isinstance(device, description.ramses_rf_class)
        and hasattr(device, description.ramses_rf_attr)
    ]
    async_add_entities(entities)


class RamsesSensor(RamsesEntity, SensorEntity):
    """Representation of a generic sensor."""

    entity_description: RamsesSensorEntityDescription

    def __init__(
        self,
        broker: RamsesBroker,
        device: RamsesRFEntity,
        entity_description: RamsesEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.info("Found %r: %s", device, entity_description.key)
        super().__init__(broker, device, entity_description)

        self.entity_id = ENTITY_ID_FORMAT.format(
            f"{device.id}_{entity_description.key}"
        )
        self._attr_unique_id = f"{device.id}-{entity_description.key}"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        # TODO: Should use dtm of last packet received, rather than is not None
        return (
            isinstance(self._device, Fakeable) and self._device.is_faked
        ) or self.state is not None  # TODO: but what if None _is_ its state?

    @property
    def native_value(self) -> Any | None:
        """Return the native value of the sensor."""
        val = getattr(self._device, self.entity_description.ramses_rf_attr)
        if self.native_unit_of_measurement == PERCENTAGE:
            return None if val is None else val * 100
        return val

    @property
    def icon(self) -> str | None:
        """Return the icon to use in the frontend, if any."""
        if self.entity_description.ramses_cc_icon_off and not self.native_value:
            return self.entity_description.ramses_cc_icon_off
        return super().icon

    # TODO: Remove this when we have config entries and devices.
    @property
    def name(self) -> str:
        """Return name temporarily prefixed with device name/id."""
        prefix = (
            self._device.name
            if hasattr(self._device, "name") and self._device.name
            else self._device.id
        )
        return f"{prefix} {super().name}"

    # the following methods are integration-specific service calls

    @callback
    def async_put_co2_level(self, co2_level: int) -> None:
        """Cast the CO2 level (if faked)."""

        # TODO: Remove from here...
        assert self.device_class == SensorDeviceClass.CO2
        assert self.native_unit_of_measurement == CONCENTRATION_PARTS_PER_MILLION

        if not isinstance(self._device, HvacCarbonDioxideSensor):
            raise TypeError(f"Cannot set CO2 level on {self._device}")
        # TODO: Until here

        # setter will raise an exception if device is not faked
        self._device.co2_level = co2_level  # would accept None

    @callback
    def async_put_dhw_temp(self, temperature: float) -> None:
        """Cast the DHW cylinder temperature (if faked)."""

        # TODO: Remove from here...
        assert self.device_class == SensorDeviceClass.TEMPERATURE
        assert self.native_unit_of_measurement == UnitOfTemperature.CELSIUS

        if not isinstance(self._device, DhwSensor):
            raise TypeError(f"Cannot set CO2 level on {self._device}")
        # TODO: Until here

        # setter will raise an exception if device is not faked
        self._device.temperature = temperature  # would accept None

    @callback
    def async_put_indoor_humidity(self, indoor_humidity: float) -> None:
        """Cast the indoor humidity level (if faked)."""

        # TODO: Remove from here...
        assert self.device_class == SensorDeviceClass.HUMIDITY
        assert self.native_unit_of_measurement == PERCENTAGE

        if not isinstance(self._device, HvacHumiditySensor):
            raise TypeError(f"Cannot set indoor humidity level on {self._device}")
        # TODO: Until here

        # setter will raise an exception if device is not faked
        self._device.indoor_humidity = indoor_humidity / 100  # would accept None

    @callback
    def async_put_room_temp(self, temperature: float) -> None:
        """Cast the room temperature (if faked)."""

        # TODO: Remove from here...
        assert self.device_class == SensorDeviceClass.TEMPERATURE
        assert self.native_unit_of_measurement == UnitOfTemperature.CELSIUS

        if not isinstance(self._device, Thermostat):
            raise TypeError(f"Cannot set CO2 level on {self._device}")
        # TODO: Until here

        # setter will raise an exception if device is not faked
        self._device.temperature = temperature  # would accept None


@dataclass(frozen=True, kw_only=True)
class RamsesSensorEntityDescription(RamsesEntityDescription, SensorEntityDescription):
    """Class describing Ramses binary sensor entities."""

    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT

    # integration-specific attributes
    ramses_cc_class: type[RamsesSensor] = RamsesSensor
    ramses_cc_icon_off: str | None = None  # no SensorEntityDescription.icon_off attr
    ramses_rf_attr: str = None  # type: ignore[assignment]
    ramses_rf_class: type[RamsesRFEntity] | UnionType = RamsesRFEntity

    def __post_init__(self) -> None:
        """Default values for descriptor attrs.

        Is a convenience to avoid having to specify the values in the DESCRIPTOR table.
        """

        # HACK: may not be acceptible to HA core devs (should just complete the table)
        object.__setattr__(self, "ramses_rf_attr", self.ramses_rf_attr or self.key)
        object.__setattr__(
            self, "ramses_cc_class", self.ramses_cc_class or RamsesSensor
        )


SENSOR_DESCRIPTIONS: tuple[RamsesSensorEntityDescription, ...] = (
    RamsesSensorEntityDescription(
        key=SZ_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        ramses_rf_class=HvacHumiditySensor | TrvActuator,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        ramses_cc_extra_attributes={
            ATTR_SETPOINT: SZ_SETPOINT,
        },
    ),
    RamsesSensorEntityDescription(
        key=SZ_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        ramses_rf_class=DhwSensor | OutSensor | Thermostat,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
        ramses_cc_extra_attributes={
            ATTR_SETPOINT: SZ_SETPOINT,
        },
    ),
    RamsesSensorEntityDescription(
        key=SZ_DEWPOINT_TEMP,
        name="Dewpoint temperature",
        icon="mdi:water-thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        ramses_rf_class=HvacHumiditySensor,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_HEAT_DEMAND,
        name="Heat demand",
        icon="mdi:radiator",
        ramses_cc_icon_off="mdi:radiator-off",
        ramses_rf_class=OtbGateway,
        native_unit_of_measurement=PERCENTAGE,
    ),
    RamsesSensorEntityDescription(  # not OtbGateway
        key=SZ_HEAT_DEMAND,
        name="Heat demand",
        icon="mdi:radiator",
        ramses_cc_icon_off="mdi:radiator-off",
        ramses_rf_class=System | TrvActuator | UfhController | ZoneBase,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_RELAY_DEMAND,
        name="Relay demand",
        icon="mdi:power-plug",
        ramses_cc_icon_off="mdi:power-plug-off",
        native_unit_of_measurement=PERCENTAGE,
    ),
    RamsesSensorEntityDescription(
        key=f"{SZ_RELAY_DEMAND}_fa",
        name="Relay demand (FA)",
        icon="mdi:power-plug",
        ramses_cc_icon_off="mdi:power-plug-off",
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
    RamsesSensorEntityDescription(
        key=SZ_BOILER_OUTPUT_TEMP,
        name="Boiler output temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_BOILER_RETURN_TEMP,
        name="Boiler return temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_BOILER_SETPOINT,
        name="Boiler setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_CH_SETPOINT,
        name="CH setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_CH_MAX_SETPOINT,
        name="CH max setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_CH_WATER_PRESSURE,
        name="CH water pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
    ),
    RamsesSensorEntityDescription(
        key=SZ_DHW_FLOW_RATE,
        name="DHW flow rate",
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
    ),
    RamsesSensorEntityDescription(
        key=SZ_DHW_SETPOINT,
        name="DHW setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_DHW_TEMP,
        name="DHW temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_OUTSIDE_TEMP,
        name="Outside temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_REL_MODULATION_LEVEL,
        name="Relative modulation level",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_MAX_REL_MODULATION,
        name="Max relative modulation level",
        native_unit_of_measurement=PERCENTAGE,
    ),
    # HVAC (mostly ventilation units)
    RamsesSensorEntityDescription(
        key=SZ_AIR_QUALITY,
        name="Air quality",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_AIR_QUALITY_BASIS,
        name="Air quality basis",
        native_unit_of_measurement=PERCENTAGE,
    ),
    RamsesSensorEntityDescription(
        key=SZ_CO2_LEVEL,
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_EXHAUST_FAN_SPEED,
        name="Exhaust fan speed",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_EXHAUST_FLOW,
        name="Exhaust flow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_SECOND,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_EXHAUST_TEMP,
        name="Exhaust temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_FAN_INFO,
        name="Fan info",
        state_class=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_FILTER_REMAINING,
        name="Filter remaining",
        native_unit_of_measurement=UnitOfTime.DAYS,
    ),
    RamsesSensorEntityDescription(
        key=SZ_INDOOR_HUMIDITY,
        name="Indoor humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_INDOOR_TEMP,
        name="Indoor temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_OUTDOOR_HUMIDITY,
        name="Outdoor humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_OUTDOOR_TEMP,
        name="Outdoor temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_POST_HEAT,
        name="Post heat",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_PRE_HEAT,
        name="Pre heat",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_REMAINING_MINS,
        name="Remaining time",
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    RamsesSensorEntityDescription(
        key=SZ_SPEED_CAPABILITIES,
        name="Speed cap",
        native_unit_of_measurement="units",
    ),
    RamsesSensorEntityDescription(
        key=SZ_SUPPLY_FAN_SPEED,
        name="Supply fan speed",
        native_unit_of_measurement=PERCENTAGE,
    ),
    RamsesSensorEntityDescription(
        key=SZ_SUPPLY_FLOW,
        name="Supply flow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_SECOND,
        entity_category=None,
    ),
    RamsesSensorEntityDescription(
        key=SZ_SUPPLY_TEMP,
        name="Supply temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=None,
    ),
    # Special projects
    RamsesSensorEntityDescription(
        key=SZ_OEM_CODE,
        name="OEM code",
        ramses_rf_class=OtbGateway,
        state_class=None,
        entity_registry_enabled_default=False,
    ),
    RamsesSensorEntityDescription(
        key="percent",
        name="Percent",
        ramses_rf_class=OtbGateway,
        icon="mdi:power-plug",
        ramses_cc_icon_off="mdi:power-plug-off",
        native_unit_of_measurement=PERCENTAGE,
        entity_registry_enabled_default=False,
    ),
    RamsesSensorEntityDescription(
        key="value",
        name="Value",
        ramses_rf_class=OtbGateway,
        native_unit_of_measurement="units",
        entity_registry_enabled_default=False,
    ),
)
