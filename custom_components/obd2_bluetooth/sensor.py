"""Sensors for the OBD-II adapter."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import ObdConfigEntry
from .entity import ObdEntity

M = SensorStateClass.MEASUREMENT


def _temp(key: str, name: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key, name=name, device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=M,
    )


def _pct(key: str, name: str, icon: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key, name=name, icon=icon, native_unit_of_measurement=PERCENTAGE,
        state_class=M, suggested_display_precision=0,
    )


def _kpa(key: str, name: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key, name=name, device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.KPA, state_class=M,
    )


SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="adapter_voltage", name="Starter battery voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=M, suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="ecu_voltage", name="ECU voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=M, suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="rpm", name="Engine RPM", icon="mdi:engine",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE, state_class=M,
    ),
    SensorEntityDescription(
        key="speed", name="Vehicle speed", device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR, state_class=M,
    ),
    _temp("coolant_temp", "Coolant temperature"),
    _temp("oil_temp", "Oil temperature"),
    _temp("intake_temp", "Intake air temperature"),
    _temp("ambient_temp", "Ambient temperature"),
    _pct("fuel_level", "Fuel level", "mdi:gas-station"),
    _pct("engine_load", "Engine load", "mdi:engine"),
    _pct("throttle", "Throttle position", "mdi:speedometer"),
    _kpa("intake_pressure", "Intake manifold pressure"),
    _kpa("baro_pressure", "Barometric pressure"),
    SensorEntityDescription(
        key="maf", name="Mass air flow", icon="mdi:weather-windy",
        native_unit_of_measurement="g/s", state_class=M,
    ),
    SensorEntityDescription(
        key="fuel_rate", name="Fuel rate", icon="mdi:fuel",
        native_unit_of_measurement="L/h", state_class=M,
    ),
    SensorEntityDescription(
        key="run_time", name="Run time since start",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS, state_class=M,
    ),
    SensorEntityDescription(
        key="dtc_count", name="Stored trouble codes", icon="mdi:car-wrench",
        state_class=M, entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ObdConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ObdSensor(coordinator, d) for d in SENSORS)


class ObdSensor(ObdEntity, SensorEntity):
    def __init__(self, coordinator, description: SensorEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        return self._value
