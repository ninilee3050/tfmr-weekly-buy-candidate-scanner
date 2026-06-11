from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from data_provider import DATA_DIR, load_weekly_data
from market_cap_provider import MarketCapCompany, fetch_us_top_market_cap
from tfmr_scanner import current_week_buy_point, scan_tfmr_buy_points


OUTPUT_DIR = Path("outputs")
SCAN_RESULT_COLUMNS = [
    "순위",
    "티커",
    "회사명",
    "시가총액",
    "주봉시작일",
    "스캔일",
    "Open",
    "Close",
    "MA5",
    "MA20",
    "MA50",
    "MA150",
    "MA200",
]
SCAN_FAILURE_COLUMNS = ["순위", "티커", "회사명", "시가총액", "오류"]
ProgressCallback = Callable[[int, int, MarketCapCompany], None]


def scan_companies(
    companies: Sequence[MarketCapCompany],
    scan_date: pd.Timestamp | str | None = None,
    data_dir: Path | str = DATA_DIR,
    force_refresh: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scan_day = pd.Timestamp.today().normalize() if scan_date is None else pd.Timestamp(scan_date).normalize()
    candidate_rows: list[dict[str, object]] = []
    failure_rows: list[dict[str, object]] = []
    total = len(companies)

    for index, company in enumerate(companies, start=1):
        if progress_callback is not None:
            progress_callback(index, total, company)
        try:
            weekly = load_weekly_data(
                company.ticker,
                data_dir=data_dir,
                include_current_week=True,
                force_refresh=force_refresh,
            )
            buy_points, _full = scan_tfmr_buy_points(weekly)
            candidate = current_week_buy_point(buy_points, scan_day)
            if candidate is not None:
                candidate_rows.append(_candidate_row(company, candidate, scan_day))
        except Exception as exc:
            failure_rows.append(_failure_row(company, str(exc)))

    return (
        pd.DataFrame(candidate_rows, columns=SCAN_RESULT_COLUMNS),
        pd.DataFrame(failure_rows, columns=SCAN_FAILURE_COLUMNS),
    )


def scan_top100(
    limit: int = 100,
    scan_date: pd.Timestamp | str | None = None,
    data_dir: Path | str = DATA_DIR,
    force_refresh: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    scan_day = pd.Timestamp.today().normalize() if scan_date is None else pd.Timestamp(scan_date).normalize()
    companies = fetch_us_top_market_cap(limit=limit)
    candidates, failures = scan_companies(
        companies,
        scan_date=scan_day,
        data_dir=data_dir,
        force_refresh=force_refresh,
        progress_callback=progress_callback,
    )
    return candidates, failures, scan_day


def save_scan_outputs(
    candidates: pd.DataFrame,
    failures: pd.DataFrame,
    scan_date: pd.Timestamp | str,
    output_dir: Path | str = OUTPUT_DIR,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scan_day = pd.Timestamp(scan_date).normalize()
    date_text = scan_day.strftime("%Y-%m-%d")
    candidate_path = output_dir / f"TFMR_Top100_scan_candidates_{date_text}.csv"
    failure_path = output_dir / f"TFMR_Top100_scan_failures_{date_text}.csv"

    candidates.to_csv(candidate_path, index=False, encoding="utf-8-sig")
    failures.to_csv(failure_path, index=False, encoding="utf-8-sig")
    return candidate_path, failure_path


def _candidate_row(
    company: MarketCapCompany,
    candidate: pd.Series,
    scan_date: pd.Timestamp,
) -> dict[str, object]:
    return {
        "순위": company.rank,
        "티커": company.ticker,
        "회사명": company.company,
        "시가총액": company.market_cap,
        "주봉시작일": pd.Timestamp(candidate.name).normalize(),
        "스캔일": scan_date,
        "Open": candidate.get("Open"),
        "Close": candidate.get("Close"),
        "MA5": candidate.get("MA5"),
        "MA20": candidate.get("MA20"),
        "MA50": candidate.get("MA50"),
        "MA150": candidate.get("MA150"),
        "MA200": candidate.get("MA200"),
    }


def _failure_row(company: MarketCapCompany, error: str) -> dict[str, object]:
    return {
        "순위": company.rank,
        "티커": company.ticker,
        "회사명": company.company,
        "시가총액": company.market_cap,
        "오류": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="TFMR Top100 이번주 매수후보 스캔")
    parser.add_argument("--limit", type=int, default=100, help="스캔할 Top N 종목 수")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="결과 CSV 저장 폴더")
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="이미 내려받은 데이터가 있으면 새로 다운로드하지 않습니다.",
    )
    args = parser.parse_args()

    def print_progress(index: int, total: int, company: MarketCapCompany) -> None:
        print(f"[{index}/{total}] {company.ticker} 스캔 중")

    candidates, failures, scan_day = scan_top100(
        limit=args.limit,
        force_refresh=not args.use_cache,
        progress_callback=print_progress,
    )
    candidate_path, failure_path = save_scan_outputs(
        candidates,
        failures,
        scan_day,
        output_dir=args.output_dir,
    )
    print(f"이번주 매수후보: {len(candidates)}개")
    print(f"실패: {len(failures)}개")
    print(f"후보 CSV: {candidate_path}")
    print(f"실패 CSV: {failure_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
