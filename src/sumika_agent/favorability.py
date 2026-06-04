from __future__ import annotations


POSITIVE_WORDS = ("谢谢", "喜欢", "可爱", "辛苦", "棒", "贴贴", "开心", "晚安", "早安")
NEGATIVE_WORDS = ("烦", "讨厌", "滚", "闭嘴", "笨", "骂", "垃圾")


def score_delta(message: str) -> float:
    delta = 0.4
    for word in POSITIVE_WORDS:
        if word in message:
            delta += 1.2
    for word in NEGATIVE_WORDS:
        if word in message:
            delta -= 2.0
    return max(-5.0, min(5.0, delta))


def clamp(value: float) -> float:
    return max(-100.0, min(100.0, value))


def natural_invite_reply(favor: float) -> str:
    if favor < 0:
        return "我先想想吧，突然这样有点紧张。"
    if favor < 40:
        return "我考虑考虑，等我想一下嘛。"
    if favor < 75:
        return "欸，听起来好像不错。我先记下来，等我想想。"
    return "你这么说我会认真考虑的。先让我悄悄记一下。"

