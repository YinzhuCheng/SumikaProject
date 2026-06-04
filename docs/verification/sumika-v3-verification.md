# Sumika v3 Verification Report

Generated: 2026-06-04

## Completed Evidence

- Branch: `codex/sumika-v3-memory-assets`
- Current branch includes the advanced memory foundation, generated role/image assets,
  sidecar adapters, low-bandwidth sidecar build patches, verification report, and ECS
  deployment fixes.
- Detailed execution plan is stored at `docs/plans/sumika-v3-advanced-memory-assets.md`.
- Upstream repositories were cloned locally under `vendor/upstream/` and locked in `third_party.lock.yml`.
- Upstream Sumika integration patches are stored under `patches/upstream/*/sumika-integration.patch`.
- The MemMachine, Graphiti, and Cognee patches include ECS-friendly Dockerfiles and Sumika
  integration files. Cognee defaults to `https://mirrors.cloud.tencent.com/pypi/simple`
  after Aliyun PyPI was found stale for `litellm>=1.83.7`.
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

## ECS Deployment Verification

- SSH works with `ecs-user@123.56.65.173`.
- Docker is installed on ECS:
  - Docker: `29.1.3`
  - Docker Compose: `2.40.3+ds1-0ubuntu1~22.04.1`
- Docker Buildx was installed on ECS for Compose sidecar image builds.
- `/opt/sumika` was created as the clean deployment checkout for
  `codex/sumika-v3-memory-assets`.
- Server-only runtime files were created outside git:
  - `/opt/sumika/deploy/.env`
  - `/opt/sumika/secrets/openrouter_key`
  - `/opt/sumika/data/`
- Docker Hub direct access timed out from the Beijing ECS. Docker daemon was configured
  with registry mirror `https://docker.m.daocloud.io/`.
- `Dockerfile` now supports configurable mirror build args and defaults to deployment
  friendly mirrors:
  - `APT_DEBIAN_MIRROR=http://mirrors.aliyun.com/debian`
  - `APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security`
  - `PIP_INDEX_URL=http://mirrors.aliyun.com/pypi/simple/`
- Compose config validation passed:
  - `docker compose --env-file deploy/.env -f deploy/compose.yml config --quiet`
  - `docker compose --env-file deploy/.env -f deploy/compose.yml --profile advanced-memory config --quiet`
- `sumika-agent` image build passed on ECS:
  - `docker compose --env-file deploy/.env -f deploy/compose.yml build --progress=plain sumika-agent`
- Upstream source was cloned on ECS under `/opt/sumika/vendor/upstream`, Sumika patches
  were applied, and patch verification passed there with:
  - `python3 scripts/manage_upstreams.py verify-patches`
- Advanced-memory sidecar image builds passed on ECS:
  - `deploy-memmachine:latest`
  - `deploy-graphiti:latest`
  - `deploy-cognee:latest`
- Advanced-memory database images were pulled and started:
  - `sumika-postgres`
  - `sumika-neo4j`
- Advanced-memory sidecars were started with `ADVANCED_MEMORY_ENABLED=false` for the main
  agent, so SQLite fallback remains the active QQ runtime path until explicitly enabled.
- Sidecar startup smoke passed:
  - `sumika-memmachine` was `healthy`
  - `sumika-cognee` was `healthy`
  - `sumika-graphiti` was `Up`
  - Container-local port checks returned `1`, `2`, `3` for MemMachine, Cognee, Graphiti.
  - Graphiti emitted duplicate Neo4j index creation warnings on repeated initialization;
    these were non-fatal and Uvicorn reached `Application startup complete`.
- ECS resource snapshot after sidecar startup was acceptable for the 8 GiB instance:
  - `sumika-agent`: about 44 MiB
  - `sumika-memmachine`: about 191 MiB
  - `sumika-graphiti`: about 99 MiB
  - `sumika-cognee`: about 474 MiB
  - `sumika-neo4j`: about 854 MiB
  - `sumika-postgres`: about 41 MiB
- The existing direct Python `sumika-agent.service` was migrated to Docker Compose while
  preserving the OneBot access token and SQLite data. NapCat remains managed by
  `napcat-shell.service`; the Compose systemd template now starts only the `sumika-agent`
  container to avoid touching the logged-in QQ runtime.
- Startup verification passed:
  - `sudo systemctl enable --now sumika-agent`
  - `systemctl is-active sumika-agent` returned `active`
  - `curl -fsS http://127.0.0.1:8787/health` returned
    `{"ok":true,"name":"星见澄夏","onebot_clients":1}`
- Restart recovery verification passed:
  - `sudo systemctl restart sumika-agent`
  - `systemctl is-active sumika-agent` returned `active`
  - health check again returned `ok=true` and `onebot_clients=1`
- `napcat-shell.service` remained active during the migration.

## Remaining Notes

- Local Docker verification still cannot run on this Windows workstation because Docker CLI
  is not installed locally. ECS runtime validation has been completed instead.
- The advanced-memory sidecars are running for smoke validation, but the main QQ agent still
  has `ADVANCED_MEMORY_ENABLED=false` in the ECS runtime. Flip it only after providing a
  server-side memory LLM key and reviewing traffic/model budget settings.
