# OBD-II Bluetooth (ELM327) for Home Assistant

[![hacs][hacs-badge]][hacs-url] [![Buy me a coffee][bmc-badge]][bmc-url]

Read live engine data from a **Bluetooth Classic ELM327-compatible OBD-II adapter** (OBDLink MX, Vgate, Veepeak and others) directly through Home Assistant's own Bluetooth radio. You don't need an extra bridge, add-on, MQTT or phone app.

Home Assistant's Bluetooth system (BlueZ) opens the adapter's serial (SPP/RFCOMM) link and hands it to the integration, so it works on Home Assistant OS, including on a Raspberry Pi.

> Unofficial. Not affiliated with or endorsed by OBD Solutions, LLC, ELM Electronics or any adapter maker. OBDLink is a trademark of OBD Solutions, LLC.

## What you get

| Entity | Notes |
|---|---|
| Starter battery voltage | The adapter's own reading (`ATRV`). Works whenever the adapter is awake, even if the engine computer isn't answering. |
| Engine running | On when RPM > 0. Goes **unavailable** (not off) when the adapter can't be reached, so a dropped link never reads as "engine off". |
| Check engine light, stored trouble codes | From mode 01 PID 01. |
| Engine RPM, vehicle speed, engine load, throttle | |
| Coolant, oil, intake air and ambient temperature | |
| Fuel level, fuel rate | |
| Intake manifold and barometric pressure, mass air flow | |
| ECU voltage, run time since start | |
| Adapter connected | Diagnostic. |

The integration asks the vehicle which readings it supports and only polls those. On vehicles with several control modules (engine and transmission), it merges every module's answer. Readings your vehicle doesn't report stay unavailable; disable them if you like.

## Requirements

- Home Assistant OS or Supervised on Linux with BlueZ, and a working local Bluetooth adapter. The built-in Raspberry Pi Bluetooth works.
- A **Bluetooth Classic** (SPP) ELM327-compatible adapter. BLE-only and Wi-Fi adapters are not supported.
- The host's Bluetooth stack must support RFCOMM. The setup flow checks this and tells you if it doesn't.

## Install

### HACS (custom repository)

1. In HACS, open the ⋮ menu, choose **Custom repositories**, and add `https://github.com/shelhart/ha-obd2-bluetooth` with type **Integration**.
2. Install **OBD-II Bluetooth (ELM327)** and restart Home Assistant.

### Manual

Copy `custom_components/obd2_bluetooth/` to `/config/custom_components/obd2_bluetooth/` and restart Home Assistant.

## Set up

1. Turn the vehicle's ignition **on** so the adapter wakes up.
2. If your adapter has a pairing button, press it.
3. Go to **Settings → Devices & services → Add integration → OBD-II Bluetooth (ELM327)** and submit. Home Assistant scans for about 12 seconds.
4. Pick your adapter and submit. Home Assistant pairs with it, opens the serial link and checks that it answers.

You only pair once. After that, Home Assistant reconnects whenever the adapter wakes up.

## Behavior

- **Poll interval**: 5 s by default. Change it under the integration's **Configure** option (2–60 s).
- **Adapter asleep**: reconnect attempts back off from 15 s up to 5 min. Each failed attempt ties up the radio for about 5 s, which would otherwise disrupt Bluetooth LE scanning for your other devices.
- **One connection at a time**: while Home Assistant holds the link, phone apps can't connect to the adapter. Disable the integration entry to free it.

## Troubleshooting

| Setup error | Meaning |
|---|---|
| Can't open serial (RFCOMM) links | The host's kernel or BlueZ lacks RFCOMM. A direct connection isn't possible on that install. |
| Pairing failed | The adapter's pairing window closed. Put it back in pairing mode and try again. |
| Paired, link didn't open | The adapter is asleep. Turn the ignition on and retry. |

For more detail, add this to `configuration.yaml`, restart, and check the log:

```yaml
logger:
  logs:
    custom_components.obd2_bluetooth: debug
```

## Support

If this is useful to you, you can [buy me a coffee][bmc-url]. Bug reports and pull requests are welcome.

## License

MIT

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs-url]: https://hacs.xyz
[bmc-badge]: https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?logo=buymeacoffee&logoColor=black
[bmc-url]: https://www.buymeacoffee.com/shelhart
