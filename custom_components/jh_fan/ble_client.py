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
    COMMAND_DELAY,
    CONNECTION_TIMEOUT,
    DEFAULT_ATTEMPTS,
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

    @property
    def connected(self) -> bool:
        return self._connected

    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = 255 if seq >= 255 else seq + 1
        return seq

    def _build_frame(self, dp_id: int, value: int) -> bytes:
        seq = self._next_seq()
        payload = [3, seq, dp_id, value]
        cs = checksum(payload)
        return bytes([FRAME_HEAD, *payload, cs, FRAME_TAIL])

    async def _notification_handler(self, _sender: BleakGATTCharacteristic, data: bytearray) -> None:
        _LOGGER.debug("Received notification: %s", data.hex())
        for callback in self._callbacks:
            callback(bytes(data))

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
