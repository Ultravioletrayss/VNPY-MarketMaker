明白了。你问的是：

> 在 `OrderMarketMakerStrategy` 这个主策略类里面，这几个普通模块类到底谁先调用、谁后调用。

也就是这几个：

```python
MarketDataManager
PricingEngine
QuoteEngine
InventorySkewEngine
HedgeEngine
QuoteRiskFilter
```

在真实策略运行里的调用顺序。

---

# 一、先说结论

在 `OrderMarketMakerStrategy` 里面，它们不是一次性按顺序调用完，而是分成三条事件线：

```text
1. 行情来了：on_tick()
2. 订单状态变化：on_order()
3. 成交发生：on_trade()
```

其中最核心的是：

```text
on_tick()：做市报价主流程
on_trade()：成交后对冲/库存处理
on_order()：订单状态维护
```

---

# 二、`on_tick()` 里的模块调用顺序

这是做市策略最核心的调用顺序。

每来一个 tick，调用一次。

```text
on_tick(tick)
↓
1. MarketDataManager
   读取五档行情
↓
2. QuoteRiskFilter
   检查行情是否合法、spread 是否够
↓
3. PricingEngine
   计算 mid price / 基准价
↓
4. QuoteEngine
   生成原始买卖报价
↓
5. InventorySkewEngine
   根据当前持仓做库存偏移，也就是软对冲
↓
6. QuoteRiskFilter
   根据最大持仓过滤报价方向
↓
7. OrderMarketMakerStrategy 自己判断是否需要撤单重挂
↓
8. cancel_all()
   撤旧单
↓
9. buy() / short()
   重新挂买单和卖单
↓
10. put_event()
   刷新界面变量
```

也就是：

```text
行情 → 风控 → 定价 → 报价 → 库存偏移 → 再风控 → 撤单 → 下单
```

---

# 三、写成代码大概是这样

```python
def on_tick(self, tick: TickData):
    # 1. 行情模块：读取五档盘口
    snapshot = self.market_data.update_tick(tick)

    # 2. 风控模块：检查行情是否合法
    if not self.quote_risk_filter.check_market_data(snapshot):
        self.cancel_all()
        return

    # 3. 风控模块：检查盘口价差是否足够
    if not self.quote_risk_filter.check_spread(snapshot):
        self.cancel_all()
        return

    # 4. 定价模块：计算基准价 / mid price
    self.mid_price = self.pricing_engine.calculate_mid_price(snapshot)

    # 5. 报价模块：生成买卖多档报价
    buy_quotes, sell_quotes = self.quote_engine.generate_quotes(
        mid_price=self.mid_price,
        price_tick=self.price_tick,
        quote_levels=self.quote_levels,
        order_volume=self.order_volume
    )

    # 6. 库存偏移模块：根据持仓调整报价，软对冲
    buy_quotes, sell_quotes = self.inventory_skew_engine.apply_skew(
        buy_quotes=buy_quotes,
        sell_quotes=sell_quotes,
        pos=self.pos,
        max_position=self.max_position,
        price_tick=self.price_tick
    )

    # 7. 风控模块：根据持仓过滤报价方向
    buy_quotes, sell_quotes = self.quote_risk_filter.filter_by_position(
        buy_quotes=buy_quotes,
        sell_quotes=sell_quotes,
        pos=self.pos,
        max_position=self.max_position
    )

    # 8. 主策略自己判断是否需要撤单重挂
    if not self.need_requote(buy_quotes, sell_quotes):
        return

    # 9. 撤旧单
    self.cancel_all()

    # 10. 挂买单
    for quote in buy_quotes:
        self.buy(quote["price"], quote["volume"])

    # 11. 挂卖单
    for quote in sell_quotes:
        self.short(quote["price"], quote["volume"])

    # 12. 刷新UI
    self.put_event()
```

---

# 四、`on_trade()` 里的模块调用顺序

成交发生时，vn.py 会调用：

```python
on_trade(trade)
```

这里主要处理：

```text
成交记录
成交后撤单
硬对冲
刷新 UI
```

调用顺序是：

```text
on_trade(trade)
↓
1. OrderMarketMakerStrategy
   记录成交次数、成交价格、成交方向
↓
2. 如果 cancel_on_trade=True
   cancel_all() 撤掉剩余挂单
↓
3. HedgeEngine
   判断当前持仓是否需要主动对冲
↓
4. 如果需要硬对冲：
   多头太多 → sell()
   空头太多 → cover()
↓
5. put_event()
   刷新界面
```

代码大概：

