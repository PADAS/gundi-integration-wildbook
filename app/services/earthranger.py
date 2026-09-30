"""EarthRanger API calls the connector needs, made directly with the destination's token.

Gundi has no API to read or update EarthRanger events, so the connector talks to each
EarthRanger destination itself (credentials from `get_er_credentials_from_destinations`).
"""
import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def site_name(base_url: str) -> str:
    """The site name used in Wildbook stamps: `https://twiga.pamdas.org` -> `twiga`."""
    return urlparse(base_url if "//" in base_url else f"//{base_url}").hostname.split(".")[0]


def _data(response: httpx.Response):
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body


def _load(value):
    while isinstance(value, str):
        value = json.loads(value)
    return value


class EarthRangerClient:

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        parsed = urlparse(base_url if "//" in base_url else f"https://{base_url}")
        root = f"{parsed.scheme or 'https'}://{parsed.netloc}"
        self.v1 = f"{root}/api/v1.0"
        self.v2 = f"{root}/api/v2.0"
        self._client = httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=timeout)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def _get(self, url: str, **params):
        response = await self._client.get(url, params=params or None)
        response.raise_for_status()
        return _data(response)

    async def get_event_type_values(self) -> List[str]:
        """Every event type on the site, following the pages when the list is paginated."""
        values = []
        url, params = f"{self.v2}/activity/eventtypes/", {"include_inactive": "true"}
        while url:
            data = await self._get(url, **params)
            if isinstance(data, dict):
                values += [t["value"] for t in data.get("results", [])]
                url, params = data.get("next"), {}  # `next` already carries the query
            else:
                values += [t["value"] for t in data]
                url = None
        return values

    async def find_event_by_serial(self, serial: int) -> Optional[dict]:
        """The event with this number, or None. EarthRanger has no filter by number, so this
        searches the text and keeps the exact match."""
        data = await self._get(f"{self.v1}/activity/events", filter=json.dumps({"text": str(serial)}))
        results = data.get("results", []) if isinstance(data, dict) else data
        hits = [e for e in results if e.get("serial_number") == serial]
        return hits[0] if len(hits) == 1 else None

    async def find_copied_event(self, source_site: str, serial: int) -> Optional[dict]:
        """On a test site: the copy of `source_site`'s event with this number, found by the
        "Copied from <site> event #<number> (" note the copy script adds. None if not exactly one."""
        data = await self._get(f"{self.v1}/activity/events", filter=json.dumps({"text": str(serial)}),
                               include_notes="true")
        results = data.get("results", []) if isinstance(data, dict) else data
        note = re.compile(rf"copied from {re.escape(source_site)} event #{serial} \(", re.IGNORECASE)
        hits = [e for e in results if any(note.search(n.get("text") or "") for n in e.get("notes") or [])]
        return hits[0] if len(hits) == 1 else None

    async def get_event(self, event_id: str) -> dict:
        return await self._get(f"{self.v1}/activity/event/{event_id}")

    async def patch_event(self, event_id: str, body: dict) -> dict:
        response = await self._client.patch(f"{self.v1}/activity/event/{event_id}", json=body)
        response.raise_for_status()
        return _data(response)

    async def get_list_fields(self, event_type: str, list_field: str) -> Optional[Dict[str, Optional[dict]]]:
        """Fields of the rows in an event type's list field, as {field: dropdown options},
        where options are {display name: stored value} and None means a free-text or file
        field. None if the type has no such list.

        Older-format types return the options inline from the v1 schema endpoint. Newer-format
        types return nothing there; their dropdowns point to a shared choice list
        (`/api/v2.0/schemas/choices.json?field=<list>`) with the names in `x-enumExtra`.
        """
        rendered = await self._get(f"{self.v1}/activity/events/schema/eventtype/{event_type}")
        if rendered and rendered.get("schema"):
            items = rendered["schema"].get("properties", {}).get(list_field, {}).get("items")
            if not items:
                return None
            fields = {}
            for name, prop in (items.get("properties") or {}).items():
                if "enum" not in prop:
                    fields[name] = None
                    continue
                labels = prop.get("enumNames") or {}
                if isinstance(labels, list):
                    labels = dict(zip(prop["enum"], labels))
                fields[name] = {labels.get(v, v): v for v in prop["enum"]}
            return fields

        event_type_data = await self._get(f"{self.v2}/activity/eventtypes/{event_type}", include_schema="true")
        schema = _load((event_type_data or {}).get("schema")) or {}
        items = schema.get("json", {}).get("properties", {}).get(list_field, {}).get("items")
        if not items:
            return None
        fields = {}
        for name, prop in (items.get("properties") or {}).items():
            refs = [a.get("$ref", "") for a in prop.get("anyOf", []) if "choices.json?field=" in a.get("$ref", "")]
            if not refs:
                fields[name] = None
                continue
            choices = await self._get(f"{self.v2}/schemas/choices.json", field=refs[0].split("field=", 1)[1])
            extra = choices.get("x-enumExtra") or {}
            fields[name] = {(extra.get(v) or {}).get("display", v): v for v in choices.get("enum") or []}
        return fields

