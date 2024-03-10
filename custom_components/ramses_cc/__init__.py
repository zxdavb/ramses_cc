"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import voluptuous as vol  # type: ignore[import-untyped]
from homeassistant.const import ATTR_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.service import verify_domain_control
from homeassistant.helpers.typing import ConfigType

from ramses_rf.device import Fakeable
from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_tx.address import pkt_addrs
from ramses_tx.command import Command
from ramses_tx.exceptions import PacketAddrSetInvalid, TransportSerialError

from .broker import RamsesBroker
from .const import (
    BROKER,
    CONF_ADVANCED_FEATURES,
    CONF_MESSAGE_EVENTS,
    CONF_SEND_PACKET,
    DOMAIN,
    SIGNAL_UPDATE,
)
from .schemas import (
    SCH_BIND_DEVICE,
    SCH_DOMAIN_CONFIG,
    SCH_SEND_PACKET,
    SVC_BIND_DEVICE,
    SVC_FORCE_UPDATE,
    SVC_SEND_PACKET,
)

if TYPE_CHECKING:
    from ramses_tx.message import Message


_LOGGER = logging.getLogger(__name__)


CONFIG_SCHEMA = vol.Schema({DOMAIN: SCH_DOMAIN_CONFIG}, extra=vol.ALLOW_EXTRA)

PLATFORMS: Final[Platform] = (
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.REMOTE,
    Platform.WATER_HEATER,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Create a ramses_rf (RAMSES_II)-based system."""

    broker = RamsesBroker(hass, config)
    try:
        await broker.start()
    except TransportSerialError as exc:
        _LOGGER.error("There is a problem with the serial port: %s", exc)
        return False

    hass.data.setdefault(DOMAIN, {})[BROKER] = broker

    register_domain_services(hass, broker)
    register_domain_events(hass, broker)

    return True


@callback  # TODO: the following is a mess - to add register/deregister of clients
def register_domain_events(hass: HomeAssistant, broker: RamsesBroker) -> None:
    """Set up the handlers for the system-wide events."""

    @callback
    def async_process_msg(msg: Message, *args: Any, **kwargs: Any) -> None:
        """Process a message from the event bus as pass it on."""

        if (
            regex := broker.config[CONF_ADVANCED_FEATURES][CONF_MESSAGE_EVENTS]
        ) and regex.search(f"{msg!r}"):
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

    broker.client.add_msg_handler(async_process_msg)


@callback
def register_domain_services(hass: HomeAssistant, broker: RamsesBroker) -> None:
    """Set up the handlers for the domain-wide services."""

    @verify_domain_control(hass, DOMAIN)  # TODO: is a work in progress
    async def async_bind_device(call: ServiceCall) -> None:
        device: Fakeable

        try:
            device = broker.client.fake_device(call.data["device_id"])
        except LookupError as exc:
            _LOGGER.error("%s", exc)
            return

        if call.data["device_info"]:
            cmd = Command(call.data["device_info"])
        else:
            cmd = None

        await device._initiate_binding_process(  # may: BindingFlowFailed
            list(call.data["offer"].keys()),
            confirm_code=list(call.data["confirm"].keys()),
            ratify_cmd=cmd,
        )  # TODO: will need to re-discover schema
        hass.helpers.event.async_call_later(5, broker.async_update)

    @verify_domain_control(hass, DOMAIN)
    async def async_force_update(_: ServiceCall) -> None:
        await broker.async_update()

    @verify_domain_control(hass, DOMAIN)
    async def async_send_packet(call: ServiceCall) -> None:
        kwargs = dict(call.data.items())  # is ReadOnlyDict
        if (
            call.data["device_id"] == "18:000730"
            and kwargs.get("from_id", "18:000730") == "18:000730"
            and broker.client.hgi.id
        ):
            kwargs["device_id"] = broker.client.hgi.id

        cmd = broker.client.create_cmd(**kwargs)

        # HACK: to fix the device_id when GWY announcing, will be:
        #    I --- 18:000730 18:006402 --:------ 0008 002 00C3  # because src != dst
        # ... should be:
        #    I --- 18:000730 --:------ 18:006402 0008 002 00C3  # 18:730 is sentinel
        if cmd.src.id == "18:000730" and cmd.dst.id == broker.client.hgi.id:
            try:
                pkt_addrs(broker.client.hgi.id + cmd._frame[16:37])
            except PacketAddrSetInvalid:
                cmd._addrs[1], cmd._addrs[2] = cmd._addrs[2], cmd._addrs[1]
                cmd._repr = None

        broker.client.send_cmd(cmd)
        hass.helpers.event.async_call_later(5, broker.async_update)

    hass.services.async_register(
        DOMAIN, SVC_BIND_DEVICE, async_bind_device, schema=SCH_BIND_DEVICE
    )
    hass.services.async_register(
        DOMAIN, SVC_FORCE_UPDATE, async_force_update, schema={}
    )

    if broker.config[CONF_ADVANCED_FEATURES].get(CONF_SEND_PACKET):
        hass.services.async_register(
            DOMAIN, SVC_SEND_PACKET, async_send_packet, schema=SCH_SEND_PACKET
        )


class RamsesEntity(Entity):
    """Base for any RAMSES II-compatible entity (e.g. Climate, Sensor)."""

    _broker: RamsesBroker
    _device: RamsesRFEntity

    _attr_should_poll = False

    entity_description: RamsesEntityDescription

    def __init__(
        self,
        broker: RamsesBroker,
        device: RamsesRFEntity,
        entity_description: RamsesEntityDescription,
    ) -> None:
        """Initialize the entity."""
        self.hass = broker.hass
        self._broker = broker
        self._device = device
        self.entity_description = entity_description

        self._attr_unique_id = device.id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the integration-specific state attributes."""
        attrs = {
            ATTR_ID: self._device.id,
        }
        if self.entity_description.ramses_cc_extra_attributes:
            attrs |= {
                k: getattr(self._device, v)
                for k, v in self.entity_description.ramses_cc_extra_attributes.items()
                if hasattr(self._device, v)
            }
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        self._broker._entities[self.unique_id] = self
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATE, self.async_write_ha_state
            )
        )

    @callback
    def async_write_ha_state_delayed(self, delay: int = 3) -> None:
        """Write to the state machine after a short delay to allow system to quiesce."""

        # FIXME: doesn't work, as injects `_now: dt``, where only self is expected
        # async_call_later(self.hass, delay, self.async_write_ha_state)

        self.hass.loop.call_later(delay, self.async_write_ha_state)


@dataclass(frozen=True, kw_only=True)
class RamsesEntityDescription(EntityDescription):
    """Class describing Ramses entities."""

    has_entity_name: bool = True

    # integration-specific attributes
    ramses_cc_extra_attributes: dict[str, str] | None = None  # TODO: may not be None?
