from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (DOMAIN, MAX_TEMP, MIN_TEMP, MODE_COOL, MODE_DRY, MODE_HEAT, MODE_OFF,
                    RECONCILE_SECONDS)

TO_HA = {MODE_COOL: HVACMode.COOL, MODE_DRY: HVACMode.DRY, MODE_HEAT: HVACMode.HEAT, MODE_OFF: HVACMode.OFF}
FROM_HA = {v: k for k, v in TO_HA.items()}
FANS = ["auto", "1", "2", "3", "4", "5"]


async def async_setup_entry(hass, entry, add):
    coord = hass.data[DOMAIN][entry.entry_id]
    add(VestelClimate(coord, d) for d in coord.devices)


class VestelClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY]
    _attr_fan_modes = FANS
    _attr_min_temp, _attr_max_temp, _attr_target_temperature_step = MIN_TEMP, MAX_TEMP, 1
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coord, dev):
        super().__init__(coord)
        self._id, self._card = dev["deviceId"], dev.get("wifiCardType", "HM07")
        self._attr_unique_id = self._id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)}, name=f"{dev.get('roomName') or dev['deviceName']} AC",
            manufacturer="Vestel", model=dev.get("deviceModel"), sw_version=dev.get("wifiVersion"),
            suggested_area=dev.get("roomName"))
        self._opt: dict = {}     # optimistic overrides until next poll
        self._last_on = MODE_HEAT
        self._unsub = None

    @property
    def _st(self):
        return {**(self.coordinator.data or {}).get(self._id, {}), **self._opt}

    @property
    def available(self):
        return super().available and self._id in (self.coordinator.data or {})

    @property
    def hvac_mode(self):
        return TO_HA.get(self._st.get("mode"))

    @property
    def fan_mode(self):
        f = self._st.get("fan")
        return FANS[f] if f is not None and 0 <= f < len(FANS) else None

    @property
    def target_temperature(self):
        return self._st.get("target")

    @property
    def current_temperature(self):
        return self._st.get("room")

    @property
    def extra_state_attributes(self):
        s = self._st
        return {"error_code": s.get("error"), "wifi_rssi": s.get("rssi")}

    @callback
    def _handle_coordinator_update(self):
        self._opt = {}
        m = (self.coordinator.data or {}).get(self._id, {}).get("mode")
        if m in (MODE_COOL, MODE_DRY, MODE_HEAT):
            self._last_on = m
        super()._handle_coordinator_update()

    def _reconcile(self):
        if self._unsub:
            self._unsub()

        async def _go(_now):
            self._unsub = None
            await self.coordinator.async_request_refresh()
        self._unsub = async_call_later(self.hass, RECONCILE_SECONDS, _go)

    async def _gensi(self, fan=None, mode=None):
        s = self._st
        fan = s.get("fan", 0) if fan is None else fan
        mode = s.get("mode", MODE_HEAT) if mode is None else mode
        await self.coordinator.api.set_gensi(self._id, fan, mode, self._card)
        self._opt.update(fan=fan, mode=mode)
        self.async_write_ha_state()
        self._reconcile()

    async def async_set_hvac_mode(self, hvac_mode):
        await self._gensi(mode=FROM_HA[hvac_mode])

    async def async_turn_off(self):
        await self._gensi(mode=MODE_OFF)

    async def async_turn_on(self):
        await self._gensi(mode=self._last_on)

    async def async_set_fan_mode(self, fan_mode):
        await self._gensi(fan=FANS.index(fan_mode))

    async def async_set_temperature(self, **kw):
        if "hvac_mode" in kw and kw["hvac_mode"]:
            await self._gensi(mode=FROM_HA[kw["hvac_mode"]])
        t = kw.get(ATTR_TEMPERATURE)
        if t is not None:
            t = int(round(max(MIN_TEMP, min(MAX_TEMP, t))))
            await self.coordinator.api.set_temp(self._id, t, self._card)
            self._opt["target"] = t
            self.async_write_ha_state()
            self._reconcile()
