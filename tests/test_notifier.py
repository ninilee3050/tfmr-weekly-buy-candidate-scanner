from __future__ import annotations

import json

import pandas as pd
import pytest

import notifier
from notifier import (
    NotificationError,
    build_failure_message,
    build_scan_message,
    notify_from_environment,
    send_telegram_message,
    short_company_name,
)

SCAN_DATE = pd.Timestamp("2026-10-16")


def event(ticker: str, company: str, stage: str, rank: int, **extra: object) -> dict:
    return {
        "순위": rank,
        "티커": ticker,
        "회사명": company,
        "단계": stage,
        "신호일": pd.Timestamp("2026-10-12"),
        "신호구분": "이번 주",
        **extra,
    }


def holding(ticker: str, company: str, rank: int, rounds: int, pnl: float) -> dict:
    return {
        "순위": rank,
        "티커": ticker,
        "회사명": company,
        "현재상태": "보유 중",
        "매수차수": rounds,
        "평가손익률": pnl,
    }


def test_message_lists_signals_by_urgency_then_the_cases_still_held() -> None:
    events = pd.DataFrame(
        [
            event("AAPL", "Apple Inc.", "1차 매수", 2, 매수차수=1, 가격=245.1),
            event("JPM", "JPMorgan Chase & Co.", "추가매수", 11, 매수차수=2, 가격=321.5),
            event("BAC", "Bank of America Corporation", "매도", 24, 수익률=2.13, 보유주수=5),
        ]
    )
    active = pd.DataFrame(
        [
            holding("AAPL", "Apple Inc.", 2, 1, 0.0),
            holding("JPM", "JPMorgan Chase & Co.", 11, 2, -1.2),
            holding("TSLA", "Tesla, Inc.", 8, 3, -4.24),
        ]
    )

    message = build_scan_message(events, active, 0, SCAN_DATE)

    assert message.splitlines() == [
        "📈 TFMR 주간 스캔 · 10/16 (금) · 확정",
        "",
        "🔴 매도 신호 <b>1건</b>",
        "▸ <code>24</code> <b>BAC</b> (Bank of America) — +2.1% · 5주",
        "",
        "🟠 추가매수 <b>1건</b>",
        "▸ <code>11</code> <b>JPM</b> (JPMorgan Chase) — 2차 · 321.50",
        "",
        "🟢 신규 1차 매수 <b>1건</b>",
        "▸ <code>2</code> <b>AAPL</b> (Apple) — 245.10",
        "",
        "보유 중 <b>1건</b>",
        "▸ <code>8</code> <b>TSLA</b> (Tesla) — 3차 · -4.2%",
    ]


def test_held_cases_are_listed_by_market_cap_rank() -> None:
    active = pd.DataFrame(
        [
            holding("LOW", "Low Rank Inc.", 80, 1, 1.0),
            holding("TOP", "Top Rank Inc.", 3, 2, -2.0),
        ]
    )

    lines = build_scan_message(pd.DataFrame(), active, 0, SCAN_DATE).splitlines()

    assert lines[2:] == [
        "매수·매도 신호 없음",
        "",
        "보유 중 <b>2건</b>",
        "▸ <code>3</code> <b>TOP</b> (Top Rank) — 2차 · -2.0%",
        "▸ <code>80</code> <b>LOW</b> (Low Rank) — 1차 · +1.0%",
    ]


def test_long_section_is_cut_with_a_remaining_count() -> None:
    events = pd.DataFrame(
        [
            event(f"T{number}", f"Company {number}", "1차 매수", number, 가격=10.0)
            for number in range(1, 19)
        ]
    )

    lines = build_scan_message(events, pd.DataFrame(), 0, SCAN_DATE).splitlines()

    assert lines[2] == "🟢 신규 1차 매수 <b>18건</b>"
    assert len(lines) == 3 + 15 + 1
    assert lines[-1] == "▸ 외 3건"


def test_message_without_signals_and_with_warning() -> None:
    message = build_scan_message(
        pd.DataFrame(),
        pd.DataFrame(),
        2,
        SCAN_DATE,
        warnings=["저장한 Top 100 목록을 사용했습니다."],
    )

    assert message.splitlines() == [
        "📈 TFMR 주간 스캔 · 10/16 (금) · 확정",
        "",
        "매수·매도 신호 없음",
        "",
        "데이터 오류 2건",
        "⚠️ 저장한 Top 100 목록을 사용했습니다.",
    ]


def test_watchlist_and_unranked_tickers_show_a_label_instead_of_a_rank() -> None:
    events = pd.DataFrame(
        [
            event("BTC-USD", "[관심] 비트코인", "1차 매수", 9000, 가격=60000.0),
            event("OLD", "Old Company", "매도", 9999, 수익률=-3.0, 보유주수=2),
        ]
    )

    message = build_scan_message(events, pd.DataFrame(), 0, SCAN_DATE)

    assert "▸ <code>관심</code> <b>BTC-USD</b> (비트코인) — 60,000.00" in message.splitlines()
    assert "▸ <code>순위 밖</code> <b>OLD</b> (Old) — -3.0% · 2주" in message.splitlines()
    assert "※ BTC-USD: 주말 거래 반영 전" in message.splitlines()


