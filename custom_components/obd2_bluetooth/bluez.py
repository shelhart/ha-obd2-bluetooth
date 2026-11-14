"""BlueZ D-Bus helpers: Classic discovery, pairing, and SPP (RFCOMM) links.

The SPP link is opened by BlueZ itself (Profile1 / ConnectProfile) and handed
to us as a file descriptor, so this works inside the HA core container even
though its Python has no AF_BLUETOOTH socket support.

No `from __future__ import annotations` in this module: dbus-fast reads the
D-Bus signatures from the string annotations on the service methods.
"""

import asyncio
import logging
import os
from dataclasses import dataclass

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
AGENT_PATH = "/io/obd2_bluetooth/agent"
PROFILE_PATH = "/io/obd2_bluetooth/spp"
LEGACY_PIN = "1234"  # only used if the adapter falls back to legacy PIN pairing

CALL_TIMEOUT = 30
PAIR_TIMEOUT = 60


class BluezError(Exception):
    """A BlueZ / D-Bus call failed."""


@dataclass
class FoundDevice:
    """A Classic device BlueZ knows about."""

    address: str
    name: str
    paired: bool


class _Agent(ServiceInterface):
    """Auto-accepting pairing agent (OBD adapters have no display or keypad)."""

    def __init__(self):
        super().__init__("org.bluez.Agent1")

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: "o") -> "s":
        return LEGACY_PIN

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        pass

    @method()
    def RequestPasskey(self, device: "o") -> "u":
        return int(LEGACY_PIN)

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        pass

    @method()
    def RequestAuthorization(self, device: "o"):
        pass

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        pass

    @method()
    def Cancel(self):
        pass


class _SppProfile(ServiceInterface):
    """SPP client profile; BlueZ calls NewConnection with the RFCOMM fd."""

    def __init__(self):
        super().__init__("org.bluez.Profile1")
        self._waiters = {}
        self.on_disconnect_request = None

    def expect(self, device_path):
        fut = asyncio.get_running_loop().create_future()
        old = self._waiters.pop(device_path, None)
        if old and not old.done():
            old.cancel()
        self._waiters[device_path] = fut
        return fut

    @method()
    def Release(self):
        pass

    @method()
    def NewConnection(self, device: "o", fd: "h", fd_properties: "a{sv}"):
        # dbus-fast never closes received fds, so we take ownership of this
        # one. (Duplicating it instead leaked the original and kept the
        # RFCOMM link open, blocking every reconnect.)
        fut = self._waiters.pop(device, None)
        if fut is None or fut.done():
            _LOGGER.debug("Unexpected SPP connection from %s; closing", device)
            os.close(fd)
            return
        fut.set_result(fd)

    @method()
    def RequestDisconnection(self, device: "o"):
        if self.on_disconnect_request:
            self.on_disconnect_request(device)


def device_path(adapter_path, address):
    return f"{adapter_path}/dev_{address.upper().replace(':', '_')}"


