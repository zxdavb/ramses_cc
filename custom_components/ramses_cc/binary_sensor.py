#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import EvoDeviceBase
from .const import ATTR_BATTERY_LEVEL, BROKER, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Set up the binary sensor entities."""

    if discovery_info is None:
        return

    devices = [
        v.get(ENTITY_CLASS, EvoBinarySensor)(hass.data[DOMAIN][BROKER], device, k, **v)
        for device in discovery_info.get("devices", [])
        for k, v in BINARY_SENSOR_ATTRS["devices"].items()
        if hasattr(device, k)
    ]

    domains = [
        v.get(ENTITY_CLASS, EvoBinarySensor)(hass.data[DOMAIN][BROKER], domain, k, **v)
        for domain in discovery_info.get("domains", [])
        for k, v in BINARY_SENSOR_ATTRS["devices"].items()
        if k == "window_open" and hasattr(domain, k)
    ]

    systems = [
        v.get(ENTITY_CLASS, EvoBinarySensor)(
            hass.data[DOMAIN][BROKER], ctl.tcs, k, **v
        )
        for ctl in discovery_info.get("devices", [])
        for k, v in BINARY_SENSOR_ATTRS["systems"].items()
        if hasattr(ctl, "_tcs") and hasattr(ctl.tcs, k)
    ]

    gateway = (
        []
        if not discovery_info.get("gateway")
        else [
            EvoGateway(
                hass.data[DOMAIN][BROKER],
                discovery_info["gateway"],
                None,
                attr_name="gateway",
                device_class=BinarySensorDeviceClass.PROBLEM,
            )
        ]
    )

    async_add_entities(devices + domains + systems + gateway)


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


class EvoFaultLog(EvoBinarySensor):
    """Representation of a system (a controller)."""

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self._device._msgs.get("0418"):
            return dt.now() - msg.dtm < td(seconds=1200)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "active_fault": self._device.tcs.active_fault,
            "latest_event": self._device.tcs.latest_event,
            "latest_fault": self._device.tcs.latest_fault,
        }

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the controller has a fault"""
        return bool(self._device.tcs.active_fault)


class EvoSystem(EvoBinarySensor):
    """Representation of a system (a controller)."""

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self._device._msgs.get("1F09"):
            return dt.now() - msg.dtm < td(seconds=msg.payload["remaining_seconds"] * 3)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "schema": self._device.tcs.schema,
        }

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the controller has been seen recently."""
        return self.available


class EvoGateway(EvoBinarySensor):
    """Representation of a gateway (a HGI80)."""

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return bool(self._device._gwy.pkt_protocol._hgi80.get("device_id"))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""

        # {% set device_id = state_attr("binary_sensor.01_145038_active_fault", "active_fault")[5] %}
        # {% for state in state_attr("binary_sensor.18_140805_gateway", "known_list") %}
        #   {%- if device_id in state %}{{ state[device_id].get('class') }}{% endif %}
        # {%- endfor -%}

        def shrink(device_hints) -> dict:
            result = device_hints
            for key in ("alias", "class", "faked"):
                if (value := result.pop(key, None)) is not None:
                    result[key] = value
            return result

        gwy = self._device._gwy
        return {
            "schema": gwy.tcs._schema_min if gwy.tcs else {},
            "config": {"enforce_known_list": gwy.config.enforce_known_list},
            "known_list": [{k: shrink(v)} for k, v in gwy._include.items()],
            "block_list": [{k: shrink(v)} for k, v in gwy._exclude.items()],
            "other_list": sorted(gwy.pkt_protocol._unwanted),
            "_is_evofw3": gwy.pkt_protocol._hgi80["is_evofw3"],
        }

    @property
    def is_on(self) -> Optional[bool]:
        """Return True if the controller has been seen recently."""
        if msg := self._device._gwy.msg_protocol._this_msg:
            return dt.now() - msg.dtm > td(seconds=300)


DEVICE_CLASS = "device_class"
ENTITY_CLASS = "entity_class"
STATE_ICONS = "state_icons"  # TBA

BINARY_SENSOR_ATTRS = {
    "systems": {
        "active_fault": {
            ENTITY_CLASS: EvoFaultLog,
            DEVICE_CLASS: BinarySensorDeviceClass.PROBLEM,
        },  # CTL
        "schema": {
            ENTITY_CLASS: EvoSystem,
        },  # CTL
    },
    "devices": {
        # Special projects
        "bit_2_4": {},
        "bit_2_5": {},
        "bit_2_6": {},
        "bit_2_7": {},
        "fault_present": {
            DEVICE_CLASS: BinarySensorDeviceClass.PROBLEM,
        },  # OTB
        # Standard sensors
        "battery_low": {
            DEVICE_CLASS: BinarySensorDeviceClass.BATTERY,
            ENTITY_CLASS: EvoBattery,
        },
        "active": {
            ENTITY_CLASS: EvoActuator,
            STATE_ICONS: ("mdi:electric-switch-closed", "mdi:electric-switch"),
        },
        "window_open": {
            DEVICE_CLASS: BinarySensorDeviceClass.WINDOW,
        },
        "ch_active": {
            STATE_ICONS: ("mdi:circle-outline", "mdi:fire-circle"),
        },
        "ch_enabled": {},
        "cooling_active": {
            STATE_ICONS: ("mdi:snowflake", "mdi:snowflake-off"),
        },
        "cooling_enabled": {},
        "dhw_active": {},
        "dhw_enabled": {},
        "flame_active": {
            STATE_ICONS: ("mdi:circle-outline", "mdi:fire-circle"),
        },
        "bit_3_7": {},
        "bit_6_6": {},
    },
    "domains": {
        "window_open": {
            DEVICE_CLASS: BinarySensorDeviceClass.WINDOW,
        },
    },
}
