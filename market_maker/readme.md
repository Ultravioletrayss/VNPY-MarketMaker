# 基于 vn.py 的大宗商品期货 Order 模式做市策略说明文档

## 1. 项目概述

### 1.1 代码性质

本策略是一个基于 **vn.py / vnpy\_ctastrategy 框架**开发的事件驱动型量化交易策略，策略类继承自 `CtaTemplate`，通过 `on_tick`、`on_trade`、`on_order`、`on_timer` 等事件函数响应行情、成交、订单状态变化和定时检查。

策略主要应用场景是**大宗商品期货做市**，尤其适合具有较好盘口深度、能够提供多档盘口数据的品种。策略通过持续在买卖盘口两侧挂出限价单，为市场提供流动性，并通过库存控制和强制对冲机制控制持仓风险。

### 1.2 策略类型

本策略属于 **Order 模式双边做市策略**。


\>在合理价格附近同时挂买单和卖单，通过买卖价差获取收益，同时承担一定库存风险。

具体来说，策略会先根据盘口数据计算一个 `fair_price`，也就是做市基准价。然后策略会围绕这个基准价，在下方挂买单，在上方挂卖单。

例如在 tick 报价模式下：
买单价格 = fair_price - spread_tick * price_tick
卖单价格 = fair_price + spread_tick * price_tick

其中各个参数含义如下：

| 参数          | 含义                         | 在策略中的作用                                 |
| ------------- | ---------------------------- | ---------------------------------------------- |
| `fair_price`  | 做市基准价                   | 策略认为当前较合理的价格，是买卖报价展开的中心 |
| `spread_tick` | 报价距离基准价的 tick 数     | 决定第一档买卖报价离基准价有多远               |
| `price_tick`  | 合约最小变动价位             | 用于把 tick 数转换成真实价格距离               |
| 买单价格      | 策略准备挂出的买入限价单价格 | 通常低于 `fair_price`，用于低价买入            |
| 卖单价格      | 策略准备挂出的卖出限价单价格 | 通常高于 `fair_price`，用于高价卖出            |

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

如果市场价格在买卖两侧来回波动，策略就有机会低买高卖，从价差中获利。
### 1.3 策略目标

本策略的核心目标包括：

1. 基于盘口数据计算合理的做市基准价；
2. 围绕基准价生成买卖双边报价；
3. 通过库存偏移机制降低单边持仓风险；
4. 在持仓超过阈值时触发强制平仓；
5. 在回测或模拟环境中验证做市逻辑的可行性。

## 2.各模块简要功能和摘要

本策略采用模块化设计，将行情处理、基准价计算、报价生成、风控过滤、库存控制、强制平仓和主策略调度拆分为多个独立模块。这样做的好处是：每个模块职责清晰，后续便于调试、扩展和单独优化。

| 模块名称 | 主要职责 | 简要说明 |
|---|---|---|
| `MarketDataManager` | 行情数据管理 | 负责接收 vn.py 传入的 `TickData`，提取买一卖一、五档买卖价格、五档挂单量、最新价、盘口价差和有效深度，并整理成统一的 `snapshot` 字典，供后续模块使用。 |
| `PricingEngine` | 基准价计算 | 负责根据盘口数据计算做市基准价 `fair_price`。支持 `mid`、`micro`、`depth_weighted`、`exp_depth_weighted` 等多种定价方式，也支持 EMA 平滑，减少基准价短期波动。 |
| `QuoteEngine` | 双边报价生成 | 负责围绕 `fair_price` 生成买卖双边报价。支持 `tick` 模式和 `percent` 模式，也支持多档报价、拆单、价格 tick 取整、被动报价限制，以及判断是否需要撤单重挂。 |
| `QuoteRiskFilter` | 报价风控过滤 | 负责判断当前行情是否适合做市，包括盘口是否合法、深度是否足够、买卖价差是否满足要求、盘口挂单量是否充足、买卖盘是否过度失衡。同时也负责根据最大持仓限制过滤报价。 |
| `InventorySkewEngine` | 库存偏移 / 软库存控制 | 负责根据当前持仓方向和持仓比例，对原始买卖报价进行整体偏移。如果多头过多，则报价整体下移；如果空头过多，则报价整体上移，从而引导策略逐步降低库存风险。 |
| `HedgeEngine` | 强制平仓 / 硬风控 | 负责在持仓超过 `hedge_threshold` 时生成强制平仓指令。如果多头超限，则生成 `SELL_CLOSE`；如果空头超限，则生成 `BUY_CLOSE`，用于快速降低持仓风险。 |
| `CancelAdvancedOrder` | 主策略类 / 事件调度 | 策略的主类，继承自 vn.py 的 `CtaTemplate`。负责在 `on_tick`、`on_trade`、`on_order`、`on_timer` 等事件中调用各个模块，完成从行情接收、报价生成、订单发送、成交处理到风险控制的完整流程。 |

整体来看，前几个模块分别负责具体功能，`OrderMarketMaker` 则负责把这些模块串联起来。策略运行时，行情首先进入 `MarketDataManager`，然后由 `PricingEngine` 计算基准价，再由 `QuoteEngine` 生成双边报价，经过 `QuoteRiskFilter` 和 `InventorySkewEngine` 处理后，最终由主策略类发送订单。如果持仓风险过高，则由 `HedgeEngine` 生成强制平仓指令。

## 3.事件驱动流程

本策略是基于 vn.py 框架的事件驱动型策略，不是主动循环运行的程序。也就是说，策略本身不会一直主动执行交易逻辑，而是等待 vn.py 框架推送不同类型的事件。

当新的行情、成交、订单状态变化或定时器事件到来时，vn.py 会自动调用策略中对应的函数。策略再根据这些事件执行行情处理、报价生成、订单管理和风险控制等逻辑。

| 事件函数              | 触发条件                     | 主要作用                                                                                                             |
| ----------------------- | ------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| `on_init()`       | 策略初始化时触发             | 用于策略初始化，输出初始化日志，并推送策略变量到界面。                                                               |
| `on_start()`      | 策略启动时触发               | 获取合约参数，清空历史状态，重置定价引擎、订单集合和报价缓存，使策略从干净状态开始运行。                             |
| `on_stop()`       | 策略停止时触发               | 停止策略运行，撤销所有订单，清空报价缓存、订单记录和状态变量。                                                       |
| `on_tick()`       | 每当新的 tick 行情到来时触发 | 策略最核心的普通做市逻辑，包括更新盘口、风控检查、计算基准价、生成双边报价、库存偏移、判断是否重挂、发送普通做市单。 |
| `on_trade()`      | 订单成交时触发               | 记录成交次数，成交后撤掉旧的普通做市单，并检查是否需要强制平仓。                                                     |
| `on_order()`      | 订单状态变化时触发           | 维护订单状态，更新普通做市订单和强制平仓订单集合，判断强制平仓状态是否结束。                                         |
| `on_timer()`      | 定时器触发                   | 当前版本主要用于更新订单数量和推送状态，后续可以扩展为订单超时撤单、hedge 兜底检查等功能。                           |
| `on_stop_order()` | 停止单状态变化时触发         | 当前策略中仅用于推送界面事件，暂未加入复杂逻辑。                                                                     |

```

```

### 3.2 策略启动阶段

策略启动时，vn.py 会先后调用初始化和启动相关函数。

流程如下：

```
on_init()
   ↓
on_start()
```

其中，`on_init()` 主要负责输出初始化日志；`on_start()` 负责真正准备策略运行环境。

`on_start()` 中主要完成以下操作：

```
1. 获取合约最小变动价位 price_tick；
2. 获取合约乘数 contract_size；
3. 重置 PricingEngine，清空 EMA 等历史定价状态；
4. 清空 QuoteEngine 中的当前报价缓存；
5. 清空订单记录 orders；
6. 清空普通做市订单集合 mm_orderids；
7. 清空强制平仓订单集合 hedge_orderids；
8. 清空最近一次强制平仓记录；
9. 设置 hedging = False。
```

这样可以保证每次策略启动时，不会受到上一轮运行状态的影响。

---

### 3.3 普通做市流程：on\_tick()

`on_tick()` 是本策略中最核心的函数。每当 vn.py 收到新的 tick 行情时，就会自动调用 `on_tick()`。

普通做市的实际执行顺序如下：

