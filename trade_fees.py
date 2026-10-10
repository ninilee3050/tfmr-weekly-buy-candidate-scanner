"""Trading costs used for the after-fee return of a trade case.

The defaults are the Kakao Pay Securities US-stock rates the user gave on
2026-05-13.  Rates change, so check them against the broker before relying
on the result; edit ``DEFAULT_FEES`` to use other rates.

Share counts in a trade case are units (round N buys N units), not a real
order size, so the per-order minimum and maximum fees of the broker are left
out: at one unit they would swamp the result, at a real order size they do
not matter.  Capital gains tax and currency exchange costs are not included.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeSchedule:
    # Broker commission as a fraction of the traded amount.
    buy_rate: float = 0.001
    sell_rate: float = 0.001
    # SEC fee as a fraction of the sold amount.
    sec_rate: float = 0.0000206
    # FINRA trading activity fee in dollars per share sold.
    taf_per_share: float = 0.000166

    def buy_cost(self, amount: float) -> float:
        """What a purchase of ``amount`` really costs."""
        return amount * (1 + self.buy_rate)

    def sell_proceeds(self, amount: float, quantity: float) -> float:
        """What a sale of ``amount`` really brings in."""
        return amount * (1 - self.sell_rate - self.sec_rate) - self.taf_per_share * quantity

    def net_return_pct(self, cost: float, sell_amount: float, quantity: float) -> float:
        """Return in percent after every fee, for ``cost`` paid and ``sell_amount`` received."""
        return (self.sell_proceeds(sell_amount, quantity) / self.buy_cost(cost) - 1) * 100


DEFAULT_FEES = FeeSchedule()
NO_FEES = FeeSchedule(buy_rate=0.0, sell_rate=0.0, sec_rate=0.0, taf_per_share=0.0)
