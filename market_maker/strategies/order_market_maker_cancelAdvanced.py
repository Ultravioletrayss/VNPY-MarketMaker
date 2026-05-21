from vnpy_ctastrategy import (
    CtaTemplate,
    TickData,
    TradeData,
    OrderData,
    StopOrder,
)


# =========================================================
# 子模块类：先空着，后面逐步实现
# =========================================================

class PriceWindowManager:
    """窗口均价模块：维护最近 C 个最新价"""
    pass


class OrderBookProcessor:
    """盘口处理模块：扣除本方订单，识别非本方盘口和单边行情"""
    pass


class ScenarioSelector:
    """场景选择模块：根据 A/B/D 选择 1-8 档"""
    pass


class QuoteGenerator:
    """报价生成模块：根据 N/E/F 生成目标买卖报价"""
    pass


class RiskManager:
    """风控模块：废单风控、成交风控、价格笼子"""
    pass


class OrderManager:
    """订单管理模块：做市订单撤单、补单、重报、容忍度判断"""
    pass


class HedgeManager:
    """对冲模块：净买/净卖触发对冲、对冲撤补、对冲废单"""
    pass


class ReportManager:
    """报告模块：输出 tick 决策、订单、成交、汇总 CSV"""
    pass


# =========================================================
# 主策略类：继承 CtaTemplate
# =========================================================

