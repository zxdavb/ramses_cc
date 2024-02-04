"""The tests for the Remote."""

import asyncio

# from unittest.mock import PropertyMock, patch
from custom_components.ramses_cc.const import DOMAIN as RAMSES_DOMAIN  # noqa: E402
import pytest
from tests.common import (  # type: ignore[import-untyped]
    async_mock_service,
    get_test_home_assistant,
)

import homeassistant.components.remote as remote
from homeassistant.components.remote import ATTR_COMMAND, DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, CONF_PLATFORM
from homeassistant.core import HomeAssistant

from .common import setup_platform

TEST_PLATFORM = {DOMAIN: {CONF_PLATFORM: RAMSES_DOMAIN}}

SERVICE_SEND_COMMAND = "send_command"
SERVICE_LEARN_COMMAND = "learn_command"
SERVICE_DELETE_COMMAND = "delete_command"

ENTITY_ID = "remote.30_123456"


@pytest.fixture
def hass() -> HomeAssistant:
    return get_test_home_assistant()


# @pytest.fixture(autouse=True)
# def patches_for_tests(monkeypatch: pytest.MonkeyPatch):
#     monkeypatch.setattr("ramses_tx.protocol._GAP_BETWEEN_WRITES", _GAP_BETWEEN_WRITES)


async def test_delete_command(hass: HomeAssistant) -> None:
    """Test the delete_command service calls."""

    hass.start()

    # for domain in (RAMSES_DOMAIN, remote.DOMAIN):
    command_calls = async_mock_service(hass, remote.DOMAIN, SERVICE_DELETE_COMMAND)

    data = {
        ATTR_ENTITY_ID: ENTITY_ID,
        ATTR_COMMAND: ["test_command"],
    }
    await hass.services.async_call(DOMAIN, SERVICE_DELETE_COMMAND, data)

    # await hass.async_block_till_done()  # FIXME: this is hanging, why?
    await asyncio.sleep(0.01)

    hass.stop()

    assert len(command_calls) == 1
    call = command_calls[-1]

    assert call.domain == remote.DOMAIN
    assert call.service == SERVICE_DELETE_COMMAND
    assert call.data[ATTR_ENTITY_ID] == ENTITY_ID


async def test_service_call(hass: HomeAssistant) -> None:
    """Test the alarm control panel can be set to away."""

    hass.start()

    # with patch("xxxxxx.abode.devices.alarm.Alarm.set_away") as mock_set_away:
    await setup_platform(hass, RAMSES_DOMAIN)

    data = {
        ATTR_ENTITY_ID: ENTITY_ID,
        ATTR_COMMAND: ["test_command"],
    }
    await hass.services.async_call(
        RAMSES_DOMAIN,
        SERVICE_DELETE_COMMAND,
        data,
        blocking=True,
    )

    # await hass.async_block_till_done()  # FIXME: will this hang too?
    await asyncio.sleep(0.01)

    hass.stop()

    # mock_set_away.assert_called_once()

    # with patch(
    #     "xxxxxx.abode.devices.alarm.Alarm.mode",
    #     new_callable=PropertyMock,
    # ) as mock_mode:
    #     mock_mode.return_value = CONST.MODE_AWAY

    #     update_callback = mock_callback.call_args[0][1]
    #     await hass.async_add_executor_job(update_callback, "area_1")
    #     await hass.async_block_till_done()

    #     state = hass.states.get(DEVICE_ID)
    #     assert state.state == STATE_ALARM_ARMED_AWAY
