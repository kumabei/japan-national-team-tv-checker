#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
サッカー日本代表 TV放送チェッカー スクレイパー
Goal.com から日本代表の試合日程・放送予定を取得して matches.json を更新する。
"""

import datetime
import json
import os
import re
import sys
from bs4 import BeautifulSoup

URL = "https://www.goal.com/jp/ニュース/japan-national-team-schedule-broadcast/1oyzx47bv2f6p1lcdsrtkc89s8"
TEAM_SCHEDULE_URL = (
    "https://www.goal.com/jp/%E3%83%81%E3%83%BC%E3%83%A0/%E6%97%A5%E6%9C%AC/"
    "%E6%97%A5%E7%A8%8B%E3%83%BB%E7%B5%90%E6%9E%9C/6duaxcbrofil112qfq4v895go"
)
# なでしこジャパン（女子A代表）: 日程結果テーブル＋放送予定テーブルを持つ記事ページ
NADESHIKO_URL = (
    "https://www.goal.com/jp/%E3%83%8B%E3%83%A5%E3%83%BC%E3%82%B9/"
    "nadeshiko-japan-schedule-broadcast/4uj3vbwdkhz51viqbodsrfcz8"
)
# 若い世代（U-21など）: 直近数日分の日本関連試合が日付ごとのテーブルで並ぶ「生きているページ」
YOUTH_LIST_URL = (
    "https://www.goal.com/jp/%E3%83%AA%E3%82%B9%E3%83%88/"
    "football-broadcast-schedule-japan/17wlgacoelh4x1vawfvh8kiq9o"
)
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
    "日本テレビ系列": "日テレ",
    "テレビ朝日系列": "テレビ朝日",
    "テレビ東京系列": "テレビ東京",
    "NHK総合テレビ": "NHK",
    "DAZN": "DAZN",
    "ABEMA": "ABEMA",
    "U-NEXT": "U-NEXT",
    # TVerは地上波の同時配信。地上波局と重複掲載されるが、シンプルさを優先してnet扱い
    "TVer": "TVer",
}

TERRESTRIAL_BROADCASTERS = {"NHK", "日テレ", "フジテレビ", "テレビ朝日", "TBS", "テレビ東京"}
BS_BROADCASTERS = {"NHK BS"}
NET_BROADCASTERS = {"DAZN", "ABEMA", "U-NEXT", "TVer"}

JAPAN_NAMES = {"日本", "サムライブルー", "日本代表"}

# チーム区分
TEAM_A = "a"
TEAM_NADESHIKO = "nadeshiko"
TEAM_YOUTH = "youth"
TEAM_LABELS = {TEAM_A: "日本代表", TEAM_NADESHIKO: "なでしこジャパン"}
TEAM_PRIORITY = {TEAM_A: 0, TEAM_NADESHIKO: 1, TEAM_YOUTH: 2}

# 「若い世代」ページ（サッカー全般の放送一覧）からA代表の試合を除外するための大会名
A_TEAM_STAGE_KEYWORDS = (
    "キリンチャレンジカップ", "キリンカップ", "ワールドカップ", "W杯",
    "アジア最終予選", "最終予選", "アジアカップ",
)
# 上のA代表キーワードを含んでいても、これらを含むなら「若い世代」扱いにする
YOUTH_STAGE_KEYWORDS = (
    "U-", "U15", "U16", "U17", "U18", "U19", "U20", "U21", "U22", "U23", "U24",
    "ユース", "オリンピック", "五輪", "アジア大会", "アジア競技大会", "女子", "なでしこ",
)

# 放送欄で「局名なし」を意味するトークン
NO_BROADCAST_TOKENS = {"未定", "なし", "未発表", "-", "‐", "―", "ー", "−"}


def normalize_broadcaster(name: str) -> str:
    name = name.strip()
    return BROADCASTER_MAP.get(name, name)


def normalize_stage(stage: str) -> str:
    """大会名の表記ゆれを吸収する。

    goal.comの取得元（スケジュール表／構造化データ）が、同じ大会でも
    「AFC アジアカップ」「AFCアジアカップ」のように半角スペースの有無を
    その都度変えて返してくることがあり、意味は同じなのにmatches.jsonへ
    無意味な差分が発生していた。ここで表記を一本化して差分を防ぐ。
    """
    stage = re.sub(r"\s+", " ", stage.strip())
    stage = stage.replace("AFC アジアカップ", "AFCアジアカップ")
    return stage


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


def parse_broadcast_tokens(text: str) -> list:
    """スペース区切りの放送局トークン列をパースする。

    A代表ページの `【テレビ】局名(時刻)` 形式とは違い、なでしこページの
    `【放送】TBS系列(録画) 【配信】 U-NEXT` や、若い世代ページの
    `U-NEXT TBS系列 TVer` のように、括弧が無いトークンが並ぶ形式に対応する。
    """
    text = re.sub(r"【[^】]*】", " ", text)
    text = re.sub(r"[(（][^)）]*[)）]", " ", text)
    broadcasters = []
    for token in text.split():
        token = token.strip("、,・/／")
        if not token or token in NO_BROADCAST_TOKENS:
            continue
        name = normalize_broadcaster(token)
        if name and name not in broadcasters:
            broadcasters.append(name)
    return broadcasters


def infer_year(date_str: str, today=None, past_threshold_days: int = 90) -> int:
    """西暦の無い「月/日」から年を推定する。

    今日より少し前までは今年の試合とみなし、極端に古い（既定では90日以上前の）
    月日は年をまたいだ来年の試合とみなす。直近数日分しか載らない
    「若い世代」ページのような用途を想定している。
    """
    today = today or datetime.date.today()
    month, day = (int(x) for x in date_str.split("/"))
    try:
        candidate = datetime.date(today.year, month, day)
    except ValueError:  # 2/29 など
        return today.year
    if (today - candidate).days >= past_threshold_days:
        return today.year + 1
    return today.year


def assign_years_sequential(entries: list, today=None) -> list:
    """日付昇順に並んだスケジュール行へ年を振る。

    シーズン一覧のように過去の試合も未来の試合も混ざるページでは、
    infer_year()の「過去なら来年」判定だと終わった試合が来年に化ける。
    最初の「今日以降」の行を今年として前後へ伸ばし、月日が巻き戻った所で
    年を繰り上げる（遡るときは繰り下げる）。
    """
    today = today or datetime.date.today()
    if not entries:
        return entries
    keys = [tuple(int(x) for x in e["date"].split("/")) for e in entries]
    anchor = next(
        (i for i, k in enumerate(keys) if k >= (today.month, today.day)),
        len(entries) - 1,
    )
    years = [None] * len(entries)
    years[anchor] = today.year
    for i in range(anchor + 1, len(entries)):
        years[i] = years[i - 1] + (1 if keys[i] < keys[i - 1] else 0)
    for i in range(anchor - 1, -1, -1):
        years[i] = years[i + 1] - (1 if keys[i] > keys[i + 1] else 0)
    for entry, year in zip(entries, years):
        entry["year"] = year
    return entries


def is_youth_stage(stage: str) -> bool:
    """大会名から「若い世代（A代表以外）」の試合かどうかを判定する。"""
    if any(k in stage for k in YOUTH_STAGE_KEYWORDS):
        return True
    return not any(k in stage for k in A_TEAM_STAGE_KEYWORDS)


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
        entry = {"date": date, "time": time_str, "stage": normalize_stage(cells[1]), **card}
        results.append(entry)
    return results


def parse_broadcast_table(soup, text_parser=None) -> dict:
    text_parser = text_parser or parse_broadcast_text
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
        result[date_time] = text_parser(cells[2])
    return result


def utc_iso_to_jst(iso_str: str):
    dt_utc = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    dt_jst = dt_utc.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    return (
        f"{dt_jst.month}/{dt_jst.day}",
        f"{dt_jst.hour:02d}:{dt_jst.minute:02d}",
        dt_jst.year,
    )


def parse_next_data_matches(html: str) -> list:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.S,
    )
    if not m:
        return []
    data = json.loads(m.group(1))
    return data["props"]["pageProps"]["content"]["matches"]


def convert_team_match(raw: dict):
    date, time_str, year = utc_iso_to_jst(raw["startDate"])
    team1 = raw["teamA"]["name"]
    team2 = raw["teamB"]["name"]

    competition_name = raw["competition"]["name"] if raw["competition"] else ""
    round_name = raw["round"]["name"] if raw["round"] else None
    if round_name and round_name != competition_name:
        stage = f"{competition_name} {round_name}"
    else:
        stage = competition_name
    stage = normalize_stage(stage)

    entry = {
        "date": date, "time": time_str, "year": year, "stage": stage,
        "team1": team1, "team2": team2,
    }
    if raw.get("score"):
        entry["score1"] = raw["score"]["teamA"]
        entry["score2"] = raw["score"]["teamB"]
    return entry


def merge_matches(schedule: list, broadcasts: dict, team: str = TEAM_A,
                   old_matches: list = None) -> list:
    # 終了した試合は放送予定ページの一覧から消えるため、broadcastsに
    # 情報が無いことは「放送局なし」ではなく「取得元から既に落ちただけ」の
    # ことが多い。新規取得が空なら、既存のmatches.jsonの値を引き継ぐ
    # （過去にブラジル戦の放送局情報が空上書きされる事故があったための対策）。
    # 同じ日時でもteamが違えば別試合なので、teamも合わせて絞り込む。
    old_by_key = {
        (m["date"], m["time"]): m
        for m in (old_matches or [])
        if m.get("team", TEAM_A) == team
    }
    matches = []
    for entry in schedule:
        key = (entry["date"], entry["time"])
        broadcasters = broadcasts.get(key, [])
        tv_onair = [b for b in broadcasters if classify_broadcaster(b) == "onair"]
        tv_bs = [b for b in broadcasters if classify_broadcaster(b) == "bs"]
        tv_net = [b for b in broadcasters if classify_broadcaster(b) == "net"]

        if not (tv_onair or tv_bs or tv_net):
            old = old_by_key.get(key)
            if old and (old.get("tv_onair") or old.get("tv_bs") or old.get("tv_net")):
                tv_onair = old.get("tv_onair", [])
                tv_bs = old.get("tv_bs", [])
                tv_net = old.get("tv_net", [])

        team1, team2 = entry["team1"], entry["team2"]
        is_japan = any(name in team1 or name in team2 for name in JAPAN_NAMES)

        score = None
        if "score1" in entry:
            score = {"home": entry["score1"], "away": entry["score2"]}

        match = {
            "date": entry["date"], "time": entry["time"], "stage": entry["stage"],
            "team1": team1, "team2": team2,
            "tv_onair": tv_onair, "tv_bs": tv_bs, "tv_net": tv_net,
            "is_japan": is_japan, "score": score, "team": team,
        }
        if "year" in entry:
            match["year"] = entry["year"]
        matches.append(match)
    return matches


def parse_nadeshiko_page(soup, today=None, old_matches=None) -> list:
    """なでしこジャパンの記事ページ（日程テーブル＋放送テーブル）をパースする。"""
    schedule = assign_years_sequential(parse_schedule_table(soup), today)
    broadcasts = parse_broadcast_table(soup, text_parser=parse_broadcast_tokens)
    return merge_matches(schedule, broadcasts, team=TEAM_NADESHIKO, old_matches=old_matches)


DATE_HEADING_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")


def parse_youth_list_page(soup, today=None, old_matches=None) -> list:
    """サッカー全般の放送一覧ページから、A代表以外の日本戦を抜き出す。

    日付見出し（h2/h3）の直後にその日のテーブルが1つ並ぶ構造。
    テーブルは [キックオフ, 対戦カード, 大会名, 放送チャンネル] の4列。
    """
    entries = []
    broadcasts = {}
    current_date = None
    for el in soup.find_all(["h1", "h2", "h3", "h4", "table"]):
        if el.name != "table":
            m = DATE_HEADING_RE.search(el.get_text(" ", strip=True))
            if m:
                current_date = f"{int(m.group(1))}/{int(m.group(2))}"
            continue
        if current_date is None:
            continue
        for row in el.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            tm = re.match(r"^(\d{1,2}):(\d{2})", cells[0].strip())
            if not tm:
                continue
            card = parse_schedule_card(cells[1])
            if card is None:
                continue
            if not any(n in card["team1"] or n in card["team2"] for n in JAPAN_NAMES):
                continue
            stage = normalize_stage(cells[2])
            if not is_youth_stage(stage):
                continue  # A代表の試合は専用ソースでカバー済み
            time_str = f"{int(tm.group(1)):02d}:{tm.group(2)}"
            entries.append({
                "date": current_date, "time": time_str,
                "year": infer_year(current_date, today),
                "stage": stage, **card,
            })
            broadcasts[(current_date, time_str)] = parse_broadcast_tokens(cells[3])
    return merge_matches(entries, broadcasts, team=TEAM_YOUTH, old_matches=old_matches)


def dedupe_matches(matches: list) -> list:
    """同じ（年・日付・時刻）の試合が複数ソースから来た場合、優先度の高い方を残す。

    例: アジア競技大会の女子戦は、なでしこページと放送一覧ページの
    両方に載る。A代表 > なでしこ > 若い世代 の順で優先する。
    """
    best = {}
    order = []
    for m in matches:
        key = (m.get("year"), m["date"], m["time"])
        current = best.get(key)
        if current is None:
            best[key] = m
            order.append(key)
        elif TEAM_PRIORITY.get(m.get("team", TEAM_A), 9) < \
                TEAM_PRIORITY.get(current.get("team", TEAM_A), 9):
            best[key] = m
    return [best[k] for k in order]


def _has_broadcast(match: dict) -> bool:
    return bool(match["tv_onair"] or match["tv_bs"] or match["tv_net"])


def detect_new_broadcasts(old_matches: list, new_matches: list) -> list:
    def _key(m):
        return (m.get("team", TEAM_A), m["date"], m["time"])

    old_by_key = {_key(m): m for m in old_matches}
    new_broadcasts = []
    for m in new_matches:
        if not _has_broadcast(m):
            continue
        key = _key(m)
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


def sort_matches(matches: list) -> list:
    def key(m):
        month, day = m["date"].split("/")
        return (m.get("year", 0), int(month), int(day), m["time"])
    return sorted(matches, key=key)


def fetch_team_matches(url: str) -> list:
    import requests

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

    matches = []
    for raw in parse_next_data_matches(res.text):
        team1 = raw["teamA"]["name"]
        team2 = raw["teamB"]["name"]
        if not any(name in team1 or name in team2 for name in JAPAN_NAMES):
            continue
        matches.append(convert_team_match(raw))
    return matches


def fetch_nadeshiko_matches(url: str = NADESHIKO_URL, old_matches=None) -> list:
    return parse_nadeshiko_page(fetch_soup(url), old_matches=old_matches)


def fetch_youth_matches(url: str = YOUTH_LIST_URL, old_matches=None) -> list:
    return parse_youth_list_page(fetch_soup(url), old_matches=old_matches)


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
        team = m.get("team", TEAM_A)
        label = TEAM_LABELS.get(team) or m["stage"]
        print(f"  [{label}] {m['date']} {m['time']}〜 {m['team1']} vs {m['team2']}"
              f"（{m['stage']}） {'・'.join(stations)}")


def main() -> list:
    old_matches = load_old_matches()

    print(f"取得中: {TEAM_SCHEDULE_URL}")
    schedule = fetch_team_matches(TEAM_SCHEDULE_URL)

    print(f"取得中: {URL}")
    soup = fetch_soup(URL)
    broadcasts = parse_broadcast_table(soup)
    a_matches = merge_matches(schedule, broadcasts, team=TEAM_A, old_matches=old_matches)
    print(f"  A代表: {len(a_matches)}試合")

    print(f"取得中: {NADESHIKO_URL}")
    nadeshiko_matches = fetch_nadeshiko_matches(old_matches=old_matches)
    print(f"  なでしこジャパン: {len(nadeshiko_matches)}試合")

    print(f"取得中: {YOUTH_LIST_URL}")
    youth_matches = fetch_youth_matches(old_matches=old_matches)
    print(f"  若い世代: {len(youth_matches)}試合")

    new_matches = sort_matches(
        dedupe_matches(a_matches + nadeshiko_matches + youth_matches)
    )

    new_broadcasts = detect_new_broadcasts(old_matches, new_matches)

    save_matches(new_matches)
    print(f"{OUTPUT_FILE} を更新しました（{len(new_matches)}試合）")
    print_new_broadcasts(new_broadcasts)
    return new_broadcasts


if __name__ == "__main__":
    main()
