"""Demo-Modus — Snapshot und Pfade aus data/demo/."""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

for _mod in ("google.cloud", "google.cloud.bigquery", "langchain_core", "langchain_core.documents"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


def test_demo_snapshot_file_exists():
    root = Path(__file__).resolve().parent.parent
    snap = root / "data" / "demo" / "workspace_snapshot.json"
    assert snap.exists(), "data/demo/workspace_snapshot.json fehlt"


def test_demo_snapshot_has_no_real_product_names():
    import json

    root = Path(__file__).resolve().parent.parent
    snap = json.loads((root / "data" / "demo" / "workspace_snapshot.json").read_text(encoding="utf-8"))
    blob = json.dumps(snap, ensure_ascii=False).lower()
    for forbidden in ("riwagisdata", "terawindata", "rgz client", "kartenapp", "riwa"):
        assert forbidden not in blob, f"Echter Produktname in Demo-Snapshot: {forbidden}"


def test_demo_tickets_use_fictional_clusters():
    root = Path(__file__).resolve().parent.parent
    csv_text = (root / "data" / "demo" / "tickets_backlog.csv").read_text(encoding="utf-8").lower()
    assert "geosuite" in csv_text
    assert "riwagisdata" not in csv_text


@patch("workspace.snapshot._load_snapshot_file")
def test_load_snapshot_demo_source(mock_load, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib
    import config
    import workspace.snapshot as snapshot_mod

    importlib.reload(config)
    importlib.reload(snapshot_mod)

    mock_load.return_value = {
        "fingerprint": "demo-test",
        "built_at": "2026-07-17T06:00:00+00:00",
        "cluster_counts": {},
        "source_themes": {},
        "data_coverage": [],
    }
    result = snapshot_mod.load_workspace_snapshot(force_rebuild=False)
    assert result.source == "demo"
    assert not result.stale


def test_demo_runtime_status(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib
    import config
    import core.runtime as runtime_mod

    importlib.reload(config)
    importlib.reload(runtime_mod)

    status = runtime_mod.get_runtime_status(check_ollama=False)
    assert status.demo_mode is True
    assert status.gcp_ok is False
    assert "Demo-Modus" in status.messages[0]


def test_apply_demo_paths_when_enabled(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib

    import config

    importlib.reload(config)
    assert config.DEMO_MODE is True
    assert config.SNAPSHOT_PATH.parent.name == "demo"
    assert config.PRODUCT_MODULE_MAPPING_PATH.parent.name == "demo"
    monkeypatch.delenv("DEMO_MODE", raising=False)
    importlib.reload(config)


def test_gis_pain_uses_demo_bereich(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib
    import config
    import core.demo_scope as demo_scope_mod
    import core.gis_pain as gis_mod

    importlib.reload(config)
    importlib.reload(demo_scope_mod)
    importlib.reload(gis_mod)
    assert gis_mod.GIS_BEREICH == "geoSuiteData"


def test_apply_demo_paths_keeps_sales_and_tera_on_production_paths(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib

    import config

    importlib.reload(config)
    root = Path(__file__).resolve().parent.parent
    assert config.SALES_PRODUCT_PENETRATION_CSV == root / "data" / "sales_product_penetration.csv"
    assert config.TERA_INSTALLATIONS_CSV == root / "data" / "tera_installations.csv"
    assert config.TERA_HOTLINE_MAPPING_PATH == root / "data" / "tera_hotline_mapping.json"
    monkeypatch.delenv("DEMO_MODE", raising=False)
    importlib.reload(config)


def test_list_catalog_sources_hides_sales_in_demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib

    import config
    import workspace.catalog as catalog_mod

    importlib.reload(config)
    importlib.reload(catalog_mod)
    names = {s["technical_name"] for s in catalog_mod.list_catalog_sources()}
    assert "sales_product_penetration" not in names


def test_demo_data_has_no_tera_or_erp_artifacts():
    root = Path(__file__).resolve().parent.parent
    demo_dir = root / "data" / "demo"
    assert not (demo_dir / "sales_product_penetration.csv").exists()
    assert not (demo_dir / "tera_installations.csv").exists()
    assert not (demo_dir / "tera_hotline_mapping.json").exists()


@patch("core.trust_status.build_trust_status")
@patch("core.evidence_orchestrator._load_product_signals_df")
@patch("core.evidence_orchestrator.is_graylog_usage_question", return_value=False)
def test_evidence_orchestrator_skips_tera_and_sales_in_demo(
    _mock_graylog,
    mock_signals,
    mock_trust,
    monkeypatch,
):
    monkeypatch.setenv("DEMO_MODE", "true")
    import importlib

    import config
    import core.evidence_orchestrator as orch_mod
    from core.sales_evidence import SALES_TECHNICAL_NAME
    from core.trust_status import TrustStatus
    from workspace.snapshot import WorkspaceSnapshot

    importlib.reload(config)
    importlib.reload(orch_mod)

    mock_signals.return_value = __import__("pandas").DataFrame()
    mock_trust.return_value = TrustStatus(
        level="mittel",
        summary="demo",
        snapshot_at="—",
        snapshot_source="disk",
        mapping_seed_entries=0,
        matrix_rows=0,
        matrix_mapped=0,
        matrix_mapped_pct=0.0,
        hotline_unmapped_pct=0.0,
        hotline_aligned=True,
        survey_match_pct=0.0,
        rag_fresh=True,
        rag_label="ok",
        rag_documents=0,
        product_signals_label="—",
        warnings=(),
        actions=(),
        top_unmapped=(),
    )
    ws = WorkspaceSnapshot.from_dict(
        {
            "fingerprint": "demo",
            "built_at": "2026-07-17T06:00:00+00:00",
            "cluster_counts": {},
            "source_themes": {},
            "data_coverage": [],
            "sales_top_products": [],
            "sales_top_revenue": [],
            "sales_total_revenue": 0.0,
            "priority_matrix": [],
            "intent_by_group": [],
            "intent_by_module": [],
        }
    )
    ctx = orch_mod.assemble_assistant_context(
        "TERA Support Druck und ERP Umsatz Priorität",
        [SALES_TECHNICAL_NAME, "support_tickets_html"],
        ws,
    )
    assert "TERA" not in ctx.domains
    assert "Sales" not in ctx.domains
    joined = "\n".join(ctx.user_blocks)
    assert "TERA" not in joined
    assert "ERP" not in joined
