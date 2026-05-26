import csv
from pathlib import Path
from collections import deque
from datetime import datetime
from typing import Any
from vnpy_ctastrategy import CtaTemplate, StopOrder
from vnpy_ctastrategy import (
    TickData,
    OrderData,
    TradeData,
)
import math
class MarketDataManager:
    """行情管理模块：接收 TickData，转换成统一 snapshot"""

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
        """更新 TickData，并返回统一行情快照 snapshot"""

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
        """计算原始行情有效盘口深度"""

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
        """返回统一 snapshot"""

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
class PriceWindowManager:
    """维护最近 C 个最新价，计算窗口均价"""

    def __init__(self, window_length: int) -> None:
        self.window_length: int = max(int(window_length), 1)
        self.prices: deque[float] = deque(maxlen=self.window_length)

    def reset(self) -> None:
        """清空窗口"""
        self.prices.clear()

    def update_window_length(self, window_length: int) -> None:
        """更新窗口长度 C"""
        window_length = max(int(window_length), 1)

        if window_length == self.window_length:
            return

        old_prices = list(self.prices)[-window_length:]

        self.window_length = window_length
        self.prices = deque(old_prices, maxlen=self.window_length)

    def update(self, last_price: float) -> None:
        """
        更新最新价窗口。

        注意：
        这里接收的是 snapshot["last_price"]，
        不再直接接收 TickData。
        """
        if last_price is None:
            return

        last_price = float(last_price)

        if last_price <= 0:
            return

        self.prices.append(last_price)

    def is_ready(self) -> bool:
        """判断是否已经累计满 C 个最新价"""
        return len(self.prices) >= self.window_length

    def get_average(self) -> float:
        """计算窗口均价，不足 C 个时返回 0.0"""
        if not self.is_ready():
            return 0.0

        return sum(self.prices) / self.window_length

    def get_diff(self, last_price: float) -> float:
        """计算：窗口均价 - 最新价"""
        if not self.is_ready():
            return 0.0

        if last_price is None:
            return 0.0

        last_price = float(last_price)

        if last_price <= 0:
            return 0.0

        return self.get_average() - last_price
class OrderBookProcessor:
    """扣除本方订单，得到非本方盘口"""

    def remove_own_orders(
            self,
            snapshot: dict,
            active_orders: dict[str, OrderData],
            own_orderids: set[str] | None = None,
    ) -> dict:
        """
        从 snapshot 五档盘口中扣除本方订单。

        注意：
        这里不再直接读取 TickData。
        snapshot 已经由 self.market_data.update_tick(tick) 生成。
        """

        bid_prices = snapshot["bid_prices"].copy()
        ask_prices = snapshot["ask_prices"].copy()
        bid_volumes = snapshot["bid_volumes"].copy()
        ask_volumes = snapshot["ask_volumes"].copy()

        raw_bid_prices = bid_prices.copy()
        raw_ask_prices = ask_prices.copy()
        raw_bid_volumes = bid_volumes.copy()
        raw_ask_volumes = ask_volumes.copy()

        for vt_orderid, order in active_orders.items():
            if own_orderids is not None and vt_orderid not in own_orderids:
                continue

            if not order.is_active():
                continue

            order_price = float(order.price or 0.0)
            order_volume = float(order.volume or 0.0)
            traded_volume = float(order.traded or 0.0)
            remaining_volume = max(order_volume - traded_volume, 0.0)

            if order_price <= 0 or remaining_volume <= 0:
                continue

            direction_text = str(order.direction).lower()

            # 买单挂在买盘，从 bid volume 里扣
            if (
                    "long" in direction_text
                    or "buy" in direction_text
                    or "多" in direction_text
                    or "买" in direction_text
            ):
                self._subtract_volume_at_price(
                    prices=bid_prices,
                    volumes=bid_volumes,
                    price=order_price,
                    volume=remaining_volume,
                )

            # 卖单挂在卖盘，从 ask volume 里扣
            elif (
                    "short" in direction_text
                    or "sell" in direction_text
                    or "空" in direction_text
                    or "卖" in direction_text
            ):
                self._subtract_volume_at_price(
                    prices=ask_prices,
                    volumes=ask_volumes,
                    price=order_price,
                    volume=remaining_volume,
                )

        bid_prices, bid_volumes = self._compact_book_side(
            prices=bid_prices,
            volumes=bid_volumes,
        )

        ask_prices, ask_volumes = self._compact_book_side(
            prices=ask_prices,
            volumes=ask_volumes,
        )

        bid1 = bid_prices[0]
        ask1 = ask_prices[0]
        bid1_volume = bid_volumes[0]
        ask1_volume = ask_volumes[0]

        market_spread = 0.0
        book_volume = 0

        if (
                bid1 > 0
                and ask1 > 0
                and ask1 > bid1
                and bid1_volume > 0
                and ask1_volume > 0
        ):
            market_spread = ask1 - bid1
            book_volume = int(min(bid1_volume, ask1_volume))

        valid_depth = self._calculate_valid_depth(
            bid_prices=bid_prices,
            bid_volumes=bid_volumes,
            ask_prices=ask_prices,
            ask_volumes=ask_volumes,
        )

        return {
            "bid_prices": bid_prices,
            "ask_prices": ask_prices,
            "bid_volumes": bid_volumes,
            "ask_volumes": ask_volumes,

            "bid1": bid1,
            "ask1": ask1,
            "bid1_volume": bid1_volume,
            "ask1_volume": ask1_volume,

            "market_spread": market_spread,
            "book_volume": book_volume,
            "valid_depth": valid_depth,

            "raw_bid_prices": raw_bid_prices,
            "raw_ask_prices": raw_ask_prices,
            "raw_bid_volumes": raw_bid_volumes,
            "raw_ask_volumes": raw_ask_volumes,
        }

    def _subtract_volume_at_price(
            self,
            prices: list[float],
            volumes: list[float],
            price: float,
            volume: float,
    ) -> None:
        """在指定价格档位扣除本方挂单量"""
        for i in range(len(prices)):
            if prices[i] == price:
                volumes[i] = max(volumes[i] - volume, 0.0)
                return

    def _compact_book_side(
            self,
            prices: list[float],
            volumes: list[float],
    ) -> tuple[list[float], list[float]]:
        """
        删除扣除后 volume <= 0 的档位，并向前补位。
        最终仍然返回 5 档。
        """
        valid_prices: list[float] = []
        valid_volumes: list[float] = []

        for price, volume in zip(prices, volumes):
            if price > 0 and volume > 0:
                valid_prices.append(price)
                valid_volumes.append(volume)

        while len(valid_prices) < 5:
            valid_prices.append(0.0)
            valid_volumes.append(0.0)

        return valid_prices[:5], valid_volumes[:5]

    def _calculate_valid_depth(
            self,
            bid_prices: list[float],
            bid_volumes: list[float],
            ask_prices: list[float],
            ask_volumes: list[float],
    ) -> int:
        """计算扣除本方订单后的有效深度"""
        valid_depth = 0

        for i in range(5):
            if (
                    bid_prices[i] > 0
                    and ask_prices[i] > 0
                    and bid_volumes[i] > 0
                    and ask_volumes[i] > 0
            ):
                valid_depth += 1
            else:
                break

        return valid_depth
