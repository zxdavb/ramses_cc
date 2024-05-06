#!/usr/bin/env python3
"""A virtual RF network useful for testing."""

from enum import StrEnum
from typing import TypedDict


class _ComPortsT(TypedDict):
    manufacturer: str
    product: str
    vid: int
    pid: int

    description: str
    serial_number: str | None
    interface: str | None

    device: str
    name: str


# NOTE: Below values are from real devices (with some contrived values)

COMPORTS_ATMEGA32U4: _ComPortsT = {  # 8/16 MHz atmega32u4 (HW Uart)
    "manufacturer": "SparkFun",
    "product": "evofw3 atmega32u4",
    "vid": 0x1B4F,  # aka SparkFun Electronics
    "pid": 0x9206,
    #
    "description": "evofw3 atmega32u4",
    "serial_number": None,
    "interface": None,
    #
    "device": "/dev/ttyACM0",  # is not a fixed value
    "name": "ttyACM0",  # not fixed
}

COMPORTS_ATMEGA328P: _ComPortsT = {  # 16MHZ atmega328 (SW Uart)
    "manufacturer": "FTDI",
    "product": "FT232R USB UART",
    "vid": 0x0403,  # aka Future Technology Devices International Ltd.
    "pid": 0x6001,
    #
    "description": "FT232R USB UART - FT232R USB UART",
    "serial_number": "A50285BI",
    "interface": "FT232R USB UART",
    #
    "device": "/dev/ttyUSB0",  # is not a fixed value
    "name": "ttyUSB0",  # not fixed
}

COMPORTS_TI4310: _ComPortsT = {  # Honeywell HGI80 (partially contrived)
    "manufacturer": "Texas Instruments",
    "product": "TUSB3410 Boot Device",
    "vid": 0x10AC,  # aka Honeywell, Inc.
    "pid": 0x0102,
    #
    "description": "TUSB3410 Boot Device",  # contrived
    "serial_number": "TUSB3410",
    "interface": None,  # assumed
    #
    "device": "/dev/ttyUSB0",  # is not a fixed value
    "name": "ttyUSB0",  # not fixed
}


class HgiFwTypes(StrEnum):
    EVOFW3 = " ".join(COMPORTS_ATMEGA32U4[k] for k in ("manufacturer", "product"))  # type: ignore[literal-required]
    HGI_80 = " ".join(COMPORTS_TI4310[k] for k in ("manufacturer", "product"))  # type: ignore[literal-required]


SCHEMA_1 = {
    "orphans_hvac": ["41:111111"],
    "known_list": {
        "18:111111": {"class": "HGI", "fw_version": "EVOFW3"},
        "41:111111": {"class": "REM"},
    },
}

SCHEMA_2 = {
    "orphans_hvac": ["42:222222"],
    "known_list": {
        "18:222222": {"class": "HGI", "fw_version": "HGI_80"},
        "42:222222": {"class": "FAN"},
    },
}

SCHEMA_3 = {
    "orphans_hvac": ["42:333333"],
    "known_list": {"18:333333": {"class": "HGI"}, "42:333333": {"class": "FAN"}},
}
