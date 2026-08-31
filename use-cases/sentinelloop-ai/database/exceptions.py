"""SentinelLoop database errors.

Do not include service-role keys, auth headers, or uploaded bytes in messages.
"""


class DatabaseError(Exception):
    """Base class for persistence-layer failures."""


class DatabaseConfigError(DatabaseError):
    """Required Supabase configuration is missing."""


class RecordNotFoundError(DatabaseError):
    """A requested row does not exist."""


class PersistenceError(DatabaseError):
    """Supabase table operation failed or returned an unexpected payload."""


class EvidenceUploadError(DatabaseError):
    """Storage upload failed before an evidence row was created."""


class PartialPersistenceError(DatabaseError):
    """Storage succeeded but the matching database insert failed (or cleanup failed)."""