class ScenarioSelector:
    """根据价差、盘口量和窗口均价偏离选择 1-8 档场景"""

    def __init__(
        self,
        spread_threshold: float,
        book_volume_threshold: int,
        window_diff_threshold: float,
        scenario_config: dict[int, tuple[int, int, int]],
    ) -> None:
        self.spread_threshold = float(spread_threshold)
        self.book_volume_threshold = int(book_volume_threshold)
        self.window_diff_threshold = float(window_diff_threshold)

        # scenario_id -> (quote_level, price_offset_tick, quote_volume)
        self.scenario_config = scenario_config

    def update_thresholds(
        self,
        spread_threshold: float,
        book_volume_threshold: int,
        window_diff_threshold: float,
    ) -> None:
        """更新场景判断阈值"""
        self.spread_threshold = float(spread_threshold)
        self.book_volume_threshold = int(book_volume_threshold)
        self.window_diff_threshold = float(window_diff_threshold)

    def update_scenario_config(
        self,
        scenario_config: dict[int, tuple[int, int, int]],
    ) -> None:
        """
        更新 8 档场景配置。

        scenario_id -> (quote_level, price_offset_tick, quote_volume)

        quote_level:
            参考非本方盘口第几档报价。

        price_offset_tick:
            在参考盘口档位基础上偏移多少个 tick。

        quote_volume:
            每次挂单数量。
        """
        self.scenario_config = scenario_config

    def select(
        self,
        spread: float,
        book_volume: int,
        abs_window_diff: float,
    ) -> int:
        """
        根据市场状态选择 1-8 档场景。

        判断维度：
        1. spread:
            非本方盘口买卖价差。

        2. book_volume:
            非本方盘口量，通常取 min(买一量, 卖一量)。

        3. abs_window_diff:
            |窗口均价 - 最新成交价|，用于衡量短期价格偏离程度。
        """

        spread_threshold = self.spread_threshold
        book_volume_threshold = self.book_volume_threshold
        window_diff_threshold = self.window_diff_threshold

        # 价差较小 + 盘口量充足 + 价格稳定
        if (
            spread < spread_threshold
            and book_volume >= book_volume_threshold
            and abs_window_diff <= window_diff_threshold
        ):
            return 1

        # 价差较小 + 盘口量充足 + 价格偏离较大
        if (
            spread < spread_threshold
            and book_volume >= book_volume_threshold
            and abs_window_diff > window_diff_threshold
        ):
            return 2

        # 价差较小 + 盘口量不足 + 价格稳定
        if (
            spread < spread_threshold
            and book_volume < book_volume_threshold
            and abs_window_diff <= window_diff_threshold
        ):
            return 3

        # 价差较小 + 盘口量不足 + 价格偏离较大
        if (
            spread < spread_threshold
            and book_volume < book_volume_threshold
            and abs_window_diff > window_diff_threshold
        ):
            return 4

        # 价差较大 + 盘口量不足 + 价格稳定
        if (
            spread >= spread_threshold
            and book_volume < book_volume_threshold
            and abs_window_diff <= window_diff_threshold
        ):
            return 5

        # 价差较大 + 盘口量不足 + 价格偏离较大
        if (
            spread >= spread_threshold
            and book_volume < book_volume_threshold
            and abs_window_diff > window_diff_threshold
        ):
            return 6

        # 价差较大 + 盘口量充足 + 价格稳定
        if (
            spread >= spread_threshold
            and book_volume >= book_volume_threshold
            and abs_window_diff <= window_diff_threshold
        ):
            return 7

        # 价差较大 + 盘口量充足 + 价格偏离较大
        if (
            spread >= spread_threshold
            and book_volume >= book_volume_threshold
            and abs_window_diff > window_diff_threshold
        ):
            return 8

        return 0

    def get_config(self, scenario_id: int) -> tuple[int, int, int]:
        """
        返回当前场景对应的报价配置。

        返回：
            quote_level:
                参考非本方盘口第几档。

            price_offset_tick:
                报价偏移 tick 数。

            quote_volume:
                挂单数量。
        """
        return self.scenario_config.get(scenario_id, (0, 0, 0))
class QuoteGenerator:
    """报价生成模块：根据场景配置生成目标买卖报价"""

    def __init__(self) -> None:
        self.last_scenario_id: int = 0

        self.last_quote_level: int = 0
        self.last_price_offset_tick: int = 0
        self.last_quote_volume: int = 0

        self.last_buy_price: float = 0.0
        self.last_sell_price: float = 0.0
        self.last_buy_volume: int = 0
        self.last_sell_volume: int = 0

    def generate_quotes(
        self,
        scenario_id: int,
        quote_level: int,
        price_offset_tick: int,
        quote_volume: int,
        other_book: dict,
        price_tick: float,
    ) -> tuple[dict | None, dict | None]:
        """
        根据当前场景配置生成买卖目标报价。

        quote_level:
            参考非本方盘口第几档。
            例如 quote_level = 1，表示参考买一/卖一；
            quote_level = 2，表示参考买二/卖二。

        price_offset_tick:
            在参考盘口价格基础上偏移多少个 tick。
            买单向下偏移，卖单向上偏移。

        quote_volume:
            每次挂单数量。

        买单价格：
            非本方买 quote_level 档价格 - price_offset_tick * price_tick

        卖单价格：
            非本方卖 quote_level 档价格 + price_offset_tick * price_tick
        """

        if scenario_id <= 0:
            return None, None

        if quote_level <= 0:
            return None, None

        if price_offset_tick < 0:
            return None, None

        if quote_volume <= 0:
            return None, None

        if price_tick <= 0:
            return None, None

        bid_prices = other_book.get("bid_prices", [])
        ask_prices = other_book.get("ask_prices", [])
        bid_volumes = other_book.get("bid_volumes", [])
        ask_volumes = other_book.get("ask_volumes", [])

        if len(bid_prices) < quote_level or len(ask_prices) < quote_level:
            return None, None

        buy_base_price = float(bid_prices[quote_level - 1] or 0.0)
        sell_base_price = float(ask_prices[quote_level - 1] or 0.0)

        buy_base_volume = (
            float(bid_volumes[quote_level - 1] or 0.0)
            if len(bid_volumes) >= quote_level
            else 0.0
        )

        sell_base_volume = (
            float(ask_volumes[quote_level - 1] or 0.0)
            if len(ask_volumes) >= quote_level
            else 0.0
        )

        if buy_base_price <= 0 or sell_base_price <= 0:
            return None, None

        if buy_base_volume <= 0 or sell_base_volume <= 0:
            return None, None

        raw_buy_price = buy_base_price - price_offset_tick * price_tick
        raw_sell_price = sell_base_price + price_offset_tick * price_tick

        buy_price = self.floor_to_tick(
            price=raw_buy_price,
            price_tick=price_tick,
        )

        sell_price = self.ceil_to_tick(
            price=raw_sell_price,
            price_tick=price_tick,
        )

        if buy_price <= 0 or sell_price <= 0:
            return None, None

        if sell_price <= buy_price:
            return None, None

        buy_quote = {
            "side": "buy",
            "scenario_id": scenario_id,

            "quote_level": quote_level,
            "price_offset_tick": price_offset_tick,
            "quote_volume": quote_volume,

            "level": quote_level,
            "base_price": buy_base_price,
            "base_volume": buy_base_volume,

            "price": buy_price,
            "volume": quote_volume,
        }

        sell_quote = {
            "side": "sell",
            "scenario_id": scenario_id,

            "quote_level": quote_level,
            "price_offset_tick": price_offset_tick,
            "quote_volume": quote_volume,

            "level": quote_level,
            "base_price": sell_base_price,
            "base_volume": sell_base_volume,

            "price": sell_price,
            "volume": quote_volume,
        }

        self.update_last_quotes(
            scenario_id=scenario_id,
            quote_level=quote_level,
            price_offset_tick=price_offset_tick,
            quote_volume=quote_volume,
            buy_quote=buy_quote,
            sell_quote=sell_quote,
        )

        return buy_quote, sell_quote

    def update_last_quotes(
        self,
        scenario_id: int,
        quote_level: int,
        price_offset_tick: int,
        quote_volume: int,
        buy_quote: dict,
        sell_quote: dict,
    ) -> None:
        """记录最近一次生成的目标报价"""

        self.last_scenario_id = scenario_id

        self.last_quote_level = quote_level
        self.last_price_offset_tick = price_offset_tick
        self.last_quote_volume = quote_volume

        self.last_buy_price = float(buy_quote["price"])
        self.last_sell_price = float(sell_quote["price"])
        self.last_buy_volume = int(buy_quote["volume"])
        self.last_sell_volume = int(sell_quote["volume"])

    def clear_last_quotes(self) -> None:
        """清空最近一次目标报价记录"""

        self.last_scenario_id = 0

        self.last_quote_level = 0
        self.last_price_offset_tick = 0
        self.last_quote_volume = 0

        self.last_buy_price = 0.0
        self.last_sell_price = 0.0
        self.last_buy_volume = 0
        self.last_sell_volume = 0

    def floor_to_tick(self, price: float, price_tick: float) -> float:
        """买单价格向下取合法 tick"""

        if price_tick <= 0:
            return price

        return math.floor(price / price_tick) * price_tick

    def ceil_to_tick(self, price: float, price_tick: float) -> float:
        """卖单价格向上取合法 tick"""

        if price_tick <= 0:
            return price

        return math.ceil(price / price_tick) * price_tick



    def get_last_quote_snapshot(self) -> dict:
        """返回最近一次目标报价快照，方便主策略更新 variables"""

        return {
            "scenario_id": self.last_scenario_id,

            "quote_level": self.last_quote_level,
            "price_offset_tick": self.last_price_offset_tick,
            "quote_volume": self.last_quote_volume,

            "buy_price": self.last_buy_price,
            "sell_price": self.last_sell_price,
            "buy_volume": self.last_buy_volume,
            "sell_volume": self.last_sell_volume,
        }
