"""Reading and writing the app's CSV output files."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from csv_io import read_csv_flexible
from market_context import SP500_STATUS_COLUMN
from scenario_tracker import save_active_scenarios
from gui.config import (
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_SCENARIO_PATH,
    DOWNLOADS_DIR,
    LAST_SCAN_INFO_PATH,
    LAST_SCAN_TABLE_PATHS,
    OUTPUT_DIR,
    RETURN_DISPLAY_COLUMNS,
)
from gui.formatting import signal_cycles_for_display


def save_outputs(
    ticker: str,
    buy_points: pd.DataFrame,
    full_table: pd.DataFrame,
    output_dir: Path | str = OUTPUT_DIR,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    buy_path = output_dir / f"{ticker}_buy_points.csv"
    full_path = output_dir / f"{ticker}_full_table.csv"

    buy_points.to_csv(buy_path, index_label="매수포인트날짜", encoding="utf-8-sig")
    full_table.to_csv(full_path, index_label="Date", encoding="utf-8-sig")
    return buy_path, full_path


def save_signal_outputs(
    ticker: str,
    signal_cycles: pd.DataFrame,
    full_table: pd.DataFrame,
    output_dir: Path | str = OUTPUT_DIR,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    signal_path = output_dir / f"{ticker}_signal_cycles.csv"
    full_path = output_dir / f"{ticker}_full_table.csv"

    signal_cycles_for_display(signal_cycles).to_csv(
        signal_path,
        index=False,
        encoding="utf-8-sig",
    )
    full_table.to_csv(full_path, index_label="Date", encoding="utf-8-sig")
    return signal_path, full_path


def load_closed_scenarios(
    path: Path | str = CLOSED_SCENARIO_PATH,
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)

    data = read_csv_flexible(path)
    if "현재 시총순위" not in data.columns and "순위" in data.columns:
        data = data.rename(columns={"순위": "현재 시총순위"})
    data = data.reindex(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)
    data[SP500_STATUS_COLUMN] = data[SP500_STATUS_COLUMN].fillna("확인불가")
    for column in ("1차신호일", "2차신호일", "3차판정일"):
        data[column] = pd.to_datetime(data[column], errors="coerce")
    for column in RETURN_DISPLAY_COLUMNS:
        data[column] = data[column].map(_restore_saved_return_value)
    return data


def save_closed_scenarios(
    data: pd.DataFrame,
    path: Path | str = CLOSED_SCENARIO_PATH,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = data.reindex(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    normalized.to_csv(temporary_path, index=False, encoding="utf-8-sig")
    temporary_path.replace(path)
    return path


def _restore_saved_return_value(value: object) -> object:
    """Restore numeric CSV values while preserving progress/status labels."""
    if pd.isna(value) or isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return value
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return value


def save_tracker_scan_outputs(
    events: pd.DataFrame,
    active_scenarios: pd.DataFrame,
    closed_results: pd.DataFrame,
    failures: pd.DataFrame,
    scan_date: pd.Timestamp,
    output_dir: Path | str = DOWNLOADS_DIR,
) -> tuple[Path, Path, Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    date_text = scan_date.strftime("%Y-%m-%d")
    event_path = output_dir / f"MMRM_signal_events_{date_text}.csv"
    active_path = output_dir / f"MMRM_active_scenarios_{date_text}.csv"
    closed_path = output_dir / f"MMRM_closed_results_{date_text}.csv"
    failure_path = output_dir / f"MMRM_Top100_scan_failures_{date_text}.csv"

    events.to_csv(event_path, index=False, encoding="utf-8-sig")
    active_scenarios.to_csv(active_path, index=False, encoding="utf-8-sig")
    closed_results.to_csv(closed_path, index=False, encoding="utf-8-sig")
    failures.to_csv(failure_path, index=False, encoding="utf-8-sig")
    return event_path, active_path, closed_path, failure_path


def save_analytics_outputs(
    sector_performance: pd.DataFrame,
    industry_performance: pd.DataFrame,
    field_rankings: pd.DataFrame,
    output_dir: Path | str = OUTPUT_DIR,
    date_suffix: str | None = None,
) -> tuple[Path, Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"_{date_suffix}" if date_suffix else ""
    prefix = "MMRM" if date_suffix else "mmrm"
    sector_path = output_dir / f"{prefix}_sector_performance{suffix}.csv"
    industry_path = output_dir / f"{prefix}_industry_performance{suffix}.csv"
    ranking_path = output_dir / f"{prefix}_field_stock_rankings{suffix}.csv"
    sector_performance.to_csv(sector_path, index=False, encoding="utf-8-sig")
    industry_performance.to_csv(industry_path, index=False, encoding="utf-8-sig")
    field_rankings.to_csv(ranking_path, index=False, encoding="utf-8-sig")
    return sector_path, industry_path, ranking_path


def save_scan_state(
    sector_performance: pd.DataFrame,
    industry_performance: pd.DataFrame,
    field_rankings: pd.DataFrame,
    active_scenarios: pd.DataFrame,
    closed_scenarios: pd.DataFrame,
    events: pd.DataFrame,
    closed_results: pd.DataFrame,
    failures: pd.DataFrame,
    scanned_at: pd.Timestamp,
) -> None:
    """Write the files the next app start and scan read back from outputs/."""
    save_analytics_outputs(sector_performance, industry_performance, field_rankings)
    save_active_scenarios(active_scenarios)
    save_closed_scenarios(closed_scenarios)
    save_last_scan(events, closed_results, failures, scanned_at)


LAST_SCAN_DATE_COLUMNS = (
    "신호일",
    "1차신호일",
    "2차신호일",
    "3차판정일",
    "종료일",
    "데이터기준일",
)


def save_last_scan(
    events: pd.DataFrame,
    closed_results: pd.DataFrame,
    failures: pd.DataFrame,
    scanned_at: pd.Timestamp,
    table_paths: dict[str, Path] = LAST_SCAN_TABLE_PATHS,
    info_path: Path | str = LAST_SCAN_INFO_PATH,
) -> None:
    """Keep the latest scan's tables so the next app start can show them."""
    tables = {"events": events, "closed_results": closed_results, "failures": failures}
    for name, table in tables.items():
        path = Path(table_paths[name])
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        table.to_csv(temporary_path, index=False, encoding="utf-8-sig")
        temporary_path.replace(path)
    # Written last: its presence means the three tables above are complete.
    info_path = Path(info_path)
    temporary_info = info_path.with_suffix(info_path.suffix + ".tmp")
    temporary_info.write_text(
        json.dumps({"scanned_at": pd.Timestamp(scanned_at).isoformat()}),
        encoding="utf-8",
    )
    temporary_info.replace(info_path)


def load_last_scan(
    table_paths: dict[str, Path] = LAST_SCAN_TABLE_PATHS,
    info_path: Path | str = LAST_SCAN_INFO_PATH,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Timestamp] | None:
    """Return (events, closed results, failures, scan time) of the saved scan."""
    try:
        info = json.loads(Path(info_path).read_text(encoding="utf-8"))
        scanned_at = pd.Timestamp(info["scanned_at"])
        tables = []
        for name in ("events", "closed_results", "failures"):
            table = read_csv_flexible(table_paths[name])
            for column in LAST_SCAN_DATE_COLUMNS:
                if column in table.columns:
                    table[column] = pd.to_datetime(table[column], errors="coerce")
            tables.append(table)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if pd.isna(scanned_at):
        return None
    return tables[0], tables[1], tables[2], scanned_at
