"""Minimal async ELM327/STN command layer over a raw RFCOMM file descriptor."""

from __future__ import annotations

import asyncio
import os

from .pids import parse_support_bitmap


class ElmError(Exception):
    """Link dropped, timed out, or the adapter misbehaved."""


class ElmTimeout(ElmError):
    """The adapter didn't finish a reply in time (link may still be fine)."""


class ElmLink:
    """Request/response over the adapter's '>' prompt protocol."""

    def __init__(self, fd: int) -> None:
        self._fd = fd
        os.set_blocking(fd, False)
        self._loop = asyncio.get_running_loop()
        self._buf = bytearray()
        self._lock = asyncio.Lock()
        self._closed = False
        self.version: str | None = None  # ATI, e.g. "ELM327 v1.3a"
        self.device: str | None = None  # STI, e.g. "STN1110 v4.x"

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self._fd)
        except OSError:
            pass

    @property
    def identity(self) -> str:
        return self.device or self.version or "ELM327 adapter"

    async def initialize(self) -> None:
        await self.command("ATZ", timeout=5)
        for cmd in ("ATE0", "ATL0", "ATS0", "ATH0", "ATSP0"):
            await self.command(cmd)
        self.version = " ".join(await self.command("ATI")) or None
        try:
            sti = " ".join(await self.command("STI"))
            self.device = sti if sti and "?" not in sti else None
        except ElmError:
            self.device = None

    async def voltage(self) -> float | None:
        """Adapter-measured voltage on OBD pin 16 (the starter battery)."""
        for line in await self.command("ATRV"):
            try:
                return float(line.upper().rstrip("V"))
            except ValueError:
                continue
        return None

    async def query_all(self, pid: int, timeout: float = 5.0) -> list[bytes]:
        """Mode 01 request; one payload per ECU that answered (CAN buses
        often have the engine and transmission modules both reply)."""
        lines = await self.command(f"01{pid:02X}", timeout)
        prefix = f"41{pid:02X}"
        out: list[bytes] = []
        for line in lines:
            hexstr = line.replace(" ", "")
            if hexstr.startswith(prefix):
                try:
                    out.append(bytes.fromhex(hexstr[4:]))
                except ValueError:
                    continue
        return out

    async def query(self, pid: int, timeout: float = 5.0) -> bytes | None:
        """Mode 01 request; first answer, or None if no ECU answered."""
        answers = await self.query_all(pid, timeout)
        return answers[0] if answers else None

    async def supported_pids(self) -> set[int]:
        supported: set[int] = set()
        for base in (0x00, 0x20, 0x40):
            # First call may search protocols. Union every ECU's bitmap: which
            # module answers first varies between boots.
            answers = await self.query_all(base, timeout=10)
            if not answers:
                break
            for raw in answers:
                supported |= parse_support_bitmap(base, raw)
            if base + 0x20 not in supported:
                break
        return supported

    async def command(self, cmd: str, timeout: float = 3.0) -> list[str]:
        async with self._lock:
            if self._closed:
                raise ElmError("link closed")
            self._drain()
            self._write((cmd + "\r").encode())
            deadline = self._loop.time() + timeout
            while b">" not in self._buf:
                remaining = deadline - self._loop.time()
                if remaining <= 0:
                    raise ElmTimeout(f"timeout waiting for reply to {cmd}")
                self._buf += await self._read_some(remaining, cmd)
            raw = bytes(self._buf[: self._buf.index(b">")])
            self._buf.clear()
        text = raw.decode("ascii", "ignore").replace("\x00", "")
        lines = [ln.strip() for ln in text.replace("\n", "\r").split("\r")]
        return [ln for ln in lines if ln and ln != cmd and ln != "SEARCHING..."]

    def _write(self, data: bytes) -> None:
        try:
            while data:
                sent = os.write(self._fd, data)
                data = data[sent:]
        except OSError as err:
            self.close()
            raise ElmError(f"write failed: {err}") from err

    def _drain(self) -> None:
        """Discard late bytes from a previously timed-out command."""
        self._buf.clear()
        while True:
            try:
                chunk = os.read(self._fd, 1024)
            except BlockingIOError:
                return
            except OSError as err:
                self.close()
                raise ElmError(f"read failed: {err}") from err
            if not chunk:
                self.close()
                raise ElmError("link closed by adapter")

    async def _read_some(self, timeout: float, cmd: str) -> bytes:
        fut: asyncio.Future[None] = self._loop.create_future()

        def _ready() -> None:
            if not fut.done():
                fut.set_result(None)

        self._loop.add_reader(self._fd, _ready)
        try:
            await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError as err:
            raise ElmTimeout(f"timeout waiting for reply to {cmd}") from err
        finally:
            self._loop.remove_reader(self._fd)
        try:
            data = os.read(self._fd, 1024)
        except BlockingIOError:
            return b""
        except OSError as err:
            self.close()
            raise ElmError(f"read failed: {err}") from err
        if not data:
            self.close()
            raise ElmError("link closed by adapter")
        return data
