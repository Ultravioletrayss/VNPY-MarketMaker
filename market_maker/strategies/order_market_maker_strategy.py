from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    TradeData,
    OrderData,
    StopOrder,
)
import math

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


#定价可能包含单基准价 或者多基准价，都有可能 目前因该是为了方便 所以用的应该是单基准价
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
        pricing_method: str = "mid",
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
    def __init__(self) -> None:
        self.current_buy_quotes: list[dict] = []
        self.current_sell_quotes: list[dict] = []

    def generate_quotes(
        self,
        fair_price: float,
        price_tick: float,
        quote_levels: int,
        order_volume: float,
        quote_mode: str = "tick",
        spread_tick: int = 1,
        level_interval_tick: int = 1,
        spread_percent: float = 0.0002,
        level_interval_percent: float = 0.0001,
        split_count: int = 1,
        snapshot: dict | None = None,
        passive: bool = True,
    ) -> tuple[list[dict], list[dict]]:
        if fair_price <= 0:
            return [], []

        if price_tick <= 0:
            return [], []

        if quote_levels <= 0:
            return [], []

        if order_volume <= 0:
            return [], []

        if split_count <= 0:
            return [], []

        quote_levels = min(quote_levels, 5)

        buy_quotes: list[dict] = []
        sell_quotes: list[dict] = []

        for level in range(1, quote_levels + 1):
            if quote_mode == "tick":
                buy_price, sell_price, offset_value = self._calculate_tick_quote_price(
                    fair_price=fair_price,
                    price_tick=price_tick,
                    level=level,
                    spread_tick=spread_tick,
                    level_interval_tick=level_interval_tick,
                )

            elif quote_mode == "percent":
                buy_price, sell_price, offset_value = self._calculate_percent_quote_price(
                    fair_price=fair_price,
                    price_tick=price_tick,
                    level=level,
                    spread_percent=spread_percent,
                    level_interval_percent=level_interval_percent,
                )

            else:
                buy_price, sell_price, offset_value = self._calculate_tick_quote_price(
                    fair_price=fair_price,
                    price_tick=price_tick,
                    level=level,
                    spread_tick=spread_tick,
                    level_interval_tick=level_interval_tick,
                )

            if passive and snapshot:
                bid1 = snapshot["bid1"]
                ask1 = snapshot["ask1"]

                if bid1 > 0:
                    buy_price = min(buy_price, bid1)

                if ask1 > 0:
                    sell_price = max(sell_price, ask1)

            if buy_price <= 0 or sell_price <= 0:
                continue

            for order_index in range(1, split_count + 1):
                buy_quotes.append(
                    {
                        "side": "buy",
                        "level": level,
                        "order_index": order_index,
                        "price": buy_price,
                        "volume": order_volume,
                        "quote_mode": quote_mode,
                        "offset_value": offset_value,
                    }
                )

                sell_quotes.append(
                    {
                        "side": "sell",
                        "level": level,
                        "order_index": order_index,
                        "price": sell_price,
                        "volume": order_volume,
                        "quote_mode": quote_mode,
                        "offset_value": offset_value,
                    }
                )

        return buy_quotes, sell_quotes

    def _calculate_tick_quote_price(
        self,
        fair_price: float,
        price_tick: float,
        level: int,
        spread_tick: int,
        level_interval_tick: int,
    ) -> tuple[float, float, float]:
        if spread_tick < 0:
            spread_tick = 0

        if level_interval_tick <= 0:
            level_interval_tick = 1

        offset_tick = spread_tick + (level - 1) * level_interval_tick

        raw_buy_price = fair_price - offset_tick * price_tick
        raw_sell_price = fair_price + offset_tick * price_tick

        buy_price = self.floor_to_tick(raw_buy_price, price_tick)
        sell_price = self.ceil_to_tick(raw_sell_price, price_tick)

        return buy_price, sell_price, float(offset_tick)

    def _calculate_percent_quote_price(
        self,
        fair_price: float,
        price_tick: float,
        level: int,
        spread_percent: float,
        level_interval_percent: float,
    ) -> tuple[float, float, float]:
        if spread_percent < 0:
            spread_percent = 0.0

        if level_interval_percent < 0:
            level_interval_percent = 0.0

        offset_percent = spread_percent + (level - 1) * level_interval_percent

        raw_buy_price = fair_price * (1 - offset_percent)
        raw_sell_price = fair_price * (1 + offset_percent)

        buy_price = self.floor_to_tick(raw_buy_price, price_tick)
        sell_price = self.ceil_to_tick(raw_sell_price, price_tick)

        return buy_price, sell_price, offset_percent

    def floor_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return math.floor(price / price_tick) * price_tick

    def ceil_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return math.ceil(price / price_tick) * price_tick

    def round_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return round(price / price_tick) * price_tick

    def need_requote(
        self,
        new_buy_quotes: list[dict],
        new_sell_quotes: list[dict],
        price_tick: float,
        update_tolerance: int,
    ) -> bool:
        if price_tick <= 0:
            return False

        if update_tolerance < 0:
            update_tolerance = 0

        tolerance_price = update_tolerance * price_tick

        if len(new_buy_quotes) != len(self.current_buy_quotes):
            return True

        if len(new_sell_quotes) != len(self.current_sell_quotes):
            return True

        for old_quote, new_quote in zip(self.current_buy_quotes, new_buy_quotes):
            old_price = old_quote["price"]
            new_price = new_quote["price"]
            old_volume = old_quote["volume"]
            new_volume = new_quote["volume"]

            if abs(new_price - old_price) > tolerance_price:
                return True

            if new_volume != old_volume:
                return True

        for old_quote, new_quote in zip(self.current_sell_quotes, new_sell_quotes):
            old_price = old_quote["price"]
            new_price = new_quote["price"]
            old_volume = old_quote["volume"]
            new_volume = new_quote["volume"]

            if abs(new_price - old_price) > tolerance_price:
                return True

            if new_volume != old_volume:
                return True

        return False

    def update_current_quotes(
        self,
        buy_quotes: list[dict],
        sell_quotes: list[dict],
    ) -> None:
        self.current_buy_quotes = [quote.copy() for quote in buy_quotes]
        self.current_sell_quotes = [quote.copy() for quote in sell_quotes]

    def clear_current_quotes(self) -> None:
        self.current_buy_quotes = []
        self.current_sell_quotes = []


