"""Support for RAMSES binary sensors."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime as dt, timedelta
import logging
from types import UnionType
from typing import Any

from ramses_rf import Gateway
from ramses_rf.device.base import BatteryState, HgiGateway
from ramses_rf.device.heat import (
    SZ_CH_ACTIVE,
    SZ_CH_ENABLED,
    SZ_COOLING_ACTIVE,
    SZ_COOLING_ENABLED,
    SZ_DHW_ACTIVE,
    SZ_DHW_BLOCKING,
    SZ_DHW_ENABLED,
    SZ_FAULT_PRESENT,
    SZ_FLAME_ACTIVE,
    SZ_OTC_ACTIVE,
    SZ_SUMMER_MODE,
    BdrSwitch,
    OtbGateway,
    TrvActuator,
)
from ramses_rf.entity_base import Entity as RamsesRFEntity
from ramses_rf.schemas import SZ_BLOCK_LIST, SZ_CONFIG, SZ_KNOWN_LIST, SZ_SCHEMA
from ramses_rf.system.heat import Logbook, System
from ramses_tx.const import SZ_BYPASS_POSITION, SZ_IS_EVOFW3

from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import RamsesEntity, RamsesEntityDescription
from .broker import RamsesBroker
from .const import (
    ATTR_ACTIVE_FAULT,
    ATTR_BATTERY_LEVEL,
    ATTR_LATEST_EVENT,
    ATTR_LATEST_FAULT,
    ATTR_WORKING_SCHEMA,
    BROKER,
    DOMAIN,
)


@dataclass(kw_only=True)
class RamsesBinarySensorEntityDescription(
    RamsesEntityDescription, BinarySensorEntityDescription
):
    """Class describing Ramses binary sensor entities."""

    attr: str | None = None
    entity_class: RamsesBinarySensor | None = None
    rf_class: type | UnionType | None = RamsesRFEntity
    entity_category: EntityCategory | None = EntityCategory.DIAGNOSTIC
    icon_off: str | None = None

    def __post_init__(self):
        """Defaults entity attr to key."""
        self.attr = self.attr or self.key


_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
    hass: HomeAssistant,
    _: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType = None,
) -> None:
    """Create binary sensors for CH/DHW (heat) & HVAC."""

    if discovery_info is None:
        return

    broker: RamsesBroker = hass.data[DOMAIN][BROKER]

    entities = [
        (description.entity_class or RamsesBinarySensor)(broker, device, description)
        for device in discovery_info["devices"]
        for description in BINARY_SENSOR_DESCRIPTIONS
        if isinstance(device, description.rf_class) and hasattr(device, description.key)
    ]
    async_add_entities(entities)


class RamsesBinarySensor(RamsesEntity, BinarySensorEntity):
    """Representation of a generic binary sensor."""

    entity_description: RamsesBinarySensorEntityDescription

    def __init__(
        self,
        broker: RamsesBroker,
        device: RamsesRFEntity,
        entity_description: RamsesEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.info("Found %r: %s", device, entity_description.key)
        super().__init__(broker, device, entity_description)

        self.entity_id = ENTITY_ID_FORMAT.format(
            f"{device.id}_{entity_description.key}"
        )
        self._attr_unique_id = f"{device.id}-{entity_description.key}"

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return self.state is not None

    @property
    def is_on(self) -> bool | None:
        """Return the state of the binary sensor."""
        return getattr(self._device, self.entity_description.attr)

    @property
    def icon(self) -> str:
        """Return the icon to use in the frontend, if any."""
        return (
            self.entity_description.icon
            if self.is_on
            else self.entity_description.icon_off
        )

    # TODO: Remove this when we have config entries and devices.
    @property
    def name(self) -> str:
        """Return name temporarily prefixed with device name/id."""
        prefix = (
            self._device.name
            if hasattr(self._device, "name") and self._device.name
            else self._device.id
        )
        return f"{prefix} {super().name}"


class RamsesLogbookBinarySensor(RamsesBinarySensor):
    """Representation of a fault log."""

    _device: Logbook

    @property
    def available(self) -> bool:
        """Return True if the device has been seen recently."""
        msg = self._device._msgs.get("0418")
        return msg and dt.now() - msg.dtm < timedelta(seconds=1200)

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        return self._device.active_fault is not None


class RamsesSystemBinarySensor(RamsesBinarySensor):
    """Representation of a system (a controller)."""

    _device: System

    @property
    def available(self) -> bool:
        """Return True if the last system sync message is recent."""
        msg = self._device._msgs.get("1F09")
        return msg and dt.now() - msg.dtm < timedelta(
            seconds=msg.payload["remaining_seconds"] * 3
        )


class RamsesGatewayBinarySensor(RamsesBinarySensor):
    """Representation of a gateway (a HGI80)."""

    _device: HgiGateway

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the integration-specific state attributes."""

        def shrink(device_hints) -> dict:
            return {
                k: v
                for k, v in device_hints.items()
                if k in ("alias", "class", "faked") and v not in (None, False)
            }

        gwy: Gateway = self._device._gwy
        return super().extra_state_attributes | {
            SZ_SCHEMA: {gwy.tcs.id: gwy.tcs._schema_min} if gwy.tcs else {},
            SZ_CONFIG: {"enforce_known_list": gwy._enforce_known_list},
            SZ_KNOWN_LIST: [{k: shrink(v)} for k, v in gwy.known_list.items()],
            SZ_BLOCK_LIST: [{k: shrink(v)} for k, v in gwy._exclude.items()],
            SZ_IS_EVOFW3: gwy._transport.get_extra_info(SZ_IS_EVOFW3),  # TODO: FIXME
        }

    @property
    def is_on(self) -> bool:
        """Return True if the gateway has received messages recently."""
        msg = self._device._gwy._this_msg  # TODO
        return msg and dt.now() - msg.dtm < timedelta(seconds=300)


