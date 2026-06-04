# Security Center False Positive Handling

This project should not use encoded shell pipelines such as:

```bash
bash -c 'echo ... | base64 -d | bash'
```

That command shape is intentionally suspicious to host protection products because it hides script content until execution time. Use fixed files and explicit command paths instead.

## Preferred Operations

Use the local wrapper for routine ECS operations:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -Action health
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -Action send-assets -UserId <qq-user-id>
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -Action agent-status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sumika_remote.ps1 -Action napcat-status
```

For manual SSH work, prefer direct executable calls:

```bash
<project-root>/.venv/bin/python <project-root>/scripts/send_sumika_assets.py import-and-send <qq-user-id>
```

Avoid command encoding, download-and-execute one-liners, broad `bash -c` wrappers, and pipes into `bash`, `sh`, `python`, or `perl`.

## Alert Triage

For every Alibaba Cloud Security Center alert:

1. Open the alert details and check command line, process path, parent process, affected asset, first occurrence, and latest occurrence.
2. Confirm the command came from an expected SSH operation, systemd unit, or project script.
3. If the command uses encoded or hidden execution, change the operation pattern first instead of adding a whitelist.
4. If the same clear, fixed business command still raises alerts after the operation is cleaned up, add the narrowest available exception.

## Whitelist Scope

Use Alibaba Cloud's alert handling whitelist only for permanent, known false positives. Keep rules precise:

- Apply to the current ECS asset only, not all assets.
- Prefer exact command line or exact file MD5/hash when the file is stable.
- Prefer exact project paths such as `<project-root>/scripts/send_sumika_assets.py`.
- Do not whitelist `/bin/bash`, `/usr/bin/bash`, `/usr/sbin/sshd`, `/usr/bin/python`, or the whole `/workspace` directory.
- Do not use broad path rules such as `/data/`, `/tmp/`, `/home/`, or `/workspace/`.
- Do not whitelist command patterns containing `base64 -d | bash`, `curl ... | bash`, or `wget ... | sh`; remove those patterns from operations.

For one-off maintenance actions that are known and finished, use `ignore` or `manually handled` rather than a permanent whitelist.

## Known Benign Project Paths

These paths are expected for Sumika runtime and may be referenced in exact-match rules after review:

- `<project-root>/.venv/bin/python`
- `<project-root>/scripts/qq_ops.py`
- `<project-root>/scripts/send_sumika_assets.py`
- `<project-root>/src/sumika_agent/`
- `<project-root>/deploy/sumika-agent-direct.service`
- `<project-root>/deploy/napcat-shell.service`
- `<napcat-install-root>/`

Always verify the alert's hash and command line before adding any of them to an allowlist.