```python
def on_trade(self, trade: TradeData):
    # 1. 记录成交
    self.trade_count += 1
    self.last_trade_price = trade.price

    # 2. 成交后撤掉旧挂单
    if self.cancel_on_trade:
        self.cancel_all()

    # 3. 主动对冲模块：判断是否需要硬对冲
    hedge_signal = self.hedge_engine.check_hedge(
        pos=self.pos,
        hedge_threshold=self.hedge_threshold,
        last_tick=self.market_data.last_tick,
        price_tick=self.price_tick
    )

    # 4. 根据对冲信号发平仓单
    if hedge_signal:
        if hedge_signal["action"] == "SELL_CLOSE":
            self.sell(hedge_signal["price"], hedge_signal["volume"])

        elif hedge_signal["action"] == "BUY_CLOSE":
            self.cover(hedge_signal["price"], hedge_signal["volume"])

    # 5. 刷新界面
    self.put_event()
```

所以：

```text
HedgeEngine 不在 on_tick 里主要工作
HedgeEngine 主要在 on_trade 里工作
```

---

# 五、`on_order()` 里的模块调用顺序

订单状态变化时调用：

```python
on_order(order)
```

这里第一版可以很简单。

调用顺序：

```text
on_order(order)
↓
1. 记录订单状态
↓
2. 判断订单是否仍然活跃
↓
3. 更新本地订单记录
↓
4. put_event()
```

如果你没有单独写 `OrderManager`，那就由主策略类自己处理。

```python
def on_order(self, order: OrderData):
    # 第一版可以先只刷新
    self.put_event()
```

第二版如果要做精细化撤单，就可以加：

```text
记录每个 order_id
记录买卖方向
记录档位 level
记录价格
记录是否已撤销/已成交
```

---

# 六、几个类在不同事件里的调用频率

| 类                          | 主要在哪个函数里调用   | 调用频率         |
| -------------------------- | ------------ | ------------ |
| `MarketDataManager`        | `on_tick()`  | 每个 tick 调一次  |
| `QuoteRiskFilter`          | `on_tick()`  | 每个 tick 多次调用 |
| `PricingEngine`            | `on_tick()`  | 每个 tick 调一次  |
| `QuoteEngine`              | `on_tick()`  | 每个 tick 调一次  |
| `InventorySkewEngine`      | `on_tick()`  | 每个 tick 调一次  |
| `HedgeEngine`              | `on_trade()` | 每次成交后调用      |
| `OrderMarketMakerStrategy` | 全部事件         | 总调度          |

---

# 七、最重要的一张顺序图

```text
行情 tick 来了
↓
OrderMarketMakerStrategy.on_tick()
↓
MarketDataManager
↓
QuoteRiskFilter
↓
PricingEngine
↓
QuoteEngine
↓
InventorySkewEngine
↓
QuoteRiskFilter
↓
need_requote()
↓
cancel_all()
↓
buy() / short()
```

成交来了：

```text
成交 trade 来了
↓
OrderMarketMakerStrategy.on_trade()
↓
cancel_all()
↓
HedgeEngine
↓
sell() / cover()
```

订单状态来了：

```text
订单 order 更新
↓
OrderMarketMakerStrategy.on_order()
↓
更新订单状态
↓
put_event()
```

---

# 八、做市策略和对冲策略分别在哪里

## 做市策略

主要在：

```text
on_tick()
```

调用这些模块：

```text
MarketDataManager
PricingEngine
QuoteEngine
InventorySkewEngine
QuoteRiskFilter
```

其中：

```text
PricingEngine + QuoteEngine = 做市报价核心
InventorySkewEngine = 做市里的库存管理/软对冲
```

---

## 对冲策略

分两层：

### 软对冲

在：

```text
InventorySkewEngine
```

调用位置：

```text
on_tick()
```

作用：

```text
通过调整买卖报价，让市场帮你减仓
```

### 硬对冲

在：

```text
HedgeEngine
```

调用位置：

```text
on_trade()
```

作用：

```text
成交后如果库存太大，主动 sell 或 cover 平仓
```

---

# 九、最终一句话

这几个类的调用顺序不是：

```text
MarketDataManager → PricingEngine → QuoteEngine → InventorySkewEngine → HedgeEngine → QuoteRiskFilter
```

一次性全部走完。

而是：

```text
on_tick 里：
MarketDataManager → QuoteRiskFilter → PricingEngine → QuoteEngine → InventorySkewEngine → QuoteRiskFilter → 撤单/下单

on_trade 里：
成交记录 → cancel_all → HedgeEngine → sell/cover

on_order 里：
订单状态记录 → put_event
```

这样才是真实交易时的调用顺序。
