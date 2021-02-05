#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""Support for Honeywell's RAMSES-II RF protocol, as used by evohome.

Requires a Honeywell HGI80 (or compatible) gateway.
"""

__version__ = "0.5.4"

DOMAIN = "evohome_cc"

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

ATTR_HEAT_DEMAND = "heat_demand"
ATTR_RELAY_DEMAND = "relay_demand"
ATTR_SETPOINT = "setpoint"
ATTR_TEMPERATURE = "temperature"

ATTR_ACTUATOR_STATE = "actuator_state"
ATTR_BATTERY_STATE = "battery_state"
ATTR_WINDOW_STATE = "window_state"

BINARY_SENSOR_ATTRS = (ATTR_ACTUATOR_STATE, ATTR_BATTERY_STATE, ATTR_WINDOW_STATE)
SENSOR_ATTRS = (ATTR_HEAT_DEMAND, ATTR_RELAY_DEMAND, ATTR_TEMPERATURE)

EVOZONE_FOLLOW = "follow_schedule"
EVOZONE_TEMPOVER = "temporary_override"
EVOZONE_PERMOVER = "permanent_override"
