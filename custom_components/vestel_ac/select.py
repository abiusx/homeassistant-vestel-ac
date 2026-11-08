from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import device_info
from .const import DOMAIN, HSWING_SHIFT, SWING_OPTIONS, VSWING_SHIFT

SWINGS = [("vertical_swing", "Vertical swing", VSWING_SHIFT, "mdi:arrow-up-down"),
          ("horizontal_swing", "Horizontal swing", HSWING_SHIFT, "mdi:arrow-left-right")]


async def async_setup_entry(hass, entry, add):
    coord = hass.data[DOMAIN][entry.entry_id]
    add(VestelSwing(coord, d, *s) for d in coord.devices for s in SWINGS)


class VestelSwing(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_options = SWING_OPTIONS

    def __init__(self, coord, dev, key, name, shift, icon):
        super().__init__(coord)
        self._dev, self._shift = dev, shift
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
    def current_option(self):
        if not self._st:
            return None
        v = (self._st["fanpo"] >> self._shift) & 7
        return SWING_OPTIONS[v] if v < len(SWING_OPTIONS) else None

    async def async_select_option(self, option):
        v = SWING_OPTIONS.index(option)
        cur = self._st["fanpo"] & ~(7 << self._shift)
        await self.coordinator.async_set_fanpo(self._dev, cur | (v << self._shift))