class SgeMarketMakingStrategy(CtaTemplate):
    """上金所新做市策略"""

    author = "Morgan"

    class SgeMarketMakingStrategy(CtaTemplate):
        """上金所新做市策略"""

        author = "Morgan"

        # =====================
        # 策略参数：做市输入参数
        # =====================

        execution_time: str = "09:00:00.000,15:30:00.000"

        spread_threshold: float = 0.0  # A
        book_volume_threshold: int = 0  # B
        window_length: int = 10  # C
        window_diff_threshold: float = 0.0  # D

        quote_offset_tick_1: int = 1  # E1
        quote_offset_tick_2: int = 1
        quote_offset_tick_3: int = 1
        quote_offset_tick_4: int = 1
        quote_offset_tick_5: int = 1
        quote_offset_tick_6: int = 1
        quote_offset_tick_7: int = 1
        quote_offset_tick_8: int = 1

        quote_volume_1: int = 1  # F1
        quote_volume_2: int = 1
        quote_volume_3: int = 1
        quote_volume_4: int = 1
        quote_volume_5: int = 1
        quote_volume_6: int = 1
        quote_volume_7: int = 1
        quote_volume_8: int = 1

        quote_level_1: int = 1  # N1
        quote_level_2: int = 1
        quote_level_3: int = 1
        quote_level_4: int = 1
        quote_level_5: int = 1
        quote_level_6: int = 1
        quote_level_7: int = 1
        quote_level_8: int = 1

        open_close_mode: str = "自动"  # G
        quote_tolerance: float = 0.0  # H

        # =====================
        # 策略参数：做市废单响应
        # =====================

        mm_reject_enabled: bool = True
        mm_max_reject_count: int = 10

        # =====================
        # 策略参数：做市成交风控
        # =====================

        buy_trade_risk_enabled: bool = False
        buy_volume_limit: int = 0
        buy_amount_limit_wan: float = 0.0

        sell_trade_risk_enabled: bool = False
        sell_volume_limit: int = 0
        sell_amount_limit_wan: float = 0.0

        # =====================
        # 策略参数：价格笼子
        # =====================

        price_cage_unit: str = "元"

        buy_price_cage_enabled: bool = False
        buy_price_base_type: str = "lastPrice"
        buy_price_upper_offset: float = 0.0
        buy_price_lower_offset: float = 0.0

        sell_price_cage_enabled: bool = False
        sell_price_base_type: str = "lastPrice"
        sell_price_upper_offset: float = 0.0
        sell_price_lower_offset: float = 0.0

        # =====================
        # 策略参数：买入对冲风控
        # =====================

        buy_hedge_enabled: bool = False
        buy_hedge_net_volume: int = 0
        buy_hedge_group: str = ""
        buy_hedge_symbol: str = ""
        buy_hedge_direction: str = "卖"
        buy_hedge_offset: str = "自动"
        buy_hedge_price_type: str = "Bid1"
        buy_hedge_price_offset: float = 0.0
        buy_hedge_price_offset_unit: str = "元"

        # =====================
        # 策略参数：卖出对冲风控
        # =====================

        sell_hedge_enabled: bool = False
        sell_hedge_net_volume: int = 0
        sell_hedge_group: str = ""
        sell_hedge_symbol: str = ""
        sell_hedge_direction: str = "买"
        sell_hedge_offset: str = "自动"
        sell_hedge_price_type: str = "Ask1"
        sell_hedge_price_offset: float = 0.0
        sell_hedge_price_offset_unit: str = "元"

        # =====================
        # 策略参数：对冲交易参数
        # =====================

        hedge_reject_enabled: bool = True
        hedge_max_reject_count: int = 10
        hedge_scope: str = "自动"

        # 需求逻辑里有，但参数表未单独列出；实现撤补时建议保留
        hedge_wait_seconds: int = 3
        hedge_max_replace_count: int = 3




        

        # =====================
        # 策略变量
        # =====================

        price_tick: float = 0.0
        contract_size: int = 0

        last_price: float = 0.0

        other_bid1: float = 0.0
        other_ask1: float = 0.0
        other_bid1_volume: int = 0
        other_ask1_volume: int = 0

        market_spread: float = 0.0
        book_volume: int = 0

        window_avg: float = 0.0
        window_diff: float = 0.0
        own_spread: float = 0.0

        current_scenario_id: int = 0
        current_N: int = 0
        current_E: int = 0
        current_F: int = 0

        target_buy_price: float = 0.0
        target_sell_price: float = 0.0
        target_buy_volume: int = 0
        target_sell_volume: int = 0

        mm_active: bool = False
        strategy_stopped: bool = False
        stop_reason: str = ""

        active_order_count: int = 0
        mm_order_count: int = 0
        hedge_order_count: int = 0

        trade_count: int = 0

        net_buy_volume: int = 0
        net_sell_volume: int = 0
        net_buy_amount: float = 0.0
        net_sell_amount: float = 0.0

        mm_reject_count: int = 0
        hedge_reject_count: int = 0

        hedging: bool = False
        hedge_replace_count: int = 0

        last_hedge_action: str = ""
        last_hedge_price: float = 0.0
        last_hedge_volume: int = 0



    parameters = [
        # 做市参数
        "execution_time",
        "spread_threshold",
        "book_volume_threshold",
        "window_length",
        "window_diff_threshold",

        "quote_offset_tick_1",
        "quote_offset_tick_2",
        "quote_offset_tick_3",
        "quote_offset_tick_4",
        "quote_offset_tick_5",
        "quote_offset_tick_6",
        "quote_offset_tick_7",
        "quote_offset_tick_8",

        "quote_volume_1",
        "quote_volume_2",
        "quote_volume_3",
        "quote_volume_4",
        "quote_volume_5",
        "quote_volume_6",
        "quote_volume_7",
        "quote_volume_8",

        "quote_level_1",
        "quote_level_2",
        "quote_level_3",
        "quote_level_4",
        "quote_level_5",
        "quote_level_6",
        "quote_level_7",
        "quote_level_8",

        "open_close_mode",
        "quote_tolerance",

        # 做市废单
        "mm_reject_enabled",
        "mm_max_reject_count",

        # 成交风控
        "buy_trade_risk_enabled",
        "buy_volume_limit",
        "buy_amount_limit_wan",
        "sell_trade_risk_enabled",
        "sell_volume_limit",
        "sell_amount_limit_wan",

        # 价格笼子
        "price_cage_unit",
        "buy_price_cage_enabled",
        "buy_price_base_type",
        "buy_price_upper_offset",
        "buy_price_lower_offset",
        "sell_price_cage_enabled",
        "sell_price_base_type",
        "sell_price_upper_offset",
        "sell_price_lower_offset",

        # 买入对冲风控
        "buy_hedge_enabled",
        "buy_hedge_net_volume",
        "buy_hedge_group",
        "buy_hedge_symbol",
        "buy_hedge_direction",
        "buy_hedge_offset",
        "buy_hedge_price_type",
        "buy_hedge_price_offset",
        "buy_hedge_price_offset_unit",

        # 卖出对冲风控
        "sell_hedge_enabled",
        "sell_hedge_net_volume",
        "sell_hedge_group",
        "sell_hedge_symbol",
        "sell_hedge_direction",
        "sell_hedge_offset",
        "sell_hedge_price_type",
        "sell_hedge_price_offset",
        "sell_hedge_price_offset_unit",

        # 对冲交易参数
        "hedge_reject_enabled",
        "hedge_max_reject_count",
        "hedge_scope",
        "hedge_wait_seconds",
        "hedge_max_replace_count",
    ]

    # =====================
    # vn.py 变量列表：用于界面监控显示
    # =====================

    variables = [
        # 合约信息
        "price_tick",
        "contract_size",

        # 行情与输出指标
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
        "window_avg",
        "window_diff",
        "own_spread",
        "valid_depth",

        # 场景与报价
        "current_scenario_id",
        "current_N",
        "current_E",
        "current_F",
        "target_buy_price",
        "target_sell_price",
        "target_buy_volume",
        "target_sell_volume",

        # 状态与订单
        "mm_active",
        "strategy_stopped",
        "stop_reason",
        "active_order_count",
        "mm_order_count",
        "hedge_order_count",

        # 成交统计
        "trade_count",
        "buy_trade_volume",
        "sell_trade_volume",
        "buy_trade_amount",
        "sell_trade_amount",
        "net_buy_volume",
        "net_sell_volume",
        "net_buy_amount",
        "net_sell_amount",

        # 废单与对冲
        "mm_reject_count",
        "hedge_reject_count",
        "hedging",
        "hedge_replace_count",
        "last_hedge_action",
        "last_hedge_price",
        "last_hedge_volume",
    ]

    def __init__(
            self,
            cta_engine,
            strategy_name: str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        # =====================
        # 功能模块
        # =====================

        self.price_window_manager = PriceWindowManager()
        self.order_book_processor = OrderBookProcessor()
        self.scenario_selector = ScenarioSelector()
        self.quote_generator = QuoteGenerator()
        self.risk_manager = RiskManager()
        self.order_manager = OrderManager()
        self.hedge_manager = HedgeManager()
        self.report_manager = ReportManager()

        # =====================
        # 订单容器
        # =====================

        self.orders: dict[str, OrderData] = {}
        self.mm_orderids: set[str] = set()
        self.hedge_orderids: set[str] = set()

        # 最新行情
        self.last_tick: TickData | None = None

    # =====================
    # 生命周期函数：先留空
    # =====================

    def on_init(self) -> None:
        pass

    def on_start(self) -> None:
        pass

    def on_stop(self) -> None:
        pass

    def on_tick(self, tick: TickData) -> None:
        pass

    def on_order(self, order: OrderData) -> None:
        pass

    def on_trade(self, trade: TradeData) -> None:
        pass

    def on_timer(self) -> None:
        pass

    def on_stop_order(self, stop_order: StopOrder) -> None:
        pass