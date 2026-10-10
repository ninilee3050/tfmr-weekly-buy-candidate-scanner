"""Assembling, filtering and ordering scan and history results."""

from __future__ import annotations

import pandas as pd

from chart_strength import annotate_completed_scenarios
from market_cap_provider import MarketCapCompany
from market_context import annotate_sp500_status
from performance_analytics import build_ticker_performance, format_rate
from gui.config import CLOSED_SCENARIO_DISPLAY_COLUMNS, SIGNAL_HISTORY_DISPLAY_COLUMNS
from gui.formatting import scan_event_priority, signal_cycles_for_display


def _failure_row(company: MarketCapCompany, error: str) -> dict[str, object]:
    return {
        "순위": company.rank,
        "티커": company.ticker,
        "회사명": company.company,
        "시가총액": company.market_cap,
        "오류": error,
    }


def validate_chart_strength_range(
    minimum_text: object,
    maximum_text: object,
    enabled: bool = True,
) -> tuple[float | None, float | None]:
    if not enabled:
        return None, None

    def parse_bound(value: object, label: str) -> float | None:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} 점수에 0~100 숫자를 입력해 주세요.") from exc
        if not 0 <= number <= 100:
            raise ValueError(f"{label} 점수는 0~100 범위여야 합니다.")
        return number

    minimum = parse_bound(minimum_text, "최소")
    maximum = parse_bound(maximum_text, "최대")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("최소 점수는 최대 점수보다 클 수 없습니다.")
    return minimum, maximum


def filter_closed_scenarios(
    data: pd.DataFrame,
    *,
    grade_enabled: bool = False,
    grade: str = "",
    score_enabled: bool = False,
    minimum_score: float | None = None,
    maximum_score: float | None = None,
) -> pd.DataFrame:
    """Filter only the closed-scenario view without mutating saved history."""
    display = data.copy()
    if display.empty:
        return display.reset_index(drop=True)

    mask = pd.Series(True, index=display.index)
    if grade_enabled:
        grades = display.get(
            "검토등급",
            pd.Series("", index=display.index, dtype="object"),
        ).fillna("").astype(str).str.strip()
        strengths = display.get(
            "차트 강도",
            pd.Series("", index=display.index, dtype="object"),
        ).fillna("").astype(str).str.strip()
        effective_grades = grades.mask(
            grades.eq("") & strengths.eq("해당 없음"),
            "해당 없음",
        )
        mask &= effective_grades.eq(str(grade).strip())

    if score_enabled:
        strengths = display.get(
            "차트 강도",
            pd.Series("", index=display.index, dtype="object"),
        ).astype(str)
        scores = pd.to_numeric(
            strengths.str.extract(r"([0-9]+(?:\.[0-9]+)?)", expand=False),
            errors="coerce",
        )
        mask &= scores.notna()
        if minimum_score is not None:
            mask &= scores.ge(minimum_score)
        if maximum_score is not None:
            mask &= scores.le(maximum_score)

    return display.loc[mask].reset_index(drop=True)


def prioritize_scan_events(data: pd.DataFrame) -> pd.DataFrame:
    """Put actionable signals first while preserving recency and market-cap order."""
    display = data.copy()
    if display.empty:
        return display
    display["_신호우선순위"] = display.apply(
        lambda row: scan_event_priority(row.get("단계"), row.get("결과")),
        axis=1,
    )
    if "차트 강도" in display.columns:
        score_text = display["차트 강도"].astype(str).str.extract(
            r"([0-9]+(?:\.[0-9]+)?)",
            expand=False,
        )
        display["_차트강도순위"] = pd.to_numeric(
            score_text, errors="coerce"
        ).fillna(-1.0)
    else:
        display["_차트강도순위"] = -1.0
    return (
        display.sort_values(
            by=["_신호우선순위", "_차트강도순위", "신호일", "순위"],
            ascending=[True, False, False, True],
            na_position="last",
        )
        .drop(columns=["_신호우선순위", "_차트강도순위"])
        .reset_index(drop=True)
    )


def prioritize_active_scenarios(data: pd.DataFrame) -> pd.DataFrame:
    display = data.copy()
    if display.empty:
        return display
    display["_상태우선순위"] = display["현재상태"].map(
        {"3차 신호 대기": 0, "2차 신호 대기": 1}
    ).fillna(2)
    first_dates = pd.to_datetime(display.get("1차신호일"), errors="coerce")
    second_dates = pd.to_datetime(display.get("2차신호일"), errors="coerce")
    display["_단계진입일"] = first_dates
    waiting_for_third = display["현재상태"].eq("3차 신호 대기")
    display.loc[waiting_for_third, "_단계진입일"] = second_dates[waiting_for_third]
    return (
        display.sort_values(
            by=["_상태우선순위", "_단계진입일", "순위", "티커"],
            ascending=[True, False, True, True],
            na_position="last",
        )
        .drop(columns=["_상태우선순위", "_단계진입일"])
        .reset_index(drop=True)
    )


def add_scan_performance_columns(
    data: pd.DataFrame,
    companies: list[MarketCapCompany],
    cycles_by_ticker: dict[str, pd.DataFrame],
    classifications: pd.DataFrame,
    sector_output: pd.DataFrame,
    horizon_months: int = 3,
) -> pd.DataFrame:
    display = data.copy()
    ticker_column = f"종목 {horizon_months}개월 승률"
    sector_column = f"섹터 {horizon_months}개월 승률"
    display[ticker_column] = "미산출 (0건)"
    display[sector_column] = "미산출 (0건)"
    if display.empty:
        return display

    ticker_performance = build_ticker_performance(
        companies,
        cycles_by_ticker,
        classifications,
        horizon_months,
    )
    ticker_rates = {
        str(row["티커"]).upper(): format_rate(
            row["승률"], row["승리"], row["분석 표본"]
        )
        for _, row in ticker_performance.iterrows()
    }

    horizon_label = f"{horizon_months}개월"
    if "분석 기간" in sector_output.columns:
        sector_rows = sector_output[sector_output["분석 기간"].eq(horizon_label)]
    else:
        sector_rows = pd.DataFrame()
    sector_rates = {
        str(row["분야"]): format_rate(
            row["승률"], row["승리"], row["분석 표본"]
        )
        for _, row in sector_rows.iterrows()
    }

    display[ticker_column] = (
        display["티커"].astype(str).str.upper().map(ticker_rates).fillna("미산출 (0건)")
    )
    if "섹터" in display.columns:
        display[sector_column] = display["섹터"].map(sector_rates).fillna("미산출 (0건)")
    return display


def add_sector_column(data: pd.DataFrame, classifications: pd.DataFrame) -> pd.DataFrame:
    display = data.copy()
    if "섹터" in display.columns:
        display = display.drop(columns=["섹터"])
    if "티커" not in display.columns:
        return display

    if classifications.empty or "티커" not in classifications.columns:
        sector_by_ticker = {}
    else:
        sector_by_ticker = {
            str(row.get("티커", "")).upper(): str(row.get("섹터", "미분류"))
            for _, row in classifications.iterrows()
        }
    position = list(display.columns).index("티커") + 1
    display.insert(
        position,
        "섹터",
        display["티커"].astype(str).str.upper().map(sector_by_ticker).fillna("미분류"),
    )
    return display


def build_closed_scenario_history(
    companies: list[MarketCapCompany],
    cycles_by_ticker: dict[str, pd.DataFrame],
    classifications: pd.DataFrame,
    previous: pd.DataFrame | None = None,
    failed_tickers: set[str] | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    current_tickers = {company.ticker.upper() for company in companies}

    for company in companies:
        cycles = cycles_by_ticker.get(company.ticker.upper())
        if cycles is None or cycles.empty or "Outcome" not in cycles.columns:
            continue
        closed = cycles.loc[
            ~cycles["Outcome"].isin({"2차 신호 대기", "3차 신호 대기"})
        ]
        if closed.empty:
            continue
        display = signal_cycles_for_display(closed)
        display.insert(0, "회사명", company.company)
        display.insert(0, "티커", company.ticker.upper())
        display.insert(0, "현재 시총순위", company.rank)
        frames.append(display)

    if frames:
        current = add_sector_column(
            pd.concat(frames, ignore_index=True),
            classifications,
        )
    else:
        current = pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)

    failed = {ticker.upper() for ticker in (failed_tickers or set())}
    if previous is not None and not previous.empty and failed:
        if "현재 시총순위" not in previous.columns and "순위" in previous.columns:
            previous = previous.rename(columns={"순위": "현재 시총순위"})
        previous_tickers = previous["티커"].astype(str).str.upper()
        preserved = previous.loc[
            previous_tickers.isin(failed & current_tickers)
        ].copy()
        current = pd.concat([current, preserved], ignore_index=True)

    if current.empty:
        return pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)

    current = current.reindex(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)
    for column in ("1차신호일", "2차신호일", "3차판정일"):
        current[column] = pd.to_datetime(current[column], errors="coerce")
    return (
        current.drop_duplicates(subset=["티커", "1차신호일"], keep="first")
        .sort_values(
            by=["1차신호일", "현재 시총순위", "티커"],
            ascending=[False, True, True],
            na_position="last",
        )
        .reset_index(drop=True)
    )


def _horizon_months(value: str) -> int:
    try:
        return int(str(value).replace("개월", "").strip())
    except ValueError:
        return 3


def annotate_signal_history_display(
    ticker: str,
    signal_cycles: pd.DataFrame,
    full_table: pd.DataFrame,
    reference: pd.DataFrame | None,
    reference_error: str | None = None,
    sp500_data: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[tuple[str, str], dict[str, object]]]:
    """Apply the scanner's chart-strength method to one ticker's history."""
    display = signal_cycles_for_display(signal_cycles)
    scored_input = display.copy()
    scored_input.insert(0, "티커", ticker.upper())
    annotated, details = annotate_completed_scenarios(
        scored_input,
        {ticker.upper(): full_table},
        reference,
        reference_error=reference_error,
    )
    waiting = annotated["결과"].astype(str).str.contains("대기", na=False)
    annotated.loc[waiting, "차트 강도"] = "산정 대기"
    annotated.loc[waiting, "검토등급"] = ""
    annotated = annotate_sp500_status(
        annotated,
        sp500_data if sp500_data is not None else pd.DataFrame(),
        reference_date_columns=("3차판정일", "2차신호일", "1차신호일"),
        pending_uses_latest=True,
    )
    return annotated.reindex(columns=SIGNAL_HISTORY_DISPLAY_COLUMNS), details


def signal_cycle_position(
    cycles: pd.DataFrame,
    cycle: pd.Series | None,
) -> int | None:
    """Return the table row position corresponding to a chart cycle."""
    if cycles.empty or cycle is None:
        return None

    matches = pd.Series(True, index=cycles.index)
    compared = False
    for column in ("FirstSignalDate", "SecondSignalDate", "ThirdDecisionDate"):
        if column not in cycles.columns or column not in cycle.index:
            continue
        target = pd.to_datetime(cycle.get(column), errors="coerce")
        values = pd.to_datetime(cycles[column], errors="coerce")
        if pd.isna(target):
            matches &= values.isna()
        else:
            matches &= values.dt.normalize().eq(pd.Timestamp(target).normalize())
        compared = True

    if "Outcome" in cycles.columns and "Outcome" in cycle.index:
        matches &= cycles["Outcome"].astype(str).eq(str(cycle.get("Outcome")))
        compared = True
    if not compared:
        return None

    positions = [
        position
        for position, matched in enumerate(matches.to_numpy(dtype=bool))
        if matched
    ]
    return positions[-1] if positions else None


def _sorted_frame(
    rows: list[dict[str, object]],
    columns: list[str],
    by: list[str],
    ascending: list[bool],
) -> pd.DataFrame:
    data = pd.DataFrame(rows, columns=columns)
    if data.empty:
        return data
    return data.sort_values(by=by, ascending=ascending, na_position="last").reset_index(drop=True)