class RiskManager:
    """报价风控模块：只做硬性安全过滤，不参与场景分档"""

    def check_other_book_valid(self, other_book: dict) -> tuple[bool, str]:
        """
        检查扣除本方订单后的非本方盘口是否合法。
        这里只判断能不能报价，不判断盘口强弱。
        """

        if not other_book:
            return False, "other_book_empty"

        bid1 = float(other_book.get("bid1", 0.0) or 0.0)
        ask1 = float(other_book.get("ask1", 0.0) or 0.0)
        bid1_volume = float(other_book.get("bid1_volume", 0.0) or 0.0)
        ask1_volume = float(other_book.get("ask1_volume", 0.0) or 0.0)

        if bid1 <= 0:
            return False, "bid1_invalid"

        if ask1 <= 0:
            return False, "ask1_invalid"

        if ask1 <= bid1:
            return False, "ask1_not_greater_than_bid1"

        if bid1_volume <= 0:
            return False, "bid1_volume_invalid"

        if ask1_volume <= 0:
            return False, "ask1_volume_invalid"

        return True, "other_book_valid"

    def check_depth(
        self,
        other_book: dict,
        min_depth: int = 1,
    ) -> tuple[bool, str]:
        """
        检查有效盘口深度。
        这是硬性底线，不参与 A/B/D 场景判断。
        """

        valid_depth = int(other_book.get("valid_depth", 0) or 0)

        if min_depth <= 0:
            min_depth = 1

        if valid_depth < min_depth:
            return False, f"depth_not_enough: {valid_depth}/{min_depth}"

        return True, "depth_pass"

    def check_quote_valid(
        self,
        quote: dict | None,
        side: str,
    ) -> tuple[bool, str]:
        """
        检查单边目标报价是否合法。
        单边 quote 为空不一定是错误，可能是被前面逻辑过滤掉。
        """

        if quote is None:
            return False, f"{side}_quote_none"

        price = float(quote.get("price", 0.0) or 0.0)
        volume = float(quote.get("volume", 0.0) or 0.0)

        if price <= 0:
            return False, f"{side}_quote_price_invalid"

        if volume <= 0:
            return False, f"{side}_quote_volume_invalid"

        return True, f"{side}_quote_valid"

    def check_two_sided_quotes(
        self,
        buy_quote: dict | None,
        sell_quote: dict | None,
    ) -> tuple[bool, str]:
        """
        检查买卖报价是否存在倒挂。
        如果只有单边报价，不在这里拦截；是否允许单边交给主策略决定。
        """

        if buy_quote is None or sell_quote is None:
            return True, "single_side_or_empty_skip_cross_check"

        buy_price = float(buy_quote.get("price", 0.0) or 0.0)
        sell_price = float(sell_quote.get("price", 0.0) or 0.0)

        if buy_price <= 0 or sell_price <= 0:
            return False, "quote_price_invalid"

        if sell_price <= buy_price:
            return False, f"quote_crossed: buy={buy_price}, sell={sell_price}"

        return True, "two_sided_quotes_pass"

    def apply_simple_price_cage(
        self,
        buy_quote: dict | None,
        sell_quote: dict | None,
        snapshot: dict,
        enabled: bool,
        price_cage_offset: float,
    ) -> tuple[dict | None, dict | None, dict]:
        """
        简化价格笼子：
        以 last_price 为中心，只允许报价落在：
        [last_price - price_cage_offset, last_price + price_cage_offset]
        """

        result = {
            "price_cage_enabled": enabled,
            "price_cage_lower": 0.0,
            "price_cage_upper": 0.0,
            "buy_price_cage_pass": True,
            "sell_price_cage_pass": True,
            "buy_price_cage_reason": "price_cage_disabled",
            "sell_price_cage_reason": "price_cage_disabled",
        }

        if not enabled:
            return buy_quote, sell_quote, result

        last_price = float(snapshot.get("last_price", 0.0) or 0.0)

        if last_price <= 0:
            result["buy_price_cage_pass"] = False
            result["sell_price_cage_pass"] = False
            result["buy_price_cage_reason"] = "last_price_invalid"
            result["sell_price_cage_reason"] = "last_price_invalid"
            return None, None, result

        price_cage_offset = abs(float(price_cage_offset or 0.0))

        lower = last_price - price_cage_offset
        upper = last_price + price_cage_offset

        result["price_cage_lower"] = lower
        result["price_cage_upper"] = upper

        filtered_buy_quote = buy_quote
        filtered_sell_quote = sell_quote

        if buy_quote is not None:
            buy_price = float(buy_quote.get("price", 0.0) or 0.0)

            if not (lower <= buy_price <= upper):
                filtered_buy_quote = None
                result["buy_price_cage_pass"] = False
                result["buy_price_cage_reason"] = (
                    f"buy_price_out_of_cage: price={buy_price}, range=[{lower}, {upper}]"
                )
            else:
                result["buy_price_cage_reason"] = "buy_price_cage_pass"

        if sell_quote is not None:
            sell_price = float(sell_quote.get("price", 0.0) or 0.0)

            if not (lower <= sell_price <= upper):
                filtered_sell_quote = None
                result["sell_price_cage_pass"] = False
                result["sell_price_cage_reason"] = (
                    f"sell_price_out_of_cage: price={sell_price}, range=[{lower}, {upper}]"
                )
            else:
                result["sell_price_cage_reason"] = "sell_price_cage_pass"

        return filtered_buy_quote, filtered_sell_quote, result

    def filter_quotes(
        self,
        buy_quote: dict | None,
        sell_quote: dict | None,
        snapshot: dict,
        other_book: dict,
        min_depth: int,
        price_cage_enabled: bool,
        price_cage_offset: float,
        require_two_sided_quote: bool = True,
    ) -> tuple[dict | None, dict | None, dict]:
        """
        报价前总风控。

        只做硬性安全过滤：
        1. 非本方盘口是否合法
        2. 有效深度是否满足底线
        3. 目标报价是否合法
        4. 买卖报价是否倒挂
        5. 是否通过价格笼子
        6. 是否要求双边报价

        注意：
        不检查 spread_threshold；
        不检查 book_volume_threshold；
        这两个交给 ScenarioSelector 做分档决策。
        """

        risk_result = {
            "risk_pass": True,
            "risk_reason": "risk_pass",

            "other_book_pass": True,
            "other_book_reason": "",

            "depth_pass": True,
            "depth_reason": "",

            "buy_quote_pass": True,
            "buy_quote_reason": "",

            "sell_quote_pass": True,
            "sell_quote_reason": "",

            "cross_check_pass": True,
            "cross_check_reason": "",

            "price_cage_result": {},
        }

        # 1. 非本方盘口合法性检查
        passed, reason = self.check_other_book_valid(other_book)
        risk_result["other_book_pass"] = passed
        risk_result["other_book_reason"] = reason

        if not passed:
            risk_result["risk_pass"] = False
            risk_result["risk_reason"] = reason
            return None, None, risk_result

        # 2. 有效深度检查
        passed, reason = self.check_depth(
            other_book=other_book,
            min_depth=min_depth,
        )
        risk_result["depth_pass"] = passed
        risk_result["depth_reason"] = reason

        if not passed:
            risk_result["risk_pass"] = False
            risk_result["risk_reason"] = reason
            return None, None, risk_result

        # 3. 单边报价合法性检查
        buy_pass, buy_reason = self.check_quote_valid(
            quote=buy_quote,
            side="buy",
        )
        sell_pass, sell_reason = self.check_quote_valid(
            quote=sell_quote,
            side="sell",
        )

        risk_result["buy_quote_pass"] = buy_pass
        risk_result["buy_quote_reason"] = buy_reason
        risk_result["sell_quote_pass"] = sell_pass
        risk_result["sell_quote_reason"] = sell_reason

        filtered_buy_quote = buy_quote if buy_pass else None
        filtered_sell_quote = sell_quote if sell_pass else None

        # 4. 是否要求双边报价
        if require_two_sided_quote:
            if filtered_buy_quote is None or filtered_sell_quote is None:
                risk_result["risk_pass"] = False
                risk_result["risk_reason"] = "two_sided_quote_required_but_missing"
                return None, None, risk_result

        else:
            if filtered_buy_quote is None and filtered_sell_quote is None:
                risk_result["risk_pass"] = False
                risk_result["risk_reason"] = "both_quotes_invalid"
                return None, None, risk_result

        # 5. 买卖报价倒挂检查
        passed, reason = self.check_two_sided_quotes(
            buy_quote=filtered_buy_quote,
            sell_quote=filtered_sell_quote,
        )
        risk_result["cross_check_pass"] = passed
        risk_result["cross_check_reason"] = reason

        if not passed:
            risk_result["risk_pass"] = False
            risk_result["risk_reason"] = reason
            return None, None, risk_result

        # 6. 价格笼子过滤
        filtered_buy_quote, filtered_sell_quote, cage_result = self.apply_simple_price_cage(
            buy_quote=filtered_buy_quote,
            sell_quote=filtered_sell_quote,
            snapshot=snapshot,
            enabled=price_cage_enabled,
            price_cage_offset=price_cage_offset,
        )

        risk_result["price_cage_result"] = cage_result

        if require_two_sided_quote:
            if filtered_buy_quote is None or filtered_sell_quote is None:
                risk_result["risk_pass"] = False
                risk_result["risk_reason"] = "two_sided_quote_filtered_by_price_cage"
                return None, None, risk_result

        else:
            if filtered_buy_quote is None and filtered_sell_quote is None:
                risk_result["risk_pass"] = False
                risk_result["risk_reason"] = "both_quotes_filtered_by_price_cage"
                return None, None, risk_result

        risk_result["risk_pass"] = True
        risk_result["risk_reason"] = "risk_pass"

        return filtered_buy_quote, filtered_sell_quote, risk_result

