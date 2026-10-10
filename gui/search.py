"""Single-ticker search and the clicks that start one."""

from __future__ import annotations

import threading
from tkinter import messagebox, ttk

import pandas as pd

from csv_io import describe_save_error
from data_provider import (
    DataLoadError,
    is_weekend_traded,
    load_weekly_data,
    normalize_ticker,
)
from indicators import calculate_indicators
from market_cap_provider import MarketCapCompany, load_saved_ranking
from market_context import load_sp500_context
from scanner import scan_trade_cases
from watchlist import WATCHLIST_RANK_START
from gui.config import TRADE_HISTORY_COLUMN_BOUNDS
from gui.scan_results import trade_history_display
from gui.storage import save_trade_case_outputs
from gui.tables import populate_table


class SearchMixin:
    """Single-ticker search and the clicks that start one. Mixed into BuyPointApp; relies on its attributes."""

    def _on_top100_select(self, _event) -> None:
        selected = self.top100_tree.selection()
        if not selected:
            return
        ticker = self.top100_tree.set(selected[0], "ticker")
        if not ticker:
            return
        self.pending_chart_first_buy_date = None
        self.ticker_var.set(ticker)
        self.run_search()

    def _on_scan_row_select(self, _event, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            return
        ticker = tree.set(selected[0], "티커")
        if not ticker:
            return
        self.pending_chart_first_buy_date = None
        self.ticker_var.set(ticker)
        self.run_search()

    def _on_closed_scenario_select(self, _event=None) -> None:
        selected = self.closed_scenario_tree.selection()
        if not selected:
            return
        item = selected[0]
        ticker = self.closed_scenario_tree.set(item, "티커")
        first_buy_date = self.closed_scenario_tree.set(item, "1차매수일")
        if not ticker or not first_buy_date:
            return
        self.pending_chart_first_buy_date = pd.Timestamp(first_buy_date)
        self.ticker_var.set(ticker)
        if self.current_ticker == ticker.upper() and not self.current_chart_data.empty:
            if self._chart_is_open():
                self._show_chart(
                    self._case_for_first_buy_date(
                        self.pending_chart_first_buy_date
                    )
                )
            return
        self.run_search()

    def _on_closed_scenario_double_click(self, event) -> None:
        item = self.closed_scenario_tree.identify_row(event.y)
        if not item:
            return
        self.closed_scenario_tree.selection_set(item)
        ticker = self.closed_scenario_tree.set(item, "티커")
        first_buy_date = self.closed_scenario_tree.set(item, "1차매수일")
        if not ticker or not first_buy_date:
            return

        self.pending_chart_first_buy_date = pd.Timestamp(first_buy_date)
        self.open_chart_after_search = True
        if self.current_ticker == ticker.upper() and not self.current_chart_data.empty:
            case = self._case_for_first_buy_date(
                self.pending_chart_first_buy_date
            )
            self._show_chart(case)
            self.open_chart_after_search = False
            self.pending_chart_first_buy_date = None

    def _on_ticker_double_click(
        self,
        event,
        tree: ttk.Treeview,
        ticker_column: str,
    ) -> None:
        item = tree.identify_row(event.y)
        if not item:
            return
        tree.selection_set(item)
        ticker = tree.set(item, ticker_column)
        if not ticker:
            return

        self.pending_chart_first_buy_date = None
        self.open_chart_after_search = True
        if (
            self.current_ticker == ticker.upper()
            and not self.current_chart_data.empty
        ):
            self._show_chart(self._latest_case())
            self.open_chart_after_search = False
            return

        self.ticker_var.set(ticker)
        self.run_search()

    def run_search(self) -> None:
        if str(self.search_button.cget("state")) == "disabled":
            # A search is running; the latest request runs once it finishes.
            self.search_requested_while_busy = True
            return
        self.search_requested_while_busy = False

        try:
            ticker = normalize_ticker(self.ticker_var.get())
        except ValueError as exc:
            messagebox.showinfo("입력 필요", str(exc))
            return

        self.search_button.configure(state="disabled")
        self.status_var.set(f"{ticker} 주봉 데이터를 불러오는 중입니다...")
        self.ticker_profile_var.set("매매 기록을 계산하는 중입니다...")
        self._set_summary_cards(None)

        company = self._company_for_ticker(ticker)
        worker = threading.Thread(
            target=self._search_worker,
            args=(ticker, company),
            daemon=True,
        )
        worker.start()

    def _company_for_ticker(self, ticker: str) -> MarketCapCompany:
        # Before the Top 100 is loaded in this session, the ranking saved by the
        # last scan still tells the company name and rank.
        for company in self.top100_companies or load_saved_ranking():
            if company.ticker.upper() == ticker.upper():
                return company
        return MarketCapCompany(
            rank=9999,
            ticker=ticker,
            company=ticker,
            market_cap="",
        )

    def _search_worker(self, ticker: str, company: MarketCapCompany) -> None:
        try:
            raw_data = load_weekly_data(
                ticker,
                include_current_week=True,
                force_refresh=True,
            )
            calculated = calculate_indicators(raw_data)
            cases, buys, full_table = scan_trade_cases(
                calculated,
                weekend_traded=is_weekend_traded(ticker),
            )
            try:
                case_path, _buy_path, _full_path = save_trade_case_outputs(
                    ticker, cases, buys, full_table
                )
                save_message = f"저장: {case_path}"
            except OSError as exc:
                # Show the result anyway when a CSV is open in Excel.
                save_message = f"저장 실패: {describe_save_error(exc)}"
            try:
                sp500_data, sp500_load = load_sp500_context(
                    expected_latest_date=full_table.index[-1],
                )
                sp500_warning = sp500_load.warning
            except Exception as exc:
                sp500_data = pd.DataFrame()
                sp500_warning = f"S&P500 상태 확인 실패: {exc}"
            history_display = trade_history_display(cases, sp500_data)
        except Exception as exc:
            self.after(0, self._show_error, ticker, exc)
            return

        self.after(
            0,
            self._show_result,
            ticker,
            cases,
            full_table,
            save_message,
            company,
            history_display,
            sp500_data,
            sp500_warning,
        )

    def _show_result(
        self,
        ticker: str,
        cases: pd.DataFrame,
        full_table: pd.DataFrame,
        save_message: str,
        company: MarketCapCompany,
        history_display: pd.DataFrame,
        sp500_data: pd.DataFrame,
        sp500_warning: str,
    ) -> None:
        self.current_ticker = ticker.upper()
        self.current_company = company.company
        self.current_rank_text = (
            f"시총 {company.rank}위" if company.rank < WATCHLIST_RANK_START else ""
        )
        self.current_chart_data = full_table.copy()
        self.current_trade_cases = cases.reset_index(drop=True).copy()
        self.current_sp500_data = sp500_data.copy()
        self.current_sp500_warning = sp500_warning
        # Newest case first; rows map back to cases via _history_case_position.
        history_rows = history_display.iloc[::-1]
        populate_table(
            self.buy_tree,
            history_rows,
            column_bounds=TRADE_HISTORY_COLUMN_BOUNDS,
            sortable=False,
        )
        self._apply_history_tags(history_rows)

        self.status_var.set(
            f"{ticker}: 매매 케이스 {len(cases)}개를 찾았습니다. {save_message}"
        )
        name = company.company if company.company.upper() != ticker.upper() else ""
        self.ticker_profile_var.set(
            "  |  ".join(
                part for part in (ticker, name, self.current_rank_text) if part
            )
        )
        self._set_summary_cards(cases)
        self.search_button.configure(state="normal")
        if self._take_queued_search(ticker):
            # The pending chart request belongs to the queued ticker.
            self.run_search()
            return

        target_case = self._case_for_first_buy_date(
            self.pending_chart_first_buy_date
        )
        if target_case is None:
            target_case = self._latest_case()

        if self._chart_is_open() or self.open_chart_after_search:
            # _show_chart also selects the matching history row.
            self._show_chart(target_case)
        self.open_chart_after_search = False
        self.pending_chart_first_buy_date = None

    def _show_error(self, ticker: str, exc: Exception) -> None:
        if isinstance(exc, DataLoadError):
            message = str(exc)
        else:
            message = f"{ticker} 처리 중 오류가 발생했습니다: {exc}"

        self.status_var.set(message)
        self.ticker_profile_var.set("매매 기록을 계산하지 못했습니다.")
        self._set_summary_cards(None)
        self.search_button.configure(state="normal")
        queued = self._take_queued_search(ticker)
        if not queued:
            self.open_chart_after_search = False
            self.pending_chart_first_buy_date = None
        messagebox.showerror("오류", message)
        if queued:
            self.run_search()

    def _take_queued_search(self, finished_ticker: str) -> bool:
        """Return True when a different ticker was requested during a search."""
        if not self.search_requested_while_busy:
            return False
        self.search_requested_while_busy = False
        try:
            requested = normalize_ticker(self.ticker_var.get())
        except ValueError:
            return False
        return requested != finished_ticker.upper()
