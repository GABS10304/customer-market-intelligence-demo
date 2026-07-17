"""Unit-Tests für Graylog-Event-Mapping."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.graylog_event_mapping import (
    clear_graylog_mapping_cache,
    is_graylog_skipped,
    resolve_graylog_modul,
)
from core.graylog_usage import aggregate_usage_by_mapping, resolve_usage_mapping_id
from core.module_ranking import resolve_ranking_modul


@pytest.fixture(autouse=True)
def _reset_mapping_cache():
    clear_graylog_mapping_cache()
    yield
    clear_graylog_mapping_cache()


def test_resolve_graylog_modul_baum():
    assert resolve_graylog_modul("Baum") == "modul_baeume"
    assert resolve_graylog_modul("Baumkontroll") == "modul_baeume"
    assert resolve_graylog_modul("Baummaßnahmen") == "modul_baeume"
    assert resolve_graylog_modul("Baumdateien") == "modul_baeume"
    assert resolve_graylog_modul("Arten in Baumgruppe") == "modul_baeume"


def test_resolve_graylog_modul_baumkontrolle_historisch():
    assert resolve_graylog_modul("Baumkontrolle historisch") == "baumkontroll_app"


def test_resolve_graylog_modul_baum_prefix_fallback():
    assert resolve_graylog_modul("Baum - Unbekannter Unterdialog") == "modul_baeume"
    assert resolve_graylog_modul("Baumkontrolle historisch") == "baumkontroll_app"


def test_resolve_graylog_modul_exact_match():
    assert resolve_graylog_modul("module.gis.query.desktop") == "rgz_basic"
    assert resolve_graylog_modul("Flurstücke") == "datenpflege_alkis"
    assert resolve_graylog_modul("Gebühren/Kosten") == "modul_verkehr"


def test_resolve_graylog_modul_prefix_match():
    assert resolve_graylog_modul("Verkehrsrechtliche Anordnungen - Umleitungen") == "modul_verkehr"
    assert resolve_graylog_modul("Verkehrszeichen - Standort") == "modul_verkehr"
    assert resolve_graylog_modul("Verkehrsinfos - Straßenachsen") == "modul_verkehr"


def test_resolve_graylog_modul_unknown_returns_none():
    assert resolve_graylog_modul("Unbekannter Dialog XYZ") is None
    assert resolve_graylog_modul("") is None


def test_is_graylog_skipped(tmp_path: Path, monkeypatch):
    mapping = {
        "version": "1.0",
        "exact": {"server.logout": "rgz_basic"},
        "prefix": {},
        "skip": ["server.logout"],
    }
    path = tmp_path / "graylog_event_mapping.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setattr("core.graylog_event_mapping.MAPPING_PATH", path)
    clear_graylog_mapping_cache()

    assert is_graylog_skipped("server.logout") is True
    assert resolve_graylog_modul("server.logout") is None


def test_resolve_usage_mapping_id_falls_back_to_ranking():
    assert resolve_usage_mapping_id("Grabstättenverwaltung") == "modul_friedhof"
    ranking = resolve_ranking_modul("Unbekanntes Modul XYZ")
    assert resolve_usage_mapping_id("Unbekanntes Modul XYZ") == ranking.mapping_id
    assert ranking.mapping_id.startswith("ranking_")


def test_aggregate_usage_by_mapping_dedupes_users_across_dialogs():
    messages = [
        {"adminId": "u1", "event": "module.dialog.load", "dialogName": "Flurstücke"},
        {"adminId": "u2", "event": "module.dialog.load", "dialogName": "Flurstücke"},
        {"adminId": "u1", "event": "module.dialog.load", "dialogName": "ALKIS Link"},
        {"adminId": "u3", "event": "module.gis.query.desktop"},
    ]
    df = aggregate_usage_by_mapping(messages, "event", "adminId")
    alkis = df[df["mapping_id"] == "datenpflege_alkis"].iloc[0]
    rgz = df[df["mapping_id"] == "rgz_basic"].iloc[0]
    assert int(alkis["aktive_nutzer"]) == 2
    assert int(rgz["aktive_nutzer"]) == 1


def test_aggregate_usage_by_mapping_skips_events(tmp_path: Path, monkeypatch):
    mapping = {
        "version": "1.0",
        "exact": {"server.logout": "rgz_basic", "module.gis.query.desktop": "rgz_basic"},
        "prefix": {},
        "skip": ["server.logout"],
    }
    path = tmp_path / "graylog_event_mapping.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setattr("core.graylog_event_mapping.MAPPING_PATH", path)
    clear_graylog_mapping_cache()

    messages = [
        {"adminId": "u1", "event": "server.logout"},
        {"adminId": "u2", "event": "module.gis.query.desktop"},
    ]
    df = aggregate_usage_by_mapping(messages, "event", "adminId")
    assert int(df[df["mapping_id"] == "rgz_basic"]["aktive_nutzer"].iloc[0]) == 1