class OrderManager:
    """订单管理模块：做市订单撤单、补单、重报、容忍度判断"""

    def __init__(self) -> None:
        self.current_scenario_id: int = 0
        # 记录订单类型，防止订单结束后从 mm_orderids 移除，on_trade 无法识别原始订单类型
        # key: vt_orderid
        # value: "MM" / "HEDGE" / "OTHER"
        self.order_type_map: dict[str, str] = {}
    def build_sync_plan(
        self,
        buy_quote: dict | None,
        sell_quote: dict | None,
        scenario_id: int,
        active_orders: dict,
        mm_orderids: set[str],
        quote_tolerance: float,
    ) -> dict:
        """
        根据目标报价和当前做市订单，生成执行计划。

        返回：
        {
            "cancel_orderids": set(),
            "send_buy_quote": dict | None,
            "send_sell_quote": dict | None,
            "reason": str,
            "scenario_changed": bool,
        }
        """

        plan = {
            "cancel_orderids": set(),
            "send_buy_quote": None,
            "send_sell_quote": None,
            "reason": "",
            "scenario_changed": False,
        }

        current_buy_orders, current_sell_orders = self.get_active_mm_orders(
            active_orders=active_orders,
            mm_orderids=mm_orderids,
        )

        # 1. 当前没有任何做市订单，直接发目标买卖单
        if not current_buy_orders and not current_sell_orders:
            plan["send_buy_quote"] = buy_quote
            plan["send_sell_quote"] = sell_quote
            plan["reason"] = "no_active_mm_orders_send_new"
            self.current_scenario_id = scenario_id
            return plan

        # 2. 场景换挡：撤掉全部做市单，后面重报
        if self.current_scenario_id and scenario_id != self.current_scenario_id:
            plan["cancel_orderids"] = set(mm_orderids)
            plan["send_buy_quote"] = buy_quote
            plan["send_sell_quote"] = sell_quote
            plan["reason"] = "scenario_changed_cancel_and_resend"
            plan["scenario_changed"] = True
            self.current_scenario_id = scenario_id
            return plan

        # 3. 场景没变，分别同步买单和卖单
        buy_plan = self.check_one_side_order(
            target_quote=buy_quote,
            current_orders=current_buy_orders,
            quote_tolerance=quote_tolerance,
        )

        sell_plan = self.check_one_side_order(
            target_quote=sell_quote,
            current_orders=current_sell_orders,
            quote_tolerance=quote_tolerance,
        )

        plan["cancel_orderids"].update(buy_plan["cancel_orderids"])
        plan["cancel_orderids"].update(sell_plan["cancel_orderids"])

        plan["send_buy_quote"] = buy_plan["send_quote"]
        plan["send_sell_quote"] = sell_plan["send_quote"]

        plan["reason"] = f"buy={buy_plan['reason']}; sell={sell_plan['reason']}"
        self.current_scenario_id = scenario_id

        return plan

    def register_order_type(self, vt_orderids: list[str], order_type: str) -> None:
        """
        注册订单类型。

        order_type:
            MM：普通做市单
            HEDGE：对冲单
        """
        for vt_orderid in vt_orderids:
            self.order_type_map[vt_orderid] = order_type

    def get_order_type(self, vt_orderid: str) -> str:
        """
        获取订单类型。
        不再只依赖 mm_orderids / hedge_orderids，避免订单集合清理后识别失败。
        """
        return self.order_type_map.get(vt_orderid, "OTHER")


    def get_active_mm_orders(
        self,
        active_orders: dict,
        mm_orderids: set[str],
    ) -> tuple[list, list]:
        """
        获取当前活跃做市买单和卖单。
        """

        buy_orders = []
        sell_orders = []

        for vt_orderid in mm_orderids:
            order = active_orders.get(vt_orderid)

            if order is None:
                continue

            if not order.is_active():
                continue

            direction_text = str(order.direction).lower()

            if (
                "long" in direction_text
                or "buy" in direction_text
                or "多" in direction_text
                or "买" in direction_text
            ):
                buy_orders.append(order)

            elif (
                "short" in direction_text
                or "sell" in direction_text
                or "空" in direction_text
                or "卖" in direction_text
            ):
                sell_orders.append(order)

        return buy_orders, sell_orders

    def check_one_side_order(
        self,
        target_quote: dict | None,
        current_orders: list,
        quote_tolerance: float,
    ) -> dict:
        """
        检查单边订单是否需要撤单、补单、重报。

        逻辑：
        1. 目标报价为空：撤掉这一边已有订单
        2. 当前没有订单：发送目标报价
        3. 当前订单价格与目标价格差 <= H：不撤不报，但如果数量不足则补单
        4. 当前订单价格与目标价格差 > H：撤旧单，发送新单
        """

        result = {
            "cancel_orderids": set(),
            "send_quote": None,
            "reason": "",
        }

        # 目标报价为空，说明这一边不允许挂单
        if target_quote is None:
            for order in current_orders:
                result["cancel_orderids"].add(order.vt_orderid)

            result["reason"] = "target_quote_none_cancel_side"
            return result

        target_price = float(target_quote["price"])
        target_volume = float(target_quote["volume"])

        if target_price <= 0 or target_volume <= 0:
            for order in current_orders:
                result["cancel_orderids"].add(order.vt_orderid)

            result["reason"] = "target_quote_invalid_cancel_side"
            return result

        # 当前这一边没有订单，直接发
        if not current_orders:
            result["send_quote"] = target_quote
            result["reason"] = "no_current_order_send_new"
            return result

        # 这里先按一边只保留一个目标订单处理
        current_order = current_orders[0]

        current_price = float(current_order.price or 0.0)
        current_volume = float(current_order.volume or 0.0)
        traded_volume = float(current_order.traded or 0.0)
        remaining_volume = max(current_volume - traded_volume, 0.0)

        price_diff = abs(target_price - current_price)

        # 价格超过容忍度：撤旧单，发新单
        if price_diff > quote_tolerance:
            for order in current_orders:
                result["cancel_orderids"].add(order.vt_orderid)

            result["send_quote"] = target_quote
            result["reason"] = "price_diff_exceed_tolerance_cancel_and_resend"
            return result

        # 价格在容忍度内：不撤单
        # 但如果因为被动成交导致剩余数量不足，则补挂差额
        missing_volume = target_volume - remaining_volume

        if missing_volume > 0:
            makeup_quote = target_quote.copy()
            makeup_quote["volume"] = missing_volume

            result["send_quote"] = makeup_quote
            result["reason"] = "price_within_tolerance_makeup_volume"
            return result

        # 价格在容忍度内，数量也够，不动
        result["reason"] = "price_within_tolerance_keep_order"
        return result

    def get_own_best_quote(
            self,
            active_orders: dict,
            mm_orderids: set[str],
    ) -> dict:
        """
        获取本方做市订单的最优买价、最优卖价、对应数量。
        用于计算本方买卖价差和 report 指标。
        """

        best_bid_price = 0.0
        best_bid_volume = 0.0

        best_ask_price = 0.0
        best_ask_volume = 0.0

        for vt_orderid in mm_orderids:
            order = active_orders.get(vt_orderid)

            if order is None:
                continue

            if not order.is_active():
                continue

            price = float(order.price or 0.0)
            volume = float(order.volume or 0.0)
            traded = float(order.traded or 0.0)
            remaining = max(volume - traded, 0.0)

            if price <= 0 or remaining <= 0:
                continue

            direction_text = str(order.direction).lower()

            # 本方买单：取最高买价
            if (
                    "long" in direction_text
                    or "buy" in direction_text
                    or "多" in direction_text
                    or "买" in direction_text
            ):
                if best_bid_price <= 0 or price > best_bid_price:
                    best_bid_price = price
                    best_bid_volume = remaining

            # 本方卖单：取最低卖价
            elif (
                    "short" in direction_text
                    or "sell" in direction_text
                    or "空" in direction_text
                    or "卖" in direction_text
            ):
                if best_ask_price <= 0 or price < best_ask_price:
                    best_ask_price = price
                    best_ask_volume = remaining

        own_spread = 0.0

        if (
                best_bid_price > 0
                and best_ask_price > 0
                and best_ask_price > best_bid_price
        ):
            own_spread = best_ask_price - best_bid_price

        return {
            "own_best_bid_price": best_bid_price,
            "own_best_ask_price": best_ask_price,
            "own_best_bid_volume": best_bid_volume,
            "own_best_ask_volume": best_ask_volume,
            "own_spread": own_spread,
        }

    def clear(self) -> None:
        """清空当前场景状态和订单类型记录"""
        self.current_scenario_id = 0
        self.order_type_map.clear()
