from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, RECONCILE_SECONDS, SCAN_SECONDS
from .vestel_api import VestelApi, VestelAuthError

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CLIMATE, Platform.SWITCH, Platform.SELECT]


class VestelCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, api, devices):
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=SCAN_SECONDS))
        self.entry, self.api, self.devices = entry, api, devices
        self._reconcile_unsub = None

    async def async_set_fanpo(self, dev: dict, value: int):
        """Send ACFANPO, patch cached state so all entities update now, re-read the unit shortly after."""
        await self.api.set_fanpo(dev["deviceId"], value, dev.get("wifiCardType", "HM07"))
        if self.data and dev["deviceId"] in self.data:
            self.data[dev["deviceId"]]["fanpo"] = value
            self.async_update_listeners()
        self.schedule_reconcile()

    def schedule_reconcile(self):
        if self._reconcile_unsub:
            self._reconcile_unsub()

        async def _go(_now):
            self._reconcile_unsub = None
            await self.async_request_refresh()
        self._reconcile_unsub = async_call_later(self.hass, RECONCILE_SECONDS, _go)

    async def _async_update_data(self):
        out = {}
        try:
            for d in self.devices:
                try:
                    out[d["deviceId"]] = await self.api.status(d["deviceId"])
                except VestelAuthError:
                    raise
                except Exception as e:  # one offline unit shouldn't fail the rest
                    _LOGGER.warning("status %s failed: %s", d["deviceName"], e)
        except VestelAuthError as e:
            raise ConfigEntryAuthFailed(str(e)) from e
        if not out:
            raise UpdateFailed("no unit returned status")
        if self.api.refresh_token != self.entry.data["refresh_token"]:
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "refresh_token": self.api.refresh_token})
        return out


def device_info(dev: dict) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, dev["deviceId"])}, name=f"{dev.get('roomName') or dev['deviceName']} AC",
        manufacturer="Vestel", model=dev.get("deviceModel"), sw_version=dev.get("wifiVersion"),
        suggested_area=dev.get("roomName"))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = VestelApi(async_get_clientsession(hass), entry.data["client_id"],
                    entry.data["client_secret"], entry.data["refresh_token"])
    try:
        devices = await api.devices()
    except VestelAuthError as e:
        raise ConfigEntryAuthFailed(str(e)) from e
    coord = VestelCoordinator(hass, entry, api, devices)
    await coord.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coord
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok
