
# 📊 `PricingEngine`（基准价计算模块）

**架构定位**：定价核心模块。负责根据盘口数据计算做市基准价 `fair_price`。后续 `QuoteEngine` 会围绕这个 `fair_price` 生成买卖双边报价。  
本模块不负责下单，也不负责风控，只负责回答一个问题：

```text
当前市场的合理基准价是多少？
````

需要注意的是，本策略的基准价主要不是直接使用 `last_price`，而是基于盘口数据计算，例如 `bid1`、`ask1`、买卖一档挂单量，以及五档盘口价格和挂单量。

---

## 📋 核心方法速查

| 方法名                                | 参数类型                                                                                                                           | 返回值     | 作用说明                                                                                                             |
| :--------------------------------- | :----------------------------------------------------------------------------------------------------------------------------- | :------ | :--------------------------------------------------------------------------------------------------------------- |
| `__init__`                         | 无                                                                                                                              | `None`  | 初始化定价状态，包括 `mid_price`、`micro_price`、`depth_weighted_mid`、`exp_weighted_depth_mid`、`ema_fair_price`、`fair_price` |
| `reset`                            | 无                                                                                                                              | `None`  | 重置定价状态，主要用于清空 EMA 历史价格，避免上一次运行影响本次结果                                                                             |
| `calculate_mid_price`              | `snapshot: dict`                                                                                                               | `float` | 计算买一卖一中间价                                                                                                        |
| `calculate_micro_price`            | `snapshot: dict`                                                                                                               | `float` | 计算考虑买一卖一挂单量的微价格                                                                                                  |
| `calculate_depth_weighted_mid`     | `snapshot: dict`, `depth: int=5`                                                                                               | `float` | 计算多档盘口加权中间价                                                                                                      |
| `calculate_exp_weighted_depth_mid` | `snapshot: dict`, `depth: int=5`, `decay: float=0.6`                                                                           | `float` | 计算指数加权五档盘口中间价                                                                                                    |
| `apply_ema_smoothing`              | `new_price: float`, `ema_alpha: float=0.2`                                                                                     | `float` | 对基准价进行 EMA 平滑，减少短期跳动                                                                                             |
| `calculate_fair_price`             | `snapshot: dict`, `pricing_method: str`, `depth: int`, `exp_depth_decay: float`, `use_ema_smoothing: bool`, `ema_alpha: float` | `float` | 统一入口，根据参数选择定价方式并返回最终 `fair_price`                                                                                |
| `round_to_tick`                    | `price: float`, `price_tick: float`                                                                                            | `float` | 将价格四舍五入到合法 tick                                                                                                  |

---

## 📦 输入数据：`snapshot`

`PricingEngine` 的输入主要是 `MarketDataManager` 生成的 `snapshot` 行情快照。

常用字段包括：

| 字段名           | 类型            | 说明       |
| :------------ | :------------ | :------- |
| `bid1`        | `float`       | 当前买一价    |
| `ask1`        | `float`       | 当前卖一价    |
| `bid1_volume` | `float`       | 当前买一挂单量  |
| `ask1_volume` | `float`       | 当前卖一挂单量  |
| `bid_prices`  | `list[float]` | 买一到买五价格  |
| `ask_prices`  | `list[float]` | 卖一到卖五价格  |
| `bid_volumes` | `list[float]` | 买一到买五挂单量 |
| `ask_volumes` | `list[float]` | 卖一到卖五挂单量 |
| `valid_depth` | `int`         | 当前有效盘口深度 |

---

## 💡 核心定价方式

### 1. `mid`：买一卖一中间价

`mid_price` 是最基础的基准价计算方式。

公式为：

```text
mid_price = (bid1 + ask1) / 2
```

例如：

```text
bid1 = 3698
ask1 = 3702

mid_price = (3698 + 3702) / 2 = 3700
```

特点：

| 优点        | 缺点                       |
| :-------- | :----------------------- |
| 简单、直观、计算快 | 只看价格，不看买卖盘挂单量，无法反映盘口力量差异 |

---

### 2. `micro`：微价格

`micro_price` 在买一卖一价格基础上，加入买一卖一挂单量。

公式为：

```text
micro_price = (ask1 * bid1_volume + bid1 * ask1_volume) / (bid1_volume + ask1_volume)
```

含义是：

```text
买一挂单量越大，说明买方力量越强，价格更可能向 ask1 靠近；
卖一挂单量越大，说明卖方压力越强，价格更可能向 bid1 靠近。
```

例如：

```text
bid1 = 3698
ask1 = 3702
bid1_volume = 100
ask1_volume = 20

micro_price = (3702 * 100 + 3698 * 20) / (100 + 20)
            = 3701.33
```

特点：

| 优点                     | 缺点                    |
| :--------------------- | :-------------------- |
| 能反映买一卖一挂单量强弱，比 mid 更敏感 | 只看第一档盘口，容易受买一卖一短期变化影响 |

---

### 3. `depth_weighted`：多档盘口加权中间价

`depth_weighted` 使用多档盘口价格和挂单量计算基准价。

计算逻辑为：

```text
买盘加权平均价 = sum(bid_price_i * bid_volume_i) / sum(bid_volume_i)

