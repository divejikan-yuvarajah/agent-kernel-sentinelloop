# QR assets

Printable location tags for the WhatsApp reporting flow.

Generate from `use-cases/sentinelloop-ai`:

```bash
uv run python scripts/generate_location_qr.py --whatsapp-number <WHATSAPP_QR_NUMBER>
```

See `docs/qr_location_system.md` for payload format, intake tagging, and the demo scan path.

Generated PNGs and `location_registry.json` are local artifacts. Do not commit phone numbers or production deep links.
