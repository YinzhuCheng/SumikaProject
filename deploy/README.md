# Deployment

This directory contains reusable deployment templates. Real hostnames, QQ account IDs, tokens, and local paths must stay outside git.

## Files

- `compose.yml`: Docker Compose stack for `sumika-agent`, NapCat, and optional AstrBot.
- Advanced-memory sidecars are behind the `advanced-memory` Compose profile and require `scripts/manage_upstreams.py clone` plus `apply-patches` before building.
- `.env.example`: application environment template.
- `napcat.env.example`: NapCat systemd environment template.
- `sumika-agent.service`: Docker Compose systemd template.
- `sumika-agent-direct.service`: direct Python systemd template.
- `napcat-shell.service`: NapCat QQ GUI systemd template using Xvfb.
- `napcat-sumika-extension/`: NapCat plugin that injects Sumika-specific OneBot actions.
- `security-allowlist.md`: Alibaba Cloud Security Center false-positive handling rules.
- `qq-kernel-evaluation.md`: QQ kernel comparison and migration notes.

## Environment

Copy templates on the target host and edit values there:

```bash
cp deploy/.env.example deploy/.env
sudo mkdir -p /etc/sumika
sudo cp deploy/napcat.env.example /etc/sumika/napcat.env
```

Required secrets:

```text
secrets/openrouter_key
secrets/admin_token
```

The files above are ignored by git.

Optional advanced-memory environment:

```env
MEMORY_LLM_BASE_URL=https://api.deepseek.com
MEMORY_LLM_MODEL=deepseek-v4-pro
MEMORY_LLM_API_KEY=<server-side-memory-llm-key>
ADVANCED_MEMORY_ENABLED=true
MEMMACHINE_URL=http://memmachine:8080
GRAPHITI_URL=http://graphiti:8000
COGNEE_URL=http://cognee:8000
NEO4J_AUTH=neo4j/<strong-local-password>
SUMIKA_POSTGRES_PASSWORD=<strong-local-password>
```

## Local Sync

From the repository root:

```powershell
$env:SUMIKA_ECS_HOST = "<ecs-host>"
$env:SUMIKA_ECS_USER = "ecs-user"
$env:SUMIKA_REMOTE_DIR = "/opt/sumika"
$env:OPENROUTER_KEY_FILE = "<local-openrouter-key-file>"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy-ecs.ps1
```

`OPENROUTER_KEY_FILE` is optional. If omitted, the script syncs code only.

## Direct Python Service

On the target host:

```bash
cd /opt/sumika
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
sudo cp deploy/sumika-agent-direct.service /etc/systemd/system/sumika-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now sumika-agent
```

## Docker Compose Service

```bash
cd /opt/sumika
sudo cp deploy/sumika-agent.service /etc/systemd/system/sumika-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now sumika-agent
```

To prepare optional advanced-memory sidecars:

```bash
.venv/bin/python scripts/manage_upstreams.py clone
.venv/bin/python scripts/manage_upstreams.py apply-patches
docker compose -f deploy/compose.yml --profile advanced-memory build
docker compose -f deploy/compose.yml --profile advanced-memory up -d
```

The main agent keeps SQLite fallback enabled, so QQ text replies continue even if these sidecars are down.

## NapCat Shell Service

Install NapCat/QQ outside this repository, then edit `/etc/sumika/napcat.env`:

```bash
NAPCAT_QQ_BIN=/opt/napcat/opt/QQ/qq
SUMIKA_QQ_UIN=<qq-uin>
```

Install the service:

```bash
sudo cp deploy/napcat-shell.service /etc/systemd/system/napcat-shell.service
sudo systemctl daemon-reload
sudo systemctl enable --now napcat-shell
```

NapCat WebUI and Sumika Admin GUI must stay bound to localhost. Access them through SSH tunnels:

```bash
ssh -L 8787:127.0.0.1:8787 <user>@<ecs-host>
ssh -L 6099:127.0.0.1:6099 <user>@<ecs-host>
```

Configure NapCat reverse WebSocket:

```text
ws://127.0.0.1:8787/onebot/ws
```

## Message Pacing

The default runtime asks OpenRouter for `xhigh` reasoning and excludes reasoning from outbound messages:

```env
OPENROUTER_REASONING_EFFORT=xhigh
OPENROUTER_REASONING_EXCLUDE=true
```

All outgoing OneBot message actions are serialized and delayed by a random sample from:

```env
OUTBOUND_MESSAGE_DELAY_MIN_SECONDS=1
OUTBOUND_MESSAGE_DELAY_MAX_SECONDS=5
```

Keep this enabled for normal operation.

## Sumika NapCat Extension

Install the plugin into NapCat's plugin directory and enable it in NapCat's `plugins.json`:

```bash
mkdir -p <napcat-plugin-dir>/napcat-sumika-extension
cp deploy/napcat-sumika-extension/* <napcat-plugin-dir>/napcat-sumika-extension/
```

Example `plugins.json` fragment:

```json
{
  "napcat-plugin-builtin": true,
  "napcat-sumika-extension": true
}
```

Custom OneBot actions injected by the plugin:

- `sumika_add_friend`
- `sumika_debug_buddy_service`
- `sumika_call_buddy_service`
- `sumika_debug_profile_service`
- `sumika_call_profile_service`
- `sumika_set_avatar_verbose`

## Maintenance Commands

Use fixed-action scripts from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -HostName <ecs-host> -Action health
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -HostName <ecs-host> -Action agent-status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -HostName <ecs-host> -Action napcat-status
```

Do not use hidden execution forms such as `base64 -d | bash`, `curl ... | bash`, or `wget ... | sh`.
