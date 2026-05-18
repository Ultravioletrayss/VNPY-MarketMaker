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

    # 判断当前盘口是不是一边倒，如果太极端，就不要贸然做市。
    def get_order_book_imbalance(self, depth: int = 5) -> float:
        bid_volume_sum, ask_volume_sum = self.get_depth_volume(depth)
        total_volume = bid_volume_sum + ask_volume_sum

        if total_volume <= 0:
            return 0.0

        return (bid_volume_sum - ask_volume_sum) / total_volume

    # 获取ask1和bid1的中价
    def get_mid_price(self) -> float:
        if not self.is_valid():
            return 0.0

        return (self.bid1 + self.ask1) / 2

    # 根据买一卖一价格 + 买一卖一挂单量，估算出来的更合理的短期基准价。
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
    quote_levels: int = 1
    order_volume: float = 1

    spread_tick: int = 2
    level_interval_tick: int = 1

    spread_percent: float = 0.0002
    level_interval_percent: float = 0.0001

    split_count: int = 1
    update_tolerance: int = 2

    min_depth: int = 3
    min_spread_tick: int = 1
    depth_check_level: int = 5
    min_depth_volume: float = 30
    max_imbalance: float = 0.70

    max_position: float = 4
    max_skew_tick: int = 2

    enable_hedge: bool = True
    hedge_threshold: float = 3
    hedge_volume: float = 1
    hedge_price_tick: int = 0

    cancel_on_trade: bool = True
    passive_quote: bool = True

    exp_depth_decay: float = 0.6
    use_ema_smoothing: bool = True

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

        # 清空最近一次强制对冲记录
        self.hedge_engine.clear_last_hedge()

        # 启动时默认不处于强制对冲状态
        self.hedging = False

        # 推送变量更新到界面
        self.put_event()

    def on_stop(self) -> None:
        self.write_log("Order做市策略停止")

        self.cancel_all()

        self.quote_engine.clear_current_quotes()

        self.orders.clear()
        self.mm_orderids.clear()
        self.hedge_orderids.clear()

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

        # 如果正在强制对冲，就不再发普通做市单
        if self.hedging:
            self.put_event()
            return

        # 行情基础检查
        if not self.quote_risk_filter.check_market_data(snapshot):
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

        # 深度检查
        if not self.quote_risk_filter.check_depth(
                snapshot=snapshot,
                min_depth=self.min_depth,
        ):
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

        # 价差检查
        if not self.quote_risk_filter.check_spread(
                snapshot=snapshot,
                price_tick=self.price_tick,
                min_spread_tick=self.min_spread_tick,
        ):
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

        # 深度挂单量检查
        if not self.quote_risk_filter.check_depth_volume(
                snapshot=snapshot,
                depth=self.depth_check_level,
                min_depth_volume=self.min_depth_volume,
        ):
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

        # 盘口不平衡检查
        if not self.quote_risk_filter.check_imbalance(
                snapshot=snapshot,
                max_imbalance=self.max_imbalance,
                depth=self.depth_check_level,
        ):
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

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
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
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

        if not buy_quotes and not sell_quotes:
            self.cancel_market_making_orders()
            self.quote_engine.clear_current_quotes()
            self.put_event()
            return

        # 判断是否需要撤单重挂
        if not self.quote_engine.need_requote(
                new_buy_quotes=buy_quotes,
                new_sell_quotes=sell_quotes,
                price_tick=self.price_tick,
                update_tolerance=self.update_tolerance,
        ):
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

        # 发新的普通卖空单
        for quote in sell_quotes:
            vt_orderids = self.short(
                price=quote["price"],
                volume=quote["volume"],
            )
            self.mm_orderids.update(vt_orderids)

        # 更新当前报价缓存
        self.quote_engine.update_current_quotes(
            buy_quotes=buy_quotes,
            sell_quotes=sell_quotes,
        )

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

        # 如果没有正在挂的 hedge 单，说明强制对冲状态可以结束
        if self.hedging and not self.hedge_orderids:
            # 如果仓位已经回到强制对冲阈值以内，就恢复普通报价
            if abs(self.pos) < self.hedge_threshold:
                self.hedging = False
                self.hedge_engine.clear_last_hedge()

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

        self.last_hedge_action = self.hedge_engine.get_last_hedge_action()
        self.last_hedge_price = self.hedge_engine.get_last_hedge_price()
        self.last_hedge_volume = self.hedge_engine.get_last_hedge_volume()

    # =====================
    # 辅助函数：更新订单数量
    # =====================

    def update_order_count(self) -> None:
        self.mm_order_count = len(self.mm_orderids)
        self.hedge_order_count = len(self.hedge_orderids)
        self.active_order_count = self.mm_order_count + self.hedge_order_count