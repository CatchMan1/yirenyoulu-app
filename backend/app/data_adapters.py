"""Bounded source mappings; no inference of prices, ratings or operating status."""

import re
from collections import deque
from datetime import datetime, timezone

from .http import utcnow

ATTRACTION_TYPES = {
    "Q33506",
    "Q16560",
    "Q174782",
    "Q47692",
    "Q22746",
    "Q23397",
    "Q6838244",
    "Q570116",
}
HOTEL_TYPES = {"Q27686"}
RESTAURANT_TYPES = {"Q11707"}


def qid(value):
    if not isinstance(value, str) or not re.fullmatch(r"Q[1-9][0-9]{0,12}", value):
        raise ValueError("INVALID_ENTITY_ID")
    return value


def _date(value):
    try:
        return datetime.fromisoformat(value.lstrip("+").replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def claims(entity, property_id):
    rows = entity.get("claims", {}).get(property_id, [])
    valid = []
    for row in rows:
        if row.get("rank") == "deprecated":
            continue
        qualifiers = row.get("qualifiers", {})
        ended = [
            _date(v.get("datavalue", {}).get("value", {}).get("time"))
            for v in qualifiers.get("P582", [])
        ]
        future = [
            _date(v.get("datavalue", {}).get("value", {}).get("time"))
            for v in qualifiers.get("P580", [])
        ]
        # Unparseable/partial temporal qualifiers cannot silently become current evidence.
        if any(t is None for t in ended + future):
            continue
        if any(t and t <= utcnow() for t in ended) or any(t and t > utcnow() for t in future):
            continue
        snak = row.get("mainsnak", {})
        if snak.get("snaktype") == "value" and "datavalue" in snak:
            valid.append(row)
    preferred = [r for r in valid if r.get("rank") == "preferred"]
    return [r["mainsnak"]["datavalue"]["value"] for r in (preferred or valid)]


def entity_label(entity):
    labels = entity.get("labels", {})
    value = next(
        (
            labels[lang].get("value")
            for lang in ["zh-hans", "zh", "en"]
            if labels.get(lang, {}).get("value")
        ),
        None,
    )
    if not value:
        raise ValueError("LABEL_MISSING")
    return value


def wikidata_record(entities, place_qid, city_qid, observed_at=None):
    qid(place_qid)
    qid(city_qid)
    place = entities.get(place_qid)
    city = entities.get(city_qid)
    if (
        not place
        or not city
        or not any(isinstance(v, dict) and v.get("id") == "Q148" for v in claims(city, "P17"))
    ):
        raise ValueError("CITY_EVIDENCE_MISSING")
    types = {v.get("id") for v in claims(place, "P31") if isinstance(v, dict)}
    kinds = []
    for kind, allowed in [
        ("hotel", HOTEL_TYPES),
        ("restaurant", RESTAURANT_TYPES),
        ("attraction", ATTRACTION_TYPES),
    ]:
        if types & allowed:
            kinds.append(kind)
    if len(kinds) != 1:
        raise ValueError("TYPE_NOT_SUPPORTED")
    queue = deque(
        (v.get("id"), [v.get("id")]) for v in claims(place, "P131") if isinstance(v, dict)
    )
    seen: set[str] = set()
    chain = None
    while queue and len(seen) < 32:
        current, path = queue.popleft()
        if not isinstance(current, str):
            continue
        if current == city_qid:
            chain = path
            break
        if current in seen or len(path) > 8:
            continue
        seen.add(current)
        for value in claims(entities.get(current, {}), "P131"):
            if isinstance(value, dict) and value.get("id"):
                queue.append((value["id"], path + [value["id"]]))
    if chain is None:
        raise ValueError("CITY_EVIDENCE_MISSING")
    coordinates = None
    points = claims(place, "P625")
    # Multiple competing best coordinates need review, never silently choose one.
    if len(points) == 1 and points[0].get("globe") == "http://www.wikidata.org/entity/Q2":
        point = points[0]
        coordinates = {
            "longitude": point["longitude"],
            "latitude": point["latitude"],
            "crs": "WGS84",
        }
    dissolved = claims(place, "P576")
    return {
        "external_id": place_qid,
        "kind": kinds[0],
        "name": entity_label(place),
        "source_url": "https://www.wikidata.org/wiki/" + place_qid,
        "observed_at": (observed_at or utcnow()).astimezone(timezone.utc).isoformat(),
        "coordinates": coordinates,
        "status": "inactive" if dissolved else "active",
        "evidence": {
            "type_ids": sorted(types),
            "city_chain": chain,
            "entity_revision": place.get("lastrevid"),
            "entity_modified": place.get("modified"),
            "coordinate_precision": points[0].get("precision") if len(points) == 1 else None,
        },
    }


def osm_record(element, city_name, observed_at=None):
    tags = element.get("tags", {})
    if tags.get("addr:city") != city_name:
        raise ValueError("CITY_EVIDENCE_MISSING")
    kind = None
    if tags.get("tourism") in {"hotel", "hostel", "guest_house", "motel"}:
        kind = "hotel"
    elif tags.get("amenity") in {"restaurant", "cafe", "fast_food", "food_court"}:
        kind = "restaurant"
    elif (
        tags.get("tourism") in {"attraction", "museum", "gallery", "viewpoint"}
        or tags.get("leisure") == "park"
    ):
        kind = "attraction"
    if kind is None:
        raise ValueError("TYPE_NOT_SUPPORTED")
    typ = element.get("type")
    number = element.get("id")
    if typ not in {"node", "way", "relation"} or type(number) is not int or number <= 0:
        raise ValueError("INVALID_EXTERNAL_ID")
    position = element if typ == "node" else element.get("center", {})
    coords = None
    if "lon" in position and "lat" in position:
        coords = {"longitude": position["lon"], "latitude": position["lat"], "crs": "WGS84"}
    return {
        "external_id": f"{typ}/{number}",
        "kind": kind,
        "name": tags.get("name"),
        "source_url": f"https://www.openstreetmap.org/{typ}/{number}",
        "observed_at": (observed_at or utcnow()).isoformat(),
        "coordinates": coords,
        "evidence": {
            "city_name": city_name,
            "osm_version": element.get("version"),
            "opening_hours_raw": tags.get("opening_hours"),
        },
    }
