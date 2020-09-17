"""Support for Honeywell's evohome II RF protocol.

Requires a Honeywell HGI80 (or compatible) gateway.
"""
from datetime import timedelta
import logging
from typing import Any, Dict, Optional

import serial
import evohome
import voluptuous as vol

from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    TEMP_CELSIUS,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import (
    ATTR_BATTERY,
    ATTR_HEAT_DEMAND,
    DOMAIN,
    STORAGE_KEY,
    STORAGE_VERSION,
    DEVICE_HAS_BINARY_SENSOR,
    DEVICE_HAS_SENSOR,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL_DEFAULT = timedelta(seconds=300)
SCAN_INTERVAL_MINIMUM = timedelta(seconds=10)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("serial_port"): cv.string,
                vol.Required("packet_log"): cv.string,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=SCAN_INTERVAL_DEFAULT
                ): vol.All(cv.time_period, vol.Range(min=SCAN_INTERVAL_MINIMUM)),
                vol.Optional("schema"): dict,
                vol.Optional("allowlist"): list,
                vol.Optional("blocklist"): list,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistantType, hass_config: ConfigType) -> bool:
    """xxx."""

    async def load_system_config(store) -> Optional[Dict]:
        app_storage = await store.async_load()
        return dict(app_storage if app_storage else {})

    store = hass.helpers.storage.Store(STORAGE_VERSION, STORAGE_KEY)
    evohome_store = await load_system_config(store)

    _LOGGER.debug("Store = %s, Config =  %s", evohome_store, hass_config[DOMAIN])

    # import ptvsd  # pylint: disable=import-error
    # _LOGGER.warning("Waiting for debugger to attach...")
    # ptvsd.enable_attach(address=("172.27.0.138", 5679))

    # ptvsd.wait_for_attach()
    # _LOGGER.debug("Debugger is attached!")

    kwargs = dict(hass_config[DOMAIN])
    serial_port = kwargs.pop("serial_port")
    kwargs["blocklist"] = dict.fromkeys(kwargs.pop("blocklist"), {})

    try:  # TODO: test invalid serial_port="AA"
        client = evohome.Gateway(serial_port, loop=hass.loop, **kwargs)
    except serial.SerialException as exc:
        _LOGGER.exception("Unable to open serial port. Message is: %s", exc)
        return False

    hass.data[DOMAIN] = {}
    hass.data[DOMAIN]["broker"] = broker = EvoBroker(
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
        """Retreive the latest state data..."""

        #     self.hass.async_create_task(self._update(self.hass, *args, **kwargs))

        # async def _update(self, *args, **kwargs) -> None:
        #     """Retreive the latest state data..."""

        evohome = self.client.evo
        _LOGGER.warning("Schema = %s", evohome.schema if evohome is not None else None)
        if evohome is None:
            return

        if [z for z in evohome.zones if z not in self.climates]:
            self.hass.async_create_task(
                async_load_platform(self.hass, "climate", DOMAIN, {}, self.hass_config)
            )

        # if evohome.dhw and self.water_heater is None:
        #     self.hass.async_create_task(
        #         async_load_platform(
        #             self.hass, "water_heater", DOMAIN, {}, self.hass_config
        #         )
        #     )

        if [
            d
            for d in evohome.devices
            if d not in self.sensors and d.type in DEVICE_HAS_SENSOR
        ]:
            self.hass.async_create_task(
                async_load_platform(self.hass, "sensor", DOMAIN, {}, self.hass_config)
            )

        if [
            d
            for d in evohome.devices
            if d not in self.binary_sensors and d.type in DEVICE_HAS_BINARY_SENSOR
        ]:
            self.hass.async_create_task(
                async_load_platform(
                    self.hass, "binary_sensor", DOMAIN, {}, self.hass_config
                )
            )

        _LOGGER.warning("Params = %s", evohome.params)
        _LOGGER.warning("Status = %s", evohome.status)

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
        return {"state": self._device_state_attrs}

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self.hass.helpers.dispatcher.async_dispatcher_connect(DOMAIN, self._refresh)


class EvoDevice(EvoEntity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    @property
    def device_class(self) -> str:
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "zone_idx": self._evo_device.zone.idx if self._evo_device.zone else None,
            "zone_name": self._evo_device.zone.name if self._evo_device.zone else None,
        }


class EvoZone(EvoEntity):
    """Base for any evohome II-compatible entity (e.g. Climate, Sensor)."""

    @property
    def device_state_attributes(self) -> Dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            "heating_type": self._evo_device.heating_type,
            "zone_config": self._evo_device.zone_config,
        }
