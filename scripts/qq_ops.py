#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_TOKEN_FILE = Path(os.environ.get("SUMIKA_ADMIN_TOKEN_FILE", "secrets/admin_token"))
DEFAULT_AVATAR = Path(os.environ.get("SUMIKA_DEFAULT_AVATAR", "assets/generated/sumika-avatar.jpg"))
DEFAULT_SIGNATURE = "星屑落在夏天，今天也想认真听你说话。"
DEFAULT_FRIEND_COMMENT = "你好呀，我是澄夏。"
DEFAULT_LOG_DIR = Path(os.environ.get("SUMIKA_QQ_OPS_LOG_DIR", "artifacts/qq_ops"))


class AgentError(RuntimeError):
    pass


def read_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token.strip()
    env_token = os.environ.get("ADMIN_TOKEN")
    if env_token:
        return env_token.strip()
    token_file = Path(args.token_file or DEFAULT_TOKEN_FILE)
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    raise AgentError(f"admin token not found: {token_file}")


def request_json(
    base_url: str,
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any] | list[Any]:
    body = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(f"{base_url.rstrip('/')}{path}", data=body, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AgentError(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise AgentError(f"{method} {path} failed: {exc}") from exc
    if not raw:
        return {}
    return json.loads(raw)


def call_action(
    base_url: str,
    token: str,
    action: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    result = request_json(
        base_url,
        token,
        "POST",
        "/api/onebot/action",
        {"action": action, "params": params or {}, "timeout": timeout},
        timeout=timeout + 5,
    )
    if not isinstance(result, dict):
        raise AgentError(f"unexpected action response type: {type(result).__name__}")
    return result


def normalize_avatar(value: str) -> str:
    if value.startswith(("base64://", "http://", "https://", "file://")):
        return value
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise AgentError(f"avatar file not found: {path}")
    return str(path)


def set_profile(
    base_url: str,
    token: str,
    avatar: str | None,
    signature: str | None,
    timeout: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if avatar:
        results.append(call_action(base_url, token, "set_qq_avatar", {"file": normalize_avatar(avatar)}, timeout))
    if signature:
        results.append(
            call_action(base_url, token, "set_self_longnick", {"longNick": signature}, timeout)
        )
    return results


def friend_ids(friend_list_response: dict[str, Any]) -> set[str]:
    data = friend_list_response.get("data") or []
    if isinstance(data, dict):
        data = data.get("friends") or data.get("items") or []
    ids: set[str] = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        for key in ("user_id", "uin", "qq", "id"):
            value = item.get(key)
            if value is not None:
                ids.add(str(value))
        uid = item.get("uid")
        if uid is not None:
            ids.add(str(uid))
    return ids


def action_ok(response: dict[str, Any]) -> bool:
    status = str(response.get("status") or "").lower()
    retcode = response.get("retcode")
    return status == "ok" or retcode == 0


def try_add_friend(
    base_url: str,
    token: str,
    user_id: str,
    comment: str,
    timeout: float,
) -> dict[str, Any]:
    user_id = user_id.strip()
    if not user_id.isdigit():
        raise AgentError("user_id must be numeric")
    friends = call_action(base_url, token, "get_friend_list", {}, timeout)
    if user_id in friend_ids(friends):
        return {"ok": True, "status": "already_friend", "user_id": user_id}

    response = call_action(
        base_url,
        token,
        "sumika_add_friend",
        {"user_id": int(user_id), "comment": comment},
        timeout,
    )
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    inner_status = str(data.get("status") or "").lower()
    if action_ok(response) and inner_status in {"already_friend", "request_sent_or_accepted"}:
        return {"ok": True, "status": "request_sent", "user_id": user_id, "response": response}
    return {
        "ok": False,
        "status": inner_status or "unsupported_or_failed",
        "user_id": user_id,
        "response": response,
        "note": "The Sumika NapCat extension is installed, but the current QQ kernel did not accept any active friend-request candidate.",
    }


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"authorization", "token", "access_token", "admin_token"}:
                cleaned[key] = "<redacted>"
            elif lowered in {"file"} and isinstance(item, str) and item.startswith("base64://"):
                cleaned[key] = f"<base64 image, {len(item)} chars>"
            else:
                cleaned[key] = sanitize(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        index = value.find("base64://")
        if index >= 0:
            return value[:index] + f"<base64 data, {len(value) - index} chars>"
        if len(value) > 1200:
            return value[:1200] + f"... <truncated, {len(value)} chars>"
    return value


def write_log(log_dir: Path, record: dict[str, Any]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d")
    path = log_dir / f"qq_ops_{stamp}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sanitize(record), ensure_ascii=False) + "\n")


def print_json(value: Any) -> None:
    print(json.dumps(sanitize(value), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scripted QQ profile and relationship operations.")
    parser.add_argument("--base-url", default=os.environ.get("SUMIKA_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token")
    parser.add_argument("--token-file", default=str(DEFAULT_TOKEN_FILE))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--log-dir", default=str(DEFAULT_LOG_DIR))

    sub = parser.add_subparsers(dest="command", required=True)

    raw = sub.add_parser("action", help="Call a raw OneBot action through the agent bridge.")
    raw.add_argument("action")
    raw.add_argument("--params-json", default="{}")

    profile = sub.add_parser("set-profile", help="Set QQ avatar and/or signature.")
    profile.add_argument("--avatar")
    profile.add_argument("--signature")

    add_friend = sub.add_parser("add-friend", help="Best-effort active friend request.")
    add_friend.add_argument("user_id")
    add_friend.add_argument("--comment", default=DEFAULT_FRIEND_COMMENT)

    defaults = sub.add_parser("apply-sumika-defaults", help="Set Sumika avatar/signature and add a friend.")
    defaults.add_argument("--avatar", default=str(DEFAULT_AVATAR))
    defaults.add_argument("--signature", default=DEFAULT_SIGNATURE)
    defaults.add_argument("--friend")
    defaults.add_argument("--comment", default=DEFAULT_FRIEND_COMMENT)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    token = read_token(args)
    log_dir = Path(args.log_dir)
    record: dict[str, Any] = {
        "ts": time.time(),
        "command": args.command,
        "base_url": args.base_url,
        "results": [],
    }

    try:
        if args.command == "action":
            params = json.loads(args.params_json)
            if not isinstance(params, dict):
                raise AgentError("--params-json must decode to an object")
            result = call_action(args.base_url, token, args.action, params, args.timeout)
        elif args.command == "set-profile":
            result = set_profile(args.base_url, token, args.avatar, args.signature, args.timeout)
        elif args.command == "add-friend":
            result = try_add_friend(args.base_url, token, args.user_id, args.comment, args.timeout)
        elif args.command == "apply-sumika-defaults":
            result = {
                "profile": set_profile(
                    args.base_url, token, args.avatar, args.signature, args.timeout
                ),
                "friend": None,
            }
            if args.friend:
                result["friend"] = try_add_friend(
                    args.base_url, token, args.friend, args.comment, args.timeout
                )
        else:
            raise AgentError(f"unknown command: {args.command}")
        record["results"] = result
        write_log(log_dir, record)
        print_json(result)
        return 0
    except Exception as exc:
        record["error"] = str(exc)
        write_log(log_dir, record)
        print_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
