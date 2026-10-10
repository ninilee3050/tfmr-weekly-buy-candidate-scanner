"""Telegram notification for the headless weekly scan.

The bot token and chat id come from the TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID environment variables (GitHub Actions secrets).  Without
them the scan runs as before and nothing is sent.
"""

from __future__ import annotations

import http.client
import json
import os
from html import escape
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pandas as pd

from scenario_tracker import ADD_BUY_STAGE, FIRST_BUY_STAGE, SELL_STAGE
from watchlist import WATCHLIST_LABEL, is_weekend_traded, market_cap_rank_text


TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
MAX_LISTED_TICKERS = 15
ITEM_MARKER = "▸"
MAX_COMPANY_NAME_LENGTH = 16
COMPANY_SUFFIXES = (
    " & Co.",
    " Group",
    " Incorporated",
    " Corporation",
    " Company",
    " Limited",
    " Holdings",
    " Holding",
    " Inc.",
    " Inc",
    " Corp.",
    " Corp",
    " Co.",
    " Ltd.",
    " Ltd",
    " plc",
    " N.V.",
    " S.A.",
)
WEEKDAY_NAMES = "월화수목금토일"
# (heading, 단계 of the scan event), most urgent first.
SIGNAL_SECTIONS = (
    ("🔴 매도 신호", SELL_STAGE),
    ("🟠 추가매수", ADD_BUY_STAGE),
    ("🟢 신규 1차 매수", FIRST_BUY_STAGE),
)


class NotificationError(RuntimeError):
    """Raised when a Telegram message could not be delivered."""


def build_scan_message(
    events: pd.DataFrame,
    active_scenarios: pd.DataFrame,
    failure_count: int,
    scan_date: pd.Timestamp,
    warnings: list[str] | None = None,
    provisional: bool = False,
    data_basis: str = "",
) -> str:
    """Summarize one scan as a short Telegram message (HTML formatting).

    This week's signals come first, most urgent on top: sells, add-on buys,
    then new first buys.  The cases still held without a signal this week
    follow.

    Each section has a heading followed by one line per stock:
    "▸ <rank> <ticker> (company) — details".  The rank is monospace and the
    ticker bold so rank, ticker, company and details read as separate items,
    and lines stay short enough not to wrap on a phone.

    ``provisional`` marks a scan run before the week's Friday close, whose
    current-week signals can still change; ``data_basis`` then says which
    session the latest prices come from.
    """
    lines = [f"📈 TFMR 주간 스캔 · {_date_label(scan_date)} · {'잠정' if provisional else '확정'}"]
    if provisional:
        lines.append(f"※ {escape(data_basis) if data_basis else '이번 주 장 마감 전'}")

    signalled: set[str] = set()
    sections = []
    for label, stage in SIGNAL_SECTIONS:
        rows = _stage_rows(events, stage)
        if not rows.empty:
            signalled.update(str(ticker) for ticker in rows["티커"])
            sections.append((label, rows.assign(_note=rows.apply(_signal_note, axis=1))))
    if not sections:
        lines += ["", "매수·매도 신호 없음"]
    holding = _holding_rows(active_scenarios, signalled)
    if not holding.empty:
        sections.append(("보유 중", holding))
    for label, rows in sections:
        lines += ["", _heading(label, len(rows)), *_stock_lines(rows)]

    notes = []
    if failure_count:
        notes.append(f"데이터 오류 {failure_count}건")
    if not events.empty and "티커" in events.columns:
        weekend_tickers = sorted(
            {str(ticker) for ticker in events["티커"] if is_weekend_traded(ticker)}
        )
        if weekend_tickers:
            # Crypto keeps trading after the Friday scan, so its week is not over.
            notes.append(f"※ {escape(', '.join(weekend_tickers))}: 주말 거래 반영 전")
    for warning in warnings or []:
        if warning:
            notes.append(f"⚠️ {escape(warning)}")
    if notes:
        lines += ["", *notes]
    return "\n".join(lines)


def build_failure_message(error: object, scan_date: pd.Timestamp) -> str:
    return (
        f"⚠️ TFMR 주간 스캔 실패 · {_date_label(scan_date)}\n\n"
        f"{escape(str(error))}\n\nGitHub Actions 실행 기록을 확인해 주세요."
    )


def notify_from_environment(text: str) -> bool:
    """Send ``text`` when Telegram is configured; return whether it was sent."""
    token = os.environ.get(TELEGRAM_TOKEN_ENV, "").strip()
    chat_id = os.environ.get(TELEGRAM_CHAT_ID_ENV, "").strip()
    if not token or not chat_id:
        return False
    send_telegram_message(text, token, chat_id)
    return True


