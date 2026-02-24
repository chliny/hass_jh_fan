"""BLE client for JH Voice Fan."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
)
from homeassistant.core import HomeAssistant

from .const import (
    CMD_STATUS_REPORT,
    COMMAND_DELAY,
    CONNECTION_TIMEOUT,
    DEFAULT_ATTEMPTS,
    DP_GET_ALL,
    DP_LEVEL,
    DP_LR_OSCILLATE,
    DP_SWITCH,
    DP_UD_OSCILLATE,
    DP_VOICE_ANNOUNCE,
    DP_TIMING_OFF,
    FRAME_HEAD,
    FRAME_TAIL,
    NOTIFY_CHAR_UUID,
    WRITE_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_DELAY = 2.0


def checksum(data: list[int]) -> int:
    return sum(data) % 256


class JHFanBLE:
    def __init__(self, address: str, hass: HomeAssistant | None = None) -> None:
        self._address = address
        self._hass = hass
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._seq = 1
        self._connected = False
        self._status_event = asyncio.Event()
        self._last_status: dict[str, Any] | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def _next_seq(self) -> int:
        seq: int = self._seq
        self._seq = 255 if seq >= 255 else seq + 1
        return seq

    def _build_frame(self, dp_id: int, value: int) -> bytes:
        seq = self._next_seq()
        payload = [3, seq, dp_id, value]
        cs = checksum(payload)
        frame = [FRAME_HEAD, *payload, cs, FRAME_TAIL]
        return bytes(frame)

    def _parse_status_report(self, data: bytes) -> dict[str, Any] | None:
        """解析设备状态上报数据。

        数据帧格式: [0xAA, 长度, 序列号, 0x53, 状态数据..., 校验和, 0x55]
        状态数据按DP点顺序排列，索引 = DP点 - 1
        """
        if len(data) < 6:
            return None

        if data[0] != FRAME_HEAD or data[-1] != FRAME_TAIL:
            return None

        # 状态上报 (0x53)
        if data[3] != CMD_STATUS_REPORT:
            return None

        status: dict[str, Any] = {}
        # JavaScript slice: data.slice(4, length + 2) 是左闭右开
        # Python 切片需要用 data[4:length + 3] 才能获取相同范围
        status_data = data[4: data[1] + 3]
        # 风扇 dp2key 映射 (根据微信小程序):
        # ["switch", "angleAutoLROnOff", undefined, "level_1", "timingPowerOff1", undefined, "angleAutoUDOnOff", ...]
        # 索引 0: switch, 索引 1: LR oscillate, 索引 3: level_1 (风速), 索引 4: timing, 索引 6: UD oscillate
        if len(status_data) >= 1:
            status["power"] = status_data[0] == 1
        if len(status_data) >= 2:
            status["oscillating_lr"] = status_data[1] == 1
        if len(status_data) >= 4:
            status["speed"] = status_data[3]
        if len(status_data) >= 5:
            status["timing_power"] = status_data[4]
        if len(status_data) >= 7:
            status["oscillating_ud"] = status_data[6] == 1
        if len(status_data) >= 19:
            status["voice_announce"] = status_data[9] == 1
        _LOGGER.debug("Parsed status: %s", status)
        return status

    async def _notification_handler(
        self, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        data_bytes = bytes(data)

        # 尝试解析状态上报
        status = self._parse_status_report(data_bytes)
        if status:
            self._last_status = status
            self._status_event.set()

    async def _get_ble_device(self) -> BLEDevice | None:
        """获取 BLE 设备对象。"""
        if self._hass:
            return async_ble_device_from_address(self._hass, self._address)
        return None

    async def connect(self) -> bool:
        async with self._lock:
            try:
                if not self._client:
                    # 尝试获取最新的 BLE 设备
                    ble_device = await self._get_ble_device()

                    if ble_device:
                        _LOGGER.debug("Found BLE device: %s", ble_device)
                        self._client = BleakClient(ble_device, timeout=CONNECTION_TIMEOUT)
                    else:
                        _LOGGER.debug("BLE device not found, creating client with address: %s", self._address)
                        self._client = BleakClient(
                            self._address, timeout=CONNECTION_TIMEOUT
                        )
                await self._client.connect()
                await self._client.start_notify(
                    NOTIFY_CHAR_UUID, self._notification_handler
                )
                self._connected = True
                _LOGGER.info("Connected to JH Fan: %s", self._address)
                return True
            except BleakError as err:
                _LOGGER.error("Failed to connect to JH Fan: %s", err)
                self._connected = False
                return False

    async def disconnect(self) -> None:
        """断开连接并停止重连任务。"""
        async with self._lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.stop_notify(NOTIFY_CHAR_UUID)
                    await self._client.disconnect()
                except BleakError as err:
                    _LOGGER.warning("Error disconnecting: %s", err)
            self._connected = False
            self._client = None

    async def _ensure_connected(self) -> bool:
        """确保连接状态，必要时重连。"""
        if self._client and self._client.is_connected and self._connected:
            _LOGGER.debug("Connection is healthy")
            return True

        _LOGGER.warning("Connection lost, attempting to reconnect...")
        self._connected = False

        # 尝试重新连接
        return await self.connect()

    async def send_command(
        self, dp_id: int, value: int, attempts: int = DEFAULT_ATTEMPTS
    ) -> bool:
        frame = self._build_frame(dp_id, value)
        _LOGGER.debug(
            "Sending command: dp=%d, value=%d, frame=%s", dp_id, value, frame.hex()
        )

        for attempt in range(attempts):
            try:
                # 检查连接状态，必要时重连
                if not await self._ensure_connected():
                    _LOGGER.warning(
                        "Connection failed (attempt %d/%d)", attempt + 1, attempts
                    )
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue
                assert self._client is not None
                await self._client.write_gatt_char(
                    WRITE_CHAR_UUID, frame, response=False
                )
                await asyncio.sleep(COMMAND_DELAY)
                return True
            except BleakError as err:
                _LOGGER.warning(
                    "Command failed (attempt %d/%d): %s", attempt + 1, attempts, err
                )
                # 标记断开并触发重连
                self._connected = False
            except Exception as err:
                _LOGGER.error(
                    "Unexpected error (attempt %d/%d): %s", attempt + 1, attempts, err
                )
                self._connected = False

        return False

    async def get_status(self, timeout: float = 5.0) -> dict[str, Any] | None:
        """获取设备所有状态。

        发送 DP_GET_ALL 命令，等待设备返回状态。
        """
        self._status_event.clear()

        # 发送获取状态命令
        if not await self.send_command(DP_GET_ALL, 0):
            _LOGGER.warning("Failed to send get_status command")
            return None

        # 等待状态上报
        try:
            await asyncio.wait_for(self._status_event.wait(), timeout=timeout)
            return self._last_status
        except asyncio.TimeoutError:
            _LOGGER.warning("Timeout waiting for status response")
            return None

    async def turn_on(self) -> bool:
        return await self.send_command(DP_SWITCH, 1)

    async def turn_off(self) -> bool:
        return await self.send_command(DP_SWITCH, 0)

    async def set_speed(self, speed: int) -> bool:
        return await self.send_command(DP_LEVEL, speed)

    async def set_oscillate_lr(self, oscillate: bool) -> bool:
        return await self.send_command(DP_LR_OSCILLATE, 1 if oscillate else 0)

    async def set_oscillate_ud(self, oscillate: bool) -> bool:
        return await self.send_command(DP_UD_OSCILLATE, 1 if oscillate else 0)

    async def set_voice_announce(self, enable: bool) -> bool:
        """设置语音播报开关。"""
        return await self.send_command(DP_VOICE_ANNOUNCE, 1 if enable else 0)

    async def set_timing_off(self, hours: int) -> bool:
        """设置定时关机时间（小时）。"""
        return await self.send_command(DP_TIMING_OFF, hours)
