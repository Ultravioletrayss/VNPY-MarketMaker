from typing import Any


class VnpyGatewayAdapter:
    """Adapter shape for plugging the teaching strategy into a vn.py strategy class.

    Pass an existing vn.py strategy instance as `strategy`. The instance should provide
    buy(price, volume), sell(price, volume), and cancel_order(order_id).
    """

    def __init__(self, strategy: Any) -> None:
        self.strategy = strategy

    def buy(self, price: float, volume: int) -> str:
        order_ids = self.strategy.buy(price, volume)
        return self._first_order_id(order_ids)

    def sell(self, price: float, volume: int) -> str:
        order_ids = self.strategy.sell(price, volume)
        return self._first_order_id(order_ids)

    def cancel_order(self, order_id: str) -> None:
        self.strategy.cancel_order(order_id)

    @staticmethod
    def _first_order_id(order_ids: Any) -> str:
        if isinstance(order_ids, str):
            return order_ids
        if order_ids:
            return str(order_ids[0])
        raise RuntimeError("vn.py did not return an order id")

