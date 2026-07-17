"""
Unmapped Hotline-Cluster → Mapping-Vorschläge für product_module_mapping.json.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from config import DATA_DIR
from core.intent_sources import iter_freetext_rows
from core.product_mapping import (
    MAPPING_PATH,
    load_mapping_entries,
    mapping_entry_by_id,
    module_display_name,
    resolve_cluster_mapping,
)
from core.tera_scope import is_tera_hotline_cluster

SUGGESTIONS_PATH = DATA_DIR / "mapping_suggestions.json"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9äöüß]+", "_", (text or "").lower())
    return re.sub(r"_+", "_", s).strip("_")[:48] or "mapping"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


@dataclass(frozen=True)
class UnmappedCluster:
    cluster: str
    label: str
    tickets: int


@dataclass(frozen=True)
class MappingSuggestion:
    action: str  # extend | create
    target_id: str
    label: str
    ticket_clusters: tuple[str, ...]
    cluster_aliases: tuple[str, ...]
    artikel_contains_any: tuple[str, ...]
    tickets_covered: int
    reason: str

    def to_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "id": self.target_id,
            "label": self.label,
            "ticket_clusters": list(self.ticket_clusters),
            "notes": self.reason,
        }
        if self.cluster_aliases:
            entry["cluster_aliases"] = list(self.cluster_aliases)
        if self.artikel_contains_any:
            entry["artikel_contains_any"] = list(self.artikel_contains_any)
        return entry


def collect_unmapped_clusters(*, min_tickets: int = 1) -> list[UnmappedCluster]:
    counts: Counter[str] = Counter()
    for row in iter_freetext_rows(include_html=True, include_csv=True):
        if row.quelle_technisch not in ("support_tickets_html_roh", "field_visits_weihnachtsbesuche"):
            continue
        cluster = (row.cluster or "").strip()
        if not cluster or is_tera_hotline_cluster(cluster) or resolve_cluster_mapping(cluster):
            continue
        counts[cluster] += 1

    out: list[UnmappedCluster] = []
    for cluster, tickets in counts.most_common():
        if tickets < min_tickets:
            continue
        out.append(
            UnmappedCluster(
                cluster=cluster,
                label=module_display_name(cluster),
                tickets=tickets,
            )
        )
    return out


def _find_extend_target(label: str, cluster: str) -> str | None:
    """Bestehenden Eintrag finden, den wir nur um ticket_clusters erweitern sollten."""
    label_n = _norm(label)
    leaf = cluster.rsplit("\\", 1)[-1].strip()
    leaf_short = leaf.split(" - ", 1)[-1].strip() if " - " in leaf else leaf
    leaf_n = _norm(leaf_short)
    cluster_n = _norm(cluster)

    keyword_rules: tuple[tuple[tuple[str, ...], str], ...] = (
        (("kanal", "awb", "awc", "web-kanal"), "modul_kanal"),
        (("wasser", "wam", "wasserbuch"), "modul_wasser"),
        (("spielplatz", "sp)"), "modul_spielplatz"),
        (("vermess", "(vm)", "vermessungs-app"), "modul_vermessungsdaten"),
        (("finanz", "(fi)", "finanzmodul"), "modul_finanz"),
        (("gruen", "(gf)", "grunfl"), "modul_gruenflaechen"),
        (("bauantrag", "bauav", "(bv)"), "modul_bauav"),
        (("bebauungs", "flachennutz", "(fnp)", "(bp)"), "modul_bebauungsplaene"),
        (("geonotiz", "(gn)"), "geonotizen"),
        (("ki funktion",), "ki_assistenz"),
        (("eakte", "teraakte", "regisafe"), "regisafe_eakte"),
        (("friedhof", "(fh)", "friedhofs"), "modul_friedhof"),
        (("strassen", "(stk)", "swr", "bestandsverzeichnis"), "modul_strassen"),
        (("verkehr", "(vk)"), "modul_verkehr"),
        (("baum", "(ba)", "baumkontroll"), "modul_baeume"),
        (("forst",), "modul_forst"),
        (("versorg", "strom", "gas", "fernwarme"), "modul_versorgungsleitungen"),
        (("datenexport", "zeichenfunktion", "aktivierungscode", "serverfehler"), "rgz_basic"),
        (("autor",), "rgz_basic"),
        (("externer nutzer", "datenabgabe"), "landkreis_gis"),
        (("kartenapp", "apps - karten"), "karten_app"),
        (("baumkontrollapp",), "baumkontroll_app"),
        (("schachtkontroll",), "kanal_app"),
        (("strassenkontrollapp",), "modul_strassen"),
        (("planauskunft", "otsbau", "g2vb", "onlinebeteilig"), "riwa_go_planauskunft"),
        (("digitaler bauantrag", "eav", "importer"), "modul_bauav"),
        (("schnittstelle", "prosoz", "boll", "gekos"), "schnittstelle_prosoz"),
        (("beitrag", "beitragswesen"), "modul_beitragswesen"),
        (("miet", "pacht", "vermieten", "verpachten"), "modul_miet_pacht"),
        (("liegenschaft",), "modul_liegenschaftsverwaltung"),
        (("gebaeude",), "modul_gebaeudemanager"),
        (("belegungsplan",), "modul_belegungsplan"),
        (("vertragsmanager",), "modul_vertragsmanager"),
        (("teramobil",), "modul_teramobil"),
        (("auskunft", "expobj"), "modul_auskunftsmodule"),
        (("adressabgleich",), "modul_adressabgleich"),
        (("wegeinfrastruktur", "(ww)"), "modul_wegeinfrastruktur"),
        (("brucken", "(br)"), "modul_bruecken"),
        (("okokonto", "(ok)"), "modul_oekokonto"),
        (("winterdienst", "(wd)"), "modul_winterdienst"),
        (("hausnummer", "(hv)"), "modul_hausnummern"),
        (("3d",), "modul_3d"),
        (("dokumentenverwaltung",), "modul_dokumentenverwaltung"),
        (("installation", "technik"), "modul_installation_technik"),
        (("edialog",), "modul_edialogdesigner"),
        (("appkit",), "modul_appkit"),
        (("ppm hardware",), "modul_ppm_hardware"),
        (("projektplan umstieg",), "modul_projektplan_umstieg"),
        (("passt in keine", "nicht aufgelistet"), "modul_passt_in_keine_andere_kategorie"),
        (("benutzerverwaltung",), "modul_benutzerverwaltung"),
        (("ressourcenmanager", "bauhof"), "modul_bauhofverwaltung_ressourcenmanager"),
    )
    haystack = f"{cluster_n} {label_n} {leaf_n}"
    for keys, target_id in keyword_rules:
        if any(k in haystack for k in keys):
            if mapping_entry_by_id(target_id):
                return target_id

    for entry in load_mapping_entries():
        if _norm(entry.label) == label_n:
            return entry.id
        if leaf_n and (_norm(entry.label) in leaf_n or leaf_n in _norm(entry.label)):
            return entry.id
        for alias in entry.cluster_aliases + entry.ranking_aliases:
            if _norm(alias) == label_n or _norm(alias) == leaf_n:
                return entry.id
        if "friedhof" in label_n and "friedhof" in _norm(entry.label):
            return entry.id
        if "beitrag" in label_n and "beitrag" in _norm(entry.label):
            return entry.id
    return None


def suggest_all_unmapped(*, min_tickets: int = 1) -> list[MappingSuggestion]:
    """Vorschläge für alle unmapped Cluster (ohne Top-N-Limit)."""
    suggestions: list[MappingSuggestion] = []
    for item in collect_unmapped_clusters(min_tickets=min_tickets):
        extend_id = _find_extend_target(item.label, item.cluster)
        alias = item.label.strip()
        if extend_id:
            entry = mapping_entry_by_id(extend_id)
            suggestions.append(
                MappingSuggestion(
                    action="extend",
                    target_id=extend_id,
                    label=entry.label if entry else extend_id,
                    ticket_clusters=(item.cluster,),
                    cluster_aliases=(alias,) if alias else (),
                    artikel_contains_any=(),
                    tickets_covered=item.tickets,
                    reason=f"Bulk-map ({item.tickets} Tickets) — Cluster an bestehenden Eintrag",
                )
            )
        else:
            target_id = f"modul_{_slug(item.label)}"
            if mapping_entry_by_id(target_id):
                target_id = f"{target_id}_{_slug(item.cluster.rsplit(chr(92), 1)[-1])[:24]}"
            suggestions.append(
                MappingSuggestion(
                    action="create",
                    target_id=target_id,
                    label=item.label.strip(),
                    ticket_clusters=(item.cluster,),
                    cluster_aliases=(alias,) if alias else (),
                    artikel_contains_any=_artikel_hints(item.label),
                    tickets_covered=item.tickets,
                    reason=f"Bulk-map ({item.tickets} Tickets) — neuer Seed-Eintrag",
                )
            )
    return suggestions


def _artikel_hints(label: str) -> tuple[str, ...]:
    n = _norm(label)
    hints: list[str] = []
    if "ressourcen" in n or "bauhof" in n:
        hints.extend(["ressourcenmanager", "bauhof"])
    if "friedhof" in n:
        hints.append("friedhof")
    if "beitrag" in n:
        hints.append("beitrag")
    if "benutzer" in n:
        hints.append("benutzerverwaltung")
    return tuple(dict.fromkeys(hints))


def suggest_mappings(*, limit: int = 5, min_tickets: int = 10) -> list[MappingSuggestion]:
    suggestions: list[MappingSuggestion] = []
    seen_labels: set[str] = set()

    for item in collect_unmapped_clusters(min_tickets=min_tickets):
        label_key = _norm(item.label)
        if label_key in seen_labels:
            continue
        seen_labels.add(label_key)

        extend_id = _find_extend_target(item.label, item.cluster)
        alias = item.label.strip()
        if extend_id:
            entry = mapping_entry_by_id(extend_id)
            suggestions.append(
                MappingSuggestion(
                    action="extend",
                    target_id=extend_id,
                    label=entry.label if entry else extend_id,
                    ticket_clusters=(item.cluster,),
                    cluster_aliases=(alias,) if alias else (),
                    artikel_contains_any=(),
                    tickets_covered=item.tickets,
                    reason=f"Top-unmapped ({item.tickets} Tickets) — Cluster an bestehenden Eintrag",
                )
            )
        else:
            target_id = f"modul_{_slug(item.label)}"
            if mapping_entry_by_id(target_id):
                target_id = f"{target_id}_hotline"
            suggestions.append(
                MappingSuggestion(
                    action="create",
                    target_id=target_id,
                    label=item.label.strip(),
                    ticket_clusters=(item.cluster,),
                    cluster_aliases=(alias,) if alias else (),
                    artikel_contains_any=_artikel_hints(item.label),
                    tickets_covered=item.tickets,
                    reason=f"Top-unmapped ({item.tickets} Tickets) — neuer Seed-Eintrag",
                )
            )
        if len(suggestions) >= limit:
            break
    return suggestions


def _load_mapping_doc() -> dict[str, Any]:
    if not MAPPING_PATH.exists():
        return {"version": "1.0", "entries": []}
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _merge_entry(existing: dict[str, Any], suggestion: MappingSuggestion) -> dict[str, Any]:
    merged = dict(existing)
    clusters = list(existing.get("ticket_clusters") or [])
    for c in suggestion.ticket_clusters:
        if c not in clusters:
            clusters.append(c)
    merged["ticket_clusters"] = clusters

    aliases = list(existing.get("cluster_aliases") or [])
    for a in suggestion.cluster_aliases:
        if a not in aliases:
            aliases.append(a)
    if aliases:
        merged["cluster_aliases"] = aliases

    if suggestion.artikel_contains_any:
        any_list = list(existing.get("artikel_contains_any") or [])
        for token in suggestion.artikel_contains_any:
            if token not in any_list:
                any_list.append(token)
        merged["artikel_contains_any"] = any_list

    note = str(existing.get("notes") or "")
    if suggestion.reason not in note:
        merged["notes"] = f"{note} · {suggestion.reason}".strip(" ·")
    return merged


def apply_suggestions(suggestions: list[MappingSuggestion]) -> dict[str, Any]:
    """Schreibt Vorschläge in product_module_mapping.json (extend oder create)."""
    doc = _load_mapping_doc()
    entries: list[dict[str, Any]] = list(doc.get("entries") or [])
    by_id = {str(e.get("id")): e for e in entries if e.get("id")}

    applied: list[str] = []
    for sug in suggestions:
        if sug.action == "extend" and sug.target_id in by_id:
            by_id[sug.target_id] = _merge_entry(by_id[sug.target_id], sug)
            applied.append(f"extend:{sug.target_id}")
        elif sug.target_id not in by_id:
            by_id[sug.target_id] = sug.to_entry()
            applied.append(f"create:{sug.target_id}")
        else:
            by_id[sug.target_id] = _merge_entry(by_id[sug.target_id], sug)
            applied.append(f"merge:{sug.target_id}")

    doc["entries"] = list(by_id.values())
    MAPPING_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    load_mapping_entries.cache_clear()
    from core.product_mapping import cluster_to_primary_group

    cluster_to_primary_group.cache_clear()
    return {"applied": applied, "entries": len(doc["entries"])}


def write_suggestions_file(suggestions: list[MappingSuggestion]) -> None:
    payload = {
        "generated_for": "top_unmapped_hotline_clusters",
        "suggestions": [
            {
                "action": s.action,
                "target_id": s.target_id,
                "label": s.label,
                "tickets_covered": s.tickets_covered,
                "entry": s.to_entry(),
            }
            for s in suggestions
        ],
    }
    SUGGESTIONS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def clear_mapping_suggestion_caches() -> None:
    load_mapping_entries.cache_clear()
    from core.product_mapping import cluster_to_primary_group

    cluster_to_primary_group.cache_clear()
