#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
サッカー日本代表 TV放送チェッカー スクレイパー
Goal.com から日本代表の試合日程・放送予定を取得して matches.json を更新する。
"""

import json
import os
import re

URL = "https://www.goal.com/jp/ニュース/japan-national-team-schedule-broadcast/1oyzx47bv2f6p1lcdsrtkc89s8"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "matches.json")

BROADCASTER_MAP = {
    "NHK": "NHK",
    "NHK総合": "NHK",
    "NHK BS": "NHK BS",
    "NHK BS1": "NHK BS",
    "NHK BSP4K": "NHK BS",
    "BSP4K": "NHK BS",
    "日本テレビ": "日テレ",
    "日テレ": "日テレ",
    "日テレ系": "日テレ",
    "フジテレビ": "フジテレビ",
    "フジテレビ系列": "フジテレビ",
    "フジ": "フジテレビ",
    "テレビ朝日": "テレビ朝日",
    "テレ朝": "テレビ朝日",
    "TBS": "TBS",
    "TBS系列": "TBS",
    "テレビ東京": "テレビ東京",
    "テレ東": "テレビ東京",
    "DAZN": "DAZN",
    "ABEMA": "ABEMA",
}

TERRESTRIAL_BROADCASTERS = {"NHK", "日テレ", "フジテレビ", "テレビ朝日", "TBS", "テレビ東京"}
BS_BROADCASTERS = {"NHK BS"}
NET_BROADCASTERS = {"DAZN", "ABEMA"}

JAPAN_NAMES = {"日本", "サムライブルー", "日本代表"}


def normalize_broadcaster(name: str) -> str:
    name = name.strip()
    return BROADCASTER_MAP.get(name, name)


def classify_broadcaster(name: str) -> str:
    if name in TERRESTRIAL_BROADCASTERS:
        return "onair"
    if name in BS_BROADCASTERS:
        return "bs"
    if name in NET_BROADCASTERS:
        return "net"
    return "onair"


def parse_date_time(text: str):
    m = re.match(r"(\d{1,2})/(\d{1,2})\([^)]+\)\s*(\d{1,2}):(\d{2})", text.strip())
    if not m:
        return None
    month, day, hour, minute = m.groups()
    return f"{int(month)}/{int(day)}", f"{int(hour):02d}:{minute}"


def parse_schedule_card(text: str):
    text = text.strip()

    m = re.match(r"^(.+?)\s+(\d+)\s*-\s*(\d+)\s+(.+?)$", text)
    if m:
        return {
            "team1": m.group(1).strip(), "score1": int(m.group(2)),
            "score2": int(m.group(3)), "team2": m.group(4).strip(),
        }

    m = re.match(r"^(.+?)\s*-\s*未定$", text)
    if m:
        return {"team1": m.group(1).strip(), "team2": "未定"}

    m = re.match(r"^(.+?)\s+vs\s+(.+?)$", text, re.I)
    if m:
        return {"team1": m.group(1).strip(), "team2": m.group(2).strip()}

    return None


def parse_broadcast_text(text: str) -> list:
    net_sep = re.search(r"【ネット】", text)
    if net_sep:
        tv_part = text[:net_sep.start()]
        net_part = text[net_sep.end():]
    else:
        tv_part, net_part = text, ""
    tv_part = re.sub(r"【テレビ】", "", tv_part)

    broadcasters = []
    for part in (tv_part, net_part):
        for m in re.finditer(r"([^()]+?)\(([^)]+)\)", part):
            name = normalize_broadcaster(m.group(1))
            if name and name not in broadcasters:
                broadcasters.append(name)
    return broadcasters


if __name__ == "__main__":
    pass
