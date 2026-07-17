"""Erweiterte Tests für core.graylog_client (ohne Live-API)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.graylog_client import (
    GraylogClient,
    GraylogError,
    GraylogConfigError,
    parse_stream_tokens,
    resolve_stream_ids,
)


def _client() -> GraylogClient:
    return GraylogClient(base_url="http://graylog:9100", token="secret")


def _msg(event: str, admin: str = "u1") -> dict:
    return {
        "message": {"event": event, "adminId": admin, "timestamp": "2026-01-01T10:00:00.000Z"}
    }


@patch("core.graylog_client.requests.request")
def test_ping_and_list_streams(mock_request):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.content = b'{"version":"5.2"}'
    mock_response.json.side_effect = [
        {"version": "5.2"},
        {"streams": [{"id": "s1", "title": "RGZ Statistik"}]},
    ]
    mock_request.return_value = mock_response

    client = _client()
    assert client.ping()["version"] == "5.2"
    streams = client.list_streams()
    assert streams[0]["id"] == "s1"


@patch("core.graylog_client.requests.request")
def test_search_absolute_falls_back_to_get_on_405(mock_request):
    fail = MagicMock(ok=False, status_code=405, text="Method Not Allowed")
    ok = MagicMock(ok=True, content=b'{"messages": []}', json=lambda: {"messages": []})

    mock_request.side_effect = [
        fail,
        ok,
    ]

    client = _client()
    result = client.search_absolute("*", ["s1"], "2026-01-01T00:00:00.000Z", "2026-01-02T00:00:00.000Z")
    assert result == {"messages": []}
    assert mock_request.call_count == 2
    assert mock_request.call_args_list[1].kwargs.get("params") is not None


@patch("core.graylog_client.requests.request")
def test_request_raises_on_connection_error(mock_request):
    mock_request.side_effect = requests.ConnectionError("timeout")
    client = _client()
    with pytest.raises(GraylogError, match="Verbindung"):
        client.ping()


@patch("core.graylog_client.requests.request")
def test_request_raises_on_http_error(mock_request):
    mock_request.return_value = MagicMock(ok=False, status_code=500, text="boom")
    with pytest.raises(GraylogError, match="HTTP 500"):
        _client().ping()


def test_extract_message_rows_skips_invalid_entries():
    payload = {
        "messages": [
            {"message": {"event": "a"}},
            {"message": "not-a-dict"},
            "invalid",
            {"message": {"event": "b"}},
        ]
    }
    rows = GraylogClient._extract_message_rows(payload)
    assert len(rows) == 2


@patch.object(GraylogClient, "search_absolute")
def test_fetch_messages_between_paginates(mock_search):
    mock_search.side_effect = [
        {"messages": [_msg("e1"), _msg("e2")]},
        {"messages": [_msg("e3")]},
    ]
    client = _client()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    rows = client.fetch_messages_between(["s1"], start, end, max_messages=10, page_size=2)
    assert len(rows) == 3
    assert mock_search.call_count == 2


@patch.object(GraylogClient, "search_absolute")
def test_fetch_messages_between_returns_empty_for_zero_max(mock_search):
    client = _client()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert client.fetch_messages_between(["s1"], start, end, max_messages=0) == []
    mock_search.assert_not_called()


def test_fetch_messages_invalid_days():
    with pytest.raises(GraylogError, match="days"):
        _client().fetch_messages(["s1"], days=0)


@patch.object(GraylogClient, "list_streams")
def test_resolve_stream_ids_by_title(mock_streams):
    mock_streams.return_value = [
        {"id": "663a4c", "title": "RGZ Statistik"},
        {"id": "other", "title": "Other"},
    ]
    ids, labels = resolve_stream_ids(_client(), ["RGZ Statistik"])
    assert ids == ["663a4c"]
    assert labels["663a4c"] == "RGZ Statistik"


@patch.object(GraylogClient, "list_streams")
def test_resolve_stream_ids_empty_tokens_returns_all(mock_streams):
    mock_streams.return_value = [
        {"id": "a", "title": "A"},
        {"id": "b", "title": "B"},
    ]
    ids, labels = resolve_stream_ids(_client(), [])
    assert set(ids) == {"a", "b"}
    assert labels["a"] == "A"


@patch.object(GraylogClient, "list_streams")
def test_resolve_stream_ids_unknown_raises(mock_streams):
    mock_streams.return_value = [{"id": "a", "title": "A"}]
    with pytest.raises(GraylogError, match="nicht gefunden"):
        resolve_stream_ids(_client(), ["missing"])


def test_parse_stream_tokens():
    assert parse_stream_tokens(" a, b ,,c ") == ["a", "b", "c"]
    assert parse_stream_tokens("") == []
