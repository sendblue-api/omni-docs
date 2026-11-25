#!/usr/bin/env python3
"""Regenerate api-reference/openapi.yaml from Omni's contract.

The contract (contracts/native/openapi.yaml in sendblue-api/omni) describes the
whole target API and marks each operation with x-status. This script keeps what
a customer can call today:

- operations whose x-status is "live" (everything else is dropped);
- schema members that are not marked x-status: planned;
- only the schemas, parameters, headers and responses still referenced.

It also replaces the contract's internal preamble with a customer one, keeps
only the production server, and turns x-permission / x-auth into a line of each
operation's description.

Where the contract comes from, first match wins:
  --contract PATH          a file
  --omni-repo DIR          a checkout; reads <ref>:contracts/native/openapi.yaml
  (neither)                GitHub, through `gh api` (needs access to the repo)

Usage:
  python3 scripts/build_reference.py --omni-repo ../omni          # write
  python3 scripts/build_reference.py --omni-repo ../omni --check  # exit 1 if stale
"""
import argparse
import copy
import pathlib
import re
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "api-reference" / "openapi.yaml"
CONTRACT = "contracts/native/openapi.yaml"
REPO = "sendblue-api/omni"
METHODS = ("get", "post", "put", "patch", "delete")
CREDENTIALS = {
    "api_key": "an API key",
    "account_token": "the account token",
    "person": "a signed-in person",
    "admin": "a signed-in administrator",
}
DESCRIPTION = """\
The Sendblue Omni API: messages, numbers, calls, recordings, media, 10DLC
registration, billing and webhooks for US messaging and calling.

Every operation on this page is live. Requests and responses are JSON with
`snake_case` names, at the root of the host with no version prefix. See the
guides for [authentication](/authentication), [idempotency](/idempotency),
[errors](/errors), [pagination](/pagination) and [webhooks](/webhooks).
"""


# The contract explains unavailable members in its own vocabulary; say it plainly.
MARKER = re.compile(r"\b(is|are) marked `x-status: planned`\s+in `\w+`")
# GitHub Push Protection flags AC/SK + 32 hex chars as Twilio credentials in public repos.
PLACEHOLDER_SID = re.compile(r"\b(AC|SK)[0-9a-fA-F]{32}\b")


def sanitize_sids(node, seen=None):
    if seen is None:
        seen = {"AC": {}, "SK": {}}

    def _replace(match):
        prefix = match.group(1)
        raw = match.group(0)
        table = seen[prefix]
        if raw not in table:
            table[raw] = f"{prefix}{'x' * 30}{len(table) + 1:02d}"
        return table[raw]

    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                node[k] = PLACEHOLDER_SID.sub(_replace, v)
            else:
                sanitize_sids(v, seen)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                node[i] = PLACEHOLDER_SID.sub(_replace, v)
            else:
                sanitize_sids(v, seen)


def reword(node):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "description" and isinstance(v, str):
                node[k] = MARKER.sub(r"\1 not available yet", v)
            else:
                reword(v)
    elif isinstance(node, list):
        for v in node:
            reword(v)


SECURITY = {
    "person": "A person's session: `Authorization: Bearer <ID token>`, the ID token the Sendblue "
              "sign-in issues. The person acts in their company's root account with the role of their seat.",
    "bearer": "`Authorization: Bearer <credential id>.<secret>`: an API key ID (`SK…`) with the key's "
              "secret, or an account ID (`AC…`) with the account's token. An existing Sendblue API key "
              "is accepted in the same form.",
    "legacyKeyId": "The ID of an existing Sendblue API key (or of an `SK…` key or `AC…` account), sent "
                   "together with `sb-api-secret-key`.",
    "legacyKeySecret": "The credential's secret, sent together with `sb-api-key-id`.",
}


class Dumper(yaml.SafeDumper):
    pass


def _text(dumper, value):
    if "\n" in value:
        lines = [line.rstrip() for line in value.split("\n")]
        return dumper.represent_scalar("tag:yaml.org,2002:str", "\n".join(lines), style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


Dumper.add_representer(str, _text)


def load_contract(args):
    if args.contract:
        return pathlib.Path(args.contract).read_text(), "file"
    if args.omni_repo:
        git = ["git", "-C", args.omni_repo]
        text = subprocess.check_output(git + ["show", f"{args.ref}:{CONTRACT}"], text=True)
        sha = subprocess.check_output(git + ["rev-parse", args.ref], text=True).strip()
        return text, sha
    ref = args.ref.removeprefix("origin/")
    text = subprocess.check_output(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw",
         f"repos/{REPO}/contents/{CONTRACT}?ref={ref}"], text=True)
    sha = subprocess.check_output(
        ["gh", "api", f"repos/{REPO}/commits/{ref}", "--jq", ".sha"], text=True).strip()
    return text, sha


