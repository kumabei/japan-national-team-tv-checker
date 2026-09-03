import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper import (
    normalize_broadcaster,
    classify_broadcaster,
    parse_date_time,
    parse_schedule_card,
    parse_broadcast_text,
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
