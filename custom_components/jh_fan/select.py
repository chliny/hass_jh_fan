"""Select entities for JH Voice Fan."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import JHFanCoordinator
from .const import DEFAULT_NAME, DOMAIN, TIMING_OPTIONS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities."""
    coordinator: JHFanCoordinator = hass.data[DOMAIN][entry.entry_id]
    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    entities = [
        JHFanSelectTimingOff(coordinator, address, name),
    ]
    async_add_entities(entities)


class JHFanSelectTimingOff(CoordinatorEntity[JHFanCoordinator], SelectEntity):
    """定时关机选择"""

    def __init__(self, coordinator: JHFanCoordinator, address: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "timing_power"
        self._attr_unique_id = f"{format_mac(address)}_select_timing_off"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_options = TIMING_OPTIONS
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": name,
            "manufacturer": "JH Voice",
            "model": "Smart Fan",
        }

    @property
    def current_option(self) -> str | None:
        hours = self.coordinator.data.get(self._attr_name, 0)
        if hours >= len(TIMING_OPTIONS):
            return "未知"
        return TIMING_OPTIONS[hours]

    async def async_select_option(self, option: str) -> None:
        if option == "关闭":
            hours = 0
        else:
            try:
                hours = TIMING_OPTIONS.index(option)
            except ValueError:
                return
        await self.coordinator.ble_client.set_timing_off(hours)
        # 刷新状态
        await self.coordinator.async_request_refresh()
