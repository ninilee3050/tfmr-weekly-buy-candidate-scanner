from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    SCAN_EVENT_DISPLAY_COLUMNS,
    SCAN_FAILURE_COLUMNS,
    TRADE_HISTORY_COLUMN_BOUNDS,
    TRADE_HISTORY_DISPLAY_COLUMNS,
)
from gui.formatting import (
    _format_value,
    active_scenario_tag,
    dashboard_summary,
    history_case_tag,
    scan_event_tag,
    scanner_table_for_display,
    trade_cases_for_display,
    trade_summary_cards,
)
from gui.scan_results import (
    build_closed_scenario_history,
    prioritize_active_scenarios,
    prioritize_scan_events,
    trade_case_position,
    trade_history_display,
)
from gui.storage import load_closed_scenarios, save_closed_scenarios
from gui.tables import _column_width, _distributed_column_widths, _table_required_width
from market_cap_provider import MarketCapCompany
from scanner import scan_trade_cases
from test_scanner import _case_frame, _week


def sold_and_held_cases() -> pd.DataFrame:
    """Two cases of one ticker: sold at +0.68%, then a new one still held."""
    cases, _buys, _full = scan_trade_cases(_two_case_frame())
    return cases


def _two_case_frame() -> pd.DataFrame:
    from test_scanner import _frame, _row

    return _frame(
        [
            _row(close=99, ma20=100, ma50=101),
            _row(open_=104, close=105, ma20=102, ma50=101),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
            _row(open_=97, close=98, ma5=97, ma20=98, ma50=100),
            _row(open_=103, close=104, ma5=103, ma20=101, ma50=100),
            _row(open_=96, close=94, ma5=97, ma20=100, ma50=99),
        ]
    )


def test_table_panel_widths_cover_every_visible_column() -> None:
    for columns, bounds in (
        (TRADE_HISTORY_DISPLAY_COLUMNS, TRADE_HISTORY_COLUMN_BOUNDS),
        (SCAN_EVENT_DISPLAY_COLUMNS, None),
        (ACTIVE_SCENARIO_DISPLAY_COLUMNS, None),
        (CLOSED_RESULT_DISPLAY_COLUMNS, None),
        (CLOSED_SCENARIO_DISPLAY_COLUMNS, None),
        (SCAN_FAILURE_COLUMNS, None),
    ):
        limits = bounds or {}
        expected = sum(
            limits.get(column, (0, _column_width(column)))[1] for column in columns
        )
        assert _table_required_width(columns, bounds) == expected + 42


def test_trade_cases_are_shown_with_korean_columns_and_units() -> None:
    display = trade_cases_for_display(sold_and_held_cases())

    assert list(display.columns) == TRADE_HISTORY_DISPLAY_COLUMNS
    assert list(display["결과"]) == ["매도 완료", "보유 중"]
    sold = display.iloc[0]
    assert _format_value(sold["1차매수일"], "1차매수일") == "2024-01-15"
    assert _format_value(sold["매수차수"], "매수차수") == "1차"
    assert _format_value(sold["눌림회차"], "눌림회차") == "1회차"
    assert _format_value(0, "눌림회차") == ""
    assert _format_value(sold["평단가"], "평단가") == "94.00"
    assert _format_value(sold["수익률"], "수익률") == "+4.26%"
    assert _format_value(sold["보유주수"], "보유주수") == "1주"
    assert _format_value(display.iloc[1]["매도일"], "매도일") == ""


def test_prices_use_thousands_separators_and_ranks_use_labels() -> None:
    assert _format_value(1698.3, "가격") == "1,698.30"
    assert _format_value(73.7976, "다음추가매수가") == "73.80"
    assert _format_value(-1.3738, "평가손익률") == "-1.37%"
    assert _format_value(8, "현재 시총순위") == "8위"
    assert _format_value(9000, "현재 시총순위") == "관심"
    assert _format_value(float("nan"), "수익률") == ""


def test_trade_history_adds_the_market_state_of_the_sell_week() -> None:
    weeks = pd.date_range("2023-06-05", periods=40, freq="W-MON")
    sp500 = pd.DataFrame(
        {"Close": [100.0] * 39 + [80.0], "MA_50": [90.0] * 40},
        index=weeks,
    )

    display = trade_history_display(sold_and_held_cases(), sp500)

    assert list(display.columns) == TRADE_HISTORY_DISPLAY_COLUMNS
    # Sold on 2024-01-22 while the index was above its 50-week line; the held
    # case uses the latest week, which is below it.
    assert list(display["S&P500 상태"]) == ["50주선 위", "50주선 아래"]


