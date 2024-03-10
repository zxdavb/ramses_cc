"""Constants for RAMSES integration."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

DOMAIN: Final[str] = "ramses_cc"

STORAGE_VERSION: Final[int] = 1
STORAGE_KEY: Final[str] = DOMAIN

BROKER: Final[str] = "broker"

# Dispatcher signals
SIGNAL_UPDATE = f"{DOMAIN}_update"

# Config
CONF_ADVANCED_FEATURES: Final[str] = "advanced_features"
CONF_COMMANDS: Final[str] = "commands"
CONF_DEV_MODE: Final[str] = "dev_mode"
CONF_MESSAGE_EVENTS: Final[str] = "message_events"
CONF_RAMSES_RF: Final[str] = "ramses_rf"
CONF_SEND_PACKET: Final[str] = "send_packet"
CONF_UNKNOWN_CODES: Final[str] = "unknown_codes"

# State
SZ_CLIENT_STATE: Final[str] = "client_state"
SZ_PACKETS: Final[str] = "packets"
SZ_REMOTES: Final[str] = "remotes"

# Entity/service attributes
ATTR_ACTIVE: Final[str] = "active"
ATTR_ACTIVE_FAULT: Final[str] = "active_fault"
ATTR_ACTUATOR: Final[str] = "enabled"
ATTR_BATTERY: Final[str] = "battery_low"
ATTR_BATTERY_LEVEL: Final[str] = "battery_level"
ATTR_CO2_LEVEL: Final[str] = "co2_level"
ATTR_COMMAND: Final[str] = "command"
ATTR_DELAY_SECS: Final[str] = "delay_secs"
ATTR_DEVICE_ID: Final[str] = "device_id"
ATTR_DIFFERENTIAL: Final[str] = "differential"
ATTR_DURATION: Final[str] = "duration"
ATTR_FAN_RATE: Final[str] = "fan_rate"
ATTR_FAULT_LOG: Final[str] = "fault_log"
ATTR_HEAT_DEMAND: Final[str] = "heat_demand"
ATTR_HUMIDITY: Final[str] = "relative_humidity"
ATTR_INDOOR_HUMIDITY: Final[str] = "indoor_humidity"
ATTR_LATEST_EVENT: Final[str] = "latest_event"
ATTR_LATEST_FAULT: Final[str] = "latest_fault"
ATTR_LOCAL_OVERRIDE: Final[str] = "local_override"
ATTR_MAX_TEMP: Final[str] = "max_temp"
ATTR_MIN_TEMP: Final[str] = "min_temp"
ATTR_MODE: Final[str] = "mode"
ATTR_MULTIROOM: Final[str] = "multiroom_mode"
ATTR_NUM_REPEATS: Final[str] = "num_repeats"
ATTR_OPENWINDOW: Final[str] = "openwindow_function"
ATTR_OVERRUN: Final[str] = "overrun"
ATTR_PERIOD: Final[str] = "period"
ATTR_RELAY_DEMAND: Final[str] = "relay_demand"
ATTR_SCHEDULE: Final[str] = "schedule"
ATTR_SETPOINT: Final[str] = "setpoint"
ATTR_SYSTEM_MODE: Final[str] = "system_mode"
ATTR_TEMPERATURE: Final[str] = "temperature"
ATTR_TIMEOUT: Final[str] = "timeout"
ATTR_UNTIL: Final[str] = "until"
ATTR_WINDOW: Final[str] = "window_open"
ATTR_WORKING_SCHEMA: Final[str] = "working_schema"

# Unofficial presets
PRESET_CUSTOM: Final[str] = "custom"
PRESET_TEMPORARY: Final[str] = "temporary"
PRESET_PERMANENT: Final[str] = "permanent"


# Volume Flow Rate units, these specific unit are not defined in HA v2024.1
class UnitOfVolumeFlowRate(StrEnum):
    """Volume flow rate units (defined by integration)."""

    LITERS_PER_MINUTE: Final[str] = "L/min"
    LITERS_PER_SECOND: Final[str] = "L/s"


class SystemMode(StrEnum):
    """System modes."""

    AUTO: Final[str] = "auto"
    AWAY: Final[str] = "away"
    CUSTOM: Final[str] = "custom"
    DAY_OFF: Final[str] = "day_off"
    DAY_OFF_ECO: Final[str] = "day_off_eco"  # set to Eco when DayOff ends
    ECO_BOOST: Final[str] = "eco_boost"  # Eco, or Boost
    HEAT_OFF: Final[str] = "heat_off"
    RESET: Final[str] = "auto_with_reset"


class ZoneMode(StrEnum):
    """Zone modes."""

    SCHEDULE: Final[str] = "follow_schedule"
    ADVANCED: Final[str] = "advanced_override"  # until the next setpoint
    PERMANENT: Final[str] = "permanent_override"  # indefinitely
    COUNTDOWN: Final[str] = "countdown_override"  # for a number of minutes (max 1,215)
    TEMPORARY: Final[str] = "temporary_override"  # until a given date/time
