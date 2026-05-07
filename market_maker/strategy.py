from .config import Config
from .market_data import MarketData, MarketSnapshot
from .order_manager import OrderManager, TradingGateway
from .pricing_engine import PricingEngine
from .quote_engine import QuoteEngine
from .risk_manager import RiskManager
from .trade_manager import TradeManager


class MarketMakerStrategy:
    """Wires market data, pricing, quoting, order management, trade handling, and risk."""

    def __init__(self, config: Config, gateway: TradingGateway) -> None:
        self.config = config
        self.market_data = MarketData()
        self.pricing_engine = PricingEngine()
        self.quote_engine = QuoteEngine(config)
        self.order_manager = OrderManager(config, gateway)
        self.trade_manager = TradeManager()
        self.risk_manager = RiskManager(config)

    @property
    def position(self) -> int:
        return self.trade_manager.position

    def on_tick(self, tick: object) -> None:
        snapshot = self.market_data.update(tick)
        print(f"[TICK] bid1={snapshot.bid1} ask1={snapshot.ask1} last={snapshot.last_price} position={self.position}")

        if not self.risk_manager.check_market_data(snapshot):
            print("[RISK] invalid market data, cancel all orders")
            self.order_manager.cancel_all()
            return

        if not self.risk_manager.check_market_spread(snapshot):
            print("[RISK] market spread too small, cancel all orders")
            self.order_manager.cancel_all()
            return

        self.requote(snapshot)

    def on_trade(self, trade: object) -> None:
        self.trade_manager.update_position(trade)
        self.trade_manager.record_trade(trade)

        if self.risk_manager.is_position_too_large(self.position):
            print("[RISK] position limit reached, cancel all orders")
            self.order_manager.cancel_all()
            return

        if self.config.cancel_on_trade:
            print("[TRADE] cancel remaining orders after trade")
            self.order_manager.cancel_all()
            if self.market_data.snapshot:
                self.requote(self.market_data.snapshot)

    def on_order(self, order: object) -> None:
        self.order_manager.update_order_status(order)

    def requote(self, snapshot: MarketSnapshot) -> None:
        mid_price = self.pricing_engine.calculate_mid(snapshot)
        buy_quotes, sell_quotes = self.quote_engine.generate_quotes(mid_price, self.position)
        buy_quotes, sell_quotes = self.risk_manager.filter_quotes_by_position(
            buy_quotes,
            sell_quotes,
            self.position,
        )

        if not self.risk_manager.check_order_count(
            len(self.order_manager.active_orders),
            len(buy_quotes) + len(sell_quotes),
        ):
            print("[RISK] active order count limit reached, skip quoting")
            return

        print(f"[QUOTE] mid={mid_price} buy={buy_quotes} sell={sell_quotes}")
        self.order_manager.update_orders(buy_quotes, sell_quotes)

