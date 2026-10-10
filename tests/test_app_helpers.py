from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from app import BuyPointApp
from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    CLOSED_SCENARIO_COLUMN_BOUNDS,
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    FIELD_DISPLAY_COLUMNS,
    RANKING_DISPLAY_COLUMNS,
    SCAN_EVENT_DISPLAY_COLUMNS,
    SCAN_FAILURE_COLUMNS,
    SIGNAL_HISTORY_COLUMN_BOUNDS,
    SIGNAL_HISTORY_DISPLAY_COLUMNS,
)
from gui.formatting import (
    _format_value,
    active_scenario_tag,
    field_performance_for_display,
    history_cycle_tag,
    ranking_for_display,
    scan_event_tag,
    scanner_table_for_display,
    signal_cycles_for_display,
)
from gui.scan_results import (
    add_scan_performance_columns,
    add_sector_column,
    annotate_signal_history_display,
    build_closed_scenario_history,
    filter_closed_scenarios,
    prioritize_active_scenarios,
    prioritize_scan_events,
    signal_cycle_position,
    validate_chart_strength_range,
)
from gui.storage import (
    load_closed_scenarios,
    save_analytics_outputs,
    save_closed_scenarios,
)
from gui.tables import _column_width, _distributed_column_widths, _table_required_width
from market_cap_provider import MarketCapCompany


def test_table_panel_widths_cover_every_visible_column() -> None:
    history_width = _table_required_width(
        SIGNAL_HISTORY_DISPLAY_COLUMNS,
        SIGNAL_HISTORY_COLUMN_BOUNDS,
    )
    scanner_tables = (
        (SCAN_EVENT_DISPLAY_COLUMNS, None),
        (ACTIVE_SCENARIO_DISPLAY_COLUMNS, None),
        (CLOSED_RESULT_DISPLAY_COLUMNS, None),
        (CLOSED_SCENARIO_DISPLAY_COLUMNS, CLOSED_SCENARIO_COLUMN_BOUNDS),
        (FIELD_DISPLAY_COLUMNS, None),
        (RANKING_DISPLAY_COLUMNS, None),
        (SCAN_FAILURE_COLUMNS, None),
    )
    scanner_width = max(
        _table_required_width(columns, bounds)
        for columns, bounds in scanner_tables
    )

    assert history_width == sum(
        bounds[1] for bounds in SIGNAL_HISTORY_COLUMN_BOUNDS.values()
    ) + 42
    assert all(
        scanner_width >= _table_required_width(columns, bounds)
        for columns, bounds in scanner_tables
    )
    assert _column_width("회사명") >= 220
    assert _column_width("결과") >= 200


def test_closed_scenario_balanced_width_keeps_last_return_column_visible() -> None:
    balanced_width = _table_required_width(
        CLOSED_SCENARIO_DISPLAY_COLUMNS,
        CLOSED_SCENARIO_COLUMN_BOUNDS,
    )

    assert list(CLOSED_SCENARIO_COLUMN_BOUNDS) == CLOSED_SCENARIO_DISPLAY_COLUMNS
    assert CLOSED_SCENARIO_COLUMN_BOUNDS["12개월후 수익률"][0] >= 100
    assert balanced_width == sum(
        maximum for _, maximum in CLOSED_SCENARIO_COLUMN_BOUNDS.values()
    ) + 42
    assert balanced_width < _table_required_width(CLOSED_SCENARIO_DISPLAY_COLUMNS)


def test_spare_table_width_is_distributed_without_squeezing_columns() -> None:
    preferred = {"회사명": 160, "결과": 130, "12개월후 수익률": 105}
    distributed = _distributed_column_widths(preferred, 600)

    assert sum(distributed.values()) == 600
    assert distributed["회사명"] > preferred["회사명"]
    assert distributed["결과"] > preferred["결과"]
    assert distributed["12개월후 수익률"] > preferred["12개월후 수익률"]
    assert _distributed_column_widths(preferred, 300) == preferred


def test_closed_scenario_filters_combine_grade_and_score_range() -> None:
    source = pd.DataFrame(
        [
            {"티커": "AAA", "차트 강도": "82.4점", "검토등급": "우선검토"},
            {"티커": "BBB", "차트 강도": "72점", "검토등급": "우선검토"},
            {"티커": "CCC", "차트 강도": "64점", "검토등급": "일반검토"},
            {"티커": "DDD", "차트 강도": "해당 없음", "검토등급": ""},
        ]
    )

    filtered = filter_closed_scenarios(
        source,
        grade_enabled=True,
        grade="우선검토",
        score_enabled=True,
        minimum_score=75,
        maximum_score=90,
    )

    assert filtered["티커"].tolist() == ["AAA"]
    assert source["티커"].tolist() == ["AAA", "BBB", "CCC", "DDD"]


