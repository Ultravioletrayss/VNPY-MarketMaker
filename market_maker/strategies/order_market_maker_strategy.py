from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    TradeData,
    OrderData,
    StopOrder,
)
import math
import csv
from pathlib import Path


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
            if self.debug:
                print(
                    f"非正常盘口，market_spread 设为 0："
                    f"bid1={self.bid1}, ask1={self.ask1}, "
                    f"bid1_volume={self.bid1_volume}, ask1_volume={self.ask1_volume}"
                )
            self.market_spread = 0.0

        self.valid_depth = self._calculate_valid_depth()

        return self.get_snapshot()

    def _calculate_valid_depth(self) -> int:
        # 有效深度默认为0
        valid_depth = 0
        # 循环遍历盘口数据，计算有效深度，量价都不为0才行
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

    # 返回快照snapshot，snapshot包含当前时刻盘口的各种数据，方便后续直接调用snapshot，snapshot为字典
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

    # 检查盘口数据是否合法
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

    # 判断当前盘口数据是否为5档
    def has_depth(self, depth: int = 5) -> bool:
        return self.valid_depth >= depth

    # 判断当前五档volume的总值是多少，分别为bid_total_volume, ask_total_volume
    def get_depth_volume(self, depth: int = 5) -> tuple[float, float]:
        depth = min(depth, 5, self.valid_depth)

        if depth <= 0:
            return 0.0, 0.0

        bid_volume_sum = sum(self.bid_volumes[:depth])
        ask_volume_sum = sum(self.ask_volumes[:depth])

        return bid_volume_sum, ask_volume_sum



class PricingEngine:
    def __init__(self) -> None:
        self.mid_price: float = 0.0
        self.micro_price: float = 0.0
        self.depth_weighted_mid: float = 0.0
        self.exp_weighted_depth_mid: float = 0.0

        self.ema_fair_price: float = 0.0
        self.fair_price: float = 0.0

        self.ema_alpha: float = 0.2

    def reset(self) -> None:
        """重置定价引擎状态，尤其是 EMA 状态"""
        self.mid_price = 0.0
        self.micro_price = 0.0
        self.depth_weighted_mid = 0.0
        self.exp_weighted_depth_mid = 0.0
        self.ema_fair_price = 0.0
        self.fair_price = 0.0

    # 计算中价，
    def calculate_mid_price(self, snapshot: dict) -> float:
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]

        if bid1 <= 0 or ask1 <= 0 or ask1 <= bid1:
            return 0.0

        self.mid_price = (bid1 + ask1) / 2
        return self.mid_price

    # 计算微基准价，就是那个公式。
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

    # 计算五档盘口加权中间价。量价相乘然后加权平均/2
    def calculate_depth_weighted_mid(self, snapshot: dict, depth: int = 5) -> float:
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

    # ==================== 新增：指数加权五档基准价 ====================

    def calculate_exp_weighted_depth_mid(
            self,
            snapshot: dict,
            depth: int = 5,
            decay: float = 0.6,
    ) -> float:
        """
        指数加权五档中间价。

        近端盘口权重更高：
        第1档权重 = 1
        第2档权重 = decay
        第3档权重 = decay^2
        ...
        """

        bid_prices = snapshot["bid_prices"]
        ask_prices = snapshot["ask_prices"]
        bid_volumes = snapshot["bid_volumes"]
        ask_volumes = snapshot["ask_volumes"]
        valid_depth = snapshot["valid_depth"]

        depth = min(depth, valid_depth, 5)

        if depth <= 0:
            return 0.0

        # decay 做保护，避免乱填
        if decay <= 0:
            decay = 0.6

        if decay > 1:
            decay = 1.0

        bid_amount = 0.0
        ask_amount = 0.0
        bid_volume_sum = 0.0
        ask_volume_sum = 0.0

        weight = 1.0

        for i in range(depth):
            bid_price = bid_prices[i]
            ask_price = ask_prices[i]
            bid_volume = bid_volumes[i]
            ask_volume = ask_volumes[i]

            if bid_price <= 0 or ask_price <= 0:
                continue

            if bid_volume <= 0 or ask_volume <= 0:
                continue

            bid_amount += bid_price * bid_volume * weight
            ask_amount += ask_price * ask_volume * weight
            bid_volume_sum += bid_volume * weight
            ask_volume_sum += ask_volume * weight

            weight *= decay

        if bid_volume_sum <= 0 or ask_volume_sum <= 0:
            return self.calculate_depth_weighted_mid(snapshot, depth)

        weighted_bid = bid_amount / bid_volume_sum
        weighted_ask = ask_amount / ask_volume_sum

        self.exp_weighted_depth_mid = (weighted_bid + weighted_ask) / 2

        return self.exp_weighted_depth_mid

    # ==================== 新增：EMA 平滑 ====================

    def apply_ema_smoothing(
            self,
            new_price: float,
            ema_alpha: float = 0.2,
    ) -> float:
        """
        对 fair_price 做 EMA 平滑。

        ema_alpha 越大，越跟随最新价格；
        ema_alpha 越小，越平滑。
        """

        if new_price <= 0:
            return new_price

        if ema_alpha <= 0:
            return new_price

        if ema_alpha > 1:
            ema_alpha = 1.0

        if self.ema_fair_price <= 0:
            self.ema_fair_price = new_price
        else:
            self.ema_fair_price = (
                    ema_alpha * new_price
                    + (1 - ema_alpha) * self.ema_fair_price
            )

        return self.ema_fair_price

    def calculate_fair_price(
            self,
            snapshot: dict,
            pricing_method: str = "exp_depth_weighted",
            depth: int = 5,
            exp_depth_decay: float = 0.6,
            use_ema_smoothing: bool = False,
            ema_alpha: float = 0.2,
    ) -> float:
        """
        计算最终基准价。

        pricing_method:
            mid
            micro
            depth_weighted
            exp_depth_weighted

        use_ema_smoothing:
            是否对最终基准价做 EMA 平滑
        """

        if pricing_method == "mid":
            raw_price = self.calculate_mid_price(snapshot)

        elif pricing_method == "micro":
            raw_price = self.calculate_micro_price(snapshot)

        elif pricing_method == "depth_weighted":
            raw_price = self.calculate_depth_weighted_mid(
                snapshot=snapshot,
                depth=depth,
            )

        elif pricing_method == "exp_depth_weighted":
            raw_price = self.calculate_exp_weighted_depth_mid(
                snapshot=snapshot,
                depth=depth,
                decay=exp_depth_decay,
            )

        else:
            raw_price = self.calculate_depth_weighted_mid(
                snapshot=snapshot,
                depth=depth,
            )

        if raw_price <= 0:
            self.fair_price = raw_price
            return raw_price

        if use_ema_smoothing:
            final_price = self.apply_ema_smoothing(
                new_price=raw_price,
                ema_alpha=ema_alpha,
            )
        else:
            final_price = raw_price

        self.fair_price = final_price
        return final_price

    # 盘口价格四舍五入，Price_tick好像要从外界获取
    def round_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return round(price / price_tick) * price_tick


