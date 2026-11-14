"""Config flow: scan (Classic), pair, and verify the adapter answers."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac

from .bluez import BluezClient, BluezError, FoundDevice
from .const import (
    CONF_IDENTITY,
    DEFAULT_SCAN_INTERVAL,
    DISCOVERY_SECONDS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .elm import ElmError, ElmLink

_LOGGER = logging.getLogger(__name__)

_RFCOMM_HINTS = ("NotAvailable", "not available", "Protocol not supported",
                 "NotSupported")


class ObdBluetoothConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._devices: dict[str, FoundDevice] = {}
        self._address: str | None = None
        self._detail = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._scan()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    async def _scan(self) -> ConfigFlowResult:
        client = BluezClient()
        try:
            await client.start()
            devices = await client.discover(DISCOVERY_SECONDS)
        except BluezError as err:
            _LOGGER.error("Bluetooth scan failed: %s", err)
            return self.async_abort(
                reason="bluez_unavailable", description_placeholders={"error": str(err)}
            )
        finally:
            await client.stop()
        self._devices = {d.address: d for d in devices}
        return await self.async_step_select()

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input.get(CONF_ADDRESS)
            if not address:
                return await self._scan()  # nothing picked: scan again
            await self.async_set_unique_id(format_mac(address))
            self._abort_if_unique_id_configured()
            self._address = address
            return await self.async_step_pair()

        if not self._devices:
            return self.async_show_form(
                step_id="select", data_schema=vol.Schema({}),
                errors={"base": "none_found"},
            )
        options = {
            a: f"{d.name} ({a}){' · paired' if d.paired else ''}"
            for a, d in self._devices.items()
        }
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({vol.Optional(CONF_ADDRESS): vol.In(options)}),
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._address is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            client = BluezClient()
            stage = "pair"
            try:
                await client.start()
                await client.pair(self._address)
                stage = "connect"
                fd = await client.connect_spp(self._address)
                stage = "talk"
                link = ElmLink(fd)
                try:
                    await link.initialize()
                    identity = link.identity
                finally:
                    link.close()
                    await client.disconnect_spp(self._address)
            except (BluezError, ElmError) as err:
                self._detail = str(err)
                _LOGGER.warning("OBD adapter setup failed at %s: %s", stage, err)
                if stage == "connect" and any(h in str(err) for h in _RFCOMM_HINTS):
                    errors["base"] = "rfcomm_missing"
                else:
                    errors["base"] = {
                        "pair": "pair_failed",
                        "connect": "connect_failed",
                        "talk": "no_response",
                    }[stage]
            finally:
                await client.stop()

            if not errors:
                return self.async_create_entry(
                    title=f"OBD-II adapter ({self._address})",
                    data={CONF_ADDRESS: self._address, CONF_IDENTITY: identity},
                )

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "address": self._address,
                "detail": self._detail or "-",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return ObdOptionsFlow()


class ObdOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    )
                }
            ),
        )
