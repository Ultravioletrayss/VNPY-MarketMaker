
# 基于 vn.py 的大宗商品期货 Order 模式做市策略说明文档

## 1. 项目概述

### 1.1 代码性质

本策略是一个基于 **vn.py / vnpy_ctastrategy 框架**开发的事件驱动型量化交易策略，策略类继承自 `CtaTemplate`，通过 `on_tick`、`on_trade`、`on_order`、`on_timer` 等事件函数响应行情、成交、订单状态变化和定时检查。

策略主要应用场景是**大宗商品期货做市**，尤其适合具有较好盘口深度、能够提供多档盘口数据的品种。策略通过持续在买卖盘口两侧挂出限价单，为市场提供流动性，并通过库存控制和强制对冲机制控制持仓风险。

### 1.2 策略类型

本策略属于 **Order 模式双边做市策略**。

也就是说，策略不是使用 vn.py 的 Quote 报价接口，而是通过普通订单函数，例如：

```python
self.buy()
self.short()
self.sell()
self.cover()
```

分别发送买开、卖开、卖平、买平订单。普通做市订单和强制平仓订单在代码中被拆分管理，分别记录在 `mm_orderids` 和 `hedge_orderids` 中。

### 1.3 策略目标

本策略的核心目标包括：

1. 基于盘口数据计算合理的做市基准价；
2. 围绕基准价生成买卖双边报价；
3. 通过库存偏移机制降低单边持仓风险；
4. 在持仓超过阈值时触发强制平仓；
5. 在回测或模拟环境中验证做市逻辑的可行性。

---

## 2. 做市策略核心思路

### 2.1 做市的基本逻辑

可以，这部分可以改成下面这样，直接放进你的 MD 里。

````markdown
## 2. 做市策略核心思路

### 2.1 做市的基本逻辑

做市策略的核心是：

> 在合理价格附近同时挂买单和卖单，通过买卖价差获取收益，同时承担一定库存风险。

具体来说，策略会先根据盘口数据计算一个 `fair_price`，也就是做市基准价。然后策略会围绕这个基准价，在下方挂买单，在上方挂卖单。

例如在 tick 报价模式下：

```text
买单价格 = fair_price - spread_tick * price_tick
卖单价格 = fair_price + spread_tick * price_tick
````

其中各个参数含义如下：

| 参数            | 含义              | 在策略中的作用                  |
| ------------- | --------------- | ------------------------ |
| `fair_price`  | 做市基准价           | 策略认为当前较合理的价格，是买卖报价展开的中心  |
| `spread_tick` | 报价距离基准价的 tick 数 | 决定第一档买卖报价离基准价有多远         |
| `price_tick`  | 合约最小变动价位        | 用于把 tick 数转换成真实价格距离      |
| 买单价格          | 策略准备挂出的买入限价单价格  | 通常低于 `fair_price`，用于低价买入 |
| 卖单价格          | 策略准备挂出的卖出限价单价格  | 通常高于 `fair_price`，用于高价卖出 |

举个例子，假设：

```text
fair_price = 3700
price_tick = 1
spread_tick = 2
```

那么策略生成的第一档报价就是：

```text
买单价格 = 3700 - 2 × 1 = 3698
卖单价格 = 3700 + 2 × 1 = 3702
```

这意味着策略会在 3698 附近挂买单，在 3702 附近挂卖单。如果市场价格在这个区间内来回波动，策略就有机会以较低价格买入、以较高价格卖出，从买卖价差中获得收益。

如果 `spread_tick` 设置得更大，买卖报价会离基准价更远，成交概率会下降，但单次成交的价差空间可能更大；如果 `spread_tick` 设置得更小，报价会更靠近市场价格，成交概率更高，但单次价差空间也会变小。因此，`spread_tick` 是做市策略中非常重要的收益与成交概率平衡参数。

````

如果你想写得更“代码对应一点”，可以再加一小段：

```markdown
在本策略代码中，`fair_price` 由 `PricingEngine` 计算得到，`price_tick` 通过 vn.py 的 `get_pricetick()` 获取，`spread_tick` 是策略参数，可以在回测或实盘运行前手动设置。最终买卖报价由 `QuoteEngine.generate_quotes()` 统一生成。
````

