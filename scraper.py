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
    "日本テレビ系": "日テレ",
    "フジテレビ系": "フジテレビ",
    "TBS系": "TBS",
    "テレビ朝日系": "テレビ朝日",
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
    text = text.replace("・", " ")  # 「TVer・DAZN」のように1語にまとまるのを防ぐ
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


def parse_broadcast_any(text: str) -> list:
    """A代表の放送欄を読む。従来の `【テレビ】局名(時刻)` 形式を先に試し、
    読めなければ現行の `【放送】日本テレビ系列 【配信】TVer・DAZN` 形式を読む。"""
    return parse_broadcast_text(text) or parse_broadcast_tokens(text)


def find_broadcast_table(soup):
    """ヘッダーに「放送」を含む表を探す。無ければ従来どおりの位置決め打ちにする。

    goal.comの記事は、日程表の後ろに別の表（アジアカップ日程など）が挿入されて
    表の順番がずれることがあり、位置決め打ち(tables[1])では別の表を読んで
    放送局が1つも取れなくなっていた。
    """
    tables = soup.find_all("table")
    for table in tables:
        header = table.find("tr")
        if header is None:
            continue
        cells = [c.get_text(" ", strip=True) for c in header.find_all(["td", "th"])]
        if any("放送" in c for c in cells):
            return table
    if not tables:
        return None
    return tables[1] if len(tables) >= 2 else tables[0]


def parse_broadcast_table(soup, text_parser=None) -> dict:
    text_parser = text_parser or parse_broadcast_any
    table = find_broadcast_table(soup)
    if table is None:
        return {}
    rows = table.find_all("tr")
    header = [c.get_text(" ", strip=True) for c in rows[0].find_all(["td", "th"])] if rows else []
    # 放送欄の列は見出しで探す。見つからなければ従来どおり3列目
    col = next((i for i, c in enumerate(header) if "放送" in c), 2)
    result = {}
    for row in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) <= col:
            continue
        date_time = parse_date_time(cells[0])
        if date_time is None:
            continue
        result[date_time] = text_parser(cells[col])
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


def carry_over_finished(old_matches: list, new_matches: list, today=None) -> list:
    """取得元の日程から消えた「終了済みの試合」を、既存データから引き継ぐ。

    終了した試合は日程ページから落ちることがあり、そのままだとmatches.jsonからも
    消えてしまう（9/23の日本×タイが消えた事故）。キーは（年・日付・時刻）で見る。
    チーム名は取得元で表記が変わる（北朝鮮／朝鮮民主主義人民共和国など）ため使わない。
    今日より前の試合だけを引き継ぐ。未来の試合は中止・日程変更で本当に
    消えた可能性があるので、引き継がない。
    """
    today = today or datetime.date.today()
    seen = {(m.get("year"), m["date"], m["time"]) for m in new_matches}
    carried = []
    for m in old_matches:
        year = m.get("year")
        if year is None or (year, m["date"], m["time"]) in seen:
            continue
        month, day = (int(x) for x in m["date"].split("/"))
        try:
            played_on = datetime.date(year, month, day)
        except ValueError:
            continue
        if played_on < today:
            carried.append(m)
    return carried


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


JFA_RESULT_URLS = {
    TEAM_A: "https://www.jfa.jp/samuraiblue/schedule_result/{year}.html",
    TEAM_NADESHIKO: "https://www.jfa.jp/nadeshikojapan/schedule_result/{year}.html",
    TEAM_YOUTH: "https://www.jfa.jp/national_team/u21/schedule_result/{year}.html",
}


