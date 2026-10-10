from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from ui_theme import (
    DEFAULT_THEME,
    UI_FONT_CANDIDATES,
    load_theme,
    save_theme,
    theme_palette,
)


def test_theme_preference_round_trip_and_invalid_fallback() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "ui_settings.json"

        assert load_theme(path) == DEFAULT_THEME
        save_theme(path, "dark")
        assert load_theme(path) == "dark"

        path.write_text('{"theme": "unknown"}', encoding="utf-8")
        assert load_theme(path) == DEFAULT_THEME


def test_dark_palette_has_distinct_chart_and_table_colors() -> None:
    light = theme_palette("light")
    dark = theme_palette("dark")

    assert light["field"] != dark["field"]
    assert light["chart_background"] != dark["chart_background"]
    assert dark["text"] != dark["field"]
    assert dark["chart_text"] != dark["chart_background"]
    assert dark["scroll_thumb"] != dark["field"]
    assert dark["scroll_thumb_active"] != dark["scroll_thumb"]
    assert dark["signal_first_bg"] != dark["field"]
    assert dark["signal_second_bg"] != dark["field"]
    assert dark["signal_third_bg"] != dark["field"]
    assert dark["history_failure_bg"] != dark["history_success_high_bg"]
    assert dark["history_success_low_bg"] != dark["history_success_high_bg"]
    assert len(
        {
            dark["history_loss_low_bg"],
            dark["history_loss_medium_bg"],
            dark["history_loss_high_bg"],
        }
    ) == 3


def test_dark_palette_uses_neutral_codex_style_surfaces() -> None:
    dark = theme_palette("dark")

    assert dark["window"] == "#181818"
    assert dark["field"] == "#151515"
    assert dark["selected"] == "#3a3a3a"

    for key in ("window", "panel", "field", "button", "chart_background", "chart_panel"):
        color = dark[key]
        assert color[1:3] == color[3:5] == color[5:7]


def test_dark_history_low_is_visually_lighter_than_medium() -> None:
    dark = theme_palette("dark")

    def perceived_luminance(color: str) -> float:
        red, green, blue = (
            int(color[index : index + 2], 16) for index in (1, 3, 5)
        )
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    low = perceived_luminance(dark["history_success_low_bg"])
    medium = perceived_luminance(dark["history_success_medium_bg"])
    high = perceived_luminance(dark["history_success_high_bg"])

    assert medium < low < high


def test_dark_palette_uses_soft_text_contrast_and_korean_font_first() -> None:
    dark = theme_palette("dark")

    assert dark["text"] == "#c9c9c9"
    assert dark["muted"] == "#8f8f8f"
    assert dark["selected_text"] != "#ffffff"
    assert UI_FONT_CANDIDATES[0] == "Noto Sans KR"