如果市场价格在买卖两侧来回波动，策略就有机会低买高卖，从价差中获利。
| 参数            | 含义              | 在策略中的作用                  |
| ------------- | --------------- | ------------------------ |
| `fair_price`  | 做市基准价           | 策略认为当前较合理的价格，是买卖报价展开的中心  |
| `spread_tick` | 报价距离基准价的 tick 数 | 决定第一档买卖报价离基准价有多远         |
| `price_tick`  | 合约最小变动价位        | 用于把 tick 数转换成真实价格距离      |
| 买单价格          | 策略准备挂出的买入限价单价格  | 通常低于 `fair_price`，用于低价买入 |
| 卖单价格          | 策略准备挂出的卖出限价单价格  | 通常高于 `fair_price`，用于高价卖出 |

---

### 2.2 基准价计算

代码中设计了一个 `PricingEngine` 模块，用于计算基准价。当前支持多种定价方式：

```text
mid                买一卖一中间价
micro              微价格，考虑买一卖一挂单量
depth_weighted     五档盘口加权中间价
exp_depth_weighted 指数加权五档盘口中间价
```

其中，最基础的是中间价：

```text
mid_price = (bid1 + ask1) / 2
```

微价格会考虑买一、卖一挂单量：

```text
micro_price = (ask1 * bid1_volume + bid1 * ask1_volume) / (bid1_volume + ask1_volume)
```

五档加权价格则进一步利用多档盘口，计算更稳定的基准价。

---

### 2.3 双边报价生成

策略通过 `QuoteEngine` 生成买卖报价。报价方式分为两类：

```text
tick 模式：按照最小变动价位生成报价
percent 模式：按照百分比偏移生成报价
```

例如 tick 模式下：

```text
第 1 档买价 = fair_price - spread_tick * price_tick
第 1 档卖价 = fair_price + spread_tick * price_tick

第 2 档买价 = fair_price - (spread_tick + level_interval_tick) * price_tick
第 2 档卖价 = fair_price + (spread_tick + level_interval_tick) * price_tick
```

策略还支持多档报价和拆单，例如：

```text
quote_levels = 3
split_count = 2
```

表示买卖两边各生成 3 档，每档拆成 2 笔订单。

---

### 2.4 被动报价机制

策略中设置了 `passive_quote` 参数，用于控制是否保持被动挂单。

如果开启被动报价：

```text
买单价格不能高于 bid1
卖单价格不能低于 ask1
```

这样做的目的是避免策略主动吃单，尽量保持挂单做市，而不是变成主动交易。

---

### 2.5 库存偏移机制，也就是软对冲

做市策略最大的问题之一是库存风险。

如果策略连续买入，就会变成多头持仓；如果连续卖出，就会变成空头持仓。因此代码中设计了 `InventorySkewEngine`，用于根据当前持仓调整报价。

逻辑是：

```text
如果当前是多头：
    买价和卖价整体向下偏移
    目的：降低继续买入的概率，提高卖出的概率

如果当前是空头：
    买价和卖价整体向上偏移
    目的：提高买回的概率，降低继续卖出的概率
```

这属于软库存控制，不是立刻平仓，而是通过调整报价让市场自然帮策略回到合理仓位。

---

### 2.6 强制平仓机制

如果持仓超过 `hedge_threshold`，策略会触发强制平仓。

代码中通过 `HedgeEngine` 生成强制平仓指令：

```text
如果 pos >= hedge_threshold：
    说明多头过大，发 sell 平多单

如果 pos <= -hedge_threshold：
    说明空头过大，发 cover 平空单
```

强制平仓触发后，策略会进入 `hedging = True` 状态。在这个状态下，`on_tick()` 不再发送普通做市单，避免一边强制平仓、一边继续加仓。

---

## 3. 代码整体结构

本策略可以分为六个主要模块：

```text
1. MarketDataManager      行情数据管理模块
2. PricingEngine          基准价计算模块
3. QuoteEngine            报价生成模块
4. QuoteRiskFilter        报价风控过滤模块
5. InventorySkewEngine    库存偏移模块
6. HedgeEngine            强制平仓模块
7. CancelAdvancedOrder    主策略模块
```

其中，前六个模块负责具体功能，最后的 `CancelAdvancedOrder` 是主策略类，负责把这些模块串联起来。

---

# 4. 各模块详细说明

## 4.1 MarketDataManager：行情数据管理模块

