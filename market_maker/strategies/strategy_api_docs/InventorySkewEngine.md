
# `InventorySkewEngine`（报价调整）

**架构定位**：库存控制模块。负责根据当前持仓方向和持仓比例，对原始买卖报价进行整体偏移，从而通过报价调整实现软对冲。

它不直接发出平仓单，也不主动吃单，而是通过改变报价位置，引导后续成交方向，让策略更容易降低已有库存风险。

简单来说：

```text
多头偏多 → 报价整体下移 → 降低继续买入概率，提高卖出概率
空头偏多 → 报价整体上移 → 提高买回概率，降低继续卖出概率
````

---

## 📋 核心方法速查

| 方法名                   | 参数类型                                                                                                                                                                           | 返回值                             | 作用说明                                              |
| :-------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------ | :------------------------------------------------ |
| `__init__`            | 无                                                                                                                                                                              | `None`                          | 初始化库存偏移状态：`last_skew_tick=0`、`last_pos_ratio=0.0` |
| `apply_skew`          | `buy_quotes: list[dict]`, `sell_quotes: list[dict]`, `pos: float`, `max_position: float`, `price_tick: float`, `max_skew_tick: int`, `snapshot: dict \| None`, `passive: bool` | `tuple[list[dict], list[dict]]` | 核心函数。根据当前持仓对买卖报价进行整体偏移                            |
| `calculate_pos_ratio` | `pos: float`, `max_position: float`                                                                                                                                            | `float`                         | 计算当前持仓占最大持仓的比例，并限制在 `[-1, 1]`                     |
| `calculate_skew_tick` | `pos_ratio: float`, `max_skew_tick: int`                                                                                                                                       | `int`                           | 根据持仓比例计算本次需要偏移多少个 tick                            |
| `move_quotes`         | `quotes: list[dict]`, `price_tick: float`, `skew_tick: int`                                                                                                                    | `list[dict]`                    | 对报价列表整体上移或下移                                      |
| `apply_passive_limit` | `buy_quotes: list[dict]`, `sell_quotes: list[dict]`, `snapshot: dict`                                                                                                          | `tuple[list[dict], list[dict]]` | 偏移后再次限制报价，避免主动吃单                                  |
| `get_last_skew_tick`  | 无                                                                                                                                                                              | `int`                           | 获取最近一次库存偏移 tick 数                                 |
| `get_last_pos_ratio`  | 无                                                                                                                                                                              | `float`                         | 获取最近一次持仓比例                                        |

---

## 📦 输入数据说明

`apply_skew()` 是本模块最核心的函数，主要输入如下：

| 参数              | 类型             | 说明                  |
| :-------------- | :------------- | :------------------ |
| `buy_quotes`    | `list[dict]`   | 原始买单报价列表            |
| `sell_quotes`   | `list[dict]`   | 原始卖单报价列表            |
| `pos`           | `float`        | 当前净持仓，正数表示多头，负数表示空头 |
| `max_position`  | `float`        | 最大允许持仓，用来衡量库存压力     |
| `price_tick`    | `float`        | 合约最小变动价位            |
| `max_skew_tick` | `int`          | 最大允许偏移 tick 数       |
| `snapshot`      | `dict \| None` | 当前行情快照，主要用于被动报价限制   |
| `passive`       | `bool`         | 是否保持被动挂单            |

输入的 `buy_quotes` 和 `sell_quotes` 通常来自 `QuoteEngine.generate_quotes()`。也就是说，库存偏移是在原始双边报价基础上进行的二次调整。

---

## 💡 核心逻辑

### 1. 持仓比例计算：`calculate_pos_ratio()`

库存偏移首先需要判断当前仓位压力有多大。

计算公式是：

```text
pos_ratio = pos / max_position
```

其中：

| 参数             | 含义           |
| :------------- | :----------- |
| `pos`          | 当前净持仓        |
| `max_position` | 最大允许持仓       |
| `pos_ratio`    | 当前持仓占最大持仓的比例 |

例如：

```text
pos = 2
max_position = 4

pos_ratio = 2 / 4 = 0.5
```

表示当前多头仓位已经达到最大允许仓位的 50%。

代码会把 `pos_ratio` 限制在 `[-1, 1]`：

```text
pos_ratio > 1  →  记为 1
pos_ratio < -1 →  记为 -1
```

这样可以避免持仓超过上限时偏移幅度无限放大。

---

### 2. 偏移 tick 计算：`calculate_skew_tick()`

得到持仓比例后，策略会计算报价需要偏移多少个 tick。

公式是：

```text
skew_tick = round(abs(pos_ratio) * max_skew_tick)
```

其中：

| 参数              | 含义            |
| :-------------- | :------------ |
| `pos_ratio`     | 当前持仓比例        |
| `max_skew_tick` | 最大允许偏移 tick 数 |
| `skew_tick`     | 本次实际偏移 tick 数 |

例如：

```text
pos_ratio = 0.5
max_skew_tick = 2

