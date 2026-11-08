from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .vestel_api import VestelApi, VestelAuthError

SCHEMA = vol.Schema({vol.Required("client_id"): str, vol.Required("client_secret"): str,
                     vol.Required("refresh_token"): str, vol.Optional("username", default=""): str})


class VestelFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, data):
        api = VestelApi(async_get_clientsession(self.hass), data["client_id"], data["client_secret"],
                        data["refresh_token"])
        devs = await api.devices()
        return {**data, "refresh_token": api.refresh_token}, devs

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            try:
                data, devs = await self._check(user_input)
            except VestelAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(data["client_id"] + ":" + (data.get("username") or "default"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Vestel {data.get('username') or ''} ({len(devs)} ACs)".replace("  ", " "), data=data)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input:
            try:
                data, _ = await self._check({**entry.data, **user_input})
            except VestelAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(step_id="reauth_confirm", errors=errors,
                                    data_schema=vol.Schema({vol.Required("refresh_token"): str}))
