"""Binary sensors for the OBD-II adapter."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ObdConfigEntry
from .entity import ObdEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ObdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities(
        [AdapterConnected(c), EngineRunning(c), CheckEngine(c)]
    )


class AdapterConnected(ObdEntity, BinarySensorEntity):
    """On while the Bluetooth link to the adapter is up."""

    _attr_name = "Adapter connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("connected"))


class EngineRunning(ObdEntity, BinarySensorEntity):
    """RPM > 0. Unavailable (not off) when the adapter can't be reached."""

    _attr_name = "Engine running"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rpm")

    @property
    def available(self) -> bool:
        data = self.coordinator.data or {}
        return self.coordinator.last_update_success and bool(data.get("connected"))

    @property
    def is_on(self) -> bool:
        rpm = self._value
        return rpm is not None and rpm > 0


class CheckEngine(ObdEntity, BinarySensorEntity):
    _attr_name = "Check engine light"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "check_engine")

    @property
    def is_on(self) -> bool:
        return bool(self._value)
