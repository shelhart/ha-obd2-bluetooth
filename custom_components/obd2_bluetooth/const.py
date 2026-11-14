"""Constants for the OBD-II Bluetooth (ELM327) integration."""

DOMAIN = "obd2_bluetooth"

CONF_IDENTITY = "identity"

DEFAULT_SCAN_INTERVAL = 5  # seconds between polls while connected
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 60

DISCOVERY_SECONDS = 12  # Bluetooth Classic inquiry time during setup

# Reconnect backoff while the adapter is asleep / out of range (seconds).
# Each failed page attempt ties up the radio for ~5 s, so don't hammer it.
BACKOFF_MIN = 15
BACKOFF_MAX = 300

# How often to retry PID support detection while the ECU isn't answering.
DETECT_RETRY = 30