class InventorySkewEngine:
    def __init__(self) -> None:
        self.last_skew_tick: int = 0
        self.last_pos_ratio: float = 0.0

    def apply_skew(
        self,
        buy_quotes: list[dict],
        sell_quotes: list[dict],
        pos: float,
        max_position: float,
        price_tick: float,
        max_skew_tick: int = 3,
        snapshot: dict | None = None,
        passive: bool = True,
    ) -> tuple[list[dict], list[dict]]:
        if not buy_quotes and not sell_quotes:
            return buy_quotes, sell_quotes

        if max_position <= 0:
            return buy_quotes, sell_quotes

        if price_tick <= 0:
            return buy_quotes, sell_quotes

        if max_skew_tick <= 0:
            self.last_skew_tick = 0
            self.last_pos_ratio = 0.0
            return buy_quotes, sell_quotes

        pos_ratio = self.calculate_pos_ratio(pos, max_position)
        skew_tick = self.calculate_skew_tick(pos_ratio, max_skew_tick)

        self.last_pos_ratio = pos_ratio
        self.last_skew_tick = skew_tick

        adjusted_buy_quotes = [quote.copy() for quote in buy_quotes]
        adjusted_sell_quotes = [quote.copy() for quote in sell_quotes]

        if skew_tick > 0:
            if pos > 0:
                adjusted_buy_quotes = self.move_quotes(
                    quotes=adjusted_buy_quotes,
                    price_tick=price_tick,
                    skew_tick=-skew_tick,
                )
                adjusted_sell_quotes = self.move_quotes(
                    quotes=adjusted_sell_quotes,
                    price_tick=price_tick,
                    skew_tick=-skew_tick,
                )

            elif pos < 0:
                adjusted_buy_quotes = self.move_quotes(
                    quotes=adjusted_buy_quotes,
                    price_tick=price_tick,
                    skew_tick=skew_tick,
                )
                adjusted_sell_quotes = self.move_quotes(
                    quotes=adjusted_sell_quotes,
                    price_tick=price_tick,
                    skew_tick=skew_tick,
                )

        if passive and snapshot:
            adjusted_buy_quotes, adjusted_sell_quotes = self.apply_passive_limit(
                buy_quotes=adjusted_buy_quotes,
                sell_quotes=adjusted_sell_quotes,
                snapshot=snapshot,
            )

        return adjusted_buy_quotes, adjusted_sell_quotes

    def calculate_pos_ratio(
        self,
        pos: float,
        max_position: float,
    ) -> float:
        if max_position <= 0:
            return 0.0

        pos_ratio = pos / max_position

        if pos_ratio > 1:
            return 1.0

        if pos_ratio < -1:
            return -1.0

        return pos_ratio

    def calculate_skew_tick(
        self,
        pos_ratio: float,
        max_skew_tick: int,
    ) -> int:
        if max_skew_tick <= 0:
            return 0

        return round(abs(pos_ratio) * max_skew_tick)

    def move_quotes(
        self,
        quotes: list[dict],
        price_tick: float,
        skew_tick: int,
    ) -> list[dict]:
        adjusted_quotes: list[dict] = []

        for quote in quotes:
            adjusted_quote = quote.copy()
            adjusted_price = adjusted_quote["price"] + skew_tick * price_tick

            if adjusted_price <= 0:
                continue

            adjusted_quote["price"] = adjusted_price
            adjusted_quote["skew_tick"] = skew_tick

            adjusted_quotes.append(adjusted_quote)

        return adjusted_quotes

    def apply_passive_limit(
        self,
        buy_quotes: list[dict],
        sell_quotes: list[dict],
        snapshot: dict,
    ) -> tuple[list[dict], list[dict]]:
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]

        adjusted_buy_quotes: list[dict] = []
        adjusted_sell_quotes: list[dict] = []

        for quote in buy_quotes:
            adjusted_quote = quote.copy()

            if bid1 > 0:
                adjusted_quote["price"] = min(adjusted_quote["price"], bid1)

            adjusted_buy_quotes.append(adjusted_quote)

        for quote in sell_quotes:
            adjusted_quote = quote.copy()

            if ask1 > 0:
                adjusted_quote["price"] = max(adjusted_quote["price"], ask1)

            adjusted_sell_quotes.append(adjusted_quote)

        return adjusted_buy_quotes, adjusted_sell_quotes

    def get_last_skew_tick(self) -> int:
        return self.last_skew_tick

    def get_last_pos_ratio(self) -> float:
        return self.last_pos_ratio


