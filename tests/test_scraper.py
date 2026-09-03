import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bs4 import BeautifulSoup
from scraper import (
    normalize_broadcaster,
    classify_broadcaster,
    parse_date_time,
    parse_schedule_card,
    parse_broadcast_text,
    parse_schedule_table,
    parse_broadcast_table,
    merge_matches,
    detect_new_broadcasts,
    utc_iso_to_jst,
    parse_next_data_matches,
    convert_team_match,
    sort_matches,
)


def test_normalize_broadcaster_maps_known_names():
    assert normalize_broadcaster("フジテレビ系列") == "フジテレビ"
    assert normalize_broadcaster("NHK BSP4K") == "NHK BS"
    assert normalize_broadcaster("日テレ系") == "日テレ"


def test_normalize_broadcaster_passes_through_unknown_names():
    assert normalize_broadcaster("謎の局") == "謎の局"


def test_classify_broadcaster():
    assert classify_broadcaster("NHK") == "onair"
    assert classify_broadcaster("NHK BS") == "bs"
    assert classify_broadcaster("DAZN") == "net"
    assert classify_broadcaster("謎の局") == "onair"


def test_parse_date_time_with_time():
    assert parse_date_time("6/30(火) 2:00") == ("6/30", "02:00")
    assert parse_date_time("9/24(木) 19:35") == ("9/24", "19:35")


def test_parse_date_time_returns_none_when_undetermined():
    assert parse_date_time("9/24(木) 未定") is None
    assert parse_date_time("未定") is None


def test_parse_schedule_card_with_score():
    result = parse_schedule_card("ブラジル 2-1 日本")
    assert result == {"team1": "ブラジル", "score1": 2, "score2": 1, "team2": "日本"}


def test_parse_schedule_card_with_undetermined_opponent():
    result = parse_schedule_card("日本 - 未定")
    assert result == {"team1": "日本", "team2": "未定"}


def test_parse_schedule_card_with_vs():
    result = parse_schedule_card("ブラジル vs 日本")
    assert result == {"team1": "ブラジル", "team2": "日本"}


def test_parse_broadcast_text_splits_tv_and_net():
    text = "【テレビ】 フジテレビ系列(0:50～) NHK BS(1:10~) NHK BSP4K(21:00~) 【ネット】 DAZN(1:00~)"
    result = parse_broadcast_text(text)
    assert result == ["フジテレビ", "NHK BS", "DAZN"]


def test_parse_broadcast_text_dedupes():
    text = "【テレビ】 NHK BS(1:00~) NHK BSP4K(2:00~)"
    assert parse_broadcast_text(text) == ["NHK BS"]


SCHEDULE_HTML = """
<table>
  <tr><th>試合日</th><th>大会</th><th>対戦カード</th><th>会場</th></tr>
  <tr><td>6/30(火) 2:00</td><td>FIFAワールドカップ2026 ラウンド32</td>
      <td>ブラジル 2-1 日本</td><td>ヒューストン・スタジアム （アメリカ）</td></tr>
  <tr><td>9/24(木) 19:35</td><td>キリンチャレンジカップ2026</td>
      <td>日本 - パラグアイ</td><td>キューアンドエースタジアム （宮城）</td></tr>
  <tr><td>10/1(木) 未定</td><td>キリンカップサッカー2026</td>
      <td>日本 - 未定</td><td>横浜国際総合競技場 （神奈川）</td></tr>
</table>
"""

BROADCAST_HTML = """
<table>
  <tr><th>試合日</th><th>対戦カード</th><th>放送・配信予定</th></tr>
  <tr><td>6/30(火) 2:00</td><td>ブラジル vs 日本</td>
      <td>【テレビ】 フジテレビ系列(0:50～) NHK BS(1:10~) 【ネット】 DAZN(1:00~)</td></tr>
</table>
"""