```
Tick 行情到来
   ↓
1. MarketDataManager 更新行情快照 snapshot
   ↓
2. 更新策略变量 bid1、ask1、market_spread、valid_depth
   ↓
3. 判断当前是否处于 hedging 状态
   ↓
如果 hedging=True：
    暂停普通报价，直接 return
如果 hedging=False：
    继续执行普通做市逻辑
   ↓
4. QuoteRiskFilter 检查行情是否合法
   ↓
5. QuoteRiskFilter 检查盘口深度是否足够
   ↓
6. QuoteRiskFilter 检查买卖价差是否足够
   ↓
7. QuoteRiskFilter 检查前 N 档挂单量是否足够
   ↓
8. QuoteRiskFilter 检查盘口是否过度失衡
   ↓
如果任意检查不通过：
    撤销普通做市单
    清空当前报价缓存
    return
   ↓
9. PricingEngine 计算 fair_price
   ↓
10. QuoteEngine 生成原始买卖报价
   ↓
11. InventorySkewEngine 根据当前持仓进行库存偏移
   ↓
12. QuoteRiskFilter 根据 max_position 做仓位硬过滤
   ↓
13. 判断买卖报价是否为空
   ↓
如果买卖报价都为空：
    撤销普通做市单
    清空当前报价缓存
    return
   ↓
14. QuoteEngine.need_requote() 判断是否需要撤单重挂
   ↓
如果不需要重挂：
    return
如果需要重挂：
    继续执行
   ↓
15. 撤销旧的普通做市订单
   ↓
16. 发送新的买单报价 buy()
   ↓
17. 发送新的卖单报价 short()
   ↓
18. 更新当前报价缓存 current_buy_quotes / current_sell_quotes
   ↓
19. 更新订单数量并推送界面状态
```

这条流程可以概括为：
行情更新 → 风控检查 → 计算基准价 → 生成报价 → 库存偏移 → 仓位过滤 → 判断重挂 → 发单

### 3.4 成交处理流程：on\_trade()

当普通做市订单或强制平仓订单发生成交时，vn.py 会触发 `on_trade()`。

```

`on_trade()` 的主要执行顺序是：
Trade 成交事件到来
↓

1. trade_count += 1
   ↓
2. 如果 cancel_on_trade=True：
   撤销普通做市订单
   清空当前报价缓存
   ↓
3. 如果 enable_hedge=True：
   调用 check_and_send_hedge_order()
   ↓
4. 更新订单数量
   ↓
5. 推送界面状态

```



这里的关键点是：成交发生后，原来的盘口环境和仓位状态都可能已经变化。因此策略会选择撤掉旧的普通做市报价，等待下一次 tick 到来后重新计算报价。

同时，成交会改变持仓，所以 `on_trade()` 中会检查是否需要强制平仓。如果当前持仓超过 `hedge_threshold`，策略会进入强制平仓逻辑。

### 3.5 订单状态维护流程：on\_order()

当订单状态发生变化时，例如订单提交、部分成交、全部成交、撤单完成等，vn.py 会触发 `on_order()`。

`on_order()` 的主要执行顺序是：



Order 状态变化事件到来
↓

1. 将订单更新到 orders 字典
   ↓
2. 如果订单已经不活跃：
   从 mm_orderids 中移除
   从 hedge_orderids 中移除
   ↓
3. 如果当前处于 hedging=True 且已经没有 hedge 订单：
   检查 abs(pos) 是否小于 hedge_threshold
   如果仓位已经回到阈值以内：
   hedging = False
   清空最近 hedge 记录
   ↓
4. 更新订单数量
   ↓
5. 推送界面状态

这个函数主要负责维护策略内部对订单状态的认知，确保普通做市订单和强制平仓订单能够被区分管理。



### 3.6 强制平仓流程

强制平仓不是单独由 vn.py 直接触发的事件，而是由策略在成交后主动检查触发。

实际流程是：

```
on_trade()
   ↓
check_and_send_hedge_order()
   ↓
HedgeEngine.check_hedge()
   ↓
判断当前 pos 是否超过 hedge_threshold
   ↓
如果没有超过：
    不触发强制平仓
如果多头超过阈值：
    生成 SELL_CLOSE 指令
如果空头超过阈值：
    生成 BUY_CLOSE 指令
   ↓
主策略进入 hedging=True
   ↓
撤销普通做市订单
   ↓
根据 hedge_order 发送 sell() 或 cover() 平仓单
   ↓
记录 hedge_orderids
```

当 `hedging=True` 时，后续 `on_tick()` 会直接 return，不再发普通做市单。这样可以避免策略一边强制平仓，一边继续挂普通做市单增加仓位。

### 3.7 定时器流程：on\_timer()

当前版本中，`on_timer()` 的逻辑比较简单：

```
Timer 事件到来
   ↓
1. 更新订单数量
   ↓
2. 推送界面状态
```

目前它主要是一个预留接口。

### 3.8 策略整体运行顺序总结

从整体上看，策略的实际运行顺序可以概括为：

```
策略初始化
   ↓
策略启动
   ↓
等待事件
   ↓
收到 tick：
    执行普通做市流程
   ↓
订单成交：
    执行成交处理和强制平仓检查
   ↓
订单状态变化：
    更新订单集合和 hedging 状态
   ↓
定时器触发：
    更新状态或执行扩展检查
   ↓
策略停止：
    撤单并清空状态
```

更简洁地说：

```
on_init / on_start
        ↓
on_tick 负责普通做市
        ↓
on_trade 负责成交后处理和强制平仓检查
        ↓
on_order 负责订单状态维护
        ↓
on_timer 作为定时兜底接口
        ↓
on_stop 负责停止和清理
```

本策略的核心特征是：它不是主动循环交易，而是等待市场事件触发。行情来了，策略才计算报价；成交发生了，策略才检查持仓风险；订单状态变化了，策略才更新内部订单记录。这种事件驱动结构符合 vn.py 框架的运行方式，也更适合实盘交易系统。





## 4.1 PricingEngine：基准价计算模块

### 4.1.1 模块定位

`PricingEngine` 是策略中的基准价计算模块，主要负责根据盘口数据计算做市使用的 `fair_price`。在做市策略中，买卖报价不是直接围绕 `last_price` 展开，而是先通过盘口数据估算一个更合理的基准价，然后再由报价模块围绕这个基准价生成买卖双边报价。:contentReference[oaicite:0]{index=0}

本模块的输入主要是 `snapshot` 行情快照，里面包含：

```text
bid1
ask1
bid1_volume
ask1_volume
bid_prices
ask_prices
bid_volumes
ask_volumes
valid_depth
```

模块的输出是：

```text
fair_price
```

也就是后续报价模块使用的做市中心价格。



### 4.1.2 模块核心功能

`PricingEngine` 主要支持以下几种基准价计算方式：

| 定价方式                 | 函数                                     | 说明                                                 |
| -------------------------- | ------------------------------------------ | ------------------------------------------------------ |
| `mid`                | `calculate_mid_price()`              | 使用买一价和卖一价的中间值作为基准价                 |
| `micro`              | `calculate_micro_price()`            | 在买一卖一价格基础上，加入买一卖一挂单量权重         |
| `depth_weighted`     | `calculate_depth_weighted_mid()`     | 使用多档盘口价格和挂单量，计算五档加权中间价         |
| `exp_depth_weighted` | `calculate_exp_weighted_depth_mid()` | 在五档加权基础上加入指数衰减权重，更重视近端盘口     |
| EMA 平滑                 | `apply_ema_smoothing()`              | 对最终基准价进行平滑，减少短期跳动                   |
| 统一入口                 | `calculate_fair_price()`             | 根据参数选择具体定价方式，并返回最终`fair_price` |

---

### 4.1.3 `calculate_mid_price()`：买一卖一中间价

`mid price` 是最基础的基准价计算方式，只使用买一价和卖一价。

计算公式为：

```text
mid_price = (bid1 + ask1) / 2
```

其中：

| 参数            | 含义                   |
| ----------------- | ------------------------ |
| `bid1`      | 当前盘口买一价         |
| `ask1`      | 当前盘口卖一价         |
| `mid_price` | 买一价和卖一价的中间值 |

这种方式的优点是简单、直观、计算速度快。缺点是只考虑价格，不考虑买卖盘挂单量，因此无法反映买卖双方力量的差异。

---

### 4.1.4 `calculate_micro_price()`：微价格

`micro price` 在 `mid price` 的基础上加入买一卖一挂单量信息。

计算公式为：

```text
micro_price = (ask1 * bid1_volume + bid1 * ask1_volume) / (bid1_volume + ask1_volume)
```

其中：

| 参数              | 含义                         |
| ------------------- | ------------------------------ |
| `bid1`        | 买一价                       |
| `ask1`        | 卖一价                       |
| `bid1_volume` | 买一挂单量                   |
| `ask1_volume` | 卖一挂单量                   |
| `micro_price` | 考虑买卖盘力量后的短期基准价 |

这个公式的含义是：如果买一挂单量更大，说明买方力量更强，价格更可能向卖一方向靠近；如果卖一挂单量更大，说明卖方压力更强，价格更可能向买一方向靠近。

因此，`micro_price` 比 `mid_price` 更敏感，更能反映买卖一档盘口力量的变化。

---

### 4.1.5 `calculate_depth_weighted_mid()`：五档盘口加权中间价

`depth_weighted` 不只使用买一卖一，而是使用多档盘口的价格和挂单量。

计算逻辑为：

```text
买盘加权平均价 = sum(bid_price_i * bid_volume_i) / sum(bid_volume_i)

卖盘加权平均价 = sum(ask_price_i * ask_volume_i) / sum(ask_volume_i)

depth_weighted_mid = (买盘加权平均价 + 卖盘加权平均价) / 2
```

