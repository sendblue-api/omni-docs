# Sendblue Omni API docs

Source of [omni-docs.sendblue.com](https://omni-docs.sendblue.com), published by Mintlify from the `main` branch of this repository.

| Path | What |
| --- | --- |
| `docs.json` | Mintlify site settings, branding, and navigation |
| `*.mdx`, `quickstart/*.mdx` | Hand-written guides and quickstarts |
| `api-reference/openapi.yaml` | **Generated.** Live API reference — do not edit by hand |
| `scripts/build_reference.py` | Filters Omni's contract down to live operations |
| `scripts/check_reference.py` | Verifies the generated spec and navigation |

## Syncing the API reference

`contracts/native/openapi.yaml` in `sendblue-api/omni` is the source of truth. `scripts/build_reference.py` keeps only operations marked `x-status: live`, strips planned fields and unreferenced components, and writes `api-reference/openapi.yaml`.

```bash
pip install -r requirements.txt
python3 scripts/build_reference.py --omni-repo ../omni          # from a local checkout
python3 scripts/build_reference.py                              # from GitHub via gh
python3 scripts/build_reference.py --omni-repo ../omni --check  # exit 1 if stale
```

The `Sync API reference` workflow (`.github/workflows/sync-reference.yml`) runs hourly and opens a pull request whenever the contract changes. To enable it on GitHub:

1. Add the repository secret `OMNI_READ_TOKEN` — a fine-grained PAT with read-only **Contents** access to `sendblue-api/omni`.
2. In **Settings → Actions → General**, enable **Allow GitHub Actions to create and approve pull requests**.

Reference wording comes from Omni's contract; edit `contracts/native/openapi.yaml` in Omni to change it.

## Preview and validate locally

The Mintlify CLI requires Node 20.17+ (Node 22 LTS recommended; Node 25 is not supported).

```bash
npx mint@latest dev            # preview at http://localhost:3000
npx mint@latest validate       # build & schema validation (same as CI)
npx mint@latest broken-links   # link check (same as CI)
python3 scripts/check_reference.py
```

## Writing rules

- Document only what is live. Leave out planned behaviour, or state plainly when something is not available yet.
- Base all behaviour on Omni's contract and docs. Never describe undocumented or unverified behaviour.
- Internal progress trackers do not belong in this repository.
