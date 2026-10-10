"""Watchlist tab: tickers scanned in addition to the Top 100."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import pandas as pd

from csv_io import describe_save_error
from watchlist import (
    WatchlistItem,
    add_watchlist_item,
    load_watchlist,
    remove_watchlist_item,
    save_watchlist,
)
from gui.tables import populate_table

WATCHLIST_DISPLAY_COLUMNS = ["티커", "이름"]


class WatchlistMixin:
    """Watchlist tab. Mixed into BuyPointApp; relies on its attributes."""

    def _build_watchlist_tab(self, parent: ttk.Frame) -> None:
        self.watchlist_items: list[WatchlistItem] = load_watchlist()
        self.watchlist_ticker_var = tk.StringVar()
        self.watchlist_name_var = tk.StringVar()

        controls = ttk.Frame(parent, padding=(4, 6, 4, 2))
        controls.pack(fill="x")
        ttk.Label(controls, text="티커").pack(side="left")
        ticker_entry = ttk.Entry(controls, textvariable=self.watchlist_ticker_var, width=12)
        ticker_entry.pack(side="left", padx=(4, 10))
        ttk.Label(controls, text="이름(선택)").pack(side="left")
        name_entry = ttk.Entry(controls, textvariable=self.watchlist_name_var, width=22)
        name_entry.pack(side="left", padx=(4, 10))
        for entry in (ticker_entry, name_entry):
            entry.bind("<Return>", lambda _event: self.add_watchlist_ticker())
        ttk.Button(controls, text="추가", command=self.add_watchlist_ticker).pack(side="left")
        ttk.Button(
            controls,
            text="선택 삭제",
            command=self.remove_selected_watchlist_ticker,
        ).pack(side="left", padx=(6, 0))

        note = ttk.Label(
            parent,
            text=(
                "관심종목은 다음 통합 스캔부터 Top 100과 함께 검사합니다. 야후 파이낸스 티커를 "
                "씁니다(예: 비트코인 BTC-USD). 행을 누르면 그 종목을 검색합니다. 금요일 자동 "
                "스캔은 GitHub에 올라간 watchlist.txt를 기준으로 합니다."
            ),
            style="LegendNote.TLabel",
            justify="left",
            padding=(4, 2, 4, 4),
        )
        note.pack(fill="x")
        self._wrap_to_width(note, parent, margin=20)

        table_frame = ttk.Frame(parent)
        table_frame.pack(fill="both", expand=True)
        self.watchlist_tree = self._create_table(table_frame)
        self.watchlist_tree.bind(
            "<<TreeviewSelect>>",
            lambda event: self._on_scan_row_select(event, self.watchlist_tree),
        )
        self._refresh_watchlist_table()

    def _refresh_watchlist_table(self) -> None:
        populate_table(
            self.watchlist_tree,
            pd.DataFrame(
                [
                    {"티커": item.ticker, "이름": item.display_name}
                    for item in self.watchlist_items
                ],
                columns=WATCHLIST_DISPLAY_COLUMNS,
            ),
        )

    def add_watchlist_ticker(self) -> None:
        try:
            items = add_watchlist_item(
                self.watchlist_items,
                self.watchlist_ticker_var.get(),
                self.watchlist_name_var.get(),
            )
        except ValueError as exc:
            messagebox.showinfo("관심종목", str(exc))
            return
        if self._save_watchlist(items):
            self.watchlist_ticker_var.set("")
            self.watchlist_name_var.set("")

    def remove_selected_watchlist_ticker(self) -> None:
        selected = self.watchlist_tree.selection()
        if not selected:
            messagebox.showinfo("관심종목", "삭제할 종목을 표에서 먼저 선택해 주세요.")
            return
        ticker = self.watchlist_tree.set(selected[0], "티커")
        self._save_watchlist(remove_watchlist_item(self.watchlist_items, ticker))

    def _save_watchlist(self, items: list[WatchlistItem]) -> bool:
        try:
            save_watchlist(items)
        except OSError as exc:
            messagebox.showerror("관심종목 저장 실패", describe_save_error(exc))
            return False
        self.watchlist_items = items
        self._refresh_watchlist_table()
        return True
