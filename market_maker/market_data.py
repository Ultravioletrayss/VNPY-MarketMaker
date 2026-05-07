from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class MarketSnapshot:
    bid_prices: list[float]
    ask_prices: list[float]
    bid_volumes: list[int]
    ask_volumes: list[int]
    last_price: float

    @property
    def bid1(self) -> float:
        return self.bid_prices[0]

    @property
    def ask1(self) -> float:
        return self.ask_prices[0]


class MarketData:
    """Stores the latest five-level order book snapshot from tick data."""

    def __init__(self) -> None:
        self.snapshot: MarketSnapshot | None = None

    def update(self, tick: Any) -> MarketSnapshot:
        bid_prices = self._read_levels(tick, "bid_price")
        ask_prices = self._read_levels(tick, "ask_price")
        bid_volumes = [int(v) for v in self._read_levels(tick, "bid_volume")]
        ask_volumes = [int(v) for v in self._read_levels(tick, "ask_volume")]
        last_price = float(self._read_value(tick, "last_price", 0))

        self.snapshot = MarketSnapshot(
            bid_prices=bid_prices,
            ask_prices=ask_prices,
            bid_volumes=bid_volumes,
            ask_volumes=ask_volumes,
            last_price=last_price,
        )
        return self.snapshot

    def _read_levels(self, tick: Any, prefix: str) -> list[float]:
        values: list[float] = []
        list_name = f"{prefix}s"
        list_value = self._read_value(tick, list_name, None)

        if isinstance(list_value, Sequence) and not isinstance(list_value, str):
            values.extend(float(v or 0) for v in list_value[:5])

        for level in range(len(values) + 1, 6):
            values.append(float(self._read_value(tick, f"{prefix}_{level}", 0) or 0))

        return values[:5]

    @staticmethod
    def _read_value(tick: Any, name: str, default: Any) -> Any:
        if isinstance(tick, dict):
            return tick.get(name, default)
        return getattr(tick, name, default)

