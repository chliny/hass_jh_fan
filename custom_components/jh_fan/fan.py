"""Fan platform for JH Voice Fan integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from propcache.api import cached_property

from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble_client import JHFanBLE
from .const import (
    DEFAULT_NAME,
    DP_CHILD_LOCK,
    DP_LEVEL,
    DP_LR_OSCILLATE,
    DP_NATURAL_WIND,
    DP_SWITCH,
    DP_UD_OSCILLATE,
    DOMAIN,
    SPEED_COUNT,
)
from .coordinator import JHFanCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    coordinator = JHFanCoordinator(hass, address)
    await coordinator.async_config_entry_first_refresh()

    async_add_entities([JHFanEntity(coordinator, address, name)])


class JHFanEntity(CoordinatorEntity[JHFanCoordinator], FanEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_speed_count = SPEED_COUNT
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.OSCILLATE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: JHFanCoordinator,
        address: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._address = address
        self._attr_unique_id = format_mac(address)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": name,
            "manufacturer": "JH Voice",
            "model": "Smart Fan",
        }

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.get("power", False)

    @cached_property
    def percentage(self) -> int | None:
        if not self.is_on:
            return 0
        speed = self.coordinator.data.get("speed", 0)
        if speed <= 0:
            return 0
        return int((speed / SPEED_COUNT) * 100)

    @property
    def oscillating(self) -> bool | None:
        return self.coordinator.data.get("oscillating", False)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.coordinator.ble_client.turn_on()
        if percentage is not None:
            speed = int((percentage / 100) * SPEED_COUNT)
            speed = max(1, min(speed, SPEED_COUNT))
            await self.coordinator.ble_client.set_speed(speed)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.ble_client.turn_off()
        await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return

        if not self.is_on:
            await self.coordinator.ble_client.turn_on()

        speed = int((percentage / 100) * SPEED_COUNT)
        speed = max(1, min(speed, SPEED_COUNT))
        await self.coordinator.ble_client.set_speed(speed)
        await self.coordinator.async_request_refresh()

    async def async_oscillate(self, oscillating: bool) -> None:
        await self.coordinator.ble_client.set_oscillate_lr(oscillating)
        await self.coordinator.async_request_refresh()
