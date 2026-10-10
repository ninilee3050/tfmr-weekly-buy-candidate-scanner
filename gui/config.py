"""Paths, table columns and layout constants shared by the GUI."""

from __future__ import annotations

from pathlib import Path

from market_context import SP500_STATUS_COLUMN


OUTPUT_DIR = Path("outputs")
DOWNLOADS_DIR = Path.home() / "Downloads"
UI_SETTINGS_PATH = OUTPUT_DIR / "ui_settings.json"
CLOSED_SCENARIO_PATH = OUTPUT_DIR / "mmrm_closed_scenarios.csv"
LAST_SCAN_INFO_PATH = OUTPUT_DIR / "mmrm_last_scan.json"
LAST_SCAN_TABLE_PATHS = {
    "events": OUTPUT_DIR / "mmrm_last_scan_events.csv",
    "closed_results": OUTPUT_DIR / "mmrm_last_scan_closed.csv",
    "failures": OUTPUT_DIR / "mmrm_last_scan_failures.csv",
}
SIGNAL_HISTORY_DISPLAY_COLUMNS = [
    "1차신호일",
    "2차신호일",
    "3차판정일",
    "결과",
    "차트 강도",
    "검토등급",
    SP500_STATUS_COLUMN,
    "3개월후 수익률",
    "6개월후 수익률",
    "9개월후 수익률",
    "12개월후 수익률",
]
SCAN_FAILURE_COLUMNS = ["순위", "티커", "회사명", "시가총액", "오류"]
MARKET_CAP_RANK_COLUMN = "현재 시총순위"
SCAN_EVENT_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "섹터",
    "단계",
    "신호일",
    "차트 강도",
    "검토등급",
    SP500_STATUS_COLUMN,
    "종목 3개월 승률",
    "섹터 3개월 승률",
    "결과",
    "신호구분",
    "데이터기준일",
]
ACTIVE_SCENARIO_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "섹터",
    "현재상태",
    "1차신호일",
    "2차신호일",
    "차트 강도",
    "검토등급",
    SP500_STATUS_COLUMN,
    "종목 3개월 승률",
    "섹터 3개월 승률",
    "데이터기준일",
    "데이터상태",
]
CLOSED_RESULT_DISPLAY_COLUMNS = [
    MARKET_CAP_RANK_COLUMN,
    "티커",
    "회사명",
    "섹터",
    "결과",
    "1차신호일",
    "2차신호일",
    "3차판정일",
    "차트 강도",
    "검토등급",
    SP500_STATUS_COLUMN,
    "종료일",
]
CLOSED_SCENARIO_DISPLAY_COLUMNS = [
    "현재 시총순위",
    "티커",
    "회사명",
    "섹터",
    "1차신호일",
    "2차신호일",
    "3차판정일",
    "결과",
    "차트 강도",
    "검토등급",
    SP500_STATUS_COLUMN,
    "3개월후 수익률",
    "6개월후 수익률",
    "9개월후 수익률",
    "12개월후 수익률",
]
CLOSED_SCENARIO_COLUMN_BOUNDS = {
    "현재 시총순위": (76, 86),
    "티커": (60, 72),
    "회사명": (150, 205),
    "섹터": (95, 130),
    "1차신호일": (90, 100),
    "2차신호일": (90, 100),
    "3차판정일": (90, 100),
    "결과": (125, 155),
    "차트 강도": (76, 90),
    "검토등급": (76, 95),
    SP500_STATUS_COLUMN: (90, 108),
    "3개월후 수익률": (100, 110),
    "6개월후 수익률": (100, 110),
    "9개월후 수익률": (100, 110),
    "12개월후 수익률": (105, 115),
}
SIGNAL_HISTORY_COLUMN_BOUNDS = {
    "1차신호일": (90, 100),
    "2차신호일": (90, 100),
    "3차판정일": (90, 100),
    "결과": (120, 155),
    "차트 강도": (76, 90),
    "검토등급": (76, 95),
    SP500_STATUS_COLUMN: (90, 108),
    "3개월후 수익률": (100, 110),
    "6개월후 수익률": (100, 110),
    "9개월후 수익률": (100, 110),
    "12개월후 수익률": (105, 115),
}
TABLE_FLEX_WEIGHTS = {
    "회사명": 4.0,
    "오류": 5.0,
    "ConditionSummary": 5.0,
    "섹터": 2.0,
    "산업": 2.0,
    "분야": 2.0,
    "결과": 2.5,
    "현재상태": 2.0,
    "데이터상태": 2.0,
    "검토등급": 1.0,
    "차트 강도": 1.0,
    SP500_STATUS_COLUMN: 1.2,
}
RETURN_DISPLAY_COLUMNS = SIGNAL_HISTORY_DISPLAY_COLUMNS[-4:]
FIELD_DISPLAY_COLUMNS = [
    "분야",
    "종목 수",
    "종료 사이클",
    "매수 건수",
    "매수 도달률",
    "분석 표본",
    "승률",
    "평소 매수 승률",
    "평소 매수 대비 초과",
    "S&P 이긴 비율",
    "S&P 대비 초과",
    "평균 손익률",
    "중앙값",
]
RANKING_DISPLAY_COLUMNS = [
    "순위",
    "티커",
    "회사명",
    "매수 건수",
    "승률",
    "평균 손익률",
    "중앙값",
    "최고",
    "최저",
    "평소 매수 대비 초과",
    "S&P 대비 초과",
    "매수 도달률",
    "종합점수",
]
HISTORY_LEGEND = (
    ("SuccessHigh", "매수 성공 · 수익", "history_success_high_bg"),
    ("LossHigh", "매수 성공 · 손실", "history_loss_high_bg"),
    ("Failure", "3차 실패", "history_failure_bg"),
    ("Discard", "2차 폐기", "history_discard_bg"),
)
HISTORY_LEGEND_COLORS = {key: color_key for key, _label, color_key in HISTORY_LEGEND}
HORIZON_CARD_MONTHS = (3, 6, 9, 12)
TOP100_PANEL_WIDTH = 490
MIN_WINDOW_SIZE = (960, 600)
SCAN_DOWNLOAD_WORKERS = 8
# Scanner notebook tab positions used by the dashboard cards.
SCAN_EVENTS_TAB = 0
ACTIVE_SCENARIOS_TAB = 1
SIGNAL_VALIDATION_DISPLAY_COLUMNS = [
    "분석 기간",
    "구분",
    "분석 표본",
    "승률",
    "평소 매수 승률",
    "평소 매수 대비 초과",
    "S&P 이긴 비율",
    "S&P 대비 초과",
    "평균 손익률",
    "중앙값",
]