其中：

| 参数               | 含义                 |
| -------------------- | ---------------------- |
| `bid_price_i`  | 第 i 档买盘价格      |
| `ask_price_i`  | 第 i 档卖盘价格      |
| `bid_volume_i` | 第 i 档买盘挂单量    |
| `ask_volume_i` | 第 i 档卖盘挂单量    |
| `depth`        | 使用几档盘口         |
| `valid_depth`  | 当前实际有效盘口深度 |

这种方式的好处是使用了更多盘口信息，比只看买一卖一更稳定。它适合有多档盘口数据的大宗商品期货做市场景。

---

### 4.1.6 `calculate_exp_weighted_depth_mid()`：指数加权五档中间价

`exp_depth_weighted` 是在普通五档加权基础上的改进。

普通五档加权会使用所有有效档位，但越靠近买一卖一的盘口，通常对短期价格更重要。因此该函数给近端盘口更高权重，远端盘口更低权重。

权重形式为：

```text
第 1 档权重 = 1
第 2 档权重 = decay
第 3 档权重 = decay^2
第 4 档权重 = decay^3
第 5 档权重 = decay^4
```

其中：

| 参数         | 含义           |
| -------------- | ---------------- |
| `depth`  | 使用的盘口深度 |
| `decay`  | 指数衰减系数   |
| `weight` | 当前档位的权重 |

如果 `decay = 0.6`，则越远离第一档，权重越低。

这种方法的优点是既利用多档盘口，又不会让远端盘口对基准价影响过大。缺点是 `decay` 需要调参，如果设置过小，会过度依赖第一档；如果设置过大，又会接近普通五档加权。

---

### 4.1.7 `apply_ema_smoothing()`：EMA 平滑

EMA 平滑用于减少 `fair_price` 的短期跳动。

公式为：

```text
ema_fair_price = ema_alpha * new_price + (1 - ema_alpha) * old_ema_fair_price
```

其中：

| 参数                     | 含义                      |
| -------------------------- | --------------------------- |
| `new_price`          | 当前最新计算出来的基准价  |
| `old_ema_fair_price` | 上一次 EMA 平滑后的基准价 |
| `ema_alpha`          | 平滑系数                  |
| `ema_fair_price`     | 平滑后的基准价            |

`ema_alpha` 越大，基准价越跟随最新行情；`ema_alpha` 越小，基准价越平滑，但反应也越慢。

EMA 的作用是减少基准价频繁跳动，从而减少后续报价模块频繁撤单重挂。

---

### 4.1.8 `calculate_fair_price()`：统一计算入口

`calculate_fair_price()` 是 `PricingEngine` 的统一入口函数。

它根据参数 `pricing_method` 选择不同的定价方式：

```text
pricing_method = "mid"
pricing_method = "micro"
pricing_method = "depth_weighted"
pricing_method = "exp_depth_weighted"
```

执行流程可以概括为：

```text
读取 snapshot
    ↓
根据 pricing_method 选择定价方式
    ↓
计算 raw_price
    ↓
如果 use_ema_smoothing=True，则进行 EMA 平滑
    ↓
得到最终 fair_price
```

也就是说，其他模块不需要关心具体用了哪种定价方法，只需要调用 `calculate_fair_price()`，就可以得到最终的 `fair_price`。

---

### 4.1.9 `reset()`：重置定价状态

`reset()` 用于清空定价模块中的历史状态，尤其是 EMA 相关状态。

它会重置：

```text
mid_price
micro_price
depth_weighted_mid
exp_weighted_depth_mid
ema_fair_price
fair_price
```

这个函数通常在策略启动时调用，避免上一轮回测或运行中的 EMA 历史值影响新一轮策略结果。

---

### 4.1.10 `round_to_tick()`：价格 tick 对齐

`round_to_tick()` 用于将价格四舍五入到合法的最小变动价位上。

计算逻辑为：

```text
合法价格 = round(price / price_tick) * price_tick
```

在期货交易中，价格必须符合合约最小变动价位，因此价格计算后需要进行 tick 对齐。

---

### 4.1.11 小结

总体来说，`PricingEngine` 是整个做市策略的定价核心。它不负责下单，也不负责风控，而是专门负责回答一个问题：

> 当前市场的合理基准价应该是多少？

后续的 `QuoteEngine` 会围绕这个 `fair_price` 生成买卖报价，因此 `PricingEngine` 的稳定性和合理性会直接影响整个做市策略的报价质量。


## 4.2 QuoteRiskFilter：报价风控过滤模块

### 4.2.1 模块定位

`QuoteRiskFilter` 是策略中的报价风控过滤模块，主要负责判断当前行情是否适合做市，以及当前持仓是否允许继续挂买单或卖单。

在做市策略中，并不是所有行情都适合报价。如果盘口数据异常、深度不足、价差太小、盘口太薄，或者买卖盘严重失衡，策略继续挂单可能会承担较大的成交风险。因此，在真正发单之前，需要先经过 `QuoteRiskFilter` 进行过滤。

这个模块主要包含两类功能：

| 功能类型 | 说明 |
|---|---|
| 行情过滤 | 判断当前盘口是否正常、深度是否足够、价差是否合理、挂单量是否充足、盘口是否过度失衡 |
| 仓位过滤 | 根据当前持仓和最大持仓限制，过滤掉可能继续扩大风险仓位的一边报价 |

---

### 4.2.2 `check_market_data()`：基础盘口检查

`check_market_data()` 用于检查最基础的买一卖一盘口是否合法。

它主要检查：

```text
bid1 > 0
ask1 > 0
ask1 > bid1
bid1_volume > 0
ask1_volume > 0
````

其中：

| 参数            | 含义    |
| ------------- | ----- |
| `bid1`        | 买一价   |
| `ask1`        | 卖一价   |
| `bid1_volume` | 买一挂单量 |
| `ask1_volume` | 卖一挂单量 |

如果 `bid1 <= 0` 或 `ask1 <= 0`，说明盘口价格无效。
如果 `ask1 <= bid1`，说明买卖价关系异常。
如果买一或卖一挂单量为 0，说明盘口缺乏有效流动性。

只要其中任意一项不满足，函数就会返回 `False`，策略不会继续报价。

---

### 4.2.3 `check_depth()`：盘口深度检查

`check_depth()` 用来检查当前盘口有效深度是否满足最低要求。

核心判断是：

```text
valid_depth >= min_depth
```

其中：

| 参数            | 含义          |
| ------------- | ----------- |
| `valid_depth` | 当前有效盘口深度    |
| `min_depth`   | 策略要求的最小盘口深度 |

例如：

```text
min_depth = 3
```

表示当前盘口至少需要有 3 档有效买卖盘，策略才允许继续报价。

如果盘口深度不足，说明市场流动性不够，策略容易在较薄的盘口中被快速成交或被价格打穿，因此应停止报价。

---

### 4.2.4 `check_spread()`：买卖价差检查

`check_spread()` 用来判断当前盘口买卖价差是否足够。

代码会先计算：

```text
spread_tick = market_spread / price_tick
```

其中：

```text
market_spread = ask1 - bid1
```

参数含义如下：

| 参数                | 含义              |
| ----------------- | --------------- |
| `market_spread`   | 当前买卖价差          |
| `price_tick`      | 合约最小变动价位        |
| `min_spread_tick` | 最小价差要求，单位是 tick |
| `spread_tick`     | 当前价差折算成多少个 tick |

如果：

```text
spread_tick < min_spread_tick
```

说明当前买卖价差太小，做市空间不足，策略不会继续报价。

这个检查的作用是避免在价差过窄时做市，因为价差太小可能覆盖不了手续费、滑点和被动成交风险。

---

### 4.2.5 `check_depth_volume()`：盘口挂单量检查

`check_depth_volume()` 用来检查前 N 档买卖盘总挂单量是否足够。

它会计算：

```text
bid_volume_sum = 前 N 档买盘挂单量总和
ask_volume_sum = 前 N 档卖盘挂单量总和
```

然后判断：

```text
bid_volume_sum >= min_depth_volume
ask_volume_sum >= min_depth_volume
```

其中：

| 参数                 | 含义              |
| ------------------ | --------------- |
| `depth`            | 检查前几档盘口         |
| `valid_depth`      | 当前实际有效盘口深度      |
| `min_depth_volume` | 前 N 档买卖盘最小挂单量要求 |

代码中实际使用的深度会取：

```text
depth = min(depth, valid_depth, 5)
```

这样可以避免检查超过实际有效盘口的数据。

如果买盘或卖盘挂单量太小，说明盘口较薄，价格可能容易被单笔订单打穿，因此策略不会报价。

---

### 4.2.6 `check_imbalance()`：盘口不平衡检查

`check_imbalance()` 用于判断买卖盘是否过度失衡。

计算公式为：

```text
imbalance = (bid_volume_sum - ask_volume_sum) / (bid_volume_sum + ask_volume_sum)
```

其中：

| 参数               | 含义           |
| ---------------- | ------------ |
| `bid_volume_sum` | 前 N 档买盘挂单量总和 |
| `ask_volume_sum` | 前 N 档卖盘挂单量总和 |
| `imbalance`      | 买卖盘不平衡程度     |
| `max_imbalance`  | 最大允许不平衡程度    |

`imbalance` 的含义是：

```text
imbalance > 0：买盘更厚
imbalance < 0：卖盘更厚
imbalance 接近 1：买盘远大于卖盘
imbalance 接近 -1：卖盘远大于买盘
```

代码最后会判断：

```text
abs(imbalance) <= max_imbalance
```

如果绝对值超过 `max_imbalance`，说明盘口一边倒，短期价格可能存在明显方向性风险，策略会停止报价。

---

### 4.2.7 `filter_by_position()`：根据持仓过滤报价

`filter_by_position()` 是根据当前持仓进行的硬风控。

它的作用不是判断行情，而是判断当前仓位是否还允许继续挂某一边的单。

逻辑如下：

```text
如果 pos >= max_position：
    删除买单 buy_quotes

