下面这版就是按你现在的 **vn.py + CtaTemplate + Order 模式做市策略** 来整理的代码架构说明。

核心结论先说：

> **最终 vn.py 只加载一个策略类：`OrderMarketMakerStrategy(CtaTemplate)`。
> 但这个策略类里面可以组合多个普通类，分别负责行情、定价、报价、库存偏移、对冲、风控、订单管理。**

---

# 一、我们这个代码最终有几个部分？

建议你现在的 `order_market_maker_strategy.py` 里写这些部分：

```python
class MarketDataManager:
    """五档行情管理"""


class PricingEngine:
    """定价模块"""


class QuoteEngine:
    """做市报价模块"""


class InventorySkewEngine:
    """库存偏移 / 软对冲模块"""


class HedgeEngine:
    """主动对冲模块"""


class QuoteRiskFilter:
    """策略内部风控模块"""


class OrderMarketMakerStrategy(CtaTemplate):
    """vn.py 真正加载的主策略类"""
```

也就是：

```text
1. MarketDataManager        行情模块
2. PricingEngine            定价模块
3. QuoteEngine              做市报价模块
4. InventorySkewEngine      库存偏移 / 软对冲模块
5. HedgeEngine              主动对冲模块
6. QuoteRiskFilter          策略内部风控模块
7. OrderMarketMakerStrategy 主策略调度模块
```

其中只有最后这个：

```python
class OrderMarketMakerStrategy(CtaTemplate):
```

会被 vn.py 的 CTA 模块识别和加载。

前面的类都是普通 Python 工具类，不继承模板。

---

# 二、每个模块负责什么？

## 1. `MarketDataManager`：行情模块

负责读取和保存上期所五档盘口。

它做的事情：

```text
读取 bid_price_1 ~ bid_price_5
读取 ask_price_1 ~ ask_price_5
读取 bid_volume_1 ~ bid_volume_5
读取 ask_volume_1 ~ ask_volume_5
读取 last_price
检查盘口是否完整
```

它不负责下单，也不负责定价。

它只回答一个问题：

> **现在市场盘口是什么样？**

---

## 2. `PricingEngine`：定价模块

负责计算做市的基准价。

第一版最简单：

```text
mid_price = (bid1 + ask1) / 2
```

后面可以扩展成：

```text
五档加权 mid
盘口不平衡修正 mid
库存偏移修正 mid
```

它回答的问题是：

> **当前这个合约的合理中间价格是多少？**

---

## 3. `QuoteEngine`：做市报价模块

负责根据基准价生成买卖双边报价。

例如：

```text
mid = 100.00
tick = 0.01
quote_levels = 3
```

生成：

```text
买1档：99.99
买2档：99.98
买3档：99.97

卖1档：100.01
卖2档：100.02
卖3档：100.03
```

它负责文档里的：

```text
多档铺价
每档偏移
每档数量
买卖 Order 价格生成
```

它回答的问题是：

> **我要在哪些价格上挂买单和卖单？**

---

## 4. `InventorySkewEngine`：库存偏移 / 软对冲模块

这个非常重要。

它不是硬平仓，而是通过调整报价，让市场自然帮你减仓。

例如：

当前你多头太多：

```text
原报价：
买：99.99
卖：100.01
```

调整后：

```text
买：99.97    买单挂远，降低继续买入概率
卖：100.00   卖单挂近，提高卖出减仓概率
```

当前你空头太多：

```text
买单挂近一点
卖单挂远一点
```

这叫：

```text
库存偏移
inventory skew
软对冲
```

它回答的问题是：

> **我现在库存偏多/偏空，报价要不要向某一边倾斜？**

---

## 5. `HedgeEngine`：主动对冲模块

这个是硬对冲。

它不是每次成交都一定对冲，而是在风险变大时主动处理仓位。

例如：

```text
当前多头超过阈值
↓
主动 sell 平多
```

或者：

```text
当前空头超过阈值
↓
主动 cover 平空
```

它负责文档里的：

```text
成交后对冲
对冲方向判断
对冲价格生成
对冲数量控制
```

第一版可以先简单实现：

```text
不每笔成交都对冲
只有净持仓超过 hedge_threshold 时才主动对冲
```

它回答的问题是：

> **库存已经危险了，要不要主动反向交易，把风险降下来？**

---

