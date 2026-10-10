"""Paths, table columns and layout constants shared by the GUI."""

from __future__ import annotations

from pathlib import Path

from market_context import SP500_STATUS_COLUMN


OUTPUT_DIR = Path("outputs")
DOWNLOADS_DIR = Path.home() / "Downloads"
UI_SETTINGS_PATH = OUTPUT_DIR / "ui_settings.json"
CLOSED_SCENARIO_PATH = OUTPUT_DIR / "tfmr_closed_scenarios.csv"
LAST_SCAN_INFO_PATH = OUTPUT_DIR / "tfmr_last_scan.json"
LAST_SCAN_TABLE_PATHS = {
    "events": OUTPUT_DIR / "tfmr_last_scan_events.csv",
    "closed_results": OUTPUT_DIR / "tfmr_last_scan_closed.csv",
    "failures": OUTPUT_DIR / "tfmr_last_scan_failures.csv",
}
PULLBACK_NUMBER_COLUMN = "눌림회차"
# Return after trading costs; the plain 수익률 is before them.
NET_RETURN_COLUMN = "실수익률"
TRADE_HISTORY_DISPLAY_COLUMNS = [
    "1차매수일",
    PULLBACK_NUMBER_COLUMN,
    "매수차수",
    "최근매수일",
    "평단가",
    "매도일",
    "매도가",
    "결과",
    "수익률",
    NET_RETURN_COLUMN,
    "보유주수",
    SP500_STATUS_COLUMN,
]
SCAN_FAILURE_COLUMNS = ["순위", "티커", "회사명", "시가총액", "오류"]
MARKET_CAP_RANK_COLUMN = "현재 시총순위"
SCAN_EVENT_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "단계",
    "결과",
    PULLBACK_NUMBER_COLUMN,
    "신호일",
    "가격",
    "평단가",
    "수익률",
    NET_RETURN_COLUMN,
    "보유주수",
    SP500_STATUS_COLUMN,
    "신호구분",
    "데이터기준일",
]
ACTIVE_SCENARIO_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "현재상태",
    "1차매수일",
    PULLBACK_NUMBER_COLUMN,
    "매수차수",
    "평단가",
    "다음추가매수가",
    "현재가",
    "평가손익률",
    "보유주수",
    SP500_STATUS_COLUMN,
    "데이터기준일",
    "데이터상태",
]
CLOSED_RESULT_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "1차매수일",
    PULLBACK_NUMBER_COLUMN,
    "매수차수",
    "매도일",
    "평단가",
    "매도가",
    "수익률",
    NET_RETURN_COLUMN,
    "보유주수",
    SP500_STATUS_COLUMN,
]
CLOSED_SCENARIO_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "1차매수일",
    PULLBACK_NUMBER_COLUMN,
    "매수차수",
    "매도일",
    "평단가",
    "매도가",
    "수익률",
    NET_RETURN_COLUMN,
    "보유주수",
    SP500_STATUS_COLUMN,
]
TRADE_HISTORY_COLUMN_BOUNDS = {
    "1차매수일": (90, 100),
    PULLBACK_NUMBER_COLUMN: (70, 80),
    "매수차수": (70, 80),
    "최근매수일": (90, 100),
    "평단가": (80, 95),
    "매도일": (90, 100),
    "매도가": (80, 95),
    "결과": (80, 95),
    "수익률": (80, 95),
    NET_RETURN_COLUMN: (80, 95),
    "보유주수": (70, 80),
    SP500_STATUS_COLUMN: (90, 108),
}
TABLE_FLEX_WEIGHTS = {
    "회사명": 4.0,
    "오류": 5.0,
    "결과": 1.5,
    "현재상태": 2.0,
    "데이터상태": 2.0,
    SP500_STATUS_COLUMN: 1.2,
}
PRICE_COLUMNS = {"가격", "평단가", "매도가", "현재가", "다음추가매수가", "최근매수가"}
HISTORY_LEGEND = (
    ("SuccessHigh", "수익", "history_success_high_bg"),
    ("LossHigh", "손실", "history_loss_high_bg"),
    ("SuccessPending", "보유 중", "history_success_pending_bg"),
)
HISTORY_LEGEND_COLORS = {key: color_key for key, _label, color_key in HISTORY_LEGEND}
# A sold case this far above or below break-even gets the strong row colour.
STRONG_RETURN_PERCENT = 5.0
TOP100_PANEL_WIDTH = 490
MIN_WINDOW_SIZE = (960, 600)
SCAN_DOWNLOAD_WORKERS = 8
# Scanner notebook tab positions used by the dashboard cards.
SCAN_EVENTS_TAB = 0
ACTIVE_SCENARIOS_TAB = 1