如果 pos <= -max_position：
    删除卖单 sell_quotes
```

其中：

| 参数             | 含义                  |
| -------------- | ------------------- |
| `pos`          | 当前净持仓，正数表示多头，负数表示空头 |
| `max_position` | 最大允许持仓              |
| `buy_quotes`   | 当前准备挂出的买单报价         |
| `sell_quotes`  | 当前准备挂出的卖单报价         |

例如，如果当前已经是多头上限：

```text
pos = 4
max_position = 4
```

此时策略不能继续挂买单，因为买单一旦成交，会让多头仓位继续增加。所以代码会直接清空 `buy_quotes`，只保留可能降低多头风险的卖单。

如果当前已经是空头上限：

```text
pos = -4
max_position = 4
```

此时策略不能继续挂卖单，因为卖单成交后会让空头仓位继续扩大。所以代码会直接清空 `sell_quotes`。

---

### 4.2.8 小结

总体来说，`QuoteRiskFilter` 是策略在报价前的安全过滤模块。它主要回答两个问题：

```text
1. 当前行情适不适合做市？
2. 当前仓位还允不允许继续挂这一边的单？
```

如果行情不满足条件，策略会撤掉普通做市单并停止报价；如果仓位已经达到上限，策略会过滤掉会继续扩大仓位的一边报价。

因此，`QuoteRiskFilter` 是连接“行情判断”和“仓位风控”的关键模块。

## 4.3 QuoteEngine：双边报价生成模块

### 4.3.1 模块定位

`QuoteEngine` 是策略中的双边报价生成模块，主要负责根据 `PricingEngine` 计算出来的 `fair_price`，生成买卖两边的报价列表。

在整个策略流程中，`PricingEngine` 负责回答“合理价格在哪里”，而 `QuoteEngine` 负责回答“围绕这个合理价格，应该挂哪些买单和卖单”。

该模块的核心输出是两个列表：

```text
buy_quotes
sell_quotes
```

其中，buy_quotes 表示准备挂出的买单报价，sell_quotes 表示准备挂出的卖单报价。每个报价会以字典形式保存，包括方向、档位、价格、手数、报价模式和偏移量等信息。




### 4.3.2 模块核心功能

`QuoteEngine` 主要包含以下功能：

| 功能             | 对应函数                               | 说明                               |
| ------------------ | ---------------------------------------- | ------------------------------------ |
| 生成买卖报价     | `generate_quotes()`                | 根据基准价生成买卖双边报价         |
| tick 模式报价    | `_calculate_tick_quote_price()`    | 按照 tick 距离计算每一档买卖价格   |
| percent 模式报价 | `_calculate_percent_quote_price()` | 按照百分比偏移计算每一档买卖价格   |
| 价格向下取整     | `floor_to_tick()`                  | 将买单价格调整到合法 tick          |
| 价格向上取整     | `ceil_to_tick()`                   | 将卖单价格调整到合法 tick          |
| 价格四舍五入     | `round_to_tick()`                  | 将价格就近调整到合法 tick          |
| 判断是否重挂     | `need_requote()`                   | 比较新旧报价，判断是否需要撤单重挂 |
| 更新报价缓存     | `update_current_quotes()`          | 保存当前已经发出的报价             |
| 清空报价缓存     | `clear_current_quotes()`           | 清空当前报价记录                   |

---

### 4.3.3 `generate_quotes()`：生成双边报价

`generate_quotes()` 是 `QuoteEngine` 的核心函数，用来生成买卖双边报价。

它的主要输入参数包括：

| 参数                         | 含义                                     |
| ------------------------------ | ------------------------------------------ |
| `fair_price`             | 做市基准价，报价围绕它上下展开           |
| `price_tick`             | 合约最小变动价位                         |
| `quote_levels`           | 报价档数，例如 3 表示买卖各挂 3 档       |
| `order_volume`           | 每一笔报价的手数                         |
| `quote_mode`             | 报价模式，支持`tick`和`percent`  |
| `spread_tick`            | tick 模式下，第一档距离基准价几个 tick   |
| `level_interval_tick`    | tick 模式下，每档之间间隔几个 tick       |
| `spread_percent`         | percent 模式下，第一档距离基准价的百分比 |
| `level_interval_percent` | percent 模式下，每档之间增加的百分比     |
| `split_count`            | 每一档拆成几笔单                         |
| `snapshot`               | 当前盘口快照，主要用于被动报价限制       |
| `passive`                | 是否保持被动报价                         |

函数会先检查参数是否合法。如果 `fair_price`、`price_tick`、`quote_levels`、`order_volume` 或 `split_count` 不合法，就直接返回空列表。

同时，代码会限制最大报价档数：

```text
quote_levels = min(quote_levels, 5)
```

也就是说，策略最多生成 5 档报价。

---

### 4.3.4 tick 模式报价

如果 `quote_mode = "tick"`，策略会调用 `_calculate_tick_quote_price()` 计算报价。

tick 模式的核心逻辑是：

```text
offset_tick = spread_tick + (level - 1) * level_interval_tick
```

然后：

```text
raw_buy_price = fair_price - offset_tick * price_tick
raw_sell_price = fair_price + offset_tick * price_tick
```

其中：

| 参数                      | 含义                              |
| --------------------------- | ----------------------------------- |
| `spread_tick`         | 第一档距离基准价的 tick 数        |
| `level_interval_tick` | 每增加一档，多远离基准价几个 tick |
| `level`               | 当前报价档位                      |
| `offset_tick`         | 当前档位最终偏移 tick 数          |

例如：

```text
fair_price = 3700
price_tick = 1
spread_tick = 2
level_interval_tick = 1
quote_levels = 3
```

则：

| 档位    | offset\_tick | 买单价格 | 卖单价格 |
| --------- | -------------: | ---------: | ---------: |
| 第 1 档 |            2 |     3698 |     3702 |
| 第 2 档 |            3 |     3697 |     3703 |
| 第 3 档 |            4 |     3696 |     3704 |

tick 模式的优点是直观，适合期货品种，因为期货合约本身就是按照最小变动价位跳动的。

---

### 4.3.5 percent 模式报价

如果 `quote_mode = "percent"`，策略会调用 `_calculate_percent_quote_price()` 计算报价。

percent 模式的核心逻辑是：

```text
offset_percent = spread_percent + (level - 1) * level_interval_percent
```

然后：

```text
raw_buy_price = fair_price * (1 - offset_percent)
raw_sell_price = fair_price * (1 + offset_percent)
```

其中：

| 参数                         | 含义                             |
| ------------------------------ | ---------------------------------- |
| `spread_percent`         | 第一档距离基准价的百分比         |
| `level_interval_percent` | 每增加一档，多远离基准价的百分比 |
| `offset_percent`         | 当前档位最终偏移百分比           |

例如：

```text
fair_price = 3700
spread_percent = 0.0002
level_interval_percent = 0.0001
quote_levels = 3
```

则：

```text
第 1 档 offset_percent = 0.0002
第 2 档 offset_percent = 0.0003
第 3 档 offset_percent = 0.0004
```

percent 模式的好处是可以按价格比例控制报价宽度，更适合在不同价格水平的品种之间做统一参数管理。

---

### 4.3.6 价格 tick 对齐

无论是 tick 模式还是 percent 模式，最终计算出来的价格都必须符合合约最小变动价位。

因此，代码中使用了三个价格处理函数：

| 函数                  | 作用                    | 主要用途     |
| ----------------------- | ------------------------- | -------------- |
| `floor_to_tick()` | 向下取整到合法 tick     | 买单价格     |
| `ceil_to_tick()`  | 向上取整到合法 tick     | 卖单价格     |
| `round_to_tick()` | 就近四舍五入到合法 tick | 一般价格处理 |

买单使用 `floor_to_tick()`，逻辑是：

```text
buy_price = floor(raw_buy_price / price_tick) * price_tick
```

卖单使用 `ceil_to_tick()`，逻辑是：

```text
sell_price = ceil(raw_sell_price / price_tick) * price_tick
```

这样做可以避免价格取整后变得过于激进。买单向下取整，卖单向上取整，更符合被动做市的思路。

---

### 4.3.7 被动报价限制

如果 `passive=True`，并且传入了 `snapshot`，代码会对买卖报价做进一步限制。

逻辑是：

```text
买单价格不能高于 bid1
卖单价格不能低于 ask1
```

对应代码逻辑为：

```text
buy_price = min(buy_price, bid1)
sell_price = max(sell_price, ask1)
```

这个设计的作用是避免策略主动吃单。

例如，如果计算出来的买单价格高于当前买一价，说明报价可能过于激进，代码会把买价压回到 `bid1`。如果计算出来的卖单价格低于当前卖一价，代码会把卖价抬回到 `ask1`。

---

### 4.3.8 多档报价与拆单

`quote_levels` 控制报价档数。

例如：

```text
quote_levels = 3
```

表示买卖两边各生成 3 档报价。

`split_count` 控制每一档拆成几笔订单。

例如：

```text
quote_levels = 3
split_count = 2
```

表示：

```text
买方：3 档，每档 2 笔，共 6 笔买单
卖方：3 档，每档 2 笔，共 6 笔卖单
```

每个报价字典包含：

| 字段               | 含义                            |
| -------------------- | --------------------------------- |
| `side`         | 报价方向，`buy`或`sell` |
| `level`        | 当前报价档位                    |
| `order_index`  | 当前档位内第几笔拆单            |
| `price`        | 报价价格                        |
| `volume`       | 报价手数                        |
| `quote_mode`   | 报价模式                        |
| `offset_value` | 当前报价偏移量                  |

需要注意的是，当前代码中的拆单是同一档内生成多笔相同价格、相同手数的订单，并没有进一步做价格分散。

---

### 4.3.9 `need_requote()`：判断是否需要撤单重挂

`need_requote()` 用来判断新报价和当前缓存报价之间的差异是否足够大。

这里的“新报价”指的是本轮 tick 重新计算后的报价，通常已经经过基准价计算、报价生成、库存偏移和仓位过滤。

“旧报价”指的是 `QuoteEngine` 中缓存的上一轮报价：

```text
current_buy_quotes
current_sell_quotes
```

函数会先计算容忍价格差：

```text
tolerance_price = update_tolerance * price_tick
```

然后判断：

```text
1. 买单数量是否变化；
2. 卖单数量是否变化；
3. 买单价格变化是否超过 tolerance_price；
4. 卖单价格变化是否超过 tolerance_price；
5. 买单或卖单手数是否变化。
```

如果上述任意条件成立，就返回 `True`，表示需要撤单重挂。
如果变化不明显，就返回 `False`，表示保留旧报价，不进行重挂。

这个函数的意义是减少不必要的频繁撤单。盘口每个 tick 都可能小幅变化，但如果变化不大，保留原来的挂单可以减少系统压力，也有利于保留订单排队位置。

---

### 4.3.10 报价缓存管理

`QuoteEngine` 内部维护两个报价缓存：

```text
current_buy_quotes
current_sell_quotes
```

其中：

| 变量                      | 含义               |
| --------------------------- | -------------------- |
| `current_buy_quotes`  | 当前缓存的买单报价 |
| `current_sell_quotes` | 当前缓存的卖单报价 |

`update_current_quotes()` 用于在成功发出新报价后，保存当前报价：

```text
current_buy_quotes = buy_quotes
current_sell_quotes = sell_quotes
```

`clear_current_quotes()` 用于清空当前报价缓存，通常在撤单、停止报价或策略重置时调用。

---

### 4.3.11 小结

总体来说，`QuoteEngine` 是策略中的报价生成核心模块。它不负责判断行情是否安全，也不负责实际发单，而是专门负责根据 `fair_price` 计算“应该报什么价格”。

它主要完成三件事：

```text
1. 根据基准价生成买卖双边报价；
2. 将报价价格调整到合法 tick；
3. 判断新报价是否有必要替换旧报价。
```

后续主策略会根据 `QuoteEngine` 生成的 `buy_quotes` 和 `sell_quotes`，再结合风控过滤、库存偏移和订单管理逻辑，决定是否真正发送订单。
## 4.4 InventorySkewEngine：库存偏移模块

### 4.4.1 模块定位

`InventorySkewEngine` 是策略中的库存偏移模块，主要用于通过调整报价实现软库存控制，也可以理解为一种“软对冲”机制。

做市策略会同时在买卖两边挂单，因此可能出现连续买入或连续卖出的情况。如果连续买入，策略会累积多头库存；如果连续卖出，策略会累积空头库存。库存过大后，策略面临的方向性风险会增加。

因此，`InventorySkewEngine` 的作用不是直接平仓，而是根据当前持仓方向，对买卖报价整体进行偏移，让策略更容易降低已有仓位。:contentReference[oaicite:0]{index=0}

简单来说：

```text
多头过多：报价整体下移，降低继续买入的概率，提高卖出的可能性
空头过多：报价整体上移，提高买回的可能性，降低继续卖出的概率
```
---

### 4.4.2 模块核心功能

`InventorySkewEngine` 主要包含以下功能：

| 功能        | 对应函数                    | 说明                   |
| --------- | ----------------------- | -------------------- |
| 应用库存偏移    | `apply_skew()`          | 根据当前持仓对买卖报价进行整体偏移    |
| 计算持仓比例    | `calculate_pos_ratio()` | 计算当前持仓占最大持仓的比例       |
| 计算偏移 tick | `calculate_skew_tick()` | 根据持仓比例计算实际偏移多少个 tick |
| 移动报价      | `move_quotes()`         | 对报价价格进行上移或下移         |
| 被动报价限制    | `apply_passive_limit()` | 防止偏移后的报价主动吃单         |
| 获取偏移状态    | `get_last_skew_tick()`  | 返回上一次偏移 tick 数       |
| 获取持仓比例    | `get_last_pos_ratio()`  | 返回上一次持仓比例            |

---

### 4.4.3 `apply_skew()`：应用库存偏移

`apply_skew()` 是库存偏移模块的核心函数。

它的输入是 `QuoteEngine` 生成的原始买卖报价：

```text
buy_quotes
sell_quotes
```

然后根据当前持仓 `pos` 进行调整。

主要参数如下：

| 参数              | 含义                  |
| --------------- | ------------------- |
| `buy_quotes`    | 原始买单报价列表            |
| `sell_quotes`   | 原始卖单报价列表            |
| `pos`           | 当前净持仓，正数表示多头，负数表示空头 |
| `max_position`  | 最大允许持仓              |
| `price_tick`    | 合约最小变动价位            |
| `max_skew_tick` | 最大允许偏移 tick 数       |
| `snapshot`      | 当前行情快照，用于被动报价限制     |
| `passive`       | 是否保持被动挂单            |

函数执行流程可以概括为：

```text
检查参数是否合法
    ↓
