"""Constants for RAMSES integration."""
from __future__ import annotations

from enum import StrEnum

DOMAIN = "ramses_cc"

STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN

# Dispatcher signals
SIGNAL_NEW_DEVICES = f"{DOMAIN}_new_devices_" + "{}"
SIGNAL_UPDATE = f"{DOMAIN}_update"

# Config
CONF_ADVANCED_FEATURES = "advanced_features"
CONF_COMMANDS = "commands"
CONF_DEV_MODE = "dev_mode"
CONF_MESSAGE_EVENTS = "message_events"
CONF_RAMSES_RF = "ramses_rf"
CONF_SCHEMA = "schema"
CONF_SEND_PACKET = "send_packet"
CONF_UNKNOWN_CODES = "unknown_codes"

# State
SZ_CLIENT_STATE = "client_state"
SZ_PACKETS = "packets"
SZ_REMOTES = "remotes"

# Entity/service attributes
ATTR_ACTIVE = "active"
ATTR_ACTIVE_FAULT = "active_fault"
ATTR_ACTUATOR = "enabled"
ATTR_BATTERY = "battery_low"
ATTR_BATTERY_LEVEL = "battery_level"
ATTR_CO2_LEVEL = "co2_level"
ATTR_COMMAND = "command"
ATTR_DELAY_SECS = "delay_secs"
ATTR_DEVICE_ID = "device_id"
ATTR_DIFFERENTIAL = "differential"
ATTR_DURATION = "duration"
ATTR_FAN_RATE = "fan_rate"
ATTR_FAULT_LOG = "fault_log"
ATTR_HEAT_DEMAND = "heat_demand"
ATTR_HUMIDITY = "relative_humidity"
ATTR_INDOOR_HUMIDITY = "indoor_humidity"
ATTR_LATEST_EVENT = "latest_event"
ATTR_LATEST_FAULT = "latest_fault"
ATTR_LOCAL_OVERRIDE = "local_override"
ATTR_MAX_TEMP = "max_temp"
ATTR_MIN_TEMP = "min_temp"
ATTR_MODE = "mode"
ATTR_MULTIROOM = "multiroom_mode"
ATTR_NUM_REPEATS = "num_repeats"
ATTR_OPENWINDOW = "openwindow_function"
ATTR_OVERRUN = "overrun"
ATTR_PERIOD = "period"
ATTR_RELAY_DEMAND = "relay_demand"
ATTR_SCHEDULE = "schedule"
ATTR_SETPOINT = "setpoint"
ATTR_SYSTEM_MODE = "system_mode"
ATTR_TEMPERATURE = "temperature"
ATTR_TIMEOUT = "timeout"
ATTR_UNTIL = "until"
ATTR_WINDOW = "window_open"
ATTR_WORKING_SCHEMA = "working_schema"

# Unofficial presets
PRESET_CUSTOM = "custom"
PRESET_TEMPORARY = "temporary"
PRESET_PERMANENT = "permanent"

# Services
SVC_DELETE_COMMAND = "delete_command"
SVC_BIND_DEVICE = "bind_device"
SVC_FORCE_UPDATE = "force_update"
SVC_GET_DHW_SCHEDULE = "get_dhw_schedule"
SVC_GET_ZONE_SCHEDULE = "get_zone_schedule"
SVC_LEARN_COMMAND = "learn_command"
SVC_PUT_CO2_LEVEL = "put_co2_level"
SVC_PUT_DHW_TEMP = "put_dhw_temp"
SVC_PUT_INDOOR_HUMIDITY = "put_indoor_humidity"
SVC_PUT_ROOM_TEMP = "put_room_temp"
SVC_RESET_DHW_MODE = "reset_dhw_mode"
SVC_RESET_DHW_PARAMS = "reset_dhw_params"
SVC_RESET_SYSTEM_MODE = "reset_system_mode"
SVC_RESET_ZONE_CONFIG = "reset_zone_config"
SVC_RESET_ZONE_MODE = "reset_zone_mode"
SVC_SEND_COMMAND = "send_command"
SVC_SEND_PACKET = "send_packet"
SVC_SET_DHW_BOOST = "set_dhw_boost"
SVC_SET_DHW_MODE = "set_dhw_mode"
SVC_SET_DHW_PARAMS = "set_dhw_params"
SVC_SET_DHW_SCHEDULE = "set_dhw_schedule"
SVC_SET_SYSTEM_MODE = "set_system_mode"
SVC_SET_ZONE_CONFIG = "set_zone_config"
SVC_SET_ZONE_MODE = "set_zone_mode"
SVC_SET_ZONE_SCHEDULE = "set_zone_schedule"


# Volume Flow Rate units, these specific unit are not defined in HA v2024.1
class UnitOfVolumeFlowRate(StrEnum):
    """Volume flow rate units (defined by integration)."""

    LITERS_PER_MINUTE = "L/min"
    LITERS_PER_SECOND = "L/s"


class SystemMode(StrEnum):
    """System modes."""

    AUTO = "auto"
    AWAY = "away"
    CUSTOM = "custom"
    DAY_OFF = "day_off"
    DAY_OFF_ECO = "day_off_eco"  # set to Eco when DayOff ends
    ECO_BOOST = "eco_boost"  # Eco, or Boost
    HEAT_OFF = "heat_off"
    RESET = "auto_with_reset"


class ZoneMode(StrEnum):
    """Zone modes."""

    SCHEDULE = "follow_schedule"
    ADVANCED = "advanced_override"  # until the next setpoint
    PERMANENT = "permanent_override"  # indefinitely
    COUNTDOWN = "countdown_override"  # for a number of minutes (max 1,215)
    TEMPORARY = "temporary_override"  # until a given date/time