def strip_planned(node):
    """Remove members marked x-status: planned, and every x-status marker."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            gone = [k for k, v in props.items() if isinstance(v, dict) and v.get("x-status") == "planned"]
            for k in gone:
                del props[k]
            if gone and isinstance(node.get("required"), list):
                node["required"] = [r for r in node["required"] if r not in gone]
        node.pop("x-status", None)
        for v in node.values():
            strip_planned(v)
    elif isinstance(node, list):
        for v in node:
            strip_planned(v)


def refs(node, found):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/"):
                found.add(tuple(v.split("/")[2:4]))
            else:
                refs(v, found)
    elif isinstance(node, list):
        for v in node:
            refs(v, found)


def build(text):
    spec = yaml.safe_load(text)
    out = copy.deepcopy(spec)
    live = 0
    for path, item in list(out["paths"].items()):
        for method in METHODS:
            op = item.get(method)
            if op is None:
                continue
            if op.get("x-status") != "live":
                del item[method]
                continue
            live += 1
            notes = []
            if op.get("x-permission"):
                notes.append(f"Required permission: `{op.pop('x-permission')}`.")
            who = [CREDENTIALS[a] for a in op.pop("x-auth", []) if a in CREDENTIALS]
            if who:
                notes.append("Accepted credentials: " + ", ".join(who) + ".")
            if notes:
                op["description"] = ((op.get("description") or "").rstrip() + "\n\n" + " ".join(notes)).strip() + "\n"
        if not any(m in item for m in METHODS):
            del out["paths"][path]
    for item in (out.get("webhooks") or {}).values():
        for op in item.values():
            if isinstance(op, dict):
                op.pop("x-auth", None)
                op.pop("x-permission", None)
    strip_planned(out)
    reword(out)
    sanitize_sids(out)
    for name, scheme in out.get("components", {}).get("securitySchemes", {}).items():
        if name in SECURITY:
            scheme["description"] = SECURITY[name]

    # Keep only the components that the remaining operations reach.
    keep, frontier = set(), set()
    refs(out["paths"], frontier)
    refs(out.get("webhooks", {}), frontier)
    components = out.get("components", {})
    while frontier:
        ref = frontier.pop()
        if ref in keep:
            continue
        keep.add(ref)
        found = set()
        refs(components.get(ref[0], {}).get(ref[1], {}), found)
        frontier |= found - keep
    for section in ("schemas", "parameters", "headers", "responses"):
        if section in components:
            components[section] = {k: v for k, v in components[section].items() if (section, k) in keep}

    used_tags = {t for item in out["paths"].values() for m in METHODS if m in item for t in item[m].get("tags", [])}
    out["tags"] = [t for t in out.get("tags", []) if t["name"] in used_tags]
    out["servers"] = [s for s in out.get("servers", []) if s.get("description") == "Production"] or out.get("servers", [])[:1]
    out["info"]["title"] = "Sendblue Omni API"
    out["info"]["description"] = DESCRIPTION
    return out, live, sum(1 for i in spec["paths"].values() for m in METHODS if m in i)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--contract")
    p.add_argument("--omni-repo")
    p.add_argument("--ref", default="origin/main")
    p.add_argument("--check", action="store_true", help="do not write; exit 1 if the committed file is stale")
    args = p.parse_args()
    text, source = load_contract(args)
    out, live, total = build(text)
    header = ("# GENERATED by scripts/build_reference.py. Do not edit by hand.\n"
              f"# Source: {REPO} {CONTRACT} ({live} live operations of {total}).\n")
    rendered = header + yaml.dump(out, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100)
    if args.check:
        if not OUT.exists() or OUT.read_text() != rendered:
            print(f"stale: {OUT.relative_to(ROOT)} differs from the contract at {source}", file=sys.stderr)
            return 1
        print(f"up to date: {live} live operations (contract at {source})")
        return 0
    OUT.write_text(rendered)
    print(f"wrote {OUT.relative_to(ROOT)}: {live} live operations of {total} (contract at {source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
