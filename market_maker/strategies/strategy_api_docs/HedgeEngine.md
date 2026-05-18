
# 🚨 `HedgeEngine`（强制平仓 / 硬风控模块）

**架构定位**：强制风险控制模块。负责在当前持仓超过设定阈值时，生成强制平仓指令。

它和 `InventorySkewEngine` 的区别是：

```text
InventorySkewEngine：通过调整报价实现软对冲
HedgeEngine：通过生成平仓指令实现硬风控
````

也就是说，`InventorySkewEngine` 是让策略尽量通过正常挂单慢慢降低库存；而 `HedgeEngine` 是当仓位已经超过风险阈值时，直接生成平仓动作，主动降低风险暴露。

---

## 📋 核心方法速查

| 方法名                          | 参数类型                                                                                                                            | 返回值            | 作用说明                                                                   |
| :--------------------------- | :------------------------------------------------------------------------------------------------------------------------------ | :------------- | :--------------------------------------------------------------------- |
| `__init__`                   | 无                                                                                                                               | `None`         | 初始化强制平仓状态缓存：`last_hedge_action`、`last_hedge_price`、`last_hedge_volume` |
| `check_hedge`                | `pos: float`, `hedge_threshold: float`, `hedge_volume: float`, `price_tick: float`, `snapshot: dict`, `hedge_price_tick: int=1` | `dict \| None` | 核心触发函数。检查持仓是否超过阈值，若触发则返回强制平仓指令                                         |
| `calculate_sell_close_price` | `bid1: float`, `price_tick: float`, `hedge_price_tick: int=1`                                                                   | `float`        | 多头超限时，计算卖出平仓价格                                                         |
| `calculate_buy_close_price`  | `ask1: float`, `price_tick: float`, `hedge_price_tick: int=1`                                                                   | `float`        | 空头超限时，计算买入平仓价格                                                         |
| `update_last_hedge`          | `hedge_order: dict`                                                                                                             | `None`         | 更新最近一次强制平仓动作、价格和数量                                                     |
| `clear_last_hedge`           | 无                                                                                                                               | `None`         | 清空强制平仓状态缓存                                                             |
| `get_last_hedge_action`      | 无                                                                                                                               | `str`          | 获取最近一次强制平仓方向                                                           |
| `get_last_hedge_price`       | 无                                                                                                                               | `float`        | 获取最近一次强制平仓价格                                                           |
| `get_last_hedge_volume`      | 无                                                                                                                               | `float`        | 获取最近一次强制平仓数量                                                           |

---

## 📦 输入参数说明

`check_hedge()` 是本模块最核心的方法，主要输入如下：

| 参数                 | 类型      | 说明                          |
| :----------------- | :------ | :-------------------------- |
| `pos`              | `float` | 当前净持仓，正数表示多头，负数表示空头         |
| `hedge_threshold`  | `float` | 强制平仓触发阈值                    |
| `hedge_volume`     | `float` | 每次强制平仓的最大数量                 |
| `price_tick`       | `float` | 合约最小变动价位                    |
| `snapshot`         | `dict`  | 当前行情快照，主要使用 `bid1` 和 `ask1` |
| `hedge_price_tick` | `int`   | 强制平仓价格相对盘口偏移的 tick 数        |

函数会先做参数和盘口检查。如果以下条件不满足，则直接返回 `None`：

```text
hedge_threshold > 0
hedge_volume > 0
price_tick > 0
bid1 > 0
ask1 > 0
ask1 > bid1
```

这样可以避免在参数错误或盘口异常时误触发强制平仓。

---

## 💡 核心触发逻辑

### 1. 多头超限：生成 `SELL_CLOSE`

如果当前持仓满足：

```text
pos >= hedge_threshold
```

说明策略当前多头仓位过大，需要卖出平仓。

此时 `check_hedge()` 会生成：

```text
SELL_CLOSE
```

也就是卖出平多指令。

对应返回结构：

```python
{
    "action": "SELL_CLOSE",
    "price": price,
    "volume": volume,
    "reason": "long_position_exceed_threshold",
}
```

---

### 2. 空头超限：生成 `BUY_CLOSE`

如果当前持仓满足：

```text
pos <= -hedge_threshold
```

说明策略当前空头仓位过大，需要买入平仓。

此时 `check_hedge()` 会生成：

```text
BUY_CLOSE
```

也就是买入平空指令。

对应返回结构：

```python
{
    "action": "BUY_CLOSE",
    "price": price,
    "volume": volume,
    "reason": "short_position_exceed_threshold",
}
```

---

## 📉 平多价格计算：`calculate_sell_close_price()`

当多头超限时，策略需要卖出平仓。
平多价格由 `calculate_sell_close_price()` 计算：

```text
price = bid1 - hedge_price_tick * price_tick
```

其中：

| 参数                 | 含义               |
| :----------------- | :--------------- |
| `bid1`             | 当前买一价            |
| `hedge_price_tick` | 相对买一价向下偏移几个 tick |
| `price_tick`       | 合约最小变动价位         |

例如：

```text
bid1 = 3700
price_tick = 1
hedge_price_tick = 1

