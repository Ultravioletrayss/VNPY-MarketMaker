
# 🧾 `QuoteEngine`（双边报价生成模块）

**架构定位**：报价生成模块。负责根据 `PricingEngine` 计算出的 `fair_price`，生成买卖双边报价列表。  
本模块不负责行情风控，也不负责实际下单，只负责回答一个问题：

```text
围绕当前 fair_price，应该生成哪些买单报价和卖单报价？
````

`QuoteEngine` 生成的结果会交给主策略，后续再经过库存偏移、仓位过滤和订单发送逻辑。

---

## 📋 核心方法速查

| 方法名                              | 参数类型                                                                                                                                                                                                                                                                             | 返回值                             | 作用说明                                                 |
| :------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------ | :--------------------------------------------------- |
| `__init__`                       | 无                                                                                                                                                                                                                                                                                | `None`                          | 初始化当前报价缓存：`current_buy_quotes`、`current_sell_quotes` |
| `generate_quotes`                | `fair_price: float`, `price_tick: float`, `quote_levels: int`, `order_volume: float`, `quote_mode: str`, `spread_tick: int`, `level_interval_tick: int`, `spread_percent: float`, `level_interval_percent: float`, `split_count: int`, `snapshot: dict \| None`, `passive: bool` | `tuple[list[dict], list[dict]]` | 核心报价函数，生成买卖双边报价列表                                    |
| `_calculate_tick_quote_price`    | `fair_price: float`, `price_tick: float`, `level: int`, `spread_tick: int`, `level_interval_tick: int`                                                                                                                                                                           | `tuple[float, float, float]`    | tick 模式下计算某一档买卖报价                                    |
| `_calculate_percent_quote_price` | `fair_price: float`, `price_tick: float`, `level: int`, `spread_percent: float`, `level_interval_percent: float`                                                                                                                                                                 | `tuple[float, float, float]`    | percent 模式下计算某一档买卖报价                                 |
| `floor_to_tick`                  | `price: float`, `price_tick: float`                                                                                                                                                                                                                                              | `float`                         | 将价格向下取整到合法 tick，主要用于买单                               |
| `ceil_to_tick`                   | `price: float`, `price_tick: float`                                                                                                                                                                                                                                              | `float`                         | 将价格向上取整到合法 tick，主要用于卖单                               |
| `round_to_tick`                  | `price: float`, `price_tick: float`                                                                                                                                                                                                                                              | `float`                         | 将价格四舍五入到合法 tick                                      |
| `need_requote`                   | `new_buy_quotes: list[dict]`, `new_sell_quotes: list[dict]`, `price_tick: float`, `update_tolerance: int`                                                                                                                                                                        | `bool`                          | 比较新旧报价差异，判断是否需要撤单重挂                                  |
| `update_current_quotes`          | `buy_quotes: list[dict]`, `sell_quotes: list[dict]`                                                                                                                                                                                                                              | `None`                          | 更新当前报价缓存                                             |
| `clear_current_quotes`           | 无                                                                                                                                                                                                                                                                                | `None`                          | 清空当前报价缓存                                             |

---

## 📦 输入参数说明

`generate_quotes()` 是本模块最核心的函数，主要参数如下：

| 参数                       | 类型             | 说明                             |
| :----------------------- | :------------- | :----------------------------- |
| `fair_price`             | `float`        | 做市基准价，买卖报价围绕它展开                |
| `price_tick`             | `float`        | 合约最小变动价位                       |
| `quote_levels`           | `int`          | 报价档数，例如 3 表示买卖各生成 3 档          |
| `order_volume`           | `float`        | 每一笔报价的手数                       |
| `quote_mode`             | `str`          | 报价模式，支持 `"tick"` 和 `"percent"` |
| `spread_tick`            | `int`          | tick 模式下，第一档距离基准价几个 tick       |
| `level_interval_tick`    | `int`          | tick 模式下，每增加一档，多远离基准价几个 tick   |
| `spread_percent`         | `float`        | percent 模式下，第一档距离基准价的百分比       |
| `level_interval_percent` | `float`        | percent 模式下，每增加一档，多远离基准价的百分比   |
| `split_count`            | `int`          | 每一档拆成几笔订单                      |
| `snapshot`               | `dict \| None` | 当前行情快照，主要用于被动报价限制              |
| `passive`                | `bool`         | 是否保持被动报价                       |

如果 `fair_price`、`price_tick`、`quote_levels`、`order_volume` 或 `split_count` 不合法，函数会直接返回空的买卖报价列表。

---

## 💡 核心报价逻辑

### 1. tick 模式报价

如果：

```text
quote_mode = "tick"
```

则策略按照合约最小变动价位计算报价。

核心公式为：

```text
offset_tick = spread_tick + (level - 1) * level_interval_tick

