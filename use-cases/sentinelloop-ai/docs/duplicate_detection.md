# Duplicate hazard detection

SentinelLoop does not open a new incident for every similar WhatsApp report. It checks whether workers are describing the **same open hazard**, then raises priority when several people confirm it.

Incident creation is unchanged: a duplicate match updates the existing record; otherwise the orchestrator creates one incident as before.

```text
Worker reports a hazard
        ↓
Local check (category + location + 24h + similarity)
        ↓
Duplicate? ──yes──► increment reports, maybe raise risk
        │
        no (or uncertain)
        ↓
Create a new incident
```

## Detection pipeline

1. Load recent incidents from the repository (no agent imports).
2. Keep **open** records only (`RESOLVED` / `CLOSED` are ignored, except a still-active closed hazard can reopen).
3. Require the **same category** and **same location**, reported within **24 hours**.
4. Compare **translated English** descriptions only (`translated_text` / stored `hazard_description`). Raw Sinhala/Tamil is never scored.
5. Local score ≥ **0.6** → duplicate (`LOCAL_SIMILARITY`). No model call.
6. If **two or more** same-site candidates sit in **0.4–0.6**, call `role_fast` **once**. `YES` merges (`AI_VERIFICATION`). `NO`, timeout, or router failure falls back to the local decision (do not merge below 0.6). Creation is never blocked.

## Local similarity

`calculate_similarity` is CPU-only:

- `difflib.SequenceMatcher` on the full translated strings
- SequenceMatcher on sorted content tokens (order-insensitive paraphrases)
- Dice overlap of light-stemmed tokens (`leak`/`leaking`/`leakage`)

The maximum of those three is the score. That is why “Oil leaking from hydraulic machine” and “Hydraulic press has oil leakage” land in the documented 0.6+ band without embeddings or a vector database.

| Case | Outcome |
| --- | --- |
| Same description | Duplicate |
| Paraphrase, same site and category | Duplicate if score ≥ 0.6 |
| Same text, different location | Not a duplicate |
| Same location, different category | Not a duplicate |
| Older than 24 hours | Ignored |
| Missing translated description | Safe fallback: create new |

## AI fallback

Prompt (verbatim):

```text
Are these two workplace hazard reports describing the same hazard?

Report A:
{description_a}

Report B:
{description_b}

Answer only:
YES or NO
```

One call, four-second timeout, `role_fast` only.

## Escalation

`handle_duplicate_match`:

1. `repository.increment_duplicate_count` (if the stored count is 0, the original report is counted so the first duplicate becomes **2 REPORTS**).
2. Timeline: `Duplicate hazard detected from another worker report.`
3. When `duplicate_count == 3`: raise `current_risk_level` one step (`LOW` → `MEDIUM` → `HIGH` → `CRITICAL`, never above `CRITICAL`) and write `Priority increased — reported by multiple workers.` with metadata `{event: duplicate_threshold_reached, count, timestamp, reason}`.

Further duplicates do not raise risk again.

## Cost counters

`duplicate_detection_stats()`:

```json
{
  "total_checks": 120,
  "local_matches": 95,
  "llm_checks": 5,
  "avoided_duplicates": 100
}
```

The command dashboard `/analytics/summary` includes these live counters plus **most repeated hazards** and **repeated hazard locations** derived from `duplicate_count > 1`.

## Dashboard

- Cards show `{n} REPORTS` only when `duplicate_count > 1`, tooltip: *Multiple workers reported this same hazard*.
- Timeline titles: **AI merged reports**, **Priority increased**.
- Analytics: repeated hazards, locations, and “This equipment has recurring reports. Consider inspection.”

## Demo

1. Worker 1: “Smoke coming from motor” → new incident.
2. Worker 2: “Motor producing smoke” (same location/category) → local duplicate, **2 REPORTS**.
3. Worker 3: another paraphrase → **3 REPORTS**, risk steps up one level.

Most matches never touch a paid model.
