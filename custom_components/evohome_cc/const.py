#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome & others."""

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

ATTR_FAN_RATE = "fan_rate"
ATTR_HUMIDITY = "relative_humidity"

ATTR_BATTERY_LEVEL = "battery_level"
ATTR_SETPOINT = "setpoint"

PERCENTAGE = "%"

BINARY_SENSOR_ATTRS = (ATTR_ACTUATOR, ATTR_BATTERY, ATTR_WINDOW)
SENSOR_ATTRS = (
    ATTR_FAN_RATE,
    ATTR_HEAT_DEMAND,
    ATTR_HUMIDITY,
    ATTR_RELAY_DEMAND,
    ATTR_TEMPERATURE,
)  # ATTR_FAULT_LOG
