#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for sensors.
"""

import logging
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    TEMP_CELSIUS,
    TIME_MINUTES,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

#
from ramses_rf.protocol.const import (
    SZ_AIR_QUALITY,
    SZ_AIR_QUALITY_BASE,
    SZ_BYPASS_POSITION,
    SZ_CO2_LEVEL,
    SZ_EXHAUST_FAN_SPEED,
    SZ_EXHAUST_FLOW,
    SZ_EXHAUST_TEMPERATURE,
    SZ_FAN_INFO,
    SZ_INDOOR_HUMIDITY,
    SZ_INDOOR_TEMPERATURE,
    SZ_OUTDOOR_HUMIDITY,
    SZ_OUTDOOR_TEMPERATURE,
    SZ_POST_HEAT,
    SZ_PRE_HEAT,
    SZ_REMAINING_TIME,
    SZ_SPEED_CAP,
    SZ_SUPPLY_FAN_SPEED,
    SZ_SUPPLY_FLOW,
    SZ_SUPPLY_TEMPERATURE,
)

from . import EvoDeviceBase
from .const import ATTR_SETPOINT, BROKER, DOMAIN, VOLUME_FLOW_RATE_LITERS_PER_MINUTE

SENSOR_KEY_TEMPERATURE = "temperature"

SENSOR_DESCRIPTION_TEMPERATURE = SensorEntityDescription(
    key=SENSOR_KEY_TEMPERATURE,
    name="Temperature",
    device_class=SensorDeviceClass.TEMPERATURE,
    native_unit_of_measurement=TEMP_CELSIUS,
    state_class=SensorStateClass.MEASUREMENT,
)
# sensor.entity_description = SENSOR_DESCRIPTION_TEMPERATURE

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Set up the sensor entities.

    discovery_info keys:
      gateway: is the ramses_rf protocol stack (gateway/protocol/transport/serial)
      devices: heat (e.g. CTL, OTB, BDR, TRV) or hvac (e.g. FAN, CO2, SWI)
      domains: TCS, DHW and Zones
    """

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    new_sensors = [
        v.get(ENTITY_CLASS, EvoSensor)(broker, device, k, **v)
        for device in discovery_info.get("devices", [])
        for k, v in SENSOR_ATTRS.items()
        if hasattr(device, k)
    ]  # and (not device._is_faked or device["fakable"])
    new_sensors += [
        v.get(ENTITY_CLASS, EvoSensor)(broker, device, f"{k}_ot", **v)
        for device in discovery_info.get("devices", [])
        for k, v in SENSOR_ATTRS_HEAT.items()
        if device._SLUG == "OTB" and hasattr(device, f"{k}_ot")
    ]
    new_sensors += [
        v.get(ENTITY_CLASS, EvoSensor)(broker, domain, k, **v)
        for domain in discovery_info.get("domains", [])
        for k, v in SENSOR_ATTRS_HEAT.items()
        if k == "heat_demand" and hasattr(domain, k)
    ]

    async_add_entities(new_sensors)


class EvoSensor(EvoDeviceBase, SensorEntity):
    """Representation of a generic sensor."""

    # _attr_state_class = SensorStateClass.MEASUREMENT  # oem_code is not a measurement

    def __init__(
        self,
        broker,
        device,
        state_attr,
        attr_name=None,
        device_id=None,
        device_class=None,
        device_units=None,
        **kwargs,
    ) -> None:
        """Initialize a sensor."""
        attr_name = attr_name or state_attr
        device_id = device_id or device.id

        _LOGGER.info("Creating a Sensor (%s) for %s", attr_name, device_id)

        super().__init__(
            broker,
            device,
            device_id,
            attr_name,
            state_attr,
            device_class,
        )

        self._unit_of_measurement = device_units  # or PERCENTAGE

    @property
    def state(self) -> Optional[Any]:  # int or float
        """Return the state of the sensor."""
        state = getattr(self._device, self._state_attr)
        if self.unit_of_measurement == PERCENTAGE:
            return None if state is None else state * 100
        # if self.unit_of_measurement == TEMP_CELSIUS:
        #     return None if state is None else int(state * 200) / 200
        return state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement of the sensor."""
        return self._unit_of_measurement


class EvoHeatDemand(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:radiator-off" if self.state == 0 else "mdi:radiator"


class EvoModLevel(EvoSensor):
    """Representation of a heat demand sensor."""

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().extra_state_attributes

        if self._state_attr[-3:] == "_ot":
            attrs.update(self._device.opentherm_status)
        else:
            attrs.update(self._device.ramses_status)
        attrs.pop("rel_modulation_level")

        return attrs


class EvoRelayDemand(EvoSensor):
    """Representation of a relay demand sensor."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:power-plug" if self.state else "mdi:power-plug-off"


