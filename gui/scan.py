"""Top 100 loading and the integrated trade-case scan."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox

import pandas as pd

from csv_io import describe_save_error
from data_provider import is_weekend_traded, load_weekly_data
from indicators import calculate_indicators
from market_cap_provider import (
    MarketCapCompany,
    MarketCapLoadError,
    fetch_us_top_market_cap_result,
)
from market_context import annotate_sp500_status, load_sp500_context
from scanner import scan_trade_cases
from scenario_tracker import (
    ACTIVE_SCENARIO_COLUMNS,
    ADD_BUY_STAGE,
    CLOSED_RESULT_COLUMNS,
    FIRST_BUY_STAGE,
    SCAN_EVENT_COLUMNS,
    SELL_STAGE,
    latest_scan_date,
    market_today,
    merge_scan_universe,
    preserve_failed_active_rows,
    summarize_ticker_cases,
)
from watchlist import load_watchlist, watchlist_companies
from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    DOWNLOADS_DIR,
    SCAN_DOWNLOAD_WORKERS,
    SCAN_EVENT_DISPLAY_COLUMNS,
    SCAN_FAILURE_COLUMNS,
)
from gui.formatting import (
    active_scenario_tag,
    history_case_tag,
    scan_event_tag,
    scanner_table_for_display,
)
from gui.scan_results import (
    _failure_row,
    _sorted_frame,
    build_closed_scenario_history,
    prioritize_active_scenarios,
    prioritize_scan_events,
)
from gui.storage import (
    save_closed_scenarios,
    save_scan_state,
    save_tracker_scan_outputs,
)
from gui.tables import populate_table


class ScanMixin:
    """Top 100 loading and the integrated trade-case scan. Mixed into BuyPointApp; relies on its attributes."""

    def load_top100(self) -> None:
        self.top100_button.configure(state="disabled")
        self.top100_status_var.set("미국 시총 Top 100 목록을 불러오는 중입니다...")
        self.top100_tree.delete(*self.top100_tree.get_children())

        worker = threading.Thread(target=self._top100_worker, daemon=True)
        worker.start()

    def _top100_worker(self) -> None:
        try:
            top100 = fetch_us_top_market_cap_result(limit=100)
        except Exception as exc:
            self.after(0, self._show_top100_error, exc)
            return

        self.after(0, self._show_top100_result, top100.companies, top100.warning)

    def _show_top100_result(
        self,
        companies: list[MarketCapCompany],
        warning: str = "",
    ) -> None:
        self._populate_top100_table(companies)
        self.top100_status_var.set(
            warning
            or f"{len(companies)}개 종목을 불러왔습니다. 행을 클릭하면 바로 검색합니다."
        )
        self.top100_button.configure(state="normal")

    def _populate_top100_table(self, companies: list[MarketCapCompany]) -> None:
        self.top100_companies = list(companies)
        self.top100_tree.delete(*self.top100_tree.get_children())
        for company in companies:
            self.top100_tree.insert(
                "",
                "end",
                values=(company.rank, company.ticker, company.company, company.market_cap),
            )

    def _show_top100_error(self, exc: Exception) -> None:
        if isinstance(exc, MarketCapLoadError):
            message = str(exc)
        else:
            message = f"미국 시총 Top 100 목록을 불러오지 못했습니다: {exc}"

        self.top100_tree.delete(*self.top100_tree.get_children())
        self.top100_companies = []
        self.top100_status_var.set("목록을 불러오지 못했습니다.")
        self.top100_button.configure(state="normal")
        messagebox.showerror("Top 100 조회 실패", message)

    def run_top100_scan(self) -> None:
        if str(self.scan_button.cget("state")) == "disabled":
            return

        self.scan_button.configure(state="disabled")
        self.scan_save_button.configure(state="disabled")
        self.top100_button.configure(state="disabled")
        self.scan_status_label.configure(style="ScanStatus.TLabel")
        self.scan_status_var.set("Top 100과 보유 중인 종목을 통합 스캔하는 중입니다...")
        self.dashboard_cards["sell"]["value"].set("스캔 중")
        self.dashboard_cards["sell"]["note"].set("완료되면 결과가 표시됩니다")
        self.scan_tree.delete(*self.scan_tree.get_children())
        self.closed_tree.delete(*self.closed_tree.get_children())
        self.failure_tree.delete(*self.failure_tree.get_children())
        # The previous scan's tables are kept so a failed scan can show them again.
        self.latest_scan_date = None

        companies = list(self.top100_companies)
        active_scenarios = self.latest_active_scenarios.copy()
        worker = threading.Thread(
            target=self._top100_scan_worker,
            args=(companies, active_scenarios),
            daemon=True,
        )
        worker.start()

    def _top100_scan_worker(
        self,
        companies: list[MarketCapCompany],
        previous_active: pd.DataFrame,
    ) -> None:
        try:
            if not companies:
                self.after(0, self.scan_status_var.set, "Top 100 목록을 먼저 불러오는 중입니다...")
                top100 = fetch_us_top_market_cap_result(limit=100)
                companies = top100.companies
                self.after(
                    0,
                    self._show_top100_loaded_by_scan,
                    companies,
                    top100.warning,
                )

            self.after(0, self.scan_status_var.set, "S&P500 주봉 데이터를 갱신하는 중입니다...")
            try:
                sp500_data, sp500_load = load_sp500_context(
                    force_refresh=True,
                    max_cache_age_seconds=None,
                )
                sp500_warning = sp500_load.warning
            except Exception as exc:
                sp500_data = pd.DataFrame()
                sp500_warning = f"S&P500 상태 확인 실패: {exc}"

            scan_date = market_today()
            # The watchlist is scanned and tracked like the Top 100, but the
            # sold-case history covers the Top 100 only.
            scan_universe = merge_scan_universe(
                [*companies, *watchlist_companies(load_watchlist(), companies)],
                previous_active,
            )
            events, active_rows, closed_results, failures, cases_by_ticker = (
                self._scan_companies(
                    scan_universe,
                    scan_date,
                    previous_active,
                    progress_label="스캔 중",
                )
            )

            if failures:
                time.sleep(2)
                retry_companies = [failure["company"] for failure in failures]
                (
                    retry_events,
                    retry_active,
                    retry_closed,
                    retry_failures,
                    retry_cases,
                ) = self._scan_companies(
                    retry_companies,
                    scan_date,
                    previous_active,
                    progress_label="실패 종목 재시도 중",
                )
                events.extend(retry_events)
                active_rows.extend(retry_active)
                closed_results.extend(retry_closed)
                cases_by_ticker.update(retry_cases)
                failures = retry_failures

            failed_tickers = {
                failure["company"].ticker
                for failure in failures
            }
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
            events_df = prioritize_scan_events(events_df)
            active_df = _sorted_frame(
                active_rows,
                ACTIVE_SCENARIO_COLUMNS,
                by=["순위", "티커"],
                ascending=[True, True],
            ).drop_duplicates(subset=["티커"], keep="last")
            active_df = prioritize_active_scenarios(active_df)
            active_df = annotate_sp500_status(
                active_df,
                sp500_data,
                use_latest=True,
            )
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
            closed_scenarios_df = annotate_sp500_status(
                build_closed_scenario_history(
                    companies,
                    cases_by_ticker,
                    previous=self.latest_closed_scenarios,
                    failed_tickers=failed_tickers,
                ),
                sp500_data,
                reference_date_columns=("매도일",),
            )
        except Exception as exc:
            self.after(0, self._show_scan_error, exc)
            return

        # Saving is separate so a file left open in Excel cannot discard the scan.
        scanned_at = pd.Timestamp.now().floor("s")
        unsaved_state = (
            active_df,
            closed_scenarios_df,
            events_df,
            closed_df,
            failures_df,
            scanned_at,
        )
        save_warning = ""
        try:
            save_scan_state(*unsaved_state)
            unsaved_state = None
        except OSError as exc:
            save_warning = describe_save_error(exc)

        self.after(
            0,
            self._show_scan_result,
            events_df,
            active_df,
            closed_df,
            closed_scenarios_df,
            failures_df,
            scan_date,
            sp500_data,
            sp500_warning,
            unsaved_state,
            save_warning,
            scanned_at,
        )

    def _show_top100_loaded_by_scan(
        self,
        companies: list[MarketCapCompany],
        warning: str = "",
    ) -> None:
        self._populate_top100_table(companies)
        self.top100_status_var.set(
            warning
            or f"{len(companies)}개 종목을 불러왔습니다. 이 목록을 기준으로 스캔합니다."
        )

    def _scan_companies(
        self,
        companies: list[MarketCapCompany],
        scan_date: pd.Timestamp,
        previous_active: pd.DataFrame,
        progress_label: str,
    ) -> tuple[
        list[dict[str, object]],
        list[dict[str, object]],
        list[dict[str, object]],
        list[dict[str, object]],
        dict[str, pd.DataFrame],
    ]:
        events: list[dict[str, object]] = []
        active_rows: list[dict[str, object]] = []
        closed_results: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        cases_by_ticker: dict[str, pd.DataFrame] = {}
        total = len(companies)
        previous_by_ticker = {
            str(row["티커"]).upper(): row
            for _, row in previous_active.iterrows()
        }
        last_scan_date = latest_scan_date(previous_active)

        def scan_one(company: MarketCapCompany):
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
            summary = summarize_ticker_cases(
                company,
                cases,
                buys,
                full_table,
                scan_date,
                previous_active=previous_by_ticker.get(company.ticker.upper()),
                last_scan_date=last_scan_date,
            )
            return cases, summary

        # Downloads dominate the scan time, so fetch several tickers at once.
        # Results are still collected in ranking order.
        with ThreadPoolExecutor(max_workers=SCAN_DOWNLOAD_WORKERS) as executor:
            futures = [executor.submit(scan_one, company) for company in companies]
            for index, (company, future) in enumerate(zip(companies, futures), start=1):
                self.after(
                    0,
                    self.scan_status_var.set,
                    f"{progress_label}... {index}/{total} {company.ticker}",
                )
                try:
                    cases, summary = future.result()
                except Exception as exc:
                    failures.append({"company": company, "error": str(exc)})
                    continue
                ticker_events, active_row, ticker_closed = summary
                cases_by_ticker[company.ticker.upper()] = cases
                events.extend(ticker_events)
                closed_results.extend(ticker_closed)
                if active_row is not None:
                    active_rows.append(active_row)

        return events, active_rows, closed_results, failures, cases_by_ticker

    def _show_scan_result(
        self,
        events: pd.DataFrame,
        active_scenarios: pd.DataFrame,
        closed_results: pd.DataFrame,
        closed_scenarios: pd.DataFrame,
        failures: pd.DataFrame,
        scan_date: pd.Timestamp,
        sp500_data: pd.DataFrame,
        sp500_warning: str,
        unsaved_state: tuple[object, ...] | None = None,
        save_warning: str = "",
        scanned_at: pd.Timestamp | None = None,
    ) -> None:
        self.unsaved_scan_state = unsaved_state
        self.last_scan_time = scanned_at if scanned_at is not None else pd.Timestamp.now()
        self.latest_scan_events = events.copy()
        self.latest_active_scenarios = active_scenarios.copy()
        self.latest_closed_results = closed_results.copy()
        self.latest_closed_scenarios = closed_scenarios.copy()
        self.latest_scan_failures = failures.copy()
        self.latest_scan_date = scan_date
        self.latest_sp500_data = sp500_data.copy()
        self.latest_sp500_warning = sp500_warning
        self._populate_scan_tables()
        self._populate_active_table()
        self._refresh_closed_scenario_view()
        self._refresh_dashboard()

        failed_tickers = ", ".join(failures["티커"].tolist()[:8]) if not failures.empty else ""
        failed_suffix = f": {failed_tickers}" if failed_tickers else ""
        if len(failures) > 8:
            failed_suffix += "..."

        stage_counts = events["단계"].value_counts() if not events.empty else {}
        sell_count = int(stage_counts.get(SELL_STAGE, 0))
        market_suffix = f" / {sp500_warning}" if sp500_warning else ""
        self.scan_status_var.set(
            f"스캔 완료 | 매도 신호 {sell_count}개 / "
            f"추가매수 {int(stage_counts.get(ADD_BUY_STAGE, 0))}개 / "
            f"신규 1차 매수 {int(stage_counts.get(FIRST_BUY_STAGE, 0))}개 / "
            f"보유 중 {len(active_scenarios)}개 / 데이터 오류 {len(failures)}개{failed_suffix}. "
            f"필요하면 스캔 저장하기를 눌러 CSV로 저장하세요.{market_suffix}"
        )
        self.scan_status_label.configure(
            style="ScanAlert.TLabel" if sell_count > 0 else "ScanStatus.TLabel"
        )
        if not events.empty:
            self.scan_notebook.select(0)
        self.scan_button.configure(state="normal")
        self.scan_save_button.configure(state="normal")
        self.top100_button.configure(state="normal")
        if save_warning:
            self.scan_status_var.set(
                f"스캔 완료, 저장 실패: {save_warning}  |  {self.scan_status_var.get()}"
            )
            messagebox.showwarning(
                "스캔 결과 저장 실패",
                "스캔은 완료되어 화면에 표시했지만 결과 파일을 저장하지 못했습니다.\n\n"
                + save_warning
                + "\n\n파일을 닫은 뒤 '스캔 저장하기'를 누르면 다시 저장합니다.",
            )

    def _populate_scan_tables(self) -> None:
        """Fill the signal, sell and error tabs from the latest scan."""
        scan_display = scanner_table_for_display(
            self.latest_scan_events,
            SCAN_EVENT_DISPLAY_COLUMNS,
        )
        populate_table(self.scan_tree, scan_display)
        for item, (_, row) in zip(self.scan_tree.get_children(), scan_display.iterrows()):
            tag = scan_event_tag(row.get("단계"))
            self.scan_tree.item(item, tags=(tag,) if tag else ())
        populate_table(
            self.closed_tree,
            scanner_table_for_display(
                self.latest_closed_results,
                CLOSED_RESULT_DISPLAY_COLUMNS,
            ),
        )
        populate_table(self.failure_tree, self.latest_scan_failures)

    def _populate_active_table(self) -> None:
        active_display = scanner_table_for_display(
            self.latest_active_scenarios,
            ACTIVE_SCENARIO_DISPLAY_COLUMNS,
        )
        populate_table(self.active_tree, active_display)
        for item, (_, row) in zip(self.active_tree.get_children(), active_display.iterrows()):
            tag = active_scenario_tag(row.get("현재상태"), row.get("매수차수"))
            self.active_tree.item(item, tags=(tag,) if tag else ())

    def _refresh_closed_scenario_view(self) -> None:
        display = self.latest_closed_scenarios.reindex(
            columns=CLOSED_SCENARIO_DISPLAY_COLUMNS
        )
        populate_table(self.closed_scenario_tree, display)
        for item, (_, row) in zip(
            self.closed_scenario_tree.get_children(), display.iterrows()
        ):
            tag = history_case_tag("매도 완료", row.get("실수익률"))
            self.closed_scenario_tree.item(item, tags=(tag,) if tag else ())

    def _show_restored_scan(self) -> None:
        """Show the tables saved by the previous scan (app start, before a scan)."""
        self._populate_scan_tables()
        self.scan_status_var.set(
            f"마지막 스캔 결과입니다 ({self.last_scan_time:%m/%d %H:%M} 기준). "
            "최신 결과를 보려면 통합 스캔을 눌러 주세요."
        )

    def _show_scan_error(self, exc: Exception) -> None:
        if isinstance(exc, MarketCapLoadError):
            message = str(exc)
        else:
            message = f"Top 100 스캔 중 오류가 발생했습니다: {exc}"

        if self.last_scan_time is not None:
            self._show_restored_scan()
        self.scan_status_var.set(message)
        self.scan_status_label.configure(style="ScanStatus.TLabel")
        self.scan_button.configure(state="normal")
        self.scan_save_button.configure(state="disabled")
        self.top100_button.configure(state="normal")
        self._refresh_dashboard()
        messagebox.showerror("Top 100 스캔 실패", message)

    def save_latest_scan(self) -> None:
        if self.latest_scan_date is None:
            messagebox.showinfo("저장할 스캔 없음", "먼저 통합 스캔을 실행해 주세요.")
            return

        try:
            if self.unsaved_scan_state is not None:
                # Retry the state files that failed to save after the scan.
                save_scan_state(*self.unsaved_scan_state)
                self.unsaved_scan_state = None
            saved_paths = save_tracker_scan_outputs(
                self.latest_scan_events,
                self.latest_active_scenarios,
                self.latest_closed_results,
                self.latest_scan_failures,
                self.latest_scan_date,
            )
            saved_paths += (
                save_closed_scenarios(
                    self.latest_closed_scenarios,
                    DOWNLOADS_DIR
                    / f"TFMR_closed_scenarios_{self.latest_scan_date:%Y-%m-%d}.csv",
                ),
            )
        except OSError as exc:
            message = describe_save_error(exc)
            self.scan_status_var.set(f"저장 실패: {message}")
            messagebox.showerror("스캔 결과 저장 실패", message)
            return
        self.scan_status_var.set(
            "스캔 결과 저장 완료: " + " / ".join(str(path) for path in saved_paths)
        )
