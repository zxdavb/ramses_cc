#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Provides support for binary sensors.
"""
from __future__ import annotations

import logging
from datetime import datetime as dt
from datetime import timedelta as td
from typing import Any

from homeassistant.components.binary_sensor import DOMAIN as PLATFORM
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

#
from ramses_rf.device.heat import (
    SZ_CH_ACTIVE,
    SZ_CH_ENABLED,
    SZ_COOLING_ACTIVE,
    SZ_COOLING_ENABLED,
    SZ_DHW_ACTIVE,
    SZ_DHW_ENABLED,
    SZ_FAULT_PRESENT,
    SZ_FLAME_ACTIVE,
)
from ramses_rf.protocol.const import SZ_BYPASS_POSITION

from . import RamsesDeviceBase
from .const import ATTR_BATTERY_LEVEL, BROKER, DOMAIN
from .helpers import migrate_to_ramses_rf
from .schemas import SVCS_BINARY_SENSOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create binary sensors for CH/DHW (heat) & HVAC.

    discovery_info keys:
      gateway: is the ramses_rf protocol stack (gateway/protocol/transport/serial)
      devices: heat (e.g. CTL, OTB, BDR, TRV) or hvac (e.g. FAN, CO2, SWI)
      domains: TCS, DHW and Zones
    """

    def entity_factory(broker, device, attr, *, entity_class=None, **kwargs):
        migrate_to_ramses_rf(hass, PLATFORM, f"{device.id}-{attr}")
        return (entity_class or RamsesBinarySensor)(broker, device, attr, **kwargs)

    if discovery_info is None:
        return

    broker = hass.data[DOMAIN][BROKER]

    new_sensors = [
        entity_factory(broker, dev, k, **v)
        for k, v in BINARY_SENSOR_ATTRS["gateway"].items()
        if (dev := discovery_info.get("gateway"))
    ]  # 18:xxxxxx - status
    new_sensors += [
        entity_factory(broker, dev, k, **v)
        for key in ("devices", "domains")
        for dev in discovery_info.get(key, [])
        for k, v in BINARY_SENSOR_ATTRS[key].items()
        if dev and hasattr(dev, k)
    ]
    # TODO: has a bug:
    # Traceback (most recent call last):
    # File "/usr/src/homeassistant/homeassistant/helpers/entity_platform.py", line 249, in _async_setup_platform
    #     await asyncio.shield(task)
    # File "/config/custom_components/ramses_cc/binary_sensor.py", line 64, in async_setup_platform
    #     new_sensors += [
    # File "/config/custom_components/ramses_cc/binary_sensor.py", line 68, in <listcomp>
    #     if getattr(tcs, "tcs") is tcs
    # AttributeError: 'NoneType' object has no attribute 'tcs'
    new_sensors += [
        entity_factory(broker, dev, k, **v)
        for dev in discovery_info.get("domains", [])  # not "devices"
        for k, v in BINARY_SENSOR_ATTRS["systems"].items()
        if dev and getattr(dev, "tcs") is dev  # HACK
    ]  # 01:xxxxxx - active_fault, schema

    async_add_entities(new_sensors)

    if not broker._services.get(PLATFORM) and new_sensors:
        broker._services[PLATFORM] = True

        register_svc = async_get_current_platform().async_register_entity_service
        [register_svc(k, v, f"svc_{k}") for k, v in SVCS_BINARY_SENSOR.items()]