def test_parse_schedule_table_extracts_rows_and_skips_undetermined_date():
    soup = BeautifulSoup(SCHEDULE_HTML, "html.parser")
    rows = parse_schedule_table(soup)
    assert len(rows) == 2  # 日程未定の1行はスキップされる
    assert rows[0]["date"] == "6/30"
    assert rows[0]["time"] == "02:00"
    assert rows[0]["stage"] == "FIFAワールドカップ2026 ラウンド32"
    assert rows[0]["team1"] == "ブラジル"
    assert rows[0]["team2"] == "日本"
    assert rows[0]["score1"] == 2
    assert rows[1]["team2"] == "パラグアイ"


def test_parse_broadcast_table_keys_by_date_time():
    soup = BeautifulSoup(BROADCAST_HTML, "html.parser")
    result = parse_broadcast_table(soup)
    assert result[("6/30", "02:00")] == ["フジテレビ", "NHK BS", "DAZN"]


def test_merge_matches_attaches_broadcasters_and_classifies():
    schedule = [{"date": "6/30", "time": "02:00", "stage": "S",
                 "team1": "ブラジル", "team2": "日本", "score1": 2, "score2": 1}]
    broadcasts = {("6/30", "02:00"): ["フジテレビ", "NHK BS", "DAZN"]}
    merged = merge_matches(schedule, broadcasts)
    assert len(merged) == 1
    m = merged[0]
    assert m["tv_onair"] == ["フジテレビ"]
    assert m["tv_bs"] == ["NHK BS"]
    assert m["tv_net"] == ["DAZN"]
    assert m["is_japan"] is True
    assert m["score"] == {"home": 2, "away": 1}


def test_merge_matches_passes_through_year_when_present():
    schedule = [{"date": "1/11", "time": "23:00", "year": 2027, "stage": "S",
                 "team1": "日本", "team2": "インドネシア"}]
    merged = merge_matches(schedule, {})
    assert merged[0]["year"] == 2027


def test_merge_matches_without_broadcast_has_empty_lists():
    schedule = [{"date": "9/24", "time": "19:35", "stage": "S",
                 "team1": "日本", "team2": "パラグアイ"}]
    merged = merge_matches(schedule, {})
    m = merged[0]
    assert m["tv_onair"] == [] and m["tv_bs"] == [] and m["tv_net"] == []
    assert m["score"] is None


def _match(date, time, team2, tv_onair=None, tv_bs=None, tv_net=None):
    return {
        "date": date, "time": time, "stage": "S", "team1": "日本", "team2": team2,
        "tv_onair": tv_onair or [], "tv_bs": tv_bs or [], "tv_net": tv_net or [],
        "is_japan": True, "score": None,
    }


def test_detect_new_broadcasts_finds_newly_confirmed_match():
    old = [_match("9/24", "19:35", "パラグアイ")]  # 放送局まだ未確定
    new = [_match("9/24", "19:35", "パラグアイ", tv_onair=["フジテレビ"])]
    result = detect_new_broadcasts(old, new)
    assert len(result) == 1
    assert result[0]["tv_onair"] == ["フジテレビ"]


def test_detect_new_broadcasts_finds_brand_new_match_with_broadcast():
    old = []
    new = [_match("10/1", "19:00", "韓国", tv_onair=["NHK"])]
    result = detect_new_broadcasts(old, new)
    assert len(result) == 1


def test_detect_new_broadcasts_ignores_unchanged_matches():
    old = [_match("9/24", "19:35", "パラグアイ", tv_onair=["フジテレビ"])]
    new = [_match("9/24", "19:35", "パラグアイ", tv_onair=["フジテレビ"])]
    assert detect_new_broadcasts(old, new) == []


def test_detect_new_broadcasts_ignores_matches_still_without_broadcast():
    old = [_match("10/5", "19:00", "未定")]
    new = [_match("10/5", "19:00", "未定")]
    assert detect_new_broadcasts(old, new) == []


def test_utc_iso_to_jst_same_day():
    assert utc_iso_to_jst("2027-01-11T14:00:00.000Z") == ("1/11", "23:00", 2027)


def test_utc_iso_to_jst_crosses_to_next_day():
    assert utc_iso_to_jst("2026-06-25T23:00:00.000Z") == ("6/26", "08:00", 2026)