def send_telegram_message(text: str, token: str, chat_id: str) -> None:
    request = Request(
        TELEGRAM_API_URL.format(token=token),
        # Messages use Telegram's HTML formatting (<b>, <code>).
        data=json.dumps(
            {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # Error text never includes the request URL, because the URL holds the token.
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise NotificationError(
            f"텔레그램 전송 실패: HTTP {exc.code} ({_telegram_error_hint(exc.code)})"
        ) from None
    except (OSError, http.client.HTTPException, ValueError) as exc:
        # URLError, timeouts and dropped connections all land here.
        raise NotificationError(
            f"텔레그램 전송 실패: {type(exc).__name__}"
        ) from None
    if not payload.get("ok"):
        raise NotificationError("텔레그램 전송 실패: 응답이 올바르지 않습니다.")


def _telegram_error_hint(status: int) -> str:
    return {
        400: "채팅 ID가 틀렸거나 봇에게 먼저 말을 걸지 않았습니다",
        401: "봇 토큰이 틀렸습니다",
        403: "봇을 차단했거나 대화를 시작하지 않았습니다",
        404: "봇 토큰이 틀렸습니다",
    }.get(status, "잠시 후 다시 시도해 주세요")


def _stage_rows(events: pd.DataFrame, stage: str) -> pd.DataFrame:
    if events.empty or "단계" not in events.columns:
        return events.iloc[0:0]
    return events[events["단계"] == stage]


def _date_label(date: pd.Timestamp) -> str:
    """"10/16 (금)" for the scan date."""
    date = pd.Timestamp(date)
    return f"{date:%m/%d} ({WEEKDAY_NAMES[date.weekday()]})"


def _heading(label: str, count: int) -> str:
    """Stage heading with the count in bold at the end, where it stands out."""
    return f"{label} <b>{count}건</b>"


def _holding_rows(active_scenarios: pd.DataFrame, signalled: set[str]) -> pd.DataFrame:
    """Held cases without a signal this scan, best market-cap rank first."""
    if active_scenarios.empty or "티커" not in active_scenarios.columns:
        return active_scenarios.iloc[0:0]
    rows = active_scenarios[~active_scenarios["티커"].astype(str).isin(signalled)]
    ranks = (
        pd.to_numeric(rows["순위"], errors="coerce")
        if "순위" in rows.columns
        else pd.Series(float("nan"), index=rows.index)
    )
    notes = rows.apply(
        lambda row: _join_details(
            _rounds_text(row.get("매수차수")), _percent_text(row.get("평가손익률"))
        ),
        axis=1,
    )
    return rows.assign(_note=notes, _rank=ranks).sort_values("_rank", na_position="last")


def _signal_note(row: pd.Series) -> str:
    """What happened: "+2.1% · 5주" for a sell, "2차 · 321.50" for a buy."""
    stage = row.get("단계")
    if stage == SELL_STAGE:
        return _join_details(_percent_text(row.get("수익률")), _weeks_text(row.get("보유주수")))
    if stage == ADD_BUY_STAGE:
        return _join_details(_rounds_text(row.get("매수차수")), _price_text(row.get("가격")))
    return _price_text(row.get("가격"))


def _join_details(*details: str) -> str:
    return " · ".join(detail for detail in details if detail)


def _number(value: object) -> float | None:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(number) else float(number)


def _percent_text(value: object) -> str:
    number = _number(value)
    return "" if number is None else f"{number:+.1f}%"


def _price_text(value: object) -> str:
    number = _number(value)
    return "" if number is None else f"{number:,.2f}"


def _weeks_text(value: object) -> str:
    number = _number(value)
    return "" if number is None else f"{int(number)}주"


def _rounds_text(value: object) -> str:
    number = _number(value)
    return "" if number is None else f"{int(number)}차"


def _stock_lines(rows: pd.DataFrame) -> list[str]:
    lines = [
        f"{ITEM_MARKER} {_stock_line(row)}"
        for _, row in rows.head(MAX_LISTED_TICKERS).iterrows()
    ]
    if len(rows) > MAX_LISTED_TICKERS:
        lines.append(f"{ITEM_MARKER} 외 {len(rows) - MAX_LISTED_TICKERS}건")
    return lines


def _stock_line(row: pd.Series) -> str:
    """"<code>59</code> <b>SAP</b> (SAP SE) — 2차 · 321.50" for one stock."""
    parts = []
    rank = _rank_label(row.get("순위"))
    if rank:
        parts.append(f"<code>{escape(rank)}</code>")
    parts.append(f"<b>{escape(str(row.get('티커', '')))}</b>")
    company = short_company_name(row.get("회사명"))
    if company:
        parts.append(f"({escape(company)})")
    text = " ".join(parts)

    note = row.get("_note")
    if isinstance(note, str) and note:
        text += f" — {escape(note)}"
    if row.get("신호구분") == "미확인 기간":
        signal_date = pd.to_datetime(row.get("신호일"), errors="coerce")
        if not pd.isna(signal_date):
            text += f" ({signal_date:%m/%d} 주)"
    return text


def _rank_label(rank: object) -> str:
    """Bare rank number, or "관심" / "순위 밖" for unranked tickers."""
    text = market_cap_rank_text(rank)
    return text[:-1] if text.endswith("위") else text


def short_company_name(company: object) -> str:
    """Company name short enough for one phone line.

    Drops the watchlist label and legal suffixes ("Mastercard Incorporated" ->
    "Mastercard") and cuts what is still too long.
    """
    if company is None or (isinstance(company, float) and pd.isna(company)):
        return ""
    name = str(company).strip()
    if name.startswith(WATCHLIST_LABEL):
        name = name[len(WATCHLIST_LABEL) :].strip()
    if name == "nan":
        return ""
    shortened = True
    while shortened:
        shortened = False
        for suffix in COMPANY_SUFFIXES:
            if name.lower().endswith(suffix.lower()) and len(name) > len(suffix):
                name = name[: -len(suffix)].rstrip(" ,")
                shortened = True
    if len(name) > MAX_COMPANY_NAME_LENGTH:
        name = name[: MAX_COMPANY_NAME_LENGTH - 1].rstrip() + "…"
    return name
