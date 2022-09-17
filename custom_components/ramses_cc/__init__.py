#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import ramses_rf
import voluptuous as vol
from homeassistant.const import PRECISION_TENTHS, TEMP_CELSIUS, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType, HomeAssistantType

from .const import BROKER, DATA, DOMAIN, SERVICE, UNIQUE_ID
from .coordinator import RamsesCoordinator
from .schemas import (
    SCH_DOMAIN_CONFIG,
    SVC_SEND_PACKET,
    SVCS_DOMAIN,
    SVCS_DOMAIN_EVOHOME,
    SVCS_WATER_HEATER_EVOHOME,
    SZ_ADVANCED_FEATURES,
    SZ_MESSAGE_EVENTS,
)
from .version import __version__ as VERSION

_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema({DOMAIN: SCH_DOMAIN_CONFIG}, extra=vol.ALLOW_EXTRA)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]


async def async_setup(
    hass: HomeAssistant,
    hass_config: ConfigType,
) -> bool:
    """Create a ramses_rf (RAMSES_II)-based system."""

    _LOGGER.info(f"{DOMAIN} v{VERSION}, is using ramses_rf v{ramses_rf.VERSION}")
    _LOGGER.debug("\r\n\nConfig = %s\r\n", hass_config[DOMAIN])

    broker = RamsesCoordinator(hass, hass_config)
    hass.data[DOMAIN] = {BROKER: broker}

    if _LOGGER.isEnabledFor(logging.DEBUG):  # TODO: remove
        app_storage = await broker._async_load_storage()
        _LOGGER.debug("\r\n\nStore = %s\r\n", app_storage)

    await broker.start()

    register_service_functions(hass, broker)
    register_trigger_events(hass, broker)

    return True


