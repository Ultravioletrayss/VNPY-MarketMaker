from .config import Config
from .market_data import MarketSnapshot
from .quote_engine import Quote


class RiskManager:
    """Pre-trade and post-trade safety checks."""

    def __init__(self, config: Config) -> None:
        self.config = config

    def check_market_data(self, snapshot: MarketSnapshot) -> bool:
        if snapshot.bid1 <= 0 or snapshot.ask1 <= 0:
            return False
        if snapshot.ask1 <= snapshot.bid1:
            return False
        return True

    def check_market_spread(self, snapshot: MarketSnapshot) -> bool:
        min_spread = self.config.min_spread_tick * self.config.price_tick
        return snapshot.ask1 - snapshot.bid1 >= min_spread

    def is_position_too_large(self, position: int) -> bool:
        return abs(position) >= self.config.max_position

    def filter_quotes_by_position(
        self,
        buy_quotes: list[Quote],
        sell_quotes: list[Quote],
        position: int,
    ) -> tuple[list[Quote], list[Quote]]:
        if position >= self.config.max_position:
            return [], sell_quotes
        if position <= -self.config.max_position:
            return buy_quotes, []
        return buy_quotes, sell_quotes

    def check_order_count(self, active_order_count: int, desired_order_count: int) -> bool:
        return max(active_order_count, desired_order_count) <= self.config.max_active_orders
