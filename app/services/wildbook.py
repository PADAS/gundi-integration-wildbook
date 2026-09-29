"""Wildbook API v3 client (token auth).

Search endpoints take OpenSearch queries and page with `from`/`size`, where
`from + size` can't go past 10,000; the total comes back in the
`X-Wildbook-Total-Hits` header. Callers that may hit more than that split the
query into smaller windows (see `search_all`).
"""
import logging
from typing import Dict, List, Tuple

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://giraffespotter.org"
MAX_RESULT_WINDOW = 10_000
PAGE_SIZE = 500
RESOLVE_BATCH = 100


class WildbookClient:

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        self.api_root = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}/api/v3"
        self._client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def search(self, index: str, query: dict, start: int = 0, size: int = PAGE_SIZE) -> Tuple[List[dict], int]:
        """One page of an index search: (hits, total)."""
        response = await self._client.post(
            f"{self.api_root}/search/{index}",
            params={"from": start, "size": size},
            json={"query": query},
        )
        response.raise_for_status()
        hits = response.json().get("hits") or []
        total = int(response.headers.get("X-Wildbook-Total-Hits", len(hits)))
        return hits, total

    async def search_all(self, index: str, query: dict) -> List[dict]:
        """Every hit of a query that fits in one result window."""
        hits, total = await self.search(index, query)
        if total > MAX_RESULT_WINDOW:
            raise ValueError(f"{total} results is more than one search can return; split the query")
        while len(hits) < total:
            page, _ = await self.search(index, query, start=len(hits))
            if not page:
                break
            hits.extend(page)
        return hits

    async def get_encounters_changed(self, since_ms: int, until_ms: int, remarks_pattern: str) -> List[dict]:
        """Encounters changed after `since_ms` and up to `until_ms` (epoch ms, `version`)
        whose remarks match `remarks_pattern`. Windows with more results than one search
        can return are split in half until each fits."""
        query = {"bool": {"filter": [
            {"range": {"version": {"gt": since_ms, "lte": until_ms}}},
            {"wildcard": {"occurrenceRemarks.keyword": remarks_pattern}},
        ]}}
        _, total = await self.search("encounter", query, size=1)
        if total > MAX_RESULT_WINDOW and until_ms - since_ms > 1:
            middle = since_ms + (until_ms - since_ms) // 2
            return (await self.get_encounters_changed(since_ms, middle, remarks_pattern)
                    + await self.get_encounters_changed(middle, until_ms, remarks_pattern))
        return await self.search_all("encounter", query) if total else []

    async def get_individual_names(self, individual_ids: List[str]) -> Dict[str, str]:
        names = {}
        ids = sorted(set(individual_ids))
        for i in range(0, len(ids), RESOLVE_BATCH):
            hits = await self.search_all("individual", {"terms": {"id": ids[i:i + RESOLVE_BATCH]}})
            names.update({h["id"]: h.get("displayName") for h in hits})
        return names

    async def get_right_side_photos(self, encounter_ids: List[str]) -> Dict[str, str]:
        """The first right-side photo URL of each encounter that has one."""
        photos = {}
        ids = sorted(set(encounter_ids))
        for i in range(0, len(ids), RESOLVE_BATCH):
            annotations = await self.search_all("annotation", {"terms": {"encounterId": ids[i:i + RESOLVE_BATCH]}})
            annotation_ids = [a["id"] for a in annotations]
            for j in range(0, len(annotation_ids), RESOLVE_BATCH):
                response = await self._client.post(
                    f"{self.api_root}/media/resolve",
                    json={"annotationIds": annotation_ids[j:j + RESOLVE_BATCH]},
                )
                response.raise_for_status()
                for media in response.json() or []:
                    encounter_id = media.get("encounterId")
                    if (media.get("imageUrl") and "right" in (media.get("viewpoint") or "")
                            and encounter_id not in photos):
                        photos[encounter_id] = media["imageUrl"]
        return photos

    async def download(self, url: str) -> bytes:
        # Photo URLs are public; the token is not sent to the media host.
        async with httpx.AsyncClient(timeout=self._client.timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def check_token(self) -> None:
        await self.search("encounter", {"match_all": {}}, size=1)
