from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

import sumika_agent.proactive as proactive_module
import sumika_agent.onebot as onebot_module
from sumika_agent.favorability import clamp, natural_invite_reply, score_delta
from sumika_agent.onebot import OneBotHub
from sumika_agent.proactive import ProactiveScheduler


def test_favorability_delta_positive_and_negative():
    assert score_delta("谢谢你，澄夏真可爱") > 0
    assert score_delta("闭嘴") < 0
    assert clamp(999) == 100
    assert clamp(-999) == -100


def test_invite_reply_is_natural():
    assert "权限" not in natural_invite_reply(0)
    assert "考虑" in natural_invite_reply(0)


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


async def test_proactive_stop_cancels_sleeping_task():
    settings = SimpleNamespace(zoneinfo=timezone(timedelta(hours=8)), proactive_enabled=False)
    hub = SimpleNamespace(budget=SimpleNamespace(allow_proactive=lambda: False))
    scheduler = ProactiveScheduler(settings, None, None, hub)

    scheduler.start()
    await asyncio.sleep(0)
    await scheduler.stop()

    assert scheduler._task.done()