price = 3700 - 1 * 1 = 3699
```

这样做的目的是让平多单价格略低于买一价，提高成交概率，从而尽快降低多头仓位。

如果计算出来的价格小于等于 0，代码会返回 `bid1`，防止出现非法价格。

---

## 📈 平空价格计算：`calculate_buy_close_price()`

当空头超限时，策略需要买入平仓。
平空价格由 `calculate_buy_close_price()` 计算：

```text
price = ask1 + hedge_price_tick * price_tick
```

其中：

| 参数                 | 含义               |
| :----------------- | :--------------- |
| `ask1`             | 当前卖一价            |
| `hedge_price_tick` | 相对卖一价向上偏移几个 tick |
| `price_tick`       | 合约最小变动价位         |

例如：

```text
ask1 = 3702
price_tick = 1
hedge_price_tick = 1

price = 3702 + 1 * 1 = 3703
```

这样做的目的是让平空单价格略高于卖一价，提高成交概率，从而尽快降低空头仓位。

---

## 📦 强制平仓数量控制

强制平仓数量不是直接等于当前全部持仓，而是：

```text
volume = min(abs(pos), hedge_volume)
```

含义是：

| 情况                         | 说明                    |
| :------------------------- | :-------------------- |
| `abs(pos) > hedge_volume`  | 本次最多只平 `hedge_volume` |
| `abs(pos) <= hedge_volume` | 本次最多平掉当前实际持仓          |

例如：

```text
pos = 5
hedge_volume = 2

volume = min(5, 2) = 2
```

表示当前虽然有 5 手持仓，但本次只平 2 手。

再比如：

```text
pos = 1
hedge_volume = 2

volume = min(1, 2) = 1
```

表示当前只有 1 手持仓，因此本次最多只能平 1 手。

---

## 📦 强制平仓指令字典结构

`check_hedge()` 触发时返回的是一个字典，而不是直接发单。

结构如下：

| 字段名      | 类型      | 说明                                                                               |
| :------- | :------ | :------------------------------------------------------------------------------- |
| `action` | `str`   | `"SELL_CLOSE"` 表示卖出平多；`"BUY_CLOSE"` 表示买入平空                                       |
| `price`  | `float` | 强制平仓价格                                                                           |
| `volume` | `float` | 实际平仓数量，等于 `min(abs(pos), hedge_volume)`                                          |
| `reason` | `str`   | 触发原因，例如 `"long_position_exceed_threshold"` 或 `"short_position_exceed_threshold"` |

这个字典只是内部信号。真正下单是在主策略里完成：

```text
SELL_CLOSE → 主策略调用 sell()
BUY_CLOSE  → 主策略调用 cover()
```

---

## 🗂️ 状态缓存

`HedgeEngine` 内部记录最近一次强制平仓信息：

```text
last_hedge_action
last_hedge_price
last_hedge_volume
```

| 变量                  | 含义         |
| :------------------ | :--------- |
| `last_hedge_action` | 最近一次强制平仓方向 |
| `last_hedge_price`  | 最近一次强制平仓价格 |
| `last_hedge_volume` | 最近一次强制平仓数量 |

对应方法：

| 方法                        | 作用                |
| :------------------------ | :---------------- |
| `update_last_hedge()`     | 在生成强制平仓指令后，更新状态缓存 |
| `clear_last_hedge()`      | 清空强制平仓状态缓存        |
| `get_last_hedge_action()` | 获取最近一次强制平仓方向      |
| `get_last_hedge_price()`  | 获取最近一次强制平仓价格      |
| `get_last_hedge_volume()` | 获取最近一次强制平仓数量      |

这些状态主要用于 UI 展示、日志监控和调试。

---

## ⚙️ 参数调节含义

| 参数                 | 作用                | 调大/调小影响                        |
| :----------------- | :---------------- | :----------------------------- |
| `hedge_threshold`  | 强制平仓触发阈值          | 调大：更晚触发强制平仓；调小：更早触发强制平仓        |
| `hedge_volume`     | 每次强制平仓最大数量        | 调大：平仓更快，但冲击更大；调小：平仓更温和，但恢复仓位更慢 |
| `hedge_price_tick` | 平仓价格相对盘口偏移 tick 数 | 调大：更容易成交，但滑点更大；调小：更保守，但可能不容易成交 |
| `price_tick`       | 合约最小变动价位          | 决定每个 hedge tick 对应的真实价格距离      |

### 参数联动建议

一般情况下：

```text
hedge_threshold < max_position
```

这样可以在仓位达到最大持仓限制之前，提前触发强制平仓。

例如：

```text
max_position = 4
hedge_threshold = 3
```

表示最大允许持仓为 4 手，但当持仓达到 3 手时，就开始强制平仓，避免仓位继续逼近上限。

---

## ✅ 小结

`HedgeEngine` 是策略中的硬风控模块。

它主要回答一个问题：

```text
当前持仓是否已经超过强制平仓阈值？如果超过，应该以什么方向、什么价格、多少数量进行平仓？
```

它和 `InventorySkewEngine` 构成双层库存控制：

| 模块                    | 控制方式   | 是否直接平仓 | 作用                 |
| :-------------------- | :----- | :----- | :----------------- |
| `InventorySkewEngine` | 调整报价   | 否      | 日常库存管理，通过报价实现软对冲   |
| `HedgeEngine`         | 生成平仓指令 | 是      | 极端情况下的硬风控，主动降低风险暴露 |

因此，当软库存偏移无法及时控制仓位时，`HedgeEngine` 会作为最后一层保护，触发强制平仓逻辑。


