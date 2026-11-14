"""Mode 01 PID decoders (SAE J1979)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# Polled first each cycle; if it gets no answer the ECU is asleep and the
# rest of the cycle is skipped.
PROBE_PID = 0x0C


def _ab(d: bytes) -> int:
    return d[0] * 256 + d[1]


PIDS: dict[int, Callable[[bytes], dict[str, Any]]] = {
    0x01: lambda d: {"check_engine": bool(d[0] & 0x80), "dtc_count": d[0] & 0x7F},
    0x04: lambda d: {"engine_load": round(d[0] * 100 / 255, 1)},
    0x05: lambda d: {"coolant_temp": d[0] - 40},
    0x0B: lambda d: {"intake_pressure": d[0]},
    0x0C: lambda d: {"rpm": round(_ab(d) / 4)},
    0x0D: lambda d: {"speed": d[0]},
    0x0F: lambda d: {"intake_temp": d[0] - 40},
    0x10: lambda d: {"maf": round(_ab(d) / 100, 2)},
    0x11: lambda d: {"throttle": round(d[0] * 100 / 255, 1)},
    0x1F: lambda d: {"run_time": _ab(d)},
    0x2F: lambda d: {"fuel_level": round(d[0] * 100 / 255, 1)},
    0x33: lambda d: {"baro_pressure": d[0]},
    0x42: lambda d: {"ecu_voltage": round(_ab(d) / 1000, 2)},
    0x46: lambda d: {"ambient_temp": d[0] - 40},
    0x5C: lambda d: {"oil_temp": d[0] - 40},
    0x5E: lambda d: {"fuel_rate": round(_ab(d) / 20, 2)},
}


def decode(pid: int, data: bytes) -> dict[str, Any]:
    """Decode one PID response; returns {} if the payload is short/garbled."""
    func = PIDS.get(pid)
    if func is None:
        return {}
    try:
        return func(data)
    except IndexError:
        return {}


def parse_support_bitmap(base: int, data: bytes) -> set[int]:
    """Decode a 0x00/0x20/0x40 'PIDs supported' bitmap."""
    if len(data) < 4:
        return set()
    bits = int.from_bytes(data[:4], "big")
    return {base + i + 1 for i in range(32) if bits & (1 << (31 - i))}
