"""Unit-Tests für Graylog Usage-Import (ohne Live-API)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.graylog_client import (
    GraylogClient,
    GraylogConfigError,
    auth_headers,
    normalize_base_url,
)
from core.graylog_usage import aggregate_usage, detect_fields, flatten_graylog_message, top_module_values


SAMPLE_MESSAGES = [
    {"module": "Modul Verkehr", "user_id": "u1", "timestamp": "2026-01-01T10:00:00.000Z"},
    {"module": "Modul Verkehr", "user_id": "u2", "timestamp": "2026-01-01T11:00:00.000Z"},
    {"module": "Modul Verkehr", "user_id": "u1", "timestamp": "2026-01-01T12:00:00.000Z"},
    {"module": "KartenApp", "username": "alice", "timestamp": "2026-01-01T13:00:00.000Z"},
    {"module": "KartenApp", "username": "bob", "timestamp": "2026-01-01T14:00:00.000Z"},
    {"Modulname": "Modul Wasser", "login": "x1", "timestamp": "2026-01-02T10:00:00.000Z"},
]


def test_normalize_base_url_strips_trailing_slash():
    assert normalize_base_url("http://graylog.example:9100/") == "http://graylog.example:9100"
    assert normalize_base_url("  http://host  ") == "http://host"


def test_auth_headers_include_requested_by():
    headers = auth_headers()
    assert headers["X-Requested-By"] == "pm-signals"


def test_graylog_client_requires_url_and_token():
    with pytest.raises(GraylogConfigError, match="GRAYLOG_URL"):
        GraylogClient(base_url="", token="abc")
    with pytest.raises(GraylogConfigError, match="GRAYLOG_TOKEN"):
        GraylogClient(base_url="http://localhost:9100", token="")


def test_graylog_client_auth_tuple():
    client = GraylogClient(base_url="http://localhost:9100", token="my-secret-token")
    assert client.auth == ("my-secret-token", "token")


@patch("core.graylog_client.requests.request")
def test_search_absolute_posts_json_with_stream_filter(mock_request):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.content = b'{"messages": []}'
    mock_response.json.return_value = {"messages": []}
    mock_request.return_value = mock_response

    client = GraylogClient(base_url="http://graylog:9100", token="tok")
    client.search_absolute(
        "*",
        ["stream-a", "stream-b"],
        "2026-01-01T00:00:00.000Z",
        "2026-01-31T23:59:59.000Z",
        limit=100,
        offset=0,
    )

    mock_request.assert_called_once()
    call_kwargs = mock_request.call_args.kwargs
    assert call_kwargs["auth"] == ("tok", "token")
    assert call_kwargs["headers"]["X-Requested-By"] == "pm-signals"
    body = call_kwargs.get("json") or {}
    assert body["filter"] == "streams:stream-a,stream-b"
    assert body["query"] == "*"
    assert body["fields"] == "timestamp,source,message"


def test_flatten_graylog_message_parses_inner_json():
    raw = {
        "source": "rgz2tcrz5",
        "message": '{"adminId":931,"event":"module.gis.query.desktop","moduleKey":1011}',
        "timestamp": "2026-07-14T07:28:06.392Z",
    }
    flat = flatten_graylog_message(raw)
    assert flat["adminId"] == 931
    assert flat["event"] == "module.gis.query.desktop"
    assert flat["source"] == "rgz2tcrz5"


def test_detect_fields_rgz_statistik_payload():
    raw = {
        "source": "rgz2tcrz5",
        "message": '{"adminId":931,"adminName":"penzberg_gd","event":"module.gis.query.desktop","moduleKey":1011}',
    }
    mod, usr = detect_fields([flatten_graylog_message(raw)])
    assert mod == "event"
    assert usr == "adminId"
    mod, usr = detect_fields(SAMPLE_MESSAGES[:3])
    assert mod == "module"
    assert usr == "user_id"


def test_detect_fields_falls_back_to_modulname_and_login():
    mod, usr = detect_fields([SAMPLE_MESSAGES[5]])
    assert mod == "Modulname"
    assert usr == "login"


def test_aggregate_usage_counts_unique_users_per_module():
    df = aggregate_usage(SAMPLE_MESSAGES[:3], "module", "user_id")
    assert len(df) == 1
    verkehr = df[df["modulname"] == "Modul Verkehr"].iloc[0]
    assert int(verkehr["aktive_nutzer"]) == 2

    df_user = aggregate_usage(SAMPLE_MESSAGES[3:5], "module", "username")
    assert len(df_user) == 1
    karten = df_user[df_user["modulname"] == "KartenApp"].iloc[0]
    assert int(karten["aktive_nutzer"]) == 2


def test_aggregate_usage_empty_when_fields_missing():
    df = aggregate_usage(SAMPLE_MESSAGES, "", "user_id")
    assert df.empty
    assert list(df.columns) == ["modulname", "aktive_nutzer"]


def test_top_module_values():
    ranked = top_module_values(SAMPLE_MESSAGES[:5], "module", limit=5)
    assert ranked[0] == ("Modul Verkehr", 3)
    assert ("KartenApp", 2) in ranked

def test_aggregate_usage_prefers_dialog_name_for_rgz_dialog_events():
    messages = [
        {
            "adminId": "u1",
            "event": "module.dialog.load",
            "dialogName": "Grabstättenverwaltung",
        },
        {
            "adminId": "u2",
            "event": "module.dialog.load",
            "dialogName": "Grabstättenverwaltung",
        },
        {
            "adminId": "u1",
            "event": "module.dialog.load",
            "dialogName": "Dokumentübersicht",
        },
    ]
    df = aggregate_usage(messages, "event", "adminId")
    grab = df[df["modulname"] == "Grabstättenverwaltung"].iloc[0]
    assert int(grab["aktive_nutzer"]) == 2
    assert "module.dialog.load" not in set(df["modulname"])

