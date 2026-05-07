# SHFE Order-Mode Market Maker

This is a teaching implementation of a simplified vn.py-style order-mode market making strategy.
It uses normal buy and sell orders instead of exchange quote orders.

## Run the demo

```powershell
python -m market_maker.main
```

The demo shows:

- reading bid1, ask1, bid/ask volume, and last price
- calculating `mid = (bid1 + ask1) / 2`
- generating one buy quote and one sell quote
- cancelling and requoting after price moves more than the tolerance
- updating position after a trade
- cancelling and requoting after a trade

## Module layout

- `config.py`: strategy parameters
- `market_data.py`: five-level book snapshot storage
- `pricing_engine.py`: mid-price calculation, with an extension point for depth-adjusted pricing
- `quote_engine.py`: buy/sell quote generation and simple inventory skew
- `risk_manager.py`: market data, spread, position, and active-order checks
- `order_manager.py`: normal order send/cancel/status tracking
- `trade_manager.py`: trade records and net position updates
- `strategy.py`: main event loop with `on_tick`, `on_trade`, and `on_order`
- `vnpy_adapter_example.py`: adapter shape for wiring the code into a vn.py strategy class

## vn.py integration idea

Inside your vn.py strategy, create:

```python
config = Config(symbol=self.vt_symbol, exchange="SHFE")
gateway = VnpyGatewayAdapter(self)
engine = MarketMakerStrategy(config, gateway)
```

Then forward events:

```python
def on_tick(self, tick):
    engine.on_tick(tick)

def on_trade(self, trade):
    engine.on_trade(trade)

def on_order(self, order):
    engine.on_order(order)
```