def test_history_rows_are_coloured_by_realized_return() -> None:
    assert history_case_tag("매도 완료", 6.77) == "history_success_high"
    assert history_case_tag("매도 완료", 5.0) == "history_success_high"
    assert history_case_tag("매도 완료", 1.58) == "history_success_medium"
    assert history_case_tag("매도 완료", 0.0) == "history_flat"
    assert history_case_tag("매도 완료", -2.0) == "history_loss_medium"
    assert history_case_tag("매도 완료", -24.28) == "history_loss_high"
    assert history_case_tag("보유 중", -8.0) == "history_success_pending"
    assert history_case_tag("매도 완료", float("nan")) == ""


def test_summary_cards_count_only_sold_cases() -> None:
    cards = trade_summary_cards(sold_and_held_cases())

    assert cards["closed"] == ("1건", "보유 중 1건")
    assert cards["win"] == ("100.0%", "1건 중 1건 수익")
    assert cards["average"] == ("+4.26%", "평균 1.0주 보유")
    assert trade_summary_cards(None)["closed"] == ("-", "")
    empty = sold_and_held_cases().iloc[0:0]
    assert trade_summary_cards(empty)["win"] == ("미산출", "매도 완료 없음")


def test_trade_case_position_matches_the_first_buy_date() -> None:
    cases = sold_and_held_cases()

    assert trade_case_position(cases, cases.iloc[0]) == 0
    assert trade_case_position(cases, cases.iloc[1]) == 1
    assert trade_case_position(cases, pd.Series({"FirstBuyDate": _week(5)})) == 1
    assert trade_case_position(cases, pd.Series({"FirstBuyDate": _week(3)})) is None
    assert trade_case_position(cases, None) is None
    assert trade_case_position(cases.iloc[0:0], cases.iloc[0]) is None


def test_chart_history_navigation_moves_one_case_and_stops_at_edges() -> None:
    from app import BuyPointApp

    cases = sold_and_held_cases()
    shown: list[pd.Timestamp] = []
    window = SimpleNamespace(
        current_trade_cases=cases,
        chart_window=SimpleNamespace(cycle=cases.iloc[1]),
        _chart_is_open=lambda: True,
        _show_chart=lambda case: shown.append(case["FirstBuyDate"]),
    )

    BuyPointApp._navigate_chart_history(window, 1)
    BuyPointApp._navigate_chart_history(window, -1)

    assert shown == [_week(2)]


def test_scan_events_put_sells_first_then_add_on_buys_then_first_buys() -> None:
    events = pd.DataFrame(
        [
            {"순위": 1, "티커": "FIRST", "단계": "1차 매수", "신호일": pd.Timestamp("2026-10-05")},
            {"순위": 9, "티커": "SELL", "단계": "매도", "신호일": pd.Timestamp("2026-10-05")},
            {"순위": 5, "티커": "ADD", "단계": "추가매수", "신호일": pd.Timestamp("2026-10-05")},
            {"순위": 2, "티커": "OLDSELL", "단계": "매도", "신호일": pd.Timestamp("2026-09-28")},
        ]
    )

    ordered = prioritize_scan_events(events)

    assert list(ordered["티커"]) == ["SELL", "OLDSELL", "ADD", "FIRST"]
    assert [scan_event_tag(stage) for stage in ordered["단계"]] == [
        "signal_third",
        "signal_third",
        "signal_second",
        "signal_first",
    ]
    assert list(events["티커"])[0] == "FIRST"  # the input is left unchanged


def test_held_cases_put_pending_sells_first_then_the_most_bought() -> None:
    active = pd.DataFrame(
        [
            {"순위": 3, "티커": "ONE", "현재상태": "보유 중", "매수차수": 1},
            {"순위": 50, "티커": "THREE", "현재상태": "보유 중", "매수차수": 3},
            {"순위": 70, "티커": "SELL", "현재상태": "매도 신호 · 잠정", "매수차수": 1},
            {"순위": 1, "티커": "TOP", "현재상태": "보유 중", "매수차수": 1},
        ]
    )

    ordered = prioritize_active_scenarios(active)

    assert list(ordered["티커"]) == ["SELL", "THREE", "TOP", "ONE"]
    assert [
        active_scenario_tag(row["현재상태"], row["매수차수"])
        for _, row in ordered.iterrows()
    ] == ["signal_third", "signal_second", "signal_first", "signal_first"]
    assert active_scenario_tag("보유 중", float("nan")) == ""


