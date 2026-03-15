"""BLE client for JH Voice Fan."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
    retry_bluetooth_connection_error,
)

from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
)
from homeassistant.core import HomeAssistant

from .const import (
    CMD_STATUS_REPORT,
    COMMAND_DELAY,
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


def checksum(data: list[int]) -> int:
    return sum(data) % 256


class JHFanBLE:
    def __init__(self, address: str, hass: HomeAssistant | None = None) -> None:
        self._address = address
        self._hass = hass
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._seq = 1
        self._status_event = asyncio.Event()
        self._last_status: dict[str, Any] | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

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
        if len(status_data) >= 10:
            status["voice_announce"] = status_data[9] == 1
        _LOGGER.debug("Parsed status: %s", status)
        return status

    def _notification_handler(
        self, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        data_bytes = bytes(data)

        # 尝试解析状态上报
        status = self._parse_status_report(data_bytes)
        if status:
            self._last_status = status
            self._status_event.set()

    def _get_ble_device(self) -> BLEDevice | None:
        """获取 BLE 设备对象。"""
        if self._hass:
            return async_ble_device_from_address(self._hass, self._address)
        return None

    async def _establish_connection(self) -> BleakClient:
        """使用 bleak-retry-connector 建立连接。"""
        ble_device = self._get_ble_device()
        if ble_device is None:
            raise ConnectionError(f"BLE device not found: {self._address}")

        async with self._lock:
            # 双重检查，避免重复连接
            if self._client is not None and self._client.is_connected:
                return self._client

            self._client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                f"JH Fan {self._address}",
                disconnected_callback=self._on_disconnect,
            )

            # 启动通知
            await self._client.start_notify(
                NOTIFY_CHAR_UUID, self._notification_handler
            )

            _LOGGER.info("Connected to JH Fan: %s", self._address)
            return self._client

    def _on_disconnect(self, client: BleakClient) -> None:
        """断开连接回调。"""
        _LOGGER.debug("JH Fan disconnected: %s", self._address)
        self._client = None

    async def disconnect(self) -> None:
        """断开连接。"""
        async with self._lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.stop_notify(NOTIFY_CHAR_UUID)
                    await self._client.disconnect()
                except Exception as err:
                    _LOGGER.warning("Error disconnecting: %s", err)
            self._client = None

    @retry_bluetooth_connection_error(attempts=DEFAULT_ATTEMPTS)
    async def _send_command_with_retry(self, frame: bytes) -> bool:
        """发送命令（带重试）。"""
        # 确保连接（内部有加锁）
        if not self.connected or self._client is None:
            await self._establish_connection()

        assert self._client is not None
        await self._client.write_gatt_char(
            WRITE_CHAR_UUID, frame, response=False
        )
        await asyncio.sleep(COMMAND_DELAY)
        return True

    async def send_command(self, dp_id: int, value: int) -> bool:
        frame = self._build_frame(dp_id, value)
        _LOGGER.debug(
            "Sending command: dp=%d, value=%d, frame=%s", dp_id, value, frame.hex()
        )

        try:
            return await self._send_command_with_retry(frame)
        except Exception as err:
            _LOGGER.error(
                "Failed to send command after retries: %s", err
            )
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
        """打开设备。"""
        return await self.send_command(DP_SWITCH, 1)

    async def turn_off(self) -> bool:
        """关闭设备。"""
        return await self.send_command(DP_SWITCH, 0)

    async def _ensure_power_on(self) -> bool:
        """确保设备已打开，未打开则先打开。"""
        # 检查缓存的状态
        if self._last_status is not None and self._last_status.get("power"):
            return True

        # 获取当前状态
        status = await self.get_status()
        if status is None:
            _LOGGER.warning("Failed to get status, assuming device is off")
            return await self.turn_on()

        if not status.get("power"):
            _LOGGER.info("Device is off, turning on first")
            return await self.turn_on()

        return True

    async def set_speed(self, speed: int) -> bool:
        """设置风速。"""
        if not await self._ensure_power_on():
            return False
        return await self.send_command(DP_LEVEL, speed)

    async def set_oscillate_lr(self, oscillate: bool) -> bool:
        """设置左右摇头开关。"""
        if oscillate and not await self._ensure_power_on():
            return False
        return await self.send_command(DP_LR_OSCILLATE, 1 if oscillate else 0)

    async def set_oscillate_ud(self, oscillate: bool) -> bool:
        """设置上下摇头开关。"""
        if oscillate and not await self._ensure_power_on():
            return False
        return await self.send_command(DP_UD_OSCILLATE, 1 if oscillate else 0)

    async def set_voice_announce(self, enable: bool) -> bool:
        """设置语音播报开关。"""
        return await self.send_command(DP_VOICE_ANNOUNCE, 1 if enable else 0)

    async def set_timing_off(self, hours: int) -> bool:
        """设置定时关机时间（小时）。"""
        if hours > 0 and not await self._ensure_power_on():
            return False
        return await self.send_command(DP_TIMING_OFF, hours)
