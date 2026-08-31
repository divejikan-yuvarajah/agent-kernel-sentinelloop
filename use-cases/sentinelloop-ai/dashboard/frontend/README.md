# SentinelLoop dashboard frontend

Placeholder only. No UI framework or components yet.

Later this layer may display:

- incident queue and open incidents
- Critical incidents
- filters by site, category, language, and risk
- hazard categories and lifecycle status
- assignments and remediation evidence
- worker verification and reopened incidents
- risk explanation and audit timeline
- summary / resolution metrics

Do not call agent internals from the frontend. Use `dashboard/api.py` →
Supabase repositories.

Status: scaffolded — not implemented.
