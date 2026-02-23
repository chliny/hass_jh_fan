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
    CMD_STATUS_REPORT,
    CONNECTION_TIMEOUT,
    DOMAIN,
    DP_LEVEL,
    DP_LR_OSCILLATE,
    DP_SWITCH,
    DP_UD_OSCILLATE,
    DP_MODE,
    DP_ANION,
    FRAME_HEAD,
    FRAME_TAIL,
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
            "oscillating_lr": False,
            "oscillating_ud": False,
            "anion": False,
            "mode": 0,
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
        """解析设备通知数据。"""
        if len(data) < 6:
            return

        if data[0] != FRAME_HEAD or data[-1] != FRAME_TAIL:
            return

        # 状态上报 (0x53)
        if data[3] == CMD_STATUS_REPORT:
            status_data = data[4 : data[1] + 2]
            if len(status_data) > 0:
                self._data["power"] = status_data[0] == 1
            if len(status_data) > 1:
                self._data["speed"] = status_data[1]
            if len(status_data) > 3:
                self._data["oscillating_lr"] = status_data[3] == 1
            if len(status_data) > 4:
                self._data["oscillating_ud"] = status_data[4] == 1
            if len(status_data) > 5:
                self._data["anion"] = status_data[5] == 1
            if len(status_data) > 6:
                self._data["mode"] = status_data[6]
            _LOGGER.debug("Status report parsed: %s", self._data)
        else:
            # 单DP点上报
            dp_id = data[3]
            value = data[4]

            if dp_id == DP_SWITCH:
                self._data["power"] = value == 1
            elif dp_id == DP_LEVEL:
                self._data["speed"] = value
            elif dp_id == DP_LR_OSCILLATE:
                self._data["oscillating_lr"] = value == 1
            elif dp_id == DP_UD_OSCILLATE:
                self._data["oscillating_ud"] = value == 1
            elif dp_id == DP_MODE:
                self._data["mode"] = value
            elif dp_id == DP_ANION:
                self._data["anion"] = value == 1

            _LOGGER.debug("Single DP parsed: dp=%d, value=%d", dp_id, value)

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
                # 连接成功后主动获取一次状态
                await self.ble_client.get_status()

        return self._data

    async def async_config_entry_first_refresh(self) -> None:
        await super().async_config_entry_first_refresh()