raw_buy_price = fair_price - offset_tick * price_tick
raw_sell_price = fair_price + offset_tick * price_tick
```

其中：

| 参数                    | 含义               |
| :-------------------- | :--------------- |
| `level`               | 当前报价档位           |
| `spread_tick`         | 第一档距离基准价的 tick 数 |
| `level_interval_tick` | 每增加一档的 tick 间隔   |
| `offset_tick`         | 当前档位最终偏移 tick 数  |

例如：

```text
fair_price = 3700
price_tick = 1
spread_tick = 2
level_interval_tick = 1
quote_levels = 3
```

则：

| 档位    | offset_tick | 买单价格 | 卖单价格 |
| :---- | ----------: | ---: | ---: |
| 第 1 档 |           2 | 3698 | 3702 |
| 第 2 档 |           3 | 3697 | 3703 |
| 第 3 档 |           4 | 3696 | 3704 |

tick 模式的优点是直观，特别适合期货品种，因为期货价格本身就是按照最小变动价位跳动的。

---

### 2. percent 模式报价

如果：

```text
quote_mode = "percent"
```

则策略按照百分比偏移计算报价。

核心公式为：

```text
offset_percent = spread_percent + (level - 1) * level_interval_percent

raw_buy_price = fair_price * (1 - offset_percent)
raw_sell_price = fair_price * (1 + offset_percent)
```

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

percent 模式的优点是可以按比例控制报价宽度，适合不同价格水平品种之间的参数统一。
但最终价格仍然需要根据 `price_tick` 调整到合法报价单位。

---

## 🔧 价格 tick 对齐

期货合约下单价格必须符合最小变动价位，因此报价生成后需要进行 tick 对齐。

本模块提供三个价格处理函数：

| 函数                | 作用           | 主要用途   |
| :---------------- | :----------- | :----- |
| `floor_to_tick()` | 向下取整到合法 tick | 买单价格   |
| `ceil_to_tick()`  | 向上取整到合法 tick | 卖单价格   |
| `round_to_tick()` | 四舍五入到合法 tick | 一般价格处理 |

买单使用向下取整：

```text
buy_price = floor(raw_buy_price / price_tick) * price_tick
```

卖单使用向上取整：

```text
sell_price = ceil(raw_sell_price / price_tick) * price_tick
```

这样做的意义是：

```text
买单不会因为取整变得过于激进；
卖单不会因为取整变得过于激进。
```

---

## 🧱 多档报价与拆单

### 1. 多档报价

`quote_levels` 控制报价档数。

例如：

```text
quote_levels = 3
```

表示买卖两边各生成 3 档报价。

代码中会限制最大报价档数：

```text
quote_levels = min(quote_levels, 5)
```

也就是说，即使参数设置超过 5，最多也只生成 5 档报价。

---

### 2. 拆单机制

`split_count` 控制每一档拆成几笔订单。

例如：

```text
quote_levels = 3
split_count = 2
```

则会生成：

```text
买方：3 档 × 2 笔 = 6 笔买单
卖方：3 档 × 2 笔 = 6 笔卖单
```

需要注意的是，当前代码中的拆单是：

```text
同一档内生成多笔相同价格、相同手数的报价。
```

并没有进一步把同一档拆成不同价格。

---

## 📦 报价字典结构

`generate_quotes()` 最终返回：

```text
buy_quotes, sell_quotes
```

其中，每一个报价都是一个字典，结构大致如下：

| 字段名            | 类型      | 说明                                       |
| :------------- | :------ | :--------------------------------------- |
| `side`         | `str`   | 报价方向，`buy` 或 `sell`                      |
| `level`        | `int`   | 当前报价档位                                   |
| `order_index`  | `int`   | 当前档位内第几笔拆单                               |
| `price`        | `float` | 报价价格                                     |
| `volume`       | `float` | 报价手数                                     |
| `quote_mode`   | `str`   | 报价模式，`tick` 或 `percent`                  |
| `offset_value` | `float` | 当前报价偏移量，tick 模式下是 tick 数，percent 模式下是百分比 |

---

## 🧊 被动报价限制

如果：

```text
passive = True
```

并且传入了 `snapshot`，策略会限制报价不能主动吃单。

规则是：

```text
买单价格不能高于 bid1
卖单价格不能低于 ask1
```

对应逻辑为：

```text
buy_price = min(buy_price, bid1)
sell_price = max(sell_price, ask1)
```

这个设计可以让策略更偏向 Maker 挂单，而不是主动 Taker 吃单。

---

## 🔁 是否需要重挂：`need_requote()`

`need_requote()` 用来判断本轮新报价是否有必要替换上一轮旧报价。

这里的“新报价”指的是：

```text
本轮 tick 重新计算出来的最终报价
```

通常已经经过：

```text
基准价计算 → 报价生成 → 库存偏移 → 仓位过滤
```

这里的“旧报价”指的是：

```text
current_buy_quotes
current_sell_quotes
```

也就是上一次成功发出后缓存的报价。

### 判断逻辑

`need_requote()` 会先计算容忍价格差：

```text
tolerance_price = update_tolerance * price_tick
```

然后检查：

```text
1. 买单数量是否变化；
2. 卖单数量是否变化；
3. 买单价格变化是否超过 tolerance_price；
4. 卖单价格变化是否超过 tolerance_price；
5. 买单或卖单手数是否变化。
```

如果任意条件成立，则返回：

```text
True
```

表示需要撤单重挂。

如果变化不明显，则返回：

```text
False
```

表示保留原报价，不进行重挂。

这个函数的意义是减少频繁撤单。盘口每个 tick 都可能小幅变化，但如果变化不大，直接保留旧报价可以减少系统压力，也有利于保留订单排队位置。

---

## 🗂️ 报价缓存管理

`QuoteEngine` 内部维护两个报价缓存：

```text
current_buy_quotes
current_sell_quotes
```

| 方法                        | 作用                    |
| :------------------------ | :-------------------- |
| `update_current_quotes()` | 在主策略成功发出新报价后，更新当前报价缓存 |
| `clear_current_quotes()`  | 在撤单、停止报价或策略重置时，清空报价缓存 |

这两个缓存主要用于后续 `need_requote()` 判断新旧报价差异。

---

## ⚙️ 参数调节含义

| 参数                       | 作用             | 调大/调小影响                         |
| :----------------------- | :------------- | :------------------------------ |
| `quote_mode`             | 报价模式           | `tick` 更直观，`percent` 更适合跨品种比例报价 |
| `quote_levels`           | 报价档数           | 调大：订单更多，覆盖更宽；调小：订单更少，结构更简单      |
| `order_volume`           | 每笔订单手数         | 调大：单笔风险和收益都放大；调小：更保守            |
| `spread_tick`            | tick 模式首档偏移    | 调大：报价更远、更保守；调小：报价更近、更容易成交       |
| `level_interval_tick`    | tick 模式档位间隔    | 调大：多档报价更分散；调小：多档报价更集中           |
| `spread_percent`         | percent 模式首档偏移 | 调大：报价更宽；调小：报价更贴近基准价             |
| `level_interval_percent` | percent 模式档位间隔 | 调大：档位更分散；调小：档位更集中               |
| `split_count`            | 每档拆单数          | 调大：订单数量增加；调小：订单数量减少             |
| `update_tolerance`       | 重挂容忍度          | 调大：减少重挂，更稳定；调小：更频繁跟随最新报价        |
| `passive`                | 是否被动报价         | 开启：更像 Maker；关闭：报价可能更激进          |

---

## ✅ 小结

`QuoteEngine` 是策略中的报价生成核心模块。

它主要完成三件事：

```text
1. 根据 fair_price 生成买卖双边报价；
2. 将报价调整到合法 tick；
3. 判断新报价是否值得替换旧报价。
```

它不直接下单，而是把 `buy_quotes` 和 `sell_quotes` 交给主策略。主策略再结合风控、库存偏移和订单管理逻辑，决定是否真正发送订单。

```
```
