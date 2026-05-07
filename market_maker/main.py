from itertools import count

from .config import Config
from .strategy import MarketMakerStrategy


class DemoGateway:
    """Small gateway mock. Replace this with vn.py buy/sell/cancel_order calls."""

    def __init__(self) -> None:
        self._order_no = count(1)

    def buy(self, price: float, volume: int) -> str:
        return f"BUY-{next(self._order_no)}"

    def sell(self, price: float, volume: int) -> str:
        return f"SELL-{next(self._order_no)}"

    def cancel_order(self, order_id: str) -> None:
        return None


def run_demo() -> None:
    config = Config(quote_levels=1)
    strategy = MarketMakerStrategy(config, DemoGateway())

    ticks = [
        {
            "bid_price_1": 3999,
            "ask_price_1": 4001,
            "bid_volume_1": 120,
            "ask_volume_1": 100,
            "last_price": 4000,
        },
        {
            "bid_price_1": 4002,
            "ask_price_1": 4004,
            "bid_volume_1": 90,
            "ask_volume_1": 110,
            "last_price": 4003,
        },
        {
            "bid_price_1": 4003,
            "ask_price_1": 4004,
            "bid_volume_1": 90,
            "ask_volume_1": 110,
            "last_price": 4004,
        },
    ]

    for tick in ticks:
        strategy.on_tick(tick)

    strategy.on_trade({"direction": "BUY", "price": 4002, "volume": 1, "order_id": "BUY-3"})


if __name__ == "__main__":
    run_demo()