skew_tick = round(0.5 * 2) = 1
```

表示本次报价需要偏移 1 个 tick。

持仓比例越高，偏移越明显；持仓接近 0 时，偏移较小或不偏移。

---

### 3. 报价移动：`move_quotes()`

真正修改报价价格的是 `move_quotes()`。

计算公式是：

```text
adjusted_price = original_price + skew_tick * price_tick
```

其中：

| 参数               | 含义                   |
| :--------------- | :------------------- |
| `original_price` | 原始报价价格               |
| `skew_tick`      | 偏移 tick 数，可以为正，也可以为负 |
| `price_tick`     | 合约最小变动价位             |
| `adjusted_price` | 偏移后的报价价格             |

---

## 🔁 多头和空头下的报价偏移

### 1. 多头偏多：报价整体下移

如果：

```text
pos > 0
```

说明策略当前多头库存偏多。此时策略不希望继续买入，而是希望更容易卖出。

因此代码会使用负的 `skew_tick`，让买卖报价整体下移：

```text
adjusted_price = original_price - skew_tick * price_tick
```

例如：

```text
原始买价 = 3698
原始卖价 = 3702
price_tick = 1
skew_tick = 1

偏移后买价 = 3697
偏移后卖价 = 3701
```

含义是：

```text
买价下移 → 不容易继续买入
卖价下移 → 更容易卖出减仓
```

---

### 2. 空头偏多：报价整体上移

如果：

```text
pos < 0
```

说明策略当前空头库存偏多。此时策略不希望继续卖出，而是希望更容易买回。

因此代码会使用正的 `skew_tick`，让买卖报价整体上移：

```text
adjusted_price = original_price + skew_tick * price_tick
```

例如：

```text
原始买价 = 3698
原始卖价 = 3702
price_tick = 1
skew_tick = 1

偏移后买价 = 3699
偏移后卖价 = 3703
```

含义是：

```text
买价上移 → 更容易买回平空
卖价上移 → 不容易继续卖出
```

---

## 🧊 被动报价限制：`apply_passive_limit()`

库存偏移之后，报价可能变得过于激进。
因此，如果 `passive=True` 且传入了 `snapshot`，模块会再次限制报价，避免主动吃单。

规则是：

```text
买单价格不能高于 bid1
卖单价格不能低于 ask1
```

对应逻辑是：

```text
buy_price = min(buy_price, bid1)
sell_price = max(sell_price, ask1)
```

这样可以保证库存偏移之后，策略仍然尽量保持 Maker 挂单，而不是主动 Taker 吃单。

---

## 🗂️ 状态缓存

模块内部记录两个状态变量：

```text
last_skew_tick
last_pos_ratio
```

| 变量               | 含义                |
| :--------------- | :---------------- |
| `last_skew_tick` | 最近一次实际偏移了多少个 tick |
| `last_pos_ratio` | 最近一次当前持仓占最大持仓的比例  |

对应方法：

| 方法                     | 作用                |
| :--------------------- | :---------------- |
| `get_last_skew_tick()` | 获取最近一次库存偏移 tick 数 |
| `get_last_pos_ratio()` | 获取最近一次持仓比例        |

这些状态主要用于 UI 展示、日志监控和调试。

---

## ⚙️ 参数调节含义

| 参数              | 作用            | 调大/调小影响                                |
| :-------------- | :------------ | :------------------------------------- |
| `max_position`  | 最大允许持仓        | 调大：允许更大库存，软偏移触发更慢；调小：仓位更容易接近上限，库存控制更严格 |
| `max_skew_tick` | 最大报价偏移 tick 数 | 调大：库存偏移更强，减仓倾向更明显；调小：报价受库存影响更小         |
| `price_tick`    | 合约最小变动价位      | 决定每个 tick 偏移对应的真实价格距离                  |
| `passive`       | 是否保持被动报价      | 开启后偏移报价不会主动吃单；关闭后报价可能更激进               |

---

## ✅ 小结

`InventorySkewEngine` 是策略中的软库存控制模块。

它主要回答一个问题：

```text
当前库存偏多或偏空时，报价应该往哪个方向移动？
```

它和强制平仓模块的区别是：

| 模块                    | 控制方式   | 是否直接平仓 | 作用               |
| :-------------------- | :----- | :----- | :--------------- |
| `InventorySkewEngine` | 调整报价   | 否      | 通过报价引导成交方向，实现软对冲 |
| `HedgeEngine`         | 生成平仓指令 | 是      | 仓位超过阈值后主动降低风险    |

因此，`InventorySkewEngine` 是普通做市报价和强制平仓之间的一层缓冲机制，用来在日常行情中尽量通过报价调整自然降低库存风险。

```
```
