"""Config flow for JH Voice Fan integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, override

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.device_registry import format_mac

from .const import DOMAIN, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


class JHFanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JH Voice Fan."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._address: str | None = None

    @override
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug("Discovered JH Fan device: %s", discovery_info)
        await self.async_set_unique_id(format_mac(discovery_info.address))
        self._abort_if_unique_id_configured()

        self._address = discovery_info.address
        self._discovered_devices[discovery_info.address] = discovery_info

        self.context["title_placeholders"] = {
            "name": discovery_info.name or "JH Fan",
            "address": discovery_info.address,
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm discovery."""
        if user_input is not None:
            name = user_input.get(CONF_NAME, "JH Fan")
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: self._address, CONF_NAME: name},
            )

        # self._address is guaranteed to be set by async_step_bluetooth
        assert self._address is not None
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovered_devices[self._address].name or "JH Fan",
            },
            data_schema=vol.Schema({vol.Optional(CONF_NAME, default="JH Fan"): str}),
        )

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(
                format_mac(self._address), raise_on_progress=False
            )
            self._abort_if_unique_id_configured()

            name = user_input.get(CONF_NAME, "JH Fan")
            return self.async_create_entry(
                title=name,
                data={CONF_ADDRESS: self._address, CONF_NAME: name},
            )

        current_addresses = set(self._async_current_ids(include_ignore=False))

        discovered: BluetoothServiceInfoBleak
        for discovered in async_discovered_service_info(self.hass):
            if SERVICE_UUID not in [s.upper() for s in discovered.service_uuids]:
                continue

            address = discovered.address
            if address in current_addresses or address in self._discovered_devices:
                continue

            _LOGGER.debug("Discovered JH Fan device: %s", discovered)
            self._discovered_devices[address] = discovered

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{info.name or 'JH Fan'} ({address})"
                            for address, info in self._discovered_devices.items()
                        }
                    ),
                    vol.Optional(CONF_NAME, default="JH Fan"): str,
                }
            ),
        )
