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
    "순위": "스캔 시점의 시가총액 순위입니다.",
    "시가총액": "순위 사이트 기준 시가총액입니다.",
    "현재 시총순위": (
        "가장 최근 통합 스캔 시점의 미국 상장 종목 시가총액 순위입니다. 신호가 났던 당시의 "
        "순위가 아닙니다. '관심'은 관심종목, '순위 밖'은 보유 중에 Top 100에서 빠진 종목입니다."
    ),
    "단계": (
        "1차 매수는 새 매수 후보, 추가매수는 보유 중 직전 매수가보다 3% 이상 내린 음봉, "
        "매도는 양봉이면서 종가가 5주선 또는 20주선 위로 마감한 경우입니다."
    ),
    "현재상태": (
        "'보유 중'은 매도 신호를 기다리는 중이고, '매도 신호 · 잠정'은 아직 끝나지 않은 "
        "이번 주 주봉에서 매도 조건이 보인 상태입니다. 금요일 종가에서 확정됩니다."
    ),
    "결과": "'보유 중'은 아직 매도 신호가 없는 케이스, '매도 완료'는 매도 신호로 끝난 케이스입니다.",
    "신호일": "신호가 나온 주입니다. 주봉이라 그 주의 월요일 날짜로 표시합니다.",
    "1차매수일": (
        "20주선이 50주선 위인 상승 사이클에서 종가가 5주선과 20주선 아래로 내려온 첫 음봉 주입니다. "
        "150주선이 200주선 위이고 종가가 200주선 위여야 합니다. 이 주의 종가에 1주를 삽니다."
    ),
    "눌림회차": (
        "20주선이 50주선을 넘은 골든크로스 뒤 몇 번째 눌림에서 1차 매수가 나왔는지입니다. "
        "200주선 조건 때문에 매수하지 않고 지나간 눌림도 셉니다. "
        "종가가 5주선과 20주선 둘 다 위로 회복한 뒤에 나온 눌림부터 다음 회차로 셉니다. "
        "한 케이스 안에서 몇 번 샀는지를 뜻하는 매수차수와는 다른 숫자입니다."
    ),
    "매수차수": (
        "이 케이스에서 지금까지 매수한 횟수입니다. N차 매수 때 N주를 사며 최대 5차까지입니다. "
        "골든크로스 뒤 몇 번째 눌림인지는 눌림회차에 따로 표시합니다."
    ),
    "최근매수일": "가장 마지막으로 매수한 주입니다.",
    "최근매수가": "가장 마지막 매수의 가격(그 주의 종가)입니다. 다음 추가매수의 기준입니다.",
    "보유수량": "지금까지 매수한 주식 수의 합입니다. 5차까지 사면 15주입니다.",
    "가격": "신호가 나온 주의 종가입니다.",
    "평단가": "매수한 주식의 평균 매수 가격입니다. 수수료는 넣지 않았습니다.",
    "다음추가매수가": (
        "직전 매수가보다 3% 낮은 가격입니다. 주봉 종가가 이 가격 이하이고 음봉이면 다음 차수를 매수합니다. "
        "5차까지 매수했으면 비어 있습니다."
    ),
    "현재가": "스캔에 쓴 가장 최근 주봉의 종가입니다.",
    "평가손익률": "현재가가 평단가보다 얼마나 높은지 또는 낮은지입니다.",
    "매도일": "양봉이면서 종가가 5주선 또는 20주선 위로 마감해 전량 매도한 주입니다.",
    "매도가": "매도한 주의 종가입니다.",
    "수익률": "매도가가 평단가보다 얼마나 높은지 또는 낮은지입니다. 보유 중이면 현재가 기준입니다.",
    "보유주수": "1차 매수 주부터 매도 주(보유 중이면 최근 주)까지의 주 수입니다.",
    "신호구분": "'이번 주'는 이번 주 주봉에서 나온 신호, '미확인 기간'은 지난 스캔 이후 놓쳤던 주의 신호입니다.",
    "데이터기준일": "스캔에 쓴 가장 최근 주봉의 월요일 날짜입니다.",
    "데이터상태": (
        "'현재 주봉 포함'은 아직 끝나지 않은 이번 주 가격이 들어간 잠정 상태입니다. "
        "'확정 주봉'은 끝난 주까지만 반영한 것이고, '갱신 실패'는 데이터를 받지 못해 이전 상태를 유지한 것입니다."
    ),
    "S&P500 상태": "신호 시점에 S&P 500 종가가 50주 이동평균선 위였는지 아래였는지입니다.",
    "오류": "데이터를 받지 못한 이유입니다. 다음 스캔에서 다시 시도합니다.",
    "이름": "관심종목에 붙인 이름입니다.",
}

DASHBOARD_CARD_DESCRIPTIONS = {
    "first": (
        "가장 최근 통합 스캔에서 새로 확인된 1차 매수 후보 건수입니다. "
        "금요일 장 마감 전의 스캔이면 잠정 결과입니다. 누르면 신호 목록으로 이동합니다."
    ),
    "add": "가장 최근 통합 스캔에서 새로 확인된 추가매수 건수입니다. 누르면 신호 목록으로 이동합니다.",
    "sell": "가장 최근 통합 스캔에서 새로 확인된 매도 신호 건수입니다. 누르면 신호 목록으로 이동합니다.",
    "holding": "1차 매수 뒤 아직 매도 신호가 나오지 않은 종목 수입니다. 누르면 보유 중 목록으로 이동합니다.",
}

SUMMARY_CARD_DESCRIPTIONS = {
    "closed": "이 종목에서 1차 매수부터 매도까지 끝난 케이스 수입니다.",
    "win": "매도가 끝난 케이스 중 수익률이 플러스였던 비율입니다.",
    "average": "매도가 끝난 케이스의 수익률 평균입니다. 수수료와 세금은 넣지 않았습니다.",
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