计算 pos_ratio
    ↓
计算 skew_tick
    ↓
复制原始报价，避免直接修改原始列表
    ↓
根据 pos 的方向移动报价
    ↓
如果 passive=True，则再次限制报价不能主动吃单
    ↓
返回调整后的买卖报价
```

---

### 4.4.4 `calculate_pos_ratio()`：计算持仓比例

`calculate_pos_ratio()` 用于计算当前持仓相对于最大允许持仓的比例。

计算公式为：

```text
pos_ratio = pos / max_position
```

其中：

| 参数             | 含义           |
| -------------- | ------------ |
| `pos`          | 当前净持仓        |
| `max_position` | 最大允许持仓       |
| `pos_ratio`    | 当前持仓占最大持仓的比例 |

例如：

```text
pos = 2
max_position = 4

pos_ratio = 2 / 4 = 0.5
```

这表示当前多头仓位已经达到最大允许仓位的 50%。

代码会把 `pos_ratio` 限制在 `[-1, 1]` 之间：

```text
pos_ratio > 1  →  记为 1
pos_ratio < -1 →  记为 -1
```

这样可以避免持仓超过上限时，偏移幅度被无限放大。

---

### 4.4.5 `calculate_skew_tick()`：计算偏移 tick 数

`calculate_skew_tick()` 用于根据持仓比例计算本次报价应该偏移多少个 tick。

计算公式为：

```text
skew_tick = round(abs(pos_ratio) * max_skew_tick)
```

其中：

| 参数              | 含义            |
| --------------- | ------------- |
| `pos_ratio`     | 当前持仓比例        |
| `max_skew_tick` | 最大允许偏移 tick 数 |
| `skew_tick`     | 实际偏移 tick 数   |

例如：

```text
pos_ratio = 0.5
max_skew_tick = 2

