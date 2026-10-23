"""Fixed official Wikidata candidate query with budgeted, bounded keyset pages.

The query returns candidates only. Current raw claims must be revalidated by
``wikidata_record`` before staging an import; the query service can lag edits.
"""

import json
import time
from dataclasses import dataclass

import httpx

from .data_adapters import ATTRACTION_TYPES, HOTEL_TYPES, RESTAURANT_TYPES, qid
from .wikidata_source import USER_AGENT, reserve_request

ENDPOINT = "https://query.wikidata.org/sparql"
ENTITY_PREFIX = "http://www.wikidata.org/entity/"
KINDS = {
    "attraction": ATTRACTION_TYPES,
    "hotel": HOTEL_TYPES,
    "restaurant": RESTAURANT_TYPES,
}


@dataclass(frozen=True)
class DiscoveryPage:
    ids: list[str]
    next_cursor: str | None


def _query(city_qid, kind, cursor, page_size):
    types = " ".join("wd:" + value for value in sorted(KINDS[kind]))
    after = 'FILTER(STR(?item) > "' + ENTITY_PREFIX + cursor + '")' if cursor is not None else ""
    # Only validated QIDs and a fixed whitelist can reach this template. No free SPARQL.
    return f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?item WHERE {{
  VALUES ?type {{ {types} }}
  wd:{city_qid} wdt:P17 wd:Q148 .
  ?item wdt:P31 ?type ; wdt:P131+ wd:{city_qid} .
  {after}
}} ORDER BY STR(?item) LIMIT {page_size + 1}"""


def _parse(raw, cursor, page_size):
    try:
        data = json.loads(raw)
        if (
            not isinstance(data, dict)
            or data.get("head", {}).get("vars") != ["item"]
            or not isinstance(data.get("results"), dict)
        ):
            raise ValueError
        rows = data["results"].get("bindings")
        if not isinstance(rows, list) or len(rows) > page_size + 1:
            raise ValueError
        ids = []
        previous = cursor
        for row in rows:
            value = row["item"]
            uri = value["value"]
            if (
                value["type"] != "uri"
                or not isinstance(uri, str)
                or not uri.startswith(ENTITY_PREFIX)
            ):
                raise ValueError
            item = qid(uri[len(ENTITY_PREFIX) :])
            if previous is not None and item <= previous:
                raise ValueError
            ids.append(item)
            previous = item
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        raise ValueError("INVALID_DISCOVERY_PAGE") from None
    delivered = ids[:page_size]
    return DiscoveryPage(delivered, delivered[-1] if len(ids) > page_size else None)


def discover_page(
    sessions, source_id, city_qid, kind, cursor=None, page_size=20, transport=None
) -> DiscoveryPage:
    """Discover one lexical-QID page; every attempt consumes a committed permit request.

    The page is not an exhaustive snapshot: edits to Wikidata can alter subsequent
    pages. Resume cursors are exclusive and ordering is lexical, not numeric.
    """
    city_qid = qid(city_qid)
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("INVALID_PLACE_KIND")
    if cursor is not None:
        cursor = qid(cursor)
    if type(page_size) is not int or not 1 <= page_size <= 20:
        raise ValueError("INVALID_PAGE_SIZE")
    query = _query(city_qid, kind, cursor, page_size)
    return _fetch_page(sessions, source_id, query, cursor, page_size, transport)


def discover_cities(
    sessions, source_id, cursor=None, page_size=50, transport=None
) -> DiscoveryPage:
    """Candidate cities; hierarchy is resolved separately in bounded entity batches."""
    if cursor is not None:
        cursor = qid(cursor)
    if type(page_size) is not int or not 1 <= page_size <= 50:
        raise ValueError("INVALID_PAGE_SIZE")
    after = 'FILTER(STR(?item) > "' + ENTITY_PREFIX + cursor + '")' if cursor else ""
    query = f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?item WHERE {{
  ?item wdt:P17 wd:Q148 ; wdt:P31/wdt:P279* wd:Q515 .
  FILTER(?item NOT IN (wd:Q8646, wd:Q14773))
  FILTER NOT EXISTS {{ ?item wdt:P576 ?dissolved }}
  {after}
}} ORDER BY STR(?item) LIMIT {page_size + 1}"""
    return _fetch_page(sessions, source_id, query, cursor, page_size, transport)


def _fetch_page(sessions, source_id, query, cursor, page_size, transport):
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(25, connect=5),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"},
    ) as client:
        for attempt in range(3):
            # This transaction ends before any network operation or backoff.
            reserve_request(sessions, source_id)
            try:
                with client.stream(
                    "GET", ENDPOINT, params={"query": query, "format": "json"}
                ) as response:
                    if response.status_code in {429, 502, 503, 504}:
                        delay = response.headers.get("Retry-After", str(attempt + 1))
                        if len(delay) > 2 or not delay.isdigit() or int(delay) > 5 or attempt == 2:
                            raise ValueError("PROVIDER_RETRY_LATER")
                        time.sleep(int(delay))
                        continue
                    if response.status_code != 200:
                        raise ValueError("PROVIDER_HTTP_" + str(response.status_code))
                    parts = []
                    size = 0
                    for part in response.iter_bytes():
                        size += len(part)
                        if size > 100_000:
                            raise ValueError("PROVIDER_RESPONSE_TOO_LARGE")
                        parts.append(part)
                return _parse(b"".join(parts), cursor, page_size)
            except httpx.HTTPError:
                if attempt == 2:
                    raise ValueError("PROVIDER_UNAVAILABLE") from None
                time.sleep(attempt + 1)
    raise ValueError("PROVIDER_UNAVAILABLE")
