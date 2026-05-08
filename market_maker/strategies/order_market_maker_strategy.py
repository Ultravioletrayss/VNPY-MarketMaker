from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    TradeData,
    OrderData,
    StopOrder,
)

class MarketDataManager:
    def __init__(self) -> None:
        self.last_tick: TickData | None = None
        self.datetime = None

        self.last_price: float = 0.0

        self.bid_prices: list[float] = [0.0] * 5
        self.ask_prices: list[float] = [0.0] * 5
        self.bid_volumes: list[float] = [0.0] * 5
        self.ask_volumes: list[float] = [0.0] * 5

        self.bid1: float = 0.0
        self.ask1: float = 0.0
        self.bid1_volume: float = 0.0
        self.ask1_volume: float = 0.0

        self.market_spread: float = 0.0
        self.valid_depth: int = 0

    def update_tick(self, tick: TickData) -> dict:
        self.last_tick = tick
        self.datetime = tick.datetime
        self.last_price = float(tick.last_price or 0.0)

        self.bid_prices = [
            float(tick.bid_price_1 or 0.0),
            float(tick.bid_price_2 or 0.0),
            float(tick.bid_price_3 or 0.0),
            float(tick.bid_price_4 or 0.0),
            float(tick.bid_price_5 or 0.0),
        ]

        self.ask_prices = [
            float(tick.ask_price_1 or 0.0),
            float(tick.ask_price_2 or 0.0),
            float(tick.ask_price_3 or 0.0),
            float(tick.ask_price_4 or 0.0),
            float(tick.ask_price_5 or 0.0),
        ]

        self.bid_volumes = [
            float(tick.bid_volume_1 or 0.0),
            float(tick.bid_volume_2 or 0.0),
            float(tick.bid_volume_3 or 0.0),
            float(tick.bid_volume_4 or 0.0),
            float(tick.bid_volume_5 or 0.0),
        ]

        self.ask_volumes = [
            float(tick.ask_volume_1 or 0.0),
            float(tick.ask_volume_2 or 0.0),
            float(tick.ask_volume_3 or 0.0),
            float(tick.ask_volume_4 or 0.0),
            float(tick.ask_volume_5 or 0.0),
        ]

        self.bid1 = self.bid_prices[0]
        self.ask1 = self.ask_prices[0]
        self.bid1_volume = self.bid_volumes[0]
        self.ask1_volume = self.ask_volumes[0]

        if self.bid1 > 0 and self.ask1 > 0 and self.ask1 > self.bid1:
            self.market_spread = self.ask1 - self.bid1
        else:
            self.market_spread = 0.0

        self.valid_depth = self._calculate_valid_depth()

        return self.get_snapshot()

    def _calculate_valid_depth(self) -> int:
        valid_depth = 0

        for i in range(5):
            if (
                self.bid_prices[i] > 0
                and self.ask_prices[i] > 0
                and self.bid_volumes[i] > 0
                and self.ask_volumes[i] > 0
            ):
                valid_depth += 1
            else:
                break

        return valid_depth

    def get_snapshot(self) -> dict:
        return {
            "datetime": self.datetime,
            "last_price": self.last_price,
            "bid_prices": self.bid_prices.copy(),
            "ask_prices": self.ask_prices.copy(),
            "bid_volumes": self.bid_volumes.copy(),
            "ask_volumes": self.ask_volumes.copy(),
            "bid1": self.bid1,
            "ask1": self.ask1,
            "bid1_volume": self.bid1_volume,
            "ask1_volume": self.ask1_volume,
            "market_spread": self.market_spread,
            "valid_depth": self.valid_depth,
        }

    def is_valid(self) -> bool:
        if self.bid1 <= 0:
            return False

        if self.ask1 <= 0:
            return False

        if self.ask1 <= self.bid1:
            return False

        if self.bid1_volume <= 0:
            return False

        if self.ask1_volume <= 0:
            return False

        return True

    def has_depth(self, depth: int = 5) -> bool:
        return self.valid_depth >= depth

    def get_depth_volume(self, depth: int = 5) -> tuple[float, float]:
        depth = min(depth, 5, self.valid_depth)

        if depth <= 0:
            return 0.0, 0.0

        bid_volume_sum = sum(self.bid_volumes[:depth])
        ask_volume_sum = sum(self.ask_volumes[:depth])

        return bid_volume_sum, ask_volume_sum

    def get_order_book_imbalance(self, depth: int = 5) -> float:
        bid_volume_sum, ask_volume_sum = self.get_depth_volume(depth)
        total_volume = bid_volume_sum + ask_volume_sum

        if total_volume <= 0:
            return 0.0

        return (bid_volume_sum - ask_volume_sum) / total_volume

    def get_mid_price(self) -> float:
        if not self.is_valid():
            return 0.0

        return (self.bid1 + self.ask1) / 2

    def get_micro_price(self) -> float:
        if not self.is_valid():
            return 0.0

        total_volume = self.bid1_volume + self.ask1_volume

        if total_volume <= 0:
            return self.get_mid_price()

        return (
            self.ask1 * self.bid1_volume
            + self.bid1 * self.ask1_volume
        ) / total_volume

