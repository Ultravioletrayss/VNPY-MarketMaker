from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TradeRecord:
    direction: str
    price: float
    volume: int
    trade_time: datetime
    order_id: str = ""


@dataclass
class TradeManager:
    position: int = 0
    trades: list[TradeRecord] = field(default_factory=list)

    def update_position(self, trade: Any) -> int:
        direction = str(self._read_value(trade, "direction", "")).upper()
        volume = int(self._read_value(trade, "volume", 0))

        if direction == "BUY":
            self.position += volume
        elif direction == "SELL":
            self.position -= volume
        else:
            raise ValueError(f"unsupported trade direction: {direction}")

        return self.position

    def record_trade(self, trade: Any) -> TradeRecord:
        record = TradeRecord(
            direction=str(self._read_value(trade, "direction", "")).upper(),
            price=float(self._read_value(trade, "price", 0)),
            volume=int(self._read_value(trade, "volume", 0)),
            trade_time=self._read_value(trade, "trade_time", datetime.now()),
            order_id=str(self._read_value(trade, "order_id", self._read_value(trade, "vt_orderid", ""))),
        )
        self.trades.append(record)
        print(f"[TRADE] {record.direction} price={record.price} volume={record.volume} position={self.position}")
        return record

    @staticmethod
    def _read_value(trade: Any, name: str, default: Any) -> Any:
        if isinstance(trade, dict):
            return trade.get(name, default)
        return getattr(trade, name, default)

