"""Vestel / homevsmart cloud API (port of vac.py)."""
from __future__ import annotations

import asyncio
import json
import time

import aiohttp

from .const import API, TEMP_OFFSET, TOKEN_URL


class VestelAuthError(Exception):
    pass


class VestelApi:
    def __init__(self, session: aiohttp.ClientSession, client_id: str, client_secret: str, refresh_token: str):
        self._s = session
        self._cid, self._csec, self.refresh_token = client_id, client_secret, refresh_token
        self._tok: str | None = None
        self._exp = 0.0
        self._lock = asyncio.Lock()

    async def _token(self, force: bool = False) -> str:
        async with self._lock:
            if force or not self._tok or time.time() > self._exp:
                data = {"grant_type": "refresh_token", "client_id": self._cid,
                        "client_secret": self._csec, "refresh_token": self.refresh_token}
                async with self._s.post(TOKEN_URL, data=data, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    j = await r.json(content_type=None)
                    if r.status != 200 or "id_token" not in j:
                        raise VestelAuthError(f"token refresh failed: {r.status} {str(j)[:200]}")
                self._tok = j["id_token"]
                self._exp = time.time() + int(j.get("expires_in", 3600)) - 300
                if j.get("refresh_token"):
                    self.refresh_token = j["refresh_token"]
            return self._tok

    async def _req(self, method: str, path: str, body: dict | None = None, retry: bool = True):
        h = {"token": await self._token()}
        async with self._s.request(method, API + path, json=body, headers=h,
                                   timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status in (401, 403) and retry:
                await self._token(force=True)
                return await self._req(method, path, body, False)
            r.raise_for_status()
            return await r.json(content_type=None)

    async def devices(self) -> list[dict]:
        out = []
        for h in (await self._req("GET", "/homes"))["items"]:
            d = await self._req("GET", f"/homes/{h['homeId']}/devices")
            for a in d["items"].get("homeappliances", []):
                if a.get("deviceType") == "AC":
                    out.append(a)
        return out

    async def status(self, dev: str) -> dict:
        x = (await self._req("GET", f"/homeappliances/legacy/status?uuid={dev}"))["data"]
        g = int(x["ACGENSI"])
        return {"mode": g & 7, "fan": g >> 3, "target": int(x["ACTEMOT"]) - TEMP_OFFSET,
                "room": int(x["ACROOTE"]), "error": int(x.get("ACERROR", 0)),
                "rssi": int(x.get("CONNRSS", 0)), "raw": x}

    async def command(self, dev: str, code: str, card: str = "HM07"):
        body = {"device_type": "AC", "wifi_card_type": card, "brand": "Vestel",
                "message": json.dumps({"cmd": f"c:{dev},{code}"})}
        r = await self._req("POST", f"/customer/devices/{dev}/legacy/command", body)
        if r.get("message") != "success":
            raise RuntimeError(f"command {code} rejected: {r}")
        return r

    async def set_gensi(self, dev: str, fan: int, mode: int, card: str = "HM07"):
        return await self.command(dev, f"ACGENSI{(fan << 3) | mode:05d}", card)

    async def set_temp(self, dev: str, t: int, card: str = "HM07"):
        return await self.command(dev, f"ACTEMOT{t + TEMP_OFFSET:05d}", card)
