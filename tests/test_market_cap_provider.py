from __future__ import annotations

from market_cap_provider import parse_stockanalysis_market_cap_table


def test_parse_stockanalysis_market_cap_table_extracts_ranked_companies() -> None:
    html = """
    <html>
      <body>
        <table>
          <thead>
            <tr>
              <th>No.</th>
              <th>Symbol</th>
              <th>Company Name</th>
              <th>Market Cap</th>
              <th>Stock Price</th>
              <th>% Change</th>
              <th>Revenue</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>1</td>
              <td>NVDA</td>
              <td>NVIDIA Corporation</td>
              <td>5.34T</td>
              <td>220.61</td>
              <td>-0.77%</td>
              <td>215.94B</td>
            </tr>
            <tr>
              <td>2</td>
              <td>GOOGL</td>
              <td>Alphabet Inc.</td>
              <td>4.70T</td>
              <td>387.66</td>
              <td>-2.34%</td>
              <td>422.50B</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """

    companies = parse_stockanalysis_market_cap_table(html)

    assert len(companies) == 2
    assert companies[0].rank == 1
    assert companies[0].ticker == "NVDA"
    assert companies[0].company == "NVIDIA Corporation"
    assert companies[0].market_cap == "5.34T"
    assert companies[1].ticker == "GOOGL"


def test_preferred_shares_and_second_listings_are_removed_and_ranks_renumbered() -> None:
    from market_cap_provider import MarketCapCompany, common_stock_listings

    listings = [
        MarketCapCompany(1, "NVDA", "NVIDIA Corporation", "5.59T"),
        MarketCapCompany(2, "BRK.B", "Berkshire Hathaway Inc.", "1.08T"),
        MarketCapCompany(3, "BAC.PRO", "Bank of America Corporation", "396.49B"),
        MarketCapCompany(4, "BAC", "Bank of America Corporation", "390.06B"),
        MarketCapCompany(5, "MS.PRE", "Morgan Stanley", "308.32B"),
        MarketCapCompany(6, "MS", "Morgan Stanley", "304.55B"),
        MarketCapCompany(7, "PBR", "Petrobras", "126.19B"),
        MarketCapCompany(8, "PBR.A", "Petrobras", "126.19B"),
    ]

    kept = common_stock_listings(listings)

    assert [(item.rank, item.ticker) for item in kept] == [
        (1, "NVDA"),
        (2, "BRK.B"),
        (3, "BAC"),
        (4, "MS"),
        (5, "PBR"),
    ]


CURRENT_LAYOUT_HTML = """
<table><thead><tr>
  <th>Rank</th><th>Company</th><th>Market Cap</th><th>Price</th><th>Today</th>
</tr></thead><tbody>
<tr><td>1</td><td><a href="/stocks/nvda/"><div><img alt=""/> <span>N</span></div>
  <div><div>NVIDIA Corporation</div> <div>NVDA</div></div></a></td>
  <td>5.77T</td><td>$238.90</td><td>+2.12%</td></tr>
<tr><td>12</td><td><a href="/stocks/brk.b/"><div><span>B</span></div>
  <div><div>Berkshire Hathaway Inc.</div> <div>BRK.B</div></div></a></td>
  <td>1.08T</td><td>$500.00</td><td>+0.10%</td></tr>
<tr><td>51</td><td><a href="/stocks/gs.prd/"><div><span>T</span></div>
  <div><div>The Goldman Sachs Group, Inc.</div> <div>GS.PRD</div></div></a></td>
  <td>283.22B</td><td>$20.00</td><td>0.00%</td></tr>
<tr><td>60</td><td><a href="/stocks/t/"><div><span>A</span></div>
  <div><div>AT&amp;T Inc.</div> <div>T</div></div></a></td>
  <td>200.00B</td><td>$28.00</td><td>0.00%</td></tr>
</tbody></table>
"""


def test_parse_current_layout_with_combined_company_cell() -> None:
    companies = parse_stockanalysis_market_cap_table(CURRENT_LAYOUT_HTML)

    assert [(c.rank, c.ticker, c.company, c.market_cap) for c in companies] == [
        (1, "NVDA", "NVIDIA Corporation", "5.77T"),
        (12, "BRK.B", "Berkshire Hathaway Inc.", "1.08T"),
        (51, "GS.PRD", "The Goldman Sachs Group, Inc.", "283.22B"),
        (60, "T", "AT&T Inc.", "200.00B"),
    ]