卖盘加权平均价 = sum(ask_price_i * ask_volume_i) / sum(ask_volume_i)

depth_weighted_mid = (买盘加权平均价 + 卖盘加权平均价) / 2
```

特点：

| 优点                         | 缺点                   |
| :------------------------- | :------------------- |
| 使用更多盘口信息，比 mid 和 micro 更稳定 | 如果远端盘口质量差，也可能被虚假挂单干扰 |

适合场景：

```text
适合有五档盘口数据、希望基准价更加平滑稳定的商品期货做市策略。
```

---

### 4. `exp_depth_weighted`：指数加权五档中间价

`exp_depth_weighted` 是在普通五档加权基础上的改进。

它给近端盘口更高权重，给远端盘口更低权重。

权重形式为：

```text
第 1 档权重 = 1
第 2 档权重 = decay
第 3 档权重 = decay^2
第 4 档权重 = decay^3
第 5 档权重 = decay^4
```

例如：

```text
decay = 0.6
```

则权重大致为：

```text
第 1 档：1
第 2 档：0.6
第 3 档：0.36
第 4 档：0.216
第 5 档：0.1296
```

计算逻辑为：

```text
指数加权买盘价 =
sum(bid_price_i * bid_volume_i * weight_i) / sum(bid_volume_i * weight_i)

指数加权卖盘价 =
sum(ask_price_i * ask_volume_i * weight_i) / sum(ask_volume_i * weight_i)

exp_depth_weighted_mid =
(指数加权买盘价 + 指数加权卖盘价) / 2
```

特点：

| 优点               | 缺点                              |
| :--------------- | :------------------------------ |
| 兼顾多档盘口信息和近端盘口敏感性 | `decay` 需要调参，设置不合适可能过度依赖近端或远端盘口 |

---

## 📉 EMA 平滑机制

除了选择不同的基准价计算方式，`PricingEngine` 还支持 EMA 平滑。

EMA 的作用是减少 `fair_price` 的短期跳动。

公式为：

```text
ema_fair_price = ema_alpha * new_price + (1 - ema_alpha) * old_ema_fair_price
```

其中：

| 参数                   | 含义              |
| :------------------- | :-------------- |
| `new_price`          | 当前最新计算出来的基准价    |
| `old_ema_fair_price` | 上一次 EMA 平滑后的基准价 |
| `ema_alpha`          | 平滑系数            |
| `ema_fair_price`     | 平滑后的基准价         |

调参含义：

| 参数变化                      | 影响                |
| :------------------------ | :---------------- |
| `ema_alpha` 调大            | 更跟随最新行情，反应更快      |
| `ema_alpha` 调小            | 更平滑，但反应更慢         |
| `use_ema_smoothing=True`  | 减少基准价抖动，降低频繁撤单    |
| `use_ema_smoothing=False` | 基准价更敏感，但可能更容易频繁变化 |

---

## 🧭 `calculate_fair_price()` 统一入口

`calculate_fair_price()` 是整个模块最重要的统一入口。

执行流程是：

```text
读取 snapshot
    ↓
根据 pricing_method 选择定价方式
    ↓
计算 raw_price
    ↓
如果 use_ema_smoothing=True，进行 EMA 平滑
    ↓
返回最终 fair_price
```

支持的 `pricing_method` 包括：

| 参数值                    | 对应方法                                 |
| :--------------------- | :----------------------------------- |
| `"mid"`                | `calculate_mid_price()`              |
| `"micro"`              | `calculate_micro_price()`            |
| `"depth_weighted"`     | `calculate_depth_weighted_mid()`     |
| `"exp_depth_weighted"` | `calculate_exp_weighted_depth_mid()` |

---

## ⚙️ 参数调节含义

| 参数                  | 作用          | 调大/调小影响                                                                 |
| :------------------ | :---------- | :---------------------------------------------------------------------- |
| `pricing_method`    | 选择定价方式      | `mid` 最简单，`micro` 更敏感，`depth_weighted` 更稳定，`exp_depth_weighted` 更重视近端盘口 |
| `pricing_depth`     | 使用几档盘口      | 调大更稳定，调小更敏感                                                             |
| `exp_depth_decay`   | 指数加权衰减系数    | 调大更重视远端盘口，调小更重视近端盘口                                                     |
| `use_ema_smoothing` | 是否开启 EMA 平滑 | 开启更稳定，关闭更敏感                                                             |
| `ema_alpha`         | EMA 平滑系数    | 调大更跟随行情，调小更平滑但滞后                                                        |

---

## ✅ 小结

`PricingEngine` 是策略的定价核心模块。

它主要回答一个问题：

```text
当前做市报价应该围绕哪个价格展开？
```

不同定价方式的特点可以总结为：

```text
mid：简单直接
micro：反映一档买卖力量
depth_weighted：利用多档盘口，更稳定
exp_depth_weighted：更重视近端盘口
EMA：减少基准价短期跳动
```

后续 `QuoteEngine` 会基于 `fair_price` 生成买卖报价，因此 `PricingEngine` 的稳定性和合理性会直接影响整个做市策略的报价质量。

```
```