def test_utc_iso_to_jst_crosses_year_boundary():
    assert utc_iso_to_jst("2026-12-31T16:00:00.000Z") == ("1/1", "01:00", 2027)


NEXT_DATA_HTML = """
<html><body>
<script id="__NEXT_DATA__" type="application/json">
{"props": {"pageProps": {"content": {"matches": [
  {"startDate": "2026-06-25T23:00:00.000Z",
   "competition": {"name": "ワールドカップ"},
   "round": {"name": "グループ F"},
   "teamA": {"name": "日本"}, "teamB": {"name": "スウェーデン"},
   "score": {"teamA": 1, "teamB": 1}, "status": "RESULT"},
  {"startDate": "2027-01-11T14:00:00.000Z",
   "competition": {"name": "AFC アジアカップ"},
   "round": null,
   "teamA": {"name": "日本"}, "teamB": {"name": "インドネシア"},
   "score": null, "status": "FIXTURE"}
]}}}}
</script>
</body></html>
"""


def test_parse_next_data_matches_extracts_raw_list():
    raw = parse_next_data_matches(NEXT_DATA_HTML)
    assert len(raw) == 2
    assert raw[0]["teamA"]["name"] == "日本"


def test_convert_team_match_with_result_and_round():
    raw = {
        "startDate": "2026-06-25T23:00:00.000Z",
        "competition": {"name": "ワールドカップ"},
        "round": {"name": "グループ F"},
        "teamA": {"name": "日本"}, "teamB": {"name": "スウェーデン"},
        "score": {"teamA": 1, "teamB": 1}, "status": "RESULT",
    }
    result = convert_team_match(raw)
    assert result == {
        "date": "6/26", "time": "08:00", "year": 2026, "stage": "ワールドカップ グループ F",
        "team1": "日本", "team2": "スウェーデン", "score1": 1, "score2": 1,
    }


def test_convert_team_match_year_follows_jst_date_across_year_boundary():
    raw = {
        "startDate": "2027-01-11T14:00:00.000Z",
        "competition": {"name": "AFC アジアカップ"}, "round": None,
        "teamA": {"name": "日本"}, "teamB": {"name": "インドネシア"},
        "score": None, "status": "FIXTURE",
    }
    assert convert_team_match(raw)["year"] == 2027


def test_convert_team_match_omits_round_when_same_as_competition():
    raw = {
        "startDate": "2026-03-28T17:00:00.000Z",
        "competition": {"name": "親善試合"},
        "round": {"name": "親善試合"},
        "teamA": {"name": "スコットランド"}, "teamB": {"name": "日本"},
        "score": {"teamA": 1, "teamB": 0}, "status": "RESULT",
    }
    result = convert_team_match(raw)
    assert result["stage"] == "親善試合"


def test_convert_team_match_fixture_without_score_or_round():
    raw = {
        "startDate": "2027-01-11T14:00:00.000Z",
        "competition": {"name": "AFC アジアカップ"},
        "round": None,
        "teamA": {"name": "日本"}, "teamB": {"name": "インドネシア"},
        "score": None, "status": "FIXTURE",
    }
    result = convert_team_match(raw)
    assert result == {
        "date": "1/11", "time": "23:00", "year": 2027, "stage": "AFC アジアカップ",
        "team1": "日本", "team2": "インドネシア",
    }


def _m(date, time, year):
    return {"date": date, "time": time, "year": year, "stage": "S",
            "team1": "日本", "team2": "X", "tv_onair": [], "tv_bs": [], "tv_net": [],
            "is_japan": True, "score": None}


def test_sort_matches_orders_across_year_boundary():
    matches = [_m("1/11", "23:00", 2027), _m("6/26", "08:00", 2026), _m("6/30", "02:00", 2026)]
    result = sort_matches(matches)
    assert [m["date"] for m in result] == ["6/26", "6/30", "1/11"]


def test_sort_matches_orders_within_same_year():
    matches = [_m("9/24", "19:35", 2026), _m("6/26", "08:00", 2026)]
    result = sort_matches(matches)
    assert [m["date"] for m in result] == ["6/26", "9/24"]
