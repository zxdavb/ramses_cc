"""Support for WaterHeater devices of (RAMSES-II RF-based) Honeywell systems."""
import logging
from typing import List

from homeassistant.components.water_heater import (
    SUPPORT_AWAY_MODE,
    SUPPORT_OPERATION_MODE,
    WaterHeaterEntity,
)
from homeassistant.const import PRECISION_TENTHS, PRECISION_WHOLE, STATE_OFF, STATE_ON
from homeassistant.helpers.typing import ConfigType, HomeAssistantType
import homeassistant.util.dt as dt_util

from . import DOMAIN, EvoZoneBase
# from .const import

_LOGGER = logging.getLogger(__name__)

STATE_AUTO = "auto"

HA_STATE_TO_EVO = {STATE_AUTO: "", STATE_ON: "On", STATE_OFF: "Off"}
EVO_STATE_TO_HA = {v: k for k, v in HA_STATE_TO_EVO.items() if k != ""}

STATE_ATTRS_DHW = ["dhwId", "activeFaults", "stateStatus", "temperatureStatus"]


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create an evohome DHW controller."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    dhw = broker.water_heater = broker.client.evo.dhw

    _LOGGER.warning(
        "Found a Water Heater (stored DHW), id=%s, name=%s", dhw.idx, dhw.name
    )

    async_add_entities([EvoDHW(broker, dhw)], update_before_add=True)


class EvoDHW(EvoZoneBase, WaterHeaterEntity):
    """Base for a DHW controller (aka boiler)."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize an evohome DHW controller."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        # self._icon = "mdi:thermometer-lines"

        self._supported_features = 0

    @property
    def state(self):
        """Return the current state."""
        return
        return EVO_STATE_TO_HA[self._evo_device.stateStatus["state"]]

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        return
        if self._evo_device.stateStatus["mode"] == "EVO_FOLLOW":
            return STATE_AUTO
        return EVO_STATE_TO_HA[self._evo_device.stateStatus["state"]]

    @property
    def operation_list(self) -> List[str]:
        """Return the list of available operations."""
        return
        return list(HA_STATE_TO_EVO)

    @property
    def is_away_mode_on(self):
        """Return True if away mode is on."""
        return
        is_off = EVO_STATE_TO_HA[self._evo_device.stateStatus["state"]] == STATE_OFF
        is_permanent = self._evo_device.stateStatus["mode"] == "EVO_PERMOVER"
        return is_off and is_permanent
