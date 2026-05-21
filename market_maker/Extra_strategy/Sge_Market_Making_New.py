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

    def get_abs_diff(self, last_price: float) -> float:
        """计算 |窗口均价 - 最新价|"""
        return abs(self.get_diff(last_price))

    def get_count(self) -> int:
        """返回当前窗口内已有行情数量"""
        return len(self.prices)
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

    def is_one_sided(self, other_book: dict) -> bool:
        """
        判断是否为单边行情。

        扣除本方订单后，如果买一或卖一为空，
        就视为单边行情。
        """
        bid1 = other_book["bid1"]
        ask1 = other_book["ask1"]
        bid1_volume = other_book["bid1_volume"]
        ask1_volume = other_book["ask1_volume"]

        if bid1 <= 0:
            return True

        if ask1 <= 0:
            return True

        if ask1 <= bid1:
            return True

        if bid1_volume <= 0:
            return True

        if ask1_volume <= 0:
            return True

        return False

    def get_spread(self, other_book: dict) -> float:
        """返回非本方盘口买卖一档价差"""
        if self.is_one_sided(other_book):
            return 0.0

        return other_book["ask1"] - other_book["bid1"]

    def get_book_volume(self, other_book: dict) -> int:
        """返回非本方盘口量：MIN(买一量, 卖一量)"""
        if self.is_one_sided(other_book):
            return 0

        return int(min(other_book["bid1_volume"], other_book["ask1_volume"]))
class ScenarioSelector:
    """根据 A/B/D 选择 1-8 档"""

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

        # scenario_id -> (N, E, F)
        self.scenario_config = scenario_config

    def update_thresholds(
        self,
        spread_threshold: float,
        book_volume_threshold: int,
        window_diff_threshold: float,
    ) -> None:
        """更新 A/B/D 参数"""
        self.spread_threshold = float(spread_threshold)
        self.book_volume_threshold = int(book_volume_threshold)
        self.window_diff_threshold = float(window_diff_threshold)

    def update_scenario_config(
        self,
        scenario_config: dict[int, tuple[int, int, int]],
    ) -> None:
        """更新 8 档 N/E/F 配置"""
        self.scenario_config = scenario_config

    def select(
        self,
        spread: float,
        book_volume: int,
        abs_window_diff: float,
    ) -> int:
        """
        根据：
        1. spread < A or spread >= A
        2. book_volume >= B or book_volume < B
        3. abs_window_diff <= D or abs_window_diff > D
        选择 1-8 档。
        """

        A = self.spread_threshold
        B = self.book_volume_threshold
        D = self.window_diff_threshold

        if spread < A and book_volume >= B and abs_window_diff <= D:
            return 1

        if spread < A and book_volume >= B and abs_window_diff > D:
            return 2

        if spread < A and book_volume < B and abs_window_diff <= D:
            return 3

        if spread < A and book_volume < B and abs_window_diff > D:
            return 4

        if spread >= A and book_volume < B and abs_window_diff <= D:
            return 5

        if spread >= A and book_volume < B and abs_window_diff > D:
            return 6

        if spread >= A and book_volume >= B and abs_window_diff <= D:
            return 7

        if spread >= A and book_volume >= B and abs_window_diff > D:
            return 8

        return 0

    def get_config(self, scenario_id: int) -> tuple[int, int, int]:
        """
        返回当前场景对应的：
        N = 挂单档位
        E = 价格偏离 tick
        F = 挂单数量
        """
        return self.scenario_config.get(scenario_id, (0, 0, 0))

    def get_decision_snapshot(
        self,
        scenario_id: int,
        spread: float,
        book_volume: int,
        abs_window_diff: float,
    ) -> dict:
        """返回当前场景选择结果，方便主策略更新变量或写 report"""
        N, E, F = self.get_config(scenario_id)

        return {
            "scenario_id": scenario_id,
            "N": N,
            "E": E,
            "F": F,
            "spread": spread,
            "book_volume": book_volume,
            "abs_window_diff": abs_window_diff,
            "spread_threshold": self.spread_threshold,
            "book_volume_threshold": self.book_volume_threshold,
            "window_diff_threshold": self.window_diff_threshold,
        }
class QuoteGenerator:
    """报价生成模块：根据 N/E/F 生成目标买卖报价"""

    def __init__(self) -> None:
        self.last_scenario_id: int = 0
        self.last_N: int = 0
        self.last_E: int = 0
        self.last_F: int = 0

        self.last_buy_price: float = 0.0
        self.last_sell_price: float = 0.0
        self.last_buy_volume: int = 0
        self.last_sell_volume: int = 0

    def generate_quotes(
            self,
            scenario_id: int,
            N: int,
            E: int,
            F: int,
            other_book: dict,
            price_tick: float,
    ) -> tuple[dict | None, dict | None]:
        """
        根据当前场景的 N/E/F 生成买卖目标报价。

        N：挂单档位
        E：价格偏离 tick 数
        F：挂单数量

        买单价格 = 非本方买 N 档价格 - price_tick * E
        卖单价格 = 非本方卖 N 档价格 + price_tick * E
        """

        if scenario_id <= 0:
            return None, None

        if N <= 0:
            return None, None

        if E < 0:
            return None, None

        if F <= 0:
            return None, None

        if price_tick <= 0:
            return None, None

        bid_prices = other_book.get("bid_prices", [])
        ask_prices = other_book.get("ask_prices", [])
        bid_volumes = other_book.get("bid_volumes", [])
        ask_volumes = other_book.get("ask_volumes", [])

        if len(bid_prices) < N or len(ask_prices) < N:
            return None, None

        buy_base_price = float(bid_prices[N - 1] or 0.0)
        sell_base_price = float(ask_prices[N - 1] or 0.0)

        buy_base_volume = float(bid_volumes[N - 1] or 0.0) if len(bid_volumes) >= N else 0.0
        sell_base_volume = float(ask_volumes[N - 1] or 0.0) if len(ask_volumes) >= N else 0.0

        if buy_base_price <= 0 or sell_base_price <= 0:
            return None, None

        if buy_base_volume <= 0 or sell_base_volume <= 0:
            return None, None

        raw_buy_price = buy_base_price - E * price_tick
        raw_sell_price = sell_base_price + E * price_tick

        buy_price = self.floor_to_tick(raw_buy_price, price_tick)
        sell_price = self.ceil_to_tick(raw_sell_price, price_tick)

        if buy_price <= 0 or sell_price <= 0:
            return None, None

        if sell_price <= buy_price:
            return None, None

        buy_quote = {
            "side": "buy",
            "scenario_id": scenario_id,
            "N": N,
            "E": E,
            "F": F,
            "level": N,
            "base_price": buy_base_price,
            "base_volume": buy_base_volume,
            "price": buy_price,
            "volume": F,
        }

        sell_quote = {
            "side": "sell",
            "scenario_id": scenario_id,
            "N": N,
            "E": E,
            "F": F,
            "level": N,
            "base_price": sell_base_price,
            "base_volume": sell_base_volume,
            "price": sell_price,
            "volume": F,
        }

        self.update_last_quotes(
            scenario_id=scenario_id,
            N=N,
            E=E,
            F=F,
            buy_quote=buy_quote,
            sell_quote=sell_quote,
        )

        return buy_quote, sell_quote

    def update_last_quotes(
            self,
            scenario_id: int,
            N: int,
            E: int,
            F: int,
            buy_quote: dict,
            sell_quote: dict,
    ) -> None:
        """记录最近一次生成的目标报价"""

        self.last_scenario_id = scenario_id
        self.last_N = N
        self.last_E = E
        self.last_F = F

        self.last_buy_price = float(buy_quote["price"])
        self.last_sell_price = float(sell_quote["price"])
        self.last_buy_volume = int(buy_quote["volume"])
        self.last_sell_volume = int(sell_quote["volume"])

    def clear_last_quotes(self) -> None:
        """清空最近一次目标报价记录"""

        self.last_scenario_id = 0
        self.last_N = 0
        self.last_E = 0
        self.last_F = 0

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

    def round_to_tick(self, price: float, price_tick: float) -> float:
        """价格就近取合法 tick"""

        if price_tick <= 0:
            return price

        return round(price / price_tick) * price_tick

    def get_last_quote_snapshot(self) -> dict:
        """返回最近一次目标报价快照，方便主策略更新 variables"""

        return {
            "scenario_id": self.last_scenario_id,
            "N": self.last_N,
            "E": self.last_E,
            "F": self.last_F,
            "buy_price": self.last_buy_price,
            "sell_price": self.last_sell_price,
            "buy_volume": self.last_buy_volume,
            "sell_volume": self.last_sell_volume,
        }
