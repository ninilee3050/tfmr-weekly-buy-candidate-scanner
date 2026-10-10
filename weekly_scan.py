from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd

from data_provider import is_weekend_traded, load_weekly_data, weekly_bar_in_progress
from indicators import calculate_indicators
from market_cap_provider import (
    MarketCapCompany,
    MarketCapLoadError,
    fetch_us_top_market_cap_result,
)
from market_context import annotate_sp500_status, load_sp500_context
from notifier import (
    NotificationError,
    build_failure_message,
    build_scan_message,
    notify_from_environment,
)
from scanner import scan_trade_cases
from scenario_tracker import (
    ACTIVE_SCENARIO_COLUMNS,
    ADD_BUY_STAGE,
    CLOSED_RESULT_COLUMNS,
    FIRST_BUY_STAGE,
    SCAN_EVENT_COLUMNS,
    SELL_STAGE,
    latest_scan_date,
    load_active_scenarios,
    market_today,
    merge_scan_universe,
    preserve_failed_active_rows,
    save_active_scenarios,
    summarize_ticker_cases,
)


from watchlist import load_watchlist, watchlist_companies


OUTPUT_DIR = Path("outputs")
TOP100_LIMIT = 100
RETRY_DELAY_SECONDS = 2
# Set by the GitHub workflow: "true" when the saved state was restored.
STATE_RESTORED_ENV = "TFMR_STATE_RESTORED"
STATE_LOST_WARNING = (
    "이전 보유 상태를 찾지 못해 처음부터 다시 추적합니다. "
    "지난 스캔 이후의 추가매수·매도 신호 중 일부가 이번 알림에 빠졌을 수 있습니다."
)
SCAN_FAILURE_COLUMNS = ["순위", "티커", "회사명", "시가총액", "오류"]


def main() -> int:
    scan_date = market_today()
    week_start = scan_date - pd.Timedelta(days=scan_date.weekday())
    # Before Friday's close this week's bar can still change, so the run only
    # reports; it never advances the saved tracking state.
    provisional = weekly_bar_in_progress(week_start)
    warnings: list[str] = []
    restore_warning = state_restore_warning()
    if restore_warning:
        print(f"경고: {restore_warning}")
        warnings.append(restore_warning)
    try:
        previous_active = load_active_scenarios()
        print("미국 시가총액 Top 100 목록과 보유 중인 종목을 불러옵니다...")
        try:
            top100 = fetch_us_top_market_cap_result(limit=TOP100_LIMIT)
            top100_companies = top100.companies
            if top100.warning:
                print(f"경고: {top100.warning}")
                warnings.append(top100.warning)
        except MarketCapLoadError as exc:
            # Keep following cases that are already held even when the
            # ranking cannot be read; only new first buys are missed.
            if previous_active.empty:
                raise
            top100_companies = []
            print(f"경고: {exc} 활성 시나리오 종목만 스캔합니다.")
            warnings.append(f"{exc} 활성 시나리오 종목만 스캔했습니다.")
        companies = merge_scan_universe(
            [
                *top100_companies,
                *watchlist_companies(load_watchlist(), top100_companies),
            ],
            previous_active,
        )
        print("S&P500 주봉 데이터를 한 번 갱신합니다...")
        try:
            sp500_data, sp500_load = load_sp500_context(
                force_refresh=True,
                max_cache_age_seconds=None,
            )
            sp500_warning = sp500_load.warning
        except Exception as exc:
            sp500_data = pd.DataFrame()
            sp500_warning = f"S&P500 상태 확인 실패: {exc}"

        events, active_rows, closed_results, failures = scan_companies(
            companies,
            scan_date,
            previous_active,
            progress_label="스캔 중",
        )
        if failures:
            print(f"실패한 {len(failures)}개 종목을 한 번 더 시도합니다...")
            time.sleep(RETRY_DELAY_SECONDS)
            retry_companies = [failure["company"] for failure in failures]
            retry_events, retry_active, retry_closed, retry_failures = scan_companies(
                retry_companies,
                scan_date,
                previous_active,
                progress_label="재시도 중",
            )
            events.extend(retry_events)
            active_rows.extend(retry_active)
            closed_results.extend(retry_closed)
            failures = retry_failures

        failed_tickers = {failure["company"].ticker for failure in failures}
        active_rows.extend(
            preserve_failed_active_rows(previous_active, failed_tickers)
        )

        events_df = _sorted_frame(
            events,
            SCAN_EVENT_COLUMNS,
            by=["신호일", "순위"],
            ascending=[False, True],
        )
        events_df = annotate_sp500_status(
            events_df,
            sp500_data,
            reference_date_columns=("신호일",),
        )
        active_df = _sorted_frame(
            active_rows,
            ACTIVE_SCENARIO_COLUMNS,
            by=["순위", "티커"],
            ascending=[True, True],
        ).drop_duplicates(subset=["티커"], keep="last")
        active_df = annotate_sp500_status(active_df, sp500_data, use_latest=True)
        closed_df = _sorted_frame(
            closed_results,
            CLOSED_RESULT_COLUMNS,
            by=["매도일", "순위"],
            ascending=[False, True],
        )
        closed_df = annotate_sp500_status(
            closed_df,
            sp500_data,
            reference_date_columns=("매도일",),
        )
        failures_df = pd.DataFrame(
            [_failure_row(failure["company"], failure["error"]) for failure in failures],
            columns=SCAN_FAILURE_COLUMNS,
        )

        saved_paths = save_scan_outputs(
            events_df,
            active_df,
            closed_df,
            failures_df,
            scan_date,
        )
        if provisional:
            print("장 마감 전 실행: 보유 상태는 저장하지 않습니다.")
        else:
            save_active_scenarios(active_df)
    except Exception as exc:
        print(f"스캔 실패: {exc}", file=sys.stderr)
        _send_notification(build_failure_message(exc, scan_date))
        return 1

    stage_counts = events_df["단계"].value_counts() if not events_df.empty else {}

    print("")
    print(
        f"스캔 완료: 신규 1차 매수 {stage_counts.get(FIRST_BUY_STAGE, 0)}개 / "
        f"추가매수 {stage_counts.get(ADD_BUY_STAGE, 0)}개 / "
        f"매도 {stage_counts.get(SELL_STAGE, 0)}개 / "
        f"보유 중 {len(active_df)}개 / 데이터 오류 {len(failures_df)}개"
    )
    if sp500_warning:
        print(sp500_warning)
    for path in saved_paths:
        print(f"저장: {path}")
    if sp500_warning:
        warnings.append(sp500_warning)
    _send_notification(
        build_scan_message(
            events_df,
            active_df,
            len(failures_df),
            scan_date,
            warnings,
            provisional=provisional,
            data_basis=data_basis_text() if provisional else "",
        )
    )
    return 0


