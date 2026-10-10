"""Signal history table linked to the chart window."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from chart_strength import chart_strength_detail_key
from chart_preview import ChartPreviewWindow
from market_context import sp500_summary_for_cycle
from ui_theme import theme_palette
from gui.formatting import history_cycle_tag
from gui.scan_results import signal_cycle_position


class HistoryChartMixin:
    """Signal history table linked to the chart window. Mixed into BuyPointApp; relies on its attributes."""

    def _apply_history_tags(
        self,
        data: pd.DataFrame,
        tree: ttk.Treeview | None = None,
    ) -> None:
        tree = tree or self.buy_tree
        for item, (_, row) in zip(tree.get_children(), data.iterrows()):
            tag = history_cycle_tag(
                row.get("결과"),
                row.get("3개월후 수익률"),
                row.get("6개월후 수익률"),
                row.get("9개월후 수익률"),
                row.get("12개월후 수익률"),
            )
            tree.item(item, tags=(tag,) if tag else ())

    def _bind_chart_strength_tooltip(
        self,
        tree: ttk.Treeview,
        signal_date_column: str,
        ticker_column: str | None = "티커",
    ) -> None:
        tree.bind(
            "<Motion>",
            lambda event, source=tree, date_column=signal_date_column,
            ticker_name=ticker_column: (
                self._on_chart_strength_motion(
                    event,
                    source,
                    date_column,
                    ticker_name,
                )
            ),
            add="+",
        )
        for sequence in ("<Leave>", "<ButtonPress>", "<MouseWheel>"):
            tree.bind(sequence, self._hide_chart_strength_tooltip, add="+")

    def _on_chart_strength_motion(
        self,
        event,
        tree: ttk.Treeview,
        signal_date_column: str,
        ticker_column: str | None = "티커",
    ) -> None:
        item = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not item or not column_id or tree.identify_region(event.x, event.y) != "cell":
            self._hide_chart_strength_tooltip()
            return

        try:
            column_index = int(column_id.removeprefix("#")) - 1
            column_name = tree["columns"][column_index]
        except (ValueError, IndexError, tk.TclError):
            self._hide_chart_strength_tooltip()
            return
        if column_name != "차트 강도":
            self._hide_chart_strength_tooltip()
            return

        ticker = (
            tree.set(item, ticker_column)
            if ticker_column
            else (self.current_ticker or "")
        )
        signal_date = tree.set(item, signal_date_column)
        detail = self.chart_strength_details.get(
            chart_strength_detail_key(ticker, signal_date)
        )
        if detail is None:
            self._hide_chart_strength_tooltip()
            return
        hover_item = (str(tree), item)
        if (
            self._chart_strength_hover_item == hover_item
            and self.chart_strength_tooltip.window
        ):
            return

        self._chart_strength_hover_item = hover_item
        self.chart_strength_tooltip.show(
            tree.winfo_rootx() + event.x + 14,
            tree.winfo_rooty() + event.y + 18,
            detail,
            theme_palette(self.theme_mode),
        )

    def _hide_chart_strength_tooltip(self, _event=None) -> None:
        self.chart_strength_tooltip.hide()
        self._chart_strength_hover_item = None

    def _on_history_double_click(self, event) -> None:
        item = self.buy_tree.identify_row(event.y)
        if not item:
            return
        self.buy_tree.selection_set(item)
        self._show_selected_history_cycle(open_window=True)

    def _on_history_select(self, _event=None) -> None:
        if self._syncing_chart_history_selection:
            return
        if self._chart_is_open():
            selected = self.buy_tree.selection()
            if selected:
                selected_position = self._history_cycle_position(selected[0])
                chart_position = signal_cycle_position(
                    self.current_signal_cycles,
                    self.chart_window.cycle,
                )
                if selected_position == chart_position:
                    return
            self._show_selected_history_cycle(open_window=False)

    def _show_selected_history_cycle(self, open_window: bool) -> None:
        selected = self.buy_tree.selection()
        if not selected or self.current_signal_cycles.empty:
            return
        position = self._history_cycle_position(selected[0])
        if not 0 <= position < len(self.current_signal_cycles):
            return
        if open_window or self._chart_is_open():
            self._show_chart(self.current_signal_cycles.iloc[position])

    def _latest_cycle(self) -> pd.Series | None:
        if self.current_signal_cycles.empty:
            return None
        return self.current_signal_cycles.iloc[-1]

    def _cycle_for_first_signal_date(
        self,
        first_signal_date: pd.Timestamp | None,
    ) -> pd.Series | None:
        if first_signal_date is None or self.current_signal_cycles.empty:
            return None
        dates = pd.to_datetime(
            self.current_signal_cycles["FirstSignalDate"],
            errors="coerce",
        ).dt.normalize()
        matches = self.current_signal_cycles.loc[
            dates.eq(pd.Timestamp(first_signal_date).normalize())
        ]
        if matches.empty:
            return None
        return matches.iloc[-1]

    def _show_chart(self, cycle: pd.Series | None) -> None:
        if not self.current_ticker or self.current_chart_data.empty:
            return
        position = signal_cycle_position(self.current_signal_cycles, cycle)
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
                cycle,
                company=self.current_company,
                rank_text=self.current_rank_text,
                navigation_index=position,
                navigation_total=len(self.current_signal_cycles),
                chart_strength_summary=self._chart_strength_summary(cycle),
                sp500_summary=sp500_summary_for_cycle(
                    self.current_sp500_data,
                    cycle,
                ),
                sp500_data=self.current_sp500_data,
                sp500_warning=self.current_sp500_warning,
            )
            if position is not None:
                self._select_history_position(position)
        except ValueError as exc:
            messagebox.showerror("차트 미리보기 오류", str(exc))

    def _chart_strength_summary(self, cycle: pd.Series | None) -> str:
        if cycle is None:
            return "차트 강도: 해당 없음"
        outcome = str(cycle.get("Outcome", ""))
        if "대기" in outcome:
            return "차트 강도: 산정 대기"
        if outcome != "매수 성공":
            return "차트 강도: 해당 없음"

        detail = self.chart_strength_details.get(
            chart_strength_detail_key(
                self.current_ticker or "",
                cycle.get("ThirdDecisionDate"),
            )
        )
        if detail is None:
            return "차트 강도: 계산 불가  |  검토등급: 확인 필요"
        return (
            f"차트 강도: {detail.get('score_text', '계산 불가')}  |  "
            f"검토등급: {detail.get('grade', '확인 필요')}"
        )

    def _navigate_chart_history(self, direction: int) -> None:
        if self.current_signal_cycles.empty or not self._chart_is_open():
            return
        current = signal_cycle_position(
            self.current_signal_cycles,
            self.chart_window.cycle,
        )
        if current is None:
            current = len(self.current_signal_cycles) - 1
        target = min(
            len(self.current_signal_cycles) - 1,
            max(0, current + (-1 if direction < 0 else 1)),
        )
        if target == current:
            return
        self._show_chart(self.current_signal_cycles.iloc[target])

    def _history_cycle_position(self, item: str) -> int:
        """Map a history table row (newest first) to its signal-cycle position."""
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
