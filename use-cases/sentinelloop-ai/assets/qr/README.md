# QR assets

Printable location tags for the Telegram reporting flow.

Generate from `use-cases/sentinelloop-ai`:

```bash
uv run python scripts/generate_location_qr.py --bot-username <TELEGRAM_BOT_USERNAME>
```

See `docs/qr_location_system.md` for payload format, intake tagging, and the demo scan path.

Generated PNGs and `location_registry.json` are local artifacts. Do not commit phone numbers or production deep links.
