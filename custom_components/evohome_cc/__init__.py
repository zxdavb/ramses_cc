#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

from datetime import timedelta
import logging
from typing import Any, Dict, Optional

import serial
import voluptuous as vol

try:
    from . import evohome_rf
except (ImportError, ModuleNotFoundError):
    import evohome_rf


from homeassistant.const import CONF_SCAN_INTERVAL, TEMP_CELSIUS
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import (
    __version__,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    BINARY_SENSOR_ATTRS,
    SENSOR_ATTRS,
)

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)  # TODO: remove for production

BROKER = "broker"

SCAN_INTERVAL_DEFAULT = timedelta(seconds=300)
SCAN_INTERVAL_MINIMUM = timedelta(seconds=10)

CONF_SERIAL_PORT = "serial_port"
CONF_CONFIG = "config"
CONF_SCHEMA = "schema"
CONF_GATEWAY_ID = "gateway_id"
CONF_PACKET_LOG = "packet_log"
CONF_MAX_ZONES = "max_zones"

CONF_ALLOW_LIST = "allow_list"
CONF_BLOCK_LIST = "block_list"
LIST_MSG = f"{CONF_ALLOW_LIST} and {CONF_BLOCK_LIST} are mutally exclusive"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                # vol.Optional(CONF_GATEWAY_ID): vol.Match(r"^18:[0-9]{6}$"),
                vol.Required(CONF_SERIAL_PORT): cv.string,
                vol.Optional("serial_config"): dict,
                vol.Required(CONF_CONFIG): vol.Schema(
                    {
                        vol.Optional(CONF_MAX_ZONES, default=12): vol.Any(None, int),
                        vol.Optional(CONF_PACKET_LOG): cv.string,
                        vol.Optional("enforce_allowlist"): bool,
                    }
                ),
                vol.Optional(CONF_SCHEMA): dict,
                vol.Exclusive(CONF_ALLOW_LIST, "device_filter", msg=LIST_MSG): list,
                vol.Exclusive(CONF_BLOCK_LIST, "device_filter", msg=LIST_MSG): list,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
            },
            extra=vol.ALLOW_EXTRA,  # TODO: remove for production
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def new_binary_sensors(broker) -> list:
    sensors = [
        s
        for s in broker.client.evo.devices + [broker.client.evo]
        if any([hasattr(s, a) for a in BINARY_SENSOR_ATTRS])
    ]
    return [s for s in sensors if s not in broker.binary_sensors]


def new_sensors(broker) -> list:
    sensors = [
        s
        for s in broker.client.evo.devices + [broker.client.evo]
        if any([hasattr(s, a) for a in SENSOR_ATTRS])
    ]
    return [s for s in sensors if s not in broker.sensors]


async def async_setup(hass: HomeAssistantType, hass_config: ConfigType) -> bool:
    """xxx."""

    async def load_system_config(store) -> Optional[Dict]:
        app_storage = await store.async_load()
        return dict(app_storage if app_storage else {})

    if __version__ == evohome_rf.__version__:
        _LOGGER.warning(
            "evohome_cc v%s, using evohome_rf v%s - versions match (this is good)",
            __version__,
            evohome_rf.__version__,
        )
    else:
        _LOGGER.error(
            "evohome_cc v%s, using evohome_rf v%s - versions don't match (this is bad)",
            __version__,
            evohome_rf.__version__,
        )

    store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
    evohome_store = await load_system_config(store)

    _LOGGER.debug("Store = %s, Config =  %s", evohome_store, hass_config[DOMAIN])

    kwargs = dict(hass_config[DOMAIN])
    serial_port = kwargs.pop(CONF_SERIAL_PORT)
    kwargs["allowlist"] = dict.fromkeys(kwargs.pop(CONF_ALLOW_LIST, []), {})
    kwargs["blocklist"] = dict.fromkeys(kwargs.pop(CONF_BLOCK_LIST, []), {})
    kwargs["config"]["log_rotate_backups"] = (
        kwargs["config"].pop("log_rotate_backups", 7)
    )

    try:  # TODO: test invalid serial_port="AA"
        client = evohome_rf.Gateway(serial_port, loop=hass.loop, **kwargs)
    except serial.SerialException as exc:
        _LOGGER.exception("Unable to open serial port. Message is: %s", exc)
        return False

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN][BROKER] = broker = EvoBroker(
        hass, client, store, hass_config[DOMAIN]
    )

    broker.hass_config = hass_config

    # #roker.loop_task = hass.async_create_task(client.start())
    broker.loop_task = hass.loop.create_task(client.start())

    hass.helpers.event.async_track_time_interval(
        broker.update, hass_config[DOMAIN][CONF_SCAN_INTERVAL]
    )

    return True


