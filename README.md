# SumikaProject

星见澄夏 QQ Agent 的工程化仓库。项目目标是在自有 ECS 上运行一个低频、可审计、带记忆和预算控制的 QQ 角色 Agent。

## Scope

- OneBot 11 反向 WebSocket 接入，当前生产内核为 NapCatQQ。
- OpenRouter `openrouter/free` 模型调用，默认启用 `xhigh` reasoning，并从 QQ 输出中排除 reasoning 内容。
- 高级记忆网关、SQLite 降级记忆、世界记忆、个人记忆、好感度、主动发言、搜索、OCR/ASR 预留接口。
- 本地隧道访问管理 GUI，不公开暴露管理面。
- 出站 QQ 消息全局串行化，并在每条消息前随机等待 `1-5s`。
- 阿里云流量预算和降级控制。

## Repository Layout

```text
assets/                  Character assets and prompt provenance
config/                  Runtime configuration
deploy/                  Compose, systemd templates, deployment docs
docs/                    Plans and architecture notes
patches/                 Auditable upstream patches
roles/                   Character-specific role assets
scripts/                 Local maintenance, generation, and QQ operation scripts
src/sumika_agent/        FastAPI app and core agent modules
tests/                   Unit tests
third_party.lock.yml     Pinned upstream repositories and patch metadata
```

## Secrets

Do not commit secrets. Runtime secrets belong in local or server-only files:

```text
deploy/.env
secrets/openrouter_key
secrets/admin_token
data/
artifacts/
```

Desktop API key files such as `dskeynew.txt` and `gptimg2.txt` are read only by local generation scripts and are never copied into the repository.

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m uvicorn sumika_agent.app:app --reload --host 127.0.0.1 --port 8787
```

Run checks:

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m pytest -q
```

## Deployment

See [deploy/README.md](deploy/README.md).

Routine remote operations should use the fixed-action wrapper instead of arbitrary encoded shell commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -HostName <ecs-host> -Action health
```

## Safety Notes

- Do not use the project for spam, mass adding, credential collection, or privacy harvesting.
- Friend/group approval remains owner-controlled through the management GUI.
- Avoid rapid message bursts. Keep the global outbound pacing enabled.
- Directly asked identity questions should be answered without pretending to be a real human.
- See [deploy/security-allowlist.md](deploy/security-allowlist.md) for Alibaba Cloud Security Center false-positive handling.
- See [deploy/qq-kernel-evaluation.md](deploy/qq-kernel-evaluation.md) for QQ kernel tradeoffs.
