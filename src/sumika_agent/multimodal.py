from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytesseract
from PIL import Image

from .budget import BudgetManager
from .settings import Settings


@dataclass
class ParsedMessage:
    text: str
    placeholders: list[str] = field(default_factory=list)
    ocr_texts: list[str] = field(default_factory=list)
    voice_texts: list[str] = field(default_factory=list)
    image_insufficient: bool = False
    voice_insufficient: bool = False


def _segments(message: Any) -> list[dict[str, Any]]:
    if isinstance(message, str):
        return [{"type": "text", "data": {"text": message}}]
    if isinstance(message, list):
        return [seg for seg in message if isinstance(seg, dict)]
    return []


class MultimodalProcessor:
    def __init__(self, settings: Settings, budget: BudgetManager):
        self.settings = settings
        self.budget = budget

    async def parse(self, message: Any) -> ParsedMessage:
        parsed = ParsedMessage(text="")
        chunks: list[str] = []
        for seg in _segments(message):
            seg_type = seg.get("type")
            data = seg.get("data") or {}
            if seg_type == "text":
                chunks.append(str(data.get("text") or ""))
            elif seg_type == "at":
                chunks.append(f"@{data.get('qq')}")
            elif seg_type == "image":
                parsed.placeholders.append("[图片]")
                ocr_text = await self._try_ocr(data)
                if ocr_text:
                    parsed.ocr_texts.append(ocr_text)
                    chunks.append(f"[图片OCR: {ocr_text}]")
                else:
                    parsed.image_insufficient = True
                    chunks.append("[图片]")
            elif seg_type in {"record", "voice"}:
                parsed.placeholders.append("[语音]")
                voice_text = str(data.get("text") or data.get("transcript") or "").strip()
                if voice_text:
                    parsed.voice_texts.append(voice_text)
                    chunks.append(f"[语音转写: {voice_text}]")
                else:
                    parsed.voice_insufficient = True
                    chunks.append("[语音]")
            else:
                chunks.append(f"[{seg_type or '未知消息'}]")
        parsed.text = "".join(chunks).strip()
        return parsed

    async def _try_ocr(self, data: dict[str, Any]) -> str:
        if not self.settings.ocr_enabled or not self.budget.allow_media():
            return ""
        url = data.get("url") or data.get("file")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return ""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content
            if len(content) > 3_000_000:
                return ""
            image = Image.open(io.BytesIO(content))
            text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            compact = re.sub(r"\s+", " ", text).strip()
            if len(compact) < 8:
                return ""
            return compact[:800]
        except Exception:
            return ""