def test_closed_scenario_filters_can_run_independently() -> None:
    source = pd.DataFrame(
        [
            {"티커": "AAA", "차트 강도": "82점", "검토등급": "우선검토"},
            {"티커": "BBB", "차트 강도": "64점", "검토등급": "일반검토"},
            {"티커": "CCC", "차트 강도": "해당 없음", "검토등급": ""},
        ]
    )

    by_score = filter_closed_scenarios(
        source,
        score_enabled=True,
        minimum_score=60,
        maximum_score=70,
    )
    by_not_applicable = filter_closed_scenarios(
        source,
        grade_enabled=True,
        grade="해당 없음",
    )

    assert by_score["티커"].tolist() == ["BBB"]
    assert by_not_applicable["티커"].tolist() == ["CCC"]


def test_chart_strength_range_validation_supports_open_bounds() -> None:
    assert validate_chart_strength_range("70", "100") == (70.0, 100.0)
    assert validate_chart_strength_range("", "85") == (None, 85.0)
    assert validate_chart_strength_range("90", "") == (90.0, None)
    assert validate_chart_strength_range("bad", "100", enabled=False) == (None, None)


def test_chart_strength_range_validation_rejects_invalid_ranges() -> None:
    for minimum, maximum in (("101", ""), ("", "-1"), ("80", "70"), ("x", "90")):
        try:
            validate_chart_strength_range(minimum, maximum)
        except ValueError:
            pass
        else:
            raise AssertionError((minimum, maximum))


def test_signal_cycle_position_matches_the_exact_history_cycle() -> None:
    cycles = pd.DataFrame(
        [
            {
                "FirstSignalDate": pd.Timestamp("2024-01-01"),
                "SecondSignalDate": pd.Timestamp("2024-02-05"),
                "ThirdDecisionDate": pd.Timestamp("2024-02-19"),
                "Outcome": "매수 성공",
            },
            {
                "FirstSignalDate": pd.Timestamp("2025-03-03"),
                "SecondSignalDate": pd.NaT,
                "ThirdDecisionDate": pd.NaT,
                "Outcome": "2차 신호 대기",
            },
        ]
    )

    assert signal_cycle_position(cycles, cycles.iloc[0].copy()) == 0
    assert signal_cycle_position(cycles, cycles.iloc[1].copy()) == 1
    assert signal_cycle_position(cycles, None) is None
    assert signal_cycle_position(pd.DataFrame(), cycles.iloc[0]) is None


def test_selected_ticker_history_uses_scanner_chart_strength_statuses() -> None:
    cycles = pd.DataFrame(
        [
            {
                "FirstSignalDate": pd.Timestamp("2024-01-01"),
                "SecondSignalDate": pd.Timestamp("2024-02-05"),
                "ThirdDecisionDate": pd.Timestamp("2024-02-19"),
                "Outcome": "매수 성공",
            },
            {
                "FirstSignalDate": pd.Timestamp("2025-01-06"),
                "SecondSignalDate": pd.Timestamp("2025-02-03"),
                "ThirdDecisionDate": pd.Timestamp("2025-02-17"),
                "Outcome": "실패",
            },
            {
                "FirstSignalDate": pd.Timestamp("2026-01-05"),
                "SecondSignalDate": pd.NaT,
                "ThirdDecisionDate": pd.NaT,
                "Outcome": "2차 신호 대기",
            },
        ]
    )

    display, details = annotate_signal_history_display(
        "AAA",
        cycles,
        pd.DataFrame(),
        reference=None,
        reference_error="기준자료 오류",
    )

    assert display.columns.tolist() == SIGNAL_HISTORY_DISPLAY_COLUMNS
    assert display.loc[0, "차트 강도"] == "계산 불가"
    assert display.loc[0, "검토등급"] == "확인 필요"
    assert display.loc[1, "차트 강도"] == "해당 없음"
    assert display.loc[2, "차트 강도"] == "산정 대기"
    assert display.loc[2, "검토등급"] == ""
    assert len(details) == 1


def test_signal_cycle_position_rejects_a_different_outcome() -> None:
    cycles = pd.DataFrame(
        [
            {
                "FirstSignalDate": pd.Timestamp("2024-01-01"),
                "SecondSignalDate": pd.NaT,
                "ThirdDecisionDate": pd.NaT,
                "Outcome": "2차 신호 대기",
            }
        ]
    )
    different = cycles.iloc[0].copy()
    different["Outcome"] = "실패"

    assert signal_cycle_position(cycles, different) is None