def data_basis_text(now: pd.Timestamp | None = None) -> str:
    """Which US session the latest prices come from, for a pre-close run."""
    if now is None:
        now = pd.Timestamp.now(tz="America/New_York")
    minutes = now.hour * 60 + now.minute
    if now.weekday() >= 5 or minutes >= 16 * 60:
        return "최근 거래일 종가까지 반영"
    if minutes >= 9 * 60 + 30:
        return "오늘 미국 장중 가격 포함"
    previous = ["금요일", "월요일", "화요일", "수요일", "목요일"][now.weekday()]
    return f"{previous} 종가까지 반영"


def state_restore_warning() -> str:
    """Warning text when the workflow reports that no saved state was restored."""
    if os.environ.get(STATE_RESTORED_ENV, "").strip().lower() == "false":
        return STATE_LOST_WARNING
    return ""


def _send_notification(text: str) -> None:
    """Send the Telegram summary; a delivery problem never fails the scan."""
    try:
        sent = notify_from_environment(text)
    except NotificationError as exc:
        print(f"경고: {exc}", file=sys.stderr)
        return
    print("텔레그램 알림을 보냈습니다." if sent else "텔레그램 설정이 없어 알림을 건너뜁니다.")


def scan_companies(
    companies: list[MarketCapCompany],
    scan_date: pd.Timestamp,
    previous_active: pd.DataFrame,
    progress_label: str,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    events: list[dict[str, object]] = []
    active_rows: list[dict[str, object]] = []
    closed_results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    previous_by_ticker = {
        str(row["티커"]).upper(): row
        for _, row in previous_active.iterrows()
    }
    last_scan_date = latest_scan_date(previous_active)

    for index, company in enumerate(companies, start=1):
        print(f"{progress_label}... {index}/{len(companies)} {company.ticker}")
        try:
            raw_data = load_weekly_data(
                company.ticker,
                include_current_week=True,
                force_refresh=True,
            )
            calculated = calculate_indicators(raw_data)
            cases, buys, full_table = scan_trade_cases(
                calculated,
                weekend_traded=is_weekend_traded(company.ticker),
            )
            ticker_events, active_row, ticker_closed = summarize_ticker_cases(
                company,
                cases,
                buys,
                full_table,
                scan_date,
                previous_active=previous_by_ticker.get(company.ticker.upper()),
                last_scan_date=last_scan_date,
            )
            events.extend(ticker_events)
            closed_results.extend(ticker_closed)
            if active_row is not None:
                active_rows.append(active_row)
        except Exception as exc:
            failures.append({"company": company, "error": str(exc)})

    return events, active_rows, closed_results, failures


def save_scan_outputs(
    events: pd.DataFrame,
    active_scenarios: pd.DataFrame,
    closed_results: pd.DataFrame,
    failures: pd.DataFrame,
    scan_date: pd.Timestamp,
    output_dir: Path | str = OUTPUT_DIR,
) -> tuple[Path, Path, Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_text = scan_date.strftime("%Y-%m-%d")
    event_path = output_dir / f"signal_events_{date_text}.csv"
    active_path = output_dir / f"active_scenarios_{date_text}.csv"
    closed_path = output_dir / f"closed_results_{date_text}.csv"
    failure_path = output_dir / f"scan_failures_{date_text}.csv"

    events.to_csv(event_path, index=False, encoding="utf-8-sig")
    active_scenarios.to_csv(active_path, index=False, encoding="utf-8-sig")
    closed_results.to_csv(closed_path, index=False, encoding="utf-8-sig")
    failures.to_csv(failure_path, index=False, encoding="utf-8-sig")
    return event_path, active_path, closed_path, failure_path


def _failure_row(company: MarketCapCompany, error: str) -> dict[str, object]:
    return {
        "순위": company.rank,
        "티커": company.ticker,
        "회사명": company.company,
        "시가총액": company.market_cap,
        "오류": error,
    }


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


if __name__ == "__main__":
    raise SystemExit(main())
