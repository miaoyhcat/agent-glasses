#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语音批准：把一句转写文字映射成明确的一个动作。

设计原则（对应「小改、要稳」）：

1. **只认固定说法**。认不出来就返回 None，什么都不做 —— 语音识别的错误
   不能变成一次批准。
2. **否定优先**。「不批准」「别批准」「取消」里都含有「批准」，
   所以先判否定，再判肯定。宁可不动，也不能把「不批准」听成「批准」。
3. **长度上限**。转写文本过长多半是串了别的话，直接不认。
4. **不保存原话**。调用方只应记录匹配到的动作，不要把整段转写写进日志
   （那可能包含用户没打算公开的内容）。

这个模块是纯函数，不碰网络、不碰数据库，便于单独测试。
"""

# 归一化时丢掉空白和常见标点（中英文都覆盖）
_PUNCT = " \t\r\n\u3000，。！？、；：,.!?;:…—-“”\"'《》()（）[]【】"

APPROVE_PHRASES = (
    "确认批准",
    "批准执行",
    "批准",
    "同意执行",
    "approve",
    "approved",
)

REJECT_PHRASES = (
    "不批准",
    "别批准",
    "不要批准",
    "拒绝",
    "取消",
    "reject",
    "rejected",
    "deny",
    "denied",
)

MAX_LEN = 120


def _normalize(text):
    return "".join(ch for ch in text if ch not in _PUNCT).lower()


def _hit(text, phrases):
    """返回命中的说法（长的优先），没命中返回 None。"""
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase in text:
            return phrase
    return None


def parse(transcript):
    """把转写映射成 'approve' / 'reject' / None。

    None 表示「没听懂」，调用方必须当作不批准处理。
    """
    if not isinstance(transcript, str):
        return None
    text = _normalize(transcript)
    if not text or len(text) > MAX_LEN:
        return None
    # 否定优先：先看有没有"不批准"这类说法
    if _hit(text, REJECT_PHRASES):
        return "reject"
    if _hit(text, APPROVE_PHRASES):
        return "approve"
    return None


def matched_phrase(transcript):
    """返回匹配到的具体说法，用于审计日志（只记短语，不记整段话）。"""
    if not isinstance(transcript, str):
        return None
    text = _normalize(transcript)
    if not text or len(text) > MAX_LEN:
        return None
    return _hit(text, REJECT_PHRASES) or _hit(text, APPROVE_PHRASES)
