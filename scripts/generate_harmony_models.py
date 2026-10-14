"""Generate wire interfaces only; this does not compile or test ArkTS."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend/harmony/entry/src/main/ets/models/ApiModels.ets"


def wire_type(schema):
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "anyOf" in schema:
        return " | ".join(wire_type(value) for value in schema["anyOf"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if schema["type"] == "array":
        return wire_type(schema["items"]) + "[]"
    return {
        "string": "string",
        "integer": "number",
        "number": "number",
        "boolean": "boolean",
        "null": "null",
    }[schema["type"]]


def generate():
    doc = json.loads((ROOT / "docs/技术开发/02接口与权限/openapi.json").read_text())
    lines = ["/** V1 wire DTOs. Source: the reviewed OpenAPI contract. */"]
    for name, schema in doc["components"]["schemas"].items():
        lines.append("export interface " + name + " {")
        for key, value in schema["properties"].items():
            optional = "" if key in schema.get("required", []) else "?"
            lines.append("  " + key + optional + ": " + wire_type(value) + ";")
        lines.append("}\n")
    lines += [
        "export interface Envelope<T> {",
        "  data: T | null;",
        "  meta: PageMeta | CursorMeta | null;",
        "  request_id: string;",
        "}",
        "export interface RouteId { id: string; }",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = generate()
    if args.check:
        if OUTPUT.read_text() != content:
            raise SystemExit("Harmony wire interfaces differ from contract")
    else:
        OUTPUT.write_text(content)
