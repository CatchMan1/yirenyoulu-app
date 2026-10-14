"""Generate typed response DTOs from the reviewed contract (no runtime doc reads)."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/技术开发/02接口与权限/openapi.json"
OUTPUT = ROOT / "backend/app/responses.py"


def generate():
    contract = json.loads(CONTRACT.read_text())
    schemas = contract["components"]["schemas"]
    lines = [
        '"""Generated response DTOs; regenerate with scripts/generate_response_models.py."""',
        "from typing import Annotated, Literal",
        "from uuid import UUID",
        "",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "class Output(BaseModel):",
        '    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)',
        "",
    ]
    emitted = set()

    def annotation(schema):
        if "$ref" in schema:
            name = schema["$ref"].split("/")[-1]
            emit(name)
            return name
        if "anyOf" in schema:
            return " | ".join(annotation(v) for v in schema["anyOf"])
        if "enum" in schema:
            return "Literal[" + ", ".join(repr(v) for v in schema["enum"]) + "]"
        kind = schema["type"]
        if kind == "array":
            value = "list[" + annotation(schema["items"]) + "]"
        elif kind == "object":
            raise ValueError("Inline object response must have a named schema")
        elif kind == "string" and schema.get("format") == "uuid":
            value = "UUID"
        else:
            value = {
                "string": "str",
                "integer": "int",
                "number": "float",
                "boolean": "bool",
                "null": "None",
            }[kind]
        constraints = {}
        keys = {
            "minimum": "ge",
            "maximum": "le",
            "exclusiveMinimum": "gt",
            "exclusiveMaximum": "lt",
            "minLength": "min_length",
            "maxLength": "max_length",
            "minItems": "min_length",
            "maxItems": "max_length",
            "pattern": "pattern",
        }
        for key, target in keys.items():
            if key in schema:
                constraints[target] = schema[key]
        extra = {
            key: schema[key]
            for key in ("format", "uniqueItems")
            if key in schema and schema.get("format") != "uuid"
        }
        args = [key + "=" + repr(v) for key, v in constraints.items()]
        if extra:
            args.append("json_schema_extra=" + repr(extra))
        return (
            "Annotated[" + value + ", Field(" + ", ".join(args) + ")]"
            if args
            else value
        )

    def emit(name):
        if name in emitted:
            return
        schema = schemas[name]
        required = set(schema.get("required", []))
        fields = []
        for key, value in schema["properties"].items():
            typed = annotation(value)
            default = "" if key in required else " = " + repr(value.get("default"))
            fields.append("    " + key + ": " + typed + default)
        if "allOf" in schema:
            fields.insert(
                0,
                '    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True, json_schema_extra='
                + repr({"allOf": schema["allOf"]})
                + ")",
            )
        lines.extend(["", "class " + name + "(Output):", *fields, ""])
        emitted.add(name)

    operations = {}
    for methods in contract["paths"].values():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            for code, response in operation["responses"].items():
                if code.startswith("2") and "content" in response:
                    name = response["content"]["application/json"]["schema"][
                        "$ref"
                    ].split("/")[-1]
                    emit(name)
                    operations[operation["operationId"]] = name
    emit("ErrorResponse")
    codes = {
        op["operationId"]: [int(c) for c in op["responses"] if not c.startswith("2")]
        for methods in contract["paths"].values()
        for method, op in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    lines.extend(
        [
            "",
            "RESPONSE_MODELS = {",
            *["    " + repr(op) + ": " + name + "," for op, name in operations.items()],
            "}",
            "",
        ]
    )
    lines.extend(["", "ERROR_CODES = " + repr(codes), ""])
    raw = "\n".join(lines)
    formatted = subprocess.run(  # noqa: S603 -- fixed project tooling, no shell
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--config",
            str(ROOT / "backend/pyproject.toml"),
            "--stdin-filename",
            "responses.py",
            "-",
        ],
        input=raw,
        text=True,
        capture_output=True,
        check=True,
    )
    return formatted.stdout


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = generate()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != content:
            raise SystemExit("Response DTOs differ from contract: regenerate them")
    else:
        OUTPUT.write_text(content)
