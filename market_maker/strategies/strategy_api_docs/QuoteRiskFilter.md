# 🛡️ `QuoteRiskFilter`（报价风控过滤模块）

**架构定位**：报价前置风控模块。负责判断当前行情是否适合做市，并根据当前持仓限制过滤报价。

在做市策略中，策略不会在任何行情下都无条件挂单。如果盘口异常、深度不足、价差太小、盘口太薄，或者买卖盘严重失衡，继续报价可能会带来较高风险。因此，`QuoteRiskFilter` 相当于策略发单前的安全检查层。

简单来说，它主要回答两个问题：

```text
当前行情适不适合做市？
当前仓位还允不允许继续挂这一边的单？
````

---

## 📋 核心方法速查

| 方法名                  | 参数类型                                                                                     | 返回值                             | 作用说明               |
| :------------------- | :--------------------------------------------------------------------------------------- | :------------------------------ | :----------------- |
| `check_market_data`  | `snapshot: dict`                                                                         | `bool`                          | 检查基础买一卖一盘口是否合法     |
| `check_depth`        | `snapshot: dict`, `min_depth: int=1`                                                     | `bool`                          | 检查当前有效盘口深度是否达到最低要求 |
| `check_spread`       | `snapshot: dict`, `price_tick: float`, `min_spread_tick: int`                            | `bool`                          | 检查当前买卖价差是否足够       |
| `check_depth_volume` | `snapshot: dict`, `depth: int=5`, `min_depth_volume: float=1`                            | `bool`                          | 检查前 N 档买卖盘挂单量是否充足  |
| `check_imbalance`    | `snapshot: dict`, `max_imbalance: float=0.9`, `depth: int=5`                             | `bool`                          | 检查盘口买卖力量是否过度失衡     |
| `filter_by_position` | `buy_quotes: list[dict]`, `sell_quotes: list[dict]`, `pos: float`, `max_position: float` | `tuple[list[dict], list[dict]]` | 根据当前持仓过滤会继续加仓的一边报价 |

---

## 📦 输入数据：`snapshot`

`QuoteRiskFilter` 主要依赖 `MarketDataManager` 生成的 `snapshot` 行情快照。

常用字段包括：

| 字段名             | 类型            | 说明                        |
| :-------------- | :------------ | :------------------------ |
| `bid1`          | `float`       | 当前买一价                     |
| `ask1`          | `float`       | 当前卖一价                     |
| `bid1_volume`   | `float`       | 当前买一挂单量                   |
| `ask1_volume`   | `float`       | 当前卖一挂单量                   |
| `market_spread` | `float`       | 当前买卖价差，通常等于 `ask1 - bid1` |
| `valid_depth`   | `int`         | 当前有效盘口深度                  |
| `bid_volumes`   | `list[float]` | 买一到买五挂单量                  |
| `ask_volumes`   | `list[float]` | 卖一到卖五挂单量                  |

---

## 💡 核心过滤逻辑

### 1. 基础盘口检查：`check_market_data()`

`check_market_data()` 用于检查最基础的买一卖一数据是否合法。

检查条件是：

```text
bid1 > 0
ask1 > 0
ask1 > bid1
bid1_volume > 0
ask1_volume > 0
```

如果这些条件中任意一个不满足，说明当前盘口数据异常，策略不会继续报价。

例如：

```text
ask1 <= bid1
```

说明买卖价关系异常，可能是行情数据错误、盘口断流，或者当前不是正常交易状态。

---

### 2. 有效深度检查：`check_depth()`

`check_depth()` 用来判断当前盘口有效深度是否达到最低要求。

核心判断是：

```text
valid_depth >= min_depth
```

其中：

| 参数            | 含义          |
| :------------ | :---------- |
| `valid_depth` | 当前实际有效盘口深度  |
| `min_depth`   | 策略要求的最小盘口深度 |

例如：

```text
min_depth = 3
```

表示当前盘口至少需要有 3 档有效买卖盘，策略才允许继续报价。

如果盘口深度不足，说明当前流动性不够，策略容易在较薄盘口中被快速成交或被价格打穿。

---

### 3. 买卖价差检查：`check_spread()`

`check_spread()` 用来判断当前买卖价差是否达到最低要求。

计算逻辑是：

```text
spread_tick = market_spread / price_tick
```

其中：

```text
market_spread = ask1 - bid1
```

然后判断：

```text
spread_tick >= min_spread_tick
```

参数含义如下：

| 参数                | 含义              |
| :---------------- | :-------------- |
| `market_spread`   | 当前买卖价差          |
| `price_tick`      | 合约最小变动价位        |
| `spread_tick`     | 当前价差折算成多少个 tick |
| `min_spread_tick` | 最小价差要求          |

如果价差太小，做市空间不足，策略就不会报价。

这个过滤的意义是避免在价差过窄时做市，因为价差可能不足以覆盖手续费、滑点和被动成交风险。

---

### 4. 盘口挂单量检查：`check_depth_volume()`

`check_depth_volume()` 用来检查前 N 档买卖盘总挂单量是否足够。

它会分别计算：

```text
bid_volume_sum = sum(bid_volumes[:depth])
ask_volume_sum = sum(ask_volumes[:depth])
```

然后判断：

```text
bid_volume_sum >= min_depth_volume
ask_volume_sum >= min_depth_volume
```

其中，实际检查深度会取：

```text
depth = min(depth, valid_depth, 5)
```

这样可以避免检查超过实际有效盘口的数据。

如果买盘或卖盘挂单量太小，说明盘口较薄，市场流动性不足，策略会停止报价。

---

### 5. 盘口不平衡检查：`check_imbalance()`

`check_imbalance()` 用于判断买卖盘是否过度失衡。

计算公式是：

```text
imbalance = (bid_volume_sum - ask_volume_sum) / (bid_volume_sum + ask_volume_sum)
```

含义是：

```text
imbalance > 0：买盘更厚
imbalance < 0：卖盘更厚
imbalance 接近 1：买盘远大于卖盘
imbalance 接近 -1：卖盘远大于买盘
```

最后判断：

```text
abs(imbalance) <= max_imbalance
```

如果 `abs(imbalance)` 超过 `max_imbalance`，说明盘口一边倒，短期价格可能存在明显方向性风险，策略不会继续报价。

---

## ⚖️ 仓位过滤逻辑：`filter_by_position()`

`filter_by_position()` 用来根据当前持仓过滤报价。

它不是判断行情，而是判断当前仓位是否还允许继续挂某一边订单。

逻辑是：

```text
如果 pos >= max_position：
    删除 buy_quotes

