from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info
from .const import DOMAIN, FANPO_ECO, FANPO_ION, FANPO_SLEEP, FANPO_TURBO

# (key, name, bit, bits the app clears when this one goes on, icon)
FUNCS = [
    ("turbo", "Turbo", FANPO_TURBO, FANPO_ECO | FANPO_SLEEP, "mdi:fan-plus"),
    ("eco", "Energy saving", FANPO_ECO, FANPO_TURBO, "mdi:leaf"),
    ("sleep", "Sleep", FANPO_SLEEP, 0, "mdi:weather-night"),
    ("ionizer", "Ionizer", FANPO_ION, 0, "mdi:atom"),
]


async def async_setup_entry(hass, entry, add):
    coord = hass.data[DOMAIN][entry.entry_id]
    add(VestelFunction(coord, d, *f) for d in coord.devices for f in FUNCS)


class VestelFunction(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, dev, key, name, bit, clears, icon):
        super().__init__(coord)
        self._dev, self._bit, self._clears = dev, bit, clears
        self._attr_unique_id = f"{dev['deviceId']}_{key}"
        self._attr_name, self._attr_icon = name, icon
        self._attr_device_info = device_info(dev)

    @property
    def _st(self):
        return (self.coordinator.data or {}).get(self._dev["deviceId"])

    @property
    def available(self):
        return super().available and self._st is not None and self._st.get("mode") != 5

    @property
    def is_on(self):
        return bool(self._st and self._st["fanpo"] & self._bit)

    async def async_turn_on(self, **kw):
        await self.coordinator.async_set_fanpo(self._dev, (self._st["fanpo"] & ~self._clears) | self._bit)

    async def async_turn_off(self, **kw):
        await self.coordinator.async_set_fanpo(self._dev, self._st["fanpo"] & ~self._bit)