def test_scanner_tables_show_only_their_display_columns() -> None:
    active = pd.DataFrame(
        [{"순위": 16, "티커": "JPM", "시가총액": "885.15B", "보유수량": 1, "평단가": 332.38}]
    )

    display = scanner_table_for_display(active, ACTIVE_SCENARIO_DISPLAY_COLUMNS)

    assert list(display.columns) == ACTIVE_SCENARIO_DISPLAY_COLUMNS
    assert display.loc[0, "현재 시총순위"] == 16
    assert "보유수량" in active.columns and "현재 시총순위" not in active.columns


def test_dashboard_counts_this_scans_signals_and_held_cases() -> None:
    events = pd.DataFrame({"단계": ["매도", "추가매수", "추가매수"]})
    active = pd.DataFrame({"현재상태": ["보유 중", "매도 신호 · 잠정", "보유 중"]})

    summary = dashboard_summary(events, active, has_scan_results=True)

    assert summary["first"][0] == "0건" and summary["first"][2] is False
    assert summary["add"][0] == "2건" and summary["add"][2] is True
    assert summary["sell"][0] == "1건" and summary["sell"][2] is True
    assert summary["holding"] == ("3건", "매도 신호 잠정 1건", False)


def test_dashboard_before_any_scan_still_shows_saved_held_cases() -> None:
    active = pd.DataFrame({"현재상태": ["보유 중"]})

    summary = dashboard_summary(pd.DataFrame(), active, has_scan_results=False)

    assert summary["sell"] == ("스캔 전", "통합 스캔 후 표시됩니다", False)
    assert summary["holding"] == ("1건", "매도 신호 대기 중", False)


def test_closed_scenario_history_collects_sold_cases_of_the_top100_newest_first() -> None:
    companies = [
        MarketCapCompany(1, "AAA", "Alpha Inc.", "1.00T"),
        MarketCapCompany(2, "BBB", "Beta Inc.", "900.00B"),
    ]
    later = _case_frame([(105, 100), (96, 98)], ma5=97, ma20=120)
    later.index = later.index + pd.Timedelta(weeks=10)
    cases_by_ticker = {
        "AAA": sold_and_held_cases(),
        "BBB": scan_trade_cases(later)[0],
        "ZZZ": sold_and_held_cases(),  # not in the Top 100
    }

    history = build_closed_scenario_history(companies, cases_by_ticker)

    assert list(history.columns) == CLOSED_SCENARIO_DISPLAY_COLUMNS
    assert list(history["티커"]) == ["BBB", "AAA"]
    assert list(history["현재 시총순위"]) == [2, 1]
    assert history.loc[1, "1차매수일"] == _week(2)
    assert history.loc[1, "수익률"] == pytest.approx((98 / 94 - 1) * 100)


def test_closed_scenario_history_keeps_saved_rows_of_a_failed_ticker_and_round_trips(
    tmp_path,
) -> None:
    companies = [
        MarketCapCompany(1, "AAA", "Alpha Inc.", "1.00T"),
        MarketCapCompany(2, "BBB", "Beta Inc.", "900.00B"),
    ]
    previous = build_closed_scenario_history(
        companies, {"AAA": sold_and_held_cases(), "BBB": sold_and_held_cases()}
    )

    history = build_closed_scenario_history(
        companies,
        {"AAA": sold_and_held_cases()},
        previous=previous,
        failed_tickers={"BBB"},
    )
    path = save_closed_scenarios(history, tmp_path / "closed.csv")
    loaded = load_closed_scenarios(path)

    assert sorted(history["티커"]) == ["AAA", "BBB"]
    assert list(loaded.columns) == CLOSED_SCENARIO_DISPLAY_COLUMNS
    assert loaded.loc[0, "매도일"] == _week(3)
    assert loaded.loc[0, "수익률"] == pytest.approx((98 / 94 - 1) * 100)
    assert loaded.loc[0, "S&P500 상태"] == "확인불가"


def test_spare_table_width_is_distributed_without_squeezing_columns() -> None:
    preferred = {"회사명": 160, "결과": 130, "수익률": 105}
    distributed = _distributed_column_widths(preferred, 600)

    assert sum(distributed.values()) == 600
    assert distributed["회사명"] > preferred["회사명"]
    assert distributed["결과"] > preferred["결과"]
    assert distributed["수익률"] > preferred["수익률"]
    assert _distributed_column_widths(preferred, 300) == preferred


def test_ticker_clicked_during_search_is_queued() -> None:
    from app import BuyPointApp

    state = _search_state("msft", busy_request=True)

    assert BuyPointApp._take_queued_search(state, "AAPL") is True
    assert state.search_requested_while_busy is False


