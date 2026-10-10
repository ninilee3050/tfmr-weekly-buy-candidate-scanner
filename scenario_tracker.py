from __future__ import annotations

from pathlib import Path

import pandas as pd

from csv_io import read_csv_flexible
from data_provider import is_weekend_traded, weekly_bar_in_progress
from market_cap_provider import MarketCapCompany
from scanner import OUTCOME_HOLDING, OUTCOME_SOLD, SELL_EVENT, buy_round_label


ACTIVE_STATE_PATH = Path("outputs") / "tfmr_active_scenarios.csv"

FIRST_BUY_STAGE = "1차 매수"
ADD_BUY_STAGE = "추가매수"
SELL_STAGE = "매도"
PROVISIONAL_SELL_STATE = "매도 신호 · 잠정"

ACTIVE_SCENARIO_COLUMNS = [
    "순위",
    "티커",
    "회사명",
    "시가총액",
    "현재상태",
    "1차매수일",
    "매수차수",
    "최근매수일",
    "최근매수가",
    "보유수량",
    "평단가",
    "다음추가매수가",
    "현재가",
    "평가손익률",
    "보유주수",
    "마지막확인일",
    "데이터기준일",
    "데이터상태",
    "S&P500 상태",
]

SCAN_EVENT_COLUMNS = [
    "순위",
    "티커",
    "회사명",
    "단계",
    "신호일",
    "결과",
    "1차매수일",
    "매수차수",
    "가격",
    "평단가",
    "수익률",
    "보유주수",
    "신호구분",
    "데이터기준일",
    "S&P500 상태",
]

CLOSED_RESULT_COLUMNS = [
    "순위",
    "티커",
    "회사명",
    "1차매수일",
    "매수차수",
    "매도일",
    "평단가",
    "매도가",
    "수익률",
    "보유주수",
    "신호구분",
    "데이터기준일",
    "S&P500 상태",
]

_DATE_COLUMNS = {
    "1차매수일",
    "최근매수일",
    "매도일",
    "신호일",
    "마지막확인일",
    "데이터기준일",
}


def load_active_scenarios(
    path: Path | str = ACTIVE_STATE_PATH,
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=ACTIVE_SCENARIO_COLUMNS)

    data = read_csv_flexible(path)
    data = data.reindex(columns=ACTIVE_SCENARIO_COLUMNS)
    data["S&P500 상태"] = data["S&P500 상태"].fillna("확인불가")
    for column in _DATE_COLUMNS.intersection(data.columns):
        data[column] = pd.to_datetime(data[column], errors="coerce")
    return data


