"""Scanner dashboard cards and 3/6/9/12-month cards."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from scenario_tracker import latest_scan_date, market_today
from gui.config import ACTIVE_SCENARIOS_TAB, HORIZON_CARD_MONTHS, SCAN_EVENTS_TAB
from gui.tooltips import (
    DASHBOARD_CARD_DESCRIPTIONS,
    HORIZON_CARD_TERMS,
    TERM_DESCRIPTIONS,
    attach_widget_tooltip,
)
from gui.formatting import dashboard_summary, horizon_card_lines
from gui.tables import card_grid_columns


class CardsMixin:
    """Scanner dashboard cards and 3/6/9/12-month cards. Mixed into BuyPointApp; relies on its attributes."""

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
            ("buy", "이번 스캔 3차 매수", SCAN_EVENTS_TAB),
            ("wait3", "3차 신호 대기", ACTIVE_SCENARIOS_TAB),
            ("wait2", "2차 신호 대기", ACTIVE_SCENARIOS_TAB),
            ("last", "마지막 스캔", None),
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
        last_scan = self.latest_scan_date
        if last_scan is None:
            last_scan = latest_scan_date(self.latest_active_scenarios)
        summary = dashboard_summary(
            self.latest_scan_events,
            self.latest_active_scenarios,
            has_scan_results=(
                self.latest_scan_date is not None or self.last_scan_time is not None
            ),
            last_scan_date=last_scan,
            today=market_today(),
            last_scan_time=self.last_scan_time,
            now=pd.Timestamp.now(),
        )
        for key, (value, note, alert) in summary.items():
            card = self.dashboard_cards[key]
            card["value"].set(value)
            card["note"].set(note)
            card["value_label"].configure(
                style="CardAlert.TLabel" if alert and key == "buy" else "CardValue.TLabel"
            )
            card["note_label"].configure(
                style="CardNoteAlert.TLabel" if alert else "CardNote.TLabel"
            )

    def _build_horizon_cards(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=(0, 6, 0, 0))
        frame.pack(fill="x")
        self.horizon_cards: dict[int, dict[str, object]] = {}
        horizon_frames: list[ttk.Frame] = []
        for months in HORIZON_CARD_MONTHS:
            card = ttk.Frame(frame, style="Card.TFrame", padding=(10, 6))
            horizon_frames.append(card)
            ttk.Label(card, text=f"{months}개월 후", style="CardTitle.TLabel").pack(anchor="w")
            labels = {}
            for name, style in (
                ("win", "HorizonValue.TLabel"),
                ("sample", "CardNote.TLabel"),
                ("nearby", "CardNote.TLabel"),
                ("sp500", "CardNote.TLabel"),
            ):
                variable = tk.StringVar(value="")
                label = ttk.Label(card, textvariable=variable, style=style)
                label.pack(anchor="w")
                labels[name] = (variable, label)
                attach_widget_tooltip(
                    self.term_tooltip,
                    label,
                    TERM_DESCRIPTIONS[HORIZON_CARD_TERMS[name]],
                )
            self.horizon_cards[months] = labels
        self._make_responsive_card_row(frame, horizon_frames, min_card_width=165)
        self._set_horizon_cards(None)

    def _set_horizon_cards(self, performance_by_horizon: dict[int, pd.Series] | None) -> None:
        for months, labels in self.horizon_cards.items():
            row = performance_by_horizon.get(months) if performance_by_horizon else None
            for name, (text, tone) in horizon_card_lines(row).items():
                variable, label = labels[name]
                variable.set(text)
                if name in {"nearby", "sp500"}:
                    label.configure(
                        style={"good": "CardGood.TLabel", "bad": "CardBad.TLabel"}.get(
                            tone, "CardNote.TLabel"
                        )
                    )
