"""Test the setup of ramses_cc with data."""

import asyncio
from datetime import datetime as dt, timedelta as td
import json
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

from custom_components.ramses_cc import DOMAIN, SVC_FORCE_UPDATE
from custom_components.ramses_cc.const import STORAGE_KEY, STORAGE_VERSION
from pytest_homeassistant_custom_component.common import MockConfigEntry
from ramses_rf.gateway import Command, Gateway
import serial

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from tests.virtual_rf import VirtualRf

# patched constants
_CALL_LATER_DELAY: Final = 0  # from: custom_components.ramses_cc.broker.py


TEST_DIR = Path(__file__).resolve().parent / "test_data"

SZ_SERVICE: Final = "service"
SZ_SERVICE_DATA: Final = "service_data"

TEST_SUITE = [
    {
        SZ_SERVICE: SVC_FORCE_UPDATE,
        SZ_SERVICE_DATA: {},
    },
]


def normalise_storage_file(file_name: str) -> dict[str, Any]:
    """Return the JSON useful for mocked storage from a .storage file."""

    with open(file_name) as f:
        storage = json.load(f)

    # correct the keys (which are dtm) to be recent, else they'll be dropped as expired
    now = dt.now()
    storage["data"]["client_state"]["packets"] = {
        (now - td(seconds=i)).isoformat(): v
        for i, v in enumerate(storage["data"]["client_state"]["packets"].values())
    }

    assert storage["key"] == STORAGE_KEY
    assert storage["version"] == STORAGE_VERSION

    return {STORAGE_KEY: {"version": STORAGE_VERSION, "data": storage["data"]}}


def cast_packets_to_rf(rf: VirtualRf, packet_log: str):
    ser = serial.Serial(rf.ports[1])

    with open(packet_log) as f:
        for line in f:
            if line := line.rstrip():
                # pkt = Packet.from_file(line[:26], line[27:])
                cmd = Command(line[31:].split("#")[0].rstrip())
                ser.write(str(cmd).encode() + b"\r\n")


async def _test_setup_common(
    hass: HomeAssistant, rf: VirtualRf, entry: ConfigEntry
) -> None:
    cast_packets_to_rf(rf, f"{TEST_DIR}/system_1.log")
    await asyncio.sleep(0.05)  # how to quiesce the above?

    _: Gateway = list(hass.data[DOMAIN].values())[0].client

    assert len(hass.services.async_services_for_domain(DOMAIN)) == 6

    for test in TEST_SUITE:
        _ = await hass.services.async_call(DOMAIN, **test, blocking=True)

    pass


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def _test_services_entry(
    hass: HomeAssistant, rf: VirtualRf, entry: ConfigEntry
) -> None:
    """Test ramses_cc via importing a config entry."""

    assert await hass.config_entries.async_setup(entry.entry_id)

    #
    try:
        await _test_setup_common(hass, rf, entry)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


@patch("custom_components.ramses_cc.broker._CALL_LATER_DELAY", _CALL_LATER_DELAY)
async def _test_services_import(
    hass: HomeAssistant, rf: VirtualRf, config: dict
) -> None:
    """Test ramses_cc via importing a configuration."""

    assert await async_setup_component(hass, DOMAIN, {DOMAIN: config})

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    try:
        await _test_setup_common(hass, rf, entry)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_services_entry(hass: HomeAssistant) -> None:
    """Test ramses_cc via config entry."""

    rf = VirtualRf(2)
    rf.set_gateway(rf.ports[0], "18:000730")

    config = {
        "serial_port": {"port_name": rf.ports[0]},
        "ramses_rf": {"disable_discovery": True},
    }  # aim to parameterize

    try:
        assert len(hass.config_entries.async_entries(DOMAIN)) == 0
        entry = MockConfigEntry(domain=DOMAIN, options=config)
        entry.add_to_hass(hass)

        await _test_services_entry(hass, rf, entry)
    finally:
        await rf.stop()


async def test_services_import(hass: HomeAssistant) -> None:
    """Test ramses_cc via importing a configuration."""

    rf = VirtualRf(2)
    rf.set_gateway(rf.ports[0], "18:000730")

    config = {
        "serial_port": rf.ports[0],
        "ramses_rf": {"disable_discovery": True},
    }  # aim to parameterize

    try:
        await _test_services_import(hass, rf, config)
    finally:
        await rf.stop()
