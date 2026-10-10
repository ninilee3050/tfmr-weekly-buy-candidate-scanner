"""Trade history table linked to the chart window."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from chart_preview import ChartPreviewWindow
from market_context import sp500_status_at
from scanner import OUTCOME_SOLD
from gui.formatting import history_case_tag
from gui.scan_results import trade_case_position


class HistoryChartMixin:
    """Trade history table linked to the chart window. Mixed into BuyPointApp; relies on its attributes."""

    def _apply_history_tags(
        self,
        data: pd.DataFrame,
        tree: ttk.Treeview | None = None,
    ) -> None:
        tree = tree or self.buy_tree
        for item, (_, row) in zip(tree.get_children(), data.iterrows()):
            tag = history_case_tag(row.get("결과"), row.get("수익률"))
            tree.item(item, tags=(tag,) if tag else ())

    def _on_history_double_click(self, event) -> None:
        item = self.buy_tree.identify_row(event.y)
        if not item:
            return
        self.buy_tree.selection_set(item)
        self._show_selected_history_case(open_window=True)

    def _on_history_select(self, _event=None) -> None:
        if self._syncing_chart_history_selection:
            return
        if self._chart_is_open():
            selected = self.buy_tree.selection()
            if selected:
                selected_position = self._history_case_position(selected[0])
                chart_position = trade_case_position(
                    self.current_trade_cases,
                    self.chart_window.cycle,
                )
                if selected_position == chart_position:
                    return
            self._show_selected_history_case(open_window=False)

    def _show_selected_history_case(self, open_window: bool) -> None:
        selected = self.buy_tree.selection()
        if not selected or self.current_trade_cases.empty:
            return
        position = self._history_case_position(selected[0])
        if not 0 <= position < len(self.current_trade_cases):
            return
        if open_window or self._chart_is_open():
            self._show_chart(self.current_trade_cases.iloc[position])

    def _latest_case(self) -> pd.Series | None:
        if self.current_trade_cases.empty:
            return None
        return self.current_trade_cases.iloc[-1]

    def _case_for_first_buy_date(
        self,
        first_buy_date: pd.Timestamp | None,
    ) -> pd.Series | None:
        if first_buy_date is None:
            return None
        position = trade_case_position(
            self.current_trade_cases,
            pd.Series({"FirstBuyDate": first_buy_date}),
        )
        if position is None:
            return None
        return self.current_trade_cases.iloc[position]

    def _show_chart(self, case: pd.Series | None) -> None:
        if not self.current_ticker or self.current_chart_data.empty:
            return
        position = trade_case_position(self.current_trade_cases, case)
        if not self._chart_is_open():
            self.chart_window = ChartPreviewWindow(
                self,
                on_close=self._on_chart_closed,
                on_navigate=self._navigate_chart_history,
                theme_mode=self.theme_mode,
            )
        try:
            self.chart_window.show_cycle(
                self.current_ticker,
                self.current_chart_data,
                case,
                company=self.current_company,
                rank_text=self.current_rank_text,
                navigation_index=position,
                navigation_total=len(self.current_trade_cases),
                sp500_summary=self._sp500_summary_for_case(case),
                sp500_data=self.current_sp500_data,
                sp500_warning=self.current_sp500_warning,
            )
            if position is not None:
                self._select_history_position(position)
        except ValueError as exc:
            messagebox.showerror("차트 미리보기 오류", str(exc))

    def _sp500_summary_for_case(self, case: pd.Series | None) -> str:
        """Market state at the sell week of a sold case, otherwise the latest."""
        reference_date = None
        if case is not None and case.get("Outcome") == OUTCOME_SOLD:
            reference_date = case.get("SellDate")
        return sp500_status_at(self.current_sp500_data, reference_date).summary

    def _navigate_chart_history(self, direction: int) -> None:
        if self.current_trade_cases.empty or not self._chart_is_open():
            return
        current = trade_case_position(
            self.current_trade_cases,
            self.chart_window.cycle,
        )
        if current is None:
            current = len(self.current_trade_cases) - 1
        target = min(
            len(self.current_trade_cases) - 1,
            max(0, current + (-1 if direction < 0 else 1)),
        )
        if target == current:
            return
        self._show_chart(self.current_trade_cases.iloc[target])

    def _history_case_position(self, item: str) -> int:
        """Map a history table row (newest first) to its trade-case position."""
        return len(self.buy_tree.get_children()) - 1 - self.buy_tree.index(item)

    def _select_history_position(self, position: int) -> None:
        children = self.buy_tree.get_children()
        if position < 0 or position >= len(children):
            return
        item = children[len(children) - 1 - position]
        self._syncing_chart_history_selection = True
        try:
            self.buy_tree.selection_set(item)
            self.buy_tree.focus(item)
            self.buy_tree.see(item)
        finally:
            self._syncing_chart_history_selection = False

    def _chart_is_open(self) -> bool:
        if self.chart_window is None:
            return False
        try:
            return bool(self.chart_window.winfo_exists())
        except tk.TclError:
            return False

    def _on_chart_closed(self) -> None:
        self.chart_window = None
