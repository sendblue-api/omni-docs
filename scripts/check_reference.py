#!/usr/bin/env python3
"""Checks that need no access to the Omni repository.

- api-reference/openapi.yaml carries no status markers (it is the filtered file);
- every page in docs.json exists, and no progress page is published.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
errors = []
spec = (ROOT / "api-reference" / "openapi.yaml").read_text()
for marker in ("x-status", "x-auth", "x-permission"):
    if marker in spec:
        errors.append(f"api-reference/openapi.yaml contains {marker}: regenerate it with scripts/build_reference.py")
# Prevent hex AC/SK placeholder SIDs from triggering GitHub Push Protection.
SID_PATTERN = re.compile(r"\b(?:AC|SK)[0-9a-fA-F]{32}\b")
for path in [ROOT / "api-reference" / "openapi.yaml", *sorted(ROOT.rglob("*.mdx"))]:
    if SID_PATTERN.search(path.read_text()):
        errors.append(f"{path.relative_to(ROOT)} contains a 32-hex AC/SK placeholder SID; use non-hex x placeholders")


def pages(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from pages(item)
    elif isinstance(node, dict):
        for key in ("tabs", "groups", "pages"):
            yield from pages(node.get(key, []))


for page in pages(json.loads((ROOT / "docs.json").read_text())["navigation"]):
    if not (ROOT / f"{page}.mdx").exists():
        errors.append(f"docs.json names a page with no file: {page}")
for internal in ("progress.mdx", "in-flight.mdx"):
    if (ROOT / internal).exists():
        errors.append(f"{internal} is an internal page and must not be in this repository")
for line in errors:
    print(line, file=sys.stderr)
sys.exit(1 if errors else 0)
