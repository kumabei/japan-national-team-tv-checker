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
    parse_broadcast_tokens,
    infer_year,
    assign_years_sequential,
    is_youth_stage,
    parse_nadeshiko_page,
    parse_youth_list_page,
    dedupe_matches,
    carry_over_finished,
    parse_jfa_results,
    apply_official_results,
    parse_broadcast_any,
    parse_jfa_broadcast_text,
    parse_jfa_schedule_links,
    parse_jfa_about_page,
    fill_broadcasts_from_jfa,
    preserve_known_values,
    find_suspicious_matches,
)
import datetime


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
    # normalize_stage() により "AFC アジアカップ" は "AFCアジアカップ" に寄せられる
    assert result == {
        "date": "1/11", "time": "23:00", "year": 2027, "stage": "AFCアジアカップ",
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


# ---------------- なでしこ・若い世代の追加分 ----------------

def test_parse_broadcast_tokens_splits_space_separated_names():
    assert parse_broadcast_tokens("U-NEXT TBS系列 TVer") == ["U-NEXT", "TBS", "TVer"]


def test_parse_broadcast_tokens_strips_markers_and_parentheses():
    text = "【放送】TBS系列(録画) 【配信】 U-NEXT"
    assert parse_broadcast_tokens(text) == ["TBS", "U-NEXT"]


def test_parse_broadcast_tokens_skips_undetermined():
    assert parse_broadcast_tokens("【放送】未定 【配信】未定") == []


def test_parse_broadcast_tokens_dedupes():
    assert parse_broadcast_tokens("DAZN(無料) DAZN") == ["DAZN"]


def test_classify_new_net_broadcasters():
    assert classify_broadcaster("U-NEXT") == "net"
    assert classify_broadcaster("TVer") == "net"


def test_normalize_broadcaster_handles_nittele_full_name():
    assert normalize_broadcaster("日本テレビ系列") == "日テレ"


TODAY = datetime.date(2026, 9, 23)


def test_infer_year_future_date_is_this_year():
    assert infer_year("10/10", TODAY) == 2026


def test_infer_year_recent_past_is_this_year():
    assert infer_year("9/21", TODAY) == 2026


def test_infer_year_far_past_rolls_over_to_next_year():
    assert infer_year("1/5", TODAY) == 2027


def test_infer_year_across_new_year():
    assert infer_year("1/2", datetime.date(2026, 12, 31)) == 2027
    assert infer_year("12/30", datetime.date(2026, 12, 31)) == 2026


def _entry(date):
    return {"date": date, "time": "19:00", "stage": "S", "team1": "日本", "team2": "X"}


def test_assign_years_sequential_keeps_past_matches_in_current_year():
    entries = [_entry("3/4"), _entry("6/6"), _entry("9/25"), _entry("12/5")]
    assign_years_sequential(entries, TODAY)
    assert [e["year"] for e in entries] == [2026, 2026, 2026, 2026]


def test_assign_years_sequential_rolls_over_at_year_boundary():
    entries = [_entry("12/20"), _entry("1/15"), _entry("3/1")]
    assign_years_sequential(entries, datetime.date(2026, 12, 18))
    assert [e["year"] for e in entries] == [2026, 2027, 2027]


def test_assign_years_sequential_handles_all_past_entries():
    entries = [_entry("3/4"), _entry("6/6")]
    assign_years_sequential(entries, TODAY)
    assert [e["year"] for e in entries] == [2026, 2026]


def test_is_youth_stage_excludes_a_team_competitions():
    assert is_youth_stage("キリンチャレンジカップ2026") is False
    assert is_youth_stage("ワールドカップ アジア最終予選") is False
    assert is_youth_stage("AFCアジアカップ") is False


def test_is_youth_stage_accepts_youth_and_women_competitions():
    assert is_youth_stage("アジア大会男子第3節") is True
    assert is_youth_stage("アジア大会女子準々決勝") is True
    assert is_youth_stage("U-20女子ワールドカップ準決勝") is True
    assert is_youth_stage("U-17ワールドカップ") is True
    assert is_youth_stage("パリオリンピック") is True


NADESHIKO_HTML = """
<table>
  <tr><th>試合日</th><th>大会</th><th>対戦カード</th><th>会場</th></tr>
  <tr><td>3/4(水) 14:00</td><td>AFC女子アジアカップ2026 グループステージ第1節</td>
      <td>日本 2-0 チャイニーズ・タイペイ</td><td>パース （オーストラリア）</td></tr>
  <tr><td>9/25(金) 19:30</td><td>第20回アジア競技大会 準々決勝</td>
      <td>日本 - フィリピン</td><td>エコパスタジアム （静岡）</td></tr>
  <tr><td>11/29(日) 13:55</td><td>MIZUHO BLUE CHALLENGE NADESHIKO 2026</td>
      <td>日本 - ブラジル</td><td>広島</td></tr>
</table>
<table>
  <tr><th>試合日</th><th>対戦カード</th><th>放送・配信</th></tr>
  <tr><td>9/25(金) 19:30</td><td>アジア競技大会 準々決勝 日本 vs フィリピン</td>
      <td>【放送】TBS系列(録画) 【配信】 U-NEXT</td></tr>
  <tr><td>11/29(日) 13:55</td><td>日本 vs ブラジル</td>
      <td>【放送】日本テレビ系列 【配信】TVer</td></tr>
</table>
"""


def test_parse_nadeshiko_page_merges_schedule_and_broadcast():
    soup = BeautifulSoup(NADESHIKO_HTML, "html.parser")
    matches = parse_nadeshiko_page(soup, TODAY)
    assert len(matches) == 3
    assert all(m["team"] == "nadeshiko" for m in matches)
    assert [m["year"] for m in matches] == [2026, 2026, 2026]
    qf = matches[1]
    assert qf["tv_onair"] == ["TBS"]
    assert qf["tv_net"] == ["U-NEXT"]
    brazil = matches[2]
    assert brazil["tv_onair"] == ["日テレ"]
    assert brazil["tv_net"] == ["TVer"]


YOUTH_HTML = """
<h2>9月23日（水・祝）</h2>
<table>
  <tr><th>キックオフ</th><th>対戦カード</th><th>大会名</th><th>配信チャンネル</th></tr>
  <tr><td>17:00</td><td>鹿島 vs 甲府</td><td>天皇杯3回戦</td><td>NHK BS</td></tr>
  <tr><td>19:30</td><td>日本 vs タイ</td><td>アジア大会男子第3節</td><td>U-NEXT TBS系列 TVer</td></tr>
  <tr><td>22:00</td><td>イタリア vs スペイン</td><td>U-20女子ワールドカップ準決勝</td><td>DAZN(無料)</td></tr>
</table>
<h3>この物語を楽しんでいただけましたか？</h3>
<h2>9月24日（木）</h2>
<table>
  <tr><th>キックオフ</th><th>対戦カード</th><th>大会名</th><th>配信チャンネル</th></tr>
  <tr><td>19:05</td><td>日本 vs ウルグアイ</td><td>キリンチャレンジカップ2026</td><td>フジテレビ系列 TVer</td></tr>
  <tr><td>19:30</td><td>日本 vs フィリピン</td><td>アジア大会女子準々決勝</td><td>U-NEXT</td></tr>
</table>
"""


def test_parse_youth_list_page_extracts_only_non_a_team_japan_matches():
    soup = BeautifulSoup(YOUTH_HTML, "html.parser")
    matches = parse_youth_list_page(soup, TODAY)
    assert len(matches) == 2  # Jリーグ・他国同士・A代表(キリン)は除外
    assert all(m["team"] == "youth" for m in matches)
    first = matches[0]
    assert (first["date"], first["time"], first["year"]) == ("9/23", "19:30", 2026)
    assert first["stage"] == "アジア大会男子第3節"
    assert first["team1"] == "日本" and first["team2"] == "タイ"
    assert first["tv_onair"] == ["TBS"]
    assert first["tv_net"] == ["U-NEXT", "TVer"]
    assert matches[1]["stage"] == "アジア大会女子準々決勝"


def test_parse_youth_list_page_ignores_tables_before_any_date_heading():
    html = "<h2>U-NEXT</h2><table><tr><th>キックオフ</th><th>対戦カード</th>" \
           "<th>大会名</th><th>配信</th></tr>" \
           "<tr><td>19:30</td><td>日本 vs タイ</td><td>アジア大会男子</td><td>U-NEXT</td></tr></table>"
    soup = BeautifulSoup(html, "html.parser")
    assert parse_youth_list_page(soup, TODAY) == []


def _team_match(team, date="9/25", time="19:30", year=2026):
    return {"date": date, "time": time, "year": year, "stage": "S",
            "team1": "日本", "team2": "フィリピン", "tv_onair": [], "tv_bs": [],
            "tv_net": [], "is_japan": True, "score": None, "team": team}


def test_dedupe_matches_prefers_higher_priority_team():
    matches = [_team_match("youth"), _team_match("nadeshiko")]
    result = dedupe_matches(matches)
    assert len(result) == 1
    assert result[0]["team"] == "nadeshiko"


def test_dedupe_matches_keeps_different_date_times():
    matches = [_team_match("nadeshiko"), _team_match("youth", time="21:00")]
    assert len(dedupe_matches(matches)) == 2


def test_merge_matches_sets_team_field():
    schedule = [{"date": "9/25", "time": "19:30", "stage": "S",
                 "team1": "日本", "team2": "X"}]
    assert merge_matches(schedule, {})[0]["team"] == "a"
    assert merge_matches(schedule, {}, team="youth")[0]["team"] == "youth"


def test_detect_new_broadcasts_distinguishes_teams():
    old = [dict(_team_match("a"), tv_onair=["NHK"])]
    new = [dict(_team_match("a"), tv_onair=["NHK"]),
           dict(_team_match("youth"), tv_onair=["TBS"])]
    result = detect_new_broadcasts(old, new)
    assert len(result) == 1
    assert result[0]["team"] == "youth"


def _finished_match(year, date, time, team1="日本", team2="タイ", **kw):
    d = {"year": year, "date": date, "time": time, "team1": team1, "team2": team2,
         "tv_onair": [], "tv_bs": [], "tv_net": [], "score": None}
    d.update(kw)
    return d


def test_carry_over_finished_keeps_past_match_dropped_from_source():
    old = [_finished_match(2026, "9/23", "19:30", score={"home": 3, "away": 0})]
    result = carry_over_finished(old, [], today=datetime.date(2026, 9, 26))
    assert result == old


def test_carry_over_finished_skips_match_still_in_new_data_even_if_team_name_differs():
    old = [_finished_match(2024, "3/21", "19:23", team2="朝鮮民主主義人民共和国")]
    new = [_finished_match(2024, "3/21", "19:23", team2="北朝鮮")]
    assert carry_over_finished(old, new, today=datetime.date(2026, 9, 26)) == []


def test_carry_over_finished_does_not_keep_future_match():
    old = [_finished_match(2026, "10/1", "19:10", team2="エクアドル")]
    assert carry_over_finished(old, [], today=datetime.date(2026, 9, 26)) == []


def test_carry_over_finished_skips_entry_without_year():
    old = [{"date": "9/23", "time": "19:30"}]
    assert carry_over_finished(old, [], today=datetime.date(2026, 9, 26)) == []


def test_parse_jfa_results_reads_scores_and_skips_unplayed():
    html = (
        '<table><tr><td class="date poscenter">9/23(水・祝)</td><td class="comp_name">大会</td>'
        '<td class="score poscenter"><a href="#">〇3-0</a></td><td class="team poscenter">タイ</td></tr>'
        '<tr><td class="date poscenter">9/26(土)</td><td class="comp_name">大会</td>'
        '<td class="score poscenter"></td><td class="team poscenter">北朝鮮</td></tr>'
        '<tr><td class="date poscenter">9/28(月)</td><td class="comp_name">大会</td>'
        '<td class="score poscenter">-</td><td class="team poscenter">ベネズエラ</td></tr>'
        '<tr><td class="date poscenter">3/1(日)</td><td class="comp_name">大会</td>'
        '<td class="score poscenter">△1-1(PK4-2)</td><td class="team poscenter">X</td></tr></table>'
    )
    assert parse_jfa_results(BeautifulSoup(html, "html.parser")) == {(9, 23): (3, 0), (3, 1): (1, 1)}


def test_apply_official_results_fills_only_empty_past_scores_and_swaps_when_japan_is_team2():
    today = datetime.date(2026, 9, 26)
    results = {"a": {2026: {(9, 24): (3, 1), (9, 20): (2, 0)}}}
    away_game = _finished_match(2026, "9/24", "19:35", team1="ウルグアイ", team2="日本", team="a")
    home_game = _finished_match(2026, "9/20", "19:00", team="a")
    has_score = _finished_match(2026, "9/20", "20:00", team="a", score={"home": 9, "away": 9})
    future = _finished_match(2026, "9/28", "19:25", team="a")
    apply_official_results([away_game, home_game, has_score, future], results, today=today)
    assert away_game["score"] == {"home": 1, "away": 3}
    assert home_game["score"] == {"home": 2, "away": 0}
    assert has_score["score"] == {"home": 9, "away": 9}
    assert future["score"] is None


def test_parse_broadcast_table_finds_table_by_header_even_when_an_extra_table_is_inserted():
    # 実際に起きた構造: 日程表・アジアカップ日程表・放送表の3つ。位置決め打ちでは2つ目を読んでしまう
    html = (
        "<table><tr><th>試合日</th><th>大会</th><th>対戦カード</th><th>会場</th></tr>"
        "<tr><td>9/24(木) 19:05</td><td>親善試合</td><td>日本 3-1 ウルグアイ</td><td>宮城</td></tr></table>"
        "<table><tr><th>試合日</th><th>大会</th><th>対戦カード</th><th>会場</th></tr>"
        "<tr><td>2027/1/11(月) 時間未定</td><td>アジアカップ</td><td>日本 - インドネシア</td><td>ジェッダ</td></tr></table>"
        "<table><tr><th>試合日</th><th>対戦カード</th><th>放送・配信</th></tr>"
        "<tr><td>9/28(月) 19:25</td><td>日本 - ベネズエラ</td><td>【放送】日本テレビ系列 【配信】TVer・DAZN</td></tr>"
        "<tr><td>10/5(月) 19:30</td><td>日本 - 未定</td><td>【放送】テレビ朝日系列 【配信】TVer・ABEMA・DAZN</td></tr></table>"
    )
    result = parse_broadcast_table(BeautifulSoup(html, "html.parser"))
    assert result[("9/28", "19:25")] == ["日テレ", "TVer", "DAZN"]
    assert result[("10/5", "19:30")] == ["テレビ朝日", "TVer", "ABEMA", "DAZN"]


def test_parse_broadcast_any_reads_both_old_and_new_formats():
    assert parse_broadcast_any("【テレビ】NHK総合(19:00)") == ["NHK"]
    assert parse_broadcast_any("【放送】TBS系列 【配信】TVer") == ["TBS", "TVer"]


def test_parse_jfa_broadcast_text_keeps_only_known_names():
    assert parse_jfa_broadcast_text("日本テレビ系全国ネット生中継／TVerライブ配信／DAZNライブ配信") == ["日テレ", "TVer", "DAZN"]
    assert parse_jfa_broadcast_text("フジテレビ系列全国生中継／TVerライブ配信") == ["フジテレビ", "TVer"]
    assert parse_jfa_broadcast_text("Youtube 「【公式】TBSスポーツ」にて生配信") == []


_JFA_SINGLE = '<div><h5>テレビ放送</h5><p>日本テレビ系全国ネット生中継／TVerライブ配信</p></div>'
_JFA_TOURNAMENT = (
    '<table class="table03"><tr><th>対戦</th><th>キックオフ</th><th>開場</th><th>TV放送・配信</th></tr>'
    '<tr><td>M1</td><td>パナマ代表　対　ニュージーランド代表</td><td>15:10</td><td>13:10</td><td>Youtube「【公式】TBSスポーツ」にて生配信</td></tr>'
    '<tr><td>M2</td><td>SAMURAI BLUE（日本代表） 対　エクアドル代表</td><td>19:10</td><td>TBS系列<br>全国ネット生中継<br>TVerライブ配信</td></tr></table>'
)


def test_parse_jfa_about_page_handles_single_match_and_tournament_table():
    assert parse_jfa_about_page(BeautifulSoup(_JFA_SINGLE, "html.parser")) == ["日テレ", "TVer"]
    assert parse_jfa_about_page(BeautifulSoup(_JFA_TOURNAMENT, "html.parser"), "19:10") == ["TBS", "TVer"]
    assert parse_jfa_about_page(BeautifulSoup(_JFA_TOURNAMENT, "html.parser"), "12:00") == []


def test_parse_jfa_schedule_links_maps_date_to_first_link():
    html = ('<table><tr><td class="date poscenter">9/28(月)</td><td><a href="/samuraiblue/20260928/">大会</a></td></tr>'
            '<tr><td class="date poscenter">10/1(木)</td><td><a href="/samuraiblue/kirincupsoccer_2026/">大会</a></td></tr></table>')
    assert parse_jfa_schedule_links(BeautifulSoup(html, "html.parser")) == {
        (9, 28): "/samuraiblue/20260928/", (10, 1): "/samuraiblue/kirincupsoccer_2026/"}


def test_fill_broadcasts_from_jfa_fills_only_empty_a_matches_and_survives_fetch_errors():
    schedule = ('<table><tr><td class="date">9/28(月)</td><td><a href="/samuraiblue/20260928/">x</a></td></tr>'
                '<tr><td class="date">10/1(木)</td><td><a href="/samuraiblue/kirincupsoccer_2026/">x</a></td></tr></table>')

    def fake_fetch(url):
        if url.endswith("2026.html"):
            return BeautifulSoup(schedule, "html.parser")
        if "20260928" in url:
            return BeautifulSoup(_JFA_SINGLE, "html.parser")
        raise RuntimeError("404")

    empty = _finished_match(2026, "9/28", "19:25", team="a", team2="ベネズエラ")
    has = _finished_match(2026, "9/28", "19:25", team="a", tv_onair=["TBS"])
    failing = _finished_match(2026, "10/1", "19:10", team="a", team2="エクアドル")
    other_team = _finished_match(2026, "9/28", "19:25", team="nadeshiko")
    filled = fill_broadcasts_from_jfa([empty, has, failing, other_team],
                                      today=datetime.date(2026, 9, 26), fetch=fake_fetch)
    assert filled == [empty]
    assert empty["tv_onair"] == ["日テレ"] and empty["tv_net"] == ["TVer"]
    assert has["tv_onair"] == ["TBS"]
    assert failing["tv_onair"] == [] and other_team["tv_onair"] == []


def test_preserve_known_values_restores_lost_broadcast_and_score_but_not_changed_ones():
    old = [_finished_match(2026, "9/24", "19:05", team="a", tv_onair=["フジテレビ"], score={"home": 3, "away": 1})]
    new = [_finished_match(2026, "9/24", "19:05", team="a")]
    restored = preserve_known_values(old, new)
    assert new[0]["tv_onair"] == ["フジテレビ"] and new[0]["score"] == {"home": 3, "away": 1}
    assert len(restored) == 2
    changed = [_finished_match(2026, "9/24", "19:05", team="a", tv_onair=["TBS"])]
    preserve_known_values(old, changed)
    assert changed[0]["tv_onair"] == ["TBS"]  # 放送局が新しく取れている場合は旧値で上書きしない


def test_find_suspicious_matches_flags_near_a_matches_without_broadcast():
    today = datetime.date(2026, 9, 26)
    near = _finished_match(2026, "9/28", "19:25", team="a")
    far = _finished_match(2026, "11/14", "19:15", team="a")
    covered = _finished_match(2026, "9/28", "19:25", team="a", tv_onair=["日テレ"])
    nadeshiko = _finished_match(2026, "9/29", "19:00", team="nadeshiko")
    assert find_suspicious_matches([near, far, covered, nadeshiko], today=today) == [near]