def parse_jfa_results(soup) -> dict:
    """JFA公式「スケジュール・結果」ページから {(月, 日): (日本の得点, 相手の得点)} を作る。

    表の行は [日付, 大会, スコア, 対戦相手, 会場, PDF]。スコアは常に日本が先
    （〇3-0／●0-1／△1-1 のように勝敗記号が付く）。未実施の試合はスコアが空か「-」。
    PK戦などが括弧で続く場合は、先頭の90分（延長）スコアだけを取る。
    """
    results = {}
    for row in soup.find_all("tr"):
        date_cell = row.find("td", class_="date")
        score_cell = row.find("td", class_="score")
        if date_cell is None or score_cell is None:
            continue
        dm = re.match(r"^\s*(\d{1,2})/(\d{1,2})", date_cell.get_text(strip=True))
        sm = re.search(r"(\d+)-(\d+)", score_cell.get_text(strip=True))
        if not dm or not sm:
            continue
        results[(int(dm.group(1)), int(dm.group(2)))] = (int(sm.group(1)), int(sm.group(2)))
    return results


def apply_official_results(matches: list, results_by_team: dict, today=None) -> list:
    """スコアが空の過去の試合に、JFA公式の結果を入れる（既にあるスコアは上書きしない）。

    取得元ごとに「同じチームの同じ日」の結果は1つだけなので、日付で突き合わせる。
    対戦相手の名前は取得元で表記が違う（北朝鮮／朝鮮民主主義人民共和国など）ため使わない。
    JFAのスコアは日本が先なので、日本がteam2の試合ではhome/awayを入れ替える。
    results_by_team は {チーム: {年: {(月, 日): (日本, 相手)}}}。
    """
    today = today or datetime.date.today()
    filled = []
    for m in matches:
        if m.get("score") is not None or m.get("year") is None:
            continue
        month, day = (int(x) for x in m["date"].split("/"))
        try:
            if datetime.date(m["year"], month, day) >= today:
                continue
        except ValueError:
            continue
        found = results_by_team.get(m.get("team", TEAM_A), {}).get(m["year"], {}).get((month, day))
        if found is None:
            continue
        japan, opponent = found
        japan_is_home = any(n in m["team1"] for n in JAPAN_NAMES)
        m["score"] = ({"home": japan, "away": opponent} if japan_is_home
                      else {"home": opponent, "away": japan})
        filled.append(m)
    return filled


def fetch_official_results(matches: list, today=None) -> dict:
    """スコアが空の過去試合がある年だけ、JFA公式ページを取得する。失敗しても更新は続ける。"""
    today = today or datetime.date.today()
    years = {m["year"] for m in matches
             if m.get("score") is None and m.get("year") and m["year"] <= today.year}
    results = {}
    for team, url_tmpl in JFA_RESULT_URLS.items():
        for year in years:
            url = url_tmpl.format(year=year)
            try:
                results.setdefault(team, {})[year] = parse_jfa_results(fetch_soup(url))
            except Exception as e:  # ネットワーク・ページ構造の変化で全体を止めない
                print(f"  警告: 公式結果を取得できませんでした（{url}）: {e}")
    return results


JFA_A_SCHEDULE_URL = JFA_RESULT_URLS[TEAM_A]
JFA_BASE = "https://www.jfa.jp"
_JFA_STRIP_RE = re.compile(r"(全国ネット生中継|全国生中継|生中継|ライブ配信)")
_KNOWN_BROADCASTERS = TERRESTRIAL_BROADCASTERS | BS_BROADCASTERS | NET_BROADCASTERS


def parse_jfa_broadcast_text(text: str) -> list:
    """JFAの放送欄（「日本テレビ系全国ネット生中継／TVerライブ配信」など）から局名を取り出す。

    知っている局名だけを採用する。YouTube配信の説明文などを、未知の名前のまま
    地上波として扱ってしまう（classify_broadcasterは未知の名前をonair扱いにする）のを防ぐ。
    """
    broadcasters = []
    for token in re.split(r"[／/\s|]+", text):
        name = normalize_broadcaster(_JFA_STRIP_RE.sub("", token).strip())
        if name in _KNOWN_BROADCASTERS and name not in broadcasters:
            broadcasters.append(name)
    return broadcasters


