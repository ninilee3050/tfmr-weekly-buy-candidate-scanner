"""Scanner dashboard cards and the selected ticker's summary cards."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from gui.config import ACTIVE_SCENARIOS_TAB, SCAN_EVENTS_TAB
from gui.tooltips import (
    DASHBOARD_CARD_DESCRIPTIONS,
    SUMMARY_CARD_DESCRIPTIONS,
    attach_widget_tooltip,
)
from gui.formatting import dashboard_summary, trade_summary_cards
from gui.tables import card_grid_columns


class CardsMixin:
    """Scanner dashboard cards and ticker summary cards. Mixed into BuyPointApp; relies on its attributes."""

    @staticmethod
    def _make_responsive_card_row(
        frame: ttk.Frame,
        cards: list[ttk.Frame],
        min_card_width: int,
    ) -> None:
        """Lay cards out in one row, or two rows when the area is too narrow."""
        state = {"columns": 0}

        def layout(width: int) -> None:
            columns = card_grid_columns(width, len(cards), min_card_width)
            if columns == state["columns"]:
                return
            state["columns"] = columns
            for index in range(len(cards)):
                frame.columnconfigure(index, weight=0, uniform="")
            for index, card in enumerate(cards):
                row, column = divmod(index, columns)
                frame.columnconfigure(column, weight=1, uniform="cards")
                card.grid(
                    row=row,
                    column=column,
                    sticky="nsew",
                    padx=(0 if column == 0 else 6, 0),
                    pady=(0 if row == 0 else 6, 0),
                )

        layout(10_000)
        frame.bind("<Configure>", lambda event: layout(event.width), add="+")

    def _build_dashboard(self, parent: ttk.Frame) -> None:
        """Summary cards above the scanner tabs; a click opens the matching tab."""
        frame = ttk.Frame(parent, padding=(0, 8, 0, 0))
        frame.grid(row=1, column=0, sticky="ew")
        cards = (
            ("first", "이번 스캔 신규 1차", SCAN_EVENTS_TAB),
            ("add", "이번 스캔 추가매수", SCAN_EVENTS_TAB),
            ("sell", "이번 스캔 매도 신호", SCAN_EVENTS_TAB),
            ("holding", "보유 중", ACTIVE_SCENARIOS_TAB),
        )
        self.dashboard_cards: dict[str, dict[str, object]] = {}
        dashboard_frames: list[ttk.Frame] = []
        for key, title, tab_index in cards:
            card = ttk.Frame(frame, style="Card.TFrame", padding=(12, 8))
            dashboard_frames.append(card)
            value_var = tk.StringVar(value="-")
            note_var = tk.StringVar(value="")
            title_label = ttk.Label(card, text=title, style="CardTitle.TLabel")
            value_label = ttk.Label(card, textvariable=value_var, style="CardValue.TLabel")
            note_label = ttk.Label(card, textvariable=note_var, style="CardNote.TLabel")
            for widget in (title_label, value_label, note_label):
                widget.pack(anchor="w")
            for widget in (card, title_label, value_label, note_label):
                attach_widget_tooltip(
                    self.term_tooltip,
                    widget,
                    DASHBOARD_CARD_DESCRIPTIONS[key],
                )
            if tab_index is not None:
                for widget in (card, title_label, value_label, note_label):
                    widget.configure(cursor="hand2")
                    widget.bind(
                        "<Button-1>",
                        lambda _event, index=tab_index: self.scan_notebook.select(index),
                    )
            self.dashboard_cards[key] = {
                "value": value_var,
                "note": note_var,
                "value_label": value_label,
                "note_label": note_label,
            }
        self._make_responsive_card_row(frame, dashboard_frames, min_card_width=170)

    def _refresh_dashboard(self) -> None:
        summary = dashboard_summary(
            self.latest_scan_events,
            self.latest_active_scenarios,
            has_scan_results=(
                self.latest_scan_date is not None or self.last_scan_time is not None
            ),
        )
        for key, (value, note, alert) in summary.items():
            card = self.dashboard_cards[key]
            card["value"].set(value)
            card["note"].set(note)
            card["value_label"].configure(
                style="CardAlert.TLabel" if alert and key == "sell" else "CardValue.TLabel"
            )

    def _build_summary_cards(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, 6, 0, 0))
        frame.pack(fill="x")
        self.summary_cards: dict[str, tuple[tk.StringVar, tk.StringVar]] = {}
        card_frames: list[ttk.Frame] = []
        for key, title in (
            ("closed", "매도 완료"),
            ("win", "승률"),
            ("average", "평균 수익률"),
        ):
            card = ttk.Frame(frame, style="Card.TFrame", padding=(10, 6))
            card_frames.append(card)
            value_var = tk.StringVar(value="-")
            note_var = tk.StringVar(value="")
            widgets = (
                card,
                ttk.Label(card, text=title, style="CardTitle.TLabel"),
                ttk.Label(card, textvariable=value_var, style="HorizonValue.TLabel"),
                ttk.Label(card, textvariable=note_var, style="CardNote.TLabel"),
            )
            for widget in widgets[1:]:
                widget.pack(anchor="w")
            for widget in widgets:
                attach_widget_tooltip(
                    self.term_tooltip,
                    widget,
                    SUMMARY_CARD_DESCRIPTIONS[key],
                )
            self.summary_cards[key] = (value_var, note_var)
        self._make_responsive_card_row(frame, card_frames, min_card_width=165)
        self._set_summary_cards(None)

    def _set_summary_cards(self, cases: pd.DataFrame | None) -> None:
        for key, (value, note) in trade_summary_cards(cases).items():
            value_var, note_var = self.summary_cards[key]
            value_var.set(value)
            note_var.set(note)