class QuoteRiskFilter:
    """报价风控过滤器：判断当前行情是否适合做市，以及根据持仓限制过滤报价"""

    def check_market_data(self, snapshot: dict) -> bool:
        """
        检查最基础的盘口数据是否合法。
        只检查买一卖一，不检查五档深度。
        """
        bid1 = snapshot["bid1"]  # 买一价
        ask1 = snapshot["ask1"]  # 卖一价
        bid1_volume = snapshot["bid1_volume"]  # 买一挂单量
        ask1_volume = snapshot["ask1_volume"]  # 卖一挂单量

        # 买一价必须大于 0
        if bid1 <= 0:
            return False

        # 卖一价必须大于 0
        if ask1 <= 0:
            return False

        # 正常盘口必须是 卖一价 > 买一价
        # 如果 ask1 <= bid1，说明盘口异常，不能报价
        if ask1 <= bid1:
            return False

        # 买一必须有挂单量
        if bid1_volume <= 0:
            return False

        # 卖一必须有挂单量
        if ask1_volume <= 0:
            return False

        return True

    def check_depth(
            self,
            snapshot: dict,  # 当前行情快照
            min_depth: int = 1  # 最小要求盘口深度，默认至少 1 档
    ) -> bool:
        """
        检查当前盘口有效深度是否足够。
        比如 min_depth=5，就要求买卖五档都有效。
        """
        valid_depth = snapshot["valid_depth"]  # 当前有效盘口深度

        return valid_depth >= min_depth

    def check_spread(
            self,
            snapshot: dict,  # 当前行情快照
            price_tick: float,  # 合约最小变动价位
            min_spread_tick: int  # 最小价差要求，单位是 tick
    ) -> bool:
        """
        检查当前买卖价差是否足够。
        如果价差太小，做市利润空间不够，就不报价。
        """
        market_spread = snapshot["market_spread"]  # 当前盘口价差 = ask1 - bid1

        # price_tick 不合法，无法换算价差 tick 数
        if price_tick <= 0:
            return False

        # 把实际价差换算成几个 tick
        # 例如 market_spread=2，price_tick=1，则 spread_tick=2
        spread_tick = market_spread / price_tick

        # 当前价差必须大于等于最低要求
        return spread_tick >= min_spread_tick

    def check_depth_volume(
            self,
            snapshot: dict,  # 当前行情快照
            depth: int = 5,  # 检查前几档盘口
            min_depth_volume: float = 1  # 前 N 档买卖盘最小挂单量要求
    ) -> bool:
        """
        检查前 N 档买卖盘挂单量是否足够。
        如果盘口太薄，容易被打穿，不适合做市。
        """
        bid_volumes = snapshot["bid_volumes"]  # 五档买盘挂单量
        ask_volumes = snapshot["ask_volumes"]  # 五档卖盘挂单量
        valid_depth = snapshot["valid_depth"]  # 当前有效深度

        # 实际检查深度不能超过：
        # 1. 传入的 depth
        # 2. 当前有效深度 valid_depth
        # 3. 最大 5 档
        depth = min(depth, valid_depth, 5)

        # 没有有效深度，直接不通过
        if depth <= 0:
            return False

        # 计算前 depth 档买盘总量
        bid_volume_sum = sum(bid_volumes[:depth])

        # 计算前 depth 档卖盘总量
        ask_volume_sum = sum(ask_volumes[:depth])

        # 买盘深度不够，不报价
        if bid_volume_sum < min_depth_volume:
            return False

        # 卖盘深度不够，不报价
        if ask_volume_sum < min_depth_volume:
            return False

        return True

    def check_imbalance(
            self,
            snapshot: dict,  # 当前行情快照
            max_imbalance: float = 0.9,  # 最大允许盘口不平衡程度
            depth: int = 5  # 用前几档盘口计算不平衡
    ) -> bool:
        """
        检查盘口买卖力量是否过度失衡。
        imbalance 接近 1 说明买盘远大于卖盘；
        imbalance 接近 -1 说明卖盘远大于买盘。
        """
        bid_volumes = snapshot["bid_volumes"]  # 五档买盘挂单量
        ask_volumes = snapshot["ask_volumes"]  # 五档卖盘挂单量
        valid_depth = snapshot["valid_depth"]  # 当前有效深度

        # 实际检查深度取最小值，避免访问无效盘口
        depth = min(depth, valid_depth, 5)

        # 没有有效深度，直接不通过
        if depth <= 0:
            return False

        # 前 depth 档买盘总量
        bid_volume_sum = sum(bid_volumes[:depth])

        # 前 depth 档卖盘总量
        ask_volume_sum = sum(ask_volumes[:depth])

        # 买卖盘总量
        total_volume = bid_volume_sum + ask_volume_sum

        # 总量为 0，不能计算 imbalance
        if total_volume <= 0:
            return False

        # 盘口不平衡程度
        # > 0 表示买盘更厚
        # < 0 表示卖盘更厚
        imbalance = (bid_volume_sum - ask_volume_sum) / total_volume

        # 绝对值不能超过最大允许值
        # 如果 abs(imbalance) 太大，说明盘口一边倒，不适合做市
        return abs(imbalance) <= max_imbalance

    def filter_by_position(
            self,
            buy_quotes: list[dict],  # 当前准备挂出的买单报价列表
            sell_quotes: list[dict],  # 当前准备挂出的卖单报价列表
            pos: float,  # 当前持仓，正数表示多头，负数表示空头
            max_position: float  # 最大允许持仓
    ) -> tuple[list[dict], list[dict]]:
        """
        根据当前持仓过滤报价。
        这是硬风控：仓位到上限后，直接砍掉会继续加仓的一边报价。
        """

        # 最大持仓参数不合法时，直接不允许报价
        if max_position <= 0:
            return [], []

        # 如果当前多头已经达到或超过上限，
        # 就不能继续挂买单，否则买单成交后会让多头更大
        if pos >= max_position:
            buy_quotes = []

        # 如果当前空头已经达到或超过上限，
        # 就不能继续挂卖单，否则卖单成交后会让空头更大
        if pos <= -max_position:
            sell_quotes = []

        # 返回过滤后的买卖报价
        return buy_quotes, sell_quotes


class QuoteEngine:
    def __init__(self) -> None:
        self.current_buy_quotes: list[dict] = []
        self.current_sell_quotes: list[dict] = []

    def generate_quotes(
            self,  # 当前 QuoteEngine 对象自己
            fair_price: float,  # 做市基准价，报价围绕它上下展开
            price_tick: float,  # 最小变动价位，比如 1、0.2、0.005
            quote_levels: int,  # 报价档数，比如 3 表示买卖各挂 3 档
            order_volume: float,  # 每一笔报价的手数
            quote_mode: str = "tick",  # 报价模式，"tick" 表示按跳数报价，"percent" 表示按百分比报价
            spread_tick: int = 1,  # tick 模式下，第一档距离基准价几个 tick
            level_interval_tick: int = 1,  # tick 模式下，每档之间间隔几个 tick
            spread_percent: float = 0.0002,  # percent 模式下，第一档距离基准价的百分比
            level_interval_percent: float = 0.0001,  # percent 模式下，每档之间增加的百分比
            split_count: int = 1,  # 每一档拆成几笔单
            snapshot: dict | None = None,  # 当前盘口快照，里面有 bid1、ask1 等行情数据
            passive: bool = True,  # 是否被动报价；True 表示买价不高于买一，卖价不低于卖一
    ) -> tuple[list[dict], list[dict]]:  # 返回两个列表：买报价列表、卖报价列表
        if fair_price <= 0:
            print(f"生成报价失败：fair_price 不合法，当前 fair_price={fair_price}")
            return [], []

        if price_tick <= 0:
            print(f"生成报价失败：price_tick 不合法，当前 price_tick={price_tick}")
            return [], []

        if quote_levels <= 0:
            print(f"生成报价失败：quote_levels 不合法，当前 quote_levels={quote_levels}")
            return [], []

        if order_volume <= 0:
            print(f"生成报价失败：order_volume 不合法，当前 order_volume={order_volume}")
            return [], []

        if split_count <= 0:
            print(f"生成报价失败：split_count 不合法，当前 split_count={split_count}")
            return [], []

        quote_levels = min(quote_levels, 5)

        buy_quotes: list[dict] = []
        sell_quotes: list[dict] = []
        """
        buy_quotes = [
    {
        "side": "buy",
        "level": 1,
        "order_index": 1,
        "price": 3999,
        "volume": 1,
        "quote_mode": "tick",
        "offset_value": 1,
    },
    {
        "side": "buy",
        "level": 2,
        "order_index": 1,
        "price": 3998,
        "volume": 1,
        "quote_mode": "tick",
        "offset_value": 2,
    },
    {
        "side": "buy",
        "level": 3,
        "order_index": 1,
        "price": 3997,
        "volume": 1,
        "quote_mode": "tick",
        "offset_value": 3,
    },
]
        """

        # 每一档单独计算，每一次循环就是一档报价
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

    # 在generate_quotes()方法中，_calculate_tick_quote_price()方法用于计算每一档的报价价格。
    def _calculate_tick_quote_price(self, fair_price: float, price_tick: float, level: int, spread_tick: int,
                                    level_interval_tick: int, ) -> tuple[float, float, float]:
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

    # 在generate_quotes()方法中，_calculate_percent_quote_price()方法用于计算每一档的报价价格。
    def _calculate_percent_quote_price(self, fair_price: float, price_tick: float, level: int, spread_percent: float,
                                       level_interval_percent: float, ) -> tuple[float, float, float]:
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

    # floor_to_tick：往下取合法价格，买单常用
    def floor_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return math.floor(price / price_tick) * price_tick

    # ceil_to_tick：往上取合法价格，卖单常用
    def ceil_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return math.ceil(price / price_tick) * price_tick

    # round_to_tick：就近取合法价格，基准价常用
    def round_to_tick(self, price: float, price_tick: float) -> float:
        if price_tick <= 0:
            return price

        return round(price / price_tick) * price_tick

    # 用来对比当前报价和InventorySkewEngine处理过后的新报价的偏差是多少，偏差过多的话决定是否要重新报价

    def need_requote(self,
                     new_buy_quotes: list[dict],  # 新生成的买单报价列表，可能已经经过库存偏移调整
                     new_sell_quotes: list[dict],  # 新生成的卖单报价列表，可能已经经过库存偏移调整
                     price_tick: float,  # 合约最小变动价位，用来计算价格容忍范围
                     update_tolerance: int,  # 报价更新容忍度，单位是 tick
                     ) -> bool:  # 返回 True 表示需要撤单重挂，False 表示不需要
        # 如果最小变动价位不合法，就无法判断价格变化，直接不重挂
        if price_tick <= 0:
            return False

        # 如果容忍度写成负数，就修正为 0
        if update_tolerance < 0:
            update_tolerance = 0

        # 把“几个 tick 的容忍度”换算成具体价格差
        # 例如 price_tick=1，update_tolerance=2，则 tolerance_price=2
        tolerance_price = update_tolerance * price_tick

        # 如果新买单数量和当前旧买单数量不一致，说明报价结构变了，需要重挂
        if len(new_buy_quotes) != len(self.current_buy_quotes):
            return True

        # 如果新卖单数量和当前旧卖单数量不一致，也需要重挂
        if len(new_sell_quotes) != len(self.current_sell_quotes):
            return True

        # 逐个比较旧买单和新买单
        for old_quote, new_quote in zip(self.current_buy_quotes, new_buy_quotes):
            old_price = old_quote["price"]  # 当前旧买单价格
            new_price = new_quote["price"]  # 新生成买单价格
            old_volume = old_quote["volume"]  # 当前旧买单手数
            new_volume = new_quote["volume"]  # 新生成买单手数

            # 如果新旧买单价格差超过容忍范围，需要撤单重挂
            if abs(new_price - old_price) > tolerance_price:
                return True

            # 如果买单手数变了，也需要撤单重挂
            if new_volume != old_volume:
                return True

        # 逐个比较旧卖单和新卖单
        for old_quote, new_quote in zip(self.current_sell_quotes, new_sell_quotes):
            old_price = old_quote["price"]  # 当前旧卖单价格
            new_price = new_quote["price"]  # 新生成卖单价格
            old_volume = old_quote["volume"]  # 当前旧卖单手数
            new_volume = new_quote["volume"]  # 新生成卖单手数

            # 如果新旧卖单价格差超过容忍范围，需要撤单重挂
            if abs(new_price - old_price) > tolerance_price:
                return True

            # 如果卖单手数变了，也需要撤单重挂
            if new_volume != old_volume:
                return True

        # 如果数量、价格、手数都没明显变化，就不需要撤单重挂
        return False

    def update_current_quotes(
            self,
            buy_quotes: list[dict],
            sell_quotes: list[dict],
    ) -> None:
        self.current_buy_quotes: list[dict] = [quote.copy() for quote in buy_quotes]
        self.current_sell_quotes: list[dict] = [quote.copy() for quote in sell_quotes]

    def clear_current_quotes(self) -> None:
        self.current_buy_quotes: list[dict] = []
        self.current_sell_quotes: list[dict] = []