class RiskManager:
    """风控模块：废单风控、成交风控、价格笼子"""

    # =====================
    # 1. 获取价格笼子基准价
    # =====================

    def get_base_price_by_type(self, snapshot: dict, price_type: str) -> float:
        """
        根据 price_type 从 snapshot 获取基准价。

        支持：
        lastPrice
        Bid1-Bid5
        Ask1-Ask5
        """

        if not snapshot:
            return 0.0

        if price_type == "lastPrice":
            return float(snapshot["last_price"] or 0.0)

        bid_prices = snapshot["bid_prices"]
        ask_prices = snapshot["ask_prices"]

        if price_type == "Bid1":
            return float(bid_prices[0] or 0.0)

        if price_type == "Bid2":
            return float(bid_prices[1] or 0.0)

        if price_type == "Bid3":
            return float(bid_prices[2] or 0.0)

        if price_type == "Bid4":
            return float(bid_prices[3] or 0.0)

        if price_type == "Bid5":
            return float(bid_prices[4] or 0.0)

        if price_type == "Ask1":
            return float(ask_prices[0] or 0.0)

        if price_type == "Ask2":
            return float(ask_prices[1] or 0.0)

        if price_type == "Ask3":
            return float(ask_prices[2] or 0.0)

        if price_type == "Ask4":
            return float(ask_prices[3] or 0.0)

        if price_type == "Ask5":
            return float(ask_prices[4] or 0.0)

        return 0.0

    # =====================
    # 2. 计算价格笼子上下限
    # =====================

    def calculate_price_cage_range(
        self,
        base_price: float,
        lower_offset: float,
        upper_offset: float,
        unit: str = "元",
    ) -> tuple[float, float]:
        """
        计算价格笼子范围。

        如果 unit == "元":
            lower = base_price + lower_offset
            upper = base_price + upper_offset

        如果 unit == "百分比":
            lower = base_price * (1 + lower_offset)
            upper = base_price * (1 + upper_offset)

        注意：
        百分比建议传小数形式：
        1% 传 0.01
        -1% 传 -0.01
        """

        if base_price <= 0:
            return 0.0, 0.0

        if unit == "百分比":
            lower = base_price * (1 + lower_offset)
            upper = base_price * (1 + upper_offset)
        else:
            lower = base_price + lower_offset
            upper = base_price + upper_offset

        if lower > upper:
            lower, upper = upper, lower

        return lower, upper

    # =====================
    # 3. 检查单个价格是否在价格笼子内
    # =====================

    def check_price_cage(
            self,
            price: float,
            snapshot: dict,
            enabled: bool,
            base_type: str,
            lower_offset: float,
            upper_offset: float,
            unit: str = "元",
    ) -> tuple[bool, str]:
        """
        检查委托价格是否在价格笼子内。

        返回：
        (是否通过, 原因)
        """

        if not enabled:
            return True, "price_cage_disabled"

        if price <= 0:
            return False, "order_price_invalid"

        base_price = self.get_base_price_by_type(
            snapshot=snapshot,
            price_type=base_type,
        )

        if base_price <= 0:
            return False, "base_price_invalid"

        lower, upper = self.calculate_price_cage_range(
            base_price=base_price,
            lower_offset=lower_offset,
            upper_offset=upper_offset,
            unit=unit,
        )

        if lower <= 0 or upper <= 0:
            return False, "price_cage_range_invalid"

        if price < lower:
            return False, f"price_below_cage_lower: price={price}, lower={lower}"

        if price > upper:
            return False, f"price_above_cage_upper: price={price}, upper={upper}"

        return True, "price_cage_pass"

    # =====================
    # 4. 对目标报价应用价格笼子
    # =====================

    def apply_price_cage_to_quotes(
            self,
            buy_quote: dict | None,
            sell_quote: dict | None,
            snapshot: dict,
            price_cage_unit: str,

            buy_price_cage_enabled: bool,
            buy_price_base_type: str,
            buy_price_lower_offset: float,
            buy_price_upper_offset: float,

            sell_price_cage_enabled: bool,
            sell_price_base_type: str,
            sell_price_lower_offset: float,
            sell_price_upper_offset: float,
    ) -> tuple[dict | None, dict | None, dict]:
        """
        对买卖目标报价应用价格笼子。

        如果买单不通过，只过滤买单。
        如果卖单不通过，只过滤卖单。
        如果两边都不通过，则返回 None, None。
        """

        result = {
            "buy_pass": True,
            "sell_pass": True,
            "buy_reason": "",
            "sell_reason": "",
        }

        filtered_buy_quote = buy_quote
        filtered_sell_quote = sell_quote

        if buy_quote is not None:
            buy_pass, buy_reason = self.check_price_cage(
                price=float(buy_quote["price"]),
                snapshot=snapshot,
                enabled=buy_price_cage_enabled,
                base_type=buy_price_base_type,
                lower_offset=buy_price_lower_offset,
                upper_offset=buy_price_upper_offset,
                unit=price_cage_unit,
            )

            result["buy_pass"] = buy_pass
            result["buy_reason"] = buy_reason

            if not buy_pass:
                filtered_buy_quote = None

        if sell_quote is not None:
            sell_pass, sell_reason = self.check_price_cage(
                price=float(sell_quote["price"]),
                snapshot=snapshot,
                enabled=sell_price_cage_enabled,
                base_type=sell_price_base_type,
                lower_offset=sell_price_lower_offset,
                upper_offset=sell_price_upper_offset,
                unit=price_cage_unit,
            )

            result["sell_pass"] = sell_pass
            result["sell_reason"] = sell_reason

            if not sell_pass:
                filtered_sell_quote = None

        return filtered_buy_quote, filtered_sell_quote, result

    # =====================
    # 5. 废单风控
    # =====================

    def check_reject_risk(
        self,
        enabled: bool,
        reject_count: int,
        max_reject_count: int,
    ) -> tuple[bool, str]:
        """
        检查废单次数是否超过上限。

        返回：
        (是否允许继续运行, 原因)
        """

        if not enabled:
            return True, "reject_risk_disabled"

        if max_reject_count <= 0:
            return True, "max_reject_count_invalid_ignore"

        if reject_count >= max_reject_count:
            return False, f"reject_count_exceed_limit: {reject_count}/{max_reject_count}"

        return True, "reject_risk_pass"

    # =====================
    # 6. 成交风控
    # =====================

    def check_trade_risk(
        self,
        buy_trade_risk_enabled: bool,
        buy_volume_limit: int,
        buy_amount_limit_wan: float,

        sell_trade_risk_enabled: bool,
        sell_volume_limit: int,
        sell_amount_limit_wan: float,

        net_buy_volume: int,
        net_sell_volume: int,
        net_buy_amount: float,
        net_sell_amount: float,
    ) -> tuple[bool, str]:
        """
        检查净买 / 净卖成交风控。

        成交额参数单位：
        - limit 用“万”
        - amount 内部建议用“元”
        """

        if buy_trade_risk_enabled:
            if buy_volume_limit > 0 and net_buy_volume >= buy_volume_limit:
                return False, f"net_buy_volume_exceed_limit: {net_buy_volume}/{buy_volume_limit}"

            buy_amount_limit = buy_amount_limit_wan * 10000

            if buy_amount_limit > 0 and net_buy_amount >= buy_amount_limit:
                return False, f"net_buy_amount_exceed_limit: {net_buy_amount}/{buy_amount_limit}"

        if sell_trade_risk_enabled:
            if sell_volume_limit > 0 and net_sell_volume >= sell_volume_limit:
                return False, f"net_sell_volume_exceed_limit: {net_sell_volume}/{sell_volume_limit}"

            sell_amount_limit = sell_amount_limit_wan * 10000

            if sell_amount_limit > 0 and net_sell_amount >= sell_amount_limit:
                return False, f"net_sell_amount_exceed_limit: {net_sell_amount}/{sell_amount_limit}"

        return True, "trade_risk_pass"

    # =====================
    # 7. 更新净买 / 净卖统计
    # =====================

    def calculate_net_trade_stats(
        self,
        buy_trade_volume: int,
        sell_trade_volume: int,
        buy_trade_amount: float,
        sell_trade_amount: float,
    ) -> dict:
        """
        根据累计买成交、卖成交，计算净买 / 净卖。
        """

        net_buy_volume = max(buy_trade_volume - sell_trade_volume, 0)
        net_sell_volume = max(sell_trade_volume - buy_trade_volume, 0)

        net_buy_amount = max(buy_trade_amount - sell_trade_amount, 0.0)
        net_sell_amount = max(sell_trade_amount - buy_trade_amount, 0.0)

        return {
            "net_buy_volume": net_buy_volume,
            "net_sell_volume": net_sell_volume,
            "net_buy_amount": net_buy_amount,
            "net_sell_amount": net_sell_amount,
        }