@callback  # TODO: add async_ to routines where required to do so
def register_trigger_events(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @callback
    def process_msg(msg, *args, **kwargs):  # process_msg(msg, prev_msg=None)
        if (
            not broker.config[SZ_ADVANCED_FEATURES][SZ_MESSAGE_EVENTS]
            and broker._sem._value == broker.MAX_SEMAPHORE_LOCKS  # HACK
        ):
            return

        event_data = {
            "dtm": msg.dtm.isoformat(),
            "src": msg.src.id,
            "dst": msg.dst.id,
            "verb": msg.verb,
            "code": msg.code,
            "payload": msg.payload,
            "packet": str(msg._pkt),
        }
        hass.bus.async_fire(f"{DOMAIN}_message", event_data)

    broker.client.create_client(process_msg)


@callback  # TODO: add async_ to routines where required to do so
def register_service_functions(hass: HomeAssistantType, broker):
    """Set up the handlers for the system-wide services."""

    @verify_domain_control(hass, DOMAIN)
    async def svc_fake_device(call: ServiceCall) -> None:
        try:
            broker.client.fake_device(**call.data)
        except LookupError as exc:
            _LOGGER.error("%s", exc)
            return
        await asyncio.sleep(1)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_force_refresh(call: ServiceCall) -> None:
        await broker.async_update()  # incl.: async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_reset_system_mode(call: ServiceCall) -> None:
        payload = {
            UNIQUE_ID: broker.client.tcs.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_set_system_mode(call: ServiceCall) -> None:
        payload = {
            UNIQUE_ID: broker.client.tcs.id,
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    @verify_domain_control(hass, DOMAIN)
    async def svc_send_packet(call: ServiceCall) -> None:
        broker.client.send_cmd(broker.client.create_cmd(**call.data))
        await asyncio.sleep(1)
        async_dispatcher_send(hass, DOMAIN)

    @verify_domain_control(hass, DOMAIN)
    async def svc_call_dhw_svc(call: ServiceCall) -> None:
        payload = {
            UNIQUE_ID: f"{broker.client.tcs.id}_HW",
            SERVICE: call.service,
            DATA: call.data,
        }
        async_dispatcher_send(hass, DOMAIN, payload)

    [
        hass.services.async_register(DOMAIN, k, svc_call_dhw_svc, schema=v)
        for k, v in SVCS_WATER_HEATER_EVOHOME.items()
    ]

    domain_service = SVCS_DOMAIN
    if not broker.config[SZ_ADVANCED_FEATURES].get(SVC_SEND_PACKET):
        del domain_service[SVC_SEND_PACKET]
    domain_service |= SVCS_DOMAIN_EVOHOME

    services = {k: v for k, v in locals().items() if k.startswith("svc")}
    [
        hass.services.async_register(DOMAIN, k, services[f"svc_{k}"], schema=v)
        for k, v in SVCS_DOMAIN.items()
        if f"svc_{k}" in services
    ]


class RamsesEntity(Entity):
    """Base for any RAMSES II-compatible entity (e.g. Climate, Sensor)."""

    entity_id: str = None  # type: ignore[assignment]
    # _attr_assumed_state: bool = False
    # _attr_attribution: str | None = None
    # _attr_context_recent_time: timedelta = timedelta(seconds=5)
    # _attr_device_info: DeviceInfo | None = None
    # _attr_entity_category: EntityCategory | None
    # _attr_has_entity_name: bool
    # _attr_entity_picture: str | None = None
    # _attr_entity_registry_enabled_default: bool
    # _attr_entity_registry_visible_default: bool
    # _attr_extra_state_attributes: MutableMapping[str, Any]
    # _attr_force_update: bool
    _attr_icon: str | None
    _attr_name: str | None
    _attr_should_poll: bool = True
    _attr_unique_id: str | None = None
    # _attr_unit_of_measurement: str | None

    def __init__(self, broker, device) -> None:
        """Initialize the entity."""
        self.hass = broker.hass
        self._broker = broker
        self._device = device

        self._attr_should_poll = False

        self._entity_state_attrs = ()

        # NOTE: this is bad: self.update_ha_state(delay=5)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = {
            a: getattr(self._device, a)
            for a in self._entity_state_attrs
            if hasattr(self._device, a)
        }
        # TODO: use self._device._parent?
        # attrs["controller_id"] = self._device.ctl.id if self._device.ctl else None
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._broker._entities[self.unique_id] = self
        async_dispatcher_connect(self.hass, DOMAIN, self.async_handle_dispatch)

    @callback  # TODO: WIP
    def _call_client_api(self, func, *args, **kwargs) -> None:
        """Wrap client APIs to make them threadsafe."""
        # self.hass.loop.call_soon_threadsafe(
        #     func(*args, **kwargs)
        # )  # HACK: call_soon_threadsafe should not be needed

        func(*args, **kwargs)
        self.update_ha_state()

    @callback
    def async_handle_dispatch(self, *args) -> None:  # TODO: remove as unneeded?
        """Process a dispatched message.

        Data validation is not required, it will have been done upstream.
        This routine is threadsafe.
        """
        if not args:
            self.update_ha_state()

    @callback
    def update_ha_state(self, delay=3) -> None:
        """Update HA state after a short delay to allow system to quiesce.

        This routine is threadsafe.
        """
        args = (delay, self.async_schedule_update_ha_state)
        self.hass.loop.call_soon_threadsafe(
            self.hass.helpers.event.async_call_later, *args
        )  # HACK: call_soon_threadsafe should not be needed


class RamsesDeviceBase(RamsesEntity):  # for: binary_sensor & sensor
    """Base for any RAMSES II-compatible entity (e.g. BinarySensor, Sensor)."""

    def __init__(
        self,
        broker,
        device,
        state_attr,
        device_class=None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self.entity_id = f"{DOMAIN}.{device.id}-{state_attr}"

        self._attr_device_class = device_class
        self._attr_unique_id = f"{device.id}-{state_attr}"  # dont include domain (ramses_cc) / platform (binary_sesnor/sensor)

        self._state_attr = state_attr

    @property
    def available(self) -> bool:
        """Return True if the sensor is available."""
        return getattr(self._device, self._state_attr) is not None

    @property
    def name(self) -> str:
        """Return the name of the binary_sensor/sensor."""
        if not hasattr(self._device, "name") or not self._device.name:
            return f"{self._device.id} {self._state_attr}"
        return f"{self._device.name} {self._state_attr}"


class EvohomeZoneBase(RamsesEntity):  # for: climate & water_heater
    """Base for any RAMSES RF-compatible entity (e.g. Controller, DHW, Zones)."""

    _attr_precision: float = PRECISION_TENTHS
    _attr_temperature_unit: str = TEMP_CELSIUS

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self._attr_unique_id = (
            device.id
        )  # dont include domain (ramses_cc) / platform (climate)

    @property
    def current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._device.temperature

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        return {
            **super().extra_state_attributes,
            "schema": self._device.schema,
            "params": self._device.params,
            # "schedule": self._device.schedule,
        }

    @property
    def name(self) -> str | None:
        """Return the name of the climate/water_heater entity."""
        return self._device.name
