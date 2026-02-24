"""Switch entities for JH Voice Fan."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import JHFanCoordinator
from .const import DEFAULT_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities."""
    coordinator: JHFanCoordinator = hass.data[DOMAIN][entry.entry_id]
    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    entities = [
        JHFanSwitchLR(coordinator, address, name),
        JHFanSwitchUD(coordinator, address, name),
        JHFanSwitchVoice(coordinator, address, name),
    ]
    async_add_entities(entities)


class JHFanSwitchLR(CoordinatorEntity[JHFanCoordinator], SwitchEntity):
    """左右摇头开关"""

    def __init__(self, coordinator: JHFanCoordinator, address: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "oscillating_lr"
        self._attr_unique_id = f"{format_mac(address)}_switch_lr_oscillate"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": name,
            "manufacturer": "JH Voice",
            "model": "Smart Fan",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get(self._attr_name, False)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.ble_client.set_oscillate_lr(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.ble_client.set_oscillate_lr(False)

    async def async_toggle(self, **kwargs) -> None:
        current = self.is_on
        if current:
            await self.async_turn_off()
        else:
            await self.async_turn_on()


class JHFanSwitchUD(CoordinatorEntity[JHFanCoordinator], SwitchEntity):
    """上下摇头开关"""

    def __init__(self, coordinator: JHFanCoordinator, address: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "oscillating_ud"
        self._attr_unique_id = f"{format_mac(address)}_switch_ud_oscillate"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": name,
            "manufacturer": "JH Voice",
            "model": "Smart Fan",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get(self._attr_name, False)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.ble_client.set_oscillate_ud(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.ble_client.set_oscillate_ud(False)

    async def async_toggle(self, **kwargs) -> None:
        current = self.is_on
        if current:
            await self.async_turn_off()
        else:
            await self.async_turn_on()


class JHFanSwitchVoice(CoordinatorEntity[JHFanCoordinator], SwitchEntity):
    """语音播报开关"""

    def __init__(self, coordinator: JHFanCoordinator, address: str, name: str) -> None:
        super().__init__(coordinator)
        self._attr_has_entity_name = True
        self._attr_name = "voice_announce"
        self._attr_unique_id = f"{format_mac(address)}_switch_voice_announce"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = {
            "identifiers": {(DOMAIN, address)},
            "name": name,
            "manufacturer": "JH Voice",
            "model": "Smart Fan",
        }

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get(self._attr_name, False)

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.ble_client.set_voice_announce(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.ble_client.set_voice_announce(False)

    async def async_toggle(self, **kwargs) -> None:
        current = self.is_on
        if current:
            await self.async_turn_off()
        else:
            await self.async_turn_on()