def parse_jfa_schedule_links(soup) -> dict:
    """JFAのA代表日程ページから {(月, 日): 試合ページのパス} を作る。"""
    links = {}
    for row in soup.find_all("tr"):
        date_cell = row.find("td", class_="date")
        link = row.find("a", href=True)
        if date_cell is None or link is None:
            continue
        dm = re.match(r"^\s*(\d{1,2})/(\d{1,2})", date_cell.get_text(strip=True))
        if dm:
            links.setdefault((int(dm.group(1)), int(dm.group(2))), link["href"])
    return links


def parse_jfa_about_page(soup, time_str: str = None) -> list:
    """試合の「大会概要(about.html)」ページから、日本代表戦の放送局を読む。

    形は2種類ある。(1) 単独試合：見出し「テレビ放送」の直後の段落。
    (2) キリンカップのような複数試合の大会：表(table03)の行。日本代表の行のうち
    キックオフ時刻が一致するものの最後のセルを読む。
    """
    for h in soup.find_all("h5"):
        if h.get_text(strip=True) == "テレビ放送":
            nxt = h.find_next_sibling()
            if nxt is not None:
                return parse_jfa_broadcast_text(nxt.get_text(" ", strip=True))
    for table in soup.find_all("table", class_="table03"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            text = " ".join(cells)
            if not ("SAMURAI BLUE" in text or "日本代表" in text):
                continue
            if time_str and time_str not in cells:
                continue
            return parse_jfa_broadcast_text(cells[-1])
    return []


def fill_broadcasts_from_jfa(matches: list, today=None, fetch=None) -> list:
    """放送局が空のA代表戦に、JFA公式の放送情報を入れる（既にある放送局は上書きしない）。

    goal.comは終了後の試合の放送行を落とすうえ、ページ構造が変わると放送局が
    1つも取れなくなる。JFAは主催者の公式情報なので、第2の取得元として使う。
    失敗しても更新は止めない。
    """
    fetch = fetch or fetch_soup
    today = today or datetime.date.today()
    targets = [m for m in matches
               if m.get("team", TEAM_A) == TEAM_A and m.get("year") == today.year
               and not _has_broadcast(m)]
    if not targets:
        return []
    filled = []
    try:
        links = parse_jfa_schedule_links(fetch(JFA_A_SCHEDULE_URL.format(year=today.year)))
    except Exception as e:
        print(f"  警告: JFAの日程ページを取得できませんでした: {e}")
        return []
    pages = {}  # 同じ大会ページを試合ごとに取り直さないためのキャッシュ（失敗もNoneで記憶）
    for m in targets:
        month, day = (int(x) for x in m["date"].split("/"))
        path = links.get((month, day))
        if not path:
            continue
        url = JFA_BASE + path.rstrip("/") + "/about.html"
        if url not in pages:
            try:
                pages[url] = fetch(url)
            except Exception as e:  # 404（試合ページ未公開・大会ページに概要が無い）など
                print(f"  警告: JFAの試合ページを取得できませんでした（{url}）: {e}")
                pages[url] = None
        if pages[url] is None:
            continue
        names = parse_jfa_about_page(pages[url], m["time"])
        if not names:
            continue
        m["tv_onair"] = [n for n in names if classify_broadcaster(n) == "onair"]
        m["tv_bs"] = [n for n in names if classify_broadcaster(n) == "bs"]
        m["tv_net"] = [n for n in names if classify_broadcaster(n) == "net"]
        filled.append(m)
    return filled


def preserve_known_values(old_matches: list, new_matches: list) -> list:
    """更新で値が悪化した試合に、既存データの値を戻す。

    放送局が「あった→空」、スコアが「あった→空」になる更新は、取得元の不調や
    構造変化による取りこぼしとみなして旧値を保つ。キーは（年・日付・時刻・チーム区分）。
    戻した内容を文字列のリストで返す（警告表示用）。
    """
    old_by_key = {(m.get("year"), m["date"], m["time"], m.get("team", TEAM_A)): m
                  for m in old_matches}
    restored = []
    for m in new_matches:
        old = old_by_key.get((m.get("year"), m["date"], m["time"], m.get("team", TEAM_A)))
        if old is None:
            continue
        if _has_broadcast(old) and not _has_broadcast(m):
            m["tv_onair"], m["tv_bs"], m["tv_net"] = old["tv_onair"], old["tv_bs"], old["tv_net"]
            restored.append(f"{m['date']} {m['team2']}: 放送局")
        if old.get("score") is not None and m.get("score") is None:
            m["score"] = old["score"]
            restored.append(f"{m['date']} {m['team2']}: スコア")
    return restored


def find_suspicious_matches(matches: list, today=None, days: int = 7) -> list:
    """A代表戦で、放送局が空のままの試合（前後 days 日以内）を返す。

    「本当に未定」なのか「取れていない」のかはデータからは区別できないため、
    どちらの可能性もあるものとして人が確認できるよう挙げる。
    """
    today = today or datetime.date.today()
    found = []
    for m in matches:
        if m.get("team", TEAM_A) != TEAM_A or m.get("year") is None or _has_broadcast(m):
            continue
        month, day = (int(x) for x in m["date"].split("/"))
        try:
            delta = (datetime.date(m["year"], month, day) - today).days
        except ValueError:
            continue
        if -3 <= delta <= days:
            found.append(m)
    return found


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
    problems = []  # 要確認の内容。最後にまとめて出す

    print(f"取得中: {TEAM_SCHEDULE_URL}")
    schedule = fetch_team_matches(TEAM_SCHEDULE_URL)
    if not schedule:
        problems.append("A代表の日程を取得できませんでした（取得元の構造変化の可能性）")

    print(f"取得中: {URL}")
    soup = fetch_soup(URL)
    broadcasts = parse_broadcast_table(soup)
    if not broadcasts:
        problems.append("goal.comの放送表から放送局を取得できませんでした（表の構造変化の可能性）")
    a_matches = merge_matches(schedule, broadcasts, team=TEAM_A, old_matches=old_matches)
    print(f"  A代表: {len(a_matches)}試合（放送表 {len(broadcasts)}行）")

    print(f"取得中: {NADESHIKO_URL}")
    nadeshiko_matches = fetch_nadeshiko_matches(old_matches=old_matches)
    print(f"  なでしこジャパン: {len(nadeshiko_matches)}試合")

    print(f"取得中: {YOUTH_LIST_URL}")
    youth_matches = fetch_youth_matches(old_matches=old_matches)
    print(f"  若い世代: {len(youth_matches)}試合")

    fetched = a_matches + nadeshiko_matches + youth_matches
    new_matches = sort_matches(
        dedupe_matches(fetched + carry_over_finished(old_matches, fetched))
    )

    filled = apply_official_results(new_matches, fetch_official_results(new_matches))
    for m in filled:
        print(f"  公式結果を反映: {m['date']} {m['team1']} {m['score']['home']}-{m['score']['away']} {m['team2']}")

    for m in fill_broadcasts_from_jfa(new_matches):
        names = m["tv_onair"] + m["tv_bs"] + m["tv_net"]
        print(f"  JFA公式の放送局を反映: {m['date']} {m['team2']} → {'・'.join(names)}")

    for what in preserve_known_values(old_matches, new_matches):
        print(f"  旧データを保持（今回の取得では欠けていた）: {what}")

    new_broadcasts = detect_new_broadcasts(old_matches, new_matches)

    save_matches(new_matches)
    print(f"{OUTPUT_FILE} を更新しました（{len(new_matches)}試合）")
    print_new_broadcasts(new_broadcasts)

    for m in find_suspicious_matches(new_matches):
        problems.append(f"{m['year']}/{m['date']} {m['team1']} 対 {m['team2']} の放送局が空です"
                        "（本当に未定か、取れていないかを確認）")
    if problems:
        print("\n===== 要確認 =====")
        for pr in problems:
            print(f"  要確認: {pr}")
    main.problems = problems
    return new_broadcasts


if __name__ == "__main__":
    main()
    # 日程・放送表が取れないなど「取得元が壊れている」場合は終了コードで知らせる
    sys.exit(1 if any("取得できませんでした" in p for p in getattr(main, "problems", [])) else 0)