### 4.1.1 模块作用

`MarketDataManager` 负责接收 `TickData`，提取盘口数据，并整理成统一的 `snapshot` 字典，方便后续模块调用。

它主要管理：

```text
last_price
bid_prices
ask_prices
bid_volumes
ask_volumes
bid1
ask1
bid1_volume
ask1_volume
market_spread
valid_depth
```

### 4.1.2 核心函数

#### `update_tick(tick)`

作用：
接收最新 tick，更新行情状态，并返回盘口快照。

主要完成：

```text
1. 保存最新 tick；
2. 提取买一到买五价格；
3. 提取卖一到卖五价格；
4. 提取买卖盘挂单量；
5. 计算 bid1 / ask1；
6. 计算 market_spread；
7. 计算 valid_depth；
8. 返回 snapshot。
```

#### `_calculate_valid_depth()`

作用：
计算当前盘口有效深度。

判断标准是：

```text
某一档的买价、卖价、买量、卖量都大于 0，才算有效档位。
```

#### `get_snapshot()`

作用：
返回当前行情快照。

后续模块不直接操作 tick，而是统一读取 snapshot。

#### `is_valid()`

作用：
检查买一卖一是否合法。

#### `has_depth(depth)`

作用：
判断当前盘口是否至少有指定深度。

#### `get_depth_volume(depth)`

作用：
计算前 N 档买卖盘总挂单量。

#### `get_order_book_imbalance(depth)`

作用：
计算盘口不平衡程度。

公式：

```text
imbalance = (bid_volume_sum - ask_volume_sum) / (bid_volume_sum + ask_volume_sum)
```

#### `get_mid_price()`

作用：
计算买一卖一中间价。

#### `get_micro_price()`

作用：
计算微价格。

---

## 4.2 PricingEngine：基准价计算模块

### 4.2.1 模块作用

`PricingEngine` 用于根据盘口数据计算做市基准价 `fair_price`。做市报价不是随便挂的，而是围绕这个 fair price 展开。

### 4.2.2 核心函数

#### `reset()`

作用：
重置定价状态，尤其是 EMA 历史价格。

这个函数在 `on_start()` 中被调用，避免上一轮回测或实盘运行的 EMA 状态影响本次结果。

#### `calculate_mid_price(snapshot)`

作用：
计算买一卖一中间价。

#### `calculate_micro_price(snapshot)`

作用：
计算微价格，考虑买一卖一挂单量。

#### `calculate_depth_weighted_mid(snapshot, depth)`

作用：
计算五档盘口加权中间价。

逻辑是：

```text
买盘加权平均价 = sum(bid_price_i * bid_volume_i) / sum(bid_volume_i)
卖盘加权平均价 = sum(ask_price_i * ask_volume_i) / sum(ask_volume_i)

depth_weighted_mid = (买盘加权平均价 + 卖盘加权平均价) / 2
```

#### `calculate_exp_weighted_depth_mid(snapshot, depth, decay)`

作用：
计算指数加权五档中间价。

特点是：

```text
越靠近盘口第一档，权重越高；
越远离盘口第一档，权重越低。
```

例如：

```text
第 1 档权重 = 1
第 2 档权重 = decay
第 3 档权重 = decay^2
```

#### `apply_ema_smoothing(new_price, ema_alpha)`

作用：
对基准价进行 EMA 平滑，减少基准价跳动。

公式：

```text
ema_price = alpha * new_price + (1 - alpha) * old_ema_price
```

#### `calculate_fair_price(...)`

作用：
统一入口函数。

根据 `pricing_method` 选择不同的基准价计算方式，然后根据 `use_ema_smoothing` 决定是否进行 EMA 平滑。

#### `round_to_tick(price, price_tick)`

作用：
将价格四舍五入到合法 tick。

---

## 4.3 QuoteEngine：报价生成模块

### 4.3.1 模块作用

`QuoteEngine` 根据基准价生成买卖报价，并判断是否需要撤单重挂。

它维护两个当前报价缓存：

```python
current_buy_quotes
current_sell_quotes
```

### 4.3.2 核心函数

#### `generate_quotes(...)`

作用：
根据 fair price 生成买卖双边报价。

它会根据以下参数生成报价：

```text
fair_price
price_tick
quote_levels
order_volume
quote_mode
spread_tick
level_interval_tick
spread_percent
level_interval_percent
split_count
passive_quote
```