class BluezClient:
    """One system-bus connection with our agent + SPP profile registered."""

    def __init__(self):
        self._bus = None
        self._agent = _Agent()
        self._profile = _SppProfile()
        self._adapter = None

    @property
    def profile(self):
        return self._profile

    async def start(self):
        if self._bus is not None:
            return
        try:
            self._bus = await MessageBus(
                bus_type=BusType.SYSTEM, negotiate_unix_fd=True
            ).connect()
        except Exception as err:  # noqa: BLE001 - surface any bus failure
            raise BluezError(f"Cannot connect to system D-Bus: {err}") from err
        self._bus.export(AGENT_PATH, self._agent)
        self._bus.export(PROFILE_PATH, self._profile)
        await self._call(
            "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent", "os",
            [AGENT_PATH, "NoInputNoOutput"],
        )
        try:
            await self._call(
                "/org/bluez", "org.bluez.ProfileManager1", "RegisterProfile",
                "osa{sv}",
                [
                    PROFILE_PATH,
                    SPP_UUID,
                    {
                        "Name": Variant("s", "OBD-II Bluetooth"),
                        "Role": Variant("s", "client"),
                        "AutoConnect": Variant("b", False),
                    },
                ],
            )
        except BluezError as err:
            if "AlreadyExists" not in str(err):
                raise

    async def stop(self):
        if self._bus is None:
            return
        bus, self._bus = self._bus, None
        try:
            bus.disconnect()  # BlueZ drops our agent/profile with the bus name
        except Exception:  # noqa: BLE001
            pass

    async def _call(self, path, interface, member, signature="", body=None,
                    timeout=CALL_TIMEOUT):
        if self._bus is None:
            raise BluezError("D-Bus not connected")
        msg = Message(
            destination=BLUEZ, path=path, interface=interface, member=member,
            signature=signature, body=body or [],
        )
        try:
            reply = await asyncio.wait_for(self._bus.call(msg), timeout)
        except asyncio.TimeoutError as err:
            raise BluezError(f"{member}: timed out") from err
        if reply.message_type == MessageType.ERROR:
            detail = reply.body[0] if reply.body else ""
            raise BluezError(f"{member}: {reply.error_name}: {detail}")
        return reply.body

    async def _objects(self):
        (objs,) = await self._call(
            "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"
        )
        return objs

    async def adapter_path(self):
        if self._adapter:
            return self._adapter
        adapters = sorted(
            p for p, ifaces in (await self._objects()).items()
            if "org.bluez.Adapter1" in ifaces
        )
        if not adapters:
            raise BluezError("No Bluetooth adapter found")
        self._adapter = adapters[0]
        return self._adapter

    async def known_devices(self):
        adapter = await self.adapter_path()
        found = []
        for path, ifaces in (await self._objects()).items():
            props = ifaces.get("org.bluez.Device1")
            if not props or not path.startswith(adapter + "/"):
                continue
            name = _v(props.get("Name")) or _v(props.get("Alias")) or ""
            # Skip the BLE crowd (sensors, trackers, BMSs...): Classic devices
            # report a Class of Device; also keep anything named OBD*.
            if "Class" not in props and "OBD" not in name.upper():
                continue
            found.append(
                FoundDevice(
                    address=_v(props.get("Address")),
                    name=name or "Unknown",
                    paired=bool(_v(props.get("Paired"))),
                )
            )
        found.sort(key=lambda d: ("OBD" not in d.name.upper(), d.name))
        return found

    async def discover(self, seconds):
        adapter = await self.adapter_path()
        try:
            await self._call(
                adapter, "org.bluez.Adapter1", "SetDiscoveryFilter", "a{sv}",
                [{"Transport": Variant("s", "bredr")}],
            )
        except BluezError as err:
            _LOGGER.debug("SetDiscoveryFilter failed: %s", err)
        await self._call(adapter, "org.bluez.Adapter1", "StartDiscovery")
        try:
            await asyncio.sleep(seconds)
        finally:
            try:
                await self._call(adapter, "org.bluez.Adapter1", "StopDiscovery")
            except BluezError as err:
                _LOGGER.debug("StopDiscovery failed: %s", err)
        return await self.known_devices()

    async def pair(self, address):
        path = device_path(await self.adapter_path(), address)
        paired = await self._get_prop(path, "Paired")
        if not paired:
            try:
                await self._call(path, "org.bluez.Device1", "Pair",
                                 timeout=PAIR_TIMEOUT)
            except BluezError as err:
                if "AlreadyExists" not in str(err):
                    raise
        await self._call(
            path, "org.freedesktop.DBus.Properties", "Set", "ssv",
            ["org.bluez.Device1", "Trusted", Variant("b", True)],
        )

    async def connect_spp(self, address, timeout=20):
        """Open the SPP link; returns an fd the caller owns."""
        path = device_path(await self.adapter_path(), address)
        fut = self._profile.expect(path)
        try:
            await self._call(path, "org.bluez.Device1", "ConnectProfile", "s",
                             [SPP_UUID], timeout=timeout)
            return await asyncio.wait_for(fut, 5)
        except asyncio.TimeoutError as err:
            # ConnectProfile "succeeded" without handing us a socket: BlueZ
            # still has a stale SPP link up. Tear it down so the retry works.
            await self.disconnect_spp(address)
            raise BluezError("stale SPP link; disconnected it, will retry") from err
        finally:
            if not fut.done():
                fut.cancel()

    async def disconnect_spp(self, address):
        """Tell BlueZ to drop the SPP link (closing our fd alone doesn't)."""
        try:
            path = device_path(await self.adapter_path(), address)
            await self._call(path, "org.bluez.Device1", "DisconnectProfile",
                             "s", [SPP_UUID], timeout=10)
        except BluezError as err:
            _LOGGER.debug("DisconnectProfile: %s", err)

    async def _get_prop(self, path, name):
        (value,) = await self._call(
            path, "org.freedesktop.DBus.Properties", "Get", "ss",
            ["org.bluez.Device1", name],
        )
        return _v(value)


def _v(value):
    return value.value if isinstance(value, Variant) else value
