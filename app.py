from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd

from chart_preview import ChartPreviewWindow
from market_cap_provider import MarketCapCompany
from scenario_tracker import (
    ACTIVE_SCENARIO_COLUMNS,
    CLOSED_RESULT_COLUMNS,
    SCAN_EVENT_COLUMNS,
    load_active_scenarios,
)
from ui_theme import configure_ui_fonts, load_theme, update_settings
from gui.config import (
    ACTIVE_SCENARIOS_TAB,
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    MIN_WINDOW_SIZE,
    OUTPUT_DIR,
    SCAN_FAILURE_COLUMNS,
    UI_SETTINGS_PATH,
)
from gui.scan_results import prioritize_active_scenarios
from gui.storage import load_closed_scenarios, load_last_scan
from gui.theme import ThemeMixin
from gui.tooltips import HoverTooltip
from gui.layout import LayoutMixin
from gui.cards import CardsMixin
from gui.scan import ScanMixin
from gui.search import SearchMixin
from gui.history import HistoryChartMixin
from gui.watchlist_tab import WatchlistMixin


class BuyPointApp(
    ThemeMixin,
    LayoutMixin,
    CardsMixin,
    ScanMixin,
    SearchMixin,
    HistoryChartMixin,
    WatchlistMixin,
    tk.Tk,
):
    """Main window. Each mixin holds one area of the screen."""

    def __init__(self) -> None:
        super().__init__()
        self.ui_font_family = configure_ui_fonts(self)
        self.title("TFMR 매매 시나리오 스캐너")
        self.minsize(*MIN_WINDOW_SIZE)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.theme_mode = load_theme(UI_SETTINGS_PATH)
        self.style = ttk.Style(self)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self._apply_theme()

        self.ticker_var = tk.StringVar()
        self.status_var = tk.StringVar(value="티커를 입력해 주세요.")
        self.top100_status_var = tk.StringVar(value="목록을 불러오려면 버튼을 눌러 주세요.")
        self.scan_status_var = tk.StringVar(value="통합 스캔을 실행하려면 버튼을 눌러 주세요.")
        self.ticker_profile_var = tk.StringVar(
            value="매매 기록을 보려면 종목을 검색해 주세요."
        )
        self.top100_companies: list[MarketCapCompany] = []
        self.latest_scan_events = pd.DataFrame(columns=SCAN_EVENT_COLUMNS)
        startup_warnings: list[str] = []
        try:
            saved_active = load_active_scenarios()
        except Exception as exc:
            saved_active = pd.DataFrame(columns=ACTIVE_SCENARIO_COLUMNS)
            startup_warnings.append(f"보유 중 파일을 읽지 못했습니다: {exc}")
        self.latest_active_scenarios = prioritize_active_scenarios(saved_active)
        self.latest_closed_results = pd.DataFrame(columns=CLOSED_RESULT_COLUMNS)
        try:
            self.latest_closed_scenarios = load_closed_scenarios()
        except Exception as exc:
            self.latest_closed_scenarios = pd.DataFrame(
                columns=CLOSED_SCENARIO_DISPLAY_COLUMNS
            )
            startup_warnings.append(f"매도 완료 파일을 읽지 못했습니다: {exc}")
        # Scan results that could not be written, kept for "스캔 저장하기".
        self.unsaved_scan_state: tuple[object, ...] | None = None
        # Local time of the latest scan, restored from the previous session.
        self.last_scan_time: pd.Timestamp | None = None
        self.latest_scan_failures = pd.DataFrame(columns=SCAN_FAILURE_COLUMNS)
        restored_scan = load_last_scan()
        if restored_scan is not None:
            (
                self.latest_scan_events,
                self.latest_closed_results,
                self.latest_scan_failures,
                self.last_scan_time,
            ) = restored_scan
        self.latest_scan_date: pd.Timestamp | None = None
        self.current_ticker: str | None = None
        self.current_company = ""
        self.current_rank_text = ""
        self.current_chart_data = pd.DataFrame()
        self.current_trade_cases = pd.DataFrame()
        self.current_sp500_data = pd.DataFrame()
        self.current_sp500_warning = ""
        self.latest_sp500_data = pd.DataFrame()
        self.latest_sp500_warning = ""
        self.chart_window: ChartPreviewWindow | None = None
        self._syncing_chart_history_selection = False
        self.open_chart_after_search = False
        self.pending_chart_first_buy_date: pd.Timestamp | None = None
        self.search_requested_while_busy = False
        self.term_tooltip = HoverTooltip(self, self.ui_font_family)

        self._build_layout()
        self._populate_active_table()
        self._refresh_closed_scenario_view()
        if self.last_scan_time is not None:
            self._show_restored_scan()
        self._refresh_dashboard()
        saved_tab = self._saved_window.get("tab")
        if isinstance(saved_tab, int) and 0 <= saved_tab < self.scan_notebook.index("end"):
            self.scan_notebook.select(saved_tab)
        elif not self.latest_active_scenarios.empty:
            # No scan has run yet, so start on the held cases, not an empty tab.
            self.scan_notebook.select(ACTIVE_SCENARIOS_TAB)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        if startup_warnings:
            self.after(200, self._show_startup_warnings, startup_warnings)

    def _on_close(self) -> None:
        try:
            update_settings(UI_SETTINGS_PATH, window=self._window_state())
        except (OSError, tk.TclError):
            pass  # Remembering the layout is a convenience; never block closing.
        self.destroy()

    def _show_startup_warnings(self, warnings: list[str]) -> None:
        messagebox.showwarning(
            "저장 파일 읽기 실패",
            "\n\n".join(warnings)
            + "\n\n빈 상태로 시작합니다. 다음 통합 스캔이 끝나면 이 파일은 새 결과로 "
            "바뀌므로, 필요하면 스캔 전에 outputs 폴더의 파일을 따로 복사해 두세요.",
        )


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        # Packaged exe: keep data/ and outputs/ beside the exe however it is started.
        os.chdir(Path(sys.executable).resolve().parent)
    app = BuyPointApp()
    if len(sys.argv) > 1:
        # "app.py NVDA" opens with that ticker searched.
        app.ticker_var.set(sys.argv[1])
        app.after(300, app.run_search)
    app.mainloop()
