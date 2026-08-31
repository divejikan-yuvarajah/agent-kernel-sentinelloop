"""Emergency keyword lists for the local safety bypass gate.

English and emoji entries follow the product spec. Sinhala and Tamil entries
are native-script workplace terms already used in SentinelLoop worker copy
(telegram receipts and follow-up verification), not romanized guesses.
"""

from __future__ import annotations

EMERGENCY_KEYWORDS = {
    "english": [
        "sos",
        "emergency",
        "help now",
        "danger",
        "fire",
        "explosion",
        "save me",
        "urgent help",
        "fire now",
        "on fire",
        "chemical leaking",
        "chemical leak",
        "machine explosion",
        "electric shock",
        "electrical shock",
        "live wire",
        "live cable",
        "heavy smoke",
        "smoke coming",
        "unconscious",
        "trapped",
        "collapsing",
        "collapse",
        "flames",
        "burning",
    ],
    "sinhala": [
        "sos",
        "අනතුර",
        "අනතුරුදායක",
    ],
    "tamil": [
        "sos",
        "ஆபத்து",
    ],
    "emoji": [
        "🆘",
        "🔥",
        "⚠️",
        "⚠",
        "🚨",
        "❗",
    ],
}

# Training / planning language that must not raise a life-safety bypass.
FALSE_POSITIVE_CONTEXT = (
    "training",
    "meeting",
    "drill",
    "exercise",
    "procedure",
    "class",
    "session",
    "workshop",
    "manual",
    "briefing",
    "awareness",
    "evacuation plan",
    "safety meeting",
    "fire safety",
    "tomorrow",
)

# Immediate-danger cues that override training/meeting suppression.
IMMEDIATE_CONTEXT = (
    "now",
    "happening",
    "currently",
    "injured",
    "trapped",
    "leaking",
    "explosion",
    "sos",
    "help",
    "near",
    "coming",
    "save me",
    "help now",
    "urgent help",
)

# Always-on phrases: never suppressed by meeting/training context.
ALWAYS_TRIGGER = (
    "sos",
    "save me",
    "help now",
    "urgent help",
    "fire now",
    "on fire",
    "chemical leaking",
    "chemical leak",
    "machine explosion",
    "electric shock",
    "electrical shock",
    "live wire",
    "live cable",
    "heavy smoke",
    "smoke coming",
    "unconscious",
    "trapped",
    "collapsing",
    "collapse",
    "අනතුර",
    "අනතුරුදායක",
    "ஆபத்து",
)

# Contextual English words that need false-positive protection.
CONTEXTUAL_WORDS = ("emergency", "danger", "fire", "flames", "burning", "explosion")

NEGATION_CONTEXT = (
    "no longer",
    "not on fire",
    "stopped",
    "fixed",
    "repaired",
    "resolved",
    "yesterday",
    "last week",
)

LOCATION_HINTS = (
    "electrical room",
    "welding section",
    "chemical storage",
    "production floor",
    "loading bay",
    "loading bay a",
    "lab b",
    "cnc area",
    "main workshop floor",
    "machine area",
)

WORKER_EMERGENCY_REPLY = {
    "en": (
        "Your emergency report has been received. "
        "Help is being notified now. "
        "Please move to a safe location and wait for assistance."
    ),
    "si": "ඔබගේ වාර්තාව ලැබුණා. කරුණාකර ආරක්ෂිත ස්ථානයේ රැඳී සිටින්න.",
    "ta": "உங்கள் அறிக்கை பெறப்பட்டது. தயவுசெய்து பாதுகாப்பான இடத்தில் காத்திருக்கவும்.",
}

RISK_EXPLANATION = "Emergency keyword trigger — bypassed normal triage"

EMERGENCY_CATEGORY = "unspecified-emergency"
EMERGENCY_RISK_LEVEL = "Critical"
DUPLICATE_WINDOW_SECONDS = 120.0
