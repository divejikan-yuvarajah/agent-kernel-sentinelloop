# Scripts

Operational helpers. Incident business logic stays in agents and tools.

## Location QR posters

```bash
uv run python scripts/generate_location_qr.py
```

Reads `locations.yaml`, writes PNG stickers and A4 posters to `assets/qr/`, and writes `assets/qr/location_registry.json`. Requires `WHATSAPP_QR_NUMBER` (E.164 digits, no `+`) or `--whatsapp-number`.

Does not call agents, mutate incidents, or contact WhatsApp.

See `docs/qr_location_system.md`.

## Horizon Engineering demo seeder

```bash
uv run python scripts/seed_demo_data.py
uv run python scripts/seed_demo_data.py --reset
uv run python scripts/seed_demo_data.py --verbose
uv run python scripts/seed_demo_data.py --summary
```

Populates the existing five Supabase tables with a fictional **Horizon Engineering Workshop** environment (9 linked incidents, multilingual reports, duplicate electrical hazard, QR tags, Slack/WhatsApp simulation, evidence, and audit history). Requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. `--reset` deletes only `DEMO-HORIZON-*` rows. Safe to rerun: existing demo refs are reused, not duplicated.
