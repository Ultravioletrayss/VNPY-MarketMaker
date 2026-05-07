from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Central strategy parameters."""

    symbol: str = "rb2501"
    exchange: str = "SHFE"

    price_tick: float = 1
    order_volume: int = 1

    quote_levels: int = 1
    spread_tick: int = 2
    update_tolerance: int = 1

    max_position: int = 10
    min_spread_tick: int = 1
    max_active_orders: int = 20

    cancel_on_trade: bool = True

