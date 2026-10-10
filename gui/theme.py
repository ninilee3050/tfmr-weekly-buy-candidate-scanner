"""Light/dark theme styles and row colors."""

from __future__ import annotations

from tkinter import ttk

from ui_theme import save_theme, theme_palette
from gui.config import HISTORY_LEGEND_COLORS, UI_SETTINGS_PATH


class ThemeMixin:
    """Light/dark theme styles and row colors. Mixed into BuyPointApp; relies on its attributes."""

    def _apply_theme(self) -> None:
        palette = theme_palette(self.theme_mode)
        self.configure(background=palette["window"])

        self.style.configure("TFrame", background=palette["window"])
        self.style.configure(
            "TLabel",
            background=palette["window"],
            foreground=palette["text"],
        )
        self.style.configure(
            "ScanStatus.TLabel",
            background=palette["window"],
            foreground=palette["text"],
        )
        self.style.configure(
            "ScanAlert.TLabel",
            background=palette["signal_third_bg"],
            foreground=palette["signal_third_text"],
            font=(self.ui_font_family, 9, "bold"),
            padding=(6, 5),
        )
        self.style.configure(
            "TLabelframe",
            background=palette["window"],
            foreground=palette["text"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        self.style.configure(
            "TLabelframe.Label",
            background=palette["window"],
            foreground=palette["text"],
        )
        self.style.configure(
            "TButton",
            background=palette["button"],
            foreground=palette["text"],
            bordercolor=palette["border"],
            focuscolor=palette["selected"],
            padding=(7, 4),
        )
        self.style.map(
            "TButton",
            background=[
                ("pressed", palette["selected"]),
                ("active", palette["button_active"]),
            ],
            foreground=[("pressed", palette["selected_text"])],
        )
        self.style.configure(
            "TEntry",
            fieldbackground=palette["field"],
            foreground=palette["text"],
            insertcolor=palette["text"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        self.style.map(
            "TEntry",
            fieldbackground=[("invalid", palette["signal_third_bg"])],
            foreground=[("invalid", palette["signal_third_text"])],
            bordercolor=[("invalid", palette["signal_third_text"])],
        )
        self.style.configure(
            "Filter.TCheckbutton",
            background=palette["window"],
            foreground=palette["text"],
            indicatorcolor=palette["field"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            focuscolor=palette["window"],
        )
        self.style.map(
            "Filter.TCheckbutton",
            background=[
                ("pressed", palette["window"]),
                ("active", palette["window"]),
            ],
            foreground=[
                ("pressed", palette["text"]),
                ("active", palette["text"]),
            ],
            indicatorcolor=[
                ("selected", palette["selected"]),
                ("!selected", palette["field"]),
            ],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=palette["field"],
            background=palette["button"],
            foreground=palette["text"],
            arrowcolor=palette["text"],
            bordercolor=palette["border"],
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette["field"])],
            foreground=[("readonly", palette["text"])],
        )
        self.style.configure(
            "Treeview",
            background=palette["field"],
            fieldbackground=palette["field"],
            foreground=palette["text"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )
        self.style.map(
            "Treeview",
            background=[("selected", palette["selected"])],
            foreground=[("selected", palette["selected_text"])],
        )
        self.style.configure(
            "Treeview.Heading",
            background=palette["panel"],
            foreground=palette["text"],
            bordercolor=palette["border"],
            relief="flat",
        )
        self.style.map(
            "Treeview.Heading",
            background=[("active", palette["button_active"])],
        )
        self.style.configure(
            "TNotebook",
            background=palette["window"],
            bordercolor=palette["border"],
        )
        self.style.configure(
            "TNotebook.Tab",
            background=palette["button"],
            foreground=palette["text"],
            padding=(9, 4),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[
                ("selected", palette["field"]),
                ("active", palette["button_active"]),
            ],
        )
        for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            self.style.configure(
                scrollbar_style,
                background=palette["scroll_thumb"],
                troughcolor=palette["field"],
                bordercolor=palette["field"],
                lightcolor=palette["scroll_thumb"],
                darkcolor=palette["scroll_thumb"],
                arrowcolor=palette["scroll_arrow"],
                gripcount=0,
                arrowsize=8,
                borderwidth=0,
                relief="flat",
            )
            self.style.map(
                scrollbar_style,
                background=[
                    ("pressed", palette["scroll_thumb_active"]),
                    ("active", palette["scroll_thumb_active"]),
                ],
                lightcolor=[
                    ("pressed", palette["scroll_thumb_active"]),
                    ("active", palette["scroll_thumb_active"]),
                ],
                darkcolor=[
                    ("pressed", palette["scroll_thumb_active"]),
                    ("active", palette["scroll_thumb_active"]),
                ],
            )

        self._configure_card_styles(palette)
        self.style.configure("TPanedwindow", background=palette["window"])
        self.style.configure(
            "Sash",
            sashthickness=8,
            gripcount=0,
            background=palette["border"],
            bordercolor=palette["window"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
        )

        self.option_add("*TCombobox*Listbox.background", palette["field"])
        self.option_add("*TCombobox*Listbox.foreground", palette["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", palette["selected"])
        self.option_add("*TCombobox*Listbox.selectForeground", palette["selected_text"])

        if hasattr(self, "theme_button"):
            self.theme_button.configure(text=self._theme_button_text())
        tooltip = getattr(self, "chart_strength_tooltip", None)
        if tooltip is not None:
            tooltip.hide()
            self._chart_strength_hover_item = None
        for tree_name in ("scan_tree", "active_tree"):
            tree = getattr(self, tree_name, None)
            if tree is not None:
                self._configure_signal_tree_tags(tree)
        for tree_name in ("buy_tree", "closed_scenario_tree"):
            tree = getattr(self, tree_name, None)
            if tree is not None:
                self._configure_history_tree_tags(tree)
        chart_window = getattr(self, "chart_window", None)
        if chart_window is not None and chart_window.winfo_exists():
            chart_window.set_theme(self.theme_mode)

    def _configure_card_styles(self, palette: dict[str, str]) -> None:
        """Styles for the dashboard cards, horizon cards and history legend."""
        family = self.ui_font_family
        self.style.configure(
            "Card.TFrame",
            background=palette["panel"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            relief="solid",
            borderwidth=1,
        )
        card_labels = {
            "CardTitle.TLabel": (palette["muted"], (family, 9)),
            "CardValue.TLabel": (palette["text"], (family, 17, "bold")),
            "CardAlert.TLabel": (palette["signal_third_text"], (family, 17, "bold")),
            "CardNote.TLabel": (palette["muted"], (family, 9)),
            "CardNoteAlert.TLabel": (palette["signal_third_text"], (family, 9, "bold")),
            "CardGood.TLabel": (palette["signal_first_text"], (family, 9, "bold")),
            "CardBad.TLabel": (palette["signal_third_text"], (family, 9, "bold")),
            "HorizonValue.TLabel": (palette["text"], (family, 13, "bold")),
        }
        for style_name, (foreground, font) in card_labels.items():
            self.style.configure(
                style_name,
                background=palette["panel"],
                foreground=foreground,
                font=font,
            )
        for key, color_key in HISTORY_LEGEND_COLORS.items():
            self.style.configure(
                f"Legend{key}.TLabel",
                background=palette[color_key],
                foreground=palette["text"],
                font=(family, 8),
                padding=(6, 1),
            )
        self.style.configure(
            "LegendNote.TLabel",
            foreground=palette["muted"],
            font=(family, 8),
        )

    def _theme_button_text(self) -> str:
        return "라이트 모드" if self.theme_mode == "dark" else "다크 모드"

    def toggle_theme(self) -> None:
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self._apply_theme()
        save_theme(UI_SETTINGS_PATH, self.theme_mode)

    def _configure_signal_tree_tags(self, tree: ttk.Treeview) -> None:
        palette = theme_palette(self.theme_mode)
        tree.tag_configure(
            "signal_first",
            background=palette["signal_first_bg"],
            foreground=palette["signal_first_text"],
        )
        tree.tag_configure(
            "signal_second",
            background=palette["signal_second_bg"],
            foreground=palette["signal_second_text"],
        )
        tree.tag_configure(
            "signal_third",
            background=palette["signal_third_bg"],
            foreground=palette["signal_third_text"],
            font=(self.ui_font_family, 9, "bold"),
        )

    def _configure_history_tree_tags(self, tree: ttk.Treeview | None = None) -> None:
        tree = tree or self.buy_tree
        palette = theme_palette(self.theme_mode)
        tag_colors = {
            "history_discard": "history_discard_bg",
            "history_failure": "history_failure_bg",
            "history_success_pending": "history_success_pending_bg",
            "history_success_low": "history_success_low_bg",
            "history_success_medium": "history_success_medium_bg",
            "history_success_high": "history_success_high_bg",
            "history_loss_low": "history_loss_low_bg",
            "history_loss_medium": "history_loss_medium_bg",
            "history_loss_high": "history_loss_high_bg",
            "history_flat": "history_flat_bg",
        }
        for tag, color_key in tag_colors.items():
            options: dict[str, object] = {"background": palette[color_key]}
            if tag == "history_success_high":
                options["font"] = (self.ui_font_family, 9, "bold")
            tree.tag_configure(tag, **options)
