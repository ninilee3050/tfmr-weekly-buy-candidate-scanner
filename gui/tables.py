"""Table widgets, column sizing, the chart-strength tooltip and window sizing."""

from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

import pandas as pd

from gui.config import MIN_WINDOW_SIZE, TABLE_FLEX_WEIGHTS
from gui.formatting import _format_value


def populate_table(
    tree: ttk.Treeview,
    data: pd.DataFrame,
    column_bounds: dict[str, tuple[int, int]] | None = None,
    sortable: bool = True,
) -> None:
    """Fill a table; clicking a heading sorts by that column unless disabled."""
    tree.delete(*tree.get_children())
    columns = list(data.columns)
    tree["columns"] = columns

    formatted_rows = [
        [_format_value(row[column], column) for column in columns]
        for _, row in data.iterrows()
    ]
    default_font = tkfont.nametofont("TkDefaultFont", root=tree)

    for column_index, column in enumerate(columns):
        measured_width = default_font.measure(str(column)) + 28
        for values in formatted_rows:
            measured_width = max(
                measured_width,
                default_font.measure(values[column_index]) + 24,
            )
        maximum_width = 700 if column == "오류" else 360
        if column_bounds and column in column_bounds:
            minimum_width, maximum_width = column_bounds[column]
            display_width = min(
                max(minimum_width, measured_width),
                maximum_width,
            )
        else:
            display_width = min(
                max(_column_width(column), measured_width),
                maximum_width,
            )
        tree.heading(
            column,
            text=column,
            command=(
                (lambda name=column: sort_table_by_column(tree, name))
                if sortable
                else ""
            ),
        )
        tree.column(column, width=display_width, minwidth=60, stretch=False)
    tree._sort_state = None

    for values in formatted_rows:
        tree.insert("", "end", values=values)

    tree._preferred_widths = {
        column: int(tree.column(column, "width"))
        for column in columns
    }
    tree.after_idle(lambda source=tree: _fit_table_columns_to_viewport(source))


WINDOW_GEOMETRY_PATTERN = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")
RANK_COLUMNS = {"순위", "현재 시총순위"}
SORT_BLANK_TEXTS = {"", "-", "해당 없음", "진행 중", "산정 대기", "미산출", "데이터 없음"}
SORT_UNIT_MULTIPLIERS = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_SORT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}")
# A number, an optional unit, and optionally a "(3/4)" style detail; nothing else.
_SORT_NUMBER_PATTERN = re.compile(
    r"^([+-]?[\d,]*\.?\d+)\s*([KMBT])?(?:%p|%|점|건|개월|개|위|회차|차|주)?(?:\s*\(.*\))?$"
)


def table_sort_key(text: object) -> tuple[int, float | str] | None:
    """Sort key for one displayed cell; ``None`` for cells that sort last.

    Numbers sort by value ("61.0% (3/4)" -> 61.0, "5.59T" -> 5.59e12) and come
    before plain text; dates sort as text, which works for YYYY-MM-DD.
    """
    value = str(text).strip()
    if value in SORT_BLANK_TEXTS or value.startswith("미산출"):
        return None
    if not _SORT_DATE_PATTERN.match(value):
        match = _SORT_NUMBER_PATTERN.match(value)
        if match:
            number = float(match.group(1).replace(",", ""))
            return 0, number * SORT_UNIT_MULTIPLIERS.get(match.group(2) or "", 1.0)
    return 1, value.casefold()


def sorted_row_order(texts: list[object], descending: bool) -> list[int]:
    """Row positions sorted by their cell text; blank cells always go last."""
    keyed = [(table_sort_key(text), index) for index, text in enumerate(texts)]
    filled = sorted(
        (item for item in keyed if item[0] is not None),
        key=lambda item: item[0],
        reverse=descending,
    )
    blank = [item for item in keyed if item[0] is None]
    return [index for _key, index in filled + blank]


def sort_table_by_column(tree: ttk.Treeview, column: str) -> None:
    """Sort rows by a column; a second click on the same heading reverses it."""
    items = list(tree.get_children())
    texts = [tree.set(item, column) for item in items]
    keys = [key for key in map(table_sort_key, texts) if key is not None]
    numeric = bool(keys) and sum(kind == 0 for kind, _value in keys) * 2 >= len(keys)
    previous = getattr(tree, "_sort_state", None)
    if previous is not None and previous[0] == column:
        descending = not previous[1]
    else:
        # Largest first is the useful default for rates, returns and scores;
        # ranks read naturally from 1 upward.
        descending = numeric and column not in RANK_COLUMNS
    for position, index in enumerate(sorted_row_order(texts, descending)):
        tree.move(items[index], "", position)
    tree._sort_state = (column, descending)
    for name in tree["columns"]:
        marker = (" ▼" if descending else " ▲") if name == column else ""
        tree.heading(name, text=f"{name}{marker}")


def _fit_table_columns_to_viewport(tree: ttk.Treeview) -> None:
    """Fill spare table width without compressing readable content widths."""
    preferred = getattr(tree, "_preferred_widths", None)
    if not preferred:
        return
    try:
        available = max(0, int(tree.winfo_width()) - 4)
    except tk.TclError:
        return
    preferred_total = sum(preferred.values())
    if available <= 1 or preferred_total <= 0:
        return

    widths = _distributed_column_widths(preferred, available)

    for column, width in widths.items():
        try:
            tree.column(column, width=max(60, int(width)), stretch=False)
        except tk.TclError:
            return