## 6. `QuoteRiskFilter`：策略内部风控模块

注意，这个不是 vn.py 自带的可视化 `RiskManagerApp`。

这是策略内部风控，负责判断：

```text
行情是否合法
spread 是否太小
持仓是否超限
是否允许继续挂买单
是否允许继续挂卖单
是否需要停止报价
```

例如：

```text
ask1 <= bid1
不报价

market_spread < min_spread
不报价

pos >= max_position
停止挂买单，只允许挂卖单

pos <= -max_position
停止挂卖单，只允许挂买单
```

它回答的问题是：

> **现在这个状态下，我还能不能报价？能报哪一边？**

---

## 7. `OrderMarketMakerStrategy(CtaTemplate)`：主策略类

这个是 vn.py 真正加载的类。

它负责把所有模块串起来：

```text
接收 tick
调用行情模块
调用定价模块
调用报价模块
调用库存偏移模块
调用风控模块
调用 vn.py 的 buy / short / sell / cover / cancel_all
处理 on_order
处理 on_trade
刷新 UI
输出日志
```

它是总调度。

---

# 三、做市策略在哪个模块？

做市策略不是单独一个函数，而是由几个模块共同完成。

核心做市逻辑在：

```text
PricingEngine
QuoteEngine
OrderMarketMakerStrategy.on_tick()
```

具体分工：

| 做市步骤      | 负责模块                                              |
| --------- | ------------------------------------------------- |
| 读取盘口      | `MarketDataManager`                               |
| 计算基准价     | `PricingEngine`                                   |
| 生成买卖报价    | `QuoteEngine`                                     |
| 判断是否可以报价  | `QuoteRiskFilter`                                 |
| 挂买单/卖单    | `OrderMarketMakerStrategy` 调用 `buy()` / `short()` |
| 行情变化后撤单重挂 | `OrderMarketMakerStrategy.on_tick()`              |
| 成交后更新状态   | `on_trade()`                                      |

所以一句话：

> **做市策略主逻辑在 `on_tick()`，具体计算由 `PricingEngine` 和 `QuoteEngine` 完成。**

---

# 四、对冲策略在哪个模块？

对冲策略分两层。

## 第一层：软对冲

位置：

```text
InventorySkewEngine
```

逻辑：

```text
不主动平仓
而是根据当前库存调整报价
让市场更容易帮你减仓
```

例如：

```text
多头太多：
买单挂远
卖单挂近

空头太多：
买单挂近
卖单挂远
```

这层建议第一版实现。

---

## 第二层：硬对冲

位置：

```text
HedgeEngine
```

逻辑：

```text
当持仓超过对冲阈值时
主动发反向平仓单
```

例如：

```text
pos >= hedge_threshold
↓
sell 平多

pos <= -hedge_threshold
↓
cover 平空
```

这层可以第一版预留，第二版再完善。

---

# 五、真实下单场景中的先后顺序

下面是最重要的部分。

真实运行时不是你主动循环，而是 vn.py 事件驱动。

---

# 阶段 1：策略加载阶段

```text
运行 run.py
↓
vn.py 窗口启动
↓
加载 CTP Gateway
↓
加载 CtaStrategyApp
↓
CTA 模块扫描 strategies 文件夹
↓
发现 OrderMarketMakerStrategy(CtaTemplate)
↓
策略出现在 CTA 添加策略界面
```

---

# 阶段 2：创建策略实例

你在界面填：

```text
strategy_name = mm_rb
vt_symbol = rb2501.SHFE
quote_levels = 3
order_volume = 1
spread_tick = 2
max_position = 10
```

背后相当于：

```python
strategy = OrderMarketMakerStrategy(
    cta_engine,
    strategy_name,
    vt_symbol,
    setting
)
```

然后 `__init__()` 里创建模块：

```python
self.market_data = MarketDataManager()
self.pricing_engine = PricingEngine()
self.quote_engine = QuoteEngine()
self.inventory_skew_engine = InventorySkewEngine()
self.hedge_engine = HedgeEngine()
self.quote_risk_filter = QuoteRiskFilter()
```

---

# 阶段 3：初始化策略

你点击：

```text
初始化
```

vn.py 调用：

```python
on_init()
```

这里做：

```text
输出日志
初始化变量
可选加载历史数据
```

例如：