skew_tick = round(0.5 * 2) = 1
```

这表示当前报价需要偏移 1 个 tick。

持仓比例越高，`skew_tick` 越大；持仓越接近 0，`skew_tick` 越小。

---

### 4.4.6 `move_quotes()`：移动报价

`move_quotes()` 负责真正修改报价价格。

计算公式为：

```text
调整后价格 = 原价格 + skew_tick * price_tick
```

其中：

| 参数               | 含义        |
| ---------------- | --------- |
| `price_tick`     | 合约最小变动价位  |
| `skew_tick`      | 偏移 tick 数 |
| `adjusted_price` | 偏移后的报价价格  |

如果当前是多头：

```text
pos > 0
```

说明策略已经买多了，需要降低继续买入的概率，同时增加卖出的可能性。因此代码会使用负的 `skew_tick`，把买卖报价整体向下移动。

例如：

```text
原始买价 = 3698
原始卖价 = 3702
price_tick = 1
skew_tick = -1

偏移后买价 = 3697
偏移后卖价 = 3701
```

如果当前是空头：

```text
pos < 0
```

说明策略已经卖多了，需要提高买回的可能性，同时降低继续卖出的概率。因此代码会使用正的 `skew_tick`，把买卖报价整体向上移动。

例如：

```text
原始买价 = 3698
原始卖价 = 3702
price_tick = 1
skew_tick = 1

偏移后买价 = 3699
偏移后卖价 = 3703
```

这就是库存偏移的核心逻辑：不是直接平仓，而是通过调整报价，引导后续成交方向。

---

### 4.4.7 `apply_passive_limit()`：被动报价限制

库存偏移之后，报价可能会变得过于激进。

因此，如果 `passive=True`，模块会调用 `apply_passive_limit()`，确保偏移后的报价不会主动吃单。

限制规则是：

```text
买单价格不能高于 bid1
卖单价格不能低于 ask1
```

对应逻辑为：

```text
buy_price = min(buy_price, bid1)
sell_price = max(sell_price, ask1)
```

这样可以保证，即使经过库存偏移，策略仍然尽量保持挂单做市，而不是主动追价成交。

---

### 4.4.8 状态记录函数

`InventorySkewEngine` 还记录了两个状态变量：

```text
last_skew_tick
last_pos_ratio
```

其中：

| 变量               | 含义               |
| ---------------- | ---------------- |
| `last_skew_tick` | 上一次实际偏移了多少个 tick |
| `last_pos_ratio` | 上一次当前持仓占最大持仓的比例  |

对应函数为：

```text
get_last_skew_tick()
get_last_pos_ratio()
```

这两个函数主要用于策略监控和调试。通过它们可以观察当前库存压力，以及策略为了控制库存对报价做了多大幅度的调整。

---

### 4.4.9 小结

总体来说，`InventorySkewEngine` 是策略中的软库存控制模块。

它主要回答一个问题：

```text
当前持仓已经偏多或偏空时，报价应该如何调整？
```

它不会直接发出平仓单，而是通过移动买卖报价来改变后续成交倾向：

```text
多头过多 → 报价整体下移 → 更容易卖出，较难继续买入
空头过多 → 报价整体上移 → 更容易买回，较难继续卖出
```

因此，这个模块是介于普通报价和强制平仓之间的一层软风险控制机制。

```
```
## 4.5 HedgeEngine：强制平仓模块

### 4.5.1 模块定位

`HedgeEngine` 是策略中的强制平仓模块，主要用于在持仓超过风险阈值后，生成强制平仓指令。

前面的 `InventorySkewEngine` 属于软库存控制，它通过调整报价，让策略更容易自然减仓；而 `HedgeEngine` 属于硬风险控制，当仓位已经超过设定阈值时，不再只是调整报价，而是直接生成平仓指令，主动降低持仓风险。

简单来说：

```text
库存偏移：通过调整报价慢慢降低仓位
强制平仓：仓位超过阈值后，直接生成平仓指令
```

---

### 4.5.2 模块核心功能

`HedgeEngine` 主要包含以下功能：

| 功能                 | 对应函数                           | 说明                                 |
| ---------------------- | ------------------------------------ | -------------------------------------- |
| 检查是否需要强制平仓 | `check_hedge()`                | 根据当前持仓判断是否超过强制平仓阈值 |
| 计算平多价格         | `calculate_sell_close_price()` | 多头超限时，计算卖出平仓价格         |
| 计算平空价格         | `calculate_buy_close_price()`  | 空头超限时，计算买入平仓价格         |
| 更新最近平仓记录     | `update_last_hedge()`          | 记录最近一次强制平仓动作、价格和数量 |
| 清空平仓记录         | `clear_last_hedge()`           | 重置最近一次强制平仓状态             |
| 获取平仓动作         | `get_last_hedge_action()`      | 返回最近一次强制平仓方向             |
| 获取平仓价格         | `get_last_hedge_price()`       | 返回最近一次强制平仓价格             |
| 获取平仓数量         | `get_last_hedge_volume()`      | 返回最近一次强制平仓数量             |

---

### 4.5.3 `check_hedge()`：检查是否触发强制平仓

`check_hedge()` 是 `HedgeEngine` 的核心函数，用于判断当前持仓是否超过强制平仓阈值。

主要输入参数如下：

| 参数                   | 含义                                         |
| ------------------------ | ---------------------------------------------- |
| `pos`              | 当前净持仓，正数表示多头，负数表示空头       |
| `hedge_threshold`  | 强制平仓触发阈值                             |
| `hedge_volume`     | 每次强制平仓的最大数量                       |
| `price_tick`       | 合约最小变动价位                             |
| `snapshot`         | 当前行情快照，主要使用`bid1`和`ask1` |
| `hedge_price_tick` | 强制平仓价格相对盘口偏移的 tick 数           |

函数会先检查参数是否合法：

```text
hedge_threshold > 0
hedge_volume > 0
price_tick > 0
bid1 > 0
ask1 > 0
ask1 > bid1
```

如果这些条件不满足，函数会直接返回 `None`，表示不触发强制平仓。

---

### 4.5.4 多头超限：生成 `SELL_CLOSE`

如果当前持仓满足：

```text
pos >= hedge_threshold
```

说明当前多头仓位过大，需要卖出平仓。

此时 `check_hedge()` 会生成一个强制平仓指令：

```text
SELL_CLOSE
```

也就是卖出平多。

平多价格由 `calculate_sell_close_price()` 计算：

```text
price = bid1 - hedge_price_tick * price_tick
```

其中：

| 参数                   | 含义                        |
| ------------------------ | ----------------------------- |
| `bid1`             | 当前买一价                  |
| `hedge_price_tick` | 相对买一价向下偏移几个 tick |
| `price_tick`       | 合约最小变动价位            |

例如：

```text
bid1 = 3700
price_tick = 1
hedge_price_tick = 1

price = 3700 - 1 * 1 = 3699
```

这样做的目的是让平多单价格略低于买一价，提高成交概率，从而更快降低多头仓位。

---

### 4.5.5 空头超限：生成 `BUY_CLOSE`

如果当前持仓满足：

```text
pos <= -hedge_threshold
```

说明当前空头仓位过大，需要买入平仓。

此时 `check_hedge()` 会生成一个强制平仓指令：

```text
BUY_CLOSE
```

也就是买入平空。

平空价格由 `calculate_buy_close_price()` 计算：

```text
price = ask1 + hedge_price_tick * price_tick
```

其中：

| 参数                   | 含义                        |
| ------------------------ | ----------------------------- |
| `ask1`             | 当前卖一价                  |
| `hedge_price_tick` | 相对卖一价向上偏移几个 tick |
| `price_tick`       | 合约最小变动价位            |

例如：

```text
ask1 = 3702
price_tick = 1
hedge_price_tick = 1

price = 3702 + 1 * 1 = 3703
```

这样做的目的是让平空单价格略高于卖一价，提高成交概率，从而更快降低空头仓位。

---

### 4.5.6 平仓数量控制

强制平仓数量不是直接等于当前全部持仓，而是取：

```text
volume = min(abs(pos), hedge_volume)
```

其中：

| 参数               | 含义                       |
| -------------------- | ---------------------------- |
| `abs(pos)`     | 当前持仓的绝对值           |
| `hedge_volume` | 每次允许强制平仓的最大数量 |
| `volume`       | 本次实际强制平仓数量       |

例如：

```text
pos = 5
hedge_volume = 2

volume = min(5, 2) = 2
```

这表示虽然当前有 5 手多头，但本次只平 2 手。

如果：

```text
pos = 1
hedge_volume = 2