class HedgeManager:
    """逐笔对冲模块：普通做市成交一笔，对冲一笔"""

    def __init__(self) -> None:
        self.last_hedge_action: str = ""
        self.last_hedge_price: float = 0.0
        self.last_hedge_volume: int = 0

    def generate_one_trade_hedge_order(
        self,
        trade: TradeData,
        snapshot: dict,
        price_tick: float,
        hedge_offset_tick: int,
    ) -> dict | None:
        """
        根据一笔普通做市成交，生成一笔反方向对冲订单。

        逻辑：
        1. 做市买成交 -> 发卖出对冲
        2. 做市卖成交 -> 发买入对冲
        """

        if not snapshot:
            return None

        if price_tick <= 0:
            return None

        volume = int(trade.volume or 0)

        if volume <= 0:
            return None

        bid1 = float(snapshot.get("bid1", 0.0) or 0.0)
        ask1 = float(snapshot.get("ask1", 0.0) or 0.0)

        if bid1 <= 0 or ask1 <= 0 or ask1 <= bid1:
            return None

        if hedge_offset_tick < 0:
            hedge_offset_tick = 0

        direction_text = str(trade.direction).lower()

        # 做市买成交 -> 卖出对冲
        if (
            "long" in direction_text
            or "buy" in direction_text
            or "多" in direction_text
            or "买" in direction_text
        ):
            price = bid1 - hedge_offset_tick * price_tick

            if price <= 0:
                return None

            hedge_order = {
                "direction": "sell",
                "price": price,
                "volume": volume,
                "action": "sell_hedge",
                "reason": "one_trade_hedge_after_mm_buy",
            }

            self.update_last_hedge(hedge_order)
            return hedge_order

        # 做市卖成交 -> 买入对冲
        if (
            "short" in direction_text
            or "sell" in direction_text
            or "空" in direction_text
            or "卖" in direction_text
        ):
            price = ask1 + hedge_offset_tick * price_tick

            if price <= 0:
                return None

            hedge_order = {
                "direction": "buy",
                "price": price,
                "volume": volume,
                "action": "buy_hedge",
                "reason": "one_trade_hedge_after_mm_sell",
            }

            self.update_last_hedge(hedge_order)
            return hedge_order

        return None

    def update_last_hedge(self, hedge_order: dict) -> None:
        """更新最近一次对冲记录"""
        self.last_hedge_action = hedge_order["action"]
        self.last_hedge_price = float(hedge_order["price"])
        self.last_hedge_volume = int(hedge_order["volume"])

    def clear_last_hedge(self) -> None:
        """清空最近一次对冲记录"""
        self.last_hedge_action = ""
        self.last_hedge_price = 0.0
        self.last_hedge_volume = 0

    def get_last_hedge_snapshot(self) -> dict:
        """返回最近一次对冲状态"""
        return {
            "last_hedge_action": self.last_hedge_action,
            "last_hedge_price": self.last_hedge_price,
            "last_hedge_volume": self.last_hedge_volume,
        }
