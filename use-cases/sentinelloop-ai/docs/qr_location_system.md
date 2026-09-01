# Location QR reporting

Workers scan a posted QR code. Telegram opens with the location already filled in. The worker only types the hazard. SentinelLoop never asks “Where are you?” or “What equipment is involved?”

```text
SCAN QR
    ↓
Telegram opens with [LOC:Lab B|Machine 4]
    ↓
Worker writes the hazard
    ↓
intake_agent strips the tag
    ↓
incident_agent prefills location/equipment (source=QR_TAGGED)
    ↓
risk → guidance → coordination
    ↓
Command dashboard shows QR Tagged + location verified
```

This is additive. The original `SLQR location="..." equipment="..."` prefix is unchanged.

## Generate posters

From `use-cases/sentinelloop-ai`:

```bash
# E.164 digits only, no plus. Example: 94771234567
uv run python scripts/generate_location_qr.py --bot-username <TELEGRAM_BOT_USERNAME>
```

Or set `TELEGRAM_BOT_USERNAME` in the local env file (never commit it).

The script:

1. Loads `locations.yaml`.
2. Validates required fields (`location`, `equipment`), unique `qr_id`, and payload length.
3. Encodes a Telegram deep link per site.
4. Writes high-contrast PNG stickers and A4 posters.
5. Writes `assets/qr/location_registry.json`.

Output:

```text
assets/qr/
    SNT-LAB-B-M4-001.png
    SNT-PROD-HP-01.png
    location_registry.json
    posters/
        SNT-LAB-B-M4-001-poster.png
```

Regenerate posters when equipment changes. Bump `version` (or set a new `qr_id`) so the old sticker is retired.

```yaml
- location: "Lab B"
  equipment: "Machine 4"
  area_code: "LAB-B-M4"
  version: 2          # becomes SNT-LAB-B-M4-V2 if qr_id is omitted
```

## Telegram deep link

Each QR encodes:

```text
https://t.me/<digits>?text=<url-encoded-message>
```

The prefilled message is always:

```text
[LOC:<location>|<equipment>]
```

Example scan result in Telegram:

```text
[LOC:Lab B|Machine 4]
```

The worker types the hazard after that prefix:

```text
[LOC:Lab B|Machine 4] Oil leaking near machine
```

Location and equipment names are sanitized (no URLs, scripts, control characters, or `|[]`). The encoded prefix is capped so the QR stays scanner-friendly. Error correction is high (`H`) with a 4-module quiet zone.

## Location tagging

`intake_agent` looks at the start of the inbound text:

| Input | Result |
| --- | --- |
| `[LOC:Lab B\|Machine 4] Smoke coming from motor` | `qr_location=Lab B`, `qr_equipment=Machine 4`, `clean_text=Smoke coming from motor` |
| `[LOC:test]`, `[LOC:Lab B]`, `[LOC:]` | Invalid. Logged as `invalid_location_tag_detected`. Treated as a normal message. |
| `SLQR location="Warehouse A" equipment="Forklift 7"` | Original workflow. Unchanged. |

Stored envelope:

- `raw_text` — original Telegram body, including the prefix
- `clean_text` — worker description only (this is what the model classifies)
- `source` — `QR_TAGGED` when the tag is valid
- `location_confidence` — `1.0` because the site came from a printed tag

The same QR fields stay on the session. A clarification reply without a new tag still carries Lab B / Machine 4 through incident, risk, guidance, and coordination.

`incident_agent` then:

- Prefills `incident.location` and `incident.equipment`
- Sets `source=QR_TAGGED`
- Does **not** ask for location or equipment

## Demo workflow (hackathon)

1. Print `assets/qr/posters/SNT-CHEM-SA-01-poster.png`.
2. A judge scans it with a phone camera or Telegram.
3. Telegram opens with `[LOC:Chemical Storage|Storage Cabinet A]`.
4. The judge types `Chemical smell detected` and sends.
5. Intake strips the tag. Incident creation skips location questions.
6. The command dashboard card shows **QR Tagged** and **Location verified**.
7. Analytics lists Chemical Storage / Storage Cabinet A under Top QR locations.
8. Coordination still alerts the officer on Slack.

Zero location questions.

## Analytics

`assets/qr/location_registry.json` is the static catalog (id, site, equipment, encoded message, file path, generated time). Live reporting stats come from incident `original_message_text`:

- `source=QR_TAGGED` and `location_verified=true` on list/detail cards
- `/analytics/summary` → `qr_tagged_incidents`, `top_qr_locations`
- Location risk score is derived from incident count and severity mix
- Preventive insight example: `Machine 4 has 5 oil leakage reports this month. Recommend maintenance inspection.`

The dashboard remains read-only. It infers QR origin from stored message text; it does not import agents.
