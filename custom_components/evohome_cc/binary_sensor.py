#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others.

Provides support for binary sensors.
"""

import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any, Dict, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from . import EvoDeviceBase, EvoEntity
from .const import ATTR_BATTERY_LEVEL, BROKER, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Set up the evohome sensor entities."""

    if discovery_info is None:
        return

    devices = [
        v.get(ENTITY_CLASS, EvoBinarySensor)(hass.data[DOMAIN][BROKER], device, k, **v)
        for device in discovery_info.get("devices", [])
        for k, v in BINARY_SENSOR_ATTRS.items()
        if device._klass != "OTB" and hasattr(device, k)
    ]

    devices += [
        v.get(ENTITY_CLASS, EvoBinarySensor)(
            hass.data[DOMAIN][BROKER], device, k, device_id=f"{device.id}_OT", **v
        )
        for device in discovery_info.get("devices", [])
        for k, v in BINARY_SENSOR_ATTRS.items()
        if device._klass == "OTB" and hasattr(device, k)
    ]

    devices += [
        v.get(ENTITY_CLASS, EvoBinarySensor)(
            hass.data[DOMAIN][BROKER], device, f"_{k}", attr_name=k, **v
        )
        for device in discovery_info.get("devices", [])
        for k, v in BINARY_SENSOR_ATTRS.items()
        if hasattr(device, f"_{k}")
    ]

    systems = [
        EvoSystem(hass.data[DOMAIN][BROKER], ctl._evo, "schema")
        for ctl in discovery_info.get("devices", [])
        if hasattr(ctl, "_evo") and ctl._is_controller
    ]

    gateway = (
        []
        if not discovery_info.get("gateway")
        else [
            EvoGateway(hass.data[DOMAIN][BROKER], discovery_info["gateway"], "config")
        ]
    )

    async_add_entities(devices + systems + gateway)


class EvoBinarySensor(EvoDeviceBase, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    #

    def __init__(
        self,
        broker,
        device,
        state_attr,
        attr_name=None,
        device_id=None,
        device_class=None,
        **kwargs,
    ) -> None:
        """Initialize a binary sensor."""
        attr_name = attr_name or state_attr
        device_id = device_id or device.id

        _LOGGER.info("Creating a Binary Sensor (%s) for %s", attr_name, device_id)

        super().__init__(
            broker,
            device,
            device_id,
            attr_name,
            state_attr,
            device_class,
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return getattr(self._device, self._state_attr)


class EvoActuator(EvoBinarySensor):
    """Representation of an actuator sensor; on means active."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:electric-switch-closed" if self.is_on else "mdi:electric-switch"


class EvoBattery(EvoBinarySensor):
    """Representation of a low battery sensor; on means low."""

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        state = self._device.battery_state
        return {
            **super().extra_state_attributes,
            ATTR_BATTERY_LEVEL: state and state.get(ATTR_BATTERY_LEVEL),
        }


class EvoSystem(EvoEntity, BinarySensorEntity):
    """Representation of a system (a controller)."""

    def __init__(self, broker, device, state_attr, **kwargs) -> None:
        """Initialize a binary sensor."""
        _LOGGER.info("Found a System (%s), id=%s", state_attr, device.id)
        super().__init__(broker, device)

        self._name = f"{device.id} (schema)"
        self._unique_id = f"{device.id}-schema"

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self._device._msgs.get("1F09"):
            return dt.now() - msg.dtm < td(seconds=msg.payload["remaining_seconds"] * 2)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "schema": self._device._evo.schema,
        }

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the controller has been seen recently."""
        return self.available

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name


class EvoGateway(EvoEntity, BinarySensorEntity):
    """Representation of a gateway (a HGI80)."""

    def __init__(self, broker, device, state_attr, **kwargs) -> None:
        """Initialize a binary sensor."""
        _LOGGER.info("Found a Gateway (%s), id=%s", state_attr, device.id)
        super().__init__(broker, device)

        self._name = f"{device.id} (config)"
        self._unique_id = f"{device.id}-config"

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        return True
        # if msgs := sorted(self._device._msgs):
        #     return dt.now() - msgs[0].dtm < td(seconds=300)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        gwy = self._device._gwy
        return {
            "schema": gwy.evo._schema_min if gwy.evo else {},
            "config": {"enforce_known_list": gwy.config.enforce_known_list},
            "known_list": [{k: v} for k, v in gwy._include.items()],
            "block_list": [{k: v} for k, v in gwy._exclude.items()],
            "other_list": sorted(gwy.pkt_protocol._unwanted),
            "_is_evofw3": gwy.pkt_protocol._hgi80["is_evofw3"],
        }

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the controller has been seen recently."""
        return self.available

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name


DEVICE_CLASS = "device_class"
ENTITY_CLASS = "entity_class"

BINARY_SENSOR_ATTRS = {
    "battery_low": {
        DEVICE_CLASS: BinarySensorDeviceClass.BATTERY,
        ENTITY_CLASS: EvoBattery,
    },
    "active": {
        ENTITY_CLASS: EvoActuator,
    },
    "window_open": {
        DEVICE_CLASS: BinarySensorDeviceClass.WINDOW,
    },
    "ch_active": {},
    "ch_enabled": {},
    "cooling_active": {},
    "cooling_enabled": {},
    "dhw_active": {},
    "dhw_enabled": {},
    "fault_present": {},
    "flame_active": {},
    # "bit_2_4": {},
    # "bit_2_5": {},
    # "bit_2_6": {},
    # "bit_2_7": {},
    "bit_3_7": {},
    "bit_6_6": {},
}
