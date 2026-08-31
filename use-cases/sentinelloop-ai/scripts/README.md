# Scripts

Operational helpers. Incident business logic stays in agents and tools.

## Location QR posters

```bash
uv run python scripts/generate_location_qr.py
```

Reads `locations.yaml`, writes PNG stickers and A4 posters to `assets/qr/`, and writes `assets/qr/location_registry.json`. Requires `WHATSAPP_QR_NUMBER` (E.164 digits, no `+`) or `--whatsapp-number`.

Does not call agents, mutate incidents, or contact WhatsApp.

See `docs/qr_location_system.md`.