最终返回：

```python
buy_quotes, sell_quotes
```

每个 quote 是一个字典，包括：

```text
side
level
order_index
price
volume
quote_mode
offset_value
```

#### `_calculate_tick_quote_price(...)`

作用：
tick 模式报价计算。

#### `_calculate_percent_quote_price(...)`

作用：
percent 模式报价计算。

#### `floor_to_tick(price, price_tick)`

作用：
价格向下取整到合法 tick，常用于买单。

#### `ceil_to_tick(price, price_tick)`

作用：
价格向上取整到合法 tick，常用于卖单。

#### `need_requote(...)`

作用：
判断新报价和当前报价相比，是否需要撤单重挂。

判断条件包括：

```text
1. 买单数量是否变化；
2. 卖单数量是否变化；
3. 买单价格变化是否超过 update_tolerance；
4. 卖单价格变化是否超过 update_tolerance；
5. 下单手数是否变化。
```

#### `update_current_quotes(...)`

作用：
更新当前报价缓存。

#### `clear_current_quotes()`

作用：
清空当前报价缓存。

---

## 4.4 QuoteRiskFilter：报价风控过滤模块

### 4.4.1 模块作用

`QuoteRiskFilter` 用来判断当前行情是否适合做市，以及根据仓位限制过滤报价。

这个模块主要解决一个问题：

> 不是所有行情都适合挂单做市。

如果盘口异常、深度不足、价差太小、买卖盘严重失衡，策略就应该停止报价。

### 4.4.2 核心函数

#### `check_market_data(snapshot)`

作用：
检查基础盘口是否合法。

包括：

```text
bid1 > 0
ask1 > 0
ask1 > bid1
bid1_volume > 0
ask1_volume > 0
```

#### `check_depth(snapshot, min_depth)`

作用：
检查有效盘口深度是否足够。

#### `check_spread(snapshot, price_tick, min_spread_tick)`

作用：
检查买卖价差是否达到最低要求。

如果价差太小，做市没有足够利润空间。

#### `check_depth_volume(snapshot, depth, min_depth_volume)`

作用：
检查前 N 档盘口挂单量是否足够。

#### `check_imbalance(snapshot, max_imbalance, depth)`

作用：
检查盘口是否过度失衡。

如果买盘远大于卖盘，或者卖盘远大于买盘，说明市场可能存在短期单边压力，不适合贸然做市。

#### `filter_by_position(buy_quotes, sell_quotes, pos, max_position)`

作用：
根据最大仓位限制过滤报价。

逻辑是：

```text
如果当前多头已经达到 max_position：
    删除买单，避免继续增加多头

如果当前空头已经达到 -max_position：
    删除卖单，避免继续增加空头
```

---

## 4.5 InventorySkewEngine：库存偏移模块

### 4.5.1 模块作用

`InventorySkewEngine` 用于进行软库存控制。

它不是直接平仓，而是通过调整买卖报价的位置，让策略逐渐降低风险仓位。

### 4.5.2 核心函数

#### `apply_skew(...)`

作用：
对买卖报价进行库存偏移。

逻辑：

```text
pos > 0：
    当前多头较多，报价整体下移

pos < 0：
    当前空头较多，报价整体上移
```

#### `calculate_pos_ratio(pos, max_position)`

作用：
计算当前持仓占最大允许持仓的比例。

结果限制在：

```text
[-1, 1]
```

#### `calculate_skew_tick(pos_ratio, max_skew_tick)`

作用：
根据持仓比例计算需要偏移多少 tick。

#### `move_quotes(quotes, price_tick, skew_tick)`

作用：
对报价列表进行价格平移。

#### `apply_passive_limit(...)`

作用：
库存偏移后，再次检查是否仍然满足被动挂单要求。

#### `get_last_skew_tick()`

作用：
返回上一次偏移 tick 数。

#### `get_last_pos_ratio()`

作用：
返回上一次持仓比例。

---

## 4.6 HedgeEngine：强制平仓模块

### 4.6.1 模块作用

`HedgeEngine` 用于处理强制平仓逻辑。

当普通软库存控制不足以降低风险时，如果仓位超过 `hedge_threshold`，策略会触发强制平仓。

### 4.6.2 核心函数

