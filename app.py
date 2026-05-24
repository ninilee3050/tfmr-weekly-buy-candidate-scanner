from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd

from data_provider import DataLoadError, load_weekly_data, normalize_ticker
from market_cap_provider import MarketCapCompany, MarketCapLoadError, fetch_us_top_market_cap
from tfmr_scanner import BUY_POINT_COLUMNS, scan_tfmr_buy_points
from weekly_scan import SCAN_FAILURE_COLUMNS, SCAN_RESULT_COLUMNS, save_scan_outputs, scan_companies


OUTPUT_DIR = Path("outputs")
DOWNLOADS_DIR = Path.home() / "Downloads"
BUY_DISPLAY_COLUMNS = ["매수포인트날짜", *BUY_POINT_COLUMNS]


class TfmrBuyBaseApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("TFMR 1회차 매수 기준봉 검증 도구")
        self.geometry("2920x900")
        self.minsize(2200, 720)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        self.ticker_var = tk.StringVar()
        self.status_var = tk.StringVar(value="티커를 입력하거나 왼쪽 Top100에서 종목을 선택해 주세요.")
        self.top100_status_var = tk.StringVar(value="Top100 목록을 불러오려면 버튼을 눌러 주세요.")
        self.scan_status_var = tk.StringVar(value="Top100 이번주 후보를 찾으려면 스캔을 실행해 주세요.")
        self.top100_companies: list[MarketCapCompany] = []
        self.latest_scan_candidates = pd.DataFrame(columns=SCAN_RESULT_COLUMNS)
        self.latest_scan_failures = pd.DataFrame(columns=SCAN_FAILURE_COLUMNS)
        self.latest_scan_date: pd.Timestamp | None = None

        self._build_layout()

    def _build_layout(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=0, minsize=470)
        main.columnconfigure(1, weight=1, minsize=1120)
        main.columnconfigure(2, weight=1, minsize=1280)
        main.rowconfigure(0, weight=1)

        self._build_left_panel(main)
        self._build_center_panel(main)
        self._build_right_panel(main)

    def _build_left_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="미국 시가총액 Top100", padding=8)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        self.top100_button = ttk.Button(panel, text="Top 100 불러오기", command=self.load_top100)
        self.top100_button.grid(row=0, column=0, sticky="ew")

        status = ttk.Label(panel, textvariable=self.top100_status_var, wraplength=420, padding=(0, 6))
        status.grid(row=1, column=0, sticky="ew")

        self.top100_tree = self._create_top100_table(panel)
        self.top100_tree.bind("<<TreeviewSelect>>", self._on_top100_select)

    def _build_center_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent)
        panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        search = ttk.Frame(panel)
        search.grid(row=0, column=0, sticky="ew")
        search.columnconfigure(0, weight=1)

        self.search_entry = ttk.Entry(search, textvariable=self.ticker_var, font=("Segoe UI", 15))
        self.search_entry.grid(row=0, column=0, sticky="ew", ipady=5)
        self.search_entry.bind("<Return>", lambda _event: self.run_search())
        self.search_entry.focus_set()

        self.search_button = ttk.Button(search, text="검색", command=self.run_search)
        self.search_button.grid(row=0, column=1, padx=(8, 0), ipady=3)

        status = ttk.Label(panel, textvariable=self.status_var, wraplength=1030, padding=(0, 8))
        status.grid(row=1, column=0, sticky="ew")

        table_frame = ttk.LabelFrame(panel, text="과거 1회차 매수 기준봉", padding=4)
        table_frame.grid(row=2, column=0, sticky="nsew")
        self.buy_tree = self._create_scrollable_table(table_frame)
        populate_table(self.buy_tree, pd.DataFrame(columns=BUY_DISPLAY_COLUMNS))

    def _build_right_panel(self, parent: ttk.Frame) -> None:
        panel = ttk.LabelFrame(parent, text="Top100 이번주 매수후보 스캐너", padding=8)
        panel.grid(row=0, column=2, sticky="nsew")
        panel.rowconfigure(2, weight=1)
        panel.columnconfigure(0, weight=1)

        buttons = ttk.Frame(panel)
        buttons.grid(row=0, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        self.scan_button = ttk.Button(buttons, text="Top 100 스캔", command=self.run_top100_scan)
        self.scan_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.scan_save_button = ttk.Button(
            buttons,
            text="스캔 저장하기",
            command=self.save_latest_scan,
            state="disabled",
        )
        self.scan_save_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        status = ttk.Label(panel, textvariable=self.scan_status_var, wraplength=1200, padding=(0, 6))
        status.grid(row=1, column=0, sticky="ew")

        self.scan_tree = self._create_scrollable_table(panel, row=2)
        populate_table(self.scan_tree, pd.DataFrame(columns=SCAN_RESULT_COLUMNS))
        self.scan_tree.bind("<<TreeviewSelect>>", self._on_scan_candidate_select)

    def _create_scrollable_table(
        self,
        parent: tk.Widget,
        row: int | None = None,
    ) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        if row is None:
            frame.pack(fill="both", expand=True)
        else:
            frame.grid(row=row, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        tree = ttk.Treeview(frame, show="headings", selectmode="browse")
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        return tree

    def _create_top100_table(self, parent: ttk.Frame) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        columns = ["순위", "티커", "회사명", "시가총액"]
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            tree.heading(column, text=column)
            width = _column_width(column)
            tree.column(column, width=width, minwidth=width, stretch=False)

        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=y_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        return tree

    def load_top100(self) -> None:
        self.top100_button.configure(state="disabled")
        self.top100_tree.delete(*self.top100_tree.get_children())
        self.top100_status_var.set("미국 시가총액 Top100 목록을 불러오는 중입니다...")
        threading.Thread(target=self._top100_worker, daemon=True).start()

    def _top100_worker(self) -> None:
        try:
            companies = fetch_us_top_market_cap(limit=100)
        except Exception as exc:
            self.after(0, self._show_top100_error, exc)
            return
        self.after(0, self._show_top100_result, companies)

    def _show_top100_result(self, companies: list[MarketCapCompany]) -> None:
        self._populate_top100(companies)
        self.top100_status_var.set(f"{len(companies)}개 종목을 불러왔습니다. 행을 클릭하면 바로 검색합니다.")
        self.top100_button.configure(state="normal")

    def _show_top100_error(self, exc: Exception) -> None:
        message = "Top100 목록을 불러오지 못했습니다. 인터넷 연결 또는 사이트 응답을 확인해 주세요."
        self.top100_companies = []
        self.top100_tree.delete(*self.top100_tree.get_children())
        self.top100_status_var.set(message)
        self.top100_button.configure(state="normal")
        messagebox.showerror("Top100 조회 실패", message)
        return

    def _populate_top100(self, companies: list[MarketCapCompany]) -> None:
        self.top100_companies = list(companies)
        self.top100_tree.delete(*self.top100_tree.get_children())
        for company in companies:
            self.top100_tree.insert(
                "",
                "end",
                values=(company.rank, company.ticker, company.company, company.market_cap),
            )

    def _on_top100_select(self, _event: object) -> None:
        selected = self.top100_tree.selection()
        if not selected:
            return
        ticker = self.top100_tree.set(selected[0], "티커")
        if ticker:
            self.ticker_var.set(ticker)
            self.run_search()

    def run_search(self) -> None:
        if str(self.search_button.cget("state")) == "disabled":
            return

        try:
            ticker = normalize_ticker(self.ticker_var.get())
        except ValueError as exc:
            messagebox.showinfo("입력 필요", str(exc))
            return

        self.search_button.configure(state="disabled")
        self.status_var.set(f"{ticker} 확정 주봉 데이터를 불러오는 중입니다...")
        threading.Thread(target=self._search_worker, args=(ticker,), daemon=True).start()

    def _search_worker(self, ticker: str) -> None:
        try:
            weekly = load_confirmed_weekly_for_search(ticker)
            buy_points, _full = scan_tfmr_buy_points(weekly)
            output_path = save_buy_points(ticker, buy_points)
        except Exception as exc:
            self.after(0, self._show_search_error, ticker, exc)
            return
        self.after(0, self._show_search_result, ticker, buy_points, output_path)

    def _show_search_result(self, ticker: str, buy_points: pd.DataFrame, output_path: Path) -> None:
        populate_table(self.buy_tree, buy_points_for_display(buy_points))
        self.status_var.set(
            f"{ticker}: 과거 확정 1회차 매수 기준봉 {len(buy_points)}개를 찾았습니다. "
            f"CSV 저장: {output_path}"
        )
        self.search_button.configure(state="normal")

    def _show_search_error(self, ticker: str, exc: Exception) -> None:
        message = str(exc) if isinstance(exc, DataLoadError) else f"{ticker} 처리 중 오류: {exc}"
        self.status_var.set(message)
        self.search_button.configure(state="normal")
        messagebox.showerror("검색 실패", message)

    def run_top100_scan(self) -> None:
        if str(self.scan_button.cget("state")) == "disabled":
            return

        self.scan_button.configure(state="disabled")
        self.scan_save_button.configure(state="disabled")
        self.top100_button.configure(state="disabled")
        self.scan_tree.delete(*self.scan_tree.get_children())
        self.scan_status_var.set("Top100 이번주 후보 스캔을 준비하는 중입니다...")
        self.latest_scan_candidates = pd.DataFrame(columns=SCAN_RESULT_COLUMNS)
        self.latest_scan_failures = pd.DataFrame(columns=SCAN_FAILURE_COLUMNS)
        self.latest_scan_date = None

        companies = list(self.top100_companies)
        threading.Thread(target=self._scan_worker, args=(companies,), daemon=True).start()

    def _scan_worker(self, companies: list[MarketCapCompany]) -> None:
        try:
            if not companies:
                self.after(0, self.scan_status_var.set, "Top100 목록을 먼저 불러오는 중입니다...")
                companies = fetch_us_top_market_cap(limit=100)
                self.after(0, self._populate_top100, companies)

            scan_date = pd.Timestamp.today().normalize()

            def progress(index: int, total: int, company: MarketCapCompany) -> None:
                self.after(0, self.scan_status_var.set, f"스캔 중... {index}/{total} {company.ticker}")

            candidates, failures = scan_companies(
                companies,
                scan_date=scan_date,
                force_refresh=True,
                progress_callback=progress,
            )
        except Exception as exc:
            self.after(0, self._show_scan_error, exc)
            return
        self.after(0, self._show_scan_result, candidates, failures, scan_date)

    def _show_scan_result(
        self,
        candidates: pd.DataFrame,
        failures: pd.DataFrame,
        scan_date: pd.Timestamp,
    ) -> None:
        self.latest_scan_candidates = candidates.copy()
        self.latest_scan_failures = failures.copy()
        self.latest_scan_date = scan_date
        populate_table(self.scan_tree, candidates)

        self.scan_status_var.set(
            f"스캔 완료: 이번주 매수후보 {len(candidates)}개, 실패 {len(failures)}개. "
            "결과는 아직 자동 저장되지 않았습니다."
        )
        self.scan_button.configure(state="normal")
        self.scan_save_button.configure(state="normal")
        self.top100_button.configure(state="normal")

    def _show_scan_error(self, exc: Exception) -> None:
        if isinstance(exc, MarketCapLoadError):
            message = "Top100 목록을 불러오지 못했습니다. 인터넷 연결 또는 사이트 응답을 확인해 주세요."
            self.top100_companies = []
            self.top100_tree.delete(*self.top100_tree.get_children())
        else:
            message = f"Top100 스캔 오류: {exc}"
        self.scan_status_var.set(message)
        self.scan_button.configure(state="normal")
        self.scan_save_button.configure(state="disabled")
        self.top100_button.configure(state="normal")
        messagebox.showerror("스캔 실패", message)
        return

    def save_latest_scan(self) -> None:
        if self.latest_scan_date is None:
            messagebox.showinfo("저장할 스캔 없음", "먼저 Top100 스캔을 실행해 주세요.")
            return

        candidate_path, failure_path = save_scan_outputs(
            self.latest_scan_candidates,
            self.latest_scan_failures,
            self.latest_scan_date,
            output_dir=DOWNLOADS_DIR,
        )
        self.scan_status_var.set(f"다운로드 폴더에 저장했습니다: {candidate_path} / {failure_path}")

    def _on_scan_candidate_select(self, _event: object) -> None:
        selected = self.scan_tree.selection()
        if not selected:
            return
        ticker = self.scan_tree.set(selected[0], "티커")
        if ticker:
            self.ticker_var.set(ticker)
            self.run_search()


def load_confirmed_weekly_for_search(ticker: str) -> pd.DataFrame:
    return load_weekly_data(
        ticker,
        include_current_week=False,
        force_refresh=True,
    )


def save_buy_points(
    ticker: str,
    buy_points: pd.DataFrame,
    output_dir: Path | str = OUTPUT_DIR,
) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{ticker}_tfmr_buy_points.csv"
    buy_points.to_csv(path, index_label="매수포인트날짜", encoding="utf-8-sig")
    return path


def buy_points_for_display(buy_points: pd.DataFrame) -> pd.DataFrame:
    if buy_points.empty:
        return pd.DataFrame(columns=BUY_DISPLAY_COLUMNS)

    display = buy_points.reset_index()
    if "Date" not in display.columns:
        display = display.rename(columns={display.columns[0]: "Date"})
    display = display.rename(columns={"Date": "매수포인트날짜"})
    return display[BUY_DISPLAY_COLUMNS]


def populate_table(tree: ttk.Treeview, data: pd.DataFrame) -> None:
    tree.delete(*tree.get_children())
    columns = list(data.columns)
    tree["columns"] = columns

    for column in columns:
        tree.heading(column, text=column)
        width = _column_width(column)
        tree.column(column, width=width, minwidth=width, stretch=False)

    for _, row in data.iterrows():
        tree.insert("", "end", values=[_format_value(row[column]) for column in columns])


def _column_width(column: str) -> int:
    widths = {
        "순위": 60,
        "티커": 78,
        "회사명": 180,
        "시가총액": 122,
        "매수포인트날짜": 132,
        "주봉시작일": 116,
        "스캔일": 106,
        "Open": 88,
        "Close": 88,
        "MA5": 74,
        "MA20": 82,
        "MA50": 82,
        "MA150": 92,
        "MA200": 92,
        "ConditionSummary": 520,
        "오류": 260,
    }
    return widths.get(column, 110)


def _format_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


if __name__ == "__main__":
    app = TfmrBuyBaseApp()
    app.mainloop()