class OrderManager:
    """订单管理模块：做市订单撤单、补单、重报、容忍度判断"""

    def __init__(self) -> None:
        self.current_scenario_id: int = 0

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
        """清空当前场景状态"""
        self.current_scenario_id = 0
class HedgeManager:
    """对冲模块：净买/净卖触发对冲、对冲撤补、对冲废单"""

    def __init__(self) -> None:
        self.last_hedge_action: str = ""
        self.last_hedge_price: float = 0.0
        self.last_hedge_volume: int = 0
        self.last_hedge_reason: str = ""

        self.hedge_order_time: dict[str, datetime] = {}
        self.hedge_replace_count: dict[str, int] = {}

    # =====================
    # 1. 判断成交是否纳入对冲范围
    # =====================

    def is_trade_in_hedge_scope(
        self,
        trade: TradeData,
        hedge_scope: str,
        mm_orderids: set[str],
        manual_orderids: set[str] | None = None,
    ) -> bool:
        """
        对冲范围：
        自动：只对策略自动做市订单成交进行对冲
        自动+手动：策略自动订单 + 手工订单成交都纳入对冲
        """

        vt_orderid = trade.vt_orderid

        if hedge_scope == "自动":
            return vt_orderid in mm_orderids

        if hedge_scope == "自动+手动":
            if vt_orderid in mm_orderids:
                return True

            if manual_orderids is not None and vt_orderid in manual_orderids:
                return True

            return False

        return vt_orderid in mm_orderids

    # =====================
    # 2. 检查净买/净卖是否触发对冲
    # =====================

    def check_hedge_trigger(
        self,
        net_buy_volume: int,
        net_sell_volume: int,

        buy_hedge_enabled: bool,
        buy_hedge_net_volume: int,

        sell_hedge_enabled: bool,
        sell_hedge_net_volume: int,
    ) -> str:
        """
        返回：
        NET_BUY  ：净买入触发对冲，默认后续发卖单
        NET_SELL ：净卖出触发对冲，默认后续发买单
        ""       ：不触发
        """

        # 净买入对冲：阈值默认为 0，即 net_buy_volume > 0 就触发
        if buy_hedge_enabled:
            if buy_hedge_net_volume <= 0:
                if net_buy_volume > 0:
                    return "NET_BUY"
            else:
                if net_buy_volume >= buy_hedge_net_volume:
                    return "NET_BUY"

        # 净卖出对冲：阈值默认为 0，即 net_sell_volume > 0 就触发
        if sell_hedge_enabled:
            if sell_hedge_net_volume <= 0:
                if net_sell_volume > 0:
                    return "NET_SELL"
            else:
                if net_sell_volume >= sell_hedge_net_volume:
                    return "NET_SELL"

        return ""

    # =====================
    # 3. 根据价格类型获取对冲基准价
    # =====================

    def get_base_price_by_type(self, snapshot: dict, price_type: str) -> float:
        """
        根据 price_type 从 snapshot 获取对冲基准价。
        """

        if not snapshot:
            return 0.0

        if price_type == "lastPrice":
            return float(snapshot["last_price"] or 0.0)

        bid_prices = snapshot["bid_prices"]
        ask_prices = snapshot["ask_prices"]

        if price_type == "Bid1":
            return float(bid_prices[0] or 0.0)

        if price_type == "Bid2":
            return float(bid_prices[1] or 0.0)

        if price_type == "Bid3":
            return float(bid_prices[2] or 0.0)

        if price_type == "Bid4":
            return float(bid_prices[3] or 0.0)

        if price_type == "Bid5":
            return float(bid_prices[4] or 0.0)

        if price_type == "Ask1":
            return float(ask_prices[0] or 0.0)

        if price_type == "Ask2":
            return float(ask_prices[1] or 0.0)

        if price_type == "Ask3":
            return float(ask_prices[2] or 0.0)

        if price_type == "Ask4":
            return float(ask_prices[3] or 0.0)

        if price_type == "Ask5":
            return float(ask_prices[4] or 0.0)

        return 0.0

    # =====================
    # 4. 计算对冲价格
    # =====================

    def calculate_hedge_price(
        self,
        base_price: float,
        price_offset: float,
        price_offset_unit: str,
    ) -> float:
        """
        对冲单价格 = 基准价 + 偏移量

        偏移单位：
        元：base_price + price_offset
        百分比：base_price * (1 + price_offset)
        """

        if base_price <= 0:
            return 0.0

        if price_offset_unit == "百分比":
            return base_price * (1 + price_offset)

        return base_price + price_offset

    # =====================
    # 5. 自动开平判断
    # =====================

    def resolve_offset(
        self,
        direction: str,
        offset_mode: str,
        pos: float,
    ) -> str:
        """
        开平方向：
        开
        平
        自动

        自动逻辑：
        - 发卖单时，如果当前有多头，则优先平仓；否则开仓
        - 发买单时，如果当前有空头，则优先平仓；否则开仓
        """

        if offset_mode in ["开", "平"]:
            return offset_mode

        if direction == "卖":
            if pos > 0:
                return "平"
            return "开"

        if direction == "买":
            if pos < 0:
                return "平"
            return "开"

        return "自动"

    # =====================
    # 6. 生成对冲订单计划
    # =====================

    def generate_hedge_order(
        self,
        hedge_type: str,
        snapshot: dict,
        pos: float,

        quote_symbol: str,
        quote_group: str,

        net_buy_volume: int,
        net_sell_volume: int,

        buy_hedge_group: str,
        buy_hedge_symbol: str,
        buy_hedge_direction: str,
        buy_hedge_offset: str,
        buy_hedge_price_type: str,
        buy_hedge_price_offset: float,
        buy_hedge_price_offset_unit: str,

        sell_hedge_group: str,
        sell_hedge_symbol: str,
        sell_hedge_direction: str,
        sell_hedge_offset: str,
        sell_hedge_price_type: str,
        sell_hedge_price_offset: float,
        sell_hedge_price_offset_unit: str,
    ) -> dict | None:
        """
        根据 NET_BUY / NET_SELL 生成对冲订单。

        NET_BUY：
            说明净买入，默认发卖单对冲。

        NET_SELL：
            说明净卖出，默认发买单对冲。
        """

        if hedge_type == "NET_BUY":
            hedge_symbol = buy_hedge_symbol or quote_symbol
            hedge_group = buy_hedge_group or quote_group
            direction = buy_hedge_direction or "卖"
            offset_mode = buy_hedge_offset or "自动"
            price_type = buy_hedge_price_type or "Bid1"
            price_offset = buy_hedge_price_offset
            price_offset_unit = buy_hedge_price_offset_unit or "元"
            volume = int(net_buy_volume)
            reason = "net_buy_hedge"

        elif hedge_type == "NET_SELL":
            hedge_symbol = sell_hedge_symbol or quote_symbol
            hedge_group = sell_hedge_group or quote_group
            direction = sell_hedge_direction or "买"
            offset_mode = sell_hedge_offset or "自动"
            price_type = sell_hedge_price_type or "Ask1"
            price_offset = sell_hedge_price_offset
            price_offset_unit = sell_hedge_price_offset_unit or "元"
            volume = int(net_sell_volume)
            reason = "net_sell_hedge"

        else:
            return None

        if volume <= 0:
            return None

        base_price = self.get_base_price_by_type(
            snapshot=snapshot,
            price_type=price_type,
        )

        if base_price <= 0:
            return None

        price = self.calculate_hedge_price(
            base_price=base_price,
            price_offset=price_offset,
            price_offset_unit=price_offset_unit,
        )

        if price <= 0:
            return None

        offset = self.resolve_offset(
            direction=direction,
            offset_mode=offset_mode,
            pos=pos,
        )

        hedge_order = {
            "hedge_type": hedge_type,
            "symbol": hedge_symbol,
            "group": hedge_group,
            "direction": direction,
            "offset": offset,
            "price_type": price_type,
            "base_price": base_price,
            "price_offset": price_offset,
            "price_offset_unit": price_offset_unit,
            "price": price,
            "volume": volume,
            "reason": reason,
        }

        self.update_last_hedge(hedge_order)

        return hedge_order

    # =====================
    # 7. 注册对冲订单
    # =====================

    def register_hedge_order(
        self,
        vt_orderid: str,
        order_time: datetime,
    ) -> None:
        """
        主策略发出对冲单后，调用这个函数记录发单时间和撤补次数。
        """

        self.hedge_order_time[vt_orderid] = order_time
        self.hedge_replace_count.setdefault(vt_orderid, 0)

    # =====================
    # 8. 对冲撤补检查
    # =====================

    def check_timeout_and_replace(
        self,
        active_orders: dict[str, OrderData],
        hedge_orderids: set[str],
        now: datetime,
        hedge_wait_seconds: int,
        hedge_max_replace_count: int,
    ) -> dict:
        """
        检查对冲单是否超时未全成。

        返回执行计划：
        {
            "cancel_orderids": set(),
            "need_replace": bool,
            "stop_strategy": bool,
            "reason": str,
        }

        注意：
        这里只生成计划。
        真正撤单、重发单，由主策略执行。
        """

        plan = {
            "cancel_orderids": set(),
            "need_replace": False,
            "stop_strategy": False,
            "reason": "",
        }

        if hedge_wait_seconds <= 0:
            return plan

        for vt_orderid in list(hedge_orderids):
            order = active_orders.get(vt_orderid)

            if order is None:
                continue

            if not order.is_active():
                continue

            order_time = self.hedge_order_time.get(vt_orderid)

            if order_time is None:
                self.hedge_order_time[vt_orderid] = now
                continue

            elapsed_seconds = (now - order_time).total_seconds()

            if elapsed_seconds < hedge_wait_seconds:
                continue

            replace_count = self.hedge_replace_count.get(vt_orderid, 0)

            if replace_count >= hedge_max_replace_count:
                plan["stop_strategy"] = True
                plan["reason"] = (
                    f"hedge_replace_exceed_limit: "
                    f"{replace_count}/{hedge_max_replace_count}"
                )
                return plan

            plan["cancel_orderids"].add(vt_orderid)
            plan["need_replace"] = True
            plan["reason"] = "hedge_order_timeout_need_replace"

            self.hedge_replace_count[vt_orderid] = replace_count + 1

        return plan

    # =====================
    # 9. 清理结束的对冲订单
    # =====================

    def clear_finished_order(self, vt_orderid: str) -> None:
        """
        对冲订单结束后，清理记录。
        """

        self.hedge_order_time.pop(vt_orderid, None)
        self.hedge_replace_count.pop(vt_orderid, None)

    # =====================
    # 10. 废单风控
    # =====================

    def check_reject_risk(
        self,
        reject_enabled: bool,
        reject_count: int,
        max_reject_count: int,
    ) -> tuple[bool, str]:
        """
        对冲废单响应：
        废单次数达到最大废单次数后，策略停止。
        """

        if not reject_enabled:
            return True, "hedge_reject_disabled"

        if max_reject_count <= 0:
            return True, "hedge_max_reject_invalid_ignore"

        if reject_count >= max_reject_count:
            return False, f"hedge_reject_exceed_limit: {reject_count}/{max_reject_count}"

        return True, "hedge_reject_pass"

    # =====================
    # 11. 最近一次对冲记录
    # =====================

    def update_last_hedge(self, hedge_order: dict) -> None:
        self.last_hedge_action = hedge_order["direction"] + hedge_order["offset"]
        self.last_hedge_price = float(hedge_order["price"])
        self.last_hedge_volume = int(hedge_order["volume"])
        self.last_hedge_reason = hedge_order["reason"]

    def clear_last_hedge(self) -> None:
        self.last_hedge_action = ""
        self.last_hedge_price = 0.0
        self.last_hedge_volume = 0
        self.last_hedge_reason = ""

    def get_last_hedge_snapshot(self) -> dict:
        return {
            "last_hedge_action": self.last_hedge_action,
            "last_hedge_price": self.last_hedge_price,
            "last_hedge_volume": self.last_hedge_volume,
            "last_hedge_reason": self.last_hedge_reason,
        }
