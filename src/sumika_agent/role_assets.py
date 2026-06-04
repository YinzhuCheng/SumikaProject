from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


ROLE_FILES = (
    "identity",
    "personality",
    "thinking_style",
    "speech_style",
    "relationships",
    "worldbook",
    "visual_bible",
    "image_plan",
    "manifest",
)


@dataclass(frozen=True)
class RoleAssets:
    root: Path
    sections: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, root: Path | str) -> "RoleAssets":
        base = Path(root)
        sections: dict[str, dict[str, Any]] = {}
        for name in ROLE_FILES:
            path = base / f"{name}.yml"
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            else:
                data = {}
            sections[name] = data
        return cls(base, sections)

    def section(self, name: str) -> dict[str, Any]:
        return self.sections.get(name, {})

    def worldbook_hits(self, text: str, limit: int = 4) -> list[dict[str, Any]]:
        entries = self.section("worldbook").get("entries") or []
        hits: list[dict[str, Any]] = []
        for entry in entries:
            triggers = entry.get("triggers") or []
            if any(str(trigger) and str(trigger) in text for trigger in triggers):
                hits.append(entry)
            if len(hits) >= limit:
                break
        return hits

    def core_asset_summary(self) -> str:
        identity = self.section("identity")
        personality = self.section("personality")
        speech = self.section("speech_style")
        thinking = self.section("thinking_style")
        relationships = self.section("relationships")
        lines = [
            f"角色身份：{identity.get('name', '星见澄夏')}，{identity.get('daily_positioning', {}).get('public_face', '')}",
            f"人格特质：{', '.join(t.get('name', '') for t in personality.get('traits', []) if t.get('name'))}",
            f"思维方式：{thinking.get('thinking_style', {}).get('default', '')}",
            f"发言风格：{speech.get('style', {}).get('tone', '')}",
            f"关系默认：{relationships.get('relationship_model', {}).get('default_relation', '')}",
        ]
        return "\n".join(line for line in lines if line.strip())
