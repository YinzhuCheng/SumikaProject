from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx

from sumika_agent.memory import MemoryContext, MemoryEvent, MemoryGateway, MemoryQuery


@dataclass(frozen=True)
class SidecarConfig:
    memmachine_url: str | None = None
    graphiti_url: str | None = None
    cognee_url: str | None = None
    timeout_seconds: float = 3.0


class AdvancedMemoryGateway:
    """Best-effort sidecar gateway with SQLite fallback.

    The exact upstream APIs are supplied by the Sumika patches. Until those sidecars are deployed,
    this gateway remains safe: all failures are swallowed after fallback state is updated.
    """

    def __init__(self, fallback: MemoryGateway, config: SidecarConfig):
        self.fallback = fallback
        self.config = config

    def ingest_event(self, event: MemoryEvent) -> None:
        self.fallback.ingest_event(event)
        payload = asdict(event)
        self._post(self.config.memmachine_url, "/sumika/episodes", payload)
        self._post(self.config.graphiti_url, "/sumika/graph/episodes", payload)

    def retrieve_context(self, query: MemoryQuery) -> MemoryContext:
        context = self.fallback.retrieve_context(query)
        worldbook = self._post(self.config.cognee_url, "/sumika/worldbook/search", asdict(query))
        relationships = self._post(self.config.graphiti_url, "/sumika/graph/relationships/search", asdict(query))
        return MemoryContext(
            world_memory=context.world_memory,
            profile=context.profile,
            worldbook=worldbook.get("items", context.worldbook) if isinstance(worldbook, dict) else context.worldbook,
            relationships=relationships.get("items", context.relationships)
            if isinstance(relationships, dict)
            else context.relationships,
        )

    def update_profile(self, user_id: str, patch: dict[str, Any]) -> None:
        self.fallback.update_profile(user_id, patch)
        self._post(self.config.memmachine_url, f"/sumika/users/{user_id}/profile", patch)

    def update_relationship(self, subject_id: str, object_id: str, patch: dict[str, Any]) -> None:
        self.fallback.update_relationship(subject_id, object_id, patch)
        payload = {"subject_id": subject_id, "object_id": object_id, **patch}
        self._post(self.config.graphiti_url, "/sumika/graph/relationships", payload)

    def reflect_session(self, scope: str, target_id: str) -> dict[str, Any]:
        fallback = self.fallback.reflect_session(scope, target_id)
        remote = self._post(
            self.config.memmachine_url,
            "/sumika/reflections",
            {"scope": scope, "target_id": target_id},
        )
        return remote if isinstance(remote, dict) and remote else fallback

    def export_user_memory(self, user_id: str) -> dict[str, Any]:
        fallback = self.fallback.export_user_memory(user_id)
        remote = self._post(self.config.memmachine_url, f"/sumika/users/{user_id}/export", {})
        if isinstance(remote, dict) and remote:
            return {"fallback": fallback, "remote": remote}
        return fallback

    def delete_user_memory(self, user_id: str) -> None:
        self.fallback.delete_user_memory(user_id)
        self._delete(self.config.memmachine_url, f"/sumika/users/{user_id}")
        self._delete(self.config.graphiti_url, f"/sumika/graph/users/{user_id}")
        self._delete(self.config.cognee_url, f"/sumika/worldbook/users/{user_id}")

    def _post(self, base_url: str | None, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not base_url:
            return {}
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                response = client.post(f"{base_url.rstrip('/')}{path}", json=payload)
                if response.status_code >= 400:
                    return {}
                return response.json()
        except Exception:
            return {}

    def _delete(self, base_url: str | None, path: str) -> None:
        if not base_url:
            return
        try:
            with httpx.Client(timeout=self.config.timeout_seconds) as client:
                client.delete(f"{base_url.rstrip('/')}{path}")
        except Exception:
            return
