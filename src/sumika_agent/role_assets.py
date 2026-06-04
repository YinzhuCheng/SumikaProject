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
        detailed_dir = base / "detailed"
        if detailed_dir.exists():
            detailed: dict[str, dict[str, Any]] = {}
            for path in sorted(detailed_dir.glob("*.yml")):
                detailed[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            sections["detailed"] = detailed
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
        detailed = self.section("detailed")
        if detailed:
            detailed_identity = detailed.get("identity", {}).get("expanded", {})
            detailed_personality = detailed.get("personality", {}).get("expanded", {})
            detailed_speech = detailed.get("speech_style", {}).get("expanded", {})
            detailed_thinking = detailed.get("thinking_style", {}).get("expanded", {})
            detailed_relationships = detailed.get("relationships", {}).get("expanded", {})
            identity = detailed_identity or identity
            personality = detailed_personality or personality
            speech = detailed_speech or speech
            thinking = detailed_thinking or thinking
            relationships = detailed_relationships or relationships
        lines = [
            f"角色身份：{_name_text(identity)}，{_dig(identity, 'daily_positioning', 'public_face') or _dig(identity, 'daily_life', 'public_face')}",
            f"人格特质：{_traits_text(personality)}",
            f"思维方式：{_dig(thinking, 'thinking_style', 'default') or _dig(thinking, 'core', 'default')}",
            f"发言风格：{_dig(speech, 'style', 'tone') or _dig(speech, 'speech_style', 'tone')}",
            f"关系默认：{_dig(relationships, 'relationship_model', 'default_relation')}",
        ]
        return "\n".join(line for line in lines if line.strip())


def _dig(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _name_text(identity: dict[str, Any]) -> str:
    name = identity.get("name")
    if isinstance(name, dict):
        return str(name.get("full") or name.get("name") or "星见澄夏")
    return str(name or "星见澄夏")


def _traits_text(personality: dict[str, Any]) -> str:
    traits = personality.get("traits")
    if isinstance(traits, list):
        names = []
        for trait in traits:
            if isinstance(trait, dict):
                names.append(str(trait.get("name") or trait.get("trait") or ""))
            else:
                names.append(str(trait))
        return ", ".join(name for name in names if name)
    expanded_traits = _dig(personality, "personality", "traits")
    if isinstance(expanded_traits, list):
        return ", ".join(str(item) for item in expanded_traits[:6])
    return ""
