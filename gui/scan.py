"""Top 100 loading and the three-stage integrated scan."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from tkinter import messagebox

import pandas as pd

from chart_strength import (
    ChartStrengthReferenceError,
    annotate_completed_scenarios,
    annotate_pending_scenarios,
    annotate_scan_events,
    load_chart_strength_reference,
)
from benchmark_analytics import add_benchmark_returns
from csv_io import describe_save_error
from data_provider import is_weekend_traded, load_weekly_data
from indicators import calculate_indicators
from market_cap_provider import (
    MarketCapCompany,
    MarketCapLoadError,
    fetch_us_top_market_cap_result,
)
from market_context import annotate_sp500_status, load_sp500_context
from performance_analytics import build_all_field_outputs
from scanner import scan_signal_cycles
from sector_provider import load_sector_classifications
from scenario_tracker import (
    ACTIVE_SCENARIO_COLUMNS,
    CLOSED_RESULT_COLUMNS,
    SCAN_EVENT_COLUMNS,
    latest_scan_date,
    market_today,
    merge_scan_universe,
    preserve_failed_active_rows,
    summarize_ticker_cycles,
)
from watchlist import (
    clear_chart_strength_for_weekend_assets,
    load_watchlist,
    watchlist_companies,
)
from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    DOWNLOADS_DIR,
    SCAN_DOWNLOAD_WORKERS,
    SCAN_EVENT_DISPLAY_COLUMNS,
    SCAN_FAILURE_COLUMNS,
)
from gui.formatting import scanner_table_for_display
from gui.scan_results import (
    _failure_row,
    _sorted_frame,
    add_scan_performance_columns,
    add_sector_column,
    build_closed_scenario_history,
    prioritize_active_scenarios,
    prioritize_scan_events,
)
from gui.storage import (
    save_analytics_outputs,
    save_closed_scenarios,
    save_scan_state,
    save_tracker_scan_outputs,
)
from gui.tables import populate_table


class ScanMixin:
    """Top 100 loading and the three-stage integrated scan. Mixed into BuyPointApp; relies on its attributes."""

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
        self.scan_status_var.set("Top 100과 활성 시나리오를 통합 스캔하는 중입니다...")
        self.dashboard_cards["buy"]["value"].set("스캔 중")
        self.dashboard_cards["buy"]["note"].set("완료되면 결과가 표시됩니다")
        self.scan_tree.delete(*self.scan_tree.get_children())
        self.closed_tree.delete(*self.closed_tree.get_children())
        self.field_tree.delete(*self.field_tree.get_children())
        self.validation_tree.delete(*self.validation_tree.get_children())
        self.ranking_tree.delete(*self.ranking_tree.get_children())
        self.failure_tree.delete(*self.failure_tree.get_children())
        # The previous scan's tables are kept so a failed scan can show them again.
        self.latest_scan_date = None
        self.latest_classifications = pd.DataFrame()
        self.latest_cycles_by_ticker = {}
        self.chart_strength_details = {}
        self._hide_chart_strength_tooltip()
        self.latest_analysis_companies = []
        self.selected_field = None
        self.field_status_var.set("가격 데이터와 시나리오 성과를 계산하는 중입니다...")

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
            # The watchlist is scanned and tracked like the Top 100, but
            # ``companies`` stays Top 100 only for the field statistics.
            scan_universe = merge_scan_universe(
                [*companies, *watchlist_companies(load_watchlist(), companies)],
                previous_active,
            )
            (
                events,
                active_rows,
                closed_results,
                failures,
                cycles_by_ticker,
                full_tables_by_ticker,
            ) = self._scan_companies(
                scan_universe,
                scan_date,
                previous_active,
                progress_label="스캔 중",
            )

            if failures:
                time.sleep(2)
                retry_companies = [failure["company"] for failure in failures]
                (
                    retry_events,
                    retry_active,
                    retry_closed,
                    retry_failures,
                    retry_cycles,
                    retry_full_tables,
                ) = self._scan_companies(
                    retry_companies,
                    scan_date,
                    previous_active,
                    progress_label="실패 종목 재시도 중",
                )
                events.extend(retry_events)
                active_rows.extend(retry_active)
                closed_results.extend(retry_closed)
                cycles_by_ticker.update(retry_cycles)
                full_tables_by_ticker.update(retry_full_tables)
                failures = retry_failures

            failed_tickers = {
                failure["company"].ticker
                for failure in failures
            }
            active_rows.extend(
                preserve_failed_active_rows(previous_active, failed_tickers)
            )
            cycles_by_ticker = {
                ticker: add_benchmark_returns(
                    cycles,
                    full_tables_by_ticker[ticker],
                    sp500_data,
                    weekend_traded=is_weekend_traded(ticker),
                )
                for ticker, cycles in cycles_by_ticker.items()
            }

            events_df = _sorted_frame(
                events,
                SCAN_EVENT_COLUMNS,
                by=["신호일", "순위"],
                ascending=[False, True],
            )
            try:
                chart_strength_reference = load_chart_strength_reference()
                reference_error = None
            except ChartStrengthReferenceError as exc:
                chart_strength_reference = None
                reference_error = str(exc)
            events_df, chart_strength_details = annotate_scan_events(
                events_df,
                full_tables_by_ticker,
                chart_strength_reference,
                reference_error=reference_error,
            )
            events_df = clear_chart_strength_for_weekend_assets(events_df)
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
            active_df = annotate_pending_scenarios(active_df)
            active_df = annotate_sp500_status(
                active_df,
                sp500_data,
                use_latest=True,
            )
            closed_df = _sorted_frame(
                closed_results,
                CLOSED_RESULT_COLUMNS,
                by=["종료일", "순위"],
                ascending=[False, True],
            )
            failures_df = pd.DataFrame(
                [_failure_row(failure["company"], failure["error"]) for failure in failures],
                columns=SCAN_FAILURE_COLUMNS,
            )

            self.after(0, self.scan_status_var.set, "종목별 섹터·산업 정보를 확인하는 중입니다...")
            classifications = load_sector_classifications(
                (company.ticker for company in scan_universe),
                progress_callback=lambda index, total, ticker: self.after(
                    0,
                    self.scan_status_var.set,
                    f"분야 정보 확인 중... {index}/{total} {ticker}",
                ),
            )
            events_df = add_sector_column(events_df, classifications)
            active_df = add_sector_column(active_df, classifications)
            closed_df = add_sector_column(closed_df, classifications)
            closed_scenarios_df = build_closed_scenario_history(
                companies,
                cycles_by_ticker,
                classifications,
                previous=self.latest_closed_scenarios,
                failed_tickers=failed_tickers,
            )
            closed_df, closed_chart_strength_details = (
                annotate_completed_scenarios(
                    closed_df,
                    full_tables_by_ticker,
                    chart_strength_reference,
                    reference_error=reference_error,
                )
            )
            closed_df = annotate_sp500_status(
                closed_df,
                sp500_data,
                reference_date_columns=("3차판정일", "종료일", "2차신호일"),
            )
            closed_scenarios_df, history_chart_strength_details = (
                annotate_completed_scenarios(
                    closed_scenarios_df,
                    full_tables_by_ticker,
                    chart_strength_reference,
                    reference_error=reference_error,
                )
            )
            closed_scenarios_df = annotate_sp500_status(
                closed_scenarios_df,
                sp500_data,
                reference_date_columns=("3차판정일", "2차신호일", "1차신호일"),
            )
            chart_strength_details.update(closed_chart_strength_details)
            chart_strength_details.update(history_chart_strength_details)

            sector_output, industry_output, ranking_output = build_all_field_outputs(
                companies,
                cycles_by_ticker,
                classifications,
            )
            events_df = add_scan_performance_columns(
                events_df,
                companies,
                cycles_by_ticker,
                classifications,
                sector_output,
            )
            active_df = add_scan_performance_columns(
                active_df,
                companies,
                cycles_by_ticker,
                classifications,
                sector_output,
            )
        except Exception as exc:
            self.after(0, self._show_scan_error, exc)
            return

        # Saving is separate so a file left open in Excel cannot discard the scan.
        scanned_at = pd.Timestamp.now().floor("s")
        unsaved_state = (
            sector_output,
            industry_output,
            ranking_output,
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
            chart_strength_details,
            active_df,
            closed_df,
            closed_scenarios_df,
            failures_df,
            scan_date,
            companies,
            cycles_by_ticker,
            classifications,
            sector_output,
            industry_output,
            ranking_output,
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
        dict[str, pd.DataFrame],
    ]:
        events: list[dict[str, object]] = []
        active_rows: list[dict[str, object]] = []
        closed_results: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []
        cycles_by_ticker: dict[str, pd.DataFrame] = {}
        full_tables_by_ticker: dict[str, pd.DataFrame] = {}
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
            cycles, full_table = scan_signal_cycles(
                calculated,
                weekend_traded=is_weekend_traded(company.ticker),
            )
            summary = summarize_ticker_cycles(
                company,
                cycles,
                full_table,
                scan_date,
                previous_active=previous_by_ticker.get(company.ticker.upper()),
                last_scan_date=last_scan_date,
            )
            return cycles, full_table, summary

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
                    cycles, full_table, summary = future.result()
                except Exception as exc:
                    failures.append({"company": company, "error": str(exc)})
                    continue
                ticker_events, active_row, ticker_closed = summary
                cycles_by_ticker[company.ticker.upper()] = cycles
                full_tables_by_ticker[company.ticker.upper()] = full_table
                events.extend(ticker_events)
                closed_results.extend(ticker_closed)
                if active_row is not None:
                    active_rows.append(active_row)

        return (
            events,
            active_rows,
            closed_results,
            failures,
            cycles_by_ticker,
            full_tables_by_ticker,
        )

    def _show_scan_result(
        self,
        events: pd.DataFrame,
        chart_strength_details: dict[tuple[str, str], dict[str, object]],
        active_scenarios: pd.DataFrame,
        closed_results: pd.DataFrame,
        closed_scenarios: pd.DataFrame,
        failures: pd.DataFrame,
        scan_date: pd.Timestamp,
        analysis_companies: list[MarketCapCompany],
        cycles_by_ticker: dict[str, pd.DataFrame],
        classifications: pd.DataFrame,
        sector_output: pd.DataFrame,
        industry_output: pd.DataFrame,
        ranking_output: pd.DataFrame,
        sp500_data: pd.DataFrame,
        sp500_warning: str,
        unsaved_state: tuple[object, ...] | None = None,
        save_warning: str = "",
        scanned_at: pd.Timestamp | None = None,
    ) -> None:
        self.unsaved_scan_state = unsaved_state
        self.last_scan_time = scanned_at if scanned_at is not None else pd.Timestamp.now()
        self.latest_scan_events = events.copy()
        self.chart_strength_details = dict(chart_strength_details)
        self.latest_active_scenarios = active_scenarios.copy()
        self.latest_closed_results = closed_results.copy()
        self.latest_closed_scenarios = closed_scenarios.copy()
        self.latest_scan_failures = failures.copy()
        self.latest_scan_date = scan_date
        self.latest_analysis_companies = list(analysis_companies)
        self.latest_cycles_by_ticker = {
            ticker: cycles.copy()
            for ticker, cycles in cycles_by_ticker.items()
        }
        self.latest_classifications = classifications.copy()
        self.latest_sector_performance = sector_output.copy()
        self.latest_industry_performance = industry_output.copy()
        self.latest_field_rankings = ranking_output.copy()
        self.latest_sp500_data = sp500_data.copy()
        self.latest_sp500_warning = sp500_warning
        scan_display = scanner_table_for_display(events, SCAN_EVENT_DISPLAY_COLUMNS)
        populate_table(self.scan_tree, scan_display)
        self._apply_scan_event_tags(scan_display)
        active_display = scanner_table_for_display(
            active_scenarios,
            ACTIVE_SCENARIO_DISPLAY_COLUMNS,
        )
        populate_table(self.active_tree, active_display)
        self._apply_active_scenario_tags(active_display)
        populate_table(
            self.closed_tree,
            scanner_table_for_display(closed_results, CLOSED_RESULT_DISPLAY_COLUMNS),
        )
        self._refresh_closed_scenario_view()
        populate_table(self.failure_tree, failures)
        self._refresh_field_analytics(reset_selection=True)
        self._refresh_signal_validation()
        self._refresh_dashboard()

        failed_tickers = ", ".join(failures["티커"].tolist()[:8]) if not failures.empty else ""
        failed_suffix = f": {failed_tickers}" if failed_tickers else ""
        if len(failures) > 8:
            failed_suffix += "..."

        first_count = int((events["단계"] == "1차 신호").sum()) if not events.empty else 0
        second_count = int((events["단계"] == "2차 신호").sum()) if not events.empty else 0
        second_rejection_count = int(
            (events["단계"] == "2차 폐기").sum()
        ) if not events.empty else 0
        third_count = int(
            ((events["단계"] == "3차 신호") & (events["결과"] == "매수 성공")).sum()
        ) if not events.empty else 0
        priority_review_count = int(
            (events.get("검토등급") == "우선검토").sum()
        ) if not events.empty and "검토등급" in events.columns else 0
        general_review_count = int(
            (events.get("검토등급") == "일반검토").sum()
        ) if not events.empty and "검토등급" in events.columns else 0
        failed_signal_count = int(
            ((events["단계"] == "3차 신호") & (events["결과"] == "실패")).sum()
        ) if not events.empty else 0
        market_suffix = f" / {sp500_warning}" if sp500_warning else ""
        self.scan_status_var.set(
            f"스캔 완료 | 즉시 확인: 3차 신호 {third_count}개 "
            f"(우선검토 {priority_review_count}개 / 일반검토 {general_review_count}개) / "
            f"출발 준비: 2차 신호 {second_count}개 / 관심 편입: 1차 신호 {first_count}개 / "
            f"2차 폐기 {second_rejection_count}개 / "
            f"신호 실패 {failed_signal_count}개 / "
            f"계속 관찰 {len(active_scenarios)}개 / 데이터 오류 {len(failures)}개{failed_suffix}. "
            f"필요하면 스캔 저장하기를 눌러 CSV로 저장하세요.{market_suffix}"
        )
        self.scan_status_label.configure(
            style="ScanAlert.TLabel" if third_count > 0 else "ScanStatus.TLabel"
        )
        if third_count > 0:
            self.scan_notebook.select(0)
            third_items = [
                item
                for item in self.scan_tree.get_children()
                if self.scan_tree.set(item, "단계") == "3차 신호"
                and self.scan_tree.set(item, "결과") == "매수 성공"
            ]
            if third_items:
                self.scan_tree.focus(third_items[0])
                self.scan_tree.see(third_items[0])
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

    def _show_restored_scan(self) -> None:
        """Show the tables saved by the previous scan (app start, before a scan)."""
        scan_display = scanner_table_for_display(
            self.latest_scan_events,
            SCAN_EVENT_DISPLAY_COLUMNS,
        )
        populate_table(self.scan_tree, scan_display)
        self._apply_scan_event_tags(scan_display)
        populate_table(
            self.closed_tree,
            scanner_table_for_display(
                self.latest_closed_results,
                CLOSED_RESULT_DISPLAY_COLUMNS,
            ),
        )
        populate_table(self.failure_tree, self.latest_scan_failures)
        self.scan_status_var.set(
            f"마지막 스캔 결과입니다 ({self.last_scan_time:%m/%d %H:%M} 기준). "
            "최신 결과를 보려면 3단계 통합 스캔을 눌러 주세요."
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
            messagebox.showinfo("저장할 스캔 없음", "먼저 3단계 통합 스캔을 실행해 주세요.")
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
            saved_paths += save_analytics_outputs(
                self.latest_sector_performance,
                self.latest_industry_performance,
                self.latest_field_rankings,
                output_dir=DOWNLOADS_DIR,
                date_suffix=self.latest_scan_date.strftime("%Y-%m-%d"),
            )
            saved_paths += (
                save_closed_scenarios(
                    self.latest_closed_scenarios,
                    DOWNLOADS_DIR
                    / f"MMRM_closed_scenarios_{self.latest_scan_date:%Y-%m-%d}.csv",
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
