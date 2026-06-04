from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from .privacy import redact_sensitive
from .role_assets import RoleAssets
from .storage import Store


@dataclass(frozen=True)
class MemoryEvent:
    scope: str
    target_id: str
    user_id: str
    message: str
    reply: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryQuery:
    user_id: str
    text: str
    scope: str = "private"
    target_id: str = ""


@dataclass(frozen=True)
class MemoryContext:
    world_memory: list[str]
    profile: dict[str, Any]
    worldbook: list[dict[str, Any]]
    relationships: list[dict[str, Any]]

    def as_prompt_context(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "worldbook": self.worldbook,
            "relationships": self.relationships,
        }


class MemoryGateway(Protocol):
    def ingest_event(self, event: MemoryEvent) -> None: ...

    def retrieve_context(self, query: MemoryQuery) -> MemoryContext: ...

    def update_profile(self, user_id: str, patch: dict[str, Any]) -> None: ...

    def update_relationship(self, subject_id: str, object_id: str, patch: dict[str, Any]) -> None: ...

    def reflect_session(self, scope: str, target_id: str) -> dict[str, Any]: ...

    def export_user_memory(self, user_id: str) -> dict[str, Any]: ...

    def delete_user_memory(self, user_id: str) -> None: ...


class SQLiteMemoryGateway:
    """Local fallback gateway; upstream sidecars plug in behind the same interface later."""

    def __init__(self, store: Store, role_assets: RoleAssets | None = None):
        self.store = store
        self.role_assets = role_assets

    def ingest_event(self, event: MemoryEvent) -> None:
        message = redact_sensitive(event.message)
        reply = redact_sensitive(event.reply)
        self.store.record_interaction(
            event.scope,
            event.target_id,
            event.user_id,
            message.text,
            reply.text,
            redaction_labels=sorted(set(message.labels + reply.labels)),
            metadata=event.metadata,
        )

    def retrieve_context(self, query: MemoryQuery) -> MemoryContext:
        profile = self.store.get_user_memory(query.user_id)
        world = [row["content"] for row in reversed(self.store.world_memories(limit=20))]
        worldbook = self.role_assets.worldbook_hits(query.text) if self.role_assets else []
        relationships = self.store.list_relationships(query.user_id, limit=10)
        return MemoryContext(world, profile, worldbook, relationships)

    def update_profile(self, user_id: str, patch: dict[str, Any]) -> None:
        allowed = {key: value for key, value in patch.items() if key in {"display_name", "summary", "preferences", "boundaries", "favorability", "last_interaction"}}
        if allowed:
            self.store.update_user_memory(user_id, **allowed)

    def update_relationship(self, subject_id: str, object_id: str, patch: dict[str, Any]) -> None:
        self.store.upsert_relationship(subject_id, object_id, patch)

    def reflect_session(self, scope: str, target_id: str) -> dict[str, Any]:
        return {
            "scope": scope,
            "target_id": target_id,
            "reflected_at": time.time(),
            "backend": "sqlite",
            "status": "fallback-summary-only",
        }

    def export_user_memory(self, user_id: str) -> dict[str, Any]:
        return self.store.export_user_memory(user_id)

    def delete_user_memory(self, user_id: str) -> None:
        self.store.delete_user_memory(user_id)
