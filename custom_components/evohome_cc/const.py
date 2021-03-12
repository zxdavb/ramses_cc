#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

from types import SimpleNamespace

DOMAIN = "evohome_cc"

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

BROKER = "broker"

DEVICE_CLASS_ACTUATOR = "actuator"

ATTR_ACTUATOR = "enabled"
ATTR_BATTERY = "battery_low"
ATTR_WINDOW = "window_open"

ATTR_FAULT_LOG = "fault_log"
ATTR_HEAT_DEMAND = "heat_demand"
ATTR_RELAY_DEMAND = "relay_demand"
ATTR_TEMPERATURE = "temperature"

ATTR_BATTERY_LEVEL = "battery_level"
ATTR_SETPOINT = "setpoint"

PERCENTAGE = "%"

BINARY_SENSOR_ATTRS = (ATTR_ACTUATOR, ATTR_BATTERY, ATTR_WINDOW)
SENSOR_ATTRS = (ATTR_HEAT_DEMAND, ATTR_RELAY_DEMAND, ATTR_TEMPERATURE)  # ATTR_FAULT_LOG

MODE = "mode"
SYSTEM_MODE = "system_mode"

SystemMode = SimpleNamespace(
    AUTO="auto",
    AWAY="away",
    CUSTOM="custom",
    DAY_OFF="day_off",
    DAY_OFF_ECO="day_off_eco",
    ECO="eco",
    HEAT_OFF="heat_off",
    RESET="auto_with_reset",
)

ZoneMode = SimpleNamespace(
    SCHEDULE="follow_schedule",
    ADVANCED="advanced_override",
    PERMANENT="permanent_override",
    _UNKNOWN="day_override",
    TEMPORARY="temporary_override",
)