volume = min(1, 2) = 1
```

这表示当前只有 1 手持仓，则最多只能平 1 手，避免平仓数量超过实际持仓。

---

### 4.5.7 返回的 `hedge_order`

当触发强制平仓时，`check_hedge()` 不会直接发单，而是返回一个字典形式的强制平仓指令。

多头超限时返回：

```python
{
    "action": "SELL_CLOSE",
    "price": price,
    "volume": volume,
    "reason": "long_position_exceed_threshold",
}
```

空头超限时返回：

```python
{
    "action": "BUY_CLOSE",
    "price": price,
    "volume": volume,
    "reason": "short_position_exceed_threshold",
}
```

这个 `hedge_order` 只是一个内部信号，真正的下单动作会在主策略中完成。

主策略会根据：

```text
action = SELL_CLOSE
```

调用 `sell()` 平多；根据：

```text
action = BUY_CLOSE
```

调用 `cover()` 平空。

---

### 4.5.8 状态记录函数

`HedgeEngine` 内部记录了最近一次强制平仓的信息：

```text
last_hedge_action
last_hedge_price
last_hedge_volume
```

含义如下：

| 变量                    | 含义                 |
| ------------------------- | ---------------------- |
| `last_hedge_action` | 最近一次强制平仓方向 |
| `last_hedge_price`  | 最近一次强制平仓价格 |
| `last_hedge_volume` | 最近一次强制平仓数量 |

`update_last_hedge()` 用于在生成强制平仓指令后更新这些变量。

`clear_last_hedge()` 用于清空最近一次强制平仓记录，通常在强制平仓状态结束后调用。

`get_last_hedge_action()`、`get_last_hedge_price()` 和 `get_last_hedge_volume()` 则用于主策略读取最近一次强制平仓状态，方便监控和调试。

---

### 4.5.9 小结

总体来说，`HedgeEngine` 是策略中的强制风险处理模块。

它主要回答一个问题：

```text
当前持仓是否已经超过强制平仓阈值？如果超过，应该以什么方向、什么价格、多少数量进行平仓？
```

它和 `InventorySkewEngine` 的区别在于：

```text
InventorySkewEngine：通过调整报价实现软对冲
HedgeEngine：通过生成平仓指令实现硬风控
```

因此，`HedgeEngine` 是策略库存风险控制的最后一层保护。当软库存偏移不足以控制仓位时，它会触发强制平仓逻辑，帮助策略快速降低风险暴露。



## 4.6 CancelAdvancedOrder：主策略调度模块

### 4.6.1 模块定位

`CancelAdvancedOrder` 是本策略的主策略类，继承自 vn.py 的 `CtaTemplate`。前面的 `PricingEngine`、`QuoteEngine`、`QuoteRiskFilter`、`InventorySkewEngine` 和 `HedgeEngine` 都是功能模块，而 `CancelAdvancedOrder` 负责把这些模块串联起来，形成完整的事件驱动做市策略。:contentReference[oaicite:0]{index=0}

简单来说，主策略主要负责：

```text
1. 接收 vn.py 推送的行情、成交、订单等事件；
2. 调用各个子模块完成定价、报价、风控、库存偏移和强制平仓；
3. 管理普通做市订单和强制平仓订单；
4. 维护策略运行状态和监控变量。
````

---

### 4.6.2 策略参数分类说明

主策略中定义了较多参数，可以按照功能分为以下几类：

| 参数类别   | 主要作用                         |
| ------ | ---------------------------- |
| 定价参数   | 控制 fair_price 如何计算           |
| 报价参数   | 控制买卖报价如何生成                   |
| 风控过滤参数 | 控制什么行情下允许报价                  |
| 库存控制参数 | 控制持仓偏移和最大仓位                  |
| 强制平仓参数 | 控制何时触发 hedge，以及 hedge 的数量和价格 |
| 订单行为参数 | 控制成交后是否撤单、是否保持被动报价           |

---

### 4.6.3 定价参数

定价参数主要影响 `PricingEngine` 计算出来的 `fair_price`。

| 参数                  |                默认值 | 含义             | 调大/调小的意义                                                                   |
| ------------------- | -----------------: | -------------- | -------------------------------------------------------------------------- |
| `pricing_method`    | `"depth_weighted"` | 基准价计算方式        | 可选择 `mid`、`micro`、`depth_weighted`、`exp_depth_weighted`，不同方法代表对盘口信息的利用程度不同 |
| `pricing_depth`     |                `5` | 使用几档盘口计算基准价    | 调大：使用更多盘口信息，更稳定；调小：更关注近端盘口，更敏感                                             |
| `exp_depth_decay`   |              `0.6` | 指数加权盘口的衰减系数    | 调大：远端盘口权重更高；调小：更重视买一卖一附近的近端盘口                                              |
| `use_ema_smoothing` |             `True` | 是否对基准价做 EMA 平滑 | 开启后基准价更平滑，但反应更慢；关闭后更敏感，但可能更抖                                               |
| `ema_alpha`         |              `0.2` | EMA 平滑系数       | 调大：更跟随最新行情；调小：更平滑，但滞后更明显                                                   |

这一组参数决定策略的“定价风格”。如果参数偏敏感，策略会更快跟随盘口变化；如果参数偏平滑，策略会减少频繁撤单，但可能对行情反应慢一些。

---

### 4.6.4 报价参数

报价参数主要影响 `QuoteEngine` 如何围绕 `fair_price` 生成买卖双边报价。

| 参数                       |      默认值 | 含义                      | 调大/调小的意义                                  |
| ------------------------ | -------: | ----------------------- | ----------------------------------------- |
| `quote_mode`             | `"tick"` | 报价模式                    | `tick` 表示按最小变动价位报价；`percent` 表示按百分比偏移报价   |
| `quote_levels`           |      `1` | 报价档数                    | 调大：买卖两边挂更多档，覆盖更宽价格区间；调小：订单更少，策略更简单        |
| `order_volume`           |      `1` | 每笔报价手数                  | 调大：单笔成交量更大，收益和风险都放大；调小：风险更小，但收益空间也小       |
| `spread_tick`            |      `2` | tick 模式下第一档距离基准价几个 tick | 调大：报价更远，成交概率降低但单次价差更大；调小：报价更近，成交概率提高但价差变小 |
| `level_interval_tick`    |      `1` | tick 模式下每档之间间隔几个 tick   | 调大：多档之间更分散；调小：多档报价更集中                     |
| `spread_percent`         | `0.0002` | percent 模式下第一档距离基准价的百分比 | 调大：报价更宽；调小：报价更贴近基准价                       |
| `level_interval_percent` | `0.0001` | percent 模式下每档之间增加的百分比   | 调大：多档报价分布更分散；调小：多档报价更集中                   |
| `split_count`            |      `1` | 每档拆成几笔单                 | 调大：每档订单数增加；调小：订单数量减少                      |
| `update_tolerance`       |      `2` | 报价更新容忍度，单位是 tick        | 调大：更不容易重挂，策略更稳定；调小：更频繁跟随最新报价              |

这一组参数决定策略的“报价风格”。如果 `spread_tick` 小、`update_tolerance` 小，策略会更激进、更频繁报价；如果 `spread_tick` 大、`update_tolerance` 大，策略会更保守、更少重挂。

---

### 4.6.5 风控过滤参数

风控过滤参数主要由 `QuoteRiskFilter` 使用，用来判断当前行情是否适合做市。

| 参数                  |    默认值 | 含义              | 调大/调小的意义                     |
| ------------------- | -----: | --------------- | ---------------------------- |
| `min_depth`         |    `3` | 最小有效盘口深度        | 调大：要求盘口更深，过滤更严格；调小：允许更浅盘口下报价 |
| `min_spread_tick`   |    `1` | 最小买卖价差要求        | 调大：只在价差更大时做市；调小：允许更窄价差下做市    |
| `depth_check_level` |    `5` | 检查前几档盘口挂单量和不平衡  | 调大：参考更多档盘口；调小：更关注近端盘口        |
| `min_depth_volume`  |   `30` | 前 N 档买卖盘最小挂单量要求 | 调大：要求盘口更厚，过滤更严格；调小：允许更薄盘口报价  |
| `max_imbalance`     | `0.70` | 最大允许盘口不平衡程度     | 调大：容忍更强的买卖盘失衡；调小：更严格过滤一边倒盘口  |

这一组参数决定策略是否“挑行情”。参数越严格，策略报价机会越少，但安全性更高；参数越宽松，策略报价机会更多，但可能暴露在更差的盘口环境中。

---

### 4.6.6 库存控制参数

库存控制参数主要影响 `InventorySkewEngine` 和仓位硬过滤逻辑。

| 参数              | 默认值 | 含义            | 调大/调小的意义                         |
| --------------- | --: | ------------- | -------------------------------- |
| `max_position`  | `4` | 最大允许净持仓       | 调大：允许更大库存，成交机会更多但风险更大；调小：仓位控制更严格 |
| `max_skew_tick` | `2` | 最大库存偏移 tick 数 | 调大：持仓偏移更明显，减仓倾向更强；调小：报价受库存影响更小   |

`max_position` 是硬限制，仓位达到上限后，会直接过滤掉继续加仓的一边报价。
`max_skew_tick` 是软控制，它不会直接禁止报价，而是通过移动报价来引导成交方向。

---

### 4.6.7 强制平仓参数

强制平仓参数主要影响 `HedgeEngine` 的触发和执行。

