from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import httpx

from .settings import Settings
from .storage import Store


class OpenRouterClient:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self._lock = asyncio.Lock()
        self._minute_bucket = ""
        self._minute_count = 0

    def _headers(self) -> dict[str, str]:
        key = self.settings.read_openrouter_key()
        if not key:
            raise RuntimeError("OpenRouter key is missing")
        return {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://codex.local/or-project",
            "X-Title": "sumika-agent",
        }

    async def _rate_gate(self) -> None:
        async with self._lock:
            now = datetime.now(self.settings.zoneinfo)
            minute = now.strftime("%Y%m%d%H%M")
            if self._minute_bucket != minute:
                self._minute_bucket = minute
                self._minute_count = 0
            if self._minute_count >= self.settings.openrouter_rpm:
                raise RuntimeError("OpenRouter RPM budget reached")
            day = now.strftime("%Y%m%d")
            if self.store.get_counter(day, "openrouter_requests") >= self.settings.openrouter_daily_limit:
                raise RuntimeError("OpenRouter daily free request budget reached")
            self._minute_count += 1
            self.store.increment_counter(day, "openrouter_requests", 1)

    async def key_status(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.settings.openrouter_base_url}/key", headers=self._headers()
            )
            if response.status_code >= 400:
                return {"ok": False, "status": response.status_code, "body": response.text[:500]}
            data = response.json().get("data", {})
            return {
                "ok": True,
                "label": data.get("label"),
                "is_free_tier": data.get("is_free_tier"),
                "limit": data.get("limit"),
                "limit_remaining": data.get("limit_remaining"),
                "usage": data.get("usage"),
            }

    async def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 400) -> dict[str, Any]:
        last: dict[str, Any] | None = None
        effort = self.settings.openrouter_reasoning_effort.strip().lower()
        request_max_tokens = max(max_tokens, self.settings.openrouter_reasoning_min_tokens) if effort != "none" else max_tokens
        for _ in range(self.settings.openrouter_empty_retry + 1):
            await self._rate_gate()
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.settings.openrouter_base_url}/chat/completions",
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json={
                        "model": self.settings.openrouter_model,
                        "messages": messages,
                        "max_tokens": request_max_tokens,
                        "temperature": 0.8,
                        "reasoning": {
                            "effort": effort,
                            "exclude": self.settings.openrouter_reasoning_exclude,
                        },
                    },
                )
            if response.status_code in {401, 402, 429}:
                self.store.set_json("openrouter_disabled", {"status": response.status_code, "body": response.text[:500]})
                raise RuntimeError(f"OpenRouter disabled by status {response.status_code}")
            response.raise_for_status()
            payload = response.json()
            text = (payload.get("choices") or [{}])[0].get("message", {}).get("content")
            last = {
                "text": text or "",
                "model": payload.get("model"),
                "usage": payload.get("usage"),
            }
            if last["text"].strip():
                return last
        return last or {"text": "", "model": None, "usage": None}
