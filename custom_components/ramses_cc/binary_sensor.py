"""Support for RAMSES binary sensors."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import logging
from types import UnionType
from typing import Any

from ramses_rf import Gateway
from ramses_rf.device.base import Entity as RamsesRFEntity, HgiGateway
from ramses_rf.system.heat import Logbook, System
from ramses_tx.const import SZ_IS_EVOFW3

from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import ATTR_BATTERY_LEVEL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesController, RamsesEntity, RamsesEntityDescription
from .const import (
    ATTR_ACTIVE_FAULT,
    ATTR_LATEST_EVENT,
    ATTR_LATEST_FAULT,
    ATTR_SCHEMA,
    CONTROLLER,
    DOMAIN,
)


@dataclass(kw_only=True)
class RamsesBinarySensorEntityDescription(
    RamsesEntityDescription, BinarySensorEntityDescription
):
    """Class describing Ramses binary sensor entities."""

    attr: str | None = None
    entity_class: RamsesBinarySensor | None = None
    rf_entity_class: type | UnionType | None = RamsesRFEntity
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    icon_off: str | None = None

    def __post_init__(self):
        """Defaults entity attr to key."""
        self.attr = self.attr or self.key


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Ramses binary sensors."""
    controller: RamsesController = hass.data[DOMAIN][CONTROLLER]
    platform = entity_platform.async_get_current_platform()

    sensor_types: tuple[RamsesBinarySensorEntityDescription, ...] = (
        RamsesBinarySensorEntityDescription(
            key="gateway",
            name="Gateway",
            rf_entity_class=Gateway,
            entity_class=RamsesGatewayBinarySensor,
            device_class=BinarySensorDeviceClass.PROBLEM,
        ),
        RamsesBinarySensorEntityDescription(
            key="schema",
            name="Schema",
            rf_entity_class=System,
            entity_class=RamsesSystemBinarySensor,
            device_class=BinarySensorDeviceClass.PROBLEM,
            extra_attributes={
                ATTR_SCHEMA: "schema",
            },
        ),
        RamsesBinarySensorEntityDescription(
            key="window_open",
            name="Window open",
            device_class=BinarySensorDeviceClass.WINDOW,
        ),
        RamsesBinarySensorEntityDescription(
            key="actuator_state",
            name="Actuator state",
            icon="mdi:electric-switch",
            icon_off="mdi:electric-switch-closed",
        ),
        RamsesBinarySensorEntityDescription(
            key="battery_low",
            device_class=BinarySensorDeviceClass.BATTERY,
            extra_attributes={
                ATTR_BATTERY_LEVEL: "battery_state",
            },
        ),
        RamsesBinarySensorEntityDescription(
            key="active_fault",
            name="Active fault",
            rf_entity_class=Logbook,
            entity_class=RamsesLogbookBinarySensor,
            device_class=BinarySensorDeviceClass.PROBLEM,
            extra_attributes={
                ATTR_ACTIVE_FAULT: "active_fault",
                ATTR_LATEST_EVENT: "latest_event",
                ATTR_LATEST_FAULT: "latest_fault",
            },
        ),
        RamsesBinarySensorEntityDescription(
            key="ch_active",
            name="CH active",
        ),
        RamsesBinarySensorEntityDescription(
            key="ch_enabled",
            name="CH enabled",
        ),
        RamsesBinarySensorEntityDescription(
            key="cooling_active",
            name="Cooling active",
            icon="mdi:snowflake",
            icon_off="mdi:snowflake-off",
        ),
        RamsesBinarySensorEntityDescription(
            key="cooling_enabled",
            name="Cooling enabled",
        ),
        RamsesBinarySensorEntityDescription(
            key="dhw_active",
            name="DHW active",
        ),
        RamsesBinarySensorEntityDescription(
            key="dhw_enabled",
            name="DHW enabled",
        ),
        RamsesBinarySensorEntityDescription(
            key="flame_active",
            name="Flame active",
            icon="mdi:circle-outline",
            icon_off="mdi:fire-circle",
        ),
        RamsesBinarySensorEntityDescription(
            key="dhw_blocking",
            name="DHW blocking",
        ),
        RamsesBinarySensorEntityDescription(
            key="otc_active",
            name="Outside temperature control active",
        ),
        RamsesBinarySensorEntityDescription(
            key="summer_mode",
            name="Summer mode",
        ),
        RamsesBinarySensorEntityDescription(
            key="fault_present",
            name="Fault present",
        ),
        RamsesBinarySensorEntityDescription(
            key="bypass_position",
            name="Bypass position",
        ),
        # Special projects
        RamsesBinarySensorEntityDescription(
            key="bit_2_4",
            entity_registry_enabled_default=False,
        ),
        RamsesBinarySensorEntityDescription(
            key="bit_2_5",
            entity_registry_enabled_default=False,
        ),
        RamsesBinarySensorEntityDescription(
            key="bit_2_6",
            entity_registry_enabled_default=False,
        ),
        RamsesBinarySensorEntityDescription(
            key="bit_2_7",
            entity_registry_enabled_default=False,
        ),
        RamsesBinarySensorEntityDescription(
            key="bit_3_7",
            entity_registry_enabled_default=False,
        ),
        RamsesBinarySensorEntityDescription(
            key="bit_6_6",
            entity_registry_enabled_default=False,
        ),
    )

    async def async_add_new_entity(entity: RamsesRFEntity):
        entities = [
            (description.entity_class or RamsesBinarySensor)(
                controller, entity, description
            )
            for description in sensor_types
            if isinstance(entity, description.rf_entity_class)
            and hasattr(entity, description.key)
        ]

        async_add_entities(entities)

    controller.async_register_platform(platform, async_add_new_entity)