class ReportManager:
    """
    Summary 统计模块。

    只统计 4 个核心指标：
    1. 最优平均报价差
    2. 平均有效报价深度（双边手）
    3. 平均有效报价时长（小时）
    4. 成交量
    """

    def __init__(self) -> None:
        self.reset()

    def record_quote(
            self,
            current_datetime: datetime,
            buy_quote: dict | None,
            sell_quote: dict | None,
    ) -> None:
        """
        记录一次 tick 下的目标报价状态。

        为了和策略1统一，这里统计的是：
        策略生成并通过风控后的目标报价，
        而不是 active_orders 里真实活跃的订单。
        """

        has_two_sided_quote = (
                buy_quote is not None
                and sell_quote is not None
                and float(buy_quote.get("price", 0.0) or 0.0) > 0
                and float(sell_quote.get("price", 0.0) or 0.0) > 0
                and float(sell_quote.get("price", 0.0) or 0.0)
                > float(buy_quote.get("price", 0.0) or 0.0)
                and float(buy_quote.get("volume", 0.0) or 0.0) > 0
                and float(sell_quote.get("volume", 0.0) or 0.0) > 0
        )

        quote_spread = 0.0
        total_quote_volume = 0.0

        if has_two_sided_quote:
            buy_price = float(buy_quote.get("price", 0.0) or 0.0)
            sell_price = float(sell_quote.get("price", 0.0) or 0.0)

            buy_volume = float(buy_quote.get("volume", 0.0) or 0.0)
            sell_volume = float(sell_quote.get("volume", 0.0) or 0.0)

            quote_spread = sell_price - buy_price

            # 和策略1统一：平均有效报价深度 = 买方报价量 + 卖方报价量
            total_quote_volume = buy_volume + sell_volume

        duration_seconds = self._calculate_effective_duration(
            current_datetime=current_datetime,
            current_effective_quote_active=has_two_sided_quote,
        )

        self.quote_obligation_records.append(
            {
                "datetime": current_datetime,
                "has_two_sided_quote": has_two_sided_quote,
                "quote_spread": quote_spread,
                "total_quote_volume": total_quote_volume,
                "effective_quote_duration_seconds": duration_seconds,
            }
        )

    def _calculate_effective_duration(
        self,
        current_datetime: datetime,
        current_effective_quote_active: bool,
    ) -> float:
        """
        计算上一段 tick 间隔是否计入有效报价时长。

        逻辑：
        如果上一条 tick 时处于双边有效报价状态，
        则上一条 tick 到当前 tick 的时间差计入有效报价时长。

        返回：
            本次新增的有效报价秒数。
        """

        effective_duration_seconds = 0.0

        if current_datetime is None:
            return 0.0

        if self.last_quote_datetime is not None:
            delta_seconds = (
                current_datetime - self.last_quote_datetime
            ).total_seconds()

            if delta_seconds < 0:
                delta_seconds = 0.0

            # 防止午休、夜盘、跨日断档被误算成有效报价时间
            if delta_seconds > self.max_continuous_interval_seconds:
                delta_seconds = 0.0

            if self.last_effective_quote_active:
                effective_duration_seconds = delta_seconds

        self.last_quote_datetime = current_datetime
        self.last_effective_quote_active = current_effective_quote_active

        return effective_duration_seconds

    def record_trade(
        self,
        trade_volume: float,
    ) -> None:
        """
        记录成交量。

        如果你只想统计普通做市成交量，
        主策略里只在 order_type == "MM" 时调用这个函数。
        """

        volume = float(trade_volume or 0.0)

        if volume <= 0:
            return

        self.trade_records.append(
            {
                "trade_volume": volume,
            }
        )

    def write_summary_csv(
        self,
        strategy_name: str,
        folder_path: str = r"C:\Users\ultra\Documents\New project\market_maker",
    ) -> None:
        """
        导出核心做市表现汇总报告。
        """

        folder = Path(folder_path)
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{strategy_name}_summary_report.csv"
        filepath = folder / filename

        records = self.quote_obligation_records

        effective_records = [
            r for r in records
            if r.get("has_two_sided_quote")
        ]

        if effective_records:
            avg_best_quote_spread = (
                sum(float(r.get("quote_spread", 0.0) or 0.0) for r in effective_records)
                / len(effective_records)
            )

            avg_effective_quote_depth = (
                sum(float(r.get("total_quote_volume", 0.0) or 0.0) for r in effective_records)
                / len(effective_records)
            )

            daily_effective_seconds: dict[str, float] = {}

            for r in effective_records:
                dt = r.get("datetime")
                duration = float(r.get("effective_quote_duration_seconds", 0.0) or 0.0)

                if not dt:
                    continue

                trading_day = str(dt)[:10]

                if trading_day not in daily_effective_seconds:
                    daily_effective_seconds[trading_day] = 0.0

                daily_effective_seconds[trading_day] += duration

            if daily_effective_seconds:
                avg_effective_quote_duration_hours = (
                    sum(daily_effective_seconds.values())
                    / len(daily_effective_seconds)
                    / 3600
                )
            else:
                avg_effective_quote_duration_hours = 0.0

        else:
            avg_best_quote_spread = 0.0
            avg_effective_quote_depth = 0.0
            avg_effective_quote_duration_hours = 0.0

        total_trade_volume = sum(
            float(r.get("trade_volume", 0.0) or 0.0)
            for r in self.trade_records
        )

        summary = {
            "席位简称": strategy_name,
            "最优平均报价差(元)": avg_best_quote_spread,
            "平均有效报价深度(双边手)": avg_effective_quote_depth,
            "平均有效报价时长(小时)": avg_effective_quote_duration_hours,
            "做市成交量": total_trade_volume,
        }

        with filepath.open(
            mode="w",
            newline="",
            encoding="utf-8-sig",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(summary.keys()),
            )
            writer.writeheader()
            writer.writerow(summary)

        print(f"核心做市表现汇总报告已导出：{filepath}")

    def reset(self) -> None:
        """
        重置 summary 统计状态。
        """

        self.quote_obligation_records: list[dict] = []
        self.trade_records: list[dict] = []

        self.last_quote_datetime: datetime | None = None
        self.last_effective_quote_active: bool = False

        # 超过这个间隔，认为中间断档，不计入有效报价时长
        self.max_continuous_interval_seconds: float = 10.0


