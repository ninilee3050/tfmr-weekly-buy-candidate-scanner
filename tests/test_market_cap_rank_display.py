from __future__ import annotations

import pandas as pd

from gui.config import (
    ACTIVE_SCENARIO_DISPLAY_COLUMNS,
    CLOSED_RESULT_DISPLAY_COLUMNS,
    MARKET_CAP_RANK_COLUMN,
    SCAN_EVENT_DISPLAY_COLUMNS,
)
from gui.formatting import _format_value, scanner_table_for_display
from gui.tables import RANK_COLUMNS, sorted_row_order, table_sort_key
from watchlist import market_cap_rank_text


def test_rank_text_distinguishes_ranked_watchlist_and_dropped_tickers() -> None:
    assert market_cap_rank_text(8) == "8위"
    assert market_cap_rank_text(100.0) == "100위"
    assert market_cap_rank_text(9000) == "관심"
    assert market_cap_rank_text(9003) == "관심"
    assert market_cap_rank_text(9999) == "순위 밖"
    assert market_cap_rank_text(float("nan")) == ""
    assert market_cap_rank_text(None) == ""


def test_scanner_tables_start_with_the_market_cap_rank() -> None:
    for columns in (
        SCAN_EVENT_DISPLAY_COLUMNS,
        ACTIVE_SCENARIO_DISPLAY_COLUMNS,
        CLOSED_RESULT_DISPLAY_COLUMNS,
    ):
        assert columns[0] == MARKET_CAP_RANK_COLUMN

    active = pd.DataFrame(
        {
            "순위": [8, 9000, 9999],
            "티커": ["META", "BTC-USD", "OLD"],
            "현재상태": ["2차 신호 대기"] * 3,
        }
    )

    display = scanner_table_for_display(active, ACTIVE_SCENARIO_DISPLAY_COLUMNS)

    assert MARKET_CAP_RANK_COLUMN == "현재 시총순위"
    shown = [_format_value(value, MARKET_CAP_RANK_COLUMN) for value in display[MARKET_CAP_RANK_COLUMN]]
    assert shown == ["8위", "관심", "순위 밖"]
    assert "순위" not in display.columns
    assert MARKET_CAP_RANK_COLUMN not in active.columns  # source is left unchanged


def test_ranks_sort_numerically_with_text_labels_after_them() -> None:
    texts = ["63위", "관심", "8위", "순위 밖", "100위"]

    assert table_sort_key("8위") == (0, 8.0)
    assert sorted_row_order(texts, descending=False) == [2, 0, 4, 1, 3]
    assert MARKET_CAP_RANK_COLUMN in RANK_COLUMNS


def test_saved_ranking_is_available_before_the_top100_is_loaded(tmp_path) -> None:
    import json

    from market_cap_provider import load_saved_ranking

    cache = tmp_path / "top100_cache.json"
    assert load_saved_ranking(cache) == []
    cache.write_text(
        json.dumps(
            {
                "saved_at": "2026-10-10 09:00",
                "companies": [
                    {"rank": 1, "ticker": "NVDA", "company": "NVIDIA Corporation", "market_cap": "5.7T"}
                ],
            }
        ),
        encoding="utf-8",
    )

    saved = load_saved_ranking(cache)

    assert [(c.rank, c.ticker, c.company) for c in saved] == [(1, "NVDA", "NVIDIA Corporation")]
