"""Coordinator for JH Voice Fan."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .ble_client import JHFanBLE
from .const import DOMAIN, UpdateInterval

_LOGGER = logging.getLogger(__name__)


class JHFanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{address}",
            update_interval=UpdateInterval,
        )
        self._address = address
        self.ble_client = JHFanBLE(address, hass)
        self._data: dict[str, Any] = {
            "power": False,
            "speed": 0,
            "oscillating_lr": False,
            "oscillating_ud": False,
            "timing_power": 0,
            "voice_announce": False,
        }

        self._unsub_bluetooth: Any = None

    @callback
    def _async_handle_bluetooth_event(
        self,
        service_info: BluetoothServiceInfoBleak,
        change: BluetoothChange,
    ) -> None:
        if change == BluetoothChange.ADVERTISEMENT:
            pass

    async def _async_update_data(self) -> dict[str, Any]:
        data = await self.ble_client.get_status()
        if data:
            self._data.update(data)
        return self._data

    async def async_config_entry_first_refresh(self) -> None:
        await super().async_config_entry_first_refresh()