class SgeMarketMakingStrategy2(CtaTemplate):
    """上金所做市策略：Tick 驱动 + 分档报价 + 逐笔对冲"""

    author = "Yang"

    # =========================================================
    # 1. 策略参数
    # =========================================================

    # 场景判断参数
    spread_threshold: float = 0.02
    book_volume_threshold: int = 5
    window_length: int = 10
    window_diff_threshold: float = 0.02

    # 自动生成报价配置的基础参数
    base_quote_level: int = 1
    base_offset_tick: int = 1
    base_quote_volume: int = 1

    # 订单同步容忍度
    quote_tolerance: float = 1.0

    # 风控参数
    min_depth: int = 1
    price_cage_enabled: bool = False
    price_cage_offset: float = 0.20

    # 逐笔对冲参数
    hedge_enabled: bool = True
    hedge_offset_tick: int = 1

    parameters = [
        "spread_threshold",
        "book_volume_threshold",
        "window_length",
        "window_diff_threshold",

        "base_quote_level",
        "base_offset_tick",
        "base_quote_volume",

        "quote_tolerance",

        "min_depth",
        "price_cage_enabled",
        "price_cage_offset",

        "hedge_enabled",
        "hedge_offset_tick",
    ]

    # =========================================================
    # 2. 策略变量
    # =========================================================

    price_tick: float = 0.0
    contract_size: int = 0

    last_price: float = 0.0
    bid1: float = 0.0
    ask1: float = 0.0
    bid1_volume: float = 0.0
    ask1_volume: float = 0.0

    other_bid1: float = 0.0
    other_ask1: float = 0.0
    other_bid1_volume: float = 0.0
    other_ask1_volume: float = 0.0

    market_spread: float = 0.0
    book_volume: int = 0
    valid_depth: int = 0

    window_avg: float = 0.0
    window_diff: float = 0.0

    current_scenario_id: int = 0
    current_quote_level: int = 0
    current_price_offset_tick: int = 0
    current_quote_volume: int = 0

    target_buy_price: float = 0.0
    target_sell_price: float = 0.0
    target_buy_volume: int = 0
    target_sell_volume: int = 0

    own_best_bid_price: float = 0.0
    own_best_ask_price: float = 0.0
    own_best_bid_volume: float = 0.0
    own_best_ask_volume: float = 0.0
    own_spread: float = 0.0

    active_order_count: int = 0
    mm_order_count: int = 0
    hedge_order_count: int = 0

    trade_count: int = 0

    last_hedge_action: str = ""
    last_hedge_price: float = 0.0
    last_hedge_volume: int = 0

    variables = [
        "price_tick",
        "contract_size",

        "last_price",
        "bid1",
        "ask1",
        "bid1_volume",
        "ask1_volume",

        "other_bid1",
        "other_ask1",
        "other_bid1_volume",
        "other_ask1_volume",

        "market_spread",
        "book_volume",
        "valid_depth",

        "window_avg",
        "window_diff",

        "current_scenario_id",
        "current_quote_level",
        "current_price_offset_tick",
        "current_quote_volume",

        "target_buy_price",
        "target_sell_price",
        "target_buy_volume",
        "target_sell_volume",

        "own_best_bid_price",
        "own_best_ask_price",
        "own_best_bid_volume",
        "own_best_ask_volume",
        "own_spread",

        "active_order_count",
        "mm_order_count",
        "hedge_order_count",

        "trade_count",

        "last_hedge_action",
        "last_hedge_price",
        "last_hedge_volume",
    ]

    # =========================================================
    # 3. 初始化
    # =========================================================

    def __init__(
        self,
        cta_engine,
        strategy_name: str,
        vt_symbol: str,
        setting: dict,
    ) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.market_data = MarketDataManager()

        self.price_window_manager = PriceWindowManager(
            window_length=self.window_length
        )

        self.order_book_processor = OrderBookProcessor()

        self.scenario_selector = ScenarioSelector(
            spread_threshold=self.spread_threshold,
            book_volume_threshold=self.book_volume_threshold,
            window_diff_threshold=self.window_diff_threshold,
            scenario_config=self.get_scenario_config(),
        )

        self.quote_generator = QuoteGenerator()
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()
        self.hedge_manager = HedgeManager()
        self.report_manager = ReportManager()

        self.orders: dict[str, OrderData] = {}
        self.mm_orderids: set[str] = set()
        self.hedge_orderids: set[str] = set()

        self.last_tick: TickData | None = None
        self.last_snapshot: dict | None = None

        self.tick_count: int = 0
        self.put_event_interval: int = 100

    # =========================================================
    # 4. 场景配置
    # =========================================================

    def get_scenario_config(self) -> dict[int, tuple[int, int, int]]:
        """
        自动生成 8 档场景配置。

        scenario_id -> (quote_level, price_offset_tick, quote_volume)
        """

        quote_level = self.base_quote_level
        price_offset_tick = self.base_offset_tick
        quote_volume = self.base_quote_volume

        return {
            1: (quote_level,     price_offset_tick,     quote_volume),
            2: (quote_level + 1, price_offset_tick + 1, quote_volume),
            3: (quote_level + 1, price_offset_tick + 1, quote_volume),
            4: (quote_level + 2, price_offset_tick + 2, quote_volume),

            5: (quote_level,     price_offset_tick,     quote_volume),
            6: (quote_level + 1, price_offset_tick + 1, quote_volume),
            7: (quote_level,     price_offset_tick,     quote_volume),
            8: (quote_level + 1, price_offset_tick + 1, quote_volume),
        }

    # =========================================================
    # 5. 生命周期函数
    # =========================================================

    def on_init(self) -> None:
        self.write_log("上金所做市策略初始化")
        self.put_event()

    def on_start(self) -> None:
        self.write_log("上金所做市策略启动")

        self.price_tick = self.get_pricetick()
        self.contract_size = self.get_size()

        self.orders.clear()
        self.mm_orderids.clear()
        self.hedge_orderids.clear()

        self.price_window_manager.reset()
        self.price_window_manager.update_window_length(self.window_length)

        self.scenario_selector.update_thresholds(
            spread_threshold=self.spread_threshold,
            book_volume_threshold=self.book_volume_threshold,
            window_diff_threshold=self.window_diff_threshold,
        )

        self.scenario_selector.update_scenario_config(
            self.get_scenario_config()
        )

        self.order_manager.clear()
        self.hedge_manager.clear_last_hedge()
        self.report_manager.reset()

        self.tick_count = 0

        self.put_event()

    def on_stop(self) -> None:
        self.write_log("上金所做市策略停止")

        self.cancel_market_making_orders()

        self.report_manager.write_summary_csv(
            strategy_name=self.strategy_name,
            folder_path=r"C:\Users\ultra\Documents\New project\market_maker\Extra_strategy"
        )

        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """Tick 驱动主流程"""

        self.last_tick = tick

        # 1. TickData -> snapshot
        snapshot = self.market_data.update_tick(tick)
        self.last_snapshot = snapshot

        self.last_price = snapshot["last_price"]
        self.bid1 = snapshot["bid1"]
        self.ask1 = snapshot["ask1"]
        self.bid1_volume = snapshot["bid1_volume"]
        self.ask1_volume = snapshot["ask1_volume"]

        # 2. 更新窗口价格
        self.price_window_manager.update(snapshot["last_price"])

        if not self.price_window_manager.is_ready():
            self.current_scenario_id = 0
            self.window_avg = 0.0
            self.window_diff = 0.0

            self.update_own_quote_variables()

            # 窗口没 ready，说明本 tick 没有生成有效目标报价
            self.report_manager.record_quote(
                current_datetime=snapshot["datetime"],
                buy_quote=None,
                sell_quote=None,
            )

            self.put_event_throttled()
            return

        # 3. 扣除本方订单，得到非本方盘口
        other_book = self.order_book_processor.remove_own_orders(
            snapshot=snapshot,
            active_orders=self.orders,
            own_orderids=self.mm_orderids,
        )

        self.other_bid1 = other_book["bid1"]
        self.other_ask1 = other_book["ask1"]
        self.other_bid1_volume = other_book["bid1_volume"]
        self.other_ask1_volume = other_book["ask1_volume"]

        self.market_spread = other_book["market_spread"]
        self.book_volume = other_book["book_volume"]
        self.valid_depth = other_book["valid_depth"]

        # 4. 计算窗口均价和窗口偏离
        self.window_avg = self.price_window_manager.get_average()
        self.window_diff = self.price_window_manager.get_diff(
            snapshot["last_price"]
        )

        # 5. 选择 1-8 档场景
        self.current_scenario_id = self.scenario_selector.select(
            spread=self.market_spread,
            book_volume=self.book_volume,
            abs_window_diff=abs(self.window_diff),
        )

        (
            self.current_quote_level,
            self.current_price_offset_tick,
            self.current_quote_volume,
        ) = self.scenario_selector.get_config(self.current_scenario_id)

        # 6. 生成目标买卖报价
        buy_quote, sell_quote = self.quote_generator.generate_quotes(
            scenario_id=self.current_scenario_id,
            quote_level=self.current_quote_level,
            price_offset_tick=self.current_price_offset_tick,
            quote_volume=self.current_quote_volume,
            other_book=other_book,
            price_tick=self.price_tick,
        )

        # 7. 报价前风控
        buy_quote, sell_quote, risk_result = self.risk_manager.filter_quotes(
            buy_quote=buy_quote,
            sell_quote=sell_quote,
            snapshot=snapshot,
            other_book=other_book,
            min_depth=self.min_depth,
            price_cage_enabled=self.price_cage_enabled,
            price_cage_offset=self.price_cage_offset,
            require_two_sided_quote=True,
        )

        self.target_buy_price = buy_quote["price"] if buy_quote else 0.0
        self.target_sell_price = sell_quote["price"] if sell_quote else 0.0
        self.target_buy_volume = int(buy_quote["volume"]) if buy_quote else 0
        self.target_sell_volume = int(sell_quote["volume"]) if sell_quote else 0

        # 8. 订单同步：撤单 / 补单 / 重报
        plan = self.order_manager.build_sync_plan(
            buy_quote=buy_quote,
            sell_quote=sell_quote,
            scenario_id=self.current_scenario_id,
            active_orders=self.orders,
            mm_orderids=self.mm_orderids,
            quote_tolerance=self.quote_tolerance,
        )

        self.execute_order_plan(plan)

        # 9. 更新本方报价和 summary
        self.update_order_count()
        self.update_own_quote_variables()

        self.report_manager.record_quote(
            current_datetime=snapshot["datetime"],
            buy_quote=buy_quote,
            sell_quote=sell_quote,
        )

        self.put_event_throttled()

    def on_order(self, order: OrderData) -> None:
        """订单状态更新"""

        if order.is_active():
            self.orders[order.vt_orderid] = order
        else:
            self.orders.pop(order.vt_orderid, None)
            self.mm_orderids.discard(order.vt_orderid)
            self.hedge_orderids.discard(order.vt_orderid)

        self.update_order_count()
        self.update_own_quote_variables()

        self.put_event_throttled()

    def on_trade(self, trade: TradeData) -> None:
        """成交后逐笔对冲"""

        self.trade_count += 1

        order_type = self.order_manager.get_order_type(trade.vt_orderid)

        if order_type == "MM":
            self.report_manager.record_trade(
                trade_volume=trade.volume
            )

            if self.hedge_enabled:
                self.hedge_one_trade(trade)

        self.update_order_count()
        self.update_own_quote_variables()

        self.put_event_throttled()

    def on_timer(self) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass

    # =========================================================
    # 6. VNpy 执行层：下单、撤单、对冲
    # =========================================================

    def execute_order_plan(self, plan: dict) -> None:
        """根据 OrderManager 生成的计划执行撤单和发单"""

        for vt_orderid in plan["cancel_orderids"]:
            order = self.orders.get(vt_orderid)

            if order and order.is_active():
                self.cancel_order(vt_orderid)

        if plan["send_buy_quote"]:
            quote = plan["send_buy_quote"]

            vt_orderids = self.buy(
                price=quote["price"],
                volume=quote["volume"],
            )

            self.mm_orderids.update(vt_orderids)
            self.order_manager.register_order_type(
                vt_orderids=vt_orderids,
                order_type="MM",
            )

        if plan["send_sell_quote"]:
            quote = plan["send_sell_quote"]

            vt_orderids = self.short(
                price=quote["price"],
                volume=quote["volume"],
            )

            self.mm_orderids.update(vt_orderids)
            self.order_manager.register_order_type(
                vt_orderids=vt_orderids,
                order_type="MM",
            )

    def hedge_one_trade(self, trade: TradeData) -> None:
        """普通做市单成交一笔，发送一笔反方向对冲单"""

        hedge_order = self.hedge_manager.generate_one_trade_hedge_order(
            trade=trade,
            snapshot=self.last_snapshot,
            price_tick=self.price_tick,
            hedge_offset_tick=self.hedge_offset_tick,
        )

        if not hedge_order:
            return

        if hedge_order["direction"] == "sell":
            vt_orderids = self.short(
                price=hedge_order["price"],
                volume=hedge_order["volume"],
            )

        elif hedge_order["direction"] == "buy":
            vt_orderids = self.buy(
                price=hedge_order["price"],
                volume=hedge_order["volume"],
            )

        else:
            return

        self.hedge_orderids.update(vt_orderids)
        self.order_manager.register_order_type(
            vt_orderids=vt_orderids,
            order_type="HEDGE",
        )

        hedge_snapshot = self.hedge_manager.get_last_hedge_snapshot()

        self.last_hedge_action = hedge_snapshot["last_hedge_action"]
        self.last_hedge_price = hedge_snapshot["last_hedge_price"]
        self.last_hedge_volume = hedge_snapshot["last_hedge_volume"]

    def cancel_market_making_orders(self) -> None:
        """只撤普通做市订单，不撤对冲订单"""

        for vt_orderid in list(self.mm_orderids):
            order = self.orders.get(vt_orderid)

            if order and order.is_active():
                self.cancel_order(vt_orderid)

        self.mm_orderids.clear()

    # =========================================================
    # 7. 状态更新
    # =========================================================

    def update_order_count(self) -> None:
        """更新订单数量"""

        self.active_order_count = 0
        self.mm_order_count = 0
        self.hedge_order_count = 0

        for vt_orderid, order in self.orders.items():
            if not order.is_active():
                continue

            self.active_order_count += 1

            order_type = self.order_manager.get_order_type(vt_orderid)

            if order_type == "MM":
                self.mm_order_count += 1

            elif order_type == "HEDGE":
                self.hedge_order_count += 1

    def update_own_quote_variables(self) -> None:
        """更新本方最优报价变量"""

        own_quote = self.order_manager.get_own_best_quote(
            active_orders=self.orders,
            mm_orderids=self.mm_orderids,
        )

        self.own_best_bid_price = own_quote["own_best_bid_price"]
        self.own_best_ask_price = own_quote["own_best_ask_price"]
        self.own_best_bid_volume = own_quote["own_best_bid_volume"]
        self.own_best_ask_volume = own_quote["own_best_ask_volume"]
        self.own_spread = own_quote["own_spread"]

    def put_event_throttled(self) -> None:
        """降低 GUI 刷新频率"""

        self.tick_count += 1

        if self.tick_count % self.put_event_interval == 0:
            self.put_event()

