"""Coordinator for JH Voice Fan."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothChange,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .ble_client import JHFanBLE
from .const import (
    CONNECTION_TIMEOUT,
    DOMAIN,
    DP_LEVEL,
    DP_LR_OSCILLATE,
    DP_SWITCH,
)

_LOGGER = logging.getLogger(__name__)


class JHFanCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{address}",
            update_interval=None,
        )
        self._address = address
        self.ble_client = JHFanBLE(address)
        self._data: dict[str, Any] = {
            "power": False,
            "speed": 0,
            "oscillating": False,
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

    def _parse_notification(self, data: bytes) -> None:
        if len(data) < 6:
            return

        if data[0] != 0xAA or data[-1] != 0x55:
            return

        dp_id = data[3]
        value = data[4]

        if dp_id == DP_SWITCH:
            self._data["power"] = value == 1
        elif dp_id == DP_LEVEL:
            self._data["speed"] = value
        elif dp_id == DP_LR_OSCILLATE:
            self._data["oscillating"] = value == 1

        self.async_set_updated_data(self._data)

    async def _async_update_data(self) -> dict[str, Any]:
        ble_device = async_ble_device_from_address(self.hass, self._address)
        if not ble_device:
            _LOGGER.debug("No BLE device found for %s", self._address)
            return self._data

        if not self.ble_client.connected:
            connected = await self.ble_client.connect(ble_device)
            if connected:
                self.ble_client.register_callback(self._parse_notification)

        return self._data

    async def async_config_entry_first_refresh(self) -> None:
        await super().async_config_entry_first_refresh()
