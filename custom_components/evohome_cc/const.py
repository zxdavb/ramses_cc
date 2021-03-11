#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

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

EVOZONE_FOLLOW = "follow_schedule"
EVOZONE_TEMPOVER = "temporary_override"
EVOZONE_PERMOVER = "permanent_override"