def save_active_scenarios(
    active_scenarios: pd.DataFrame,
    path: Path | str = ACTIVE_STATE_PATH,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    normalized = active_scenarios.reindex(columns=ACTIVE_SCENARIO_COLUMNS)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    normalized.to_csv(temporary_path, index=False, encoding="utf-8-sig")
    temporary_path.replace(path)
    return path


def merge_scan_universe(
    top100_companies: list[MarketCapCompany],
    active_scenarios: pd.DataFrame,
) -> list[MarketCapCompany]:
    companies_by_ticker = {
        company.ticker: company
        for company in top100_companies
    }

    for _, row in active_scenarios.iterrows():
        ticker = str(row.get("티커", "")).strip().upper()
        if not ticker or ticker in companies_by_ticker:
            continue
        companies_by_ticker[ticker] = MarketCapCompany(
            rank=_rank_or_default(row.get("순위")),
            ticker=ticker,
            company=_text(row.get("회사명")),
            market_cap=_text(row.get("시가총액")),
        )

    return list(companies_by_ticker.values())


def summarize_ticker_cases(
    company: MarketCapCompany,
    cases: pd.DataFrame,
    buys: pd.DataFrame,
    full_table: pd.DataFrame,
    scan_date: pd.Timestamp | str,
    previous_active: pd.Series | None = None,
    last_scan_date: pd.Timestamp | str | None = None,
    now: pd.Timestamp | None = None,
) -> tuple[list[dict[str, object]], dict[str, object] | None, list[dict[str, object]]]:
    """Summarize one ticker's trade cases into new events, an active row and sells.

    ``last_scan_date`` is the most recent scan date across the whole previous
    active state (see ``latest_scan_date``).  It lets a ticker that was not
    being tracked still report a case that opened after that scan.  ``now``
    decides whether the latest weekly bar is still open; it defaults to the
    current time.
    """
    if full_table.empty:
        return [], None, []

    week_start = _week_start(scan_date)
    data_date = pd.Timestamp(full_table.index[-1]).normalize()
    has_previous = previous_active is not None
    previous_first = _as_timestamp(
        previous_active.get("1차매수일") if has_previous else None
    )
    previous_rounds = _rounds(previous_active.get("매수차수") if has_previous else None)
    last_checked = _as_timestamp(
        previous_active.get("마지막확인일") if has_previous else None
    )
    # Signals are labelled with the Monday of their weekly bar, while scan
    # dates are real calendar days, so compare both on a weekly basis.
    last_checked_week = _week_start(last_checked) if last_checked is not None else None
    last_scan_date = _as_timestamp(last_scan_date)
    last_scan_week = _week_start(last_scan_date) if last_scan_date is not None else None

    events: list[dict[str, object]] = []
    closed_results: list[dict[str, object]] = []

    for _, case in cases.iterrows():
        first_date = _as_timestamp(case.get("FirstBuyDate"))
        if previous_first is not None and first_date is not None and first_date < previous_first:
            continue
        same_tracked_case = has_previous and previous_first == first_date

        for signal_date, stage, buy in _case_signals(case, buys):
            already_known = (
                same_tracked_case
                and buy is not None
                and int(buy["Round"]) <= previous_rounds
            )
            if not _should_report_signal(
                signal_date,
                first_date=first_date,
                week_start=week_start,
                has_previous=has_previous,
                already_known=already_known,
                last_checked_week=last_checked_week,
                last_scan_week=last_scan_week,
            ):
                continue
            event = _event_row(
                company=company,
                case=case,
                stage=stage,
                buy=buy,
                signal_date=signal_date,
                week_start=week_start,
                data_date=data_date,
                last_close=full_table.iloc[-1]["Close"],
            )
            events.append(event)
            if stage == SELL_STAGE and case["Outcome"] == OUTCOME_SOLD:
                closed_results.append(_closed_result_row(event))

    open_cases = cases[cases["Outcome"] == OUTCOME_HOLDING]
    active_row = None
    if not open_cases.empty:
        case = open_cases.iloc[-1]
        active_row = {
            "순위": company.rank,
            "티커": company.ticker,
            "회사명": company.company,
            "시가총액": company.market_cap,
            "현재상태": (
                PROVISIONAL_SELL_STATE if _sell_pending(case) else OUTCOME_HOLDING
            ),
            "1차매수일": _as_timestamp(case.get("FirstBuyDate")),
            "매수차수": int(case["BuyRounds"]),
            "최근매수일": _as_timestamp(case.get("LastBuyDate")),
            "최근매수가": case.get("LastBuyPrice"),
            "보유수량": int(case["Quantity"]),
            "평단가": case.get("AveragePrice"),
            "다음추가매수가": case.get("NextAddBuyPrice"),
            "현재가": full_table.iloc[-1]["Close"],
            "평가손익률": case.get("ReturnPct"),
            "보유주수": int(case["HoldingWeeks"]),
            "마지막확인일": pd.Timestamp(scan_date).normalize(),
            "데이터기준일": data_date,
            "데이터상태": (
                "현재 주봉 포함"
                if weekly_bar_in_progress(
                    data_date,
                    now=now,
                    weekend_traded=is_weekend_traded(company.ticker),
                )
                else "확정 주봉"
            ),
        }

    return events, active_row, closed_results


def preserve_failed_active_rows(
    active_scenarios: pd.DataFrame,
    failed_tickers: set[str],
) -> list[dict[str, object]]:
    if active_scenarios.empty or not failed_tickers:
        return []

    preserved = []
    for _, row in active_scenarios.iterrows():
        if str(row.get("티커", "")).upper() not in failed_tickers:
            continue
        item = row.reindex(ACTIVE_SCENARIO_COLUMNS).to_dict()
        item["데이터상태"] = "갱신 실패"
        preserved.append(item)
    return preserved


def _sell_pending(case: pd.Series) -> bool:
    """True for an open case whose sell showed up on the unfinished week."""
    return bool(case.get("Provisional")) and case.get("LastEvent") == SELL_EVENT


def _case_signals(
    case: pd.Series,
    buys: pd.DataFrame,
) -> list[tuple[pd.Timestamp, str, pd.Series | None]]:
    """Every buy of the case in order, then its sell when there is one."""
    signals: list[tuple[pd.Timestamp, str, pd.Series | None]] = []
    case_buys = buys[buys["FirstBuyDate"] == case["FirstBuyDate"]]
    for _, buy in case_buys.iterrows():
        stage = FIRST_BUY_STAGE if int(buy["Round"]) == 1 else ADD_BUY_STAGE
        signals.append((pd.Timestamp(buy["Date"]).normalize(), stage, buy))
    sell_date = _as_timestamp(case.get("SellDate"))
    if sell_date is None and _sell_pending(case):
        sell_date = _as_timestamp(case.get("LastEventDate"))
    if sell_date is not None:
        signals.append((sell_date, SELL_STAGE, None))
    return signals


def _event_row(
    company: MarketCapCompany,
    case: pd.Series,
    stage: str,
    buy: pd.Series | None,
    signal_date: pd.Timestamp,
    week_start: pd.Timestamp,
    data_date: pd.Timestamp,
    last_close: float,
) -> dict[str, object]:
    if buy is not None:
        result = buy_round_label(buy["Round"])
        rounds = int(buy["Round"])
        price = buy["Price"]
        average = buy["AveragePrice"]
        return_pct = float("nan")
    else:
        sold = case["Outcome"] == OUTCOME_SOLD
        result = OUTCOME_SOLD if sold else PROVISIONAL_SELL_STATE
        rounds = int(case["BuyRounds"])
        price = case["SellPrice"] if sold else last_close
        average = case["AveragePrice"]
        return_pct = case["ReturnPct"]

    return {
        "순위": company.rank,
        "티커": company.ticker,
        "회사명": company.company,
        "단계": stage,
        "신호일": signal_date,
        "결과": result,
        "1차매수일": _as_timestamp(case.get("FirstBuyDate")),
        "매수차수": rounds,
        "가격": price,
        "평단가": average,
        "수익률": return_pct,
        "보유주수": int(case["HoldingWeeks"]),
        "신호구분": "이번 주" if signal_date == week_start else "미확인 기간",
        "데이터기준일": data_date,
    }


def _closed_result_row(event: dict[str, object]) -> dict[str, object]:
    row = {
        column: event.get(column)
        for column in CLOSED_RESULT_COLUMNS
    }
    row["매도일"] = event.get("신호일")
    row["매도가"] = event.get("가격")
    return row


def _should_report_signal(
    signal_date: pd.Timestamp,
    first_date: pd.Timestamp | None,
    week_start: pd.Timestamp,
    has_previous: bool,
    already_known: bool,
    last_checked_week: pd.Timestamp | None,
    last_scan_week: pd.Timestamp | None,
) -> bool:
    if signal_date == week_start:
        return True
    if has_previous:
        # The week of the last check is included because that scan may have
        # seen only part of the week; buys it already saved are not repeated.
        if already_known:
            return False
        return last_checked_week is None or signal_date >= last_checked_week
    # An untracked ticker has no case the previous scan knew about, unless
    # that case already closed.  Only report cases that opened afterwards.
    return (
        last_scan_week is not None
        and first_date is not None
        and first_date >= last_scan_week
        and signal_date >= last_scan_week
    )


def _rounds(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def latest_scan_date(active_scenarios: pd.DataFrame) -> pd.Timestamp | None:
    """Return the most recent 마지막확인일 stored in the active state."""
    if active_scenarios.empty or "마지막확인일" not in active_scenarios.columns:
        return None
    dates = pd.to_datetime(active_scenarios["마지막확인일"], errors="coerce").dropna()
    if dates.empty:
        return None
    return pd.Timestamp(dates.max()).normalize()


def market_today() -> pd.Timestamp:
    """Today's date in US market time (New York), as a naive timestamp.

    Weekly bars follow the US trading week.  Using the local clock in Korea
    would start the new week on Monday morning, before the US week opens.
    """
    return pd.Timestamp.now(tz="America/New_York").tz_localize(None).normalize()


def _as_timestamp(value: object) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).normalize()


def _week_start(value: pd.Timestamp | str) -> pd.Timestamp:
    date = pd.Timestamp(value).normalize()
    return date - pd.Timedelta(days=date.weekday())


def _text(value: object) -> str:
    """A CSV cell as text; empty cells read back as NaN become ""."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _rank_or_default(value: object) -> int:
    try:
        if pd.isna(value):
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        return 9999