class EvoTemperature(EvoSensor):
    """Representation of a temperature sensor (incl. DHW sensor)."""

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = super().extra_state_attributes
        if hasattr(self._device, ATTR_SETPOINT):
            attrs[ATTR_SETPOINT] = self._device.setpoint
        return attrs


class EvoFaultLog(EvoDeviceBase):
    """Representation of a system's fault log."""

    # DEVICE_CLASS = DEVICE_CLASS_PROBLEM
    DEVICE_UNITS = "entries"

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device, None, None)  # TODO

        self._fault_log = None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._device._fault_log._fault_log_done

    @property
    def state(self) -> int:
        """Return the number of issues."""
        return len(self._fault_log)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the device state attributes."""
        return {
            **super().extra_state_attributes,
            "fault_log": self._device._fault_log,
        }

    async def async_update(self) -> None:
        """Process the sensor's state data."""
        # self._fault_log = self._device.fault_log()  # TODO: needs sorting out
        pass


DEVICE_CLASS = "device_class"
DEVICE_UNITS = "device_units"
ENTITY_CLASS = "entity_class"

SENSOR_ATTRS_HEAT = {
    # Special projects
    "oem_code": {  # 3220/73
        DEVICE_UNITS: None,
    },
    "percent": {  # 2401
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoRelayDemand,
    },
    "value": {  # 2401
        DEVICE_UNITS: "units",
    },
    # SENSOR_ATTRS_BDR = {  # incl: actuator
    "relay_demand": {  # 0008
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoRelayDemand,
    },
    "relay_demand_fa": {  # 0008
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoRelayDemand,
    },
    "modulation_level": {  # 3EF0/3EF1
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoModLevel,
    },
    # SENSOR_ATTRS_OTB = {  # excl. actuator
    "boiler_output_temp": {  # 3200, 3220|19
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "boiler_return_temp": {  # 3210, 3220|1C
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "boiler_setpoint": {  # 22D9, 3220|01
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "ch_max_setpoint": {  # 1081, 3220|39
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "ch_setpoint": {  # 3EF0
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "ch_water_pressure": {  # 1300, 3220|12
        DEVICE_CLASS: SensorDeviceClass.PRESSURE,
        DEVICE_UNITS: "bar",
    },
    "dhw_flow_rate": {  # 12F0, 3220|13
        DEVICE_UNITS: VOLUME_FLOW_RATE_LITERS_PER_MINUTE,
    },
    "dhw_setpoint": {  # 10A0, 3220|38
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "dhw_temp": {  # 1290, 3220|1A
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "max_rel_modulation": {  # 3200|0E
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoModLevel,
    },
    "outside_temp": {  # 1290, 3220|1B
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    "rel_modulation_level": {  # 3EFx, 3200|11
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoModLevel,
    },
    # SENSOR_ATTRS_OTH = {
    "heat_demand": {  # 3150
        DEVICE_UNITS: PERCENTAGE,
        ENTITY_CLASS: EvoHeatDemand,
    },
    "temperature": {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
        ENTITY_CLASS: EvoTemperature,
        "fakable": True,
    },
}

SENSOR_ATTRS_HVAC = {
    # "boost_timer": {DEVICE_UNITS: TIME_MINUTES,},
    # "fan_rate":    {DEVICE_UNITS: PERCENTAGE,},
    SZ_AIR_QUALITY: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_AIR_QUALITY_BASE: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_BYPASS_POSITION: {
        DEVICE_UNITS: "units",
    },
    SZ_CO2_LEVEL: {
        DEVICE_CLASS: SensorDeviceClass.CO2,
        DEVICE_UNITS: CONCENTRATION_PARTS_PER_MILLION,
    },
    SZ_EXHAUST_FAN_SPEED: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_EXHAUST_FLOW: {
        DEVICE_UNITS: None,
    },
    SZ_EXHAUST_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_FAN_INFO: {
        DEVICE_UNITS: None,
    },
    SZ_INDOOR_HUMIDITY: {
        DEVICE_CLASS: SensorDeviceClass.HUMIDITY,
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_INDOOR_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_OUTDOOR_HUMIDITY: {
        DEVICE_CLASS: SensorDeviceClass.HUMIDITY,
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_OUTDOOR_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
    SZ_POST_HEAT: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_PRE_HEAT: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_REMAINING_TIME: {
        DEVICE_UNITS: TIME_MINUTES,
    },
    SZ_SPEED_CAP: {
        DEVICE_UNITS: "units",
    },
    SZ_SUPPLY_FAN_SPEED: {
        DEVICE_UNITS: PERCENTAGE,
    },
    SZ_SUPPLY_FLOW: {
        DEVICE_UNITS: None,
    },
    SZ_SUPPLY_TEMPERATURE: {
        DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        DEVICE_UNITS: TEMP_CELSIUS,
    },
}

SENSOR_ATTRS = SENSOR_ATTRS_HEAT | SENSOR_ATTRS_HVAC