class InventorySkewEngine:
    def __init__(self) -> None:  # 初始化库存偏移引擎对象
        self.last_skew_tick: int = 0  # 记录上一次报价偏移了多少个 tick
        self.last_pos_ratio: float = 0.0  # 记录上一次当前持仓占最大持仓的比例

    def apply_skew(  # 对买卖报价应用库存偏移
            self,  # 类实例本身，用来访问成员变量和方法
            buy_quotes: list[dict],  # 原始买单报价列表，每个元素通常是一个报价字典
            sell_quotes: list[dict],  # 原始卖单报价列表，每个元素通常是一个报价字典
            pos: float,  # 当前净持仓，正数表示多头，负数表示空头
            max_position: float,  # 最大允许持仓，用来衡量当前库存压力
            price_tick: float,  # 合约最小变动价位，用来计算价格偏移幅度
            max_skew_tick: int = 3,  # 最大允许偏移 tick 数，默认最多偏移 3 个 tick
            snapshot: dict | None = None,  # 当前行情快照，可用于获取 bid1、ask1 等盘口价格
            passive: bool = True,  # 是否保持被动挂单，True 表示尽量不主动吃单
    ) -> tuple[list[dict], list[dict]]:  # 返回调整后的买单列表和卖单列表
        if not buy_quotes and not sell_quotes:
            # 如果买卖报价列表都为空，无需进行偏移处理，直接返回
            return buy_quotes, sell_quotes

        if max_position <= 0:
            # 如果最大持仓限制无效（小于等于0），无法计算持仓比例，直接返回原始报价
            return buy_quotes, sell_quotes

        if price_tick <= 0:
            # 如果最小价格变动单位无效（小于等于0），无法计算价格偏移，直接返回原始报价
            return buy_quotes, sell_quotes

        if max_skew_tick <= 0:
            # 如果最大偏移tick数无效（小于等于0），重置偏移状态并返回原始报价
            self.last_skew_tick = 0
            self.last_pos_ratio = 0.0
            return buy_quotes, sell_quotes

        # 计算当前持仓占最大持仓的比例，范围在[-1, 1]之间
        pos_ratio = self.calculate_pos_ratio(pos, max_position)

        # 根据持仓比例计算需要偏移的tick数量
        skew_tick = self.calculate_skew_tick(pos_ratio, max_skew_tick)

        # 保存当前的持仓比例和偏移tick数，用于后续跟踪和调试
        self.last_pos_ratio = pos_ratio
        self.last_skew_tick = skew_tick

        # 深拷贝买卖报价列表，避免修改原始数据，为后续价格调整做准备
        adjusted_buy_quotes = [quote.copy() for quote in buy_quotes]
        adjusted_sell_quotes = [quote.copy() for quote in sell_quotes]

        # 如果需要偏移的tick数大于0，根据持仓方向调整报价
        if skew_tick > 0:
            if pos > 0:
                # 多头持仓：买卖报价都向下偏移，促进卖出、抑制买入，降低多头仓位
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
                # 空头持仓：买卖报价都向上偏移，促进买入、抑制卖出，降低空头仓位
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

        # 如果启用被动模式且有行情快照，应用被动挂单限制，避免主动吃单
        if passive and snapshot:
            adjusted_buy_quotes, adjusted_sell_quotes = self.apply_passive_limit(
                buy_quotes=adjusted_buy_quotes,
                sell_quotes=adjusted_sell_quotes,
                snapshot=snapshot,
            )

        # 返回经过库存偏移和被动限制处理后的最终报价
        return adjusted_buy_quotes, adjusted_sell_quotes

    # 计算持仓比例，将实际持仓标准化到[-1, 1]区间
    def calculate_pos_ratio(
            self,
            pos: float,
            max_position: float,
    ) -> float:

        # 如果最大持仓限制无效，返回0表示无偏移
        if max_position <= 0:
            return 0.0

        # 计算持仓比例：正数表示多头，负数表示空头
        pos_ratio = pos / max_position

        # 限制比例上限为1.0（防止超出最大持仓时过度偏移）
        if pos_ratio > 1:
            return 1.0

        # 限制比例下限为-1.0（防止超出最大持仓时过度偏移）
        if pos_ratio < -1:
            return -1.0

        # 返回标准化后的持仓比例
        return pos_ratio

    def calculate_skew_tick(
            self,
            pos_ratio: float,
            max_skew_tick: int,
    ) -> int:
        """根据持仓比例计算需要偏移的tick数量"""
        # 如果最大偏移tick数无效，返回0表示不偏移
        if max_skew_tick <= 0:
            return 0

        # 偏移量与持仓比例的绝对值成正比，持仓越大偏移越多
        return round(abs(pos_ratio) * max_skew_tick)

    def move_quotes(
            self,
            quotes: list[dict],
            price_tick: float,
            skew_tick: int,
    ) -> list[dict]:
        """对报价列表应用价格偏移"""
        adjusted_quotes: list[dict] = []

        for quote in quotes:
            # 复制报价字典，避免修改原始数据
            adjusted_quote = quote.copy()

            # 计算偏移后的价格：原价格 + (偏移tick数 × 最小变动价位)
            adjusted_price = adjusted_quote["price"] + skew_tick * price_tick

            # 过滤掉价格为负或零的无效报价
            if adjusted_price <= 0:
                continue

            # 更新报价价格和记录偏移tick数
            adjusted_quote["price"] = adjusted_price
            adjusted_quote["skew_tick"] = skew_tick

            adjusted_quotes.append(adjusted_quote)

        # 返回调整后的报价列表（可能因价格无效而减少）
        return adjusted_quotes

    def apply_passive_limit(
            self,
            buy_quotes: list[dict],
            sell_quotes: list[dict],
            snapshot: dict,
    ) -> tuple[list[dict], list[dict]]:
        """应用被动挂单限制，确保报价不会主动吃单"""
        # 获取市场最优买卖价
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]

        adjusted_buy_quotes: list[dict] = []
        adjusted_sell_quotes: list[dict] = []

        # 处理买单：确保买单价格不超过市场买一价，保持被动排队
        for quote in buy_quotes:
            adjusted_quote = quote.copy()

            if bid1 > 0:
                # 取较小值：如果计算的买价高于bid1，则降为bid1，避免主动吃卖单
                adjusted_quote["price"] = min(adjusted_quote["price"], bid1)

            adjusted_buy_quotes.append(adjusted_quote)

        # 处理卖单：确保卖单价格不低于市场卖一价，保持被动排队
        for quote in sell_quotes:
            adjusted_quote = quote.copy()

            if ask1 > 0:
                # 取较大值：如果计算的卖价低于ask1，则升为ask1，避免主动吃买单
                adjusted_quote["price"] = max(adjusted_quote["price"], ask1)

            adjusted_sell_quotes.append(adjusted_quote)

        # 返回经过被动限制的买卖报价
        return adjusted_buy_quotes, adjusted_sell_quotes

    """
    #limit2 相当于虽然能保持档位间距，但会额外把报价推远，可能降低成交概率。 又重新算了一遍各档位，感觉有点过于保守了。
    def apply_passive_limit2(
        self,
        buy_quotes: list[dict],
        sell_quotes: list[dict],
        snapshot: dict,
        price_tick: float,
    ) -> tuple[list[dict], list[dict]]:
        #应用被动挂单限制，确保报价不会主动吃单，同时保持多档报价间距

        # 获取市场最优买卖价
        bid1 = snapshot["bid1"]
        ask1 = snapshot["ask1"]

        adjusted_buy_quotes: list[dict] = []
        adjusted_sell_quotes: list[dict] = []

        # 如果 price_tick 不合法，就退回到原来的简单 passive 限制
        if price_tick <= 0:
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

        # 处理买单：
        # 第 1 档买单最多挂在 bid1
        # 第 2 档买单最多挂在 bid1 - 1 * price_tick
        # 第 3 档买单最多挂在 bid1 - 2 * price_tick
        for index, quote in enumerate(buy_quotes):
            adjusted_quote = quote.copy()

            if bid1 > 0:
                max_buy_price = bid1 - index * price_tick
                adjusted_quote["price"] = min(adjusted_quote["price"], max_buy_price)

            adjusted_buy_quotes.append(adjusted_quote)

        # 处理卖单：
        # 第 1 档卖单最低挂在 ask1
        # 第 2 档卖单最低挂在 ask1 + 1 * price_tick
        # 第 3 档卖单最低挂在 ask1 + 2 * price_tick
        for index, quote in enumerate(sell_quotes):
            adjusted_quote = quote.copy()

            if ask1 > 0:
                min_sell_price = ask1 + index * price_tick
                adjusted_quote["price"] = max(adjusted_quote["price"], min_sell_price)

            adjusted_sell_quotes.append(adjusted_quote)

        # 返回经过 passive 限制，并保持档位间距后的买卖报价
        return adjusted_buy_quotes, adjusted_sell_quotes
    """

    def get_last_skew_tick(self) -> int:
        """获取上一次应用的库存偏移tick数，用于监控和调试"""
        return self.last_skew_tick

    def get_last_pos_ratio(self) -> float:
        """获取上一次的持仓比例，用于监控当前库存风险程度"""
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
            # abs为绝对值的意思
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

    # 以略低于买一价的价格挂单，提高成交优先级，快速平掉多头仓位
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

    # 以略高于卖一价的价格挂单，提高成交优先级，快速平掉空头仓位
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
        """更新最近一次强制平仓操作的记录"""
        self.last_hedge_action = hedge_order["action"]
        self.last_hedge_price = hedge_order["price"]
        self.last_hedge_volume = hedge_order["volume"]

    def clear_last_hedge(self) -> None:
        """清空强制平仓记录，重置为初始状态"""
        self.last_hedge_action = ""
        self.last_hedge_price = 0.0
        self.last_hedge_volume = 0.0

    def get_last_hedge_action(self) -> str:
        """获取最近一次强制平仓的操作类型"""
        return self.last_hedge_action

    def get_last_hedge_price(self) -> float:
        """获取最近一次强制平仓的价格"""
        return self.last_hedge_price

    def get_last_hedge_volume(self) -> float:
        """获取最近一次强制平仓的数量"""
        return self.last_hedge_volume


