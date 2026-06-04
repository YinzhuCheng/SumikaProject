from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .prompting import PromptCompiler
from .role_assets import RoleAssets


@dataclass(frozen=True)
class Persona:
    name: str
    nickname: str
    timezone: str
    base_persona: str
    style_rules: list[str]
    activity: dict[str, Any]
    favorability: dict[str, str]
    world_memory_seed: list[str]
    role_asset_dir: str | None = None
    role_assets: RoleAssets | None = None

    @classmethod
    def load(cls, path: Path) -> "Persona":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        role_asset_dir = data.get("role_asset_dir")
        role_assets = RoleAssets.load(role_asset_dir) if role_asset_dir else None
        return cls(
            name=data["name"],
            nickname=data.get("nickname", data["name"]),
            timezone=data.get("timezone", "Asia/Shanghai"),
            base_persona=data["base_persona"],
            style_rules=data.get("style_rules", []),
            activity=data.get("activity", {}),
            favorability=data.get("favorability", {}),
            world_memory_seed=data.get("world_memory_seed", []),
            role_asset_dir=role_asset_dir,
            role_assets=role_assets,
        )

    def favorability_hint(self, user_memory: dict[str, Any]) -> str:
        favor = float(user_memory.get("favorability") or 0)
        if favor < -20:
            return self.favorability.get("cold", "")
        if favor < 30:
            return self.favorability.get("familiar", "")
        if favor < 70:
            return self.favorability.get("warm", "")
        return self.favorability.get("close", "")

    def system_prompt(
        self,
        world_memory: list[str],
        user_memory: dict[str, Any],
        gateway_context: dict[str, Any] | None = None,
    ) -> str:
        compiler = PromptCompiler(self.role_assets)
        return compiler.compile_system_prompt(
            base_persona=self.base_persona,
            style_rules=self.style_rules,
            favor_hint=self.favorability_hint(user_memory),
            world_memory=world_memory,
            user_memory=user_memory,
            gateway_context=gateway_context,
        )