class HedgeEngine:
    def __init__(self) -> None:
        self.last_hedge_action: str = ""
        self.last_hedge_price: float = 0.0
        self.last_hedge_volume: float = 0.0

    def check_hedge(
        self,
        pos: float,
        hedge_threshold: float,
        hedge_volume: float,
        price_tick: float,
        snapshot: dict,
        hedge_price_tick: int = 1,
    ) -> dict | None:
        if hedge_threshold <= 0:
            return None

        if hedge_volume <= 0:
            return None

        if price_tick <= 0:
            return None

        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]

        if bid1 <= 0 or ask1 <= 0 or ask1 <= bid1:
            return None

        if pos >= hedge_threshold:
            price = self.calculate_sell_close_price(
                bid1=bid1,
                price_tick=price_tick,
                hedge_price_tick=hedge_price_tick,
            )

            volume = min(abs(pos), hedge_volume)

            hedge_order = {
                "action": "SELL_CLOSE",
                "price": price,
                "volume": volume,
                "reason": "long_position_exceed_threshold",
            }

            self.update_last_hedge(hedge_order)
            return hedge_order

        if pos <= -hedge_threshold:
            price = self.calculate_buy_close_price(
                ask1=ask1,
                price_tick=price_tick,
                hedge_price_tick=hedge_price_tick,
            )

            volume = min(abs(pos), hedge_volume)

            hedge_order = {
                "action": "BUY_CLOSE",
                "price": price,
                "volume": volume,
                "reason": "short_position_exceed_threshold",
            }

            self.update_last_hedge(hedge_order)
            return hedge_order

        return None

    def calculate_sell_close_price(
        self,
        bid1: float,
        price_tick: float,
        hedge_price_tick: int = 1,
    ) -> float:
        if hedge_price_tick < 0:
            hedge_price_tick = 0

        price = bid1 - hedge_price_tick * price_tick

        if price <= 0:
            return bid1

        return price

    def calculate_buy_close_price(
        self,
        ask1: float,
        price_tick: float,
        hedge_price_tick: int = 1,
    ) -> float:
        if hedge_price_tick < 0:
            hedge_price_tick = 0

        return ask1 + hedge_price_tick * price_tick

    def update_last_hedge(self, hedge_order: dict) -> None:
        self.last_hedge_action = hedge_order["action"]
        self.last_hedge_price = hedge_order["price"]
        self.last_hedge_volume = hedge_order["volume"]

    def clear_last_hedge(self) -> None:
        self.last_hedge_action = ""
        self.last_hedge_price = 0.0
        self.last_hedge_volume = 0.0

    def get_last_hedge_action(self) -> str:
        return self.last_hedge_action

    def get_last_hedge_price(self) -> float:
        return self.last_hedge_price

    def get_last_hedge_volume(self) -> float:
        return self.last_hedge_volume

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