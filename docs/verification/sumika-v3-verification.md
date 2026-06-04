# Sumika v3 Verification Report

Generated: 2026-06-04

## Completed Evidence

- Branch: `codex/sumika-v3-memory-assets`
- Pushed commits:
  - `d1b5e46 Add Sumika advanced memory architecture foundation`
  - `355a3e6 Generate Sumika role assets and image pipeline`
  - `e85860b Add advanced memory sidecar adapters`
- Detailed execution plan is stored at `docs/plans/sumika-v3-advanced-memory-assets.md`.
- Upstream repositories were cloned locally under `vendor/upstream/` and locked in `third_party.lock.yml`.
- Upstream Sumika integration patches are stored under `patches/upstream/*/sumika-integration.patch`.
- Patch verification passed with:
  - `.venv\Scripts\python.exe scripts\manage_upstreams.py verify-patches`
- UTF-8 mojibake scan across repository source/config/docs/assets had no matches.
- Secret/absolute-path scan across repository tracked paths had no matches.
- Unit tests passed:
  - `.venv\Scripts\python.exe -m pytest -q`
  - Result: `9 passed`
- Ruff passed:
  - `.venv\Scripts\python.exe -m ruff check .`
  - Result: `All checks passed`

## DeepSeek Text Assets

- Script: `scripts/generate_sumika_text_assets.py`
- Model: `deepseek-v4-pro`
- Thinking: `reasoning_effort=max`
- Output directory: `roles/sumika/detailed/`
- Generated detailed sections: 8
- Manifest: `roles/sumika/detailed/manifest.yml`
- Raw API records are stored under ignored `artifacts/role_generation/deepseek/` with authorization redacted.

## Yunwu Image Assets

- Script: `scripts/generate_sumika_images.py`
- Model: `gpt-image-2`
- Selected manifest: `assets/generated/sumika_v3/manifest.yml`
- Candidate attempts required: 219
- Candidate successes in manifest: 219
- Selected final assets: 73
- Selected stages:
  - line_art: 10
  - costume_props: 15
  - standees: 20
  - avatars: 3
  - stickers: 10
  - cg: 15
- Non-CG selected assets passed alpha-channel validation.
- Candidate archive is stored under ignored `assets/generated/candidates/sumika_v3/`.
- Raw Yunwu records are stored under ignored `artifacts/image_generation/yunwu/` with authorization redacted.

## Memory Architecture

- Local fallback gateway: `src/sumika_agent/memory.py`
- Advanced sidecar gateway: `src/sumika_agent/memory_backends/sidecar.py`
- Prompt blocks: `src/sumika_agent/prompting/blocks.py`
- Privacy filter: `src/sumika_agent/privacy.py`
- Role asset loader: `src/sumika_agent/role_assets.py`
- Runtime now loads DeepSeek detailed role assets when present.
- Advanced sidecars are optional and disabled by default; SQLite fallback remains active.

## Deployment Verification Gap

Local Docker verification could not run because Docker CLI is not installed on this workstation:

```text
docker: The term 'docker' is not recognized as the name of a cmdlet...
```

ECS SSH read-only probes also failed for both likely users:

```text
root@123.56.65.173: Permission denied (publickey,password).
ubuntu@123.56.65.173: Permission denied (publickey,password).
```

Because of that, Docker Compose startup/restart on ECS remains unverified. The code and compose files are present, but runtime validation needs working SSH credentials or an interactive console session.