class PricingEngine:
    def __init__(self) -> None:
        self.mid_price: float = 0.0
        self.micro_price: float = 0.0
        self.depth_weighted_mid: float = 0.0
        self.fair_price: float = 0.0

    def calculate_mid_price(self, snapshot: dict) -> float:
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]

        if bid1 <= 0 or ask1 <= 0 or ask1 <= bid1:
            return 0.0

        self.mid_price = (bid1 + ask1) / 2
        return self.mid_price

    def calculate_micro_price(self, snapshot: dict) -> float:
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]
        bid1_volume = snapshot["bid1_volume"]
        ask1_volume = snapshot["ask1_volume"]

        if bid1 <= 0 or ask1 <= 0 or ask1 <= bid1:
            return 0.0

        total_volume = bid1_volume + ask1_volume

        if total_volume <= 0:
            return self.calculate_mid_price(snapshot)

        self.micro_price = (
            ask1 * bid1_volume
            + bid1 * ask1_volume
        ) / total_volume

        return self.micro_price

    def calculate_depth_weighted_mid(
        self,
        snapshot: dict,
        depth: int = 5
    ) -> float:
        bid_prices = snapshot["bid_prices"]
        ask_prices = snapshot["ask_prices"]
        bid_volumes = snapshot["bid_volumes"]
        ask_volumes = snapshot["ask_volumes"]
        valid_depth = snapshot["valid_depth"]

        depth = min(depth, valid_depth, 5)

        if depth <= 0:
            return 0.0

        bid_amount = 0.0
        ask_amount = 0.0
        bid_volume_sum = 0.0
        ask_volume_sum = 0.0

        for i in range(depth):
            bid_price = bid_prices[i]
            ask_price = ask_prices[i]
            bid_volume = bid_volumes[i]
            ask_volume = ask_volumes[i]

            if bid_price <= 0 or ask_price <= 0:
                continue

            if bid_volume <= 0 or ask_volume <= 0:
                continue

            bid_amount += bid_price * bid_volume
            ask_amount += ask_price * ask_volume
            bid_volume_sum += bid_volume
            ask_volume_sum += ask_volume

        if bid_volume_sum <= 0 or ask_volume_sum <= 0:
            return self.calculate_mid_price(snapshot)

        weighted_bid = bid_amount / bid_volume_sum
        weighted_ask = ask_amount / ask_volume_sum

        self.depth_weighted_mid = (weighted_bid + weighted_ask) / 2

        return self.depth_weighted_mid

    def calculate_fair_price(
        self,
        snapshot: dict,
        pricing_method: str,
        depth: int = 5
    ) -> float:
        if pricing_method == "mid":
            self.fair_price = self.calculate_mid_price(snapshot)

        elif pricing_method == "micro":
            self.fair_price = self.calculate_micro_price(snapshot)

        elif pricing_method == "depth_weighted":
            self.fair_price = self.calculate_depth_weighted_mid(
                snapshot=snapshot,
                depth=depth
            )

        else:
            self.fair_price = self.calculate_mid_price(snapshot)

        return self.fair_price

    def round_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return round(price / price_tick) * price_tick


class QuoteEngine:
    """报价模块"""
    pass


class InventorySkewEngine:
    """库存偏移/软对冲模块"""
    pass


class HedgeEngine:
    """主动对冲模块"""
    pass

class QuoteRiskFilter:
    def check_market_data(self, snapshot: dict) -> bool:
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]
        bid1_volume = snapshot["bid1_volume"]
        ask1_volume = snapshot["ask1_volume"]

        if bid1 <= 0:
            return False

        if ask1 <= 0:
            return False

        if ask1 <= bid1:
            return False

        if bid1_volume <= 0:
            return False

        if ask1_volume <= 0:
            return False

        return True

    def check_depth(
        self,
        snapshot: dict,
        min_depth: int = 1
    ) -> bool:
        valid_depth = snapshot["valid_depth"]

        return valid_depth >= min_depth

    def check_spread(
        self,
        snapshot: dict,
        price_tick: float,
        min_spread_tick: int
    ) -> bool:
        market_spread = snapshot["market_spread"]

        if price_tick <= 0:
            return False

        spread_tick = market_spread / price_tick

        return spread_tick >= min_spread_tick

    def check_depth_volume(
        self,
        snapshot: dict,
        depth: int = 5,
        min_depth_volume: float = 1
    ) -> bool:
        bid_volumes = snapshot["bid_volumes"]
        ask_volumes = snapshot["ask_volumes"]
        valid_depth = snapshot["valid_depth"]

        depth = min(depth, valid_depth, 5)

        if depth <= 0:
            return False

        bid_volume_sum = sum(bid_volumes[:depth])
        ask_volume_sum = sum(ask_volumes[:depth])

        if bid_volume_sum < min_depth_volume:
            return False

        if ask_volume_sum < min_depth_volume:
            return False

        return True

    def check_imbalance(
        self,
        snapshot: dict,
        max_imbalance: float = 0.9,
        depth: int = 5
    ) -> bool:
        bid_volumes = snapshot["bid_volumes"]
        ask_volumes = snapshot["ask_volumes"]
        valid_depth = snapshot["valid_depth"]

        depth = min(depth, valid_depth, 5)

        if depth <= 0:
            return False

        bid_volume_sum = sum(bid_volumes[:depth])
        ask_volume_sum = sum(ask_volumes[:depth])
        total_volume = bid_volume_sum + ask_volume_sum

        if total_volume <= 0:
            return False

        imbalance = (bid_volume_sum - ask_volume_sum) / total_volume

        return abs(imbalance) <= max_imbalance

    def filter_by_position(
        self,
        buy_quotes: list[dict],
        sell_quotes: list[dict],
        pos: float,
        max_position: float
    ) -> tuple[list[dict], list[dict]]:
        if max_position <= 0:
            return [], []

        if pos >= max_position:
            buy_quotes = []

        if pos <= -max_position:
            sell_quotes = []

        return buy_quotes, sell_quotes


class OrderMarketMakerStrategy(CtaTemplate):
    """Order模式通用做市策略"""
    pass