def test_same_ticker_clicked_during_search_is_not_rerun() -> None:
    from app import BuyPointApp

    assert BuyPointApp._take_queued_search(_search_state("AAPL", True), "aapl") is False
    assert BuyPointApp._take_queued_search(_search_state("MSFT", False), "AAPL") is False


def test_history_rows_are_newest_first_and_map_back_to_cases() -> None:
    from app import BuyPointApp

    rows = ["row_newest", "row_middle", "row_oldest"]
    selected = []
    window = SimpleNamespace(
        buy_tree=SimpleNamespace(
            get_children=lambda: rows,
            index=rows.index,
            selection_set=selected.append,
            focus=lambda item: None,
            see=lambda item: None,
        ),
        _syncing_chart_history_selection=False,
    )
    window._history_case_position = lambda item: BuyPointApp._history_case_position(window, item)

    assert BuyPointApp._history_case_position(window, "row_newest") == 2
    assert BuyPointApp._history_case_position(window, "row_oldest") == 0
    BuyPointApp._select_history_position(window, 0)
    assert selected == ["row_oldest"]


def test_window_fits_small_screens_and_keeps_full_size_on_wide_ones() -> None:
    from gui.tables import fit_window_to_screen

    assert fit_window_to_screen(3501, 820, 5120, 1440) == (3501, 820)
    assert fit_window_to_screen(3501, 820, 1920, 1080) == (1880, 820)
    assert fit_window_to_screen(3501, 820, 1366, 768) == (1326, 688)
    assert fit_window_to_screen(3501, 820, 800, 600) == (960, 600)


def test_default_dividers_split_by_content_width() -> None:
    from gui.tables import default_sash_positions

    assert default_sash_positions(1800, False, 490, 1000, 1500) == [720]
    top100_open = default_sash_positions(1300, True, 490, 1000, 1500)
    assert top100_open[0] == 286  # Top 100 takes at most ~22% on small screens
    assert top100_open[1] == 286 + int((1300 - 286) * 0.4)
    assert default_sash_positions(3450, True, 490, 1000, 1500)[0] == 490


def test_cards_wrap_to_two_rows_only_when_narrow() -> None:
    from gui.tables import card_grid_columns

    assert card_grid_columns(900, 4, 170) == 4
    assert card_grid_columns(600, 4, 170) == 2
    assert card_grid_columns(100, 2, 170) == 2


def test_table_cells_sort_by_number_date_or_text() -> None:
    from gui.tables import sorted_row_order, table_sort_key

    assert table_sort_key("61.0% (3/4)") == (0, 61.0)
    assert table_sort_key("+12.35%") == (0, 12.35)
    assert table_sort_key("-2.19%p") == (0, -2.19)
    assert table_sort_key("5.59T") == (0, 5.59e12)
    assert table_sort_key("396.49B") == (0, 396.49e9)
    assert table_sort_key("1,177") == (0, 1177.0)
    assert table_sort_key("2026-08-17") == (1, "2026-08-17")
    assert table_sort_key("3차 신호 대기") == (1, "3차 신호 대기")
    assert table_sort_key("해당 없음") is None
    assert table_sort_key("미산출 (0건)") is None

    rates = ["36.4% (4/11)", "해당 없음", "100.0% (4/4)", "", "63.6% (7/11)"]
    assert sorted_row_order(rates, descending=True) == [2, 4, 0, 1, 3]
    assert sorted_row_order(rates, descending=False) == [0, 4, 2, 1, 3]
    assert sorted_row_order(["BAC", "aapl", "MSFT"], descending=False) == [1, 0, 2]


def test_last_scan_tables_round_trip(tmp_path) -> None:
    from gui.storage import load_last_scan, save_last_scan

    paths = {name: tmp_path / f"{name}.csv" for name in ("events", "closed_results", "failures")}
    info = tmp_path / "last_scan.json"
    events = pd.DataFrame(
        [{"티커": "NVDA", "단계": "매도", "결과": "매도 완료", "신호일": pd.Timestamp("2026-09-28")}]
    )
    empty = pd.DataFrame(columns=["티커", "오류"])

    assert load_last_scan(paths, info) is None
    save_last_scan(events, empty, empty, pd.Timestamp("2026-10-06 22:40:05"), paths, info)
    restored_events, closed, failures, scanned_at = load_last_scan(paths, info)

    assert restored_events.loc[0, "결과"] == "매도 완료"
    assert restored_events.loc[0, "신호일"] == pd.Timestamp("2026-09-28")
    assert closed.empty and failures.empty
    assert scanned_at == pd.Timestamp("2026-10-06 22:40:05")