def test_signal_from_a_missed_week_shows_its_week() -> None:
    events = pd.DataFrame(
        [
            event(
                "MA", "Mastercard Incorporated", "추가매수", 20,
                매수차수=3, 가격=500.0,
                신호일=pd.Timestamp("2026-10-05"), 신호구분="미확인 기간",
            )
        ]
    )

    message = build_scan_message(events, pd.DataFrame(), 0, SCAN_DATE)

    assert "▸ <code>20</code> <b>MA</b> (Mastercard) — 3차 · 500.00 (10/05 주)" in message.splitlines()


def test_events_without_rank_or_detail_columns_are_still_listed() -> None:
    events = pd.DataFrame([{"티커": "AAA", "단계": "1차 매수"}])

    message = build_scan_message(events, pd.DataFrame(), 0, SCAN_DATE)

    assert "▸ <b>AAA</b>" in message.splitlines()


def test_provisional_message_has_a_one_line_notice() -> None:
    with_basis = build_scan_message(
        pd.DataFrame(), pd.DataFrame(), 0, SCAN_DATE, provisional=True, data_basis="목요일 종가까지 반영"
    )
    without_basis = build_scan_message(pd.DataFrame(), pd.DataFrame(), 0, SCAN_DATE, provisional=True)

    assert with_basis.splitlines()[:3] == [
        "📈 TFMR 주간 스캔 · 10/16 (금) · 잠정",
        "※ 목요일 종가까지 반영",
        "",
    ]
    assert without_basis.splitlines()[1] == "※ 이번 주 장 마감 전"


def test_data_basis_follows_the_new_york_clock() -> None:
    from weekly_scan import data_basis_text

    friday_before_open = pd.Timestamp("2026-10-16 01:00", tz="America/New_York")
    friday_session = pd.Timestamp("2026-10-16 11:00", tz="America/New_York")
    monday_before_open = pd.Timestamp("2026-10-19 08:00", tz="America/New_York")
    saturday = pd.Timestamp("2026-10-17 10:00", tz="America/New_York")

    assert data_basis_text(friday_before_open) == "목요일 종가까지 반영"
    assert data_basis_text(friday_session) == "오늘 미국 장중 가격 포함"
    assert data_basis_text(monday_before_open) == "금요일 종가까지 반영"
    assert data_basis_text(saturday) == "최근 거래일 종가까지 반영"


def test_company_names_are_shortened_to_fit_one_line() -> None:
    assert short_company_name("Mastercard Incorporated") == "Mastercard"
    assert short_company_name("Meta Platforms, Inc.") == "Meta Platforms"
    assert short_company_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert short_company_name("UnitedHealth Group Incorporated") == "UnitedHealth"
    assert short_company_name("SAP SE") == "SAP SE"
    assert short_company_name("[관심] 비트코인") == "비트코인"
    assert short_company_name("Taiwan Semiconductor Manufacturing Company Limited") == "Taiwan Semicond…"
    assert short_company_name(None) == ""
    assert short_company_name(float("nan")) == ""


def test_company_names_are_shortened_to_fit_one_line() -> None:
    assert short_company_name("Mastercard Incorporated") == "Mastercard"
    assert short_company_name("Meta Platforms, Inc.") == "Meta Platforms"
    assert short_company_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert short_company_name("UnitedHealth Group Incorporated") == "UnitedHealth"
    assert short_company_name("SAP SE") == "SAP SE"
    assert short_company_name("[관심] 비트코인") == "비트코인"
    assert short_company_name("Taiwan Semiconductor Manufacturing Company Limited") == "Taiwan Semicond…"
    assert short_company_name(None) == ""
    assert short_company_name(float("nan")) == ""


def test_text_from_outside_is_escaped_for_html() -> None:
    message = build_scan_message(
        pd.DataFrame([event("A&B", "AT&T Inc.", "1차 매수", 60, 가격=20.0)]),
        pd.DataFrame(),
        0,
        SCAN_DATE,
        warnings=["<목록> 오류 & 재시도"],
    )
    failure = build_failure_message("HTTP <500> & retry", SCAN_DATE)

    assert "▸ <code>60</code> <b>A&amp;B</b> (AT&amp;T) — 20.00" in message.splitlines()
    assert "⚠️ &lt;목록&gt; 오류 &amp; 재시도" in message
    assert failure.startswith("⚠️ TFMR 주간 스캔 실패 · 10/16 (금)")
    assert "HTTP &lt;500&gt; &amp; retry" in failure


def test_nothing_is_sent_without_telegram_settings(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(
        notifier, "send_telegram_message", lambda *args: pytest.fail("must not send")
    )

    assert notify_from_environment("hello") is False


def test_message_is_posted_as_html_to_the_configured_chat(monkeypatch) -> None:
    sent = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr(notifier, "urlopen", fake_urlopen)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", " TEST-TOKEN ")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "4242")

    assert notify_from_environment("<b>SAP</b>") is True
    assert sent["url"] == "https://api.telegram.org/botTEST-TOKEN/sendMessage"
    assert sent["body"] == {"chat_id": "4242", "text": "<b>SAP</b>", "parse_mode": "HTML"}


def test_delivery_errors_do_not_reveal_the_token(monkeypatch) -> None:
    from urllib.error import HTTPError

    def failing_urlopen(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", None, None)

    monkeypatch.setattr(notifier, "urlopen", failing_urlopen)

    with pytest.raises(NotificationError) as error:
        send_telegram_message("text", "SECRET-TOKEN", "1")

    assert "SECRET-TOKEN" not in str(error.value)
    assert "봇 토큰이 틀렸습니다" in str(error.value)
    assert error.value.__cause__ is None
