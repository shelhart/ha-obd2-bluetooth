"""Connection management and polling for the OBD-II adapter."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .bluez import BluezClient, BluezError
from .const import (
    BACKOFF_MAX,
    BACKOFF_MIN,
    CONF_IDENTITY,
    DEFAULT_SCAN_INTERVAL,
    DETECT_RETRY,
    DOMAIN,
)
from .elm import ElmError, ElmLink, ElmTimeout
from .pids import PIDS, PROBE_PID, decode

_LOGGER = logging.getLogger(__name__)


def _offline() -> dict[str, Any]:
    return {"connected": False, "values": {}}


class ObdCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keeps one SPP link open and polls the adapter + ECU."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, bluez: BluezClient
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.address: str = entry.data[CONF_ADDRESS]
        self.identity: str = entry.data.get(CONF_IDENTITY) or "ELM327 adapter"
        self._bluez = bluez
        self._link: ElmLink | None = None
        self._supported: set[int] | None = None
        self._next_attempt = 0.0
        self._next_detect = 0.0
        self._backoff = BACKOFF_MIN
        # BlueZ is already tearing the link down here; just release our fd.
        bluez.profile.on_disconnect_request = lambda _dev: self._close_fd()

    async def _async_update_data(self) -> dict[str, Any]:
        if (self._link is None or self._link.closed) and not await self._connect():
            return _offline()
        link = self._link
        assert link is not None
        values: dict[str, Any] = {}
        try:
            values["adapter_voltage"] = await link.voltage()
            now = time.monotonic()
            if self._supported is None and now >= self._next_detect:
                found = await link.supported_pids()
                if found:
                    self._supported = found
                    _LOGGER.debug("Supported PIDs: %s",
                                  " ".join(f"{p:02X}" for p in sorted(found)))
                else:
                    self._next_detect = now + DETECT_RETRY
            if self._supported:
                values.update(await self._poll(link, self._supported))
        except ElmError as err:
            _LOGGER.debug("Lost link to %s: %s", self.address, err)
            await self._drop_link()
            self._next_attempt = time.monotonic() + BACKOFF_MIN
            return _offline()
        return {"connected": True, "values": values}

    async def _poll(self, link: ElmLink, supported: set[int]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        order = [PROBE_PID] + sorted(p for p in PIDS if p != PROBE_PID)
        for pid in order:
            if pid not in supported:
                continue
            try:
                raw = await link.query(pid)
            except ElmTimeout:
                # One slow PID isn't a dead link (ATRV above proved it's up).
                _LOGGER.debug("PID %02X timed out", pid)
                raw = None
            if raw is None:
                if pid == PROBE_PID:
                    break  # ECU asleep; skip the rest this cycle
                continue
            out.update(decode(pid, raw))
        return out

    async def _connect(self) -> bool:
        now = time.monotonic()
        if now < self._next_attempt:
            return False
        try:
            fd = await self._bluez.connect_spp(self.address)
        except BluezError as err:
            self._schedule_retry(now, err)
            return False
        link = ElmLink(fd)
        try:
            await link.initialize()
        except ElmError as err:
            link.close()
            await self._bluez.disconnect_spp(self.address)
            self._schedule_retry(now, err)
            return False
        self._link = link
        self._backoff = BACKOFF_MIN
        _LOGGER.info("Connected to %s (%s)", self.address, link.identity)
        return True

    def _schedule_retry(self, now: float, err: Exception) -> None:
        self._next_attempt = now + self._backoff
        _LOGGER.debug("Connect to %s failed (%s); retry in %ss",
                      self.address, err, self._backoff)
        self._backoff = min(self._backoff * 2, BACKOFF_MAX)

    def _close_fd(self) -> None:
        if self._link is not None:
            self._link.close()
            self._link = None

    async def _drop_link(self) -> None:
        had_link = self._link is not None
        self._close_fd()
        if had_link:
            await self._bluez.disconnect_spp(self.address)

    async def async_close(self) -> None:
        await self._drop_link()
        await self._bluez.stop()
