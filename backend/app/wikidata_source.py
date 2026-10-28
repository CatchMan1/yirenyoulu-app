"""Allowlisted official API, bounded responses/retries and durable request budget."""

import json
import time

import httpx
from sqlalchemy import select

from .data_adapters import qid
from .http import aware, utcnow
from .ingestion import policy_for
from .models import ImportPermit

ENDPOINT = "https://www.wikidata.org/w/api.php"
USER_AGENT = "YirenYouluSample/0.2 (https://github.com/CatchMan1/yirenyoulu-app)"


def reserve_request(sessions, source_id):
    with sessions.begin() as db:
        policy_for(db, source_id, True)
        permit = db.scalar(
            select(ImportPermit).where(ImportPermit.source_id == source_id).with_for_update()
        )
        if not permit or aware(permit.expires_at) <= utcnow():
            raise ValueError("PERMIT_REQUIRED")
        if permit.used_requests >= permit.max_requests:
            raise ValueError("REQUEST_BUDGET_EXHAUSTED")
        permit.used_requests += 1


def fetch_entities(sessions, source_id, ids, transport=None):
    if not 1 <= len(ids) <= 25:
        raise ValueError("ENTITY_BATCH_LIMIT")
    ids = list(dict.fromkeys(qid(value) for value in ids))
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(15, connect=5),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as client:
        for attempt in range(3):
            reserve_request(sessions, source_id)
            try:
                with client.stream(
                    "GET",
                    ENDPOINT,
                    params={
                        "action": "wbgetentities",
                        "format": "json",
                        "ids": "|".join(ids),
                        "props": "labels|claims|info",
                        "languages": "zh-hans|zh|en",
                        "maxlag": "5",
                    },
                ) as response:
                    retry = response.status_code in {429, 502, 503, 504}
                    if retry:
                        raw = response.headers.get("Retry-After", str(attempt + 1))
                        if len(raw) > 2 or not raw.isdigit() or int(raw) > 5 or attempt == 2:
                            raise ValueError("PROVIDER_RETRY_LATER")
                        time.sleep(int(raw))
                        continue
                    if response.status_code != 200:
                        raise ValueError("PROVIDER_HTTP_" + str(response.status_code))
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 3_000_000:
                            raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
                        chunks.append(chunk)
                data = json.loads(b"".join(chunks))
                if data.get("error", {}).get("code") == "maxlag":
                    if attempt == 2:
                        raise ValueError("PROVIDER_RETRY_LATER")
                    time.sleep(2)
                    continue
                entities = data.get("entities")
                if not isinstance(entities, dict) or any(
                    not isinstance(v, dict) for v in entities.values()
                ):
                    raise ValueError("INVALID_PROVIDER_RESPONSE")
                return entities
            except httpx.TransportError:
                if attempt == 2:
                    raise ValueError("PROVIDER_UNAVAILABLE") from None
        raise ValueError("PROVIDER_UNAVAILABLE")
