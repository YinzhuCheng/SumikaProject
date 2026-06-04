from __future__ import annotations

import asyncio
import random
from datetime import datetime, time as dt_time

from .onebot import OneBotHub, Target
from .persona import Persona
from .settings import Settings
from .storage import Store


class ProactiveScheduler:
    def __init__(self, settings: Settings, store: Store, persona: Persona, hub: OneBotHub):
        self.settings = settings
        self.store = store
        self.persona = persona
        self.hub = hub
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    def _active_for_proactive(self) -> bool:
        now = datetime.now(self.settings.zoneinfo).time()
        return dt_time(10, 0) <= now < dt_time(23, 59, 59)

    async def _tick(self) -> None:
        if (
            not self.settings.proactive_enabled
            or not self._active_for_proactive()
            or not self.hub.budget.allow_proactive()
        ):
            return
        # Low-frequency stochastic trigger: roughly once every 90 minutes while online.
        if random.random() > (1 / 90):
            return
        users = [u for u in self.store.list_user_memories(limit=50) if (u.get("last_interaction") or 0)]
        if not users:
            return
        user = random.choice(users)
        target = Target("private", str(user["user_id"]))
        await self.hub.send_proactive(target, str(user["user_id"]))
