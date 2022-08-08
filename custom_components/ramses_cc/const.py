#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by CH/DHW & HVAC."""
from __future__ import annotations

from types import SimpleNamespace

DOMAIN = "ramses_cc"

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

ATTR_FAN_RATE = "fan_rate"
ATTR_HUMIDITY = "relative_humidity"

ATTR_BATTERY_LEVEL = "battery_level"
ATTR_SETPOINT = "setpoint"

VOLUME_FLOW_RATE_LITERS_PER_MINUTE = "L/min"


DATA = "data"
SERVICE = "service"
UNIQUE_ID = "unique_id"

BINARY_SENSOR_ATTRS = (ATTR_ACTUATOR, ATTR_BATTERY, ATTR_WINDOW)
SENSOR_ATTRS = (
    ATTR_FAN_RATE,
    ATTR_HEAT_DEMAND,
    ATTR_HUMIDITY,
    ATTR_RELAY_DEMAND,
    ATTR_TEMPERATURE,
)  # ATTR_FAULT_LOG


SystemMode = SimpleNamespace(
    AUTO="auto",
    AWAY="away",
    CUSTOM="custom",
    DAY_OFF="day_off",
    DAY_OFF_ECO="day_off_eco",  # set to Eco when DayOff ends
    ECO_BOOST="eco_boost",  # Eco, or Boost
    HEAT_OFF="heat_off",
    RESET="auto_with_reset",
)
SYSTEM_MODE_MAP = {
    "00": SystemMode.AUTO,
    "01": SystemMode.HEAT_OFF,
    "02": SystemMode.ECO_BOOST,
    "03": SystemMode.AWAY,
    "04": SystemMode.DAY_OFF,
    "05": SystemMode.DAY_OFF_ECO,
    "06": SystemMode.RESET,
    "07": SystemMode.CUSTOM,
}
SYSTEM_MODE_LOOKUP = {v: k for k, v in SYSTEM_MODE_MAP.items()}

ZoneMode = SimpleNamespace(
    SCHEDULE="follow_schedule",
    ADVANCED="advanced_override",  # until the next setpoint
    PERMANENT="permanent_override",  # indefinitely
    COUNTDOWN="countdown_override",  # for a number of minutes (max 1,215)
    TEMPORARY="temporary_override",  # until a given date/time
)
ZONE_MODE_MAP = {
    "00": ZoneMode.SCHEDULE,
    "01": ZoneMode.ADVANCED,
    "02": ZoneMode.PERMANENT,
    "03": ZoneMode.COUNTDOWN,
    "04": ZoneMode.TEMPORARY,
}
ZONE_MODE_LOOKUP = {v: k for k, v in ZONE_MODE_MAP.items()}
