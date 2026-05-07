from dataclasses import dataclass
from typing import Protocol

from .config import Config
from .quote_engine import Quote


class TradingGateway(Protocol):
    def buy(self, price: float, volume: int) -> str:
        ...

    def sell(self, price: float, volume: int) -> str:
        ...

    def cancel_order(self, order_id: str) -> None:
        ...


@dataclass
class ActiveOrder:
    order_id: str
    direction: str
    price: float
    volume: int
    level: int
    status: str = "SUBMITTING"


class OrderManager:
    """Sends, cancels, tracks, and requotes normal order-mode orders."""

    def __init__(self, config: Config, gateway: TradingGateway) -> None:
        self.config = config
        self.gateway = gateway
        self.active_orders: dict[str, ActiveOrder] = {}

    def update_orders(self, buy_quotes: list[Quote], sell_quotes: list[Quote]) -> None:
        desired_quotes = buy_quotes + sell_quotes
        desired_keys = {(quote.direction, quote.level): quote for quote in desired_quotes}

        for order in list(self.active_orders.values()):
            quote = desired_keys.get((order.direction, order.level))
            if quote is None or self._need_requote(order.price, quote.price):
                self.cancel_order(order.order_id)

        current_keys = {
            (order.direction, order.level)
            for order in self.active_orders.values()
            if order.status in {"SUBMITTING", "NOTTRADED", "PARTTRADED"}
        }

        for quote in desired_quotes:
            if (quote.direction, quote.level) not in current_keys:
                self.send_order(quote)

    def send_order(self, quote: Quote) -> str:
        if quote.direction == "BUY":
            order_id = self.gateway.buy(quote.price, quote.volume)
        elif quote.direction == "SELL":
            order_id = self.gateway.sell(quote.price, quote.volume)
        else:
            raise ValueError(f"unsupported direction: {quote.direction}")

        self.active_orders[order_id] = ActiveOrder(
            order_id=order_id,
            direction=quote.direction,
            price=quote.price,
            volume=quote.volume,
            level=quote.level,
            status="NOTTRADED",
        )
        print(f"[ORDER] send {quote.direction} level={quote.level} price={quote.price} volume={quote.volume} id={order_id}")
        return order_id

    def cancel_order(self, order_id: str) -> None:
        order = self.active_orders.get(order_id)
        if not order:
            return
        self.gateway.cancel_order(order_id)
        order.status = "CANCELLED"
        self.active_orders.pop(order_id, None)
        print(f"[ORDER] cancel id={order_id} direction={order.direction} price={order.price}")

    def cancel_all(self) -> None:
        for order_id in list(self.active_orders):
            self.cancel_order(order_id)

    def update_order_status(self, order: object) -> None:
        order_id = self._read_value(order, "order_id", self._read_value(order, "vt_orderid", ""))
        status = self._read_value(order, "status", "")
        if order_id in self.active_orders:
            self.active_orders[order_id].status = str(status)
            if str(status).upper() in {"ALLTRADED", "CANCELLED", "REJECTED"}:
                self.active_orders.pop(order_id, None)

    def _need_requote(self, old_price: float, new_price: float) -> bool:
        diff_tick = abs(old_price - new_price) / self.config.price_tick
        return diff_tick > self.config.update_tolerance

    @staticmethod
    def _read_value(obj: object, name: str, default: object) -> object:
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

