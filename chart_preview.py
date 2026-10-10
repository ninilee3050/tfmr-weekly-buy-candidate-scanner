from __future__ import annotations

from dataclasses import dataclass
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import numpy as np
import pandas as pd

from market_context import SP500_NAME, SP500_TICKER, load_sp500_context
from ui_theme import configure_ui_fonts, normalize_theme, theme_palette


CHART_COLUMNS = [
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "MA_5",
    "MA_20",
    "MA_50",
    "MA_150",
    "MA_200",
    "Volume_MA_50",
    "Momentum",
    "MACD",
    "Signal",
    "Histogram",
    "RSI",
    "MFI",
]

MA_STYLES = {
    "MA_5": ("#6aa84f", 2.0),
    "MA_20": ("#00d4d8", 2.4),
    "MA_50": ("#1428e8", 2.8),
    "MA_150": ("#9b1010", 3.2),
    "MA_200": ("#f00078", 3.6),
}
LIGHT_MA_COLOR_OVERRIDES = {
    "MA_20": "#00e5ff",
}
DARK_MA_COLOR_OVERRIDES = {
    "MA_150": "#c77832",
}


def moving_average_styles(theme_mode: str) -> dict[str, tuple[str, float]]:
    """Return theme-aware MA colors while preserving periods and widths."""
    styles = dict(MA_STYLES)
    overrides = (
        DARK_MA_COLOR_OVERRIDES
        if normalize_theme(theme_mode) == "dark"
        else LIGHT_MA_COLOR_OVERRIDES
    )
    for column, color in overrides.items():
        _original_color, width = styles[column]
        styles[column] = (color, width)
    return styles


def _blend_hex(foreground: str, background: str, opacity: float) -> str:
    foreground_rgb = tuple(int(foreground[index : index + 2], 16) for index in (1, 3, 5))
    background_rgb = tuple(int(background[index : index + 2], 16) for index in (1, 3, 5))
    blended = tuple(
        round(front * opacity + back * (1 - opacity))
        for front, back in zip(foreground_rgb, background_rgb)
    )
    return "#" + "".join(f"{channel:02x}" for channel in blended)


def _relative_luminance(color: str) -> float:
    channels = []
    for index in (1, 3, 5):
        value = int(color[index : index + 2], 16) / 255
        channels.append(
            value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        )
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def readable_text_color(color: str, background: str, text_color: str) -> str:
    """Keep a label's hue but move it toward the text color until it is legible."""
    if not color.startswith("#") or len(color) != 7:
        return color
    for opacity in (1.0, 0.8, 0.65, 0.5, 0.35, 0.2):
        candidate = _blend_hex(color, text_color, opacity)
        if contrast_ratio(candidate, background) >= MIN_TEXT_CONTRAST:
            return candidate
    return text_color


OSCILLATOR_UPPER = 70.0
OSCILLATOR_CENTER = 50.0
OSCILLATOR_LOWER = 30.0
CANDLE_UP_COLOR = "#ef4444"
CANDLE_DOWN_COLOR = "#2563eb"
INDICATOR_BAR_OPACITY = 0.5
POSITIVE_BAR_COLOR = _blend_hex(CANDLE_UP_COLOR, "#ffffff", INDICATOR_BAR_OPACITY)
NEGATIVE_BAR_COLOR = _blend_hex(CANDLE_DOWN_COLOR, "#ffffff", INDICATOR_BAR_OPACITY)
MACD_SIGNAL_COLOR = MA_STYLES["MA_50"][0]
VOLUME_MA_STYLE = MA_STYLES["MA_50"]
OSCILLATOR_LINE_COLOR = CANDLE_UP_COLOR
CANDLE_WIDTH_RATIO = 0.76
PRICE_RANGE_MA_MARGIN = 0.25
PRICE_SCALE_TICKS = 5
MIN_TEXT_CONTRAST = 3.5
SIGNAL_LABEL_MIN_GAP = 30
CANDLE_BODY_FILL = ""
INDICATOR_BAR_WIDTH_RATIO = 0.84
ZOOM_IN_FACTOR = 0.88
ZOOM_OUT_FACTOR = 1.14
BENCHMARK_TICKER = SP500_TICKER
BENCHMARK_NAME = SP500_NAME
BENCHMARK_SIGNAL_OPACITY = 0.78
BENCHMARK_SIGNAL_WIDTH = 2.2

SIGNAL_STYLES = (
    ("1차", "FirstSignalDate", "#16a34a"),
    ("2차", "SecondSignalDate", "#f59e0b"),
    ("3차", "ThirdDecisionDate", "#dc2626"),
)

BUY_MARKER_HORIZONS = (
    ("3M", 13, "Return3M", "Return3MStatus"),
    ("6M", 26, "Return6M", "Return6MStatus"),
    ("9M", 39, "Return9M", "Return9MStatus"),
    ("12M", 52, "Return12M", "Return12MStatus"),
)

RETURN_HORIZONS = (
    ("3M", "Return3M", "Return3MStatus"),
    ("6M", "Return6M", "Return6MStatus"),
    ("9M", "Return9M", "Return9MStatus"),
    ("12M", "Return12M", "Return12MStatus"),
)


def format_cycle_return(value, status) -> str:
    """Format one stored forward return without recalculating it."""
    if value is not None and not pd.isna(value):
        try:
            return f"{float(value):+.2f}%"
        except (TypeError, ValueError):
            return str(value)
    if status is not None and not pd.isna(status):
        status_text = str(status).strip()
        if status_text:
            return status_text
    return "-"


def cycle_return_summary(cycle: pd.Series | None) -> str:
    """Build the compact 3/6/9/12-month result shown in the chart header."""
    if cycle is None:
        return ""
    statuses = {str(cycle.get(status_column, "")) for _, _, status_column in RETURN_HORIZONS}
    if statuses == {"해당 없음"}:
        # Failed or discarded cycles have no returns to show.
        return ""
    return " · ".join(
        f"{label} {format_cycle_return(cycle.get(value_column), cycle.get(status_column))}"
        for label, value_column, status_column in RETURN_HORIZONS
    )


@dataclass(frozen=True)
class Panel:
    name: str
    top: float
    bottom: float


