#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from qq_ops import DEFAULT_BASE_URL, DEFAULT_LOG_DIR, DEFAULT_TOKEN_FILE, call_action, read_token, sanitize


DEFAULT_REMOTE_ASSETS = Path(os.environ.get("SUMIKA_ASSETS_DIR", "assets/generated"))
STICKER_NAMES = [
    "sumika_01_happy.png",
    "sumika_02_confused.png",
    "sumika_03_shy.png",
    "sumika_04_serious.png",
    "sumika_05_sleepy.png",
    "sumika_06_pout.png",
    "sumika_07_cheer.png",
    "sumika_08_received.png",
]


def action_success(response: dict[str, Any]) -> bool:
    return str(response.get("status") or "").lower() == "ok" or response.get("retcode") == 0


def sticker_paths(assets_dir: Path) -> list[Path]:
    return [assets_dir / "stickers" / name for name in STICKER_NAMES]


def add_custom_faces(base_url: str, token: str, assets_dir: Path, timeout: float) -> list[dict[str, Any]]:
    results = []
    for path in sticker_paths(assets_dir):
        if not path.exists():
            results.append({"file": str(path), "ok": False, "error": "missing file"})
            continue
        response = call_action(
            base_url,
            token,
            "add_custom_face",
            {"file": str(path), "file_name": path.name, "is_origin": True},
            timeout,
        )
        results.append({"file": str(path), "ok": action_success(response), "response": response})
    return results


def send_private_message(
    base_url: str,
    token: str,
    user_id: int,
    message: str | list[dict[str, Any]],
    timeout: float,
) -> dict[str, Any]:
    return call_action(
        base_url,
        token,
        "send_private_msg",
        {"user_id": user_id, "message": message},
        timeout,
    )


def send_text_chunks(
    base_url: str,
    token: str,
    user_id: int,
    text: str,
    timeout: float,
    chunk_size: int = 900,
) -> list[dict[str, Any]]:
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    return [send_private_message(base_url, token, user_id, chunk, timeout) for chunk in chunks]


def image_segment(path: Path) -> list[dict[str, Any]]:
    return [{"type": "image", "data": {"file": str(path)}}]


def send_assets(
    base_url: str,
    token: str,
    assets_dir: Path,
    user_id: int,
    timeout: float,
) -> dict[str, Any]:
    results: dict[str, Any] = {"probe": None, "stickers": [], "persona": []}
    probe = send_private_message(
        base_url,
        token,
        user_id,
        "你好呀，我是澄夏。给你看一点我的小表情和人设。",
        timeout,
    )
    results["probe"] = probe
    if not action_success(probe):
        results["skipped"] = "private message probe failed"
        return results

    for path in sticker_paths(assets_dir):
        response = send_private_message(base_url, token, user_id, image_segment(path), timeout)
        results["stickers"].append({"file": str(path), "ok": action_success(response), "response": response})

    reference = assets_dir / "sumika-character-reference.png"
    if reference.exists():
        response = send_private_message(base_url, token, user_id, image_segment(reference), timeout)
        results["persona"].append({"file": str(reference), "ok": action_success(response), "response": response})

    persona_card = assets_dir / "sumika-persona-card.md"
    if persona_card.exists():
        text = persona_card.read_text(encoding="utf-8")
        responses = send_text_chunks(base_url, token, user_id, text, timeout)
        results["persona"].append(
            {
                "file": str(persona_card),
                "ok": all(action_success(response) for response in responses),
                "responses": responses,
            }
        )
    return results


def write_log(log_dir: Path, record: dict[str, Any]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"sumika_assets_{time.strftime('%Y%m%d')}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sanitize(record), ensure_ascii=False) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import and send Sumika stickers/persona assets.")
    parser.add_argument("--base-url", default=os.environ.get("SUMIKA_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token")
    parser.add_argument("--token-file", default=str(DEFAULT_TOKEN_FILE))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))
    parser.add_argument("--assets-dir", default=str(DEFAULT_REMOTE_ASSETS))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("add-custom-faces")
    send = sub.add_parser("send-to")
    send.add_argument("user_id", type=int)
    all_cmd = sub.add_parser("import-and-send")
    all_cmd.add_argument("user_id", type=int)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    token = read_token(args)
    assets_dir = Path(args.assets_dir)
    record: dict[str, Any] = {
        "ts": time.time(),
        "command": args.command,
        "assets_dir": str(assets_dir),
        "results": None,
    }
    try:
        if args.command == "add-custom-faces":
            result = {"custom_faces": add_custom_faces(args.base_url, token, assets_dir, args.timeout)}
        elif args.command == "send-to":
            result = send_assets(args.base_url, token, assets_dir, args.user_id, args.timeout)
        elif args.command == "import-and-send":
            result = {
                "custom_faces": add_custom_faces(args.base_url, token, assets_dir, args.timeout),
                "send": send_assets(args.base_url, token, assets_dir, args.user_id, args.timeout),
            }
        else:
            raise RuntimeError(f"unknown command: {args.command}")
        record["results"] = result
        write_log(Path(args.log_dir), record)
        print(json.dumps(sanitize(result), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        record["error"] = str(exc)
        write_log(Path(args.log_dir), record)
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