def _distributed_column_widths(
    preferred: dict[str, int],
    available: int,
) -> dict[str, int]:
    """Distribute only spare pixels; never squeeze preferred readable widths."""
    widths = dict(preferred)
    extra = int(available) - sum(widths.values())
    if extra <= 0 or not widths:
        return widths

    weights = {
        column: TABLE_FLEX_WEIGHTS.get(
            column,
            1.0 if column.endswith(("수익률", "손익률")) else 0.0,
        )
        for column in widths
    }
    if not any(weights.values()):
        weights = {column: 1.0 for column in widths}
    flexible = [column for column, weight in weights.items() if weight > 0]
    total_weight = sum(weights[column] for column in flexible)
    assigned = 0
    for column in flexible[:-1]:
        addition = int(extra * weights[column] / total_weight)
        widths[column] += addition
        assigned += addition
    if flexible:
        widths[flexible[-1]] += extra - assigned
    return widths


def _table_required_width(
    columns: list[str],
    column_bounds: dict[str, tuple[int, int]] | None = None,
) -> int:
    """Return the panel width needed to show every configured column at once."""
    bounds = column_bounds or {}
    return sum(
        bounds.get(column, (_column_width(column), _column_width(column)))[1]
        for column in columns
    ) + 42


def _column_width(column: str) -> int:
    if column in {
        "Date",
        "1차매수일",
        "최근매수일",
        "매도일",
        "신호일",
        "마지막확인일",
        "데이터기준일",
    }:
        return 110
    if column == "회사명":
        return 220
    if column == "오류":
        return 420
    if column in {"순위", "티커"}:
        return 70
    if column in {"현재 시총순위", "시가총액"}:
        return 95
    if column == "결과":
        return 110
    if column in {"매수차수", "보유주수", "눌림회차"}:
        return 80
    if column in {"가격", "평단가", "매도가", "현재가", "최근매수가"}:
        return 90
    if column == "다음추가매수가":
        return 115
    if column in {"단계", "신호구분"}:
        return 95
    if column in {"현재상태", "데이터상태"}:
        return 125
    if column.endswith("수익률") or column.endswith("손익률"):
        return 100
    return 110


def fit_window_to_screen(
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int]:
    """Shrink the preferred window size so it fits on the screen."""
    min_width, min_height = MIN_WINDOW_SIZE
    fitted_width = max(min_width, min(width, screen_width - 40))
    fitted_height = max(min_height, min(height, screen_height - 80))
    return fitted_width, fitted_height


def restored_window_placement(
    saved: object,
    default_width: int,
    default_height: int,
    screen_width: int,
    screen_height: int,
    virtual_bounds: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Return (width, height, x, y) from saved window state, kept on screen.

    Without usable saved state the default size is centered as on first start.
    The size is limited to the primary screen; the position is kept inside
    ``virtual_bounds`` (left, top, right, bottom of all monitors together) so
    a window left on a second monitor reopens there.
    """
    width, height, x, y = default_width, default_height, None, None
    if isinstance(saved, dict):
        try:
            width, height = int(saved["width"]), int(saved["height"])
            x, y = int(saved["x"]), int(saved["y"])
        except (KeyError, TypeError, ValueError):
            width, height, x, y = default_width, default_height, None, None
    width, height = fit_window_to_screen(width, height, screen_width, screen_height)
    if x is None or y is None:
        return (
            width,
            height,
            max(0, (screen_width - width) // 2),
            max(0, (screen_height - height) // 3),
        )
    left, top, right, bottom = virtual_bounds or (0, 0, screen_width, screen_height)
    x = min(max(left, x), max(left, right - width))
    y = min(max(top, y), max(top, bottom - height))
    return width, height, x, y


def scaled_sash_positions(
    saved_positions: object,
    saved_total: object,
    total_width: int,
    expected_count: int,
) -> list[int] | None:
    """Saved divider positions rescaled to the current width, if still usable."""
    if not isinstance(saved_positions, list) or len(saved_positions) != expected_count:
        return None
    try:
        positions = [int(position) for position in saved_positions]
        scale = total_width / int(saved_total)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    scaled = [int(position * scale) for position in positions]
    if scaled != sorted(scaled) or not all(0 < p < total_width for p in scaled):
        return None
    return scaled


def card_grid_columns(width: int, count: int, min_card_width: int) -> int:
    """All cards in one row when they fit, otherwise two per row."""
    if count <= 2 or width >= count * min_card_width:
        return count
    return 2


def default_sash_positions(
    total_width: int,
    show_top100: bool,
    top100_width: int,
    history_width: int,
    scanner_width: int,
) -> list[int]:
    """Divider positions: Top 100 at its width (at most ~22%), rest by content."""
    left = min(top100_width, max(280, int(total_width * 0.22))) if show_top100 else 0
    remaining = max(0, total_width - left)
    center = int(remaining * history_width / max(1, history_width + scanner_width))
    return [left, left + center] if show_top100 else [center]