| 参数                 |    默认值 | 含义                | 调大/调小的意义                         |
| ------------------ | -----: | ----------------- | -------------------------------- |
| `enable_hedge`     | `True` | 是否启用强制平仓          | 开启后仓位超限会触发 hedge；关闭后只依靠库存偏移和仓位过滤 |
| `hedge_threshold`  |    `3` | 强制平仓触发阈值          | 调大：更晚触发强制平仓；调小：更早触发强制平仓          |
| `hedge_volume`     |    `1` | 每次强制平仓数量          | 调大：每次平仓更快，但冲击更大；调小：平仓更温和，但恢复仓位更慢 |
| `hedge_price_tick` |    `0` | 平仓价格相对盘口偏移 tick 数 | 调大：更激进，提高成交概率；调小：更保守，可能不容易成交     |

这一组参数决定策略在库存风险过高时的处理强度。
如果 `hedge_threshold` 低、`hedge_volume` 大、`hedge_price_tick` 大，强制平仓会更积极；反之则更保守。

---

### 4.6.8 订单行为参数

订单行为参数控制策略在成交和报价时的具体行为。

| 参数                |    默认值 | 含义           | 调大/调小的意义                            |
| ----------------- | -----: | ------------ | ----------------------------------- |
| `cancel_on_trade` | `True` | 成交后是否撤销普通做市单 | 开启后成交即撤旧单，等待下一轮重新报价；关闭后原报价可能继续保留    |
| `passive_quote`   | `True` | 是否保持被动报价     | 开启后买价不高于 bid1，卖价不低于 ask1；关闭后报价可能更激进 |

`cancel_on_trade=True` 的意义是：成交后仓位和盘口都可能发生变化，所以先撤掉旧报价，避免旧报价在新环境下继续暴露风险。

`passive_quote=True` 的意义是：策略尽量挂单提供流动性，而不是主动追价吃单。

---

### 4.6.9 策略变量说明

除了参数外，主策略还维护了一组运行变量，用于记录策略状态。

| 变量                   | 含义              |
| -------------------- | --------------- |
| `price_tick`         | 合约最小变动价位        |
| `contract_size`      | 合约乘数            |
| `bid1`               | 当前买一价           |
| `ask1`               | 当前卖一价           |
| `market_spread`      | 当前买卖价差          |
| `valid_depth`        | 当前有效盘口深度        |
| `fair_price`         | 当前做市基准价         |
| `active_order_count` | 当前活跃订单总数        |
| `mm_order_count`     | 当前普通做市订单数量      |
| `hedge_order_count`  | 当前强制平仓订单数量      |
| `trade_count`        | 当前累计成交次数        |
| `last_skew_tick`     | 最近一次库存偏移 tick 数 |
| `last_pos_ratio`     | 最近一次持仓比例        |
| `last_hedge_action`  | 最近一次强制平仓方向      |
| `last_hedge_price`   | 最近一次强制平仓价格      |
| `last_hedge_volume`  | 最近一次强制平仓数量      |
| `hedging`            | 当前是否处于强制平仓状态    |

这些变量主要用于策略监控和界面展示，方便观察策略当前运行情况。

---

### 4.6.10 主策略初始化逻辑

在 `__init__()` 中，主策略会初始化所有子模块：

```text
MarketDataManager
PricingEngine
QuoteEngine
InventorySkewEngine
HedgeEngine
QuoteRiskFilter
```

同时，策略还维护三类订单集合：

| 变量               | 含义          |
| ---------------- | ----------- |
| `orders`         | 保存全部订单记录    |
| `mm_orderids`    | 保存普通做市订单 ID |
| `hedge_orderids` | 保存强制平仓订单 ID |

这样设计的好处是：普通做市订单和强制平仓订单可以分开管理。撤普通单时不会误撤 hedge 单，处理 hedge 时也不会混淆普通做市订单。

---

### 4.6.11 `on_start()`：策略启动逻辑

策略启动时会执行 `on_start()`。

主要流程是：

```text
1. 获取合约最小变动价位 price_tick
2. 获取合约乘数 contract_size
3. 重置 PricingEngine
4. 清空报价缓存
5. 清空订单记录
6. 清空普通做市订单 ID
7. 清空强制平仓订单 ID
8. 清空最近一次 hedge 记录
9. 设置 hedging = False
```

这个函数的作用是让策略每次启动时都从干净状态开始，避免上一次运行的订单、报价缓存或 EMA 状态影响本次运行。

---

### 4.6.12 `on_tick()`：普通做市主流程

`on_tick()` 是主策略中最核心的普通做市逻辑。每当 vn.py 收到新的 tick 行情时，就会触发该函数。

执行流程如下：

```text
Tick 行情到来
    ↓
MarketDataManager 更新行情快照
    ↓
更新 bid1、ask1、market_spread、valid_depth
    ↓
如果 hedging=True，暂停普通报价
    ↓
QuoteRiskFilter 进行行情过滤
    ↓
PricingEngine 计算 fair_price
    ↓
QuoteEngine 生成原始买卖报价
    ↓
InventorySkewEngine 进行库存偏移
    ↓
QuoteRiskFilter 根据 max_position 做仓位硬过滤
    ↓
QuoteEngine.need_requote() 判断是否需要撤单重挂
    ↓
如果需要重挂：
    撤销旧普通做市单
    发送新的 buy / short 订单
    更新报价缓存
```

这里的关键点是：`on_tick()` 不只是简单发单，而是完整串联了行情、定价、报价、风控和库存控制。

---

### 4.6.13 `on_trade()`：成交处理逻辑

当订单成交时，vn.py 会触发 `on_trade()`。

执行流程是：

```text
1. trade_count += 1
2. 如果 cancel_on_trade=True，撤销普通做市单并清空报价缓存
3. 如果 enable_hedge=True，检查是否需要强制平仓
4. 更新订单数量
5. 推送界面状态
```

成交后撤单的原因是：成交会改变仓位，原来的报价可能已经不适合当前状态，因此需要等待下一轮 tick 重新计算报价。

---

### 4.6.14 `on_order()`：订单状态维护逻辑

当订单状态变化时，会触发 `on_order()`。

执行流程是：

```text
1. 将订单更新到 orders 字典
2. 如果订单不再活跃，从 mm_orderids 和 hedge_orderids 中移除
3. 如果当前处于 hedging=True 且没有 hedge 订单：
       检查仓位是否回到 hedge_threshold 以内
       如果已经回到阈值以内，则 hedging=False
4. 更新订单数量
5. 推送界面状态
```

这个函数的核心作用是维护订单集合，确保策略内部知道哪些订单仍然活跃，哪些订单已经结束。

---

### 4.6.15 `check_and_send_hedge_order()`：强制平仓调度逻辑

`check_and_send_hedge_order()` 是主策略中负责调用 `HedgeEngine` 的函数。

执行流程是：

```text
获取当前 snapshot
    ↓
调用 HedgeEngine.check_hedge()
    ↓
如果没有触发 hedge：
    return
    ↓
如果已经有 hedge 单在挂：
    return
    ↓
设置 hedging = True
    ↓
撤销普通做市单
    ↓
如果 action = SELL_CLOSE：
    调用 sell() 平多
如果 action = BUY_CLOSE：
    调用 cover() 平空
    ↓
记录 hedge_orderids
    ↓
更新最近 hedge 状态
```

这里有一个重要设计：一旦进入 `hedging=True`，后续 `on_tick()` 会直接返回，不再发普通做市单。这样可以避免策略一边强制平仓，一边继续做市加仓。

---

### 4.6.16 订单管理辅助函数

主策略中还包含几个辅助函数，用于管理订单。

| 函数                              | 作用                       |
| ------------------------------- | ------------------------ |
| `cancel_market_making_orders()` | 只撤普通做市订单，不撤强制平仓订单        |
| `cancel_hedge_orders()`         | 只撤强制平仓订单                 |
| `update_order_count()`          | 更新普通订单数、hedge 订单数和活跃订单总数 |

其中，普通做市订单和强制平仓订单是分开维护的：

```text
mm_orderids      普通做市订单
hedge_orderids   强制平仓订单
```

这种分离设计可以降低订单管理混乱的风险。

---

### 4.6.17 主策略整体逻辑总结

整体来看，主策略的运行逻辑可以概括为：

```text
行情来了：
    更新行情 → 风控检查 → 计算基准价 → 生成报价 → 库存偏移 → 仓位过滤 → 判断重挂 → 发普通做市单

成交了：
    记录成交 → 撤普通做市单 → 检查是否需要强制平仓

订单状态变了：
    更新订单集合 → 清理已结束订单 → 判断 hedge 是否结束

强制平仓触发：
    暂停普通做市 → 撤普通单 → 发平仓单 → 等待 hedge 结束
```

因此，`CancelAdvancedOrder` 不是一个单独的计算模块，而是整个策略的调度中心。它负责把行情、报价、风控、库存偏移、强制平仓和订单管理整合成一个完整的事件驱动做市系统。