BINARY_SENSOR_DESCRIPTIONS: tuple[RamsesBinarySensorEntityDescription, ...] = (
    RamsesBinarySensorEntityDescription(
        key="status",
        attr="id",  # FIXME:
        name="Gateway status",
        rf_class=HgiGateway,
        entity_class=RamsesGatewayBinarySensor,
    ),
    RamsesBinarySensorEntityDescription(
        key="status",
        attr="id",  # FIXME:
        name="System status",
        rf_class=System,
        entity_class=RamsesSystemBinarySensor,
        extra_attributes={
            ATTR_WORKING_SCHEMA: SZ_SCHEMA,
        },
    ),
    RamsesBinarySensorEntityDescription(
        key=TrvActuator.WINDOW_OPEN,
        name="Window open",
        device_class=BinarySensorDeviceClass.WINDOW,
    ),
    RamsesBinarySensorEntityDescription(
        key=BdrSwitch.ACTIVE,
        name="Active",
        icon="mdi:electric-switch",
        icon_off="mdi:electric-switch-closed",
    ),
    RamsesBinarySensorEntityDescription(
        key=BatteryState.BATTERY_LOW,
        device_class=BinarySensorDeviceClass.BATTERY,
        extra_attributes={
            ATTR_BATTERY_LEVEL: BatteryState.BATTERY_STATE,
        },
    ),
    RamsesBinarySensorEntityDescription(
        key="active_fault",
        name="Active fault",
        rf_class=Logbook,
        entity_class=RamsesLogbookBinarySensor,
        device_class=BinarySensorDeviceClass.PROBLEM,
        extra_attributes={
            ATTR_ACTIVE_FAULT: "active_fault",
            ATTR_LATEST_EVENT: "latest_event",
            ATTR_LATEST_FAULT: "latest_fault",
        },
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_CH_ACTIVE,
        name="CH active",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_CH_ENABLED,
        name="CH enabled",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_COOLING_ACTIVE,
        name="Cooling active",
        icon="mdi:snowflake",
        icon_off="mdi:snowflake-off",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_COOLING_ENABLED,
        name="Cooling enabled",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_DHW_ACTIVE,
        name="DHW active",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_DHW_ENABLED,
        name="DHW enabled",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_FLAME_ACTIVE,
        name="Flame active",
        icon="mdi:circle-outline",
        icon_off="mdi:fire-circle",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_DHW_BLOCKING,
        name="DHW blocking",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_OTC_ACTIVE,
        name="Outside temperature control active",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_SUMMER_MODE,
        name="Summer mode",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_FAULT_PRESENT,
        name="Fault present",
    ),
    RamsesBinarySensorEntityDescription(
        key=SZ_BYPASS_POSITION,
        name="Bypass position",
    ),
    # Special projects
    RamsesBinarySensorEntityDescription(
        key="bit_2_4",
        name="Bit 2/4",
        rf_class=OtbGateway,
        entity_registry_enabled_default=False,
    ),
    RamsesBinarySensorEntityDescription(
        key="bit_2_5",
        name="Bit 2/5",
        rf_class=OtbGateway,
        entity_registry_enabled_default=False,
    ),
    RamsesBinarySensorEntityDescription(
        key="bit_2_6",
        name="Bit 2/6",
        rf_class=OtbGateway,
        entity_registry_enabled_default=False,
    ),
    RamsesBinarySensorEntityDescription(
        key="bit_2_7",
        name="Bit 2/7",
        rf_class=OtbGateway,
        entity_registry_enabled_default=False,
    ),
    RamsesBinarySensorEntityDescription(
        key="bit_3_7",
        name="Bit 3/7",
        rf_class=OtbGateway,
        entity_registry_enabled_default=False,
    ),
    RamsesBinarySensorEntityDescription(
        key="bit_6_6",
        name="Bit 6/6",
        rf_class=OtbGateway,
        entity_registry_enabled_default=False,
    ),
)
