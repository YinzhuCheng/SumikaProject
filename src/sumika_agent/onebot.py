from __future__ import annotations

import asyncio
import json
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .budget import BudgetManager
from .favorability import clamp, natural_invite_reply, score_delta
from .memory import MemoryEvent, MemoryGateway, MemoryQuery
from .multimodal import MultimodalProcessor
from .openrouter import OpenRouterClient
from .persona import Persona
from .privacy import looks_sensitive, redact_sensitive
from .search import SearchTool
from .settings import Settings
from .storage import Store


@dataclass
class Target:
    scope: str
    target_id: str


class OneBotHub:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        persona: Persona,
        budget: BudgetManager,
        openrouter: OpenRouterClient,
        search: SearchTool,
        multimodal: MultimodalProcessor,
        memory_gateway: MemoryGateway | None = None,
    ):
        self.settings = settings
        self.store = store
        self.persona = persona
        self.budget = budget
        self.openrouter = openrouter
        self.search = search
        self.multimodal = multimodal
        self.memory_gateway = memory_gateway
        self._clients: set[WebSocket] = set()
        self._pending_actions: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._outbound_message_lock = asyncio.Lock()
        self.self_id: str | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        try:
            while True:
                raw = await websocket.receive_text()
                event = json.loads(raw)
                if self._resolve_action_response(event):
                    continue
                await self.handle_event(event, websocket)
        except WebSocketDisconnect:
            pass
        finally:
            self._clients.discard(websocket)

    async def send_action(self, action: str, params: dict[str, Any]) -> None:
        if not self._clients:
            return
        await self._pace_outbound_message(action)
        payload = {"action": action, "params": params, "echo": str(uuid.uuid4())}
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def call_action(
        self, action: str, params: dict[str, Any] | None = None, timeout: float = 30.0
    ) -> dict[str, Any]:
        websocket = next(iter(self._clients), None)
        if websocket is None:
            raise RuntimeError("no OneBot client connected")
        echo = str(uuid.uuid4())
        payload = {"action": action, "params": params or {}, "echo": echo}
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending_actions[echo] = future
        try:
            await self._pace_outbound_message(action)
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending_actions.pop(echo, None)

    async def _pace_outbound_message(self, action: str) -> None:
        if action not in {"send_msg", "send_private_msg", "send_group_msg"}:
            return
        low = max(0.0, float(self.settings.outbound_message_delay_min_seconds))
        high = max(low, float(self.settings.outbound_message_delay_max_seconds))
        async with self._outbound_message_lock:
            await asyncio.sleep(random.uniform(low, high))

    def _resolve_action_response(self, event: dict[str, Any]) -> bool:
        echo = event.get("echo")
        if not echo:
            return False
        future = self._pending_actions.get(str(echo))
        if future is None:
            return False
        if not future.done():
            future.set_result(event)
        return True

    async def handle_event(self, event: dict[str, Any], websocket: WebSocket | None = None) -> None:
        if event.get("self_id"):
            self.self_id = str(event.get("self_id"))
        post_type = event.get("post_type")
        if post_type == "message":
            await self._handle_message(event)
        elif post_type == "request":
            await self._handle_request(event)

    async def _handle_request(self, event: dict[str, Any]) -> None:
        request_type = str(event.get("request_type") or "")
        user_id = str(event.get("user_id") or "")
        memory = self.store.get_user_memory(user_id)
        reply = natural_invite_reply(float(memory.get("favorability") or 0))
        self.store.enqueue_approval(
            {
                "request_type": request_type,
                "flag": event.get("flag"),
                "user_id": user_id,
                "group_id": str(event.get("group_id") or ""),
                "comment": event.get("comment") or "",
                "natural_reply": reply,
            }
        )
        if user_id.isdigit():
            await self.send_action("send_private_msg", {"user_id": int(user_id), "message": reply})

    async def _handle_message(self, event: dict[str, Any]) -> None:
        if not self.budget.allow_text():
            return
        message_type = str(event.get("message_type") or "")
        user_id = str(event.get("user_id") or "")
        group_id = str(event.get("group_id") or "")
        target = Target("private", user_id) if message_type == "private" else Target("group", group_id)
        parsed = await self.multimodal.parse(event.get("message"))
        raw_text = parsed.text or ""

        if message_type == "group" and not self._should_reply_group(event, raw_text):
            return

        if parsed.image_insufficient and not raw_text.replace("[图片]", "").strip():
            await self._send_reply(target, "手机看不到图片")
            return
        if parsed.voice_insufficient and not raw_text.replace("[语音]", "").strip():
            await self._send_reply(target, "刚刚那段我没听清，能不能打字说一遍呀。")
            return

        safe_text = redact_sensitive(raw_text).text
        reply = await self.generate_reply(user_id, safe_text)
        if reply:
            await self._send_reply(target, reply)
            self._record_interaction(target, user_id, safe_text, reply, event)
            self._update_memory_after_message(user_id, event, safe_text)

    def _should_reply_group(self, event: dict[str, Any], text: str) -> bool:
        group_id = str(event.get("group_id") or "")
        if not self.store.is_whitelisted("group", group_id):
            return False
        if self.persona.nickname in text or self.persona.name in text:
            return True
        if self.self_id and f"@{self.self_id}" in text:
            return True
        return False

    async def generate_reply(self, user_id: str, text: str) -> str:
        memory = self.store.get_user_memory(user_id)
        world = [row["content"] for row in reversed(self.store.world_memories(limit=20))]
        gateway_context: dict[str, Any] = {}
        if self.memory_gateway:
            context = self.memory_gateway.retrieve_context(MemoryQuery(user_id=user_id, text=text))
            memory = context.profile
            world = context.world_memory
            gateway_context = context.as_prompt_context()

        messages = [
            {
                "role": "system",
                "content": self.persona.system_prompt(world, memory, gateway_context),
            }
        ]

        if self.search.should_search(text):
            results = self.search.search(text, max_results=4)
            messages.append(
                {
                    "role": "system",
                    "content": "你刚刚查到这些资料。只把有把握的部分自然说出来，不要列机械来源清单：\n"
                    + self.search.format_for_prompt(results),
                }
            )
        messages.append({"role": "user", "content": text})
        result = await self.openrouter.chat(messages)
        reply = str(result.get("text") or "").strip()
        if not reply:
            reply = random.choice(
                [
                    "我刚刚有点走神了，再说一遍好不好。",
                    "嗯……这句我没想好，等我一下嘛。",
                ]
            )
        return reply[:1200]

    async def _send_reply(self, target: Target, message: str) -> None:
        if target.scope == "private":
            await self.send_action("send_private_msg", {"user_id": int(target.target_id), "message": message})
        else:
            await self.send_action("send_group_msg", {"group_id": int(target.target_id), "message": message})

    def _record_interaction(
        self, target: Target, user_id: str, message: str, reply: str, event: dict[str, Any]
    ) -> None:
        if self.memory_gateway:
            self.memory_gateway.ingest_event(
                MemoryEvent(
                    scope=target.scope,
                    target_id=target.target_id,
                    user_id=user_id,
                    message=message,
                    reply=reply,
                    metadata={
                        "message_id": event.get("message_id"),
                        "message_type": event.get("message_type"),
                        "nickname": event.get("sender", {}).get("nickname"),
                    },
                )
            )
            return
        self.store.record_interaction(target.scope, target.target_id, user_id, message, reply)

    def _update_memory_after_message(self, user_id: str, event: dict[str, Any], text: str) -> None:
        memory = self.store.get_user_memory(
            user_id, display_name=str(event.get("sender", {}).get("nickname") or "")
        )
        favor = clamp(float(memory.get("favorability") or 0) + score_delta(text))
        summary = str(memory.get("summary") or "")
        if len(text) > 4 and not looks_sensitive(text):
            if len(summary) < 600:
                summary = (summary + "\n" + f"最近聊到：{text[:80]}").strip()
        patch = {"favorability": favor, "last_interaction": time.time(), "summary": summary}
        if self.memory_gateway:
            self.memory_gateway.update_profile(user_id, patch)
        else:
            self.store.update_user_memory(user_id, **patch)

    async def send_proactive(self, target: Target, user_id: str) -> None:
        if not self.budget.allow_proactive():
            return
        memory = self.store.get_user_memory(user_id)
        favor = float(memory.get("favorability") or 0)
        if favor < 10 and random.random() > 0.08:
            return
        world = [row["content"] for row in reversed(self.store.world_memories(limit=20))]
        prompt = (
            "现在是你的主动发言时机。写一句自然、低打扰、人格一致的话，"
            "不要解释触发机制，不要像通知，不要提好感度。"
        )
        result = await self.openrouter.chat(
            [
                {"role": "system", "content": self.persona.system_prompt(world, memory)},
                {"role": "user", "content": prompt},
            ],
            max_tokens=120,
        )
        text = str(result.get("text") or "").strip()
        if text:
            await self._send_reply(target, text[:500])