class ReportManager:
    """报告模块：输出 tick 决策、订单、成交、汇总 CSV"""

    def __init__(
        self,
        report_dir: str = "reports",
        strategy_name: str = "sge_market_making",
    ) -> None:
        self.report_dir = Path(report_dir)
        self.strategy_name = strategy_name

        self.tick_rows: list[dict] = []
        self.order_rows: list[dict] = []
        self.trade_rows: list[dict] = []

        # =====================
        # 核心 summary 统计变量
        # =====================

        self.quote_sample_count: int = 0

        # 本方双边有效报价样本数量
        self.valid_quote_sample_count: int = 0

        # 本方买卖价差累计
        self.own_spread_sum: float = 0.0

        # 本方有效报价深度累计
        # 这里用 MIN(本方买量, 本方卖量)，表示双边同时有效的深度
        self.effective_depth_sum: float = 0.0

        # 有效报价时长，单位秒
        self.effective_quote_seconds: float = 0.0

        # 上一个 tick 的时间
        self.last_tick_datetime: datetime | None = None

        # 上一个 tick 是否处于双边有效报价状态
        self.last_effective_quote_active: bool = False

        # 成交统计
        self.total_trade_volume: float = 0.0
        self.mm_trade_volume: float = 0.0
        self.hedge_trade_volume: float = 0.0

        self.total_trade_amount: float = 0.0
        self.mm_trade_amount: float = 0.0
        self.hedge_trade_amount: float = 0.0

        # 停止原因
        self.stop_reason: str = ""

    # =====================
    # 1. 记录 tick 决策
    # =====================

    def record_tick_decision(
        self,
        tick: TickData,
        mm_active: bool,
        strategy_stopped: bool,
        action: str,
        reason: str,

        window_avg: float,
        window_diff: float,

        other_bid1: float,
        other_ask1: float,
        other_bid1_volume: float,
        other_ask1_volume: float,
        market_spread: float,
        book_volume: float,

        scenario_id: int,
        N: int,
        E: int,
        F: int,

        target_buy_price: float,
        target_sell_price: float,
        target_buy_volume: float,
        target_sell_volume: float,

        own_best_bid_price: float,
        own_best_ask_price: float,
        own_best_bid_volume: float,
        own_best_ask_volume: float,
    ) -> None:
        """
        每个 tick 记录一次策略决策。

        同时更新核心报价指标：
        1. 最优平均报价差
        2. 平均有效报价深度
        3. 平均有效报价时长
        """

        dt = tick.datetime
        last_price = float(tick.last_price or 0.0)

        own_spread = 0.0
        effective_depth = 0.0

        has_valid_two_sided_quote = (
            own_best_bid_price > 0
            and own_best_ask_price > 0
            and own_best_ask_price > own_best_bid_price
            and own_best_bid_volume > 0
            and own_best_ask_volume > 0
        )

        if has_valid_two_sided_quote:
            own_spread = own_best_ask_price - own_best_bid_price
            effective_depth = min(own_best_bid_volume, own_best_ask_volume)

        # 更新 summary 统计
        self.quote_sample_count += 1

        if has_valid_two_sided_quote:
            self.valid_quote_sample_count += 1
            self.own_spread_sum += own_spread
            self.effective_depth_sum += effective_depth

        self._update_effective_quote_duration(
            current_datetime=dt,
            current_effective_quote_active=has_valid_two_sided_quote,
        )

        row = {
            "datetime": dt,
            "last_price": last_price,

            "mm_active": mm_active,
            "strategy_stopped": strategy_stopped,
            "action": action,
            "reason": reason,

            "window_avg": window_avg,
            "window_diff": window_diff,

            "other_bid1": other_bid1,
            "other_ask1": other_ask1,
            "other_bid1_volume": other_bid1_volume,
            "other_ask1_volume": other_ask1_volume,
            "market_spread": market_spread,
            "book_volume": book_volume,

            "scenario_id": scenario_id,
            "N": N,
            "E": E,
            "F": F,

            "target_buy_price": target_buy_price,
            "target_sell_price": target_sell_price,
            "target_buy_volume": target_buy_volume,
            "target_sell_volume": target_sell_volume,

            "own_best_bid_price": own_best_bid_price,
            "own_best_ask_price": own_best_ask_price,
            "own_best_bid_volume": own_best_bid_volume,
            "own_best_ask_volume": own_best_ask_volume,

            "own_spread": own_spread,
            "effective_depth": effective_depth,
            "has_valid_two_sided_quote": has_valid_two_sided_quote,
        }

        self.tick_rows.append(row)

    def _update_effective_quote_duration(
        self,
        current_datetime: datetime,
        current_effective_quote_active: bool,
    ) -> None:
        """
        统计有效报价时长。

        逻辑：
        如果上一段时间内处于双边有效报价状态，
        则把 last_tick_datetime 到 current_datetime 的时间差计入有效报价时长。
        """

        if self.last_tick_datetime is not None:
            delta_seconds = (current_datetime - self.last_tick_datetime).total_seconds()

            if delta_seconds < 0:
                delta_seconds = 0

            if self.last_effective_quote_active:
                self.effective_quote_seconds += delta_seconds

        self.last_tick_datetime = current_datetime
        self.last_effective_quote_active = current_effective_quote_active

    # =====================
    # 2. 记录订单
    # =====================

    def record_order(
        self,
        order: OrderData,
        order_type: str,
        scenario_id: int = 0,
        reason: str = "",
    ) -> None:
        """
        记录订单状态。

        order_type:
            MM
            HEDGE
            MANUAL
        """

        row = {
            "datetime": getattr(order, "datetime", ""),
            "vt_orderid": getattr(order, "vt_orderid", ""),
            "symbol": getattr(order, "symbol", ""),
            "exchange": getattr(order, "exchange", ""),
            "order_type": order_type,

            "direction": str(getattr(order, "direction", "")),
            "offset": str(getattr(order, "offset", "")),
            "price": float(getattr(order, "price", 0.0) or 0.0),
            "volume": float(getattr(order, "volume", 0.0) or 0.0),
            "traded": float(getattr(order, "traded", 0.0) or 0.0),
            "status": str(getattr(order, "status", "")),

            "scenario_id": scenario_id,
            "reason": reason,
        }

        self.order_rows.append(row)

    # =====================
    # 3. 记录成交
    # =====================

    def record_trade(
        self,
        trade: TradeData,
        order_type: str,
        contract_size: float = 1.0,
        trigger_hedge: bool = False,
        net_buy_volume: float = 0.0,
        net_sell_volume: float = 0.0,
    ) -> None:
        """
        记录成交，并更新成交量统计。

        order_type:
            MM
            HEDGE
            MANUAL
        """

        price = float(getattr(trade, "price", 0.0) or 0.0)
        volume = float(getattr(trade, "volume", 0.0) or 0.0)
        amount = price * volume * contract_size

        self.total_trade_volume += volume
        self.total_trade_amount += amount

        if order_type == "MM":
            self.mm_trade_volume += volume
            self.mm_trade_amount += amount

        elif order_type == "HEDGE":
            self.hedge_trade_volume += volume
            self.hedge_trade_amount += amount

        row = {
            "datetime": getattr(trade, "datetime", ""),
            "vt_orderid": getattr(trade, "vt_orderid", ""),
            "vt_tradeid": getattr(trade, "vt_tradeid", ""),
            "symbol": getattr(trade, "symbol", ""),
            "exchange": getattr(trade, "exchange", ""),
            "order_type": order_type,

            "direction": str(getattr(trade, "direction", "")),
            "offset": str(getattr(trade, "offset", "")),
            "price": price,
            "volume": volume,
            "amount": amount,

            "net_buy_volume": net_buy_volume,
            "net_sell_volume": net_sell_volume,
            "trigger_hedge": trigger_hedge,
        }

        self.trade_rows.append(row)

    # =====================
    # 4. 生成 summary 指标
    # =====================

    def get_summary(self) -> dict:
        """
        生成核心汇总指标。

        重点指标：
        1. 最优平均报价差(元)
        2. 平均有效报价深度(双边手)
        3. 平均有效报价时长(小时)
        4. 成交量
        """

        if self.valid_quote_sample_count > 0:
            best_avg_quote_spread = self.own_spread_sum / self.valid_quote_sample_count
            avg_effective_quote_depth = self.effective_depth_sum / self.valid_quote_sample_count
        else:
            best_avg_quote_spread = 0.0
            avg_effective_quote_depth = 0.0

        avg_effective_quote_hours = self.effective_quote_seconds / 3600

        return {
            "quote_sample_count": self.quote_sample_count,
            "valid_quote_sample_count": self.valid_quote_sample_count,

            "best_avg_quote_spread_yuan": best_avg_quote_spread,
            "avg_effective_quote_depth_lot": avg_effective_quote_depth,
            "avg_effective_quote_hours": avg_effective_quote_hours,

            "total_trade_volume": self.total_trade_volume,
            "mm_trade_volume": self.mm_trade_volume,
            "hedge_trade_volume": self.hedge_trade_volume,

            "total_trade_amount": self.total_trade_amount,
            "mm_trade_amount": self.mm_trade_amount,
            "hedge_trade_amount": self.hedge_trade_amount,

            "stop_reason": self.stop_reason,
        }

    # =====================
    # 5. 写 CSV 文件
    # =====================

    def write_all_reports(self) -> None:
        """输出所有 CSV 文件"""

        self.report_dir.mkdir(parents=True, exist_ok=True)

        self._write_csv(
            filename=f"{self.strategy_name}_tick_decision_report.csv",
            rows=self.tick_rows,
        )

        self._write_csv(
            filename=f"{self.strategy_name}_order_report.csv",
            rows=self.order_rows,
        )

        self._write_csv(
            filename=f"{self.strategy_name}_trade_report.csv",
            rows=self.trade_rows,
        )

        self._write_csv(
            filename=f"{self.strategy_name}_summary_report.csv",
            rows=[self.get_summary()],
        )

    def _write_csv(
        self,
        filename: str,
        rows: list[dict],
    ) -> None:
        """写单个 CSV 文件"""

        if not rows:
            return

        path = self.report_dir / filename

        fieldnames = list(rows[0].keys())

        with path.open(
            mode="w",
            newline="",
            encoding="utf-8-sig",
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
            )
            writer.writeheader()
            writer.writerows(rows)

    # =====================
    # 6. 停止原因
    # =====================

    def set_stop_reason(self, reason: str) -> None:
        """记录策略停止原因"""
        self.stop_reason = reason

    # =====================
    # 7. 重置
    # =====================

    def reset(self) -> None:
        """重置 report 状态"""

        self.tick_rows.clear()
        self.order_rows.clear()
        self.trade_rows.clear()

        self.quote_sample_count = 0
        self.valid_quote_sample_count = 0

        self.own_spread_sum = 0.0
        self.effective_depth_sum = 0.0
        self.effective_quote_seconds = 0.0

        self.last_tick_datetime = None
        self.last_effective_quote_active = False

        self.total_trade_volume = 0.0
        self.mm_trade_volume = 0.0
        self.hedge_trade_volume = 0.0

        self.total_trade_amount = 0.0
        self.mm_trade_amount = 0.0
        self.hedge_trade_amount = 0.0

        self.stop_reason = ""


