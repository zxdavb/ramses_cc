"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""
from __future__ import annotations

import logging
from typing import Any

import ramses_rf
from ramses_tx.exceptions import TransportSerialError
import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    CONF_SCAN_INTERVAL,
    EVENT_HOMEASSISTANT_START,
    PRECISION_TENTHS,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import BROKER, DOMAIN
from .coordinator import RamsesBroker
from .schemas import (
    SCH_DOMAIN_CONFIG,
    SVC_SEND_PACKET,
    SVCS_DOMAIN,
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Create a ramses_rf (RAMSES_II)-based system."""

    _LOGGER.info(
        "%s v%s, is using ramses_rf v%s",
        DOMAIN,
        VERSION,
        ramses_rf.VERSION,
    )
    _LOGGER.debug("\r\n\nConfig = %s\r\n", config[DOMAIN])

    broker = RamsesBroker(hass, config)
    try:
        await broker.start()
    except TransportSerialError as exc:
        _LOGGER.error("There is a problem with the serial port: %s", exc)
        return False

    hass.data.setdefault(DOMAIN, {})[BROKER] = broker

    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_interval=config[DOMAIN][CONF_SCAN_INTERVAL],
    )
    coordinator.update_method = broker.async_update

    if _LOGGER.isEnabledFor(logging.DEBUG):  # TODO: remove
        app_storage = await broker._async_load_storage()
        _LOGGER.debug("\r\n\nStore = %s\r\n", app_storage)

    # NOTE: .async_listen_once(EVENT_HOMEASSISTANT_START, awaitable_coro)
    # NOTE: will be passed event, as: async def awaitable_coro(_event: Event):
    await coordinator.async_config_entry_first_refresh()  # will save access tokens too
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, broker.async_update)

    register_domain_services(hass, broker)
    register_domain_events(hass, broker)

    return True


# TODO: add async_ to routines where required to do so
@callback  # TODO: the following is a mess - to add register/deregister of clients
def register_domain_events(hass: HomeAssistant, broker: RamsesBroker) -> None:
    """Set up the handlers for the system-wide events."""

    @callback
    def process_msg(msg, *args, **kwargs):  # process_msg(msg, prev_msg=None)
        if (
            regex := broker.config[SZ_ADVANCED_FEATURES][SZ_MESSAGE_EVENTS]
        ) and regex.match(f"{msg!r}"):
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

        if broker.learn_device_id and broker.learn_device_id == msg.src.id:
            event_data = {
                "src": msg.src.id,
                "code": msg.code,
                "packet": str(msg._pkt),
            }
            hass.bus.async_fire(f"{DOMAIN}_learn", event_data)

    broker.client.add_msg_handler(process_msg)


@callback  # TODO: add async_ to routines where required to do so
def register_domain_services(hass: HomeAssistant, broker: RamsesBroker):
    """Set up the handlers for the domain-wide services."""

    @verify_domain_control(hass, DOMAIN)
    async def svc_fake_device(call: ServiceCall) -> None:
        try:
            broker.client.fake_device(**call.data)
        except LookupError as exc:
            _LOGGER.error("%s", exc)
            return
        hass.helpers.event.async_call_later(5, broker.async_update)

    @verify_domain_control(hass, DOMAIN)
    async def svc_force_update(_: ServiceCall) -> None:
        await broker.async_update()

    @verify_domain_control(hass, DOMAIN)
    async def svc_send_packet(call: ServiceCall) -> None:
        kwargs = dict(call.data.items())  # is ReadOnlyDict
        if (
            call.data["device_id"] == "18:000730"
            and kwargs.get("from_id", "18:000730") == "18:000730"
            and broker.client.hgi.id
        ):
            kwargs["device_id"] = broker.client.hgi.id
        broker.client.send_cmd(broker.client.create_cmd(**kwargs))
        hass.helpers.event.async_call_later(5, broker.async_update)

    domain_service = SVCS_DOMAIN
    if not broker.config[SZ_ADVANCED_FEATURES].get(SVC_SEND_PACKET):
        del domain_service[SVC_SEND_PACKET]

    services = {k: v for k, v in locals().items() if k.startswith("svc")}
    for name, schema in SVCS_DOMAIN.items():
        if f"svc_{name}" in services:
            hass.services.async_register(
                DOMAIN, name, services[f"svc_{name}"], schema=schema
            )


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
        device_class: SensorDeviceClass | None = None,
        unique_id_attr: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        self.entity_id = f"{DOMAIN}.{device.id}-{state_attr}"

        self._attr_device_class = device_class
        self._attr_unique_id = f"{device.id}-{unique_id_attr or state_attr}"
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
    _attr_temperature_unit: str = UnitOfTemperature.CELSIUS

    def __init__(self, broker, device) -> None:
        """Initialize the sensor."""
        super().__init__(broker, device)

        # dont include platform/domain (climate.ramses_cc)
        self._attr_unique_id = device.id

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
        }

    @property
    def name(self) -> str | None:
        """Return the name of the climate/water_heater entity."""
        return self._device.name
