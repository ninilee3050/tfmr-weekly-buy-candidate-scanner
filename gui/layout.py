"""Window layout: panes, panels, tabs and tables."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ui_theme import load_settings
from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    HISTORY_LEGEND,
    SCAN_EVENT_DISPLAY_COLUMNS,
    SCAN_FAILURE_COLUMNS,
    STRONG_RETURN_PERCENT,
    TOP100_PANEL_WIDTH,
    TRADE_HISTORY_COLUMN_BOUNDS,
    TRADE_HISTORY_DISPLAY_COLUMNS,
    UI_SETTINGS_PATH,
)
from gui.tooltips import attach_heading_tooltips
from gui.tables import (
    WINDOW_GEOMETRY_PATTERN,
    _fit_table_columns_to_viewport,
    _table_required_width,
    default_sash_positions,
    populate_table,
    restored_window_placement,
    scaled_sash_positions,
)


class LayoutMixin:
    """Window layout: panes, panels, tabs and tables. Mixed into BuyPointApp; relies on its attributes."""

    def _build_layout(self) -> None:
        left_panel_width = TOP100_PANEL_WIDTH
        history_panel_width = _table_required_width(
            TRADE_HISTORY_DISPLAY_COLUMNS,
            TRADE_HISTORY_COLUMN_BOUNDS,
        )
        scanner_table_specs = (
            (SCAN_EVENT_DISPLAY_COLUMNS, None),
            (ACTIVE_SCENARIO_DISPLAY_COLUMNS, None),
            (CLOSED_RESULT_DISPLAY_COLUMNS, None),
            (CLOSED_SCENARIO_DISPLAY_COLUMNS, None),
            (SCAN_FAILURE_COLUMNS, None),
        )
        scanner_panel_width = max(
            _table_required_width(columns, column_bounds)
            for columns, column_bounds in scanner_table_specs
        )
        full_width = left_panel_width + history_panel_width + scanner_panel_width + 48
        screen_width, screen_height = self._screen_size()
        saved_window = load_settings(UI_SETTINGS_PATH).get("window")
        self._saved_window = saved_window if isinstance(saved_window, dict) else {}
        width, height, x, y = restored_window_placement(
            self._saved_window,
            full_width,
            820,
            screen_width,
            screen_height,
            virtual_bounds=self._virtual_screen_bounds(),
        )
        self.geometry(f"{width}x{height}+{x}+{y}")
        self._history_panel_width = history_panel_width
        self._scanner_panel_width = scanner_panel_width
        if "top100_visible" in self._saved_window:
            self.top100_visible = bool(self._saved_window["top100_visible"])
        else:
            # A wide enough screen shows all three areas; otherwise Top 100 starts folded.
            self.top100_visible = width >= full_width

        main_frame = ttk.Frame(self, padding=14)
        main_frame.pack(fill="both", expand=True)
        # Draggable dividers between the areas; the panes no longer force a width.
        self.main_panes = ttk.Panedwindow(main_frame, orient="horizontal")
        self.main_panes.pack(fill="both", expand=True)

        left_panel = ttk.LabelFrame(self.main_panes, text="미국 시총 Top 100", padding=6)
        left_panel.configure(width=left_panel_width)
        left_panel.grid_propagate(False)
        left_panel.rowconfigure(2, weight=1)
        left_panel.columnconfigure(0, weight=1)
        self.left_panel = left_panel

        self.top100_button = ttk.Button(
            left_panel,
            text="Top 100 불러오기",
            command=self.load_top100,
        )
        self.top100_button.grid(row=0, column=0, sticky="ew")

        top100_status = ttk.Label(
            left_panel,
            textvariable=self.top100_status_var,
            wraplength=330,
            padding=(0, 6, 0, 6),
        )
        top100_status.grid(row=1, column=0, sticky="ew")

        self.top100_tree = self._create_top100_table(left_panel)
        self.top100_tree.bind("<<TreeviewSelect>>", self._on_top100_select)
        self.top100_tree.bind(
            "<Double-1>",
            lambda event: self._on_ticker_double_click(event, self.top100_tree, "ticker"),
        )

        self.center_panel = ttk.Frame(self.main_panes, padding=(10, 0, 10, 0))
        self.center_panel.configure(width=history_panel_width)
        self.center_panel.grid_propagate(False)
        center_panel = self.center_panel
        center_panel.rowconfigure(4, weight=1)
        center_panel.columnconfigure(0, weight=1)

        search_frame = ttk.Frame(center_panel)
        search_frame.grid(row=0, column=0, sticky="ew")
        search_frame.columnconfigure(1, weight=1)

        self.top100_toggle_button = ttk.Button(
            search_frame,
            text=self._top100_toggle_text(),
            command=self.toggle_top100_panel,
        )
        self.top100_toggle_button.grid(row=0, column=0, padx=(0, 8), ipady=4)

        self.search_entry = ttk.Entry(
            search_frame,
            textvariable=self.ticker_var,
            font=(self.ui_font_family, 16),
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", ipady=6)
        self.search_entry.bind("<Return>", lambda _event: self.run_search())
        self.search_entry.focus_set()

        self.search_button = ttk.Button(
            search_frame,
            text="검색",
            command=self.run_search,
        )
        self.search_button.grid(row=0, column=2, padx=(8, 0), ipady=4)

        self.theme_button = ttk.Button(
            search_frame,
            text=self._theme_button_text(),
            command=self.toggle_theme,
        )
        self.theme_button.grid(row=0, column=3, padx=(8, 0), ipady=4)

        status_label = ttk.Label(
            center_panel,
            textvariable=self.status_var,
            padding=(0, 8, 0, 8),
        )
        status_label.grid(row=1, column=0, sticky="ew")
        self._wrap_to_width(status_label, center_panel, margin=30)

        summary_frame = ttk.LabelFrame(center_panel, text="선택 종목 매매 성과", padding=5)
        summary_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        summary_label = ttk.Label(summary_frame, textvariable=self.ticker_profile_var)
        summary_label.pack(anchor="w")
        self._wrap_to_width(summary_label, center_panel, margin=50)
        self._build_summary_cards(summary_frame)

        legend_frame = ttk.Frame(center_panel, padding=(0, 2, 0, 4))
        legend_frame.grid(row=3, column=0, sticky="ew")
        for key, label, _color_key in HISTORY_LEGEND:
            ttk.Label(
                legend_frame,
                text=label,
                style=f"Legend{key}.TLabel",
            ).pack(side="left", padx=(0, 4))
        ttk.Label(
            legend_frame,
            text=f"수익·손실이 {STRONG_RETURN_PERCENT:g}% 이상이면 진한 색입니다",
            style="LegendNote.TLabel",
        ).pack(side="left", padx=(6, 0))

        table_frame = ttk.LabelFrame(
            center_panel,
            text="매매 기록 (최신순 · 행 더블클릭: 차트 미리보기)",
            padding=4,
        )
        table_frame.grid(row=4, column=0, sticky="nsew")
        self.buy_tree = self._create_table(table_frame)
        self._configure_history_tree_tags()
        populate_table(
            self.buy_tree,
            pd.DataFrame(columns=TRADE_HISTORY_DISPLAY_COLUMNS),
            column_bounds=TRADE_HISTORY_COLUMN_BOUNDS,
            sortable=False,
        )
        self.buy_tree.bind("<<TreeviewSelect>>", self._on_history_select)
        self.buy_tree.bind("<Double-1>", self._on_history_double_click)

        self.scanner_panel = ttk.LabelFrame(
            self.main_panes,
            text="TFMR 매매 시나리오 스캐너",
            padding=6,
        )
        self.scanner_panel.configure(width=scanner_panel_width)
        self.scanner_panel.grid_propagate(False)
        if self.top100_visible:
            self.main_panes.add(self.left_panel, weight=0)
        self.main_panes.add(self.center_panel, weight=2)
        self.main_panes.add(self.scanner_panel, weight=3)
        self.after_idle(self._apply_initial_pane_widths)
        scanner_panel = self.scanner_panel
        scanner_panel.rowconfigure(3, weight=1)
        scanner_panel.columnconfigure(0, weight=1)

        scan_button_frame = ttk.Frame(scanner_panel)
        scan_button_frame.grid(row=0, column=0, sticky="ew")
        scan_button_frame.columnconfigure(0, weight=1)
        scan_button_frame.columnconfigure(1, weight=1)

        self.scan_button = ttk.Button(
            scan_button_frame,
            text="통합 스캔",
            command=self.run_top100_scan,
        )
        self.scan_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.scan_save_button = ttk.Button(
            scan_button_frame,
            text="스캔 저장하기",
            command=self.save_latest_scan,
            state="disabled",
        )
        self.scan_save_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._build_dashboard(scanner_panel)

        self.scan_status_label = ttk.Label(
            scanner_panel,
            textvariable=self.scan_status_var,
            padding=(0, 6, 0, 6),
            style="ScanStatus.TLabel",
        )
        self.scan_status_label.grid(row=2, column=0, sticky="ew")
        self._wrap_to_width(self.scan_status_label, scanner_panel, margin=40)

        self.scan_notebook = ttk.Notebook(scanner_panel)
        self.scan_notebook.grid(row=3, column=0, sticky="nsew")

        event_tab = ttk.Frame(self.scan_notebook)
        active_tab = ttk.Frame(self.scan_notebook)
        closed_tab = ttk.Frame(self.scan_notebook)
        closed_scenario_tab = ttk.Frame(self.scan_notebook)
        failure_tab = ttk.Frame(self.scan_notebook)
        watchlist_tab = ttk.Frame(self.scan_notebook)
        self.scan_notebook.add(event_tab, text="이번 스캔 신호")
        self.scan_notebook.add(active_tab, text="보유 중")
        self.scan_notebook.add(closed_tab, text="이번 스캔 매도")
        self.scan_notebook.add(closed_scenario_tab, text="매도 완료")
        self.scan_notebook.add(failure_tab, text="오류")
        self.scan_notebook.add(watchlist_tab, text="관심종목")

        self.scan_tree = self._create_table(event_tab)
        self.active_tree = self._create_table(active_tab)
        self._configure_signal_tree_tags(self.scan_tree)
        self._configure_signal_tree_tags(self.active_tree)
        self.closed_tree = self._create_table(closed_tab)
        self.closed_scenario_tree = self._create_table(closed_scenario_tab)
        self._configure_history_tree_tags(self.closed_scenario_tree)
        self.failure_tree = self._create_table(failure_tab)
        self._build_watchlist_tab(watchlist_tab)

        populate_table(self.scan_tree, pd.DataFrame(columns=SCAN_EVENT_DISPLAY_COLUMNS))
        populate_table(self.active_tree, pd.DataFrame(columns=ACTIVE_SCENARIO_DISPLAY_COLUMNS))
        populate_table(self.closed_tree, pd.DataFrame(columns=CLOSED_RESULT_DISPLAY_COLUMNS))
        populate_table(
            self.closed_scenario_tree,
            pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS),
        )
        populate_table(self.failure_tree, pd.DataFrame(columns=SCAN_FAILURE_COLUMNS))

        for tree in (self.scan_tree, self.active_tree, self.closed_tree):
            tree.bind(
                "<<TreeviewSelect>>",
                lambda event, source=tree: self._on_scan_row_select(event, source),
            )
            tree.bind(
                "<Double-1>",
                lambda event, source=tree: self._on_ticker_double_click(
                    event,
                    source,
                    "티커",
                ),
            )
        self.closed_scenario_tree.bind(
            "<<TreeviewSelect>>",
            self._on_closed_scenario_select,
        )
        self.closed_scenario_tree.bind(
            "<Double-1>",
            self._on_closed_scenario_double_click,
        )

    def _create_table(self, parent: tk.Widget) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, show="headings")
        attach_heading_tooltips(self.term_tooltip, tree)
        tree.bind(
            "<Configure>",
            lambda _event, source=tree: _fit_table_columns_to_viewport(source),
            add="+",
        )
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _screen_size(self) -> tuple[int, int]:
        return self.winfo_screenwidth(), self.winfo_screenheight()

    def _virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """Left, top, right, bottom of all monitors together (Windows virtual screen)."""
        left, top = self.winfo_vrootx(), self.winfo_vrooty()
        return left, top, left + self.winfo_vrootwidth(), top + self.winfo_vrootheight()

    def _top100_toggle_text(self) -> str:
        return "Top 100 닫기" if self.top100_visible else "Top 100 열기"

    def toggle_top100_panel(self) -> None:
        if self.top100_visible:
            self.main_panes.forget(self.left_panel)
        else:
            self.main_panes.insert(0, self.left_panel, weight=0)
        self.top100_visible = not self.top100_visible
        self.top100_toggle_button.configure(text=self._top100_toggle_text())
        self.after_idle(self._apply_default_pane_widths)

    def _apply_initial_pane_widths(self, attempts: int = 0) -> None:
        """Restore the maximized state and divider positions of the last session."""
        zoomed = bool(self._saved_window.get("zoomed"))
        if zoomed and self.state() != "zoomed":
            self.state("zoomed")
        self.update_idletasks()
        total = self.main_panes.winfo_width()
        # Maximizing resizes the window a moment later; wait for the real width
        # so the saved divider positions are scaled against it, not the old one.
        still_resizing = zoomed and self.winfo_width() < self.winfo_screenwidth() - 100
        if (total <= 1 or still_resizing) and attempts < 20:
            self.after(50, lambda: self._apply_initial_pane_widths(attempts + 1))
            return
        positions = scaled_sash_positions(
            self._saved_window.get("sashes"),
            self._saved_window.get("pane_width"),
            total,
            expected_count=2 if self.top100_visible else 1,
        )
        if positions is None:
            self._apply_default_pane_widths()
            return
        for index, position in enumerate(positions):
            self.main_panes.sashpos(index, position)

    def _window_state(self) -> dict[str, object]:
        """What to remember about the window for the next start."""
        state = dict(self._saved_window)
        zoomed = self.state() == "zoomed"
        match = WINDOW_GEOMETRY_PATTERN.match(self.geometry())
        if match and not zoomed:
            # While maximized, keep the size the window had before maximizing.
            width, height, x, y = (int(value) for value in match.groups())
            state.update(width=width, height=height, x=x, y=y)
        pane_count = 2 if self.top100_visible else 1
        state.update(
            zoomed=zoomed,
            top100_visible=self.top100_visible,
            sashes=[self.main_panes.sashpos(index) for index in range(pane_count)],
            pane_width=self.main_panes.winfo_width(),
            tab=self.scan_notebook.index("current"),
        )
        return state

    def _apply_default_pane_widths(self) -> None:
        self.update_idletasks()
        total = self.main_panes.winfo_width()
        if total <= 1:
            self.after(50, self._apply_default_pane_widths)
            return
        positions = default_sash_positions(
            total,
            self.top100_visible,
            TOP100_PANEL_WIDTH,
            self._history_panel_width,
            self._scanner_panel_width,
        )
        for index, position in enumerate(positions):
            self.main_panes.sashpos(index, position)

    @staticmethod
    def _wrap_to_width(label: ttk.Label, container: tk.Widget, margin: int) -> None:
        """Re-wrap a label's text whenever its area is resized."""
        container.bind(
            "<Configure>",
            lambda event: label.configure(wraplength=max(200, event.width - margin)),
            add="+",
        )

    def _create_top100_table(self, parent: tk.Widget) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        columns = ["rank", "ticker", "company", "market_cap"]
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("rank", text="순위")
        tree.heading("ticker", text="티커")
        tree.heading("company", text="회사명")
        tree.heading("market_cap", text="시가총액")
        tree.column("rank", width=52, minwidth=45, anchor="center", stretch=False)
        tree.column("ticker", width=76, minwidth=60, anchor="center", stretch=False)
        tree.column("company", width=230, minwidth=180, stretch=False)
        tree.column("market_cap", width=100, minwidth=95, anchor="e", stretch=False)

        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        return tree