class SgeMarketMakingStrategy(CtaTemplate):
    """上金所新做市策略：简化核心版"""

    author = "Yang"

    # =========================================================
    # 1. 策略参数：尽量少，适合回测
    # =========================================================

    execution_time: str = "09:00:00.000,15:30:00.000"

    # A/B/C/D
    spread_threshold: float = 0.02
    book_volume_threshold: int = 5
    window_length: int = 10
    window_diff_threshold: float = 0.02

    # 自动生成 N/E/F 的基础参数
    base_quote_level: int = 1
    base_offset_tick: int = 1
    base_quote_volume: int = 1

    # 报单容忍度 H
    quote_tolerance: float = 1.0

    # 简化价格笼子：以 last_price 为中心
    price_cage_enabled: bool = False
    price_cage_offset: float = 0.20

    # 简化对冲：成交一笔对冲一笔
    hedge_enabled: bool = True
    hedge_offset_tick: int = 1

    # =========================================================
    # 2. 策略变量：界面展示 / 内部状态
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
    own_spread: float = 0.0

    own_best_bid_price: float = 0.0
    own_best_ask_price: float = 0.0
    own_best_bid_volume: float = 0.0
    own_best_ask_volume: float = 0.0

    current_scenario_id: int = 0
    current_N: int = 0
    current_E: int = 0
    current_F: int = 0

    target_buy_price: float = 0.0
    target_sell_price: float = 0.0
    target_buy_volume: int = 0
    target_sell_volume: int = 0

    active_order_count: int = 0
    mm_order_count: int = 0
    hedge_order_count: int = 0

    trade_count: int = 0
    buy_trade_volume: int = 0
    sell_trade_volume: int = 0
    net_buy_volume: int = 0
    net_sell_volume: int = 0

    last_hedge_action: str = ""
    last_hedge_price: float = 0.0
    last_hedge_volume: int = 0

    strategy_stopped: bool = False

    # =========================================================
    # 3. vn.py 参数列表
    # =========================================================

    parameters = [
        "execution_time",

        "spread_threshold",
        "book_volume_threshold",
        "window_length",
        "window_diff_threshold",

        "base_quote_level",
        "base_offset_tick",
        "base_quote_volume",

        "quote_tolerance",

        "price_cage_enabled",
        "price_cage_offset",

        "hedge_enabled",
        "hedge_offset_tick",
    ]

    # =========================================================
    # 4. vn.py 变量列表
    # =========================================================

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
        "own_spread",

        "own_best_bid_price",
        "own_best_ask_price",
        "own_best_bid_volume",
        "own_best_ask_volume",

        "current_scenario_id",
        "current_N",
        "current_E",
        "current_F",

        "target_buy_price",
        "target_sell_price",
        "target_buy_volume",
        "target_sell_volume",

        "active_order_count",
        "mm_order_count",
        "hedge_order_count",

        "trade_count",
        "buy_trade_volume",
        "sell_trade_volume",
        "net_buy_volume",
        "net_sell_volume",

        "last_hedge_action",
        "last_hedge_price",
        "last_hedge_volume",

        "strategy_stopped",
    ]

    # =========================================================
    # 5. 初始化
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

        self.orders: dict[str, OrderData] = {}
        self.mm_orderids: set[str] = set()
        self.hedge_orderids: set[str] = set()

        self.last_tick: TickData | None = None
        self.last_snapshot: dict | None = None
        # 回测性能优化：tick 计数，用于降低 put_event 频率
        self.tick_count: int = 0
        self.put_event_interval: int = 100

        # 回测性能优化：交易时间只解析一次，避免每个 tick 重复 strptime
        self.execution_start_time = None
        self.execution_end_time = None
    # =========================================================
    # 6. 自动生成 8 档 N/E/F
    # =========================================================

    def get_scenario_config(self) -> dict[int, tuple[int, int, int]]:
        """
        自动生成 8 档配置。
        scenario_id -> (N, E, F)
        """

        N = self.base_quote_level
        E = self.base_offset_tick
        F = self.base_quote_volume

        return {
            # 价差小，容易被动成交，所以偏保守
            1: (N, E, F),  # 盘口量足 + 价格稳定
            2: (N + 1, E + 1, F),  # 盘口量足 + 价格不稳定
            3: (N + 1, E + 1, F),  # 盘口量不足 + 价格稳定
            4: (N + 2, E + 2, F),  # 盘口量不足 + 价格不稳定

            # 价差大，空间更充足，可以相对积极
            5: (N, E, F),  # 盘口量不足 + 价格稳定
            6: (N + 1, E + 1, F),  # 盘口量不足 + 价格不稳定
            7: (N, E, F),  # 盘口量足 + 价格稳定
            8: (N + 1, E + 1, F),  # 盘口量足 + 价格不稳定
        }

    # =========================================================
    # 7. 生命周期函数
    # =========================================================

    def on_init(self) -> None:
        self.write_log("上金所新做市策略初始化")
        self.put_event()

    def on_start(self) -> None:
        self.write_log("上金所新做市策略启动")

        self.price_tick = self.get_pricetick()
        self.contract_size = self.get_size()
        # 只在启动时解析一次交易时间，避免每个 tick 都 strptime
        self.parse_execution_time()
        self.orders.clear()
        self.mm_orderids.clear()
        self.hedge_orderids.clear()

        self.price_window_manager.reset()
        self.price_window_manager.update_window_length(self.window_length)

        self.order_manager.clear()

        self.scenario_selector.update_thresholds(
            spread_threshold=self.spread_threshold,
            book_volume_threshold=self.book_volume_threshold,
            window_diff_threshold=self.window_diff_threshold,
        )

        self.scenario_selector.update_scenario_config(
            self.get_scenario_config()
        )

        self.strategy_stopped = False

        self.put_event()

    def on_stop(self) -> None:
        self.write_log("上金所新做市策略停止")
        self.cancel_market_making_orders()
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """核心报价逻辑"""

        self.last_tick = tick

        snapshot = self.market_data.update_tick(tick)
        self.last_snapshot = snapshot

        self.last_price = snapshot["last_price"]
        self.bid1 = snapshot["bid1"]
        self.ask1 = snapshot["ask1"]
        self.bid1_volume = snapshot["bid1_volume"]
        self.ask1_volume = snapshot["ask1_volume"]

        self.price_window_manager.update(snapshot["last_price"])

        if self.strategy_stopped:
            self.put_event_throttled()
            return

        if not self.in_execution_time(snapshot["datetime"]):
            self.cancel_market_making_orders()
            self.update_own_quote_variables()
            self.put_event_throttled()
            return

        if not self.price_window_manager.is_ready():
            self.window_avg = 0.0
            self.window_diff = 0.0
            self.current_scenario_id = 0
            self.update_own_quote_variables()
            self.put_event_throttled()
            return

        other_book = self.order_book_processor.remove_own_orders(
            snapshot=snapshot,
            active_orders=self.orders,
            own_orderids=self.mm_orderids,
        )

        self.other_bid1 = other_book["bid1"]
        self.other_ask1 = other_book["ask1"]
        self.other_bid1_volume = other_book["bid1_volume"]
        self.other_ask1_volume = other_book["ask1_volume"]
        self.valid_depth = other_book["valid_depth"]

        if self.order_book_processor.is_one_sided(other_book):
            self.cancel_market_making_orders()

            self.market_spread = 0.0
            self.book_volume = 0
            self.current_scenario_id = 0

            self.update_own_quote_variables()
            self.put_event_throttled()
            return

        self.window_avg = self.price_window_manager.get_average()
        self.window_diff = self.price_window_manager.get_diff(
            snapshot["last_price"]
        )

        self.market_spread = other_book["market_spread"]
        self.book_volume = other_book["book_volume"]

        self.current_scenario_id = self.scenario_selector.select(
            spread=self.market_spread,
            book_volume=self.book_volume,
            abs_window_diff=abs(self.window_diff),
        )

        self.current_N, self.current_E, self.current_F = (
            self.scenario_selector.get_config(self.current_scenario_id)
        )

        buy_quote, sell_quote = self.quote_generator.generate_quotes(
            scenario_id=self.current_scenario_id,
            N=self.current_N,
            E=self.current_E,
            F=self.current_F,
            other_book=other_book,
            price_tick=self.price_tick,
        )

        buy_quote, sell_quote = self.apply_simple_price_cage(
            buy_quote=buy_quote,
            sell_quote=sell_quote,
            snapshot=snapshot,
        )

        self.target_buy_price = buy_quote["price"] if buy_quote else 0.0
        self.target_sell_price = sell_quote["price"] if sell_quote else 0.0
        self.target_buy_volume = buy_quote["volume"] if buy_quote else 0
        self.target_sell_volume = sell_quote["volume"] if sell_quote else 0

        plan = self.order_manager.build_sync_plan(
            buy_quote=buy_quote,
            sell_quote=sell_quote,
            scenario_id=self.current_scenario_id,
            active_orders=self.orders,
            mm_orderids=self.mm_orderids,
            quote_tolerance=self.quote_tolerance,
        )

        self.execute_order_plan(plan)

        self.update_own_quote_variables()
        self.update_order_count()

        self.put_event_throttled()

    def on_order(self, order: OrderData) -> None:
        """
        订单状态更新。

        关键优化：
        1. 非活跃订单从 mm_orderids / hedge_orderids 中移除；
        2. self.orders 只保留活跃订单，避免订单字典越来越大；
        3. 降低 put_event 频率。
        """

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
        """成交一笔，对冲一笔"""

        self.trade_count += 1

        order_type = self.get_order_type(trade.vt_orderid)

        volume = int(trade.volume or 0)

        direction_text = str(trade.direction).lower()

        if (
            "long" in direction_text
            or "buy" in direction_text
            or "多" in direction_text
            or "买" in direction_text
        ):
            self.buy_trade_volume += volume

        elif (
            "short" in direction_text
            or "sell" in direction_text
            or "空" in direction_text
            or "卖" in direction_text
        ):
            self.sell_trade_volume += volume

        self.net_buy_volume = max(
            self.buy_trade_volume - self.sell_trade_volume,
            0,
        )
        self.net_sell_volume = max(
            self.sell_trade_volume - self.buy_trade_volume,
            0,
        )

        if order_type == "MM" and self.hedge_enabled:
            self.hedge_one_trade(trade)

        self.update_order_count()
        self.update_own_quote_variables()

        self.put_event()

    def on_timer(self) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass

    # =========================================================
    # 8. 辅助函数
    # =========================================================

    def apply_simple_price_cage(
        self,
        buy_quote: dict | None,
        sell_quote: dict | None,
        snapshot: dict,
    ) -> tuple[dict | None, dict | None]:
        """简化价格笼子：last_price 上下 price_cage_offset"""

        if not self.price_cage_enabled:
            return buy_quote, sell_quote

        last_price = float(snapshot["last_price"] or 0.0)

        if last_price <= 0:
            return None, None

        lower = last_price - self.price_cage_offset
        upper = last_price + self.price_cage_offset

        if buy_quote and not (lower <= buy_quote["price"] <= upper):
            buy_quote = None

        if sell_quote and not (lower <= sell_quote["price"] <= upper):
            sell_quote = None

        return buy_quote, sell_quote

    def execute_order_plan(self, plan: dict) -> None:
        """执行撤单/发单计划"""

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

        if plan["send_sell_quote"]:
            quote = plan["send_sell_quote"]
            vt_orderids = self.short(
                price=quote["price"],
                volume=quote["volume"],
            )
            self.mm_orderids.update(vt_orderids)

    def hedge_one_trade(self, trade: TradeData) -> None:
        """做市成交一笔，对冲一笔"""

        if not self.last_snapshot:
            return

        volume = int(trade.volume or 0)

        if volume <= 0:
            return

        direction_text = str(trade.direction).lower()

        # 做市买成交 -> 卖出对冲
        if (
            "long" in direction_text
            or "buy" in direction_text
            or "多" in direction_text
            or "买" in direction_text
        ):
            price = self.bid1 - self.hedge_offset_tick * self.price_tick

            if price <= 0:
                return

            vt_orderids = self.short(price=price, volume=volume)

            self.last_hedge_action = "卖开"
            self.last_hedge_price = price
            self.last_hedge_volume = volume

        # 做市卖成交 -> 买入对冲
        elif (
            "short" in direction_text
            or "sell" in direction_text
            or "空" in direction_text
            or "卖" in direction_text
        ):
            price = self.ask1 + self.hedge_offset_tick * self.price_tick

            if price <= 0:
                return

            vt_orderids = self.buy(price=price, volume=volume)

            self.last_hedge_action = "买开"
            self.last_hedge_price = price
            self.last_hedge_volume = volume

        else:
            return

        self.hedge_orderids.update(vt_orderids)

    def cancel_market_making_orders(self) -> None:
        """
        只撤做市订单，不撤对冲订单。

        关键优化：
        撤单后先清空本地 mm_orderids，避免旧订单 ID 反复参与扫描。
        """

        for vt_orderid in list(self.mm_orderids):
            order = self.orders.get(vt_orderid)

            if order and order.is_active():
                self.cancel_order(vt_orderid)

        self.mm_orderids.clear()

    def update_order_count(self) -> None:
        self.active_order_count = 0
        self.mm_order_count = 0
        self.hedge_order_count = 0

        for vt_orderid, order in self.orders.items():
            if not order.is_active():
                continue

            self.active_order_count += 1

            if vt_orderid in self.mm_orderids:
                self.mm_order_count += 1

            elif vt_orderid in self.hedge_orderids:
                self.hedge_order_count += 1

    def put_event_throttled(self) -> None:
        """
        降低 GUI 刷新频率。
        tick 回测中如果每个 tick 都 put_event，会明显拖慢速度。
        """
        self.tick_count += 1

        if self.tick_count % self.put_event_interval == 0:
            self.put_event()

    def update_own_quote_variables(self) -> None:
        own_quote = self.order_manager.get_own_best_quote(
            active_orders=self.orders,
            mm_orderids=self.mm_orderids,
        )

        self.own_best_bid_price = own_quote["own_best_bid_price"]
        self.own_best_ask_price = own_quote["own_best_ask_price"]
        self.own_best_bid_volume = own_quote["own_best_bid_volume"]
        self.own_best_ask_volume = own_quote["own_best_ask_volume"]
        self.own_spread = own_quote["own_spread"]

    def get_order_type(self, vt_orderid: str) -> str:
        if vt_orderid in self.mm_orderids:
            return "MM"

        if vt_orderid in self.hedge_orderids:
            return "HEDGE"

        return "OTHER"

    def in_execution_time(self, dt) -> bool:
        """
        判断当前 tick 是否在交易时间内。
        交易时间已经在 on_start 中解析好，这里只做比较。
        """
        if self.execution_start_time is None or self.execution_end_time is None:
            return True

        if dt is None:
            return False

        current_time = dt.time()

        if self.execution_start_time <= self.execution_end_time:
            return self.execution_start_time <= current_time <= self.execution_end_time

        return (
                current_time >= self.execution_start_time
                or current_time <= self.execution_end_time
        )

    def parse_execution_time(self) -> None:
        """
        启动时解析 execution_time。
        原来每个 tick 都解析字符串，回测时会拖慢速度。
        """
        self.execution_start_time = None
        self.execution_end_time = None

        if not self.execution_time:
            return

        try:
            start_str, end_str = self.execution_time.split(",")

            self.execution_start_time = datetime.strptime(
                start_str.strip(),
                "%H:%M:%S.%f",
            ).time()

            self.execution_end_time = datetime.strptime(
                end_str.strip(),
                "%H:%M:%S.%f",
            ).time()

        except Exception:
            self.execution_start_time = None
            self.execution_end_time = None