#### `check_hedge(...)`

作用：
检查是否需要强制平仓。

逻辑：

```text
如果 pos >= hedge_threshold：
    生成 SELL_CLOSE 指令

如果 pos <= -hedge_threshold：
    生成 BUY_CLOSE 指令
```

#### `calculate_sell_close_price(...)`

作用：
计算多头强制平仓价格。

#### `calculate_buy_close_price(...)`

作用：
计算空头强制平仓价格。

#### `update_last_hedge(hedge_order)`

作用：
记录最近一次 hedge 行为。

#### `clear_last_hedge()`

作用：
清空 hedge 状态记录。

#### `get_last_hedge_action()`

作用：
返回最近一次 hedge 动作。

#### `get_last_hedge_price()`

作用：
返回最近一次 hedge 价格。

#### `get_last_hedge_volume()`

作用：
返回最近一次 hedge 数量。

---

## 4.7 CancelAdvancedOrder：主策略模块

### 4.7.1 模块作用

`CancelAdvancedOrder` 是主策略类，继承自 `CtaTemplate`。它负责把前面的行情、定价、报价、风控、库存偏移、强制平仓模块串联起来。

### 4.7.2 核心参数

可以分成几类：

#### 定价参数

```text
pricing_method
pricing_depth
exp_depth_decay
use_ema_smoothing
ema_alpha
```

#### 报价参数

```text
quote_mode
quote_levels
order_volume
spread_tick
level_interval_tick
spread_percent
level_interval_percent
split_count
update_tolerance
```

#### 行情风控参数

```text
min_depth
min_spread_tick
depth_check_level
min_depth_volume
max_imbalance
```

#### 库存控制参数

```text
max_position
max_skew_tick
```

#### 强制平仓参数

```text
enable_hedge
hedge_threshold
hedge_volume
hedge_price_tick
```

#### 订单管理参数

```text
cancel_on_trade
passive_quote
```

---

# 5. 事件驱动流程

## 5.1 on_init：策略初始化

作用：

```text
策略初始化；
输出日志；
推送界面变量。
```

---

## 5.2 on_start：策略启动

作用：

```text
1. 获取 price_tick；
2. 获取 contract_size；
3. 重置 PricingEngine；
4. 清空报价缓存；
5. 清空订单记录；
6. 清空 mm_orderids；
7. 清空 hedge_orderids；
8. 清空最近 hedge 记录；
9. 设置 hedging = False。
```

这个函数保证每次策略启动时都从干净状态开始。

---

## 5.3 on_tick：行情驱动的普通做市逻辑

`on_tick()` 是普通做市的核心函数。

完整流程是：

```text
1. 更新盘口快照；
2. 更新策略变量 bid1 / ask1 / market_spread / valid_depth；
3. 如果正在 hedging，直接 return；
4. 检查行情是否合法；
5. 检查盘口深度；
6. 检查买卖价差；
7. 检查盘口挂单量；
8. 检查盘口不平衡；
9. 计算 fair_price；
10. 生成原始买卖报价；
11. 应用库存偏移；
12. 根据最大仓位过滤报价；
13. 判断是否需要撤单重挂；
14. 撤旧普通做市单；
15. 发新普通买单和卖单；
16. 更新当前报价缓存；
17. 更新订单数量。
```

可以在文档中画成流程图：

```text
Tick 到来
   ↓
更新盘口数据
   ↓
行情风控检查
   ↓
计算 fair_price
   ↓
生成双边报价
   ↓
库存偏移
   ↓
仓位硬过滤
   ↓
是否需要重挂？
   ↓
撤旧单 + 发新单
```

---

## 5.4 on_trade：成交驱动的对冲检查

`on_trade()` 在订单成交后触发。

主要逻辑：

```text
1. trade_count += 1；
2. 如果 cancel_on_trade=True，撤掉普通做市单；
3. 清空当前报价缓存；
4. 如果 enable_hedge=True，检查是否需要强制平仓；
5. 更新订单数量。
```

设计思路是：

> 普通做市单成交后，原来的盘口环境可能已经变化，所以先撤掉旧报价，等待下一轮 tick 重新报价。

---

## 5.5 on_order：订单状态维护

`on_order()` 用于维护订单状态。

主要逻辑：

