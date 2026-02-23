"""BLE client for JH Voice Fan."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS

from .const import (
    CMD_STATUS_REPORT,
    COMMAND_DELAY,
    CONNECTION_TIMEOUT,
    DEFAULT_ATTEMPTS,
    DP_GET_ALL,
    FRAME_HEAD,
    FRAME_TAIL,
    NOTIFY_CHAR_UUID,
    SERVICE_UUID,
    WRITE_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)


def checksum(data: list[int]) -> int:
    return sum(data) % 256


class JHFanBLE:
    def __init__(self, address: str) -> None:
        self._address = address
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._seq = 1
        self._callbacks: list[Callable[[bytes], None]] = []
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
        _LOGGER.debug("Built frame: %s", frame)
        return bytes(frame)

    def _parse_status_report(self, data: bytes) -> dict[str, Any] | None:
        """解析设备状态上报数据。

        数据帧格式: [0xAA, 长度, 序列号, 0x53, 状态数据..., 校验和, 0x55]
        状态数据按DP点顺序排列
        """
        if len(data) < 6:
            return None

        if data[0] != FRAME_HEAD or data[-1] != FRAME_TAIL:
            return None

        if data[3] != CMD_STATUS_REPORT:
            return None

        # 状态数据从第4字节开始，到校验和之前
        status_data = data[4 : data[1] + 2]

        # DP点顺序映射 (根据微信小程序 fanKey2Dp)
        # 位置 0: DP_SWITCH (1) - 开关
        # 位置 1: DP_LEVEL (2) - 风速
        # 位置 2: DP_TIMING_OFF (3) - 定时关机
        # 位置 3: DP_LR_OSCILLATE (4) - 左右摇头
        # 位置 4: DP_UD_OSCILLATE (5) - 上下摇头
        # 位置 5: DP_ANION (6) - 负离子
        # 位置 6: DP_MODE (7) - 模式
        # ...

        status: dict[str, Any] = {}

        if len(status_data) > 0:
            status["power"] = status_data[0] == 1
        if len(status_data) > 1:
            status["speed"] = status_data[1]
        if len(status_data) > 3:
            status["oscillating_lr"] = status_data[3] == 1
        if len(status_data) > 4:
            status["oscillating_ud"] = status_data[4] == 1
        if len(status_data) > 5:
            status["anion"] = status_data[5] == 1
        if len(status_data) > 6:
            status["mode"] = status_data[6]

        _LOGGER.debug("Parsed status: %s", status)
        return status

    async def _notification_handler(
        self, _sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        _LOGGER.debug("Received notification: %s", data.hex())
        data_bytes = bytes(data)

        # 尝试解析状态上报
        status = self._parse_status_report(data_bytes)
        if status:
            self._last_status = status
            self._status_event.set()

        # 回调通知
        for callback in self._callbacks:
            callback(data_bytes)

    def register_callback(self, callback: Callable[[bytes], None]) -> None:
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[bytes], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def connect(self, ble_device: BLEDevice | None = None) -> bool:
        async with self._lock:
            if self._connected and self._client and self._client.is_connected:
                return True

            try:
                if ble_device:
                    self._client = BleakClient(ble_device, timeout=CONNECTION_TIMEOUT)
                else:
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
        async with self._lock:
            if self._client and self._client.is_connected:
                try:
                    await self._client.stop_notify(NOTIFY_CHAR_UUID)
                    await self._client.disconnect()
                except BleakError as err:
                    _LOGGER.warning("Error disconnecting: %s", err)
            self._connected = False
            self._client = None

    async def send_command(
        self, dp_id: int, value: int, attempts: int = DEFAULT_ATTEMPTS
    ) -> bool:
        frame = self._build_frame(dp_id, value)
        _LOGGER.debug(
            "Sending command: dp=%d, value=%d, frame=%s", dp_id, value, frame.hex()
        )

        for attempt in range(attempts):
            try:
                async with self._lock:
                    if not self._client or not self._client.is_connected:
                        if not await self.connect():
                            await asyncio.sleep(1)
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
                self._connected = False
                await asyncio.sleep(1)

        return False

    async def get_status(self, timeout: float = 5.0) -> dict[str, Any] | None:
        """获取设备所有状态。

        发送 DP_GET_ALL 命令，等待设备返回状态。
        """
        self._status_event.clear()
        self._last_status = None

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
        return await self.send_command(1, 1)

    async def turn_off(self) -> bool:
        return await self.send_command(1, 0)

    async def set_speed(self, speed: int) -> bool:
        return await self.send_command(2, speed)

    async def set_oscillate_lr(self, oscillate: bool) -> bool:
        return await self.send_command(4, 1 if oscillate else 0)

    async def set_oscillate_ud(self, oscillate: bool) -> bool:
        return await self.send_command(5, 1 if oscillate else 0)

    async def set_natural_wind(self, enable: bool) -> bool:
        return await self.send_command(27, 1 if enable else 0)

    async def set_child_lock(self, enable: bool) -> bool:
        return await self.send_command(26, 1 if enable else 0)