class EvoBroker:
    """Container for client and data."""

    def __init__(self, hass, client, store, params) -> None:
        """Initialize the client and its data structure(s)."""
        self.hass = hass
        self.client = client
        self._store = store
        self.params = params

        self.config = None
        self.status = None

        self.binary_sensors = []
        self.climates = []
        self.water_heater = None
        self.sensors = []

        self.hass_config = None
        self.loop_task = None

    async def save_system_config(self) -> None:
        """Save..."""
        app_storage = {}

        await self._store.async_save(app_storage)

    async def update(self, *args, **kwargs) -> None:
        """Retrieve the latest state data..."""

        #     self.hass.async_create_task(self._update(self.hass, *args, **kwargs))

        # async def _update(self, *args, **kwargs) -> None:
        #     """Retrieve the latest state data..."""

        evohome = self.client.evo
        _LOGGER.debug("Schema = %s", evohome.schema if evohome is not None else None)
        if evohome is None:
            return

        if [z for z in evohome.zones if z not in self.climates]:
            self.hass.async_create_task(
                async_load_platform(self.hass, "climate", DOMAIN, {}, self.hass_config)
            )

        if evohome.dhw and self.water_heater is None:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, "water_heater", DOMAIN, {}, self.hass_config
                )
            )

        if new_sensors(self):
            self.hass.async_create_task(
                async_load_platform(self.hass, "sensor", DOMAIN, {}, self.hass_config)
            )

        if new_binary_sensors(self):
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, "binary_sensor", DOMAIN, {}, self.hass_config
                )
            )

        _LOGGER.debug("Params = %s", evohome.params)
        _LOGGER.debug("Status = %s", evohome.status)

        # inform the evohome devices that state data has been updated
        self.hass.helpers.dispatcher.async_dispatcher_send(DOMAIN)


class EvoEntity(Entity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize the entity."""
        self._evo_device = evo_device
        self._evo_broker = evo_broker

        self._unique_id = self._name = None
        self._device_state_attrs = {}

    @callback
    def _refresh(self) -> None:
        self.async_schedule_update_ha_state(force_refresh=True)

    @property
    def should_poll(self) -> bool:
        """Entities should not be polled."""
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        # result = {}
        # for attr in ("schema", "config", "status"):
        #     if hasattr(self._evo_device, attr):
        #         result.update({attr: getattr(self._evo_device, attr)})
        return {
            "controller": self._evo_device._ctl.id if self._evo_device._ctl else None
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(DOMAIN, self._refresh)


class EvoDeviceBase(EvoEntity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._evo_device._is_present

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            # "domain_id": self._evo_device. self._domain_id,
            # "zone_name": self._evo_device.zone.name if self._evo_device.zone else None,
        }


class EvoZoneBase(EvoEntity):
    """Base for any evohome RF-compatible entity (e.g. Climate, Sensor)."""

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._evo_device.temperature

    @property
    def name(self) -> str:
        return self._evo_device.name

    @property
    def supported_features(self) -> int:
        """Return the list of supported features."""
        return self._supported_features

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement used by the platform."""
        return TEMP_CELSIUS

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().device_state_attributes,
            # "zone_idx": self._evo_device.idx,
            # "zone_name": self._evo_device.zone.name if self._evo_device.zone else None,
        }