def cycle_view_dates(
    index: pd.DatetimeIndex,
    cycle: pd.Series | None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    dates = _normalized_index(index)
    if dates.empty:
        raise ValueError("차트 데이터가 비어 있습니다.")

    latest = dates[-1]
    if cycle is None or pd.isna(cycle.get("FirstSignalDate")):
        start = max(dates[0], latest - pd.DateOffset(years=3))
        return dates[dates.searchsorted(start, side="left")], latest

    first = _timestamp(cycle.get("FirstSignalDate"))
    second = _timestamp(cycle.get("SecondSignalDate"))
    third = _timestamp(cycle.get("ThirdDecisionDate"))
    anchor = third if third is not None else second if second is not None else first
    start = first - pd.DateOffset(years=1)
    end = anchor + pd.DateOffset(years=1)

    if "대기" in str(cycle.get("Outcome", "")):
        end = max(end, latest)
    start = max(dates[0], start)
    end = min(latest, end)
    start_position = min(len(dates) - 1, int(dates.searchsorted(start, side="left")))
    end_position = max(0, int(dates.searchsorted(end, side="right") - 1))
    return dates[start_position], dates[end_position]


def cycle_view_indices(
    index: pd.DatetimeIndex,
    cycle: pd.Series | None,
) -> tuple[int, int]:
    dates = _normalized_index(index)
    start_date, end_date = cycle_view_dates(dates, cycle)
    start = int(dates.searchsorted(start_date, side="left"))
    end = int(dates.searchsorted(end_date, side="right") - 1)
    return max(0, start), min(len(dates) - 1, max(start, end))


def comparison_view_indices(
    index: pd.DatetimeIndex,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> tuple[int, int]:
    """Map the stock chart's visible date range onto the benchmark index."""
    dates = _normalized_index(index)
    if dates.empty:
        raise ValueError("비교 지수 데이터가 비어 있습니다.")
    start = int(dates.searchsorted(pd.Timestamp(start_date), side="left"))
    end = int(dates.searchsorted(pd.Timestamp(end_date), side="right") - 1)
    start = min(len(dates) - 1, max(0, start))
    end = min(len(dates) - 1, max(start, end))
    return start, end


def expanded_comparison_width(window_width: int, primary_chart_width: int) -> int:
    """Keep the primary chart width and append an equally useful right pane."""
    return int(window_width) + max(640, int(primary_chart_width)) + 4


class ChartPreviewWindow(tk.Toplevel):
    """Interactive weekly chart kept in one reusable Tkinter window."""

    def __init__(
        self,
        master: tk.Misc,
        on_close=None,
        on_navigate=None,
        theme_mode: str = "light",
    ) -> None:
        super().__init__(master)
        self.ui_font_family = configure_ui_fonts(self)
        self._on_close_callback = on_close
        self._on_navigate_callback = on_navigate
        self.theme_mode = normalize_theme(theme_mode)
        self.palette = theme_palette(self.theme_mode)
        self.configure(background=self.palette["window"])
        self.title("MMRM 시나리오 차트 미리보기")
        width = min(1600, self.winfo_screenwidth() - 40)
        height = min(920, self.winfo_screenheight() - 80)
        self.geometry(f"{width}x{height}")
        self.minsize(min(1000, width), min(680, height))
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.status_var = tk.StringVar(value="차트 데이터를 준비해 주세요.")
        self.chart_strength_var = tk.StringVar(value="차트 강도: 산정 대기")
        self.hover_var = tk.StringVar(
            value=(
                "방향키 ←·→: 이전·다음 기록  |  휠: 확대·축소  |  "
                "드래그: 좌우 이동  |  더블클릭: 선택 사이클 전체 보기"
            )
        )
        self.header_frame = ttk.Frame(self)
        self.header_frame.pack(fill="x")
        ttk.Label(
            self.header_frame,
            textvariable=self.status_var,
            font=(self.ui_font_family, 11, "bold"),
            padding=(10, 7, 485, 2),
        ).pack(side="left", fill="x", expand=True)
        self.previous_button = ttk.Button(
            self.header_frame,
            text="← 이전",
            command=lambda: self._request_navigation(-1),
            state="disabled",
        )
        self.navigation_var = tk.StringVar(value="- / -")
        self.navigation_label = ttk.Label(
            self.header_frame,
            textvariable=self.navigation_var,
            anchor="center",
            width=8,
        )
        self.next_button = ttk.Button(
            self.header_frame,
            text="다음 →",
            command=lambda: self._request_navigation(1),
            state="disabled",
        )
        self.benchmark_button = ttk.Button(
            self.header_frame,
            text="S&P 500 비교 열기",
            command=self._toggle_benchmark,
        )
        self._position_header_controls()
        ttk.Label(
            self,
            textvariable=self.chart_strength_var,
            font=(self.ui_font_family, 9, "bold"),
            padding=(10, 0, 10, 2),
        ).pack(fill="x")
        ttk.Label(
            self,
            textvariable=self.hover_var,
            padding=(10, 2, 10, 7),
        ).pack(fill="x")

        self.chart_area = ttk.Frame(self)
        self.chart_area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            self.chart_area,
            background=self.palette["chart_background"],
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.comparison_frame = ttk.Frame(self.chart_area)
        self.comparison_status_var = tk.StringVar(value="S&P 500 데이터를 준비해 주세요.")
        self.comparison_canvas = tk.Canvas(
            self.comparison_frame,
            background=self.palette["chart_background"],
            highlightthickness=0,
            cursor="crosshair",
        )
        self.comparison_canvas.pack(fill="both", expand=True)
        self.panel_title_font = tkfont.Font(
            root=self,
            family=self.ui_font_family,
            size=8,
            weight="bold",
        )
        self.panel_value_font = tkfont.Font(
            root=self,
            family=self.ui_font_family,
            size=8,
        )

        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._clear_crosshair)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self.canvas.bind("<Double-Button-1>", self._reset_view)
        self.comparison_canvas.bind("<Configure>", self._on_resize)
        self.comparison_canvas.bind("<Motion>", self._on_comparison_motion)
        self.comparison_canvas.bind("<Leave>", self._clear_crosshair)
        self.comparison_canvas.bind("<MouseWheel>", self._on_comparison_mousewheel)
        self.comparison_canvas.bind("<ButtonPress-1>", self._on_comparison_drag_start)
        self.comparison_canvas.bind("<B1-Motion>", self._on_comparison_drag_motion)
        self.comparison_canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self.comparison_canvas.bind("<Double-Button-1>", self._reset_view)
        self.bind("<Left>", lambda _event: self._request_navigation(-1))
        self.bind("<Right>", lambda _event: self._request_navigation(1))

        self.ticker = ""
        self.company = ""
        self.data = pd.DataFrame()
        self.cycle: pd.Series | None = None
        self.view_start = 0
        self.view_end = 0
        self.initial_view = (0, 0)
        self._redraw_job: str | None = None
        self._drag_origin: tuple[int, int, int, float] | None = None
        self.benchmark_data = pd.DataFrame()
        self.benchmark_visible = False
        self.benchmark_loading = False
        self._geometry_before_benchmark: str | None = None
        self._primary_width_before_benchmark = 0
        self._state_before_benchmark = "normal"
        self._window_size_before_benchmark = (0, 0)
        self._window_position_before_benchmark = (0, 0)
        self.navigation_index: int | None = None
        self.navigation_total = 0

    def _position_header_controls(self, fixed_right: int | None = None) -> None:
        relx = 1.0 if fixed_right is None else 0.0
        right = -10 if fixed_right is None else max(490, int(fixed_right) - 10)
        common = {"relx": relx, "y": 6, "anchor": "ne"}
        self.benchmark_button.place_configure(x=right, **common)
        self.next_button.place_configure(x=right - 165, **common)
        self.navigation_label.place_configure(x=right - 250, y=10, anchor="ne", relx=relx)
        self.previous_button.place_configure(x=right - 330, **common)

    def _request_navigation(self, direction: int) -> str:
        if direction < 0 and str(self.previous_button.cget("state")) == "disabled":
            return "break"
        if direction > 0 and str(self.next_button.cget("state")) == "disabled":
            return "break"
        if self._on_navigate_callback is not None:
            self._on_navigate_callback(-1 if direction < 0 else 1)
        return "break"

    def _set_navigation_state(self, index: int | None, total: int) -> None:
        self.navigation_index = index
        self.navigation_total = max(0, int(total))
        if index is None or self.navigation_total <= 0:
            self.navigation_var.set("- / -")
            self.previous_button.configure(state="disabled")
            self.next_button.configure(state="disabled")
            return
        current = min(self.navigation_total - 1, max(0, int(index)))
        self.navigation_index = current
        self.navigation_var.set(f"{current + 1} / {self.navigation_total}")
        self.previous_button.configure(state="normal" if current > 0 else "disabled")
        self.next_button.configure(
            state="normal" if current < self.navigation_total - 1 else "disabled"
        )

    def set_theme(self, mode: str) -> None:
        self.theme_mode = normalize_theme(mode)
        self.palette = theme_palette(self.theme_mode)
        self.configure(background=self.palette["window"])
        self.canvas.configure(background=self.palette["chart_background"])
        self.comparison_canvas.configure(background=self.palette["chart_background"])
        self._schedule_redraw()

    def _toggle_benchmark(self) -> None:
        if self.benchmark_visible and not self.benchmark_data.empty:
            self._hide_benchmark()
            return
        if not self.benchmark_visible:
            self._show_benchmark_frame()
        if not self.benchmark_data.empty:
            self._schedule_redraw()
            return
        if self.benchmark_loading:
            return

        self.benchmark_loading = True
        self.benchmark_button.configure(text="S&P 500 불러오는 중...", state="disabled")
        self.comparison_status_var.set("S&P 500 주봉 데이터를 불러오는 중입니다...")
        self._schedule_redraw()
        threading.Thread(target=self._load_benchmark_worker, daemon=True).start()

    def _show_benchmark_frame(self) -> None:
        if self.benchmark_visible:
            return
        self.update_idletasks()
        self.benchmark_visible = True
        self._state_before_benchmark = self.state()
        self._geometry_before_benchmark = self.geometry()
        self._primary_width_before_benchmark = max(640, self.canvas.winfo_width())
        self._window_size_before_benchmark = (self.winfo_width(), self.winfo_height())
        self._window_position_before_benchmark = (self.winfo_x(), self.winfo_y())
        self._position_header_controls(self._window_size_before_benchmark[0])
        if self._state_before_benchmark != "normal":
            self.state("normal")
            self.update_idletasks()
        self._expand_for_benchmark()
        self.comparison_frame.configure(width=self._primary_width_before_benchmark)
        self.comparison_frame.pack_propagate(False)
        self.comparison_frame.pack(
            side="right",
            fill="both",
            expand=False,
            padx=(4, 0),
        )
        self.benchmark_button.configure(text="S&P 500 비교 닫기")

    def _hide_benchmark(self) -> None:
        self.benchmark_visible = False
        self.comparison_frame.pack_forget()
        self.comparison_frame.pack_propagate(True)
        self.benchmark_button.configure(text="S&P 500 비교 열기", state="normal")
        self._position_header_controls()
        self._clear_crosshair()
        if self._state_before_benchmark == "zoomed":
            try:
                self.state("zoomed")
            except tk.TclError:
                pass
        elif self._geometry_before_benchmark and self.state() == "normal":
            try:
                self.geometry(self._geometry_before_benchmark)
            except tk.TclError:
                pass
        self._geometry_before_benchmark = None
        self._primary_width_before_benchmark = 0
        self._state_before_benchmark = "normal"
        self._window_size_before_benchmark = (0, 0)
        self._window_position_before_benchmark = (0, 0)
        self._schedule_redraw()

    def _expand_for_benchmark(self) -> None:
        self.update_idletasks()
        width, height = self._window_size_before_benchmark
        if width <= 0 or height <= 0:
            width, height = self.winfo_width(), self.winfo_height()
        desired_width = expanded_comparison_width(
            width,
            self._primary_width_before_benchmark,
        )
        desired_height = height
        x, y = self._window_position_before_benchmark
        x = max(0, x)
        y = max(0, y)
        # On a smaller screen the side-by-side charts share the screen width.
        screen_width = self.winfo_screenwidth()
        desired_width = min(desired_width, screen_width)
        if x < screen_width and x + desired_width > screen_width:
            x = max(0, screen_width - desired_width)
        self.maxsize(
            max(desired_width, self.winfo_screenwidth()),
            max(desired_height, self.winfo_screenheight()),
        )
        self.geometry(f"{desired_width}x{desired_height}+{x}+{y}")
        self.update_idletasks()

    def _load_benchmark_worker(self) -> None:
        try:
            expected_latest = self.data.index[-1] if not self.data.empty else None
            prepared, load_result = load_sp500_context(
                expected_latest_date=expected_latest,
            )
        except Exception as exc:  # Network/provider errors are shown in the UI.
            try:
                self.after(0, self._finish_benchmark_error, str(exc))
            except tk.TclError:
                pass
            return
        try:
            self.after(0, self._finish_benchmark_load, prepared, load_result.warning)
        except tk.TclError:
            pass

    def _window_alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _finish_benchmark_load(self, data: pd.DataFrame, warning: str = "") -> None:
        if not self._window_alive():
            return
        if data.empty:
            self._finish_benchmark_error("S&P 500 데이터가 비어 있습니다.")
            return
        self.benchmark_loading = False
        prepared = data.loc[:, CHART_COLUMNS].copy()
        prepared.index = _normalized_index(pd.DatetimeIndex(prepared.index))
        self.benchmark_data = prepared[~prepared.index.duplicated(keep="last")].sort_index()
        latest = self.benchmark_data.index[-1].strftime("%Y-%m-%d")
        suffix = f"  |  {warning}" if warning else ""
        self.comparison_status_var.set(
            f"S&P 500 (^GSPC)  |  데이터 기준일 {latest}{suffix}"
        )
        self.benchmark_button.configure(text="S&P 500 비교 닫기", state="normal")
        self._schedule_redraw()

    def _finish_benchmark_error(self, details: str) -> None:
        if not self._window_alive():
            return
        self.benchmark_loading = False
        self.comparison_status_var.set("S&P 500 데이터를 불러오지 못했습니다.")
        self.benchmark_button.configure(text="S&P 500 다시 시도", state="normal")
        messagebox.showerror(
            "S&P 500 비교 차트 오류",
            "S&P 500 주봉 데이터를 불러오지 못했습니다.\n\n" + details,
            parent=self,
        )

    def show_cycle(
        self,
        ticker: str,
        data: pd.DataFrame,
        cycle: pd.Series | None,
        company: str = "",
        rank_text: str = "",
        navigation_index: int | None = None,
        navigation_total: int = 0,
        chart_strength_summary: str = "",
        sp500_summary: str = "",
        sp500_data: pd.DataFrame | None = None,
        sp500_warning: str = "",
    ) -> None:
        missing = [column for column in CHART_COLUMNS if column not in data.columns]
        if missing:
            raise ValueError("차트 필수 컬럼이 없습니다: " + ", ".join(missing))

        prepared = data.loc[:, CHART_COLUMNS].copy()
        prepared.index = _normalized_index(pd.DatetimeIndex(prepared.index))
        prepared = prepared[~prepared.index.duplicated(keep="last")].sort_index()
        if prepared.empty:
            raise ValueError("표시할 차트 데이터가 없습니다.")

        self.ticker = ticker.upper()
        self.company = company
        self.data = prepared
        self.cycle = cycle.copy() if cycle is not None else None
        self.view_start, self.view_end = cycle_view_indices(prepared.index, cycle)
        self.initial_view = (self.view_start, self.view_end)
        self._drag_origin = None

        first = _date_text(cycle.get("FirstSignalDate")) if cycle is not None else "-"
        second = _date_text(cycle.get("SecondSignalDate")) if cycle is not None else "-"
        third = _date_text(cycle.get("ThirdDecisionDate")) if cycle is not None else "-"
        outcome = str(cycle.get("Outcome", "전체 차트")) if cycle is not None else "최근 3년"
        returns = cycle_return_summary(cycle)
        name = f" · {company}" if company and company.upper() != self.ticker else ""
        if rank_text:
            name += f" · {rank_text}"
        return_suffix = f"  |  {returns}" if returns else ""
        self.status_var.set(
            f"{self.ticker}{name}  |  1차 {first}  ·  2차 {second}  ·  "
            f"3차 {third}  |  {outcome}{return_suffix}"
        )
        summary_parts = [chart_strength_summary or "차트 강도: 해당 없음"]
        if sp500_summary:
            summary_parts.append(sp500_summary)
        self.chart_strength_var.set("  |  ".join(summary_parts))
        if sp500_data is not None and not sp500_data.empty:
            benchmark = sp500_data.loc[:, CHART_COLUMNS].copy()
            benchmark.index = _normalized_index(pd.DatetimeIndex(benchmark.index))
            self.benchmark_data = (
                benchmark[~benchmark.index.duplicated(keep="last")].sort_index()
            )
            latest = self.benchmark_data.index[-1].strftime("%Y-%m-%d")
            suffix = f"  |  {sp500_warning}" if sp500_warning else ""
            self.comparison_status_var.set(
                f"S&P 500 (^GSPC)  |  데이터 기준일 {latest}{suffix}"
            )
        else:
            self.benchmark_data = pd.DataFrame()
            self.comparison_status_var.set("S&P 500 데이터를 준비해 주세요.")
        self._set_navigation_state(navigation_index, navigation_total)
        self.title(f"{self.ticker} · MMRM 시나리오 차트 미리보기")
        self.deiconify()
        self.lift()
        self.focus_force()
        self._schedule_redraw()

    def _close(self) -> None:
        callback = self._on_close_callback
        self._on_close_callback = None
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
            self._redraw_job = None
        self.destroy()
        if callback is not None:
            callback()

    def _on_resize(self, _event=None) -> None:
        self._schedule_redraw()

    def _schedule_redraw(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after_idle(self._redraw)

    def _redraw(self) -> None:
        self._redraw_job = None
        if not self._window_alive():
            return
        self.canvas.delete("all")
        if self.data.empty or self.canvas.winfo_width() < 200:
            self._redraw_benchmark()
            return

        panels = self._panels()
        visible = self.data.iloc[self.view_start : self.view_end + 1]
        x_positions = self._x_positions(len(visible))

        self._draw_panel_frames(panels, visible)
        self._draw_price(panels[0], visible, x_positions)
        self._draw_volume(panels[1], visible, x_positions)
        self._draw_momentum(panels[2], visible, x_positions)
        self._draw_macd(panels[3], visible, x_positions)
        self._draw_oscillator(panels[4], visible, x_positions, "RSI")
        self._draw_oscillator(panels[5], visible, x_positions, "MFI")
        self._draw_signal_lines(panels)
        self._draw_buy_markers(panels[0], visible)
        self._draw_date_axis(visible, x_positions, panels[-1].bottom)
        self._show_rightmost_values(panels, visible)
        self._redraw_benchmark()

    def _panels(self) -> list[Panel]:
        height = max(500, self.canvas.winfo_height())
        top = 12.0
        bottom = height - 28.0
        gap = 5.0
        weights = (0.39, 0.13, 0.10, 0.14, 0.12, 0.12)
        usable = bottom - top - gap * (len(weights) - 1)
        panels = []
        cursor = top
        names = ("가격", "거래량", "Momentum", "MACD", "RSI", "MFI")
        for name, weight in zip(names, weights):
            panel_bottom = cursor + usable * weight
            panels.append(Panel(name, cursor, panel_bottom))
            cursor = panel_bottom + gap
        return panels

    def _plot_edges(self) -> tuple[float, float]:
        return 64.0, max(180.0, self.canvas.winfo_width() - 92.0)

    def _x_positions(self, count: int) -> np.ndarray:
        left, right = self._plot_edges()
        step = (right - left) / max(1, count)
        return left + (np.arange(count) + 0.5) * step

    def _draw_panel_frames(self, panels: list[Panel], visible: pd.DataFrame) -> None:
        left, right = self._plot_edges()
        for panel in panels:
            self.canvas.create_rectangle(
                left,
                panel.top,
                right,
                panel.bottom,
                outline=self.palette["chart_border"],
                fill=self.palette["chart_panel"],
            )
            self.canvas.create_text(
                left + 6,
                panel.top + 5,
                text=panel.name,
                anchor="nw",
                fill=self.palette["chart_text"],
                font=self.panel_title_font,
            )
            for fraction in (0.25, 0.5, 0.75):
                y = panel.top + (panel.bottom - panel.top) * fraction
                self.canvas.create_line(
                    left,
                    y,
                    right,
                    y,
                    fill=self.palette["chart_grid"],
                )

        count = len(visible)
        for fraction in np.linspace(0, 1, min(9, count), endpoint=True):
            x = left + (right - left) * fraction
            self.canvas.create_line(
                x,
                panels[0].top,
                x,
                panels[-1].bottom,
                fill=self.palette["chart_grid"],
            )

    def _draw_price(self, panel: Panel, data: pd.DataFrame, xs: np.ndarray) -> None:
        ma_styles = moving_average_styles(self.theme_mode)
        low, high = _price_range(data)
        y = lambda value: _map_y(value, low, high, panel)
        self._draw_scale(panel, low, high, ticks=PRICE_SCALE_TICKS)

        step = (self._plot_edges()[1] - self._plot_edges()[0]) / max(1, len(data))
        candle_half = max(0.7, step * CANDLE_WIDTH_RATIO / 2)

        # Keep candles above the moving averages, but leave their bodies hollow so
        # a moving-average line remains visible while passing through a candle.
        for column, (color, width) in ma_styles.items():
            self._draw_line(
                xs,
                data[column],
                y,
                color,
                width,
                tag=f"{column.lower()}_line",
                clip=(low, high),
            )

        for x, (_, row) in zip(xs, data.iterrows()):
            if any(pd.isna(row[column]) for column in ("Open", "High", "Low", "Close")):
                continue
            rising = row["Close"] >= row["Open"]
            color = CANDLE_UP_COLOR if rising else CANDLE_DOWN_COLOR
            top = y(max(row["Open"], row["Close"]))
            bottom = y(min(row["Open"], row["Close"]))
            if abs(bottom - top) < 1:
                bottom = top + 1
            self.canvas.create_line(x, y(row["High"]), x, top, fill=color)
            self.canvas.create_line(x, bottom, x, y(row["Low"]), fill=color)
            self.canvas.create_rectangle(
                x - candle_half,
                top,
                x + candle_half,
                bottom,
                outline=color,
                fill=CANDLE_BODY_FILL,
                tags=(
                    "candle_body",
                    "rising_candle" if rising else "falling_candle",
                ),
            )

    def _draw_volume(self, panel: Panel, data: pd.DataFrame, xs: np.ndarray) -> None:
        _, high = _finite_range(data[["Volume", "Volume_MA_50"]].to_numpy(), padding=0.08)
        low = 0.0
        y = lambda value: _map_y(value, low, high, panel)
        self._draw_scale(panel, low, high, compact=True)
        step = (self._plot_edges()[1] - self._plot_edges()[0]) / max(1, len(data))
        half = max(0.7, step * INDICATOR_BAR_WIDTH_RATIO / 2)
        baseline = y(0)
        for x, (_, row) in zip(xs, data.iterrows()):
            color = self._indicator_bar_color(row["Close"] >= row["Open"])
            if pd.notna(row["Volume"]):
                self.canvas.create_rectangle(
                    x - half,
                    y(row["Volume"]),
                    x + half,
                    baseline,
                    outline=color,
                    fill=color,
                )
        self._draw_line(xs, data["Volume_MA_50"], y, *VOLUME_MA_STYLE)

    def _draw_momentum(self, panel: Panel, data: pd.DataFrame, xs: np.ndarray) -> None:
        low, high = _finite_range(data["Momentum"].to_numpy(), include_zero=True, padding=0.10)
        y = lambda value: _map_y(value, low, high, panel)
        self._draw_scale(panel, low, high)
        zero = y(0)
        left, right = self._plot_edges()
        self._draw_zero_bars(data["Momentum"], xs, y, "momentum")
        self.canvas.create_line(
            left,
            zero,
            right,
            zero,
            fill=self.palette["zero_line"],
        )

    def _draw_macd(self, panel: Panel, data: pd.DataFrame, xs: np.ndarray) -> None:
        low, high = _finite_range(
            data[["MACD", "Signal", "Histogram"]].to_numpy(),
            include_zero=True,
            padding=0.10,
        )
        y = lambda value: _map_y(value, low, high, panel)
        self._draw_scale(panel, low, high)
        zero = y(0)
        left, right = self._plot_edges()
        self._draw_zero_bars(data["Histogram"], xs, y, "macd")
        self.canvas.create_line(
            left,
            zero,
            right,
            zero,
            fill=self.palette["zero_line"],
        )
        self._draw_line(xs, data["MACD"], y, "#ff5b5b", 1.5)
        self._draw_line(xs, data["Signal"], y, MACD_SIGNAL_COLOR, 1.5)

    def _draw_zero_bars(
        self,
        series: pd.Series,
        xs: np.ndarray,
        mapper,
        tag_prefix: str,
    ) -> None:
        left, right = self._plot_edges()
        step = (right - left) / max(1, len(series))
        half = max(0.8, step * INDICATOR_BAR_WIDTH_RATIO / 2)
        zero = mapper(0)
        for x, value in zip(xs, series):
            if pd.isna(value):
                continue
            positive = value >= 0
            color = self._indicator_bar_color(positive)
            direction = "positive" if positive else "negative"
            self.canvas.create_rectangle(
                x - half,
                mapper(value),
                x + half,
                zero,
                outline=color,
                fill=color,
                tags=(f"{tag_prefix}_bar", f"{tag_prefix}_{direction}_bar"),
            )

    def _draw_oscillator(
        self,
        panel: Panel,
        data: pd.DataFrame,
        xs: np.ndarray,
        column: str,
    ) -> None:
        y = lambda value: _map_y(value, 0.0, 100.0, panel)
        self._draw_scale(panel, 0.0, 100.0)
        left, right = self._plot_edges()
        self._draw_threshold_fill(
            panel,
            xs,
            data[column],
            OSCILLATOR_UPPER,
            above=True,
            color=self.palette["overbought_fill"],
            tag=f"{column.lower()}_overbought_fill",
        )
        self._draw_threshold_fill(
            panel,
            xs,
            data[column],
            OSCILLATOR_LOWER,
            above=False,
            color=self.palette["oversold_fill"],
            tag=f"{column.lower()}_oversold_fill",
        )
        self.canvas.create_line(
            left,
            y(OSCILLATOR_UPPER),
            right,
            y(OSCILLATOR_UPPER),
            fill="#ef4444",
            dash=(4, 3),
        )
        self.canvas.create_line(
            left,
            y(OSCILLATOR_CENTER),
            right,
            y(OSCILLATOR_CENTER),
            fill="#16a34a",
            width=1,
        )
        self.canvas.create_line(
            left,
            y(OSCILLATOR_LOWER),
            right,
            y(OSCILLATOR_LOWER),
            fill="#3b5bff",
            dash=(4, 3),
        )
        self._draw_line(xs, data[column], y, OSCILLATOR_LINE_COLOR, 1.5)

    def _indicator_bar_color(self, positive: bool) -> str:
        candle_color = CANDLE_UP_COLOR if positive else CANDLE_DOWN_COLOR
        return _blend_hex(
            candle_color,
            self.palette["chart_panel"],
            INDICATOR_BAR_OPACITY,
        )

    def _draw_threshold_fill(
        self,
        panel: Panel,
        xs: np.ndarray,
        series: pd.Series,
        threshold: float,
        above: bool,
        color: str,
        tag: str,
    ) -> None:
        baseline = _map_y(threshold, 0.0, 100.0, panel)
        values = series.to_numpy(dtype=float)
        for position in range(len(values) - 1):
            x1, x2 = float(xs[position]), float(xs[position + 1])
            value1, value2 = values[position], values[position + 1]
            if not np.isfinite(value1) or not np.isfinite(value2):
                continue

            inside1 = value1 > threshold if above else value1 < threshold
            inside2 = value2 > threshold if above else value2 < threshold
            if not inside1 and not inside2:
                continue

            if inside1 and inside2:
                points = (
                    x1,
                    baseline,
                    x1,
                    _map_y(value1, 0.0, 100.0, panel),
                    x2,
                    _map_y(value2, 0.0, 100.0, panel),
                    x2,
                    baseline,
                )
            else:
                crossing = x1 + (threshold - value1) / (value2 - value1) * (x2 - x1)
                if inside1:
                    points = (
                        x1,
                        baseline,
                        x1,
                        _map_y(value1, 0.0, 100.0, panel),
                        crossing,
                        baseline,
                    )
                else:
                    points = (
                        crossing,
                        baseline,
                        x2,
                        _map_y(value2, 0.0, 100.0, panel),
                        x2,
                        baseline,
                    )
            self.canvas.create_polygon(
                *points,
                fill=color,
                outline=color,
                tags=("oscillator_fill", tag),
            )

    def _draw_line(
        self,
        xs,
        series,
        mapper,
        color: str,
        width: float,
        tag: str | None = None,
        clip: tuple[float, float] | None = None,
    ) -> None:
        """Draw a polyline; values outside ``clip`` break the line."""
        tags = (tag,) if tag else ()
        points: list[float] = []
        for x, value in zip(xs, series):
            outside = clip is not None and not pd.isna(value) and not (
                clip[0] <= float(value) <= clip[1]
            )
            if pd.isna(value) or outside:
                if len(points) >= 4:
                    self.canvas.create_line(
                        *points,
                        fill=color,
                        width=width,
                        smooth=False,
                        tags=tags,
                    )
                points = []
                continue
            points.extend((float(x), float(mapper(value))))
        if len(points) >= 4:
            self.canvas.create_line(
                *points,
                fill=color,
                width=width,
                smooth=False,
                tags=tags,
            )

    def _draw_scale(
        self,
        panel: Panel,
        low: float,
        high: float,
        compact: bool = False,
        ticks: int = 3,
    ) -> None:
        right = self._plot_edges()[1]
        for fraction in np.linspace(0.0, 1.0, ticks):
            value = high - (high - low) * fraction
            raw_y = panel.top + (panel.bottom - panel.top) * fraction
            y = min(panel.bottom - 8, max(panel.top + 8, raw_y))
            text = _compact_number(value) if compact else _number(value)
            self.canvas.create_text(
                right + 6,
                y,
                text=text,
                anchor="w",
                fill=self.palette["chart_text"],
                font=(self.ui_font_family, 8),
                tags="scale_label",
            )

    def _draw_signal_lines(self, panels: list[Panel]) -> None:
        if self.cycle is None:
            return
        left, right = self._plot_edges()
        count = self.view_end - self.view_start + 1
        label_y = panels[0].top + 22
        previous_label_x: float | None = None
        for label, column, color in SIGNAL_STYLES:
            signal_date = _timestamp(self.cycle.get(column))
            if signal_date is None:
                continue
            position = int(self.data.index.searchsorted(signal_date, side="left"))
            if position < self.view_start or position > self.view_end:
                continue
            x = left + ((position - self.view_start) + 0.5) / max(1, count) * (right - left)
            self.canvas.create_line(
                x,
                panels[0].top,
                x,
                panels[-1].bottom,
                fill=color,
                width=2,
            )
            # Signals a week apart would print on top of each other; step down.
            if previous_label_x is not None and x - previous_label_x < SIGNAL_LABEL_MIN_GAP:
                label_y += 16
            else:
                label_y = panels[0].top + 22
            previous_label_x = x
            self.canvas.create_text(
                x + 3,
                label_y,
                text=label,
                anchor="nw",
                fill=color,
                font=(self.ui_font_family, 9, "bold"),
            )

    def _draw_buy_markers(self, panel: Panel, visible: pd.DataFrame) -> None:
        """Mark the 3rd-signal buy price and the 3/6/9/12-month outcomes."""
        cycle = self.cycle
        if cycle is None or visible.empty or cycle.get("Outcome") != "매수 성공":
            return
        buy_date = _timestamp(cycle.get("ThirdDecisionDate"))
        if buy_date is None:
            return
        position = int(self.data.index.searchsorted(buy_date, side="left"))
        if position >= len(self.data) or self.data.index[position] != buy_date:
            return
        if position > self.view_end:
            return

        low, high = _price_range(visible)
        left, right = self._plot_edges()
        count = max(1, self.view_end - self.view_start + 1)

        def x_at(index: int) -> float:
            return left + ((index - self.view_start) + 0.5) / count * (right - left)

        def y_at(value: float) -> float:
            return _map_y(min(high, max(low, value)), low, high, panel)

        text_color = self.palette["text"]
        background = self.palette["chart_panel"]
        buy_close = float(self.data["Close"].iloc[position])
        line_color = readable_text_color(SIGNAL_STYLES[2][2], background, text_color)
        if low <= buy_close <= high:
            start_x = x_at(position) if position >= self.view_start else left
            buy_y = y_at(buy_close)
            self.canvas.create_line(
                start_x,
                buy_y,
                right,
                buy_y,
                fill=line_color,
                dash=(5, 3),
                width=1,
                tags="buy_marker",
            )
            self._create_label_with_background(
                right - 4,
                buy_y - 3,
                text=f"매수 {_number(buy_close)}",
                anchor="se",
                fill=line_color,
            )

        for label, weeks, value_column, status_column in BUY_MARKER_HORIZONS:
            target = position + weeks
            if not self.view_start <= target <= self.view_end or target >= len(self.data):
                continue
            value = cycle.get(value_column)
            if cycle.get(status_column) != "확정" or value is None or pd.isna(value):
                continue
            x = x_at(target)
            y = y_at(float(self.data["Close"].iloc[target]))
            color = readable_text_color(
                CANDLE_UP_COLOR if float(value) >= 0 else CANDLE_DOWN_COLOR,
                background,
                text_color,
            )
            self.canvas.create_oval(
                x - 4, y - 4, x + 4, y + 4, outline=color, width=2, tags="buy_marker"
            )
            self._create_label_with_background(
                x,
                max(panel.top + 14, y - 7),
                text=f"{label} {float(value):+.1f}%",
                anchor="s",
                fill=color,
            )

    def _create_label_with_background(
        self,
        x: float,
        y: float,
        text: str,
        anchor: str,
        fill: str,
    ) -> None:
        """Draw a small label on a panel-colored box so candles don't hide it."""
        item = self.canvas.create_text(
            x,
            y,
            text=text,
            anchor=anchor,
            fill=fill,
            font=(self.ui_font_family, 8, "bold"),
            tags="buy_marker",
        )
        box = self.canvas.bbox(item)
        if box:
            background = self.canvas.create_rectangle(
                box[0] - 2,
                box[1] - 1,
                box[2] + 2,
                box[3] + 1,
                fill=self.palette["chart_panel"],
                outline="",
                tags="buy_marker",
            )
            self.canvas.tag_raise(item, background)

    def _draw_date_axis(self, data: pd.DataFrame, xs: np.ndarray, bottom: float) -> None:
        if data.empty:
            return
        tick_count = min(10, len(data))
        positions = np.unique(np.linspace(0, len(data) - 1, tick_count).astype(int))
        for position in positions:
            date = pd.Timestamp(data.index[position]).strftime("%Y-%m-%d")
            self.canvas.create_text(
                xs[position],
                bottom + 8,
                text=date,
                anchor="n",
                fill=self.palette["chart_text"],
                font=(self.ui_font_family, 8),
            )

    def _comparison_plot_edges(self) -> tuple[float, float]:
        return 64.0, max(180.0, self.comparison_canvas.winfo_width() - 92.0)

    def _comparison_panels(self) -> list[Panel]:
        original_canvas = self.canvas
        self.canvas = self.comparison_canvas
        try:
            panels = self._panels()
        finally:
            self.canvas = original_canvas
        price = panels[0]
        panels[0] = Panel(f"S&P 500 ({BENCHMARK_TICKER})", price.top, price.bottom)
        return panels

    def _benchmark_slice(self) -> pd.DataFrame:
        if self.data.empty or self.benchmark_data.empty:
            return pd.DataFrame()
        start_date = self.data.index[self.view_start]
        end_date = self.data.index[self.view_end]
        start, end = comparison_view_indices(
            self.benchmark_data.index,
            start_date,
            end_date,
        )
        return self.benchmark_data.iloc[start : end + 1]

    def _redraw_benchmark(self) -> None:
        self.comparison_canvas.delete("all")
        if not self.benchmark_visible:
            return
        if self.benchmark_loading:
            self.comparison_canvas.create_text(
                max(1, self.comparison_canvas.winfo_width()) / 2,
                max(1, self.comparison_canvas.winfo_height()) / 2,
                text="S&P 500 데이터를 불러오는 중입니다...",
                fill=self.palette["chart_text"],
                font=(self.ui_font_family, 10),
            )
            return
        visible = self._benchmark_slice()
        if visible.empty or self.comparison_canvas.winfo_width() < 160:
            return

        original_canvas = self.canvas
        self.canvas = self.comparison_canvas
        try:
            panels = self._comparison_panels()
            xs = self._x_positions(len(visible))
            self._draw_panel_frames(panels, visible)
            self._draw_price(panels[0], visible, xs)
            self._draw_volume(panels[1], visible, xs)
            self._draw_momentum(panels[2], visible, xs)
            self._draw_macd(panels[3], visible, xs)
            self._draw_oscillator(panels[4], visible, xs, "RSI")
            self._draw_oscillator(panels[5], visible, xs, "MFI")
            self._draw_date_axis(visible, xs, panels[-1].bottom)
            self._draw_panel_hover_values(panels, visible.iloc[-1])
        finally:
            self.canvas = original_canvas

        self._draw_benchmark_signal_lines(panels, visible)
        self._set_benchmark_status(visible.index[-1])

    def _draw_benchmark_signal_lines(
        self,
        panels: list[Panel],
        visible: pd.DataFrame,
    ) -> None:
        if self.cycle is None or visible.empty:
            return
        left, right = self._comparison_plot_edges()
        count = len(visible)
        for label, column, color in SIGNAL_STYLES:
            signal_date = _timestamp(self.cycle.get(column))
            if signal_date is None or signal_date < visible.index[0] or signal_date > visible.index[-1]:
                continue
            position = int(visible.index.searchsorted(signal_date, side="left"))
            position = min(count - 1, max(0, position))
            x = left + (position + 0.5) / max(1, count) * (right - left)
            faded = _blend_hex(
                color,
                self.palette["chart_panel"],
                BENCHMARK_SIGNAL_OPACITY,
            )
            self.comparison_canvas.create_line(
                x,
                panels[0].top,
                x,
                panels[-1].bottom,
                fill=faded,
                width=BENCHMARK_SIGNAL_WIDTH,
                dash=(5, 3),
            )
            self.comparison_canvas.create_text(
                x + 3,
                panels[0].top + 22,
                text=f"{self.ticker} {label}",
                anchor="nw",
                fill=faded,
                font=(self.ui_font_family, 8, "bold"),
            )

    def _show_benchmark_values(
        self,
        panels: list[Panel],
        row: pd.Series,
        date,
    ) -> None:
        original_canvas = self.canvas
        self.canvas = self.comparison_canvas
        try:
            self._draw_panel_hover_values(panels, row)
        finally:
            self.canvas = original_canvas
        self._set_benchmark_status(date)

    def _set_benchmark_status(self, date) -> None:
        self.comparison_status_var.set(
            f"S&P 500 (^GSPC)  |  {pd.Timestamp(date).strftime('%Y-%m-%d')}"
        )

    def _on_motion(self, event) -> None:
        if self.data.empty or self._drag_origin is not None:
            return
        left, right = self._plot_edges()
        panels = self._panels()
        if event.x < left or event.x > right or event.y < panels[0].top or event.y > panels[-1].bottom:
            self._clear_crosshair()
            return

        count = self.view_end - self.view_start + 1
        relative = (event.x - left) / max(1.0, right - left)
        offset = min(count - 1, max(0, int(relative * count)))
        position = self.view_start + offset
        x = left + (offset + 0.5) / max(1, count) * (right - left)
        self.canvas.delete("crosshair")
        self.canvas.create_line(
            x,
            panels[0].top,
            x,
            panels[-1].bottom,
            fill=self.palette["crosshair"],
            dash=(3, 3),
            tags="crosshair",
        )
        self.canvas.create_line(
            left,
            event.y,
            right,
            event.y,
            fill=self.palette["crosshair"],
            dash=(3, 3),
            tags="crosshair",
        )
        row = self.data.iloc[position]
        date = self.data.index[position].strftime("%Y-%m-%d")
        self._draw_panel_hover_values(panels, row)
        self._draw_crosshair_date(x, panels[-1].bottom, date)
        self._draw_comparison_crosshair(pd.Timestamp(self.data.index[position]))
        self.hover_var.set(f"{date}  |  십자선 수치는 각 보조지표 제목 옆에 표시됩니다.")

    def _on_comparison_motion(self, event) -> None:
        if not self.benchmark_visible or self.benchmark_data.empty or self._drag_origin is not None:
            return
        visible = self._benchmark_slice()
        if visible.empty:
            return
        left, right = self._comparison_plot_edges()
        panels = self._comparison_panels()
        if (
            event.x < left
            or event.x > right
            or event.y < panels[0].top
            or event.y > panels[-1].bottom
        ):
            self._clear_crosshair()
            return
        relative = (event.x - left) / max(1.0, right - left)
        offset = min(len(visible) - 1, max(0, int(relative * len(visible))))
        date = pd.Timestamp(visible.index[offset])
        self._draw_comparison_crosshair(date, horizontal_y=event.y)
        self._draw_primary_crosshair(date)

    def _draw_comparison_crosshair(
        self,
        date: pd.Timestamp,
        horizontal_y: float | None = None,
    ) -> None:
        if not self.benchmark_visible or self.benchmark_data.empty:
            return
        visible = self._benchmark_slice()
        if visible.empty:
            return
        position = int(visible.index.searchsorted(pd.Timestamp(date), side="left"))
        position = min(len(visible) - 1, max(0, position))
        left, right = self._comparison_plot_edges()
        panels = self._comparison_panels()
        x = left + (position + 0.5) / max(1, len(visible)) * (right - left)
        self.comparison_canvas.delete("crosshair")
        self.comparison_canvas.create_line(
            x,
            panels[0].top,
            x,
            panels[-1].bottom,
            fill=self.palette["crosshair"],
            dash=(3, 3),
            tags="crosshair",
        )
        row = visible.iloc[position]
        actual_date = pd.Timestamp(visible.index[position])
        if horizontal_y is None:
            horizontal_y = price_crosshair_y(visible, panels[0], row.get("Close"))
        if horizontal_y is not None:
            self.comparison_canvas.create_line(
                left,
                horizontal_y,
                right,
                horizontal_y,
                fill=self.palette["crosshair"],
                dash=(3, 3),
                tags="crosshair",
            )
        self._show_benchmark_values(panels, row, actual_date)
        self._draw_comparison_crosshair_date(
            x,
            panels[-1].bottom,
            actual_date.strftime("%Y-%m-%d"),
        )

    def _draw_primary_crosshair(self, date: pd.Timestamp) -> None:
        if self.data.empty:
            return
        position = int(self.data.index.searchsorted(pd.Timestamp(date), side="left"))
        position = min(self.view_end, max(self.view_start, position))
        count = self.view_end - self.view_start + 1
        left, right = self._plot_edges()
        panels = self._panels()
        x = left + ((position - self.view_start) + 0.5) / max(1, count) * (right - left)
        self.canvas.delete("crosshair")
        self.canvas.create_line(
            x,
            panels[0].top,
            x,
            panels[-1].bottom,
            fill=self.palette["crosshair"],
            dash=(3, 3),
            tags="crosshair",
        )
        row = self.data.iloc[position]
        actual_date = pd.Timestamp(self.data.index[position])
        visible = self.data.iloc[self.view_start : self.view_end + 1]
        horizontal_y = price_crosshair_y(visible, panels[0], row.get("Close"))
        if horizontal_y is not None:
            self.canvas.create_line(
                left,
                horizontal_y,
                right,
                horizontal_y,
                fill=self.palette["crosshair"],
                dash=(3, 3),
                tags="crosshair",
            )
        self._draw_panel_hover_values(panels, row)
        self._draw_crosshair_date(x, panels[-1].bottom, actual_date.strftime("%Y-%m-%d"))
        self.hover_var.set(
            f"{actual_date.strftime('%Y-%m-%d')}  |  S&P 500 차트와 십자선 연동"
        )

    def _draw_crosshair_date(self, x: float, bottom: float, date: str) -> None:
        left, right = self._plot_edges()
        half_width = self.panel_value_font.measure(date) / 2 + 6
        center_x = min(right - half_width, max(left + half_width, x))
        top = bottom + 2
        label_bottom = bottom + 21
        self.canvas.create_rectangle(
            center_x - half_width,
            top,
            center_x + half_width,
            label_bottom,
            outline=self.palette["date_label_background"],
            fill=self.palette["date_label_background"],
            tags=("crosshair", "crosshair_date_background"),
        )
        self.canvas.create_text(
            center_x,
            (top + label_bottom) / 2,
            text=date,
            fill=self.palette["date_label_text"],
            font=self.panel_value_font,
            tags=("crosshair", "crosshair_date_label"),
        )

    def _draw_comparison_crosshair_date(self, x: float, bottom: float, date: str) -> None:
        left, right = self._comparison_plot_edges()
        half_width = self.panel_value_font.measure(date) / 2 + 6
        center_x = min(right - half_width, max(left + half_width, x))
        top = bottom + 2
        label_bottom = bottom + 21
        self.comparison_canvas.create_rectangle(
            center_x - half_width,
            top,
            center_x + half_width,
            label_bottom,
            outline=self.palette["date_label_background"],
            fill=self.palette["date_label_background"],
            tags="crosshair",
        )
        self.comparison_canvas.create_text(
            center_x,
            (top + label_bottom) / 2,
            text=date,
            fill=self.palette["date_label_text"],
            font=self.panel_value_font,
            tags="crosshair",
        )

    def _draw_panel_hover_values(self, panels: list[Panel], row: pd.Series) -> None:
        self.canvas.delete("panel_hover_value")
        ma_styles = moving_average_styles(self.theme_mode)
        price_values = [
            ("O", row["Open"], self.palette["muted"], False),
            ("H", row["High"], CANDLE_UP_COLOR, False),
            ("L", row["Low"], CANDLE_DOWN_COLOR, False),
            ("C", row["Close"], self.palette["text"], False),
            *[
                (column.replace("MA_", "MA"), row[column], color, False)
                for column, (color, _width) in ma_styles.items()
            ],
        ]
        specifications = (
            (panels[0], "price", price_values),
            (
                panels[1],
                "volume",
                [
                    ("", row["Volume"], self.palette["muted"], True),
                    ("평균", row["Volume_MA_50"], VOLUME_MA_STYLE[0], True),
                ],
            ),
            (
                panels[2],
                "momentum",
                [
                    (
                        "",
                        row["Momentum"],
                        self._indicator_bar_color(row["Momentum"] >= 0),
                        False,
                    )
                ],
            ),
            (
                panels[3],
                "macd",
                [
                    (
                        "Histogram",
                        row["Histogram"],
                        self._indicator_bar_color(row["Histogram"] >= 0),
                        False,
                    ),
                    ("MACD", row["MACD"], "#ff5b5b", False),
                    ("Signal", row["Signal"], MACD_SIGNAL_COLOR, False),
                ],
            ),
            (panels[4], "rsi", [("", row["RSI"], OSCILLATOR_LINE_COLOR, False)]),
            (panels[5], "mfi", [("", row["MFI"], OSCILLATOR_LINE_COLOR, False)]),
        )

        left, _right = self._plot_edges()
        for panel, tag_prefix, values in specifications:
            x = left + 16 + self.panel_title_font.measure(panel.name)
            for label, value, color, compact in values:
                formatted = _compact_number(value) if compact else _number(value)
                text = f"{label} {formatted}".strip()
                self.canvas.create_text(
                    x,
                    panel.top + 5,
                    text=text,
                    anchor="nw",
                    fill=readable_text_color(
                        color,
                        self.palette["chart_panel"],
                        self.palette["text"],
                    ),
                    font=self.panel_value_font,
                    tags=("panel_hover_value", f"{tag_prefix}_hover_value"),
                )
                x += self.panel_value_font.measure(text) + 9

    def _clear_crosshair(self, _event=None) -> None:
        self.canvas.delete("crosshair")
        self.comparison_canvas.delete("crosshair")
        if self.data.empty:
            return
        visible = self.data.iloc[self.view_start : self.view_end + 1]
        self._show_rightmost_values(self._panels(), visible)
        benchmark_visible = self._benchmark_slice()
        if self.benchmark_visible and not benchmark_visible.empty:
            self._show_benchmark_values(
                self._comparison_panels(),
                benchmark_visible.iloc[-1],
                benchmark_visible.index[-1],
            )

    def _show_rightmost_values(
        self,
        panels: list[Panel],
        visible: pd.DataFrame,
    ) -> None:
        if visible.empty:
            return
        row = visible.iloc[-1]
        date = visible.index[-1].strftime("%Y-%m-%d")
        self._draw_panel_hover_values(panels, row)
        self.hover_var.set(
            f"{date}  |  현재 화면의 가장 오른쪽 주봉 수치"
        )

    def _on_mousewheel(self, event) -> None:
        if self.data.empty or event.delta == 0:
            return
        left, right = self._plot_edges()
        anchor = min(1.0, max(0.0, (event.x - left) / max(1.0, right - left)))
        self._zoom_view(event.delta, anchor)

    def _on_comparison_mousewheel(self, event) -> None:
        if self.data.empty or event.delta == 0:
            return
        left, right = self._comparison_plot_edges()
        anchor = min(1.0, max(0.0, (event.x - left) / max(1.0, right - left)))
        self._zoom_view(event.delta, anchor)

    def _zoom_view(self, delta: int, anchor: float) -> None:
        count = self.view_end - self.view_start + 1
        new_count = int(
            round(count * (ZOOM_IN_FACTOR if delta > 0 else ZOOM_OUT_FACTOR))
        )
        new_count = min(len(self.data), max(12, new_count))
        anchor_index = self.view_start + int(anchor * max(0, count - 1))
        new_start = anchor_index - int(anchor * max(0, new_count - 1))
        self.view_start, self.view_end = _clamped_view(new_start, new_count, len(self.data))
        self._clear_crosshair()
        self._schedule_redraw()

    def _on_drag_start(self, event) -> None:
        if self.data.empty:
            return
        left, right = self._plot_edges()
        self._start_drag(event.x, right - left)

    def _on_comparison_drag_start(self, event) -> None:
        if self.data.empty:
            return
        left, right = self._comparison_plot_edges()
        self._start_drag(event.x, right - left)

    def _start_drag(self, x: int, plot_width: float) -> None:
        self._drag_origin = (x, self.view_start, self.view_end, max(1.0, plot_width))
        self.canvas.configure(cursor="fleur")
        self.comparison_canvas.configure(cursor="fleur")

    def _on_drag_motion(self, event) -> None:
        if self._drag_origin is None:
            return
        self._update_drag(event.x)

    def _on_comparison_drag_motion(self, event) -> None:
        if self._drag_origin is None:
            return
        self._update_drag(event.x)

    def _update_drag(self, x: int) -> None:
        origin_x, origin_start, origin_end, plot_width = self._drag_origin
        count = origin_end - origin_start + 1
        shift = int(round((origin_x - x) / plot_width * count))
        self.view_start, self.view_end = _clamped_view(origin_start + shift, count, len(self.data))
        self._schedule_redraw()

    def _on_drag_end(self, _event=None) -> None:
        self._drag_origin = None
        self.canvas.configure(cursor="crosshair")
        self.comparison_canvas.configure(cursor="crosshair")

    def _reset_view(self, _event=None) -> None:
        if self.data.empty:
            return
        self.view_start, self.view_end = self.initial_view
        self._drag_origin = None
        self._clear_crosshair()
        self._schedule_redraw()


def _normalized_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(pd.to_datetime(index))
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    return dates


def _timestamp(value) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)
    return timestamp


def _date_text(value) -> str:
    timestamp = _timestamp(value)
    return timestamp.strftime("%Y-%m-%d") if timestamp is not None else "-"


def _finite_range(values, include_zero: bool = False, padding: float = 0.05) -> tuple[float, float]:
    array = np.asarray(values, dtype=float).reshape(-1)
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        return 0.0, 1.0
    low = float(finite.min())
    high = float(finite.max())
    if include_zero:
        low = min(0.0, low)
        high = max(0.0, high)
    if low == high:
        margin = max(abs(low) * 0.05, 1.0)
    else:
        margin = (high - low) * padding
    return low - margin, high + margin


def _map_y(value: float, low: float, high: float, panel: Panel) -> float:
    if high <= low:
        return (panel.top + panel.bottom) / 2
    ratio = (float(value) - low) / (high - low)
    return panel.bottom - ratio * (panel.bottom - panel.top)


def _price_range(data: pd.DataFrame) -> tuple[float, float]:
    """Fit the price panel to the candles.

    Moving averages only widen the range when they are close to the candles;
    a far-away 150/200-week line would otherwise squash the candles, so it is
    clipped at the panel edge instead.
    """
    candles = data[["Low", "High"]].to_numpy(dtype=float).reshape(-1)
    candles = candles[np.isfinite(candles)]
    averages = data[list(MA_STYLES)].to_numpy(dtype=float).reshape(-1)
    averages = averages[np.isfinite(averages)]
    if candles.size == 0:
        return _finite_range(averages, padding=0.06)
    low, high = float(candles.min()), float(candles.max())
    margin = max(high - low, abs(high) * 0.05) * PRICE_RANGE_MA_MARGIN
    nearby = averages[(averages >= low - margin) & (averages <= high + margin)]
    return _finite_range(np.concatenate([candles, nearby]), padding=0.06)


def price_crosshair_y(
    data: pd.DataFrame,
    panel: Panel,
    close_value: object,
) -> float | None:
    """Map one synchronized date's close to its own chart price panel."""
    numeric_close = pd.to_numeric(pd.Series([close_value]), errors="coerce").iloc[0]
    if pd.isna(numeric_close) or data.empty:
        return None
    low, high = _price_range(data)
    return _map_y(float(numeric_close), low, high, panel)


def _clamped_view(start: int, count: int, total: int) -> tuple[int, int]:
    count = min(total, max(1, count))
    start = min(max(0, start), total - count)
    return start, start + count - 1


def _number(value: float) -> str:
    if pd.isna(value):
        return "-"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def _compact_number(value: float) -> str:
    if pd.isna(value):
        return "-"
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f}K"
    return _number(value)