```text
1. 更新 orders 字典；
2. 如果订单不再活跃，从 mm_orderids 和 hedge_orderids 中删除；
3. 如果 hedge 单结束，并且仓位回到阈值以内，则退出 hedging 状态；
4. 更新订单数量。
```

---

## 5.6 on_timer：定时检查

当前代码中的 `on_timer()` 版本比较简单，主要用于：

```text
1. 更新订单数量；
2. 推送界面变量。
```

后续可以扩展为：

```text
1. 普通订单超时撤单；
2. hedge 订单超时重挂；
3. 定时检查持仓是否超过阈值；
4. 定时输出策略状态日志。
```

---

# 6. 订单管理设计

## 6.1 普通做市订单

普通做市订单记录在：

```python
self.mm_orderids
```

普通做市单由 `on_tick()` 产生：

```python
self.buy()
self.short()
```

其中：

```text
buy   用于挂买开单
short 用于挂卖开单
```

---

## 6.2 强制平仓订单

强制平仓订单记录在：

```python
self.hedge_orderids
```

强制平仓订单由 `check_and_send_hedge_order()` 产生：

```python
self.sell()
self.cover()
```

其中：

```text
sell  用于平多
cover 用于平空
```

---

## 6.3 普通订单和 hedge 订单隔离

代码中把普通订单和 hedge 订单分开管理：

```text
mm_orderids      普通做市订单
hedge_orderids   强制平仓订单
```

这样做的好处是：

```text
撤普通做市单时，不影响 hedge 单；
撤 hedge 单时，不影响普通做市单；
强制平仓期间，可以暂停普通报价。
```

---

# 7. 回测数据管理与回测方法

## 7.1 回测数据来源

本策略依赖 tick 级别盘口数据，尤其适合使用大宗商品期货的多档盘口数据进行回测。

数据字段应至少包括：

```text
datetime
last_price
bid_price_1 ~ bid_price_5
ask_price_1 ~ ask_price_5
bid_volume_1 ~ bid_volume_5
ask_volume_1 ~ ask_volume_5
volume
turnover
open_interest
```

如果只有 K 线数据，则无法完整测试该策略的盘口逻辑，因为策略中的定价、深度检查、盘口不平衡、被动报价都依赖 tick 盘口数据。

---

## 7.2 数据导入

可以将 CSV 格式的 tick 数据清洗后导入 vn.py 数据库。

数据导入时需要注意：

```text
1. 合约代码要和 vn.py 的 vt_symbol 对齐；
2. datetime 要正确解析；
3. bid_price / ask_price 字段不能错位；
4. volume 字段要区分累计成交量和盘口挂单量；
5. price_tick 要和合约真实最小变动价位一致。
```

---

## 7.3 回测流程

回测流程可以写成：

```text
1. 准备商品期货 tick 数据；
2. 清洗并转换为 vn.py TickData 格式；
3. 导入 vn.py 数据库；
4. 在 CTA 回测模块中选择对应 vt_symbol；
5. 设置回测时间区间；
6. 设置手续费、滑点、合约乘数、最小变动价位；
7. 设置策略参数；
8. 运行回测；
9. 观察成交、持仓、净值、回撤、收益等指标；
10. 对比不同参数组合下的结果。
```

---

## 7.4 当前回测重点

目前回测不应只看最终收益，而应该重点观察：

```text
1. 策略是否能够正常发单；
2. 普通做市订单是否正常撤单重挂；
3. 成交后是否触发 cancel_on_trade；
4. 仓位是否被控制在 max_position 附近；
5. 超过 hedge_threshold 后是否触发强制平仓；
6. hedge 状态下是否暂停普通报价；
7. EMA 打开和关闭后结果是否符合预期；
8. depth_weighted 和 exp_depth_weighted 哪种定价方式更稳定。
```

---

## 7.5 当前回测成果

这一部分可以根据你自己的实际结果补充。建议结构这样写：

