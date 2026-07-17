"""
Signale vs. Reach — einheitliche Quellen-Aufteilung für das Dashboard.

Drei Linsen auf Rohdaten-Ebene:
  Stimmen (Say · Freitext) · Feel (Skalen) · Reach (Do)
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from config import DELIMITER
from core.intent_sources import freetext_inventory
from core.module_ranking import RANKING_CSV
from core.module_usage import USAGE_CSV
from core.survey_data import SURVEY_SOURCE_LABEL
from core.survey_inventory import survey_inventory


@dataclass(frozen=True)
class SourceLane:
    """Eine zählbare Quelle in einer Linse."""

    key: str
    label: str
    count: int
    hint: str = ""


@dataclass(frozen=True)
class ReachInventory:
    graylog_module_rows: int
    graylog_nutzer_sum: int
    ranking_module_rows: int
    ranking_kunden_sum: int

    @property
    def breakdown(self) -> str:
        return (
            f"Graylog {self.graylog_nutzer_sum} Nutzer ({self.graylog_module_rows} Module) · "
            f"Ranking {self.ranking_kunden_sum} Kunden ({self.ranking_module_rows} Module)"
        )


@dataclass(frozen=True)
class SignalOverview:
    """Rohsignale nach Linse — ohne Produkt-Matrix-Doppelzählung."""

    stimmen: tuple[SourceLane, ...]
    feel: tuple[SourceLane, ...]
    reach: ReachInventory

    @property
    def stimmen_total(self) -> int:
        return sum(lane.count for lane in self.stimmen)

    @property
    def feel_skalen_total(self) -> int:
        return next((lane.count for lane in self.feel if lane.key == "skalen"), 0)

    def stimmen_breakdown(self) -> str:
        return " · ".join(f"{lane.label} {lane.count}" for lane in self.stimmen if lane.count)

    def feel_breakdown(self) -> str:
        return " · ".join(f"{lane.label} {lane.count}" for lane in self.feel if lane.count)


@lru_cache(maxsize=1)
def reach_inventory() -> ReachInventory:
    graylog_rows = graylog_sum = 0
    if USAGE_CSV.exists():
        df = pd.read_csv(USAGE_CSV, sep=DELIMITER, encoding="utf-8-sig")
        if not df.empty and "aktive_nutzer" in df.columns:
            graylog_rows = len(df)
            graylog_sum = int(pd.to_numeric(df["aktive_nutzer"], errors="coerce").fillna(0).sum())

    ranking_rows = ranking_sum = 0
    if RANKING_CSV.exists():
        df = pd.read_csv(RANKING_CSV, sep=DELIMITER, encoding="utf-8-sig")
        if not df.empty and "Kunden" in df.columns:
            ranking_rows = len(df)
            ranking_sum = int(pd.to_numeric(df["Kunden"], errors="coerce").fillna(0).sum())

    return ReachInventory(
        graylog_module_rows=graylog_rows,
        graylog_nutzer_sum=graylog_sum,
        ranking_module_rows=ranking_rows,
        ranking_kunden_sum=ranking_sum,
    )


def clear_signal_inventory_cache() -> None:
    signal_overview.cache_clear()
    reach_inventory.cache_clear()
    from core.survey_inventory import clear_survey_inventory_cache

    clear_survey_inventory_cache()


@lru_cache(maxsize=1)
def signal_overview() -> SignalOverview:
    ft = freetext_inventory()
    survey = survey_inventory()
    reach = reach_inventory()

    stimmen: list[SourceLane] = [
        SourceLane(
            key="hotline",
            label="Hotline",
            count=ft.hotline,
            hint="HTML Scraper-Scope (riwaGis + teraWin + otsBau, ohne Allgemein)",
        ),
        SourceLane(
            key="feldbesuche",
            label="Feldbesuche",
            count=ft.feldbesuche,
            hint="Weihnachtsbesuche / Feldfeedback",
        ),
        SourceLane(
            key="umfrage_freitext",
            label="Umfrage-Anregung",
            count=ft.umfrage_freitext,
            hint=f"Freitext-Spalte in {survey.source_file} (Anregungen/Wünsche)",
        ),
    ]
    if ft.extra:
        for label, count in ft.extra:
            stimmen.append(
                SourceLane(
                    key=f"extra:{label}",
                    label=label,
                    count=count,
                    hint="Weitere Inbox-/Pipeline-CSV mit Freitext",
                )
            )

    skalen_ohne = max(survey.raw_rows - ft.umfrage_freitext, 0)
    feel: list[SourceLane] = [
        SourceLane(
            key="skalen",
            label=f"{SURVEY_SOURCE_LABEL} · Skalen",
            count=survey.raw_rows,
            hint=f"Alle Zeilen in {survey.source_file} (NPS, UX, Support …)",
        ),
        SourceLane(
            key="skalen_ohne_freitext",
            label="nur Skalen",
            count=skalen_ohne,
            hint="Umfragezeilen ohne auswertbaren Anregungs-Freitext",
        ),
        SourceLane(
            key="skalen_mit_freitext",
            label="mit Anregung",
            count=ft.umfrage_freitext,
            hint="Überlappt mit Stimmen Σ (dieselben Freitexte)",
        ),
    ]

    return SignalOverview(stimmen=tuple(stimmen), feel=tuple(feel), reach=reach)
