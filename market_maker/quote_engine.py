from dataclasses import dataclass

from .config import Config


@dataclass(frozen=True)
class Quote:
    level: int
    direction: str
    price: float
    volume: int


class QuoteEngine:
    """Generates normal buy/sell order quotes around a reference price."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def generate_quotes(self, mid_price: float, position: int = 0) -> tuple[list[Quote], list[Quote]]:
        buy_quotes: list[Quote] = []
        sell_quotes: list[Quote] = []

        bid_offset, ask_offset = self._inventory_offsets(position)

        for level in range(1, self.config.quote_levels + 1):
            base_ticks = self.config.spread_tick / 2 + level - 1
            buy_price = self._round_to_tick(mid_price - (base_ticks + bid_offset) * self.config.price_tick)
            sell_price = self._round_to_tick(mid_price + (base_ticks + ask_offset) * self.config.price_tick)

            buy_quotes.append(Quote(level, "BUY", buy_price, self.config.order_volume))
            sell_quotes.append(Quote(level, "SELL", sell_price, self.config.order_volume))

        return buy_quotes, sell_quotes

    def _inventory_offsets(self, position: int) -> tuple[float, float]:
        limit = max(self.config.max_position, 1)
        ratio = max(min(position / limit, 1), -1)

        if ratio > 0:
            return ratio, -ratio
        if ratio < 0:
            return ratio, -ratio
        return 0, 0

    def _round_to_tick(self, price: float) -> float:
        ticks = round(price / self.config.price_tick)
        return ticks * self.config.price_tick

