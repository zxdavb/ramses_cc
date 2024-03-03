"""Test the ramses_cc custom component."""

import asyncio
import json
from datetime import datetime as dt, timedelta as td
from pathlib import Path
from typing import Any

from custom_components.ramses_cc.const import STORAGE_KEY, STORAGE_VERSION
from ramses_rf.gateway import Command, Gateway

from .virtual_rf import VirtualRf

TEST_DIR = Path(__file__).resolve().parent / "test_data"


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


async def no_data_left_to_read(gwy: Gateway) -> None:
    """Wait until all pending data frames are read."""

    while gwy._transport.serial.in_waiting:
        await asyncio.sleep(0.001)


async def cast_packets_to_rf(
    rf: VirtualRf, packet_log: str, /, gwy: Gateway | None = None
) -> None:
    """Send packets from a log file to the virtual RF."""

    frames = []

    with open(packet_log) as f:
        for line in f:
            if line := line.rstrip():
                cmd = Command(line[31:].split("#")[0].rstrip())
                frames.append(str(cmd).encode() + b"\r\n")

    await rf.dump_frames_to_rf(frames)

    if gwy:
        await asyncio.wait_for(no_data_left_to_read(gwy), timeout=0.5)
