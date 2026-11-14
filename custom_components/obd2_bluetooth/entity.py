"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ObdCoordinator


class ObdEntity(CoordinatorEntity[ObdCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ObdCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(CONNECTION_BLUETOOTH, coordinator.address)},
            name="OBD-II adapter",
            model=coordinator.identity,
        )

    @property
    def _value(self):
        data = self.coordinator.data or {}
        return data.get("values", {}).get(self._key)

    @property
    def available(self) -> bool:
        return super().available and self._value is not None
