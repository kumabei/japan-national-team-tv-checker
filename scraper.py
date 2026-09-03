#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
サッカー日本代表 TV放送チェッカー スクレイパー
Goal.com から日本代表の試合日程・放送予定を取得して matches.json を更新する。
"""

import json
import os
import re
import sys
from bs4 import BeautifulSoup

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

    m = re.match(r"^(.+?)\s*-\s*(.+?)$", text)
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


def parse_schedule_table(soup) -> list:
    table = soup.find_all("table")[0]
    rows = table.find_all("tr")
    results = []
    for row in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        date_time = parse_date_time(cells[0])
        if date_time is None:
            continue
        card = parse_schedule_card(cells[2])
        if card is None:
            continue
        date, time_str = date_time
        entry = {"date": date, "time": time_str, "stage": cells[1], **card}
        results.append(entry)
    return results


def parse_broadcast_table(soup) -> dict:
    tables = soup.find_all("table")
    if len(tables) == 0:
        return {}
    # Use the second table if it exists (schedule + broadcast on same page),
    # otherwise use the first table (broadcast-only page)
    table = tables[1] if len(tables) >= 2 else tables[0]
    rows = table.find_all("tr")
    result = {}
    for row in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        date_time = parse_date_time(cells[0])
        if date_time is None:
            continue
        result[date_time] = parse_broadcast_text(cells[2])
    return result


def merge_matches(schedule: list, broadcasts: dict) -> list:
    matches = []
    for entry in schedule:
        key = (entry["date"], entry["time"])
        broadcasters = broadcasts.get(key, [])
        tv_onair = [b for b in broadcasters if classify_broadcaster(b) == "onair"]
        tv_bs = [b for b in broadcasters if classify_broadcaster(b) == "bs"]
        tv_net = [b for b in broadcasters if classify_broadcaster(b) == "net"]

        team1, team2 = entry["team1"], entry["team2"]
        is_japan = any(name in team1 or name in team2 for name in JAPAN_NAMES)

        score = None
        if "score1" in entry:
            score = {"home": entry["score1"], "away": entry["score2"]}

        matches.append({
            "date": entry["date"], "time": entry["time"], "stage": entry["stage"],
            "team1": team1, "team2": team2,
            "tv_onair": tv_onair, "tv_bs": tv_bs, "tv_net": tv_net,
            "is_japan": is_japan, "score": score,
        })
    return matches


def _has_broadcast(match: dict) -> bool:
    return bool(match["tv_onair"] or match["tv_bs"] or match["tv_net"])


def detect_new_broadcasts(old_matches: list, new_matches: list) -> list:
    old_by_key = {(m["date"], m["time"]): m for m in old_matches}
    new_broadcasts = []
    for m in new_matches:
        if not _has_broadcast(m):
            continue
        key = (m["date"], m["time"])
        old = old_by_key.get(key)
        if old is None or not _has_broadcast(old):
            new_broadcasts.append(m)
    return new_broadcasts


def fetch_soup(url: str):
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    }
    res = requests.get(url, headers=headers, timeout=30)
    res.raise_for_status()
    res.encoding = "utf-8"
    return BeautifulSoup(res.text, "html.parser")


def load_old_matches() -> list:
    if not os.path.exists(OUTPUT_FILE):
        return []
    with open(OUTPUT_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_matches(matches: list):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)


def print_new_broadcasts(new_broadcasts: list):
    if not new_broadcasts:
        print("新着の放送予定はありません。")
        return
    print(f"新しく放送予定が確定した試合が {len(new_broadcasts)} 件あります:")
    for m in new_broadcasts:
        stations = m["tv_onair"] + m["tv_bs"] + m["tv_net"]
        print(f"  {m['date']} {m['time']}〜 {m['team1']} vs {m['team2']}"
              f"（{m['stage']}） {'・'.join(stations)}")


def main() -> list:
    print(f"取得中: {URL}")
    soup = fetch_soup(URL)

    schedule = parse_schedule_table(soup)
    broadcasts = parse_broadcast_table(soup)
    new_matches = merge_matches(schedule, broadcasts)

    old_matches = load_old_matches()
    new_broadcasts = detect_new_broadcasts(old_matches, new_matches)

    save_matches(new_matches)
    print(f"{OUTPUT_FILE} を更新しました（{len(new_matches)}試合）")
    print_new_broadcasts(new_broadcasts)
    return new_broadcasts


if __name__ == "__main__":
    main()
