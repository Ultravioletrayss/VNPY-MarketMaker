
# 📊 `MarketDataManager`（行情数据管理模块）

**架构定位**：行情数据预处理模块。负责接收 vn.py 推送的 `TickData`，提取最新成交价、买卖一档、五档盘口价格、五档盘口挂单量、盘口价差和有效深度，并统一整理成 `snapshot` 字典，供后续 `PricingEngine`、`QuoteRiskFilter`、`InventorySkewEngine` 和 `HedgeEngine` 使用。

简单来说，`MarketDataManager` 是整个策略的数据入口：

```text
TickData 原始行情
    ↓
MarketDataManager 清洗和整理
    ↓
snapshot 行情快照
    ↓
后续模块统一读取 snapshot
````

---

## 📋 核心方法速查

| 方法名                        | 参数类型             | 返回值                   | 作用说明                                                                                          |
| :------------------------- | :--------------- | :-------------------- | :-------------------------------------------------------------------------------------------- |
| `__init__`                 | 无                | `None`                | 初始化行情缓存，包括 `last_tick`、`last_price`、五档买卖价、五档买卖量、`bid1`、`ask1`、`market_spread`、`valid_depth` 等 |
| `update_tick`              | `tick: TickData` | `dict`                | 核心函数。接收最新 tick，更新内部行情状态，并返回最新 `snapshot`                                                      |
| `_calculate_valid_depth`   | 无                | `int`                 | 计算当前盘口有效深度，买卖价格和挂单量都大于 0 才算有效档位                                                               |
| `get_snapshot`             | 无                | `dict`                | 返回当前行情快照，供其他模块统一调用                                                                            |
| `is_valid`                 | 无                | `bool`                | 检查买一卖一盘口是否合法                                                                                  |
| `has_depth`                | `depth: int=5`   | `bool`                | 判断当前盘口是否至少有指定深度                                                                               |
| `get_depth_volume`         | `depth: int=5`   | `tuple[float, float]` | 计算前 N 档买盘总量和卖盘总量                                                                              |
| `get_order_book_imbalance` | `depth: int=5`   | `float`               | 计算盘口买卖力量不平衡程度                                                                                 |
| `get_mid_price`            | 无                | `float`               | 计算买一卖一中间价                                                                                     |
| `get_micro_price`          | 无                | `float`               | 计算考虑买一卖一挂单量的微价格                                                                               |

---

## 📦 `snapshot` 字典结构

`get_snapshot()` 返回的行情快照大致包含以下字段：

| 字段名             | 类型            | 说明                      |
| :-------------- | :------------ | :---------------------- |
| `datetime`      | `datetime`    | 当前 tick 时间              |
| `last_price`    | `float`       | 最新成交价                   |
| `bid_prices`    | `list[float]` | 买一到买五价格                 |
| `ask_prices`    | `list[float]` | 卖一到卖五价格                 |
| `bid_volumes`   | `list[float]` | 买一到买五挂单量                |
| `ask_volumes`   | `list[float]` | 卖一到卖五挂单量                |
| `bid1`          | `float`       | 买一价                     |
| `ask1`          | `float`       | 卖一价                     |
| `bid1_volume`   | `float`       | 买一挂单量                   |
| `ask1_volume`   | `float`       | 卖一挂单量                   |
| `market_spread` | `float`       | 当前买卖价差，等于 `ask1 - bid1` |
| `valid_depth`   | `int`         | 当前有效盘口深度                |

---

## 💡 核心逻辑说明

### 1. 行情更新逻辑

`update_tick()` 是本模块最核心的方法。每次新的 tick 到来后，它会完成以下工作：

```text
1. 保存最新 tick；
2. 提取 last_price；
3. 提取 bid_price_1 ~ bid_price_5；
4. 提取 ask_price_1 ~ ask_price_5；
5. 提取 bid_volume_1 ~ bid_volume_5；
6. 提取 ask_volume_1 ~ ask_volume_5；
7. 更新 bid1、ask1、bid1_volume、ask1_volume；
8. 计算 market_spread；
9. 计算 valid_depth；
10. 返回 snapshot。
```

---

### 2. 有效深度计算

`_calculate_valid_depth()` 用来计算当前盘口有几档是有效的。

判断标准是：

```text
bid_price_i > 0
ask_price_i > 0
bid_volume_i > 0
ask_volume_i > 0
```

只有同一档的买价、卖价、买量、卖量都有效，才算一档有效深度。

例如：

```text
第 1 档有效
第 2 档有效
第 3 档无效
```

则：

```text
valid_depth = 2
```

---

### 3. 盘口合法性检查

`is_valid()` 主要检查买一卖一是否正常：

```text
bid1 > 0
ask1 > 0
ask1 > bid1
bid1_volume > 0
ask1_volume > 0
```

如果这些条件不满足，说明当前盘口数据异常，不适合继续用于报价。

---

### 4. 盘口不平衡计算

`get_order_book_imbalance()` 用于衡量买卖盘力量差异。

计算公式为：

```text
imbalance = (bid_volume_sum - ask_volume_sum) / (bid_volume_sum + ask_volume_sum)
```

含义是：

```text
imbalance > 0：买盘更厚
imbalance < 0：卖盘更厚
imbalance 越接近 1：买盘优势越明显
imbalance 越接近 -1：卖盘优势越明显
```

---

### 5. mid price 和 micro price

`get_mid_price()` 计算买一卖一中间价：

```text
mid_price = (bid1 + ask1) / 2
```

`get_micro_price()` 计算微价格：

```text
micro_price = (ask1 * bid1_volume + bid1 * ask1_volume) / (bid1_volume + ask1_volume)
```

其中，`micro_price` 会考虑买一卖一挂单量，因此比普通中间价更能反映短期盘口力量。

---

## ✅ 小结

`MarketDataManager` 是策略的行情数据入口模块，主要作用是把 vn.py 原始 `TickData` 转换成结构清晰、字段统一的 `snapshot`。

它主要回答一个问题：

```text
当前盘口状态是什么？
```

后续所有核心模块，包括定价、报价风控、库存偏移和强制平仓，都会基于这个 `snapshot` 进行计算。因此，`MarketDataManager` 的作用是为整个策略提供干净、统一、可复用的行情数据基础。

```
```