def test_text_starting_with_a_digit_is_not_sorted_as_a_number() -> None:
    from gui.tables import table_sort_key

    assert table_sort_key("3M Company") == (1, "3m company")
    assert table_sort_key("2차 이격 과다 폐기") == (1, "2차 이격 과다 폐기")
    assert table_sort_key("3개월") == (0, 3.0)
    assert table_sort_key("82.5점") == (0, 82.5)
    assert table_sort_key("10건") == (0, 10.0)


def test_saved_window_placement_is_restored_and_kept_on_screen() -> None:
    from gui.tables import restored_window_placement

    saved = {"width": 2400, "height": 900, "x": 300, "y": 120}

    assert restored_window_placement(saved, 3501, 820, 5120, 1440) == (2400, 900, 300, 120)
    # The same settings file opened on a small laptop.
    assert restored_window_placement(saved, 3501, 820, 1366, 768) == (1326, 688, 40, 80)
    # No or broken saved state: default size, centered.
    assert restored_window_placement(None, 3501, 820, 5120, 1440) == (3501, 820, 809, 206)
    assert restored_window_placement({"width": "x"}, 1000, 700, 1920, 1080) == (
        1000,
        700,
        460,
        126,
    )


def test_saved_dividers_scale_with_the_window_or_are_dropped() -> None:
    from gui.tables import scaled_sash_positions

    assert scaled_sash_positions([400, 1200], 2000, 2000, 2) == [400, 1200]
    assert scaled_sash_positions([400, 1200], 2000, 1000, 2) == [200, 600]
    assert scaled_sash_positions([400, 1200], 2000, 1000, 1) is None  # Top 100 folded now
    assert scaled_sash_positions(None, None, 1000, 1) is None
    assert scaled_sash_positions([1200, 400], 2000, 2000, 2) is None


def test_settings_updates_keep_other_values(tmp_path) -> None:
    from ui_theme import load_settings, load_theme, save_theme, update_settings

    path = tmp_path / "ui_settings.json"
    update_settings(path, window={"width": 1200, "tab": 3})
    save_theme(path, "dark")

    assert load_theme(path) == "dark"
    assert load_settings(path)["window"] == {"width": 1200, "tab": 3}


def test_every_table_column_has_a_hover_explanation() -> None:
    import gui.config as config
    from gui.tooltips import TERM_DESCRIPTIONS
    from gui.watchlist_tab import WATCHLIST_DISPLAY_COLUMNS

    column_lists = [
        config.TRADE_HISTORY_DISPLAY_COLUMNS,
        config.SCAN_EVENT_DISPLAY_COLUMNS,
        config.ACTIVE_SCENARIO_DISPLAY_COLUMNS,
        config.CLOSED_RESULT_DISPLAY_COLUMNS,
        config.CLOSED_SCENARIO_DISPLAY_COLUMNS,
        config.SCAN_FAILURE_COLUMNS,
        WATCHLIST_DISPLAY_COLUMNS,
    ]
    columns = {column for columns in column_lists for column in columns}

    assert columns - set(TERM_DESCRIPTIONS) == set()


def test_heading_explanation_ignores_the_sort_marker() -> None:
    from gui.tooltips import TERM_DESCRIPTIONS, term_description

    assert term_description("수익률 ▼") == TERM_DESCRIPTIONS["수익률"]
    assert term_description("다음추가매수가 ▲") == TERM_DESCRIPTIONS["다음추가매수가"]
    assert term_description("없는 컬럼") == ""


def test_hover_explanation_waits_and_is_cancelled_when_the_pointer_leaves() -> None:
    from gui.tooltips import HOVER_DELAY_MS, HoverTooltip

    scheduled, cancelled = [], []
    owner = SimpleNamespace(
        after=lambda delay, *args: scheduled.append((delay, args)) or f"job{len(scheduled)}",
        after_cancel=cancelled.append,
    )
    tooltip = HoverTooltip(owner, "Arial")

    tooltip.schedule("heading", "설명", 10, 20)
    tooltip.schedule("heading", "설명", 11, 21)  # still on the same heading

    assert [delay for delay, _args in scheduled] == [HOVER_DELAY_MS]
    tooltip.cancel()
    assert cancelled == ["job1"]
    tooltip.schedule("other", "", 0, 0)  # nothing to explain
    assert len(scheduled) == 1


def _search_state(requested: str, busy_request: bool) -> SimpleNamespace:
    return SimpleNamespace(
        search_requested_while_busy=busy_request,
        ticker_var=SimpleNamespace(get=lambda: requested),
    )