# 主策略, 继承CtaTemplate
class CancelAdvancedOrder(CtaTemplate):
    """Order模式通用做市策略"""

    author = "Morgan"
    # =====================
    # 策略参数
    # =====================
    pricing_method: str = "depth_weighted"
    pricing_depth: int = 5

    quote_mode: str = "tick"

    # 扩大报价档位，提高报价深度
    quote_levels: int = 3
    order_volume: float = 1

    # 报价稍微远一点，降低成交概率，提高挂单存活时间
    spread_tick: int = 3
    level_interval_tick: int = 2

    spread_percent: float = 0.0002
    level_interval_percent: float = 0.0001

    split_count: int = 1

    # 大幅提高容忍度，减少因为价格小幅变化就撤单
    update_tolerance: int = 20
    # 连续风控失败多少次才撤单，避免一个异常 tick 就撤单
    max_risk_fail_count: int = 3

    # 普通做市单最短挂单时间，没挂够不允许因为报价变化撤单
    min_quote_life_seconds: float = 5.0
    # 放宽风控，避免盘口短暂变化就撤单
    min_depth: int = 1
    min_spread_tick: int = 1
    depth_check_level: int = 3
    min_depth_volume: float = 1
    max_imbalance: float = 0.95

    # 放宽库存空间，减少强制对冲触发
    max_position: float = 8
    max_skew_tick: int = 2

    enable_hedge: bool = True

    # 提高触发强制对冲阈值，避免太早进入 hedging
    hedge_threshold: float = 6

    # 每次对冲 2 手
    hedge_volume: float = 2

    # 对冲单稍微激进，防止 hedge 挂死
    hedge_price_tick: int = 2

    # 重点：成交后不撤普通报价
    cancel_on_trade: bool = False

    # 继续保持被动报价，减少主动成交
    passive_quote: bool = True

    exp_depth_decay: float = 0.6
    use_ema_smoothing: bool = True
    ema_alpha: float = 0.2
    # =====================
    # 策略变量
    # =====================

    price_tick: float = 0.0
    contract_size: int = 0

    bid1: float = 0.0
    ask1: float = 0.0
    market_spread: float = 0.0
    valid_depth: int = 0

    fair_price: float = 0.0



    active_order_count: int = 0
    mm_order_count: int = 0
    hedge_order_count: int = 0

    trade_count: int = 0

    last_skew_tick: int = 0
    last_pos_ratio: float = 0.0

    last_hedge_action: str = ""
    last_hedge_price: float = 0.0
    last_hedge_volume: float = 0.0

    hedging: bool = False
    # 这两个 list 是给 vn.py 的策略框架识别用的。
    parameters = [
        "pricing_method",
        "pricing_depth",

        "exp_depth_decay",
        "use_ema_smoothing",
        "ema_alpha",

        "quote_mode",
        "quote_levels",
        "order_volume",

        "spread_tick",
        "level_interval_tick",

        "spread_percent",
        "level_interval_percent",

        "split_count",
        "update_tolerance",

        "max_risk_fail_count",
        "min_quote_life_seconds",

        "min_depth",
        "min_spread_tick",
        "depth_check_level",
        "min_depth_volume",
        "max_imbalance",

        "max_position",
        "max_skew_tick",

        "enable_hedge",
        "hedge_threshold",
        "hedge_volume",
        "hedge_price_tick",

        "cancel_on_trade",
        "passive_quote",
    ]
    # 这两个 list 是给 vn.py 的策略框架识别用的。
    variables = [
        "price_tick",
        "contract_size",

        "bid1",
        "ask1",
        "market_spread",
        "valid_depth",

        "fair_price",

        "active_order_count",
        "mm_order_count",
        "hedge_order_count",
        "trade_count",

        "last_skew_tick",
        "last_pos_ratio",

        "last_hedge_action",
        "last_hedge_price",
        "last_hedge_volume",

        "hedging",
    ]

    def __init__(
            self,
            cta_engine,
            strategy_name: str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        # 各个功能模块
        self.market_data = MarketDataManager()
        self.pricing_engine = PricingEngine()
        self.quote_engine = QuoteEngine()
        self.inventory_skew_engine = InventorySkewEngine()
        self.hedge_engine = HedgeEngine()
        self.quote_risk_filter = QuoteRiskFilter()

        # 全部订单记录
        self.orders: dict[str, OrderData] = {}

        # 普通做市订单 ID
        self.mm_orderids: set[str] = set()
        # 强制对冲订单 ID
        self.hedge_orderids: set[str] = set()
        # 记录每个普通做市订单对应的报价信息
        # key: vt_orderid
        # value: quote dict + 当时行情深度信息
        self.order_quote_info: dict[str, dict] = {}
        # 记录每一笔成交明细，最后导出 CSV
        # 记录每一笔成交明细，最后导出 CSV
        self.trade_records: list[dict] = []

        # 记录普通做市挂单明细，最后导出 CSV
        self.order_records: list[dict] = []

        # 记录强制对冲单明细，最后导出 CSV
        self.hedge_records: list[dict] = []

        # 记录做市义务指标，最后导出 CSV
        self.quote_obligation_records: list[dict] = []
        # 连续风控失败次数
        self.risk_fail_count: int = 0

        # 最近一次普通做市发单时间
        self.last_mm_order_time = None
        # 自定义调试日志文件路径
        self.debug_log_file = Path(
            rf"C:\Users\ultra\Documents\New project\market_maker\{self.strategy_name}_debug_log.txt"
        )
    # =====================
    # 生命周期函数
    # =====================

    def on_init(self) -> None:
        self.write_log("Order做市策略初始化")
        self.put_event()

    def on_start(self) -> None:
        self.write_log("Order做市策略启动")

        # 获取合约最小变动价位
        self.price_tick = self.get_pricetick()

        # 获取合约乘数
        self.contract_size = self.get_size()

        # 重置定价引擎状态
        # 主要是清空 EMA 的历史 fair_price，避免上一次运行残留影响本次回测/实盘
        self.pricing_engine.reset()

        # 清空当前报价缓存
        self.quote_engine.clear_current_quotes()

        # 清空订单记录
        self.orders.clear()

        # 清空普通做市订单 ID
        self.mm_orderids.clear()

        # 清空强制对冲订单 ID
        self.hedge_orderids.clear()
        # 清空订单报价档位映射
        self.order_quote_info.clear()
        self.trade_records.clear()
        self.order_records.clear()
        self.hedge_records.clear()
        self.quote_obligation_records.clear()
        self.risk_fail_count = 0
        self.last_mm_order_time = None
        # 清空最近一次强制对冲记录
        self.hedge_engine.clear_last_hedge()

        # 启动时默认不处于强制对冲状态
        self.hedging = False

        # 推送变量更新到界面
        self.put_event()

    def on_stop(self) -> None:
        self.write_log("Order做市策略停止")

        # 停止策略时导出各类报告
        self.export_trade_records()
        self.export_order_records()
        self.export_hedge_records()
        self.export_quote_obligation_records()
        self.export_summary_report()
        self.cancel_all()

        self.quote_engine.clear_current_quotes()

        self.orders.clear()
        self.mm_orderids.clear()
        self.hedge_orderids.clear()
        self.order_quote_info.clear()
        self.trade_records.clear()
        self.order_records.clear()
        self.hedge_records.clear()
        self.quote_obligation_records.clear()
        self.hedging = False

        self.put_event()

    # =====================
    # on_tick：行情来了，负责普通做市报价
    # =====================

    def on_tick(self, tick: TickData) -> None:
        """
        行情事件。

        主要负责：
        1. 更新行情快照；
        2. 检查行情是否适合做市；
        3. 计算基准价；
        4. 生成原始报价；
        5. 库存偏移；
        6. 仓位过滤；
        7. 撤旧普通单，发新普通单。
        """

        snapshot = self.market_data.update_tick(tick)

        self.bid1 = snapshot["bid1"]
        self.ask1 = snapshot["ask1"]
        self.market_spread = snapshot["market_spread"]
        self.valid_depth = snapshot["valid_depth"]

        if self.price_tick <= 0:
            self.price_tick = self.get_pricetick()

        # 先检查强制对冲状态是否可以解除
        self.check_hedging_recovery()

        # 如果仍然正在强制对冲，就不再发普通做市单
        if self.hedging:
            self.debug_print_no_quote(
                reason="HEDGING_BLOCKED",
                snapshot=snapshot,
            )
            self.put_event()
            return

        # 行情基础检查
        if not self.quote_risk_filter.check_market_data(snapshot):
            self.handle_risk_failed(snapshot, "MARKET_DATA_FAILED")
            self.put_event()
            return

        # 深度检查
        if not self.quote_risk_filter.check_depth(
                snapshot=snapshot,
                min_depth=self.min_depth,
        ):
            self.handle_risk_failed(snapshot, "DEPTH_FAILED")
            self.put_event()
            return

        # 价差检查
        if not self.quote_risk_filter.check_spread(
                snapshot=snapshot,
                price_tick=self.price_tick,
                min_spread_tick=self.min_spread_tick,
        ):
            self.handle_risk_failed(snapshot, "SPREAD_FAILED")
            self.put_event()
            return

        # 深度挂单量检查
        if not self.quote_risk_filter.check_depth_volume(
                snapshot=snapshot,
                depth=self.depth_check_level,
                min_depth_volume=self.min_depth_volume,
        ):
            self.handle_risk_failed(snapshot, "DEPTH_VOLUME_FAILED")
            self.put_event()
            return

        # 盘口不平衡检查
        if not self.quote_risk_filter.check_imbalance(
                snapshot=snapshot,
                max_imbalance=self.max_imbalance,
                depth=self.depth_check_level,
        ):
            self.handle_risk_failed(snapshot, "IMBALANCE_FAILED")
            self.put_event()
            return
        # 风控全部通过，清空连续失败计数
        self.risk_fail_count = 0
        # 计算基准价
        self.fair_price = self.pricing_engine.calculate_fair_price(
            snapshot=snapshot,
            pricing_method=self.pricing_method,
            depth=self.pricing_depth,
            exp_depth_decay=self.exp_depth_decay,
            use_ema_smoothing=self.use_ema_smoothing,
            ema_alpha=self.ema_alpha,
        )

        if self.fair_price <= 0:
            self.handle_risk_failed(snapshot, "FAIR_PRICE_FAILED")
            self.put_event()
            return

        # 生成原始报价
        buy_quotes, sell_quotes = self.quote_engine.generate_quotes(
            fair_price=self.fair_price,
            price_tick=self.price_tick,
            quote_levels=self.quote_levels,
            order_volume=self.order_volume,
            quote_mode=self.quote_mode,
            spread_tick=self.spread_tick,
            level_interval_tick=self.level_interval_tick,
            spread_percent=self.spread_percent,
            level_interval_percent=self.level_interval_percent,
            split_count=self.split_count,
            snapshot=snapshot,
            passive=self.passive_quote,
        )

        # 根据库存进行软偏移
        buy_quotes, sell_quotes = self.inventory_skew_engine.apply_skew(
            buy_quotes=buy_quotes,
            sell_quotes=sell_quotes,
            pos=self.pos,
            max_position=self.max_position,
            price_tick=self.price_tick,
            max_skew_tick=self.max_skew_tick,
            snapshot=snapshot,
            passive=self.passive_quote,
        )

        self.last_skew_tick = self.inventory_skew_engine.get_last_skew_tick()
        self.last_pos_ratio = self.inventory_skew_engine.get_last_pos_ratio()

        # 根据最大仓位做硬过滤
        buy_quotes, sell_quotes = self.quote_risk_filter.filter_by_position(
            buy_quotes=buy_quotes,
            sell_quotes=sell_quotes,
            pos=self.pos,
            max_position=self.max_position,
        )

        # 记录做市义务指标
        self.record_quote_obligation(
            snapshot=snapshot,
            buy_quotes=buy_quotes,
            sell_quotes=sell_quotes,
        )

        if not buy_quotes and not sell_quotes:
            self.debug_print_no_quote(
                reason="EMPTY_QUOTES_AFTER_POSITION_FILTER",
                snapshot=snapshot,
            )
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

        # 判断是否需要撤单重挂
        need_requote = self.quote_engine.need_requote(
            new_buy_quotes=buy_quotes,
            new_sell_quotes=sell_quotes,
            price_tick=self.price_tick,
            update_tolerance=self.update_tolerance,
        )

        if not need_requote:
            self.put_event()
            return

        # 如果已经有普通做市单，但还没挂满最短时间，不允许撤单重挂
        if self.mm_orderids and not self.can_requote_by_time(snapshot):
            self.put_event()
            return



        # 只撤普通做市单，不动 hedge 单
        self.cancel_market_making_orders()

        # 发新的普通买单

        for quote in buy_quotes:
            vt_orderids = self.buy(
                price=quote["price"],
                volume=quote["volume"],
            )
            self.mm_orderids.update(vt_orderids)

            for vt_orderid in vt_orderids:
                quote_info = quote.copy()
                quote_info["valid_depth"] = self.valid_depth
                quote_info["quote_levels"] = self.quote_levels
                quote_info["pricing_depth"] = self.pricing_depth
                quote_info["fair_price"] = self.fair_price
                quote_info["bid1"] = self.bid1
                quote_info["ask1"] = self.ask1
                self.order_quote_info[vt_orderid] = quote_info

                self.order_records.append(
                    {
                        "datetime": snapshot["datetime"],
                        "vt_orderid": vt_orderid,
                        "vt_symbol": self.vt_symbol,
                        "order_type": "MM",
                        "side": quote.get("side"),
                        "level": quote.get("level"),
                        "order_index": quote.get("order_index"),
                        "order_price": quote.get("price"),
                        "order_volume": quote.get("volume"),
                        "quote_mode": quote.get("quote_mode"),
                        "offset_value": quote.get("offset_value"),
                        "quote_levels": self.quote_levels,
                        "pricing_depth": self.pricing_depth,
                        "valid_depth": self.valid_depth,
                        "fair_price": self.fair_price,
                        "bid1": self.bid1,
                        "ask1": self.ask1,
                        "pos_when_order": self.pos,
                    }
                )
        # 发新的普通卖空单
        # 发新的普通卖空单
        for quote in sell_quotes:
            vt_orderids = self.short(
                price=quote["price"],
                volume=quote["volume"],
            )
            self.mm_orderids.update(vt_orderids)

            for vt_orderid in vt_orderids:
                quote_info = quote.copy()
                quote_info["valid_depth"] = self.valid_depth
                quote_info["quote_levels"] = self.quote_levels
                quote_info["pricing_depth"] = self.pricing_depth
                quote_info["fair_price"] = self.fair_price
                quote_info["bid1"] = self.bid1
                quote_info["ask1"] = self.ask1
                self.order_quote_info[vt_orderid] = quote_info

                self.order_records.append(
                    {
                        "datetime": snapshot["datetime"],
                        "vt_orderid": vt_orderid,
                        "vt_symbol": self.vt_symbol,
                        "order_type": "MM",
                        "side": quote.get("side"),
                        "level": quote.get("level"),
                        "order_index": quote.get("order_index"),
                        "order_price": quote.get("price"),
                        "order_volume": quote.get("volume"),
                        "quote_mode": quote.get("quote_mode"),
                        "offset_value": quote.get("offset_value"),
                        "quote_levels": self.quote_levels,
                        "pricing_depth": self.pricing_depth,
                        "valid_depth": self.valid_depth,
                        "fair_price": self.fair_price,
                        "bid1": self.bid1,
                        "ask1": self.ask1,
                        "pos_when_order": self.pos,
                    }
                )
        # 更新当前报价缓存
        self.quote_engine.update_current_quotes(
            buy_quotes=buy_quotes,
            sell_quotes=sell_quotes,
        )

        # 记录本次普通做市发单时间，用于限制最短挂单时长
        self.last_mm_order_time = snapshot["datetime"]

        self.update_order_count()
        self.put_event()

    # =====================
    # on_trade：成交了，负责强制对冲检查
    # =====================

    def on_trade(self, trade: TradeData) -> None:
        """
        成交事件。

        主要负责：
        1. 记录成交次数；
        2. 成交后撤掉普通做市单；
        3. 检查是否触发强制对冲；
        4. 如果触发，就发强制平仓单。
        """

        self.trade_count += 1
        quote_info = self.order_quote_info.get(trade.vt_orderid)
        record = {
            "datetime": trade.datetime,
            "vt_orderid": trade.vt_orderid,
            "vt_symbol": trade.vt_symbol,
            "direction": trade.direction.value if hasattr(trade.direction, "value") else trade.direction,
            "offset": trade.offset.value if hasattr(trade.offset, "value") else trade.offset,
            "trade_price": trade.price,
            "trade_volume": trade.volume,

            # 报价相关信息
            "quote_side": quote_info.get("side") if quote_info else "",
            "quote_level": quote_info.get("level") if quote_info else "",
            "order_index": quote_info.get("order_index") if quote_info else "",
            "quote_price": quote_info.get("price") if quote_info else "",
            "quote_volume": quote_info.get("volume") if quote_info else "",
            "quote_mode": quote_info.get("quote_mode") if quote_info else "",
            "offset_value": quote_info.get("offset_value") if quote_info else "",

            # 深度与定价信息
            "quote_levels": quote_info.get("quote_levels") if quote_info else "",
            "pricing_depth": quote_info.get("pricing_depth") if quote_info else "",
            "valid_depth": quote_info.get("valid_depth") if quote_info else "",
            "fair_price": quote_info.get("fair_price") if quote_info else "",
            "bid1": quote_info.get("bid1") if quote_info else "",
            "ask1": quote_info.get("ask1") if quote_info else "",

            # 策略状态
            "pos_after_trade": self.pos,
            "trade_count": self.trade_count,
        }

        self.trade_records.append(record)


        if quote_info:
            self.write_log(
                f"普通做市成交："
                f"方向={quote_info.get('side')}, "
                f"成交价={trade.price}, "
                f"成交量={trade.volume}, "
                f"报价档位=第{quote_info.get('level')}档, "
                f"拆单序号={quote_info.get('order_index')}, "
                f"挂单价={quote_info.get('price')}, "
                f"报价模式={quote_info.get('quote_mode')}, "
                f"报价偏移={quote_info.get('offset_value')}, "
                f"策略报价深度={quote_info.get('quote_levels')}档, "
                f"定价使用深度={quote_info.get('pricing_depth')}档, "
                f"当时行情有效深度={quote_info.get('valid_depth')}档, "
                f"fair_price={quote_info.get('fair_price')}, "
                f"bid1={quote_info.get('bid1')}, "
                f"ask1={quote_info.get('ask1')}"
            )
        else:
            self.write_log(
                f"非普通做市订单成交或未找到报价信息："
                f"vt_orderid={trade.vt_orderid}, "
                f"price={trade.price}, volume={trade.volume}"
            )
        # 普通做市成交后，最好撤掉旧报价，等待下一个 tick 重新报价
        if self.cancel_on_trade:
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()

        # 检查是否需要强制对冲
        if self.enable_hedge:
            self.check_and_send_hedge_order()

        self.update_order_count()
        self.put_event()

    # =====================
    # on_order：订单状态变了，负责维护订单集合
    # =====================

    def on_order(self, order: OrderData) -> None:
        """
        订单事件。

        主要负责：
        1. 更新订单状态；
        2. 区分普通做市单和强制对冲单；
        3. 清理已经完成的订单；
        4. 如果强制对冲单结束，判断是否恢复普通做市。
        """

        self.orders[order.vt_orderid] = order

        if not order.is_active():
            self.mm_orderids.discard(order.vt_orderid)
            self.hedge_orderids.discard(order.vt_orderid)

        # 检查强制对冲状态是否可以解除
        self.check_hedging_recovery()

        self.update_order_count()
        self.put_event()

    # =====================
    # on_timer：定时检查，可选
    # =====================

    def on_timer(self) -> None:
        """
        定时事件。

        这里先保留简单版本。
        后面可以加：
        1. 普通订单超时撤单；
        2. 对冲订单超时重挂；
        3. 日志输出；
        4. 风控兜底。
        """

        self.update_order_count()
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder) -> None:
        self.put_event()

    # =====================
    # 辅助函数：撤普通做市单
    # =====================

    def cancel_market_making_orders(self) -> None:
        """
        只撤普通做市单，不撤强制对冲单。
        """

        for vt_orderid in list(self.mm_orderids):
            self.cancel_order(vt_orderid)

        self.mm_orderids.clear()
        self.quote_engine.clear_current_quotes()
        self.last_mm_order_time = None

    # =====================
    # 辅助函数：撤强制对冲单
    # =====================

    def cancel_hedge_orders(self) -> None:
        """
        只撤强制对冲单。
        """

        for vt_orderid in list(self.hedge_orderids):
            self.cancel_order(vt_orderid)

        self.hedge_orderids.clear()

    def debug_print_no_quote(
            self,
            reason: str,
            snapshot: dict,
    ) -> None:
        """
        记录为什么没有继续报价。
        不再 print，改成写入本地 debug_log.txt。
        """

        dt = snapshot.get("datetime")

        # 只重点记录 2025-03-03 11:50 之后，避免文件太大
        if dt and str(dt) < "2025-03-03 11:50:00":
            return

        bid_volumes = snapshot.get("bid_volumes", [])
        ask_volumes = snapshot.get("ask_volumes", [])

        depth = min(self.depth_check_level, snapshot.get("valid_depth", 0), 5)

        bid_volume_sum = sum(bid_volumes[:depth]) if depth > 0 else 0
        ask_volume_sum = sum(ask_volumes[:depth]) if depth > 0 else 0

        msg = (
            "\n========== NO QUOTE DEBUG =========="
            f"\nreason={reason}"
            f"\ndatetime={dt}"
            f"\npos={self.pos}"
            f"\nhedging={self.hedging}"
            f"\nhedge_orderids={list(self.hedge_orderids)}"
            f"\nhedge_threshold={self.hedge_threshold}"
            f"\nbid1={snapshot.get('bid1')}, ask1={snapshot.get('ask1')}"
            f"\nbid1_volume={snapshot.get('bid1_volume')}, ask1_volume={snapshot.get('ask1_volume')}"
            f"\nmarket_spread={snapshot.get('market_spread')}"
            f"\nprice_tick={self.price_tick}"
            f"\nvalid_depth={snapshot.get('valid_depth')}, min_depth={self.min_depth}"
            f"\ndepth_check_level={self.depth_check_level}, actual_check_depth={depth}"
            f"\nbid_volume_sum={bid_volume_sum}, ask_volume_sum={ask_volume_sum}, min_depth_volume={self.min_depth_volume}"
            f"\nmax_imbalance={self.max_imbalance}"
            f"\nfair_price={self.fair_price}"
            f"\nmm_orderids={list(self.mm_orderids)}"
            "\n====================================\n"
        )

        self.debug_log(msg)

    def debug_log(self, msg: str) -> None:
        """
        同时写入 vn.py 日志系统和本地 debug_log.txt 文件。
        """

        try:
            self.write_log(msg)
        except Exception:
            pass

        try:
            folder = Path(r"C:\Users\ultra\Documents\New project\market_maker")
            folder.mkdir(parents=True, exist_ok=True)

            with open(self.debug_log_file, mode="a", encoding="utf-8-sig") as f:
                f.write(str(msg) + "\n")
        except Exception:
            pass

    def handle_risk_failed(self, snapshot: dict, reason: str) -> None:
        """
        风控失败处理。
        不再单次失败就撤单，而是连续失败达到阈值后才撤单。
        """

        self.risk_fail_count += 1

        self.debug_print_no_quote(
            reason=f"{reason}_COUNT_{self.risk_fail_count}",
            snapshot=snapshot,
        )

        if self.risk_fail_count >= self.max_risk_fail_count:
            self.debug_log(
                f"连续风控失败达到阈值，撤普通做市单："
                f"datetime={snapshot['datetime']}, "
                f"reason={reason}, "
                f"risk_fail_count={self.risk_fail_count}, "
                f"max_risk_fail_count={self.max_risk_fail_count}"
            )

            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()

    def can_requote_by_time(self, snapshot: dict) -> bool:
        """
        判断普通做市单是否已经挂满最短时间。
        没挂满 min_quote_life_seconds，不允许因为报价变化撤单重挂。
        """

        if self.last_mm_order_time is None:
            return True

        current_datetime = snapshot["datetime"]

        try:
            live_seconds = (current_datetime - self.last_mm_order_time).total_seconds()
        except Exception:
            return True

        if live_seconds >= self.min_quote_life_seconds:
            return True

        self.debug_log(
            f"未达到最短挂单时间，不撤单重挂："
            f"datetime={current_datetime}, "
            f"live_seconds={live_seconds}, "
            f"min_quote_life_seconds={self.min_quote_life_seconds}"
        )

        return False
    def check_hedging_recovery(self) -> None:
        """
        检查强制对冲状态是否可以恢复。
        防止 hedge_orderids 残留导致策略一直卡在 hedging=True。
        """

        if not self.hedging:
            return

        # 如果仓位已经回到阈值以内，就允许恢复普通做市
        if abs(self.pos) < self.hedge_threshold:
            self.debug_log(
                "\n========== HEDGING RECOVERY =========="
                f"\npos={self.pos}"
                f"\nhedge_threshold={self.hedge_threshold}"
                f"\nremain_hedge_orderids={list(self.hedge_orderids)}"
                "\n======================================\n"
            )


            # 如果还有残留的 hedge 单 ID，尝试撤掉仍然活跃的
            for vt_orderid in list(self.hedge_orderids):
                order = self.orders.get(vt_orderid)

                if order and order.is_active():
                    self.cancel_order(vt_orderid)

            self.hedge_orderids.clear()
            self.hedging = False
            self.hedge_engine.clear_last_hedge()

            self.last_hedge_action = ""
            self.last_hedge_price = 0.0
            self.last_hedge_volume = 0.0

    # =====================
    # 辅助函数：检查并发送强制对冲单
    # =====================

    def check_and_send_hedge_order(self) -> None:
        """
        检查当前持仓是否超过强制对冲阈值。
        如果超过，就暂停普通做市，撤普通单，发强制平仓单。
        """

        snapshot = self.market_data.get_snapshot()

        hedge_order = self.hedge_engine.check_hedge(
            pos=self.pos,
            hedge_threshold=self.hedge_threshold,
            hedge_volume=self.hedge_volume,
            price_tick=self.price_tick,
            snapshot=snapshot,
            hedge_price_tick=self.hedge_price_tick,
        )

        if not hedge_order:
            return

        # 已经有强制对冲单在挂着，就不要重复发
        if self.hedge_orderids:
            return

        # 进入强制对冲状态
        self.hedging = True

        # 先撤普通做市单，避免一边对冲一边继续加仓
        self.cancel_market_making_orders()

        # 根据 hedge_order 发平仓单
        if hedge_order["action"] == "SELL_CLOSE":
            vt_orderids = self.sell(
                price=hedge_order["price"],
                volume=hedge_order["volume"],
            )
            self.hedge_orderids.update(vt_orderids)

        elif hedge_order["action"] == "BUY_CLOSE":
            vt_orderids = self.cover(
                price=hedge_order["price"],
                volume=hedge_order["volume"],
            )
            self.hedge_orderids.update(vt_orderids)

        else:
            return

        for vt_orderid in vt_orderids:
            self.hedge_records.append(
                {
                    "datetime": snapshot["datetime"],
                    "vt_orderid": vt_orderid,
                    "vt_symbol": self.vt_symbol,
                    "order_type": "HEDGE",
                    "hedge_action": hedge_order["action"],
                    "hedge_reason": hedge_order["reason"],
                    "hedge_price": hedge_order["price"],
                    "hedge_volume": hedge_order["volume"],
                    "pos_when_hedge": self.pos,
                    "hedge_threshold": self.hedge_threshold,
                    "hedge_price_tick": self.hedge_price_tick,
                    "bid1": snapshot["bid1"],
                    "ask1": snapshot["ask1"],
                    "fair_price": self.fair_price,
                    "valid_depth": self.valid_depth,
                    "market_spread": self.market_spread,
                }
            )

        self.last_hedge_action = self.hedge_engine.get_last_hedge_action()
        self.last_hedge_price = self.hedge_engine.get_last_hedge_price()
        self.last_hedge_volume = self.hedge_engine.get_last_hedge_volume()
        # 回测中可能出现 hedge 单瞬间成交，但 hedge_orderids 后加入导致状态残留
        # 所以发完 hedge 单后立刻做一次恢复检查
        self.check_hedging_recovery()
    # =====================
    # 辅助函数：更新订单数量
    # =====================
    def record_quote_obligation(
            self,
            snapshot: dict,
            buy_quotes: list[dict],
            sell_quotes: list[dict],
    ) -> None:
        """
        记录每次生成报价后的做市义务指标。

        注意：
        有效报价时长不是简单用“下一条记录时间 - 当前记录时间”无限累计。
        如果两条记录之间间隔过长，比如午休、夜盘间隔、跨日、行情断档，
        这段时间不能计入有效报价时长。
        """

        current_datetime = snapshot["datetime"]

        # 相邻报价记录最大允许间隔。
        # 超过这个值，认为中间报价状态不连续，不计入有效报价时长。
        max_quote_gap_seconds = 10.0

        # 先给上一条记录补持续时间
        if self.quote_obligation_records:
            last_record = self.quote_obligation_records[-1]
            last_datetime = last_record.get("datetime")

            try:
                raw_duration_seconds = (current_datetime - last_datetime).total_seconds()
            except Exception:
                raw_duration_seconds = 0.0

            # 默认不计入
            duration_seconds = 0.0
            effective_duration_seconds = 0.0

            # 只有同一天、且间隔不超过阈值，才认为报价连续
            same_day = str(current_datetime)[:10] == str(last_datetime)[:10]

            if (
                    raw_duration_seconds > 0
                    and raw_duration_seconds <= max_quote_gap_seconds
                    and same_day
            ):
                duration_seconds = raw_duration_seconds

                if last_record.get("has_two_sided_quote"):
                    effective_duration_seconds = raw_duration_seconds

            last_record["next_datetime"] = current_datetime
            last_record["duration_seconds"] = duration_seconds
            last_record["effective_quote_duration_seconds"] = effective_duration_seconds

        has_buy_quote = len(buy_quotes) > 0
        has_sell_quote = len(sell_quotes) > 0
        has_two_sided_quote = has_buy_quote and has_sell_quote

        best_buy_price = max([q["price"] for q in buy_quotes]) if buy_quotes else 0.0
        best_sell_price = min([q["price"] for q in sell_quotes]) if sell_quotes else 0.0

        if has_two_sided_quote and self.price_tick > 0:
            quote_spread = best_sell_price - best_buy_price
            quote_spread_tick = quote_spread / self.price_tick
        else:
            quote_spread = 0.0
            quote_spread_tick = 0.0

        buy_quote_volume = sum(q["volume"] for q in buy_quotes)
        sell_quote_volume = sum(q["volume"] for q in sell_quotes)

        record = {
            "datetime": current_datetime,
            "next_datetime": "",
            "duration_seconds": 0.0,
            "effective_quote_duration_seconds": 0.0,

            "vt_symbol": self.vt_symbol,

            "has_buy_quote": has_buy_quote,
            "has_sell_quote": has_sell_quote,
            "has_two_sided_quote": has_two_sided_quote,

            "best_buy_price": best_buy_price,
            "best_sell_price": best_sell_price,
            "quote_spread": quote_spread,
            "quote_spread_tick": quote_spread_tick,

            "buy_quote_count": len(buy_quotes),
            "sell_quote_count": len(sell_quotes),
            "total_quote_count": len(buy_quotes) + len(sell_quotes),
            "buy_quote_volume": buy_quote_volume,
            "sell_quote_volume": sell_quote_volume,
            "total_quote_volume": buy_quote_volume + sell_quote_volume,

            "quote_levels": self.quote_levels,
            "pricing_depth": self.pricing_depth,
            "valid_depth": self.valid_depth,
            "fair_price": self.fair_price,
            "bid1": self.bid1,
            "ask1": self.ask1,
            "market_spread": self.market_spread,
            "pos": self.pos,
            "hedging": self.hedging,
        }

        self.quote_obligation_records.append(record)

    def export_csv_with_chinese_header(
            self,
            filepath: Path,
            records: list[dict],
            header_map: dict,
    ) -> None:
        """
        按中文表头导出 CSV。
        records 内部仍然用英文 key，不影响代码逻辑。
        """

        if not records:
            return

        fieldnames = list(records[0].keys())

        with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)

            # 写中文表头
            chinese_headers = [
                header_map.get(field, field)
                for field in fieldnames
            ]
            writer.writerow(chinese_headers)

            # 写数据
            for record in records:
                writer.writerow([
                    record.get(field, "")
                    for field in fieldnames
                ])

    def export_trade_records(self) -> None:
        """
        导出成交明细到 CSV。
        """

        if not self.trade_records:
            self.write_log("没有成交记录，不导出成交报告")
            return

        folder = Path(r"C:\Users\ultra\Documents\New project\market_maker")
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{self.strategy_name}_trade_records.csv"
        filepath = folder / filename

        header_map = {
            "datetime": "成交时间",
            "vt_orderid": "订单编号",
            "vt_symbol": "合约代码",
            "direction": "成交方向",
            "offset": "开平",
            "trade_price": "成交价格",
            "trade_volume": "成交数量",

            "quote_side": "报价方向",
            "quote_level": "报价档位",
            "order_index": "拆单序号",
            "quote_price": "挂单价格",
            "quote_volume": "挂单数量",
            "quote_mode": "报价模式",
            "offset_value": "报价偏移",

            "quote_levels": "策略报价档数",
            "pricing_depth": "定价使用深度",
            "valid_depth": "行情有效深度",
            "fair_price": "基准价",
            "bid1": "买一价",
            "ask1": "卖一价",

            "pos_after_trade": "成交后持仓",
            "trade_count": "成交计数",
        }

        self.export_csv_with_chinese_header(
            filepath=filepath,
            records=self.trade_records,
            header_map=header_map,
        )

        self.write_log(f"成交报告已导出：{filepath}")

    def export_order_records(self) -> None:
        """
        导出普通做市挂单明细到 CSV。
        """

        if not self.order_records:
            self.write_log("没有普通做市挂单记录，不导出挂单报告")
            return

        folder = Path(r"C:\Users\ultra\Documents\New project\market_maker")
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{self.strategy_name}_order_records.csv"
        filepath = folder / filename

        header_map = {
            "datetime": "挂单时间",
            "vt_orderid": "订单编号",
            "vt_symbol": "合约代码",
            "order_type": "订单类型",
            "side": "报价方向",
            "level": "报价档位",
            "order_index": "拆单序号",
            "order_price": "挂单价格",
            "order_volume": "挂单数量",
            "quote_mode": "报价模式",
            "offset_value": "报价偏移",

            "quote_levels": "策略报价档数",
            "pricing_depth": "定价使用深度",
            "valid_depth": "行情有效深度",
            "fair_price": "基准价",
            "bid1": "买一价",
            "ask1": "卖一价",
            "pos_when_order": "挂单时持仓",
        }

        self.export_csv_with_chinese_header(
            filepath=filepath,
            records=self.order_records,
            header_map=header_map,
        )

        self.write_log(f"普通做市挂单报告已导出：{filepath}")

    def export_hedge_records(self) -> None:
        """
        导出强制对冲单明细到 CSV。
        """

        if not self.hedge_records:
            self.write_log("没有强制对冲记录，不导出对冲报告")
            return

        folder = Path(r"C:\Users\ultra\Documents\New project\market_maker")
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{self.strategy_name}_hedge_records.csv"
        filepath = folder / filename

        header_map = {
            "datetime": "对冲发单时间",
            "vt_orderid": "订单编号",
            "vt_symbol": "合约代码",
            "order_type": "订单类型",
            "hedge_action": "对冲动作",
            "hedge_reason": "对冲原因",
            "hedge_price": "对冲价格",
            "hedge_volume": "对冲数量",
            "pos_when_hedge": "对冲时持仓",
            "hedge_threshold": "对冲阈值",
            "hedge_price_tick": "对冲价格偏移tick",
            "bid1": "买一价",
            "ask1": "卖一价",
            "fair_price": "基准价",
            "valid_depth": "行情有效深度",
            "market_spread": "市场价差",
        }

        self.export_csv_with_chinese_header(
            filepath=filepath,
            records=self.hedge_records,
            header_map=header_map,
        )

        self.write_log(f"强制对冲报告已导出：{filepath}")

    def export_quote_obligation_records(self) -> None:
        """
        导出做市义务指标到 CSV。
        """

        if not self.quote_obligation_records:
            self.write_log("没有做市义务记录，不导出做市义务报告")
            return

        folder = Path(r"C:\Users\ultra\Documents\New project\market_maker")
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{self.strategy_name}_quote_obligation_records.csv"
        filepath = folder / filename

        header_map = {
            "datetime": "记录时间",
            "next_datetime": "下一记录时间",
            "duration_seconds": "持续时间_秒",
            "effective_quote_duration_seconds": "有效报价持续时间_秒",

            "vt_symbol": "合约代码",

            "has_buy_quote": "是否有买方报价",
            "has_sell_quote": "是否有卖方报价",
            "has_two_sided_quote": "是否双边报价",

            "best_buy_price": "最优买报价",
            "best_sell_price": "最优卖报价",
            "quote_spread": "报价价差",
            "quote_spread_tick": "报价价差_tick",

            "buy_quote_count": "买方报价笔数",
            "sell_quote_count": "卖方报价笔数",
            "total_quote_count": "总报价笔数",
            "buy_quote_volume": "买方报价深度",
            "sell_quote_volume": "卖方报价深度",
            "total_quote_volume": "总报价深度",

            "quote_levels": "策略报价档数",
            "pricing_depth": "定价使用深度",
            "valid_depth": "行情有效深度",
            "fair_price": "基准价",
            "bid1": "买一价",
            "ask1": "卖一价",
            "market_spread": "市场价差",
            "pos": "当前持仓",
            "hedging": "是否正在强制对冲",
        }

        self.export_csv_with_chinese_header(
            filepath=filepath,
            records=self.quote_obligation_records,
            header_map=header_map,
        )

        self.write_log(f"做市义务报告已导出：{filepath}")
    def update_order_count(self) -> None:
        self.mm_order_count = len(self.mm_orderids)
        self.hedge_order_count = len(self.hedge_orderids)
        self.active_order_count = self.mm_order_count + self.hedge_order_count

    def export_summary_report(self) -> None:
        """
        导出核心做市表现汇总报告。

        指标口径：
        1. 最优平均报价差：只统计双边有效报价时的 quote_spread
        2. 平均有效报价深度：只统计双边有效报价时的 total_quote_volume
        3. 平均有效报价时长：按交易日统计，每日累计双边有效报价时长，再取平均，单位小时
        4. 成交量：汇总成交数量
        """

        folder = Path(r"C:\Users\ultra\Documents\New project\market_maker")
        folder.mkdir(parents=True, exist_ok=True)

        filename = f"{self.strategy_name}_summary_report.csv"
        filepath = folder / filename

        records = self.quote_obligation_records

        # 只统计双边有效报价记录
        effective_records = [
            r for r in records
            if r.get("has_two_sided_quote")
        ]

        if effective_records:
            # 最优平均报价差，单位：元
            avg_best_quote_spread = (
                    sum(float(r.get("quote_spread", 0) or 0) for r in effective_records)
                    / len(effective_records)
            )

            # 平均有效报价深度，双边手数
            avg_effective_quote_depth = (
                    sum(float(r.get("total_quote_volume", 0) or 0) for r in effective_records)
                    / len(effective_records)
            )

            # =====================
            # 平均有效报价时长：按交易日累计，再取平均
            # =====================
            daily_effective_seconds: dict[str, float] = {}

            for r in effective_records:
                dt = r.get("datetime")
                duration = float(r.get("effective_quote_duration_seconds", 0) or 0)

                if not dt:
                    continue

                # 取日期，例如 2025-03-03
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

        # 成交量
        # 注意：如果是期货，这里通常是“手”；
        # 如果你要展示成“千克”，需要根据具体合约乘数换算。
        total_trade_volume = sum(
            float(r.get("trade_volume", 0) or 0)
            for r in self.trade_records
        )

        summary = {
            "席位简称": self.strategy_name,
            "最优平均报价差(元)": avg_best_quote_spread,
            "平均有效报价深度(双边手)": avg_effective_quote_depth,
            "平均有效报价时长(小时)": avg_effective_quote_duration_hours,
            "成交量": total_trade_volume,
        }

        with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
            writer.writeheader()
            writer.writerow(summary)

        self.write_log(f"核心做市表现汇总报告已导出：{filepath}")