```python
def on_init(self):
    self.write_log("策略初始化")
```

此时：

```text
inited = True
trading = False
```

注意：初始化期间不能真正下单。

---

# 阶段 4：启动策略

你点击：

```text
启动
```

vn.py 调用：

```python
on_start()
```

这里做：

```text
输出日志
获取 pricetick
准备开始报价
```

例如：

```python
def on_start(self):
    self.write_log("策略启动")
    self.price_tick = self.get_pricetick()
```

启动后：

```text
trading = True
```

这时候 `buy()`、`short()`、`cancel_all()` 才会真正生效。

---

# 阶段 5：第一次行情到来

CTP 推送 tick。

vn.py 自动调用：

```python
on_tick(tick)
```

这是真正做市开始的地方。

---

# 六、`on_tick()` 内部真实调用顺序

这个是代码核心。

```text
1. 收到 tick
2. MarketDataManager 读取五档盘口
3. QuoteRiskFilter 检查行情是否合法
4. PricingEngine 计算 mid price
5. QuoteEngine 生成原始买卖报价
6. InventorySkewEngine 根据库存调整报价
7. QuoteRiskFilter 根据持仓过滤买卖方向
8. 判断旧报价是否需要更新
9. 如果需要更新：cancel_all()
10. 发送新的买单 buy()
11. 发送新的卖单 short()
12. put_event() 刷新 UI
```

用伪代码表示：

```python
def on_tick(self, tick):
    # 1. 读取五档行情
    snapshot = self.market_data.update_tick(tick)

    # 2. 行情合法性检查
    if not self.quote_risk_filter.check_market_data(snapshot):
        self.cancel_all()
        return

    # 3. spread 检查
    if not self.quote_risk_filter.check_spread(snapshot, self.min_spread_tick):
        self.cancel_all()
        return

    # 4. 计算基准价
    self.mid_price = self.pricing_engine.calculate_mid_price(snapshot)

    # 5. 生成原始报价
    buy_quotes, sell_quotes = self.quote_engine.generate_quotes(
        mid_price=self.mid_price,
        price_tick=self.price_tick,
        quote_levels=self.quote_levels,
        order_volume=self.order_volume
    )

    # 6. 库存偏移，软对冲
    buy_quotes, sell_quotes = self.inventory_skew_engine.apply_skew(
        buy_quotes=buy_quotes,
        sell_quotes=sell_quotes,
        pos=self.pos,
        max_position=self.max_position,
        price_tick=self.price_tick
    )

    # 7. 持仓风控过滤
    buy_quotes, sell_quotes = self.quote_risk_filter.filter_by_position(
        buy_quotes=buy_quotes,
        sell_quotes=sell_quotes,
        pos=self.pos,
        max_position=self.max_position
    )

    # 8. 判断是否需要撤单重挂
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

    # 12. 刷新界面
    self.put_event()
```

---

# 七、真实成交后的先后顺序

如果你的买单或者卖单成交，vn.py 会自动调用：

```python
on_trade(trade)
```

成交后的顺序：

```text
1. 收到成交回报
2. 更新成交统计
3. 判断是否需要成交后撤单
4. 判断库存是否过大
5. 调用 HedgeEngine 判断是否需要硬对冲
6. 如需对冲，发 sell 或 cover
7. 刷新 UI
```

伪代码：

```python
def on_trade(self, trade):
    # 1. 记录成交次数
    self.trade_count += 1

    # 2. 成交后撤单重报
    if self.cancel_on_trade:
        self.cancel_all()

    # 3. 判断是否需要主动对冲
    hedge_order = self.hedge_engine.generate_hedge_order(
        pos=self.pos,
        hedge_threshold=self.hedge_threshold,
        tick=self.market_data.last_tick,
        price_tick=self.price_tick
    )

    # 4. 如果需要硬对冲，则下平仓单
    if hedge_order:
        if hedge_order["action"] == "SELL_CLOSE":
            self.sell(hedge_order["price"], hedge_order["volume"])

        elif hedge_order["action"] == "BUY_CLOSE":
            self.cover(hedge_order["price"], hedge_order["volume"])

    # 5. 刷新界面
    self.put_event()
```

注意：

```text
self.pos 通常由 CTA 引擎根据成交自动维护。
```

所以 `on_trade()` 里更多是记录统计、触发撤单、触发对冲。

---

# 八、订单状态更新的先后顺序

当你发单、撤单、成交、拒单时，vn.py 会调用：

```python
on_order(order)
```

这里负责：

```text
记录订单状态
判断订单是否还活跃
统计撤单次数
后续支持“只撤某一档订单”
```

第一版可以简单写：

```python
def on_order(self, order):
    self.put_event()
```

第二版再完善。

---

# 九、停止策略时的顺序

你点击：

```text
停止
```

vn.py 调用：

```python
on_stop()
```

你应该做：

```text
1. 输出日志
2. 撤销所有挂单
3. 清理状态
4. 刷新 UI
```

代码：

```python
def on_stop(self):
    self.write_log("策略停止")
    self.cancel_all()
    self.put_event()
```

这非常重要。

做市策略挂单多，停止时必须撤单。

---

# 十、完整真实运行链路

把所有阶段连起来，就是：

```text
run.py 启动 vn.py
↓
加载 CTP Gateway
↓
加载 CTA 策略模块
↓
CTA 扫描策略文件
↓
识别 OrderMarketMakerStrategy
↓
用户添加策略实例，填写参数
↓
on_init 初始化
↓
on_start 启动
↓
CTP 推送 tick
↓
on_tick 触发做市逻辑
↓
读取五档盘口
↓
计算基准价
↓
生成多档买卖报价
↓
库存偏移/软对冲
↓
策略内部风控
↓
撤旧单
↓
buy 挂买单
↓
short 挂卖单
↓
订单状态变化 → on_order
↓
订单成交 → on_trade
↓
成交后撤单/库存检查/硬对冲
↓
继续等待下一个 tick
```

---

# 十一、文档四大模块和代码模块对应表

| 说明书模块          | 代码位置                                 |
| -------------- | ------------------------------------ |
| 定价             | `PricingEngine`                      |
| 多档铺价           | `QuoteEngine`                        |
| Order 模式买卖独立下单 | `OrderMarketMakerStrategy.on_tick()` |
| 容忍度更新          | `need_requote()` / `OrderManager` 思想 |
| 成交后撤单          | `on_trade()`                         |
| 成交后对冲          | `HedgeEngine`                        |
| 净成交量控制         | `QuoteRiskFilter` / `HedgeEngine`    |
| 撤单异常处理         | `on_order()` 后续扩展                    |
| 单位时间成交量限制      | `QuoteRiskFilter` 后续扩展               |
| 自动开平           | `buy / short / sell / cover`         |
| 撤补机制           | `HedgeEngine` 后续扩展                   |
| 自对冲            | 不做                                   |
| Quote 联动更新     | 不做，因为我们只做 Order                      |

---

# 十二、第一版到底要实现哪些？

第一版必须实现：

```text
1. MarketDataManager
   读取五档盘口

2. PricingEngine
   计算 mid price

3. QuoteEngine
   生成买卖多档报价

4. InventorySkewEngine
   根据库存调整报价，体现软对冲

5. QuoteRiskFilter
   检查盘口、spread、最大仓位

6. OrderMarketMakerStrategy
   继承 CtaTemplate，接 vn.py 事件，调用 buy/short/cancel_all

7. on_tick
   完成做市主流程

8. on_trade
   完成成交后撤单和对冲判断

9. on_order
   记录订单状态，第一版可以简单
```

第一版可以不完整实现：

```text
1. 复杂跨合约对冲
2. 自对冲
3. 撤补重试
4. Quote 模式
5. 公式编辑器
6. 多合约套利
```

---

# 十三、一句话总结

你的代码结构应该是：

```text
一个策略文件
多个普通模块类
一个 CtaTemplate 主策略类
```

做市策略在：

```text
PricingEngine + QuoteEngine + on_tick
```

软对冲策略在：

```text
InventorySkewEngine
```

硬对冲策略在：

```text
HedgeEngine + on_trade
```

真实下单顺序是：

```text
行情 tick 到来
↓
on_tick 计算并生成报价
↓
cancel_all 撤旧单
↓
buy 挂买单
↓
short 挂卖单
↓
成交后 on_trade
↓
根据库存决定撤单/软对冲/硬对冲
```

最终 vn.py 只识别：

```python
class OrderMarketMakerStrategy(CtaTemplate):
```

但这个类内部组合所有做市和对冲模块。
