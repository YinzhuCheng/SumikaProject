from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

import sumika_agent.onebot as onebot_module
import sumika_agent.proactive as proactive_module
from sumika_agent.favorability import clamp, natural_invite_reply, score_delta
from sumika_agent.memory import MemoryEvent, MemoryQuery, SQLiteMemoryGateway
from sumika_agent.memory_backends import AdvancedMemoryGateway, SidecarConfig
from sumika_agent.onebot import OneBotHub
from sumika_agent.privacy import looks_sensitive, redact_sensitive
from sumika_agent.proactive import ProactiveScheduler
from sumika_agent.role_assets import RoleAssets
from sumika_agent.storage import Store


def test_favorability_delta_positive_and_negative():
    assert score_delta("谢谢你，澄夏真可爱") > 0
    assert score_delta("闭嘴") < 0
    assert clamp(999) == 100
    assert clamp(-999) == -100


def test_invite_reply_is_natural():
    reply = natural_invite_reply(0)
    assert "权限" not in reply
    assert "考虑" in reply


def test_privacy_redaction():
    result = redact_sensitive("我的手机号是 13800138000，token=abc123")
    assert result.redacted
    assert "13800138000" not in result.text
    assert "abc123" not in result.text
    assert looks_sensitive("密码：hunter2")


def test_role_assets_worldbook_hits():
    assets = RoleAssets.load(Path("roles/sumika"))
    hits = assets.worldbook_hits("你会写星屑笔记吗")
    assert hits
    assert hits[0]["id"] == "stardust_notebook"
    summary = assets.core_asset_summary()
    assert "角色身份" in summary


def test_sqlite_memory_gateway_export_and_delete(tmp_path):
    store = Store(tmp_path / "sumika.sqlite3")
    assets = RoleAssets.load(Path("roles/sumika"))
    gateway = SQLiteMemoryGateway(store, assets)
    gateway.ingest_event(
        MemoryEvent(
            scope="private",
            target_id="10001",
            user_id="10001",
            message="我喜欢星屑笔记，手机号 13800138000",
            reply="我记住这个兴趣啦。",
        )
    )
    context = gateway.retrieve_context(MemoryQuery(user_id="10001", text="星屑笔记"))
    assert context.worldbook
    exported = gateway.export_user_memory("10001")
    assert exported["interactions"]
    assert "13800138000" not in exported["interactions"][0]["message"]
    gateway.delete_user_memory("10001")
    assert not gateway.export_user_memory("10001")["interactions"]


def test_advanced_memory_gateway_falls_back_when_sidecars_unavailable(tmp_path):
    store = Store(tmp_path / "sumika.sqlite3")
    fallback = SQLiteMemoryGateway(store, RoleAssets.load(Path("roles/sumika")))
    gateway = AdvancedMemoryGateway(
        fallback,
        SidecarConfig(
            memmachine_url="http://127.0.0.1:1",
            graphiti_url="http://127.0.0.1:1",
            cognee_url="http://127.0.0.1:1",
            timeout_seconds=0.05,
        ),
    )
    gateway.ingest_event(
        MemoryEvent(scope="private", target_id="10001", user_id="10001", message="喜欢星空")
    )
    context = gateway.retrieve_context(MemoryQuery(user_id="10001", text="星空"))
    assert context.profile["user_id"] == "10001"
    assert fallback.export_user_memory("10001")["interactions"]


def test_proactive_time_window(monkeypatch):
    settings = SimpleNamespace(zoneinfo=timezone(timedelta(hours=8)))
    scheduler = ProactiveScheduler(settings, None, None, None)

    class FixedDateTime(datetime):
        fixed: datetime

        @classmethod
        def now(cls, tz=None):
            return cls.fixed.astimezone(tz)

    monkeypatch.setattr(proactive_module, "datetime", FixedDateTime)

    FixedDateTime.fixed = datetime(2026, 6, 4, 10, 0, tzinfo=settings.zoneinfo)
    assert scheduler._active_for_proactive()

    FixedDateTime.fixed = datetime(2026, 6, 4, 23, 30, tzinfo=settings.zoneinfo)
    assert scheduler._active_for_proactive()

    FixedDateTime.fixed = datetime(2026, 6, 5, 0, 30, tzinfo=settings.zoneinfo)
    assert not scheduler._active_for_proactive()

    FixedDateTime.fixed = datetime(2026, 6, 5, 2, 30, tzinfo=settings.zoneinfo)
    assert not scheduler._active_for_proactive()


@pytest.mark.asyncio
async def test_outbound_message_pacing(monkeypatch):
    settings = SimpleNamespace(
        outbound_message_delay_min_seconds=1.0,
        outbound_message_delay_max_seconds=5.0,
    )
    hub = OneBotHub(settings, None, None, None, None, None, None)
    sleeps = []

    async def fake_sleep(value):
        sleeps.append(value)

    monkeypatch.setattr(onebot_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(onebot_module.random, "uniform", lambda low, high: 3.25)

    await hub._pace_outbound_message("send_private_msg")
    await hub._pace_outbound_message("get_friend_list")

    assert sleeps == [3.25]


@pytest.mark.asyncio
async def test_proactive_stop_cancels_sleeping_task():
    settings = SimpleNamespace(zoneinfo=timezone(timedelta(hours=8)), proactive_enabled=False)
    hub = SimpleNamespace(budget=SimpleNamespace(allow_proactive=lambda: False))
    scheduler = ProactiveScheduler(settings, None, None, hub)

    scheduler.start()
    await asyncio.sleep(0)
    await scheduler.stop()

    assert scheduler._task.done()