class RamsesBinarySensor(RamsesEntity, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    entity_description: RamsesBinarySensorEntityDescription

    def __init__(
        self, controller, device, entity_description: RamsesEntityDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(controller, device, entity_description)

        self.entity_id = ENTITY_ID_FORMAT.format(
            f"{device.id}_{entity_description.attr}"
        )
        self._attr_unique_id = f"{device.id}-{entity_description.key}"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.state is not None

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return getattr(self.rf_entity, self.entity_description.attr)

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return (
            self.entity_description.icon_on
            if self.is_on
            else self.entity_description.icon_off
        )

    # TODO: Remove this when we have config entries and devices.
    @property
    def name(self) -> str:
        """Return name temporarily prefixed with device ID."""
        return f"{self.rf_entity.id} {super().name}"


class RamsesLogbookBinarySensor(RamsesBinarySensor):
    """Representation of a fault log."""

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self.rf_entity._msgs.get("0418"):
            return dt.now() - msg.dtm < timedelta(seconds=1200)


class RamsesSystemBinarySensor(RamsesBinarySensor):
    """Representation of a system (a controller)."""

    rf_entity: System

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        if msg := self.rf_entity._msgs.get("1F09"):
            return dt.now() - msg.dtm < timedelta(
                seconds=msg.payload["remaining_seconds"] * 3
            )

    @property
    def is_on(self) -> bool | None:
        """Return True if the controller has been seen recently."""
        return self.available


class RamsesGatewayBinarySensor(RamsesBinarySensor):
    """Representation of a gateway (a HGI80)."""

    rf_entity: HgiGateway

    @property
    def available(self) -> bool:
        """Return True if the device is available."""
        return bool(self.rf_entity._gwy.hgi)  # TODO: look at most recent packet

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the integration-specific state attributes."""

        def shrink(device_hints) -> dict:
            return {
                k: v
                for k, v in device_hints.items()
                if k in ("alias", "class", "faked") and v not in (None, False)
            }

        gwy: Gateway = self.rf_entity._gwy
        return super().extra_state_attributes | {
            "schema": {gwy.tcs.id: gwy.tcs._schema_min} if gwy.tcs else {},
            "config": {"enforce_known_list": gwy._enforce_known_list},
            "known_list": [{k: shrink(v)} for k, v in gwy.known_list.items()],
            "block_list": [{k: shrink(v)} for k, v in gwy._exclude.items()],
            "is_evofw3": gwy._transport.get_extra_info(SZ_IS_EVOFW3),  # TODO: FIXME
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the gateway has been seen recently."""
        if msg := self.rf_entity._gwy._protocol._this_msg:  # TODO
            return dt.now() - msg.dtm > timedelta(seconds=300)
