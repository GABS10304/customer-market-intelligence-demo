"""
Semantische Synonym-Cluster für Intent/Bedarf — erweiterbar ohne Code-Änderung.

Ein Cluster bündelt Wörter mit gleicher Bedeutung (z. B. «mühselig» ≈ «umständlich»).
Neue Terme kommen in data/intent_synonym_clusters.json (Challenge-Feedback / PM-Pflege).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from config import DATA_DIR

LEXICON_PATH = DATA_DIR / "intent_synonym_clusters.json"

_BUILTIN_CLUSTERS: dict[str, dict[str, Any]] = {
    "ux_reibung": {
        "label": "UX-Reibung",
        "bedarf": "UX-Kritik",
        "terms": [
            "mühselig",
            "muehsam",
            "mühsam",
            "muhsam",
            "umständlich",
            "umstaendlich",
            "lästig",
            "laestig",
            "aufwendig",
            "cumbersome",
        ],
    },
    "ux_unuebersichtlich": {
        "label": "UX-Unübersichtlichkeit",
        "bedarf": "UX-Kritik",
        "terms": [
            "unübersichtlich",
            "unuebersichtlich",
            "unintuitiv",
            "verwirrend",
        ],
    },
    "service_wartezeit": {
        "label": "Service-Wartezeit",
        "bedarf": "Service-Kritik",
        "terms": [
            "wartezeit",
            "wochen",
            "monate",
            "keine rückmeldung",
            "keine rueckmeldung",
            "geht nichts vorran",
            "geht nichts voran",
        ],
    },
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


@lru_cache(maxsize=1)
def load_clusters() -> dict[str, dict[str, Any]]:
    """Built-in-Cluster + optionale Erweiterungen aus JSON (PM / Challenge-Feedback)."""
    merged = {
        cid: {"label": c["label"], "bedarf": c["bedarf"], "terms": list(c["terms"])}
        for cid, c in _BUILTIN_CLUSTERS.items()
    }
    if not LEXICON_PATH.exists():
        return merged
    try:
        data = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return merged
    for cid, raw in (data.get("clusters") or {}).items():
        if cid not in merged:
            merged[cid] = {
                "label": str(raw.get("label") or cid),
                "bedarf": str(raw.get("bedarf") or ""),
                "terms": [],
            }
        extra = [str(t).lower().strip() for t in raw.get("terms") or [] if str(t).strip()]
        seen = set(merged[cid]["terms"])
        for term in extra:
            if term not in seen:
                merged[cid]["terms"].append(term)
                seen.add(term)
    return merged


def cluster_hits(text: str, cluster_id: str) -> tuple[str, ...]:
    """Treffer in einem Cluster — gibt die gefundenen Terme zurück."""
    lower = _normalize(text)
    cluster = load_clusters().get(cluster_id)
    if not cluster or not lower:
        return ()
    return tuple(t for t in cluster["terms"] if t in lower)


def any_cluster_hit(text: str, cluster_id: str) -> bool:
    return bool(cluster_hits(text, cluster_id))


def clusters_for_bedarf(bedarf: str) -> dict[str, dict[str, Any]]:
    return {
        cid: c for cid, c in load_clusters().items() if c.get("bedarf") == bedarf
    }


def all_terms_for_bedarf(bedarf: str) -> frozenset[str]:
    terms: set[str] = set()
    for cluster in clusters_for_bedarf(bedarf).values():
        terms.update(cluster.get("terms") or [])
    return frozenset(terms)


def suggest_terms_from_text(text: str, *, bedarf: str) -> tuple[str, ...]:
    """
    Terme im Text, die noch in keinem Cluster für diesen bedarf liegen —
    Kandidaten für Challenge-Feedback / JSON-Erweiterung.
    """
    lower = _normalize(text)
    known = all_terms_for_bedarf(bedarf)
    tokens = re.findall(r"[a-zäöüß]{4,}", lower)
    return tuple(t for t in tokens if t not in known)
