from __future__ import annotations

import argparse
import asyncio
import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ROLE_DIR = ROOT / "roles" / "sumika"
CANDIDATE_DIR = ROOT / "assets" / "generated" / "candidates" / "sumika_v3"
FINAL_DIR = ROOT / "assets" / "generated" / "sumika_v3"
ARTIFACT_DIR = ROOT / "artifacts" / "image_generation" / "yunwu"
BASE_URL = "https://yunwu.ai"


@dataclass(frozen=True)
class ImageJob:
    stage_id: str
    index: int
    transparent: bool
    prompt: str
    references: tuple[Path, ...]


def read_key(path: Path | None = None) -> str:
    key_path = path or Path.home() / "Desktop" / "gptimg2.txt"
    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"empty Yunwu key file: {key_path}")
    return key


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def rel(path: Path | str) -> str:
    return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")


def has_alpha(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            if image.mode in {"RGBA", "LA"}:
                return True
            return "transparency" in image.info
    except Exception:
        return False


def build_stage_prompt(stage_id: str, visual: dict[str, Any], transparent: bool, index: int) -> str:
    anchor = visual.get("visual_anchor") or {}
    negative = ", ".join(visual.get("negative_prompt") or [])
    transparent_hint = "transparent background, isolated PNG asset" if transparent else "full illustration background"
    stage_hints = {
        "line_art": "clean anime line art design sheet, no color fill, consistent face and hair silhouette",
        "costume_props": "costume and prop design sheet, cardigan, dress, notebook, star hairpin, object callouts without text",
        "standees": "full-body standing character illustration, polished anime style",
        "avatars": "QQ avatar bust crop, readable at small size, centered face",
        "stickers": "chibi sticker expression, expressive face, crisp outline",
        "cg": "cinematic anime CG scene, warm daily-life mood",
    }
    return f"""
Create asset #{index} for original anime character 星见澄夏.
Stage: {stage_id}. {stage_hints.get(stage_id, '')}.
Background requirement: {transparent_hint}.
Character anchors: hair={anchor.get('hair')}; eyes={anchor.get('eyes')}; accessory={anchor.get('accessory')}; outfit={anchor.get('outfit')}; mood={anchor.get('mood')}.
Consistency: same character identity, same hair color, same eye color, same gentle bookish feeling.
No text, no watermark, no brand logo.
Negative: {negative}.
""".strip()


def initial_references(visual: dict[str, Any]) -> tuple[Path, ...]:
    refs = []
    for item in visual.get("reference_assets") or []:
        path = ROOT / item
        if path.exists():
            refs.append(path)
    return tuple(refs[:8])


async def decode_image_item(client: httpx.AsyncClient, item: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if item.get("b64_json"):
        output.write_bytes(base64.b64decode(item["b64_json"]))
        return
    url = item.get("url")
    if not url:
        raise RuntimeError(f"image response item has no b64_json or url: {item}")
    response = await client.get(str(url), follow_redirects=True)
    response.raise_for_status()
    output.write_bytes(response.content)


async def request_image(
    client: httpx.AsyncClient,
    key: str,
    job: ImageJob,
    output: Path,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return {"status": "dry_run", "path": rel(output), "alpha": False}
    headers = {"Authorization": f"Bearer {key}"}
    data = {
        "model": "gpt-image-2",
        "prompt": job.prompt,
        "n": "1",
        "size": "1024x1024",
        "quality": "medium",
    }
    if job.transparent:
        data["background"] = "transparent"

    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for ref in job.references:
        files.append(("image", (ref.name, ref.read_bytes(), "image/png")))

    endpoint = "/v1/images/edits" if files else "/v1/images/generations"
    response = await client.post(f"{BASE_URL}{endpoint}", headers=headers, data=data, files=files or None)
    record = {
        "stage": job.stage_id,
        "index": job.index,
        "endpoint": endpoint,
        "status_code": response.status_code,
        "request": {"headers": {"Authorization": "[REDACTED]"}, "data": data, "references": [rel(p) for p in job.references]},
        "response_text": response.text[:4000],
    }
    ARTIFACT_DIR.joinpath(job.stage_id).mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.joinpath(job.stage_id, f"{job.index:03d}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    response.raise_for_status()
    payload = response.json()
    item = payload["data"][0]
    await decode_image_item(client, item, output)
    return {"status": "ok", "path": rel(output), "alpha": has_alpha(output), "response": {"created": payload.get("created")}}


async def generate_stage(
    client: httpx.AsyncClient,
    key: str,
    stage: dict[str, Any],
    visual: dict[str, Any],
    references: tuple[Path, ...],
    semaphore: asyncio.Semaphore,
    dry_run: bool,
) -> list[dict[str, Any]]:
    jobs = [
        ImageJob(
            stage_id=stage["id"],
            index=index,
            transparent=bool(stage.get("transparent")),
            prompt=build_stage_prompt(stage["id"], visual, bool(stage.get("transparent")), index),
            references=references,
        )
        for index in range(1, int(stage["candidate_count"]) + 1)
    ]

    async def one(job: ImageJob) -> dict[str, Any]:
        async with semaphore:
            output = CANDIDATE_DIR / job.stage_id / f"{job.stage_id}_{job.index:03d}.png"
            try:
                result = await request_image(client, key, job, output, dry_run)
                if (
                    result.get("status") == "ok"
                    and job.transparent
                    and not result.get("alpha")
                    and not dry_run
                ):
                    retry_job = ImageJob(
                        stage_id=job.stage_id,
                        index=job.index,
                        transparent=job.transparent,
                        prompt=job.prompt
                        + "\nCritical correction: export as a true transparent-background PNG with alpha channel.",
                        references=job.references,
                    )
                    retry_output = CANDIDATE_DIR / job.stage_id / f"{job.stage_id}_{job.index:03d}_retry.png"
                    retry_result = await request_image(client, key, retry_job, retry_output, dry_run)
                    retry_result["retried_for_alpha"] = True
                    result = retry_result
            except Exception as exc:
                result = {"status": "failed", "path": rel(output), "error": str(exc)}
            return {"stage": job.stage_id, "index": job.index, "transparent_required": job.transparent, **result}

    results = await asyncio.gather(*(one(job) for job in jobs))
    selected = []
    for result in results:
        if result["status"] != "ok":
            continue
        if result["transparent_required"] and not result.get("alpha"):
            continue
        selected.append(result)
        if len(selected) >= int(stage["final_count"]):
            break
    for rank, result in enumerate(selected, start=1):
        source = ROOT / result["path"]
        target = FINAL_DIR / stage["id"] / f"{stage['id']}_{rank:02d}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        result["selected_path"] = rel(target)
    return results


async def run(dry_run: bool, concurrency: int, smoke: bool) -> None:
    image_plan = load_yaml(ROLE_DIR / "image_plan.yml")
    visual = load_yaml(ROLE_DIR / "visual_bible.yml")
    references = initial_references(visual)
    key = "" if dry_run else read_key()
    stages = image_plan.get("stages") or []
    if smoke:
        stages = [{**stages[0], "candidate_count": 1, "final_count": 1}]
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 5)))
    manifest = {
        "schema_version": 1,
        "model": image_plan.get("model", "gpt-image-2"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dry_run": dry_run,
        "smoke": smoke,
        "stages": [],
    }
    async with httpx.AsyncClient(timeout=240) as client:
        for stage in stages:
            results = await generate_stage(client, key, stage, visual, references, semaphore, dry_run)
            manifest["stages"].append(
                {
                    "id": stage["id"],
                    "candidate_count": len(results),
                    "success_count": sum(1 for item in results if item["status"] == "ok"),
                    "selected_count": sum(1 for item in results if item.get("selected_path")),
                    "results": results,
                }
            )
            selected_refs = [ROOT / item["selected_path"] for item in results if item.get("selected_path")]
            references = tuple((list(selected_refs) + list(references))[:8])
    dump_yaml(FINAL_DIR / "manifest.yml", manifest)


async def repair_failed(concurrency: int) -> None:
    manifest_path = FINAL_DIR / "manifest.yml"
    if not manifest_path.exists():
        raise RuntimeError(f"missing image manifest: {manifest_path}")
    manifest = load_yaml(manifest_path)
    image_plan = load_yaml(ROLE_DIR / "image_plan.yml")
    visual = load_yaml(ROLE_DIR / "visual_bible.yml")
    stages_by_id = {stage["id"]: stage for stage in image_plan.get("stages", [])}
    key = read_key()
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 5)))

    def save() -> None:
        for stage_manifest in manifest.get("stages", []):
            results = stage_manifest.get("results", [])
            stage_manifest["success_count"] = sum(1 for item in results if item.get("status") == "ok")
            stage_manifest["selected_count"] = sum(1 for item in results if item.get("selected_path"))
        dump_yaml(manifest_path, manifest)

    async with httpx.AsyncClient(timeout=httpx.Timeout(420.0, connect=30.0)) as client:
        references = initial_references(visual)
        for stage_manifest in manifest.get("stages", []):
            stage_id = stage_manifest["id"]
            stage = stages_by_id[stage_id]
            for result in [item for item in stage_manifest.get("results", []) if item.get("status") != "ok"]:
                async with semaphore:
                    index = int(result["index"])
                    job = ImageJob(
                        stage_id=stage_id,
                        index=index,
                        transparent=bool(stage.get("transparent")),
                        prompt=build_stage_prompt(stage_id, visual, bool(stage.get("transparent")), index),
                        references=tuple(),
                    )
                    output = CANDIDATE_DIR / stage_id / f"{stage_id}_{index:03d}_repair_generation.png"
                    try:
                        repaired = await request_image(client, key, job, output, dry_run=False)
                        if job.transparent and repaired.get("status") == "ok" and not repaired.get("alpha"):
                            retry = ImageJob(
                                stage_id=stage_id,
                                index=index,
                                transparent=True,
                                prompt=job.prompt
                                + "\nCritical correction: export as a true transparent-background PNG with alpha channel.",
                                references=tuple(),
                            )
                            retry_output = (
                                CANDIDATE_DIR
                                / stage_id
                                / f"{stage_id}_{index:03d}_repair_generation_retry.png"
                            )
                            repaired = await request_image(client, key, retry, retry_output, dry_run=False)
                            repaired["retried_for_alpha"] = True
                        result.clear()
                        result.update(
                            {
                                "stage": stage_id,
                                "index": index,
                                "transparent_required": bool(stage.get("transparent")),
                                **repaired,
                                "repaired": True,
                                "repair_endpoint": "generations_no_reference",
                            }
                        )
                    except Exception as exc:
                        result["error"] = str(exc)
                    save()
                    await asyncio.sleep(8)
            selected_refs = [ROOT / item["selected_path"] for item in stage_manifest.get("results", []) if item.get("selected_path")]
            references = tuple((selected_refs + list(references))[:8])
    save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--repair-failed", action="store_true")
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    if args.repair_failed:
        asyncio.run(repair_failed(args.concurrency))
    else:
        asyncio.run(run(args.dry_run, args.concurrency, args.smoke))


if __name__ == "__main__":
    main()