```markdown
### 7.5 当前回测成果

目前策略已经完成了基于 tick 数据的初步回测验证。从回测结果看，策略能够完成以下功能：

1. 正常读取 tick 盘口数据；
2. 根据盘口计算 fair_price；
3. 围绕 fair_price 生成双边报价；
4. 在行情不满足条件时停止报价；
5. 在成交后撤销旧报价；
6. 根据持仓变化进行库存偏移；
7. 在持仓超过阈值后触发强制平仓；
8. 能够统计普通订单数量、hedge 订单数量、成交次数等策略状态变量。

但当前回测也暴露出一些需要进一步优化的问题：

1. 撤单和重挂之间仍然存在异步确认问题；
2. hedge 机制目前主要由成交事件触发，后续可以在 on_timer 中增加兜底检查；
3. EMA 平滑虽然降低了基准价波动，但可能导致报价反应变慢；
4. exp_depth_weighted 定价方式不一定优于普通 depth_weighted，需要结合具体品种盘口特征调参。
```

---

# 8. 当前代码优势

可以写成：

```markdown
## 8. 当前代码优势

本策略相较于简单的双边挂单策略，具有以下特点：

1. 模块化程度较高  
   行情管理、定价、报价、风控、库存控制、强制平仓分别封装为独立模块，便于后续维护和扩展。

2. 支持多种基准价计算方式  
   策略不仅支持简单 mid price，也支持 micro price、五档加权中间价和指数加权五档中间价。

3. 支持盘口风控  
   策略在报价前会检查盘口合法性、深度、价差、挂单量和盘口不平衡，避免在异常行情下盲目做市。

4. 支持软库存控制  
   通过 InventorySkewEngine 根据持仓方向调整报价，降低库存不断累积的风险。

5. 支持强制平仓  
   当持仓超过阈值时，策略会暂停普通报价，并发出平仓订单降低风险。

6. 普通订单和 hedge 订单分离管理  
   通过 mm_orderids 和 hedge_orderids 分别管理不同类型订单，降低订单管理混乱的风险。
```

---

# 9. 当前代码不足与后续优化方向

建议一定要写这一节，显得你不是只会吹，而是知道代码边界。

```markdown
## 9. 当前不足与优化方向

虽然当前策略已经具备完整的做市框架，但仍存在一些需要进一步优化的地方。

### 9.1 撤单重挂的异步确认问题

当前策略在需要重挂时，会先调用 cancel_market_making_orders() 撤销普通做市单，然后立即发送新订单。但在真实交易环境中，撤单不是同步完成的，交易所需要时间返回撤单确认。因此可能出现旧订单尚未撤销、新订单已经发出的情况。

后续可以增加 requoting 状态，等待 on_order 确认旧订单全部撤销后，再发送新报价。

### 9.2 hedge 兜底检查不足

当前强制平仓主要在 on_trade() 中触发。如果 hedge 单未成交、被撤销或部分成交，而后续没有新的成交事件，策略可能无法及时继续处理超限仓位。

后续可以在 on_timer() 中增加持仓检查，如果持仓仍然超过 hedge_threshold，则继续尝试发送或调整 hedge 订单。

### 9.3 定价方式需要结合品种调参

exp_depth_weighted 并不一定天然优于 depth_weighted。如果盘口远端噪声较大，指数加权可能更好；但如果近端盘口容易被虚假挂单干扰，过度强调近端盘口反而可能降低效果。

### 9.4 回测和实盘仍存在差异

当前回测主要验证策略逻辑，但真实交易中还会受到排队成交、撤单延迟、撮合优先级、手续费、滑点、网络延迟等因素影响。因此回测盈利不代表实盘一定盈利。
```

---

# 10. 文档结尾总结

最后可以这样收尾：

```markdown
## 10. 总结

本策略是一个基于 vn.py 框架开发的事件驱动型大宗商品期货 Order 模式做市策略。策略以 tick 级盘口数据为输入，通过 PricingEngine 计算做市基准价，再由 QuoteEngine 围绕基准价生成买卖双边报价。同时，策略通过 QuoteRiskFilter 对行情质量进行过滤，通过 InventorySkewEngine 实现软库存控制，并通过 HedgeEngine 在仓位超过阈值时进行强制平仓。

整体来看，该策略已经形成了较完整的做市交易闭环，包括行情处理、基准价计算、报价生成、风险过滤、库存管理、强制平仓和回测验证。后续优化重点主要集中在撤单确认机制、hedge 兜底机制、参数调优和更贴近实盘的撮合模拟。
```

---

你这个 MD 的大标题建议就叫：

```markdown
# 基于 vn.py 的大宗商品期货 Order 模式做市策略设计与实现
```

这个标题比“代码介绍”高级很多，也更像课程项目/实习展示文档。