def test_chart_history_navigation_moves_one_cycle_and_stops_at_edges() -> None:
    cycles = pd.DataFrame(
        [
            {"FirstSignalDate": pd.Timestamp("2024-01-01"), "Outcome": "실패"},
            {"FirstSignalDate": pd.Timestamp("2025-01-06"), "Outcome": "매수 성공"},
            {"FirstSignalDate": pd.Timestamp("2026-01-05"), "Outcome": "2차 신호 대기"},
        ]
    )
    app = object.__new__(BuyPointApp)
    app.current_signal_cycles = cycles
    app.chart_window = SimpleNamespace(cycle=cycles.iloc[1].copy())
    app._chart_is_open = lambda: True
    shown: list[pd.Series] = []
    app._show_chart = shown.append

    BuyPointApp._navigate_chart_history(app, -1)
    BuyPointApp._navigate_chart_history(app, 1)
    assert [row["FirstSignalDate"] for row in shown] == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2026-01-05"),
    ]

    app.chart_window.cycle = cycles.iloc[0].copy()
    shown.clear()
    BuyPointApp._navigate_chart_history(app, -1)
    assert shown == []


def test_chart_preview_strength_summary_tracks_selected_history_cycle() -> None:
    signal_date = pd.Timestamp("2026-07-27")
    cycle = pd.Series(
        {
            "Outcome": "매수 성공",
            "ThirdDecisionDate": signal_date,
        }
    )
    app = object.__new__(BuyPointApp)
    app.current_ticker = "AAA"
    app.chart_strength_details = {
        ("AAA", "2026-07-27"): {
            "score_text": "82.4점",
            "grade": "우선검토",
        }
    }

    assert BuyPointApp._chart_strength_summary(app, cycle) == (
        "차트 강도: 82.4점  |  검토등급: 우선검토"
    )
    assert BuyPointApp._chart_strength_summary(
        app,
        pd.Series({"Outcome": "3차 신호 대기"}),
    ) == "차트 강도: 산정 대기"


def test_select_history_position_selects_focuses_and_scrolls_the_row() -> None:
    class FakeTree:
        def __init__(self) -> None:
            self.selected = None
            self.focused = None
            self.visible = None

        def get_children(self):
            return ("row0", "row1", "row2")

        def selection_set(self, item):
            self.selected = item

        def focus(self, item):
            self.focused = item

        def see(self, item):
            self.visible = item

    app = object.__new__(BuyPointApp)
    app.buy_tree = FakeTree()
    app._syncing_chart_history_selection = False

    BuyPointApp._select_history_position(app, 1)

    assert app.buy_tree.selected == "row1"
    assert app.buy_tree.focused == "row1"
    assert app.buy_tree.visible == "row1"
    assert app._syncing_chart_history_selection is False


def test_closed_scenario_history_collects_current_top100_and_sorts_by_first_signal() -> None:
    companies = [
        MarketCapCompany(1, "AAA", "Alpha", "1T"),
        MarketCapCompany(2, "BBB", "Beta", "900B"),
    ]
    cycles_by_ticker = {
        "AAA": pd.DataFrame(
            [
                {
                    "FirstSignalDate": "2026-01-05",
                    "SecondSignalDate": "2026-01-12",
                    "ThirdDecisionDate": "2026-01-19",
                    "Outcome": "매수 성공",
                    "Return3M": 12.0,
                    "Return3MStatus": "확정",
                },
                {
                    "FirstSignalDate": "2026-07-20",
                    "Outcome": "2차 신호 대기",
                },
            ]
        ),
        "BBB": pd.DataFrame(
            [
                {
                    "FirstSignalDate": "2026-03-02",
                    "SecondSignalDate": "2026-03-09",
                    "ThirdDecisionDate": None,
                    "Outcome": "2차 이격 과다 폐기",
                }
            ]
        ),
        "OLD": pd.DataFrame(
            [{"FirstSignalDate": "2026-06-01", "Outcome": "실패"}]
        ),
    }
    classifications = pd.DataFrame(
        [
            {"티커": "AAA", "섹터": "정보기술"},
            {"티커": "BBB", "섹터": "금융"},
        ]
    )

    history = build_closed_scenario_history(
        companies,
        cycles_by_ticker,
        classifications,
    )

    assert history.columns.tolist() == CLOSED_SCENARIO_DISPLAY_COLUMNS
    assert history["현재 시총순위"].tolist() == [2, 1]
    assert history["티커"].tolist() == ["BBB", "AAA"]
    assert history["섹터"].tolist() == ["금융", "정보기술"]
    assert "2차 신호 대기" not in history["결과"].tolist()
    assert "OLD" not in history["티커"].tolist()


