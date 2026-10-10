"""Window layout: panes, panels, tabs and tables."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ui_theme import load_settings
from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    CLOSED_SCENARIO_COLUMN_BOUNDS,
    CLOSED_SCENARIO_DISPLAY_COLUMNS,
    FIELD_DISPLAY_COLUMNS,
    HISTORY_LEGEND,
    RANKING_DISPLAY_COLUMNS,
    SCAN_EVENT_DISPLAY_COLUMNS,
    SCAN_FAILURE_COLUMNS,
    SIGNAL_HISTORY_COLUMN_BOUNDS,
    SIGNAL_HISTORY_DISPLAY_COLUMNS,
    SIGNAL_VALIDATION_DISPLAY_COLUMNS,
    TOP100_PANEL_WIDTH,
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
            SIGNAL_HISTORY_DISPLAY_COLUMNS,
            SIGNAL_HISTORY_COLUMN_BOUNDS,
        )
        scanner_table_specs = (
            (SCAN_EVENT_DISPLAY_COLUMNS, None),
            (ACTIVE_SCENARIO_DISPLAY_COLUMNS, None),
            (CLOSED_RESULT_DISPLAY_COLUMNS, None),
            (CLOSED_SCENARIO_DISPLAY_COLUMNS, CLOSED_SCENARIO_COLUMN_BOUNDS),
            (FIELD_DISPLAY_COLUMNS, None),
            (RANKING_DISPLAY_COLUMNS, None),
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

        summary_frame = ttk.LabelFrame(center_panel, text="선택 종목 시나리오 성과", padding=5)
        summary_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        for variable in (self.ticker_profile_var, self.ticker_cycle_summary_var):
            summary_label = ttk.Label(summary_frame, textvariable=variable)
            summary_label.pack(anchor="w")
            self._wrap_to_width(summary_label, center_panel, margin=50)
        self._build_horizon_cards(summary_frame)

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
            text="색이 진할수록 3·6·9·12개월 결과가 한쪽으로 뚜렷합니다",
            style="LegendNote.TLabel",
        ).pack(side="left", padx=(6, 0))

        table_frame = ttk.LabelFrame(
            center_panel,
            text="3단계 신호 과거 기록 (최신순 · 행 더블클릭: 차트 미리보기)",
            padding=4,
        )
        table_frame.grid(row=4, column=0, sticky="nsew")
        self.buy_tree = self._create_table(table_frame)
        self._configure_history_tree_tags()
        populate_table(
            self.buy_tree,
            pd.DataFrame(columns=SIGNAL_HISTORY_DISPLAY_COLUMNS),
            column_bounds=SIGNAL_HISTORY_COLUMN_BOUNDS,
            sortable=False,
        )
        self.buy_tree.bind("<<TreeviewSelect>>", self._on_history_select)
        self.buy_tree.bind("<Double-1>", self._on_history_double_click)

        self.scanner_panel = ttk.LabelFrame(
            self.main_panes,
            text="MMRM 시나리오 추적 스캐너",
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
            text="3단계 통합 스캔",
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
        field_tab = ttk.Frame(self.scan_notebook)
        validation_tab = ttk.Frame(self.scan_notebook)
        failure_tab = ttk.Frame(self.scan_notebook)
        watchlist_tab = ttk.Frame(self.scan_notebook)
        self.scan_notebook.add(event_tab, text="이번 스캔 신호")
        self.scan_notebook.add(active_tab, text="활성 시나리오")
        self.scan_notebook.add(closed_tab, text="이번 스캔 종료")
        self.scan_notebook.add(closed_scenario_tab, text="종료 시나리오")
        self.scan_notebook.add(field_tab, text="분야별 성과")
        self.scan_notebook.add(validation_tab, text="신호 효과 검증")
        self.scan_notebook.add(failure_tab, text="오류")
        # Added last so the positions of the earlier tabs stay the same.
        self.scan_notebook.add(watchlist_tab, text="관심종목")

        self.scan_tree = self._create_table(event_tab)
        self.active_tree = self._create_table(active_tab)
        self._configure_signal_tree_tags(self.scan_tree)
        self._configure_signal_tree_tags(self.active_tree)
        self.closed_tree = self._create_table(closed_tab)
        closed_filter_frame = ttk.Frame(
            closed_scenario_tab,
            padding=(4, 4, 4, 2),
        )
        closed_filter_frame.pack(fill="x")
        ttk.Checkbutton(
            closed_filter_frame,
            text="검토등급",
            variable=self.closed_grade_filter_enabled_var,
            command=self._refresh_closed_scenario_view,
            style="Filter.TCheckbutton",
        ).pack(side="left")
        grade_combo = ttk.Combobox(
            closed_filter_frame,
            textvariable=self.closed_grade_filter_var,
            values=("우선검토", "일반검토", "확인 필요", "해당 없음"),
            width=10,
            state="readonly",
        )
        grade_combo.pack(side="left", padx=(2, 12))
        grade_combo.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._refresh_closed_scenario_view(),
        )

        ttk.Checkbutton(
            closed_filter_frame,
            text="차트 강도",
            variable=self.closed_score_filter_enabled_var,
            command=self._refresh_closed_scenario_view,
            style="Filter.TCheckbutton",
        ).pack(side="left")
        self.closed_score_min_entry = ttk.Entry(
            closed_filter_frame,
            textvariable=self.closed_score_min_var,
            width=6,
        )
        self.closed_score_min_entry.pack(side="left", padx=(2, 3))
        ttk.Label(closed_filter_frame, text="~").pack(side="left")
        self.closed_score_max_entry = ttk.Entry(
            closed_filter_frame,
            textvariable=self.closed_score_max_var,
            width=6,
        )
        self.closed_score_max_entry.pack(side="left", padx=(3, 6))
        for entry in (self.closed_score_min_entry, self.closed_score_max_entry):
            entry.bind("<Return>", lambda _event: self._refresh_closed_scenario_view())
        ttk.Button(
            closed_filter_frame,
            text="적용",
            command=self._refresh_closed_scenario_view,
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            closed_filter_frame,
            text="초기화",
            command=self._reset_closed_scenario_filters,
        ).pack(side="left")
        ttk.Label(
            closed_filter_frame,
            textvariable=self.closed_filter_status_var,
        ).pack(side="right")

        closed_scenario_table_frame = ttk.Frame(closed_scenario_tab)
        closed_scenario_table_frame.pack(fill="both", expand=True)
        self.closed_scenario_tree = self._create_table(closed_scenario_table_frame)
        self._configure_history_tree_tags(self.closed_scenario_tree)
        self._build_field_performance_tab(field_tab)
        self._build_signal_validation_tab(validation_tab)
        self.failure_tree = self._create_table(failure_tab)
        self._build_watchlist_tab(watchlist_tab)

        populate_table(self.scan_tree, pd.DataFrame(columns=SCAN_EVENT_DISPLAY_COLUMNS))
        populate_table(self.active_tree, pd.DataFrame(columns=ACTIVE_SCENARIO_DISPLAY_COLUMNS))
        populate_table(self.closed_tree, pd.DataFrame(columns=CLOSED_RESULT_DISPLAY_COLUMNS))
        populate_table(
            self.closed_scenario_tree,
            pd.DataFrame(columns=CLOSED_SCENARIO_DISPLAY_COLUMNS),
            column_bounds=CLOSED_SCENARIO_COLUMN_BOUNDS,
        )
        populate_table(self.field_tree, pd.DataFrame(columns=FIELD_DISPLAY_COLUMNS))
        populate_table(self.ranking_tree, pd.DataFrame(columns=RANKING_DISPLAY_COLUMNS))
        populate_table(self.failure_tree, pd.DataFrame(columns=SCAN_FAILURE_COLUMNS))

        self.scan_tree.bind(
            "<<TreeviewSelect>>",
            lambda event: self._on_scan_row_select(event, self.scan_tree),
        )
        self._bind_chart_strength_tooltip(self.scan_tree, "신호일")
        self._bind_chart_strength_tooltip(self.active_tree, "2차신호일")
        self._bind_chart_strength_tooltip(self.closed_tree, "3차판정일")
        self._bind_chart_strength_tooltip(
            self.closed_scenario_tree,
            "3차판정일",
        )
        self._bind_chart_strength_tooltip(
            self.buy_tree,
            "3차판정일",
            ticker_column=None,
        )
        self.active_tree.bind(
            "<<TreeviewSelect>>",
            lambda event: self._on_scan_row_select(event, self.active_tree),
        )
        self.closed_tree.bind(
            "<<TreeviewSelect>>",
            lambda event: self._on_scan_row_select(event, self.closed_tree),
        )
        self.closed_scenario_tree.bind(
            "<<TreeviewSelect>>",
            self._on_closed_scenario_select,
        )
        self.closed_scenario_tree.bind(
            "<Double-1>",
            self._on_closed_scenario_double_click,
        )
        self.ranking_tree.bind(
            "<<TreeviewSelect>>",
            lambda event: self._on_scan_row_select(event, self.ranking_tree),
        )
        for tree in (self.scan_tree, self.active_tree, self.closed_tree, self.ranking_tree):
            tree.bind(
                "<Double-1>",
                lambda event, source=tree: self._on_ticker_double_click(
                    event,
                    source,
                    "티커",
                ),
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

    def _build_field_performance_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        controls = ttk.Frame(parent, padding=(4, 4, 4, 0))
        controls.grid(row=0, column=0, sticky="ew")
        ttk.Label(controls, text="구분").pack(side="left")
        level_combo = ttk.Combobox(
            controls,
            textvariable=self.field_level_var,
            values=("섹터", "산업"),
            width=8,
            state="readonly",
        )
        level_combo.pack(side="left", padx=(4, 14))
        ttk.Label(controls, text="분석 기간").pack(side="left")
        horizon_combo = ttk.Combobox(
            controls,
            textvariable=self.field_horizon_var,
            values=("3개월", "6개월", "9개월", "12개월"),
            width=8,
            state="readonly",
        )
        horizon_combo.pack(side="left", padx=(4, 14))
        ttk.Label(controls, text="종목 정렬").pack(side="left")
        sort_combo = ttk.Combobox(
            controls,
            textvariable=self.ranking_sort_var,
            values=(
                "종합점수",
                "승률",
                "평균 손익률",
                "매수 도달률",
                "평소 매수 대비 초과",
                "S&P 대비 초과",
            ),
            width=14,
            state="readonly",
        )
        sort_combo.pack(side="left", padx=(4, 0))
        for combo in (level_combo, horizon_combo, sort_combo):
            combo.bind("<<ComboboxSelected>>", self._on_field_control_change)

        ttk.Label(
            parent,
            textvariable=self.field_status_var,
            padding=(4, 5, 4, 5),
        ).grid(row=1, column=0, sticky="ew")

        panes = ttk.Panedwindow(parent, orient="vertical")
        panes.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        field_frame = ttk.LabelFrame(panes, text="분야별 종합 성과", padding=4)
        ranking_frame = ttk.LabelFrame(panes, text="선택 분야 종목 순위", padding=4)
        panes.add(field_frame, weight=1)
        panes.add(ranking_frame, weight=1)
        self.field_tree = self._create_table(field_frame)
        self.ranking_tree = self._create_table(ranking_frame)
        self.field_tree.bind("<<TreeviewSelect>>", self._on_field_select)

    def _build_signal_validation_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text=(
                "평소 매수 승률: 같은 종목을 신호 앞뒤 1년 안의 아무 주에나 샀을 때의 승률입니다. "
                "신호 승률이 이보다 높고 평소 매수 대비 초과가 플러스여야 매수 타이밍 효과가 "
                "있다고 볼 수 있습니다.  S&P 이긴 비율·S&P 대비 초과: 같은 주에 S&P 500을 "
                "사서 같은 기간 들고 있었을 때와 비교한 값입니다.  현재 Top 100 종목 기준이라 "
                "생존편향이 포함되어 있습니다."
            ),
            wraplength=720,
            justify="left",
            padding=(4, 4, 4, 2),
        ).pack(fill="x")
        ttk.Label(
            parent,
            textvariable=self.validation_status_var,
            padding=(4, 0, 4, 4),
        ).pack(fill="x")
        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="both", expand=True)
        self.validation_tree = self._create_table(table_frame)
        populate_table(
            self.validation_tree,
            pd.DataFrame(columns=SIGNAL_VALIDATION_DISPLAY_COLUMNS),
        )

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
