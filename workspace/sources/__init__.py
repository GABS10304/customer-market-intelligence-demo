"""Source adapter package."""

from workspace.sources.detector import DetectionResult, detect_source
from workspace.sources.profiles import BUILTIN_PROFILES, SourceProfile, get_profile, legacy_evidence_key

__all__ = [
    "BUILTIN_PROFILES",
    "SourceProfile",
    "DetectionResult",
    "detect_source",
    "get_profile",
    "legacy_evidence_key",
]