class RamsesBinarySensor(RamsesDeviceBase, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    def __init__(
        self,
        broker,  # ramses_cc broker
        device,  # ramses_rf device
        state_attr,  # key of attr_dict +/- _ot suffix
        device_class=None,  # attr_dict value
        **kwargs,  # leftover attr_dict values
    ) -> None:
        """Initialize a binary sensor."""

        _LOGGER.info("Found a Binary Sensor for %s: %s", device.id, state_attr)

        super().__init__(
            broker,
            device,
            state_attr,
            device_class=device_class,
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return getattr(self._device, self._state_attr)


class RamsesActuator(RamsesBinarySensor):
    """Representation of an actuator sensor; on means active."""

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return "mdi:electric-switch-closed" if self.is_on else "mdi:electric-switch"


class RamsesBattery(RamsesBinarySensor):
    """Representation of a low battery sensor; on means low."""

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        state = self._device.battery_state
        return {
            **super().extra_state_attributes,
            ATTR_BATTERY_LEVEL: state and state.get(ATTR_BATTERY_LEVEL),
        }


class RamsesFaultLog(RamsesBinarySensor):
    """Representation of a system (a controller)."""

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self._device._msgs.get("0418"):
            return dt.now() - msg.dtm < td(seconds=1200)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "active_fault": self._device.tcs.active_fault,
            "latest_event": self._device.tcs.latest_event,
            "latest_fault": self._device.tcs.latest_fault,
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the controller has a fault."""
        return bool(self._device.tcs.active_fault)


class RamsesSystem(RamsesBinarySensor):
    """Representation of a system (a controller)."""

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self._device._msgs.get("1F09"):
            return dt.now() - msg.dtm < td(seconds=msg.payload["remaining_seconds"] * 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "schema": self._device.tcs.schema,
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the controller has been seen recently."""
        return self.available


class RamsesGateway(RamsesBinarySensor):
    """Representation of a gateway (a HGI80)."""

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return bool(self._device._gwy.pkt_protocol._hgi80.get("device_id"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""

        # {% set device_id = state_attr("binary_sensor.01_145038_active_fault", "active_fault")[5] %}
        # {% for state in state_attr("binary_sensor.18_140805_gateway", "known_list") %}
        #   {%- if device_id in state %}{{ state[device_id].get('class') }}{% endif %}
        # {%- endfor -%}

        def shrink(device_hints) -> dict:
            return {
                k: v
                for k, v in device_hints.items()
                if k in ("alias", "class", "faked") and v not in (None, False)
            }

        gwy = self._device._gwy
        return {
            "schema": {gwy.tcs.id: gwy.tcs._schema_min} if gwy.tcs else {},
            "config": {"enforce_known_list": gwy.config.enforce_known_list},
            "known_list": [{k: shrink(v)} for k, v in gwy.known_list.items()],
            "block_list": [{k: shrink(v)} for k, v in gwy._exclude.items()],
            "other_list": sorted(
                d for d in gwy.pkt_protocol._unwanted if d not in gwy._exclude
            ),
            "_is_evofw3": gwy.pkt_protocol._hgi80["is_evofw3"],
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the controller has been seen recently."""
        if msg := self._device._gwy.msg_protocol._this_msg:
            return dt.now() - msg.dtm > td(seconds=300)


DEVICE_CLASS = "device_class"
ENTITY_CLASS = "entity_class"
STATE_ICONS = "state_icons"  # TBA

BINARY_SENSOR_ATTRS = {
    "devices": {  # the devices
        # Special projects
        "bit_2_4": {},
        "bit_2_5": {},
        "bit_2_6": {},
        "bit_2_7": {},
        "bit_3_7": {},
        "bit_6_6": {},
        SZ_FAULT_PRESENT: {
            DEVICE_CLASS: BinarySensorDeviceClass.PROBLEM,
        },  # OTB
        # Standard sensors
        "battery_low": {
            DEVICE_CLASS: BinarySensorDeviceClass.BATTERY,
            ENTITY_CLASS: RamsesBattery,
        },
        "active": {
            ENTITY_CLASS: RamsesActuator,
            STATE_ICONS: ("mdi:electric-switch-closed", "mdi:electric-switch"),
        },
        SZ_CH_ACTIVE: {
            STATE_ICONS: ("mdi:circle-outline", "mdi:fire-circle"),
        },
        SZ_CH_ENABLED: {},
        SZ_COOLING_ACTIVE: {
            STATE_ICONS: ("mdi:snowflake", "mdi:snowflake-off"),
        },
        SZ_COOLING_ENABLED: {},
        SZ_DHW_ACTIVE: {},
        SZ_DHW_ENABLED: {},
        SZ_FLAME_ACTIVE: {
            STATE_ICONS: ("mdi:circle-outline", "mdi:fire-circle"),
        },
        "window_open": {
            DEVICE_CLASS: BinarySensorDeviceClass.WINDOW,
        },
        SZ_BYPASS_POSITION: {},
    },
    "domains": {  # the non-devices: TCS, DHW, & Zones
        "window_open": {
            DEVICE_CLASS: BinarySensorDeviceClass.WINDOW,
        },
    },
    "systems": {  # the TCS specials (faults, schedule & schema)
        "active_fault": {
            ENTITY_CLASS: RamsesFaultLog,
            DEVICE_CLASS: BinarySensorDeviceClass.PROBLEM,
        },
        "schema": {
            ENTITY_CLASS: RamsesSystem,
        },
    },
    "gateway": {  # the gateway (not the HGI, which is a device)
        "status": {
            ENTITY_CLASS: RamsesGateway,
            DEVICE_CLASS: BinarySensorDeviceClass.PROBLEM,
        },
    },
}