def exchange_list_html(rows: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f"<tr><td>{index}</td><td>{ticker}</td><td>{name}</td><td>{cap}</td>"
        f"<td>$1.00</td><td>0.00%</td><td>1B</td></tr>"
        for index, (ticker, name, cap) in enumerate(rows, start=1)
    )
    return (
        "<table><thead><tr><th>No.</th><th>Symbol</th><th>Company Name</th>"
        "<th>Market Cap</th><th>Stock Price</th><th>% Change</th><th>Revenue</th>"
        f"</tr></thead><tbody>{body}</tbody></table>"
    )


NASDAQ_HTML = exchange_list_html(
    [("NVDA", "NVIDIA Corporation", "5.72T"), ("AAPL", "Apple Inc.", "4.86T"),
     ("COST", "Costco Wholesale Corporation", "409.37B")]
)
NYSE_HTML = exchange_list_html(
    [("TSM", "Taiwan Semiconductor", "2.07T"), ("BRK.B", "Berkshire Hathaway Inc.", "1.08T"),
     ("BAC.PRO", "Bank of America Corporation", "396.49B"),
     ("BAC", "Bank of America Corporation", "390.06B")]
)


def test_market_cap_text_is_ordered_by_value() -> None:
    from market_cap_provider import market_cap_value

    assert market_cap_value("5.72T") == 5.72e12
    assert market_cap_value("$396.49B") == 396.49e9
    assert market_cap_value("1,234") == 1234.0
    assert market_cap_value("n/a") == float("-inf")


def test_ranking_merges_the_nasdaq_and_nyse_lists_by_market_cap(monkeypatch) -> None:
    import market_cap_provider as provider

    requested = []

    def fake_download(url: str) -> str:
        requested.append(url)
        return NASDAQ_HTML if "nasdaq" in url else NYSE_HTML

    monkeypatch.setattr(provider, "_download_list_page", fake_download)

    result = provider.fetch_us_top_market_cap_result(limit=5, cache_path=None)

    assert requested == list(provider.US_EXCHANGE_LIST_URLS)
    assert [(c.rank, c.ticker) for c in result.companies] == [
        (1, "NVDA"),
        (2, "AAPL"),
        (3, "TSM"),
        (4, "BRK.B"),
        (5, "COST"),  # BAC.PRO (preferred) is dropped; BAC (390B) comes 6th
    ]
    assert result.warning == ""


def test_saved_ranking_is_used_when_the_live_pages_cannot_be_read(
    monkeypatch, tmp_path
) -> None:
    import pytest

    import market_cap_provider as provider

    cache = tmp_path / "top100_cache.json"
    monkeypatch.setattr(
        provider,
        "_download_list_page",
        lambda url: NASDAQ_HTML if "nasdaq" in url else NYSE_HTML,
    )
    live = provider.fetch_us_top_market_cap_result(limit=3, cache_path=cache)
    assert live.warning == "" and cache.exists()

    # The site changes its layout: nothing can be parsed any more.
    monkeypatch.setattr(provider, "_download_list_page", lambda url: "<html></html>")
    fallback = provider.fetch_us_top_market_cap_result(limit=3, cache_path=cache)

    assert [c.ticker for c in fallback.companies] == ["NVDA", "AAPL", "TSM"]
    assert "저장한 목록을 사용합니다" in fallback.warning
    with pytest.raises(provider.MarketCapLoadError):
        provider.fetch_us_top_market_cap_result(limit=3, cache_path=tmp_path / "none.json")


def test_heading_with_a_hash_prefix_is_still_recognised() -> None:
    html = CURRENT_LAYOUT_HTML.replace("<th>Rank</th>", "<th># Rank</th>")

    companies = parse_stockanalysis_market_cap_table(html)

    assert [c.ticker for c in companies] == ["NVDA", "BRK.B", "GS.PRD", "T"]


def test_the_commonly_traded_share_class_is_kept_for_dual_class_companies() -> None:
    from market_cap_provider import MarketCapCompany, common_stock_listings

    kept = common_stock_listings(
        [
            MarketCapCompany(1, "BRK.A", "Berkshire Hathaway Inc.", "1.08T"),
            MarketCapCompany(2, "BRK.B", "Berkshire Hathaway Inc.", "1.08T"),
            MarketCapCompany(3, "HEI.A", "HEICO Corporation", "20B"),
            MarketCapCompany(4, "HEI", "HEICO Corporation", "20B"),
            MarketCapCompany(5, "GOOGL", "Alphabet Inc.", "4T"),
        ]
    )

    assert [(c.rank, c.ticker) for c in kept] == [(1, "BRK.B"), (2, "HEI"), (3, "GOOGL")]