def test_closed_scenario_history_preserves_failed_current_ticker_and_round_trips(
    tmp_path,
) -> None:
    previous = pd.DataFrame(
        [
            {
                "순위": 1,
                "티커": "AAA",
                "회사명": "Alpha",
                "섹터": "정보기술",
                "1차신호일": "2025-01-06",
                "결과": "실패",
            },
            {
                "순위": 3,
                "티커": "OLD",
                "회사명": "Old",
                "섹터": "금융",
                "1차신호일": "2024-01-01",
                "결과": "실패",
            },
        ]
    )
    history = build_closed_scenario_history(
        [MarketCapCompany(1, "AAA", "Alpha", "1T")],
        {},
        pd.DataFrame(),
        previous=previous,
        failed_tickers={"AAA"},
    )

    path = save_closed_scenarios(history, tmp_path / "closed.csv")
    loaded = load_closed_scenarios(path)

    assert loaded["티커"].tolist() == ["AAA"]
    assert loaded.loc[0, "현재 시총순위"] == 1
    assert loaded.loc[0, "1차신호일"] == pd.Timestamp("2025-01-06")


def test_closed_scenario_loader_migrates_legacy_rank_column(tmp_path) -> None:
    path = tmp_path / "legacy_closed.csv"
    pd.DataFrame(
        [{"순위": 7, "티커": "AAA", "1차신호일": "2025-01-06"}]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    loaded = load_closed_scenarios(path)

    assert "순위" not in loaded.columns
    assert loaded.loc[0, "현재 시총순위"] == 7


def test_closed_scenario_loader_restores_mixed_saved_returns_as_numbers(tmp_path) -> None:
    path = tmp_path / "mixed_returns.csv"
    pd.DataFrame(
        [
            {
                "티커": "AAA",
                "1차신호일": "2025-01-06",
                "3개월후 수익률": 12.3456789,
                "6개월후 수익률": "진행 중",
            },
            {
                "티커": "BBB",
                "1차신호일": "2025-02-03",
                "3개월후 수익률": "-4.5%",
                "6개월후 수익률": "해당 없음",
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8-sig")

    loaded = load_closed_scenarios(path)

    assert loaded.loc[0, "3개월후 수익률"] == 12.3456789
    assert _format_value(loaded.loc[0, "3개월후 수익률"], "3개월후 수익률") == (
        "+12.35%"
    )
    assert loaded.loc[0, "6개월후 수익률"] == "진행 중"
    assert loaded.loc[1, "3개월후 수익률"] == -4.5
    assert loaded.loc[1, "6개월후 수익률"] == "해당 없음"


def test_signal_history_displays_progress_and_unavailable_states() -> None:
    cycles = pd.DataFrame(
        [
            {
                "FirstSignalDate": pd.Timestamp("2026-01-05"),
                "SecondSignalDate": pd.Timestamp("2026-01-12"),
                "ThirdDecisionDate": pd.Timestamp("2026-01-19"),
                "Outcome": "매수 성공",
                "Return3M": float("nan"),
                "Return3MStatus": "진행 중",
                "Return6M": 12.345,
                "Return6MStatus": "확정",
                "Return9M": float("nan"),
                "Return9MStatus": "데이터 없음",
                "Return12M": float("nan"),
                "Return12MStatus": "진행 중",
            },
            {
                "Outcome": "실패",
                "Return3M": float("nan"),
                "Return3MStatus": "해당 없음",
                "Return6M": float("nan"),
                "Return6MStatus": "해당 없음",
                "Return9M": float("nan"),
                "Return9MStatus": "해당 없음",
                "Return12M": float("nan"),
                "Return12MStatus": "해당 없음",
            },
        ]
    )

    display = signal_cycles_for_display(cycles)

    assert display.loc[0, "3개월후 수익률"] == "진행 중"
    assert display.loc[0, "6개월후 수익률"] == 12.345
    assert display.loc[0, "9개월후 수익률"] == "데이터 없음"
    assert display.loc[1, "3개월후 수익률"] == "해당 없음"


def test_second_spread_columns_are_readable_and_formatted_as_percent() -> None:
    assert _format_value(14.778206, "MA20_50이격률") == "+14.78%"
    assert _column_width("MA20_50이격률") >= 120
    assert _column_width("결과") >= 150


def test_sector_column_is_inserted_after_ticker_without_changing_source() -> None:
    source = pd.DataFrame([{"순위": 1, "티커": "NVDA", "회사명": "NVIDIA"}])
    classifications = pd.DataFrame(
        [{"티커": "NVDA", "섹터": "정보기술", "산업": "반도체"}]
    )

    display = add_sector_column(source, classifications)

    assert display.columns.tolist() == ["순위", "티커", "섹터", "회사명"]
    assert display.loc[0, "섹터"] == "정보기술"
    assert "섹터" not in source.columns


def test_scanner_display_hides_diagnostic_columns_without_changing_source() -> None:
    source = pd.DataFrame(
        [
            {
                "티커": "NVDA",
                "회사명": "NVIDIA",
                "단계": "2차 신호",
                "Close": 100.0,
                "MA_5": 99.0,
                "MA20_50이격률": 1.2,
            }
        ]
    )
    columns = ["티커", "회사명", "단계", "데이터기준일"]

    display = scanner_table_for_display(source, columns)

    assert display.columns.tolist() == columns
    assert "Close" not in display.columns
    assert "MA_5" not in display.columns
    assert "MA20_50이격률" not in display.columns
    assert "Close" in source.columns


def test_scan_events_prioritize_actionable_third_then_second_then_first() -> None:
    events = pd.DataFrame(
        [
            {"순위": 1, "단계": "1차 신호", "결과": "2차 신호 대기", "신호일": pd.Timestamp("2026-07-20")},
            {"순위": 2, "단계": "2차 신호", "결과": "3차 신호 대기", "신호일": pd.Timestamp("2026-07-20")},
            {"순위": 3, "단계": "3차 신호", "결과": "매수 성공", "신호일": pd.Timestamp("2026-07-13")},
            {"순위": 4, "단계": "3차 신호", "결과": "실패", "신호일": pd.Timestamp("2026-07-20")},
        ]
    )

    sorted_events = prioritize_scan_events(events)

    assert sorted_events[["단계", "결과"]].values.tolist() == [
        ["3차 신호", "매수 성공"],
        ["2차 신호", "3차 신호 대기"],
        ["1차 신호", "2차 신호 대기"],
        ["3차 신호", "실패"],
    ]
    assert scan_event_tag("3차 신호", "매수 성공") == "signal_third"
    assert scan_event_tag("2차 신호", "3차 신호 대기") == "signal_second"
    assert scan_event_tag("1차 신호", "2차 신호 대기") == "signal_first"
    assert scan_event_tag("3차 신호", "실패") == ""


def test_scan_events_order_successful_third_signals_by_chart_strength() -> None:
    events = pd.DataFrame(
        [
            {
                "순위": 1,
                "티커": "LOW",
                "단계": "3차 신호",
                "결과": "매수 성공",
                "신호일": pd.Timestamp("2026-07-27"),
                "차트 강도": "55점",
            },
            {
                "순위": 20,
                "티커": "HIGH",
                "단계": "3차 신호",
                "결과": "매수 성공",
                "신호일": pd.Timestamp("2026-07-20"),
                "차트 강도": "82점",
            },
            {
                "순위": 2,
                "티커": "SECOND",
                "단계": "2차 신호",
                "결과": "3차 신호 대기",
                "신호일": pd.Timestamp("2026-07-27"),
                "차트 강도": "산정 대기",
            },
        ]
    )

    sorted_events = prioritize_scan_events(events)

    assert sorted_events["티커"].tolist() == ["HIGH", "LOW", "SECOND"]


def test_active_scenarios_prioritize_third_waiting_and_use_completed_stage_colors() -> None:
    active = pd.DataFrame(
        [
            {
                "순위": 1,
                "티커": "AAA",
                "현재상태": "2차 신호 대기",
                "1차신호일": "2026-07-20",
                "2차신호일": pd.NaT,
            },
            {
                "순위": 5,
                "티커": "BBB",
                "현재상태": "3차 신호 대기",
                "1차신호일": "2026-07-13",
                "2차신호일": "2026-07-06",
            },
            {
                "순위": 2,
                "티커": "CCC",
                "현재상태": "3차 신호 대기",
                "1차신호일": "2026-06-01",
                "2차신호일": "2026-07-20",
            },
            {
                "순위": 3,
                "티커": "DDD",
                "현재상태": "2차 신호 대기",
                "1차신호일": "2026-06-01",
                "2차신호일": pd.NaT,
            },
        ]
    )

    sorted_active = prioritize_active_scenarios(active)

    assert sorted_active["티커"].tolist() == ["CCC", "BBB", "AAA", "DDD"]
    assert active_scenario_tag("3차 신호 대기") == "signal_second"
    assert active_scenario_tag("2차 신호 대기") == "signal_first"
    assert active_scenario_tag("매수 성공") == ""


def test_history_cycle_colors_use_all_confirmed_return_horizons() -> None:
    assert history_cycle_tag("2차 이격 과다 폐기", "해당 없음") == "history_discard"
    assert history_cycle_tag("실패", "해당 없음") == "history_failure"
    assert history_cycle_tag(
        "매수 성공", "진행 중", "진행 중", "진행 중", "진행 중"
    ) == "history_success_pending"

    assert history_cycle_tag("매수 성공", 5.0, "진행 중", "진행 중", "진행 중") == (
        "history_success_low"
    )
    assert history_cycle_tag("매수 성공", 5.0, 8.0, "진행 중", "진행 중") == (
        "history_success_low"
    )
    assert history_cycle_tag("매수 성공", 5.0, 8.0, 12.0, "진행 중") == (
        "history_success_medium"
    )
    assert history_cycle_tag("매수 성공", 5.0, 8.0, 12.0, 20.0) == (
        "history_success_high"
    )

    assert history_cycle_tag("매수 성공", 5.0, 8.0, 12.0, -2.0) == (
        "history_success_medium"
    )
    assert history_cycle_tag("매수 성공", 5.0, 8.0, -3.0, -6.0) == "history_flat"
    assert history_cycle_tag("매수 성공", 5.0, -2.0, -3.0, -6.0) == (
        "history_loss_low"
    )
    assert history_cycle_tag("매수 성공", -1.0, -2.0, -3.0, "진행 중") == (
        "history_loss_medium"
    )
    assert history_cycle_tag("매수 성공", -1.0, -2.0, -3.0, -4.0) == (
        "history_loss_high"
    )
    assert history_cycle_tag("매수 성공", 0.0, 0.0, 0.0, 0.0) == "history_flat"


def test_scan_events_show_ticker_and_sector_win_rates_with_samples() -> None:
    companies = [
        MarketCapCompany(1, "AAA", "AAA Company", "1.00T"),
        MarketCapCompany(2, "BBB", "BBB Company", "900B"),
    ]
    cycles_by_ticker = {
        "AAA": pd.DataFrame(
            [{"Outcome": "매수 성공", "Return3M": 8.0, "Return3MStatus": "확정"}]
        ),
        "BBB": pd.DataFrame(
            [{"Outcome": "매수 성공", "Return3M": -2.0, "Return3MStatus": "확정"}]
        ),
    }
    classifications = pd.DataFrame(
        [
            {"티커": "AAA", "섹터": "정보기술", "산업": "반도체"},
            {"티커": "BBB", "섹터": "정보기술", "산업": "소프트웨어"},
        ]
    )
    sector_output = pd.DataFrame(
        [
            {
                "분석 기간": "3개월",
                "분야": "정보기술",
                "승률": 50.0,
                "승리": 1,
                "분석 표본": 2,
            }
        ]
    )
    events = pd.DataFrame([{"티커": "AAA", "섹터": "정보기술"}])

    display = add_scan_performance_columns(
        events,
        companies,
        cycles_by_ticker,
        classifications,
        sector_output,
    )

    assert display.loc[0, "종목 3개월 승률"] == "100.0% (1/1)"
    assert display.loc[0, "섹터 3개월 승률"] == "50.0% (1/2)"


def test_field_and_ranking_views_show_denominators_without_hiding_small_samples() -> None:
    field = pd.DataFrame(
        [
            {
                "분야": "정보기술",
                "종목 수": 2,
                "종료 사이클": 5,
                "매수 건수": 3,
                "매수 도달률": 60.0,
                "승리": 1,
                "분석 표본": 1,
                "승률": 100.0,
                "평균 손익률": 10.0,
                "중앙값": 10.0,
            }
        ]
    )
    ranking = pd.DataFrame(
        [
            {
                "순위": 1,
                "티커": "NVDA",
                "회사명": "NVIDIA",
                "종료 사이클": 5,
                "매수 건수": 3,
                "매수 도달률": 60.0,
                "승리": 1,
                "분석 표본": 1,
                "승률": 100.0,
                "평균 손익률": 10.0,
                "중앙값": 10.0,
                "최고": 10.0,
                "최저": 10.0,
                "종합점수": 100.0,
            }
        ]
    )

    field_display = field_performance_for_display(field)
    ranking_display = ranking_for_display(ranking)

    assert field_display.loc[0, "승률"] == "100.0% (1/1)"
    assert field_display.loc[0, "매수 도달률"] == "60.0% (3/5)"
    assert ranking_display.loc[0, "승률"] == "100.0% (1/1)"


def test_analytics_outputs_use_stable_and_dated_names(tmp_path) -> None:
    data = pd.DataFrame([{"분야": "정보기술"}])

    stable = save_analytics_outputs(data, data, data, output_dir=tmp_path)
    dated = save_analytics_outputs(
        data,
        data,
        data,
        output_dir=tmp_path,
        date_suffix="2026-07-26",
    )

    assert [path.name for path in stable] == [
        "mmrm_sector_performance.csv",
        "mmrm_industry_performance.csv",
        "mmrm_field_stock_rankings.csv",
    ]
    assert [path.name for path in dated] == [
        "MMRM_sector_performance_2026-07-26.csv",
        "MMRM_industry_performance_2026-07-26.csv",
        "MMRM_field_stock_rankings_2026-07-26.csv",
    ]
    assert all(path.exists() for path in (*stable, *dated))


def _search_state(requested: str, busy_request: bool) -> SimpleNamespace:
    return SimpleNamespace(
        search_requested_while_busy=busy_request,
        ticker_var=SimpleNamespace(get=lambda: requested),
    )


def test_ticker_clicked_during_search_is_queued() -> None:
    from app import BuyPointApp

    state = _search_state("msft", busy_request=True)

    assert BuyPointApp._take_queued_search(state, "AAPL") is True
    assert state.search_requested_while_busy is False


def test_same_ticker_clicked_during_search_is_not_rerun() -> None:
    from app import BuyPointApp

    assert BuyPointApp._take_queued_search(_search_state("AAPL", True), "aapl") is False
    assert BuyPointApp._take_queued_search(_search_state("MSFT", False), "AAPL") is False


def test_closed_scenarios_load_after_excel_resave(tmp_path) -> None:
    path = tmp_path / "closed_excel.csv"
    pd.DataFrame(
        [{"현재 시총순위": 3, "티커": "AAA", "1차신호일": "2025-01-06", "결과": "매수 성공"}]
    ).to_csv(path, index=False, encoding="cp949")

    loaded = load_closed_scenarios(path)

    assert loaded.loc[0, "결과"] == "매수 성공"


def test_median_max_min_returns_are_shown_as_percentages() -> None:
    assert _format_value(12.3456, "중앙값") == "+12.35%"
    assert _format_value(40.0, "최고") == "+40.00%"
    assert _format_value(-8.5, "최저") == "-8.50%"


def test_signal_validation_view_formats_baselines() -> None:
    from gui.formatting import signal_validation_for_display

    validation = pd.DataFrame(
        [
            {
                "분석 기간": "3개월",
                "구분": "우선검토",
                "분석 표본": 4,
                "승리": 3,
                "승률": 75.0,
                "평소 매수 승률": 56.66,
                "평소 매수 대비 초과": 1.234,
                "S&P 이긴 비율": 50.0,
                "S&P 대비 초과": -0.5,
                "평균 손익률": 4.0,
                "중앙값": 3.0,
                "S&P 비교 표본": 4,
                "S&P 이긴 건수": 2,
                "평소 매수 비교 표본": 4,
            }
        ]
    )

    display = signal_validation_for_display(validation)

    assert display.loc[0, "승률"] == "75.0% (3/4)"
    assert display.loc[0, "평소 매수 승률"] == "56.7%"
    assert display.loc[0, "S&P 이긴 비율"] == "50.0% (2/4)"
    assert _format_value(display.loc[0, "평소 매수 대비 초과"], "평소 매수 대비 초과") == "+1.23%p"
    assert _format_value(display.loc[0, "S&P 대비 초과"], "S&P 대비 초과") == "-0.50%p"


def test_dashboard_before_any_scan_uses_saved_state() -> None:
    from gui.formatting import dashboard_summary

    active = pd.DataFrame({"현재상태": ["3차 신호 대기", "3차 신호 대기", "2차 신호 대기"]})

    summary = dashboard_summary(
        pd.DataFrame(),
        active,
        has_scan_results=False,
        last_scan_date=pd.Timestamp("2026-09-18"),
        today=pd.Timestamp("2026-09-28"),
    )

    assert summary["buy"] == ("스캔 전", "통합 스캔 후 표시됩니다", False)
    assert summary["wait3"][0] == "2건"
    assert summary["wait2"][0] == "1건"
    assert summary["last"] == ("09/18", "10일 전 · 스캔 필요", True)


def test_dashboard_counts_this_scans_buys_and_priority() -> None:
    from gui.formatting import dashboard_summary

    events = pd.DataFrame(
        {
            "단계": ["3차 신호", "3차 신호", "3차 신호", "1차 신호"],
            "결과": ["매수 성공", "매수 성공", "실패", "2차 신호 대기"],
            "검토등급": ["우선검토", "일반검토", "", ""],
        }
    )

    summary = dashboard_summary(
        events,
        pd.DataFrame(),
        has_scan_results=True,
        last_scan_date=pd.Timestamp("2026-09-28"),
        today=pd.Timestamp("2026-09-28"),
    )

    assert summary["buy"] == ("2건", "우선검토 1건", True)
    assert summary["wait3"][0] == "0건"
    assert summary["last"] == ("09/28", "오늘", False)


def test_dashboard_without_scan_history_asks_for_a_scan() -> None:
    from gui.formatting import dashboard_summary

    summary = dashboard_summary(
        pd.DataFrame(), pd.DataFrame(), False, None, pd.Timestamp("2026-09-28")
    )

    assert summary["last"] == ("기록 없음", "통합 스캔을 실행해 주세요", True)


def test_horizon_card_lines_color_the_comparisons() -> None:
    from gui.formatting import horizon_card_lines

    row = pd.Series(
        {"분석 표본": 4, "승리": 3, "승률": 75.0, "평소 매수 대비 초과": 2.5, "S&P 대비 초과": -1.0}
    )

    lines = horizon_card_lines(row)

    assert lines["win"] == ("승률 75.0%", "")
    assert lines["sample"] == ("4건 중 3건 수익", "")
    assert lines["nearby"] == ("평소 매수 대비 +2.50%p", "good")
    assert lines["sp500"] == ("S&P 대비 -1.00%p", "bad")
    assert horizon_card_lines(pd.Series({"분석 표본": 0}))["win"] == ("미산출", "")
    assert horizon_card_lines(None)["win"] == ("-", "")


def test_history_rows_are_newest_first_and_map_back_to_cycles() -> None:
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
    window._history_cycle_position = lambda item: BuyPointApp._history_cycle_position(window, item)

    assert BuyPointApp._history_cycle_position(window, "row_newest") == 2
    assert BuyPointApp._history_cycle_position(window, "row_oldest") == 0
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
        [{"티커": "NVDA", "단계": "3차 신호", "결과": "매수 성공", "신호일": pd.Timestamp("2026-09-28")}]
    )
    empty = pd.DataFrame(columns=["티커", "오류"])

    assert load_last_scan(paths, info) is None
    save_last_scan(events, empty, empty, pd.Timestamp("2026-10-06 22:40:05"), paths, info)
    restored_events, closed, failures, scanned_at = load_last_scan(paths, info)

    assert restored_events.loc[0, "결과"] == "매수 성공"
    assert restored_events.loc[0, "신호일"] == pd.Timestamp("2026-09-28")
    assert closed.empty and failures.empty
    assert scanned_at == pd.Timestamp("2026-10-06 22:40:05")


def test_dashboard_uses_restored_scan_time() -> None:
    from gui.formatting import dashboard_summary

    summary = dashboard_summary(
        pd.DataFrame(columns=["단계", "결과"]),
        pd.DataFrame(),
        has_scan_results=True,
        last_scan_date=None,
        today=pd.Timestamp("2026-10-06"),
        last_scan_time=pd.Timestamp("2026-10-05 22:40"),
        now=pd.Timestamp("2026-10-06 09:00"),
    )

    assert summary["buy"] == ("0건", "이번 스캔 매수 신호 없음", False)
    assert summary["last"] == ("10/05 22:40", "1일 전", False)


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
        config.SIGNAL_HISTORY_DISPLAY_COLUMNS,
        config.SCAN_EVENT_DISPLAY_COLUMNS,
        config.ACTIVE_SCENARIO_DISPLAY_COLUMNS,
        config.CLOSED_RESULT_DISPLAY_COLUMNS,
        config.CLOSED_SCENARIO_DISPLAY_COLUMNS,
        config.FIELD_DISPLAY_COLUMNS,
        config.RANKING_DISPLAY_COLUMNS,
        config.SIGNAL_VALIDATION_DISPLAY_COLUMNS,
        config.SCAN_FAILURE_COLUMNS,
        WATCHLIST_DISPLAY_COLUMNS,
    ]
    columns = {column for columns in column_lists for column in columns}

    assert columns - set(TERM_DESCRIPTIONS) == set()


def test_heading_explanation_ignores_the_sort_marker() -> None:
    from gui.tooltips import TERM_DESCRIPTIONS, term_description

    assert term_description("승률 ▼") == TERM_DESCRIPTIONS["승률"]
    assert term_description("평소 매수 대비 초과 ▲") == TERM_DESCRIPTIONS["평소 매수 대비 초과"]
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