如果 pos <= -max_position：
    删除 sell_quotes
```

其中：

| 参数             | 含义                  |
| :------------- | :------------------ |
| `pos`          | 当前净持仓，正数表示多头，负数表示空头 |
| `max_position` | 最大允许持仓              |
| `buy_quotes`   | 当前准备挂出的买单报价         |
| `sell_quotes`  | 当前准备挂出的卖单报价         |

例如：

```text
pos = 4
max_position = 4
```

说明当前多头已经达到上限，此时不能继续挂买单，否则买单成交后会让多头仓位继续扩大。因此代码会清空 `buy_quotes`。

如果：

```text
pos = -4
max_position = 4
```

说明当前空头已经达到上限，此时不能继续挂卖单，否则卖单成交后会让空头仓位继续扩大。因此代码会清空 `sell_quotes`。

---

## ⚙️ 参数调节含义

| 参数                  | 作用           | 调大/调小影响                       |
| :------------------ | :----------- | :---------------------------- |
| `min_depth`         | 最小有效盘口深度     | 调大：过滤更严格，只在盘口更深时报价；调小：允许浅盘口报价 |
| `min_spread_tick`   | 最小买卖价差要求     | 调大：只在价差更宽时报价；调小：允许更窄价差下报价     |
| `depth_check_level` | 检查前几档盘口      | 调大：参考更多档盘口；调小：更关注近端盘口         |
| `min_depth_volume`  | 前 N 档最小挂单量要求 | 调大：要求盘口更厚；调小：允许较薄盘口报价         |
| `max_imbalance`     | 最大允许盘口失衡程度   | 调大：更宽松，容忍更强失衡；调小：更严格，过滤一边倒盘口  |
| `max_position`      | 最大允许净持仓      | 调大：允许更大库存风险；调小：仓位控制更保守        |

---

## ✅ 小结

`QuoteRiskFilter` 是策略发单前的风控过滤层。

它主要完成两件事：

```text
1. 判断当前行情是否适合做市；
2. 判断当前持仓是否允许继续挂某一边报价。
```

如果行情检查不通过，主策略会撤销普通做市单并停止报价。
如果仓位达到上限，模块会删除可能继续扩大风险仓位的一边报价。

因此，`QuoteRiskFilter` 是连接行情质量判断和仓位风险控制的关键模块。

```
```
