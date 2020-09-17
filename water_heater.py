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

from . import DOMAIN, EvoZone
# from .const import

_LOGGER = logging.getLogger(__name__)

STATE_AUTO = "auto"

HA_STATE_TO_EVO = {STATE_AUTO: "", STATE_ON: "On", STATE_OFF: "Off"}
EVO_STATE_TO_HA = {v: k for k, v in HA_STATE_TO_EVO.items() if k != ""}

STATE_ATTRS_DHW = ["dhwId", "activeFaults", "stateStatus", "temperatureStatus"]


async def async_setup_platform(
    hass: HomeAssistantType, config: ConfigType, async_add_entities, discovery_info=None
) -> None:
    """Create a DHW controller."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    dhw = broker.water_heater = broker.client.evo.dhw

    _LOGGER.warn(
        "Found a Water Heater (stored DHW), id=%s, name=%s", dhw.idx, dhw.name
    )

    async_add_entities([EvoDHW(broker, dhw)], update_before_add=True)


class EvoDHW(EvoZone, WaterHeaterEntity):
    """Base for a Honeywell TCC DHW controller (aka boiler)."""

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize an evohome DHW controller."""
        super().__init__(evo_broker, evo_device)

        self._unique_id = evo_device.id
        self._name = "DHW controller"
        # self._icon = "mdi:thermometer-lines"

        self._supported_features = SUPPORT_AWAY_MODE | SUPPORT_OPERATION_MODE

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

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode for a DHW controller.

        Except for Auto, the mode is only until the next SetPoint.
        """

        return

        if operation_mode == STATE_AUTO:
            await self._evo_broker.call_client_api(self._evo_device.set_dhw_auto())
        else:
            await self._update_schedule()
            until = dt_util.parse_datetime(self.setpoints.get("next_sp_from", ""))
            until = dt_util.as_utc(until) if until else None

            if operation_mode == STATE_ON:
                await self._evo_broker.call_client_api(
                    self._evo_device.set_dhw_on(until=until)
                )
            else:  # STATE_OFF
                await self._evo_broker.call_client_api(
                    self._evo_device.set_dhw_off(until=until)
                )

    async def async_turn_away_mode_on(self):
        """Turn away mode on."""
        # await self._evo_broker.call_client_api(self._evo_device.set_dhw_off())

    async def async_turn_away_mode_off(self):
        """Turn away mode off."""
        # await self._evo_broker.call_client_api(self._evo_device.set_dhw_auto())
