# SentinelLoop durable data model

Supabase / PostgreSQL is the canonical incident store. Agent Kernel sessions are
**not** interchangeable with these records.

- Session: tracks where the conversation currently is.
- Supabase: tracks what actually happened.

## Security

`SUPABASE_SERVICE_ROLE_KEY` bypasses Row Level Security. Use it only in
server-side code (`database/client.py`). Never put a real key in `.env.example`,
never log it, never ship it to `dashboard/frontend`.

## Client

`database/client.py` reads `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`.
Missing values raise `DatabaseConfigError` naming the unset variables.

Evidence files upload to the `evidence` bucket (`SUPABASE_STORAGE_BUCKET` if
set, otherwise `evidence`). Object keys:

`<incident_id>/<stage>/<uuid><ext>`

`storage_reference` stores the SDK public URL (or the object path if a URL
cannot be produced). If the bucket is private, that URL may not be anonymously
fetchable; this layer does not change Storage policies.

Upload-then-insert is not a SQL transaction. If the `incident_evidence` insert
fails after a successful upload, the repository attempts to delete the object
and raises `PartialPersistenceError`.

`increment_duplicate_count` uses compare-and-set on `duplicate_count` (no RPC
in the available schema sources). Concurrent increments retry a few times.

Status updates and `incident_updates` inserts are separate calls. There is no
client-side transaction.

## MVP tables (exactly five)

1. `incidents` — includes `duplicate_count`
2. `incident_evidence` — metadata + `storage_reference` URL; `stage` on upload
3. `risk_assessments` — row model only (no repository writes in this phase)
4. `assignments`
5. `incident_updates`

Part 2 SQL was not checked into this repository. Models follow `SPEC.md` plus
the persistence prompt (`duplicate_count`, evidence `stage`). Extra columns
returned by PostgREST are ignored.

## Repository

See `repository.py`: `create_incident`, `get_incident`, `list_incidents`,
`update_incident_status`, `add_update`, `assign_incident`, `add_evidence`,
`increment_duplicate_count`.
