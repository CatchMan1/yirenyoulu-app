"""Conservative adapter for reviewed Overture Places snapshots."""

import struct

from .ingestion import PlaceRecord

LICENSES = {"CDLA-Permissive-2.0", "CC0-1.0", "Apache-2.0"}


def adapt_record(
    row: dict, *, city_names: list[str], bounds: list[float], release: str, observed_at: str
) -> dict:
    sources = row.get("sources") or []
    if not sources or any(s.get("license") not in LICENSES for s in sources):
        raise ValueError("SOURCE_LICENSE_UNVERIFIED")
    if row.get("operating_status") not in {None, "open"}:
        raise ValueError("OPERATING_STATUS_UNVERIFIED")
    confidence = row.get("confidence")
    if not isinstance(confidence, (float, int)) or not 0.8 <= confidence <= 1:
        raise ValueError("LOW_CONFIDENCE")
    addresses = [
        a
        for a in row.get("addresses") or []
        if a.get("country") == "CN" and a.get("locality") in city_names
    ]
    if not addresses:
        raise ValueError("CITY_UNVERIFIED")
    taxonomy = row.get("taxonomy") or {}
    hierarchy = taxonomy.get("hierarchy") or []
    kinds = [k for k in ("hotel", "restaurant") if k in hierarchy]
    if len(kinds) != 1:
        raise ValueError("TYPE_UNSUPPORTED")
    box = row.get("bbox") or {}
    try:
        raw = bytes.fromhex(row["geometry_hex"])
        if len(raw) != 21 or raw[0] not in {0, 1}:
            raise ValueError("COORDINATES_UNVERIFIED")
        typ, x, y = struct.unpack(("<" if raw[0] else ">") + "Idd", raw[1:])
        if typ != 1 or not (bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]):
            raise ValueError("COORDINATES_UNVERIFIED")
        if not (box["xmin"] <= x <= box["xmax"] and box["ymin"] <= y <= box["ymax"]):
            raise ValueError("COORDINATES_UNVERIFIED")
    except (KeyError, TypeError, struct.error):
        raise ValueError("COORDINATES_UNVERIFIED") from None
    value = {
        "external_id": row.get("id"),
        "kind": kinds[0],
        "name": (row.get("names") or {}).get("primary"),
        "source_url": "https://docs.overturemaps.org/attribution/",
        "observed_at": observed_at,
        "coordinates": {"longitude": x, "latitude": y, "crs": "WGS84"},
        "evidence": {
            "release": release,
            "operating_status": row.get("operating_status"),
            "version": row.get("version"),
            "sources": sources,
            "locality": addresses[0]["locality"],
            "taxonomy": taxonomy,
            "confidence": confidence,
        },
    }
    if addresses[0].get("freeform"):
        value["address"] = addresses[0]["freeform"]
    return PlaceRecord.model_validate(value).model_dump(mode="json", exclude_unset=True)


def import_snapshot(
    sessions, source_id: str, city_id: str, records: list[dict], reference: str
) -> list[dict]:
    from .ingestion import apply_batch, approve_batch, create_batch, fingerprint, report

    results = []
    for kind in ("hotel", "restaurant"):
        selected = sorted((r for r in records if r["kind"] == kind), key=lambda r: r["external_id"])
        for offset in range(0, len(selected), 100):
            chunk = selected[offset : offset + 100]
            key = "overture-" + fingerprint({"city": city_id, "records": chunk})
            batch = create_batch(sessions, source_id, city_id, kind, chunk, key)
            approve_batch(sessions, batch, reference)
            apply_batch(sessions, batch)
            results.append(report(sessions, batch))
    return results


def separate_duplicates(records: list[dict], existing: list[dict]) -> tuple[list[dict], list[dict]]:
    """Conservatively hold nearby candidates; proximity does not prove identity."""
    from math import asin, cos, radians, sin, sqrt

    from .models import normalize_place_name

    accepted: list[dict] = []
    review: list[dict] = []
    for row in records:
        duplicate = False
        for other in existing + accepted:
            if row["kind"] != other["kind"]:
                continue
            if normalize_place_name(row["name"]) == normalize_place_name(other["name"]):
                duplicate = True
                break
            a, b = row.get("coordinates"), other.get("coordinates")
            if not a or not b or a["crs"] != "WGS84" or b["crs"] != "WGS84":
                continue
            lat1, lat2 = radians(a["latitude"]), radians(b["latitude"])
            dlat = lat2 - lat1
            dlon = radians(b["longitude"] - a["longitude"])
            distance = 12742000 * asin(
                min(1, sqrt(sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2))
            )
            if distance <= (200 if row["kind"] == "hotel" else 30):
                duplicate = True
                break
        (review if duplicate else accepted).append(row)
    return accepted, review
