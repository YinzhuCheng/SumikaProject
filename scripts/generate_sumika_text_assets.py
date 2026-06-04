from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE_DIR = ROOT / "roles" / "sumika"
OUTPUT_DIR = ROLE_DIR / "detailed"
ARTIFACT_DIR = ROOT / "artifacts" / "role_generation" / "deepseek"
MODEL = "deepseek-v4-pro"
BASE_URL = "https://api.deepseek.com"
SECTIONS = [
    "identity",
    "personality",
    "thinking_style",
    "speech_style",
    "relationships",
    "worldbook",
    "visual_bible",
    "image_plan",
]


@dataclass(frozen=True)
class SectionJob:
    name: str
    draft: dict[str, Any]


def read_key(path: Path | None = None) -> str:
    key_path = path or Path.home() / "Desktop" / "dskeynew.txt"
    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"empty DeepSeek key file: {key_path}")
    return key


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    safe = json.loads(json.dumps(record, ensure_ascii=False))
    headers = safe.get("headers")
    if isinstance(headers, dict):
        for key in list(headers):
            if key.lower() in {"authorization", "cookie"}:
                headers[key] = "[REDACTED]"
    return safe


def build_prompt(job: SectionJob) -> str:
    draft = yaml.safe_dump(job.draft, allow_unicode=True, sort_keys=False)
    return f"""
你正在为 QQ 角色 Agent “星见澄夏”扩写角色资产层。

要求：
- 保持人物锚点：黑青色及肩发、暖琥珀眼、星形发饰、浅色针织开衫、书卷气、天真宜人。
- 允许扩写身份、社会关系、职业/日常定位、世界书、人格、思维和发言风格。
- 不写平台规避、刷屏、隐私收集、冒充真实人类等内容。
- 直接被问到 AI/机器人时，可以坦白是企划中的 AI 角色，但普通聊天不主动出戏。
- 输出必须是严格 JSON，不要 Markdown。

请把下面 `{job.name}` 草稿扩写成详细资料。返回 JSON：
{{
  "schema_version": 1,
  "section": "{job.name}",
  "expanded": {{
    "...": "可被 YAML 保存的结构化内容"
  }}
}}

草稿 YAML：
{draft}
""".strip()


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


async def generate_section(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    key: str,
    job: SectionJob,
    dry_run: bool,
) -> dict[str, Any]:
    prompt = build_prompt(job)
    base_payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.55,
        "response_format": {"type": "json_object"},
    }
    if dry_run:
        return {"schema_version": 1, "section": job.name, "expanded": job.draft, "dry_run": True}

    attempts = [
        {"max_tokens": 8192, "reasoning_effort": "max", "thinking": {"type": "enabled"}},
        {"max_tokens": 16384, "reasoning_effort": "max"},
        {"max_tokens": 32768, "reasoning_effort": "max"},
    ]
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    last_error = ""
    for attempt_index, attempt in enumerate(attempts, start=1):
        payload = {**base_payload, **attempt}
        async with semaphore:
            started = time.time()
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            elapsed = time.time() - started
        record = {
            "section": job.name,
            "attempt": attempt_index,
            "elapsed_seconds": round(elapsed, 3),
            "request": {
                "url": f"{BASE_URL}/chat/completions",
                "headers": {"Authorization": "Bearer ..."},
                "json": payload,
            },
            "status_code": response.status_code,
            "response_text": response.text,
        }
        (ARTIFACT_DIR / f"{job.name}.attempt{attempt_index}.json").write_text(
            json.dumps(redact_record(record), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        response.raise_for_status()
        body = response.json()
        message = body["choices"][0]["message"]
        content = str(message.get("content") or "").strip()
        if not content:
            last_error = f"empty content; usage={body.get('usage')}"
            continue
        parsed = parse_json_object(content)
        parsed["usage"] = body.get("usage")
        parsed["model"] = body.get("model")
        parsed["attempt"] = attempt_index
        return parsed
    raise RuntimeError(f"DeepSeek returned no final content for {job.name}: {last_error}")


async def run(dry_run: bool, concurrency: int) -> None:
    jobs = [SectionJob(name, load_yaml(ROLE_DIR / f"{name}.yml")) for name in SECTIONS]
    key = "" if dry_run else read_key()
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=180) as client:
        results = await asyncio.gather(
            *(generate_section(client, semaphore, key, job, dry_run) for job in jobs)
        )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "model": MODEL,
        "thinking": {"type": "enabled", "reasoning_effort": "max"},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sections": [],
    }
    for result in results:
        section = result["section"]
        expanded = result.get("expanded") or {}
        out = {
            "schema_version": 1,
            "section": section,
            "source": "deepseek-v4-pro-max-thinking" if not dry_run else "dry-run",
            "expanded": expanded,
        }
        dump_yaml(OUTPUT_DIR / f"{section}.yml", out)
        manifest["sections"].append(
            {
                "section": section,
                "path": f"roles/sumika/detailed/{section}.yml",
                "usage": result.get("usage"),
                "model": result.get("model") or MODEL,
            }
        )
    dump_yaml(OUTPUT_DIR / "manifest.yml", manifest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(run(args.dry_run, max(1, min(args.concurrency, 30))))


if __name__ == "__main__":
    main()
