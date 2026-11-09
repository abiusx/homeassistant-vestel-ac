# Vestel AC for Home Assistant

A Home Assistant custom integration for Vestel Wi-Fi air conditioners that are paired in the
Vestel Smart Life app (Turkish: *Akıllı Yaşam*). It talks to Vestel's cloud, the same one the app
uses. Each AC becomes a `climate` entity, so it also works with the HomeKit bridge, Google Home and
Alexa.

Tested on Home Assistant 2025.9 with four Vestel FLORA units (Wi-Fi card HM07).

## What it controls

- Mode: off, auto, cool, heat, dry, fan only. In fan only the unit picks fan speed 1 and 25 °C
  by itself. In auto it chooses cooling or heating from the room temperature.
- Fan: auto, 1–5
- Target temperature: 18–30 °C, in 1 °C steps
- Reads room temperature, error code and Wi-Fi signal strength
- Switches: turbo, energy saving (eco), sleep, ionizer. As in the Vestel app, turning turbo on turns
  eco and sleep off, and turning eco on turns turbo off.
- Selects: vertical and horizontal swing, `off` or louver setting `1`–`6`

The switches and selects are unavailable while the AC is off.

Vestel's cloud is slow: a command is accepted at once, but the unit's reported state changes 3–6
seconds later. The integration shows the new value immediately and re-reads the unit about 6
seconds after each command. It polls all units every 45 seconds.

Not supported: the unit's built-in on/off timers (use a Home Assistant automation instead).

## Install

**HACS:** HACS → ⋮ → Custom repositories → add `https://github.com/abiusx/homeassistant-vestel-ac`
as an Integration, install *Vestel AC (cloud)*, restart Home Assistant.

**Manual:** copy `custom_components/vestel_ac` into your Home Assistant `config/custom_components/`
and restart.

Then: Settings → Devices & services → Add integration → *Vestel AC (cloud)*.

## Credentials

The setup screen asks for three values: `client_id`, `client_secret` and `refresh_token`.
None of them ship with this integration. The first two belong to Vestel's mobile app and the third
to your own login, so you capture all three from the app's own traffic:

1. Run an HTTPS-intercepting proxy (for example [mitmproxy](https://mitmproxy.org)) on your
   computer, point your phone's Wi-Fi proxy at it and install its CA certificate on the phone.
2. Log out of the Vestel app and log back in.
3. Find the request `POST https://hosted-kimlik.vestel.com.tr/oauth2/token`. Its request body has
   `client_id` and `client_secret`; its response has `refresh_token`.
4. Paste the three into the setup screen. Then delete the capture: it also contains your password.

If you're stuck, ask your favourite LLM to walk you through intercepting an iOS or Android app's
HTTPS traffic with mitmproxy, or open an issue here.

Home Assistant uses the refresh token every hour to get a new `id_token`. How long Vestel keeps a
refresh token valid is not documented. If it stops working, Home Assistant shows a
*Reauthenticate* prompt; capture a new refresh token and paste it there.

## How it works

- Token: `POST hosted-kimlik.vestel.com.tr/oauth2/token` with `grant_type=refresh_token` returns
  an `id_token` valid for one hour.
- API base `https://sh-native-api.homevsmart.com/v1.0`, header `token: <id_token>`.
  `GET /homes`, `GET /homes/{homeId}/devices`, `GET /homeappliances/legacy/status?uuid={deviceId}`,
  `POST /customer/devices/{deviceId}/legacy/command`.
- Status fields: `ACGENSI = fan << 3 | mode` (mode 0 auto, 1 cool, 2 dry, 3 fan only, 4 heat, 5 off; fan 0 auto, 1–5),
  `ACTEMOT = target °C + 32736`, `ACROOTE = room °C`. Commands send the same fields back, for
  example `ACTEMOT32760` sets 24 °C.
- `ACFANPO` is a bit field: bit 0 turbo, bits 1–3 vertical swing (0–6), bits 4–6 horizontal swing
  (0–6), bit 7 sleep, bit 8 ionizer, bit 9 eco. Sending `ACFANPO<value>` sets all of them at once.
- Each command carries the unit's `wifi_card_type` from the device list (`HM07`, `HM03`, ...);
  a command with the wrong card type is accepted by the cloud but ignored by the unit.

The API was worked out by [iltekin/vestel-ac-remote-control](https://github.com/iltekin/vestel-ac-remote-control)
(a Node.js server and web panel); this integration re-implements its API layer in Python for Home
Assistant.

## Disclaimer

Not affiliated with or endorsed by Vestel. It uses an undocumented cloud API that Vestel can change
or close at any time.
