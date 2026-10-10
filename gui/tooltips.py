"""Plain-language explanations shown when the pointer rests on a term."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui_theme import theme_palette

# The pointer must rest this long, so just moving across the screen shows nothing.
HOVER_DELAY_MS = 600
TOOLTIP_WRAP_WIDTH = 380
SORT_MARKERS = (" ▲", " ▼")

TERM_DESCRIPTIONS = {
    "티커": "종목 기호입니다. 행을 누르면 그 종목을 검색합니다.",
    "회사명": "회사 이름입니다. 앞에 [관심]이 붙으면 Top 100이 아니라 관심종목입니다.",
    "섹터": "야후 파이낸스 기준 업종 대분류입니다.",
    "분야": "선택한 구분(섹터 또는 산업)의 이름입니다.",
    "종목 수": "이 분야에 속한 Top 100 종목 수입니다.",
    "순위": "선택한 정렬 기준에 따른 분야 안 순위입니다.",
    "시가총액": "순위 사이트 기준 시가총액입니다.",
    "현재 시총순위": (
        "가장 최근 통합 스캔 시점의 미국 상장 종목 시가총액 순위입니다. 신호가 났던 당시의 "
        "순위가 아닙니다. '관심'은 관심종목, '순위 밖'은 추적 중에 Top 100에서 빠진 종목입니다."
    ),
    "단계": (
        "1차 신호는 관심 편입, 2차 신호는 눌림 확인, 3차 신호는 매수 판정입니다. "
        "2차 폐기는 2차 시점에 조건이 맞지 않아 시나리오를 버린 경우입니다."
    ),
    "현재상태": (
        "'2차 신호 대기'는 1차 신호 뒤 눌림을 기다리는 중이고, "
        "'3차 신호 대기'는 2차 신호 뒤 반등 양봉을 기다리는 중입니다."
    ),
    "결과": (
        "매수 성공은 3차에서 종가가 20주선 위로 마감한 경우, 실패는 20주선을 넘지 못한 경우입니다. "
        "2차 폐기는 20주선이 50주선보다 너무 높거나 중기 구조가 맞지 않아 버린 경우입니다."
    ),
    "신호일": "신호가 나온 주입니다. 주봉이라 그 주의 월요일 날짜로 표시합니다.",
    "1차신호일": (
        "기존 MMRM 조건(MACD 상승 전환, Momentum·RSI·MFI 양호, 150주선이 200주선 위, "
        "50주선이 20주선 위)을 충족해 시나리오가 시작된 주입니다."
    ),
    "2차신호일": "1차 신호 뒤 종가가 5주선 아래에서 음봉으로 마감한 주입니다. 눌림을 확인한 시점입니다.",
    "3차판정일": (
        "2차 신호 뒤 종가가 5주선 위에서 양봉으로 마감한 주입니다. "
        "이때 종가가 20주선 위면 매수 성공, 아니면 실패로 판정합니다."
    ),
    "종료일": "시나리오가 2차 폐기, 매수 성공 또는 실패로 끝난 주입니다.",
    "신호구분": (
        "'이번 주'는 이번 주 주봉에서 나온 신호, '미확인 기간'은 지난 스캔 이후 놓쳤던 주의 신호, "
        "'규칙 재평가'는 이전에 통과했던 2차 신호가 다시 계산해 폐기된 경우입니다."
    ),
    "데이터기준일": "스캔에 쓴 가장 최근 주봉의 월요일 날짜입니다.",
    "데이터상태": (
        "'현재 주봉 포함'은 아직 끝나지 않은 이번 주 가격이 들어간 잠정 상태입니다. "
        "'확정 주봉'은 끝난 주까지만 반영한 것이고, '갱신 실패'는 데이터를 받지 못해 이전 상태를 유지한 것입니다."
    ),
    "차트 강도": (
        "3차 신호 주의 차트 상태를 과거 매수 성공 사례와 비교한 상대 점수(0~100)입니다. "
        "수익 확률이 아니라 과거 분포에서의 위치입니다. 점수 칸에 마우스를 올리면 세부 항목이 나옵니다."
    ),
    "검토등급": "차트 강도가 70점 이상이면 우선검토, 그보다 낮으면 일반검토입니다.",
    "S&P500 상태": "신호 시점에 S&P 500 종가가 50주 이동평균선 위였는지 아래였는지입니다.",
    "3개월후 수익률": "3차 매수 주의 종가 대비 13주 뒤 종가의 변화율입니다. '진행 중'은 아직 기간이 지나지 않은 것입니다.",
    "6개월후 수익률": "3차 매수 주의 종가 대비 26주 뒤 종가의 변화율입니다. '진행 중'은 아직 기간이 지나지 않은 것입니다.",
    "9개월후 수익률": "3차 매수 주의 종가 대비 39주 뒤 종가의 변화율입니다. '진행 중'은 아직 기간이 지나지 않은 것입니다.",
    "12개월후 수익률": "3차 매수 주의 종가 대비 52주 뒤 종가의 변화율입니다. '진행 중'은 아직 기간이 지나지 않은 것입니다.",
    "종목 3개월 승률": "이 종목의 과거 3차 매수 뒤 3개월 승률입니다. 괄호 안은 (수익 건수/확정 건수)입니다.",
    "섹터 3개월 승률": "이 종목이 속한 섹터 전체의 과거 3차 매수 뒤 3개월 승률입니다.",
    "종료 사이클": "매수 성공, 실패, 2차 폐기로 끝난 시나리오 수입니다.",
    "매수 건수": "3차 매수 성공으로 끝난 시나리오 수입니다.",
    "매수 도달률": "끝난 시나리오 중 3차 매수 성공까지 간 비율입니다. 괄호 안은 (매수 건수/종료 사이클)입니다.",
    "분석 표본": "선택한 기간이 지나 수익률이 확정되어 통계에 들어간 매수 건수입니다.",
    "승률": (
        "3차 매수 뒤 선택한 기간이 지났을 때 수익률이 플러스였던 비율입니다. "
        "결과가 확정된 사례만 계산하며, 괄호 안은 (수익 건수/확정 건수)입니다."
    ),
    "평소 매수 승률": (
        "같은 종목을 신호 앞뒤 1년 안의 아무 주에나 샀을 때의 승률입니다. "
        "신호 승률이 이보다 높아야 신호를 기다린 보람이 있습니다."
    ),
    "평소 매수 대비 초과": (
        "신호대로 샀을 때의 수익률에서, 같은 종목을 앞뒤 1년 안의 아무 주에나 샀을 때의 평균 수익률을 뺀 값입니다. "
        "플러스면 매수 타이밍 효과가 있었다는 뜻입니다."
    ),
    "S&P 이긴 비율": "같은 주에 S&P 500을 사서 같은 기간 들고 있었을 때보다 수익률이 높았던 비율입니다.",
    "S&P 대비 초과": (
        "신호대로 샀을 때의 수익률에서 같은 기간 S&P 500 수익률을 뺀 평균입니다. "
        "변동성이 큰 종목은 상승장에서 이 값이 크게 나오므로, 타이밍 효과는 '평소 매수 대비'로 보는 편이 정확합니다."
    ),
    "평균 손익률": "확정된 매수 사례의 선택한 기간 수익률 평균입니다.",
    "중앙값": "수익률을 크기순으로 세웠을 때 가운데 값입니다. 몇 건의 큰 수익이나 손실에 덜 흔들립니다.",
    "최고": "확정된 매수 사례 중 가장 높았던 수익률입니다.",
    "최저": "확정된 매수 사례 중 가장 낮았던 수익률입니다.",
    "종합점수": "분야 안에서 승률 순위와 평균 손익률 순위를 평균한 점수(0~100)입니다.",
    "분석 기간": "3차 매수 뒤 얼마 지난 시점의 결과인지입니다.",
    "구분": (
        "'전체 매수 성공'은 모든 3차 매수, '차트 강도 산정분'은 점수가 계산된 사례, "
        "'우선검토'와 '일반검토'는 그중 등급별 사례입니다."
    ),
    "오류": "데이터를 받지 못한 이유입니다. 다음 스캔에서 다시 시도합니다.",
    "이름": "관심종목에 붙인 이름입니다.",
}

DASHBOARD_CARD_DESCRIPTIONS = {
    "buy": (
        "가장 최근 통합 스캔에서 새로 확인된 3차 매수 성공 건수입니다. "
        "금요일 장 마감 전의 스캔이면 잠정 결과입니다. 누르면 신호 목록으로 이동합니다."
    ),
    "wait3": "2차 신호까지 나와 반등 양봉(3차 판정)을 기다리는 종목 수입니다. 누르면 활성 시나리오로 이동합니다.",
    "wait2": "1차 신호가 나와 눌림(2차 신호)을 기다리는 종목 수입니다. 누르면 활성 시나리오로 이동합니다.",
    "last": "이 PC에서 마지막으로 통합 스캔을 한 시각입니다. 7일 넘게 지나면 스캔이 필요하다고 표시합니다.",
}

HORIZON_CARD_TERMS = {
    "win": "승률",
    "sample": "분석 표본",
    "nearby": "평소 매수 대비 초과",
    "sp500": "S&P 대비 초과",
}


def term_description(heading_text: object) -> str:
    """Explanation for a column heading, ignoring a sort marker; "" if none."""
    name = str(heading_text)
    for marker in SORT_MARKERS:
        if name.endswith(marker):
            name = name[: -len(marker)]
    return TERM_DESCRIPTIONS.get(name.strip(), "")


class HoverTooltip:
    """One shared popup that appears after the pointer rests on a term."""

    def __init__(self, owner: tk.Misc, font_family: str) -> None:
        self.owner = owner
        self.font_family = font_family
        self.window: tk.Toplevel | None = None
        self._job: str | None = None
        self._key: object = None

    def schedule(self, key: object, text: str, x: int, y: int) -> None:
        """Show ``text`` near (x, y) after the delay unless the pointer leaves."""
        if key == self._key:
            return
        self.cancel()
        if not text:
            return
        self._key = key
        self._job = self.owner.after(HOVER_DELAY_MS, self._show, text, x, y)

    def cancel(self, _event=None) -> None:
        if self._job is not None:
            self.owner.after_cancel(self._job)
            self._job = None
        self._key = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None

    def _show(self, text: str, x: int, y: int) -> None:
        self._job = None
        palette = theme_palette(getattr(self.owner, "theme_mode", "light"))
        window = tk.Toplevel(self.owner)
        window.wm_overrideredirect(True)
        # Stay above the main window even when that window is kept on top.
        window.attributes("-topmost", True)
        window.configure(background=palette["border"])
        tk.Label(
            window,
            text=text,
            background=palette["field"],
            foreground=palette["text"],
            font=(self.font_family, 9),
            justify="left",
            wraplength=TOOLTIP_WRAP_WIDTH,
            padx=10,
            pady=8,
        ).pack(padx=1, pady=1)
        window.update_idletasks()
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        x = max(4, min(x + 14, window.winfo_screenwidth() - width - 8))
        y = max(4, min(y + 18, window.winfo_screenheight() - height - 8))
        window.wm_geometry(f"+{x}+{y}")
        self.window = window


def attach_widget_tooltip(tooltip: HoverTooltip, widget: tk.Misc, text: str) -> None:
    """Explain a label or card when the pointer rests on it."""
    widget.bind(
        "<Enter>",
        lambda event: tooltip.schedule(widget, text, event.x_root, event.y_root),
        add="+",
    )
    for sequence in ("<Leave>", "<ButtonPress>"):
        widget.bind(sequence, tooltip.cancel, add="+")


def attach_heading_tooltips(tooltip: HoverTooltip, tree: ttk.Treeview) -> None:
    """Explain a table's column headings; rows never trigger the popup."""

    def on_motion(event) -> None:
        if tree.identify_region(event.x, event.y) != "heading":
            tooltip.cancel()
            return
        column_id = tree.identify_column(event.x)
        try:
            column = tree["columns"][int(column_id.lstrip("#")) - 1]
        except (ValueError, IndexError):
            tooltip.cancel()
            return
        tooltip.schedule(
            (tree, column),
            term_description(column),
            event.x_root,
            event.y_root,
        )

    tree.bind("<Motion>", on_motion, add="+")
    for sequence in ("<Leave>", "<ButtonPress>", "<MouseWheel>"):
        tree.bind(sequence, tooltip.cancel, add="+")
