"""
Graylog REST-Client — Universal Search für Modul-Usage-Import.

Auth: HTTP Basic (GRAYLOG_TOKEN als Username, Passwort „token“).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from config import GRAYLOG_TOKEN, GRAYLOG_URL, GRAYLOG_VERIFY_SSL


class GraylogError(Exception):
    """Fehler bei Graylog-API-Aufrufen."""


class GraylogConfigError(GraylogError):
    """Fehlende oder ungültige Graylog-Konfiguration."""


REQUESTED_BY = "pm-signals"
DEFAULT_PAGE_SIZE = 500
DEFAULT_SEARCH_FIELDS = "timestamp,source,message"


def normalize_base_url(url: str) -> str:
    """Entfernt trailing slash von der Basis-URL."""
    return (url or "").strip().rstrip("/")


def auth_headers() -> dict[str, str]:
    """Standard-Header inkl. X-Requested-By für Graylog REST."""
    return {
        "X-Requested-By": REQUESTED_BY,
        "Accept": "application/json",
    }


class GraylogClient:
    """Minimaler Graylog-5-Client für Ping, Streams und Universal Search."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        verify_ssl: bool | None = None,
    ) -> None:
        resolved_url = GRAYLOG_URL if base_url is None else base_url
        resolved_token = GRAYLOG_TOKEN if token is None else token
        self.base_url = normalize_base_url(resolved_url)
        self.token = resolved_token.strip()
        self.verify_ssl = GRAYLOG_VERIFY_SSL if verify_ssl is None else verify_ssl
        if not self.base_url:
            raise GraylogConfigError("GRAYLOG_URL ist nicht gesetzt (.env oder Parameter).")
        if not self.token:
            raise GraylogConfigError("GRAYLOG_TOKEN ist nicht gesetzt (.env oder Parameter).")

    @property
    def auth(self) -> tuple[str, str]:
        return (self.token, "token")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = auth_headers()
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = requests.request(
                method,
                url,
                auth=self.auth,
                headers=headers,
                params=params,
                json=json_body,
                verify=self.verify_ssl,
                timeout=120,
            )
        except requests.RequestException as exc:
            raise GraylogError(f"Graylog-Verbindung fehlgeschlagen: {exc}") from exc

        if not response.ok:
            snippet = (response.text or "")[:300]
            raise GraylogError(
                f"Graylog {method} {path} -> HTTP {response.status_code}: {snippet}"
            )

        if not response.content:
            return {}
        return response.json()

    def ping(self) -> dict[str, Any]:
        """System-Info inkl. Version."""
        return self._request("GET", "/api/system")

    def list_streams(self) -> list[dict[str, Any]]:
        """Alle Streams (id, title, …)."""
        data = self._request("GET", "/api/streams")
        streams = data.get("streams")
        return list(streams) if isinstance(streams, list) else []

    def search_absolute(
        self,
        query: str,
        stream_ids: list[str],
        from_iso: str,
        to_iso: str,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Universal Search (absolute Zeitraum) — legacy /api/search/universal/absolute."""
        payload: dict[str, Any] = {
            "query": query or "*",
            "from": from_iso,
            "to": to_iso,
            "limit": limit,
            "offset": offset,
            "sort": "timestamp:desc",
            "fields": DEFAULT_SEARCH_FIELDS,
            "decorate": "false",
        }
        if stream_ids:
            payload["filter"] = "streams:" + ",".join(stream_ids)

        # Graylog 5.2 legacy endpoint: POST oft 405 — GET mit Query-Parametern.
        try:
            return self._request(
                "POST",
                "/api/search/universal/absolute",
                json_body=payload,
            )
        except GraylogError as exc:
            if "HTTP 405" not in str(exc):
                raise
            return self._request(
                "GET",
                "/api/search/universal/absolute",
                params=payload,
            )

    @staticmethod
    def _extract_message_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in payload.get("messages") or []:
            if not isinstance(item, dict):
                continue
            msg = item.get("message")
            if isinstance(msg, dict):
                rows.append(msg)
        return rows

    def fetch_messages_between(
        self,
        stream_ids: list[str],
        from_dt: datetime,
        to_dt: datetime,
        *,
        query: str = "*",
        max_messages: int = 10_000,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Paginiert Nachrichten zwischen zwei UTC-Zeitpunkten."""
        if max_messages < 1:
            return []
        if from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
        if to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)

        from_iso = from_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        to_iso = to_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        collected: list[dict[str, Any]] = []
        offset = 0
        limit = min(page_size, max_messages)

        while len(collected) < max_messages:
            payload = self.search_absolute(
                query,
                stream_ids,
                from_iso,
                to_iso,
                limit=limit,
                offset=offset,
            )
            batch = self._extract_message_rows(payload)
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < limit:
                break
            offset += len(batch)
            limit = min(page_size, max_messages - len(collected))

        return collected[:max_messages]

    def fetch_messages(
        self,
        stream_ids: list[str],
        days: int,
        *,
        query: str = "*",
        max_messages: int = 10_000,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Paginiert Nachrichten der letzten `days` Tage (max. `max_messages`)."""
        if days < 1:
            raise GraylogError("days muss >= 1 sein.")
        if max_messages < 1:
            return []

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        from_iso = start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        to_iso = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        collected: list[dict[str, Any]] = []
        offset = 0
        limit = min(page_size, max_messages)

        while len(collected) < max_messages:
            payload = self.search_absolute(
                query,
                stream_ids,
                from_iso,
                to_iso,
                limit=limit,
                offset=offset,
            )
            batch = self._extract_message_rows(payload)
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < limit:
                break
            offset += len(batch)
            limit = min(page_size, max_messages - len(collected))

        return collected[:max_messages]


def parse_stream_tokens(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def resolve_stream_ids(
    client: GraylogClient,
    tokens: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Mappt Stream-IDs oder -Namen auf IDs. Leer = alle Streams."""
    streams = client.list_streams()
    by_id = {str(s.get("id", "")).strip(): s for s in streams}
    by_title = {str(s.get("title", "")).strip().lower(): s for s in streams if s.get("title")}

    if not tokens:
        ids = [sid for sid in by_id if sid]
        labels = {sid: str(by_id[sid].get("title") or sid) for sid in ids}
        return ids, labels

    resolved: list[str] = []
    labels: dict[str, str] = {}
    for token in tokens:
        if token in by_id:
            sid = token
        else:
            match = by_title.get(token.lower())
            if match is None:
                raise GraylogError(f"Stream nicht gefunden: {token!r}")
            sid = str(match.get("id", "")).strip()
        if sid and sid not in resolved:
            resolved.append(sid)
            labels[sid] = str(by_id.get(sid, {}).get("title") or sid)
    return resolved, labels
