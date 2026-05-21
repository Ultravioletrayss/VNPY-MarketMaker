可以，按我们现在已经写/规划的模块，当前一共有 **8 个模块类**，主策略类另算。
下面先只梳理这 8 个功能类里面的函数。

---

# 一、模块总览

| 类名                   |                            模块作用 | 函数数量 |
| -------------------- | ------------------------------: | ---: |
| `PriceWindowManager` |              维护最近 C 个最新价，计算窗口均价 |  7 个 |
| `OrderBookProcessor` |                  扣除本方订单，生成非本方盘口 |  7 个 |
| `ScenarioSelector`   |               根据 A/B/D 选择 1-8 档 |  4 个 |
| `QuoteGenerator`     |               根据 N/E/F 生成目标买卖报价 |  6 个 |
| `RiskManager`        |                  价格笼子、废单风控、成交风控 |  7 个 |
| `OrderManager`       |                  换挡、撤单、补单、容忍度判断 |  5 个 |
| `HedgeManager`       |                   净买/净卖对冲、撤补、废单 | 12 个 |
| `ReportManager`      | 输出 tick/order/trade/summary CSV |  9 个 |

目前功能类合计：

```text
7 + 7 + 4 + 6 + 7 + 5 + 12 + 9 = 57 个函数
```

---

# 二、`PriceWindowManager`

负责：

```text
最近 C 个最新价
窗口均价
窗口均价 - 最新价
|窗口均价 - 最新价|
```

| 函数名                    | 入参                   | 出参      | 作用                   |
| ---------------------- | -------------------- | ------- | -------------------- |
| `__init__`             | `window_length: int` | `None`  | 初始化窗口长度 C 和价格队列      |
| `reset`                | 无                    | `None`  | 清空价格窗口               |
| `update_window_length` | `window_length: int` | `None`  | 更新窗口长度 C             |
| `update`               | `last_price: float`  | `None`  | 用最新价更新窗口             |
| `is_ready`             | 无                    | `bool`  | 判断是否累计满 C 个价格        |
| `get_average`          | 无                    | `float` | 返回窗口均价，不足 C 个返回 0    |
| `get_diff`             | `last_price: float`  | `float` | 返回窗口均价 - 最新价         |
| `get_abs_diff`         | `last_price: float`  | `float` | 返回 `abs(窗口均价 - 最新价)` |
| `get_count`            | 无                    | `int`   | 返回当前窗口内已有价格数量        |

这个类后面可以加一个：

```python
update_tick(tick: TickData)
```

直接从 `TickData.last_price` 更新窗口，更符合 vn.py 风格。

---

# 三、`OrderBookProcessor`

负责：

```text
读取 TickData 五档盘口
扣除本方订单
生成非本方盘口
判断单边行情
计算非本方价差和盘口量
```

| 函数名                         | 入参                                                                                        | 出参                                | 作用                       |
| --------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------- | ------------------------ |
| `remove_own_orders`         | `tick: TickData`, `active_orders: dict[str, OrderData]`, `own_orderids: set[str] \| None` | `dict`                            | 从五档盘口里扣除本方订单，返回非本方盘口     |
| `_subtract_volume_at_price` | `prices: list[float]`, `volumes: list[float]`, `price: float`, `volume: float`            | `None`                            | 在指定价格档扣除本方挂单量            |
| `_compact_book_side`        | `prices: list[float]`, `volumes: list[float]`                                             | `tuple[list[float], list[float]]` | 删除数量为 0 的档位，并向前补位        |
| `_calculate_valid_depth`    | `bid_prices`, `bid_volumes`, `ask_prices`, `ask_volumes`                                  | `int`                             | 计算扣除本方订单后的有效盘口深度         |
| `is_one_sided`              | `other_book: dict`                                                                        | `bool`                            | 判断非本方盘口是否单边              |
| `get_spread`                | `other_book: dict`                                                                        | `float`                           | 返回非本方买卖一档价差              |
| `get_book_volume`           | `other_book: dict`                                                                        | `int`                             | 返回非本方盘口量：`MIN(买一量, 卖一量)` |

这个类对应两个特殊要求：

```text
4. 只有单边行情，需要撤回做市订单，对冲订单不撤
5. 如果单边全是本方订单，按照单边行情处理
```

---

# 四、`ScenarioSelector`

负责：

```text
根据 A/B/D 三个条件选择 1-8 档
再根据档位拿到 N/E/F
```

| 函数名                      | 入参                                                                                      | 出参                     | 作用                  |
| ------------------------ | --------------------------------------------------------------------------------------- | ---------------------- | ------------------- |
| `__init__`               | `spread_threshold`, `book_volume_threshold`, `window_diff_threshold`, `scenario_config` | `None`                 | 初始化 A/B/D 和 8 档配置   |
| `update_thresholds`      | `spread_threshold`, `book_volume_threshold`, `window_diff_threshold`                    | `None`                 | 更新 A/B/D 参数         |
| `update_scenario_config` | `scenario_config: dict[int, tuple[int, int, int]]`                                      | `None`                 | 更新 8 档 N/E/F 配置     |
| `select`                 | `spread: float`, `book_volume: int`, `abs_window_diff: float`                           | `int`                  | 根据 A/B/D 返回场景编号 1-8 |
| `get_config`             | `scenario_id: int`                                                                      | `tuple[int, int, int]` | 返回当前场景对应的 N/E/F     |
| `get_decision_snapshot`  | `scenario_id`, `spread`, `book_volume`, `abs_window_diff`                               | `dict`                 | 返回决策快照，方便写日志/report |

核心逻辑就是：

```text
spread < A or spread >= A
book_volume >= B or book_volume < B
abs(window_avg - last_price) <= D or > D
```

然后选择：

```text
1 → N1/E1/F1
2 → N2/E2/F2
...
8 → N8/E8/F8
```

---

# 五、`QuoteGenerator`

负责：

```text
根据 N/E/F 生成目标买单和目标卖单
```

| 函数名                       | 入参                                                       | 出参                                  | 作用            |
| ------------------------- | -------------------------------------------------------- | ----------------------------------- | ------------- |
| `__init__`                | 无                                                        | `None`                              | 初始化最近一次目标报价记录 |
| `generate_quotes`         | `scenario_id`, `N`, `E`, `F`, `other_book`, `price_tick` | `tuple[dict \| None, dict \| None]` | 生成目标买报价和卖报价   |
| `update_last_quotes`      | `scenario_id`, `N`, `E`, `F`, `buy_quote`, `sell_quote`  | `None`                              | 记录最近一次目标报价    |
| `clear_last_quotes`       | 无                                                        | `None`                              | 清空最近目标报价      |
| `floor_to_tick`           | `price: float`, `price_tick: float`                      | `float`                             | 买单价格向下对齐 tick |
| `ceil_to_tick`            | `price: float`, `price_tick: float`                      | `float`                             | 卖单价格向上对齐 tick |
| `round_to_tick`           | `price: float`, `price_tick: float`                      | `float`                             | 价格就近对齐 tick   |
| `get_last_quote_snapshot` | 无                                                        | `dict`                              | 返回最近一次目标报价快照  |

核心公式：

```text
买单价格 = 非本方买 N 档价格 - price_tick × E
卖单价格 = 非本方卖 N 档价格 + price_tick × E

买单数量 = F
卖单数量 = F
```

---

# 六、`RiskManager`

负责三类风控：

```text
价格笼子
废单风控
成交风控
```

| 函数名                          | 入参                                                                               | 出参                                        | 作用                                 |
| ---------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------- | ---------------------------------- |
| `get_base_price_by_type`     | `tick: TickData`, `price_type: str`                                              | `float`                                   | 根据 `lastPrice/Bid1-5/Ask1-5` 获取基准价 |
| `calculate_price_cage_range` | `base_price`, `lower_offset`, `upper_offset`, `unit`                             | `tuple[float, float]`                     | 计算价格笼子上下限                          |
| `check_price_cage`           | `price`, `tick`, `enabled`, `base_type`, `lower_offset`, `upper_offset`, `unit`  | `tuple[bool, str]`                        | 检查某个委托价格是否在价格笼子内                   |
| `apply_price_cage_to_quotes` | `buy_quote`, `sell_quote`, `tick`, 以及买卖价格笼子参数                                    | `tuple[dict \| None, dict \| None, dict]` | 对买卖报价应用价格笼子                        |
| `check_reject_risk`          | `enabled`, `reject_count`, `max_reject_count`                                    | `tuple[bool, str]`                        | 检查废单次数是否超过上限                       |
| `check_trade_risk`           | 买卖成交风控参数 + 净买净卖统计                                                                | `tuple[bool, str]`                        | 检查净买/净卖成交量、成交额是否超限                 |
| `calculate_net_trade_stats`  | `buy_trade_volume`, `sell_trade_volume`, `buy_trade_amount`, `sell_trade_amount` | `dict`                                    | 计算净买/净卖成交量和成交额                     |

对应特殊要求：

```text
6. 废单次数超过上限，策略停止
7. 成交量、成交额净买上限、净卖上限，超过后策略停止
8. 委托价格不在价格笼子范围内，暂停委托
```

---

# 七、`OrderManager`

负责：

```text
换挡撤单
不换挡补单
价格容忍度内不动
生成订单执行计划
```

| 函数名                    | 入参                                                                                          | 出参                  | 作用                   |
| ---------------------- | ------------------------------------------------------------------------------------------- | ------------------- | -------------------- |
| `__init__`             | 无                                                                                           | `None`              | 初始化当前场景编号            |
| `build_sync_plan`      | `buy_quote`, `sell_quote`, `scenario_id`, `active_orders`, `mm_orderids`, `quote_tolerance` | `dict`              | 根据目标报价和当前订单生成撤单/发单计划 |
| `get_active_mm_orders` | `active_orders`, `mm_orderids`                                                              | `tuple[list, list]` | 获取当前活跃做市买单和卖单        |
| `check_one_side_order` | `target_quote`, `current_orders`, `quote_tolerance`                                         | `dict`              | 判断单边订单是否需要撤、补、重报     |
| `clear`                | 无                                                                                           | `None`              | 清空当前场景状态             |

对应特殊要求 3：

```text
报单被动成交，需要重新触发挂单计算
如挂单换挡，则先撤单后重报
如挂单档位没换，则补挂被动成交部分订单
如果重新挂单价格在容忍度范围内，不进行报撤
```

---

# 八、`HedgeManager`

负责：

```text
净买/净卖触发对冲
生成对冲单
自动开平
对冲撤补
对冲废单风控
```

| 函数名                         | 入参                                                                                        | 出参                 | 作用                               |
| --------------------------- | ----------------------------------------------------------------------------------------- | ------------------ | -------------------------------- |
| `__init__`                  | 无                                                                                         | `None`             | 初始化最近对冲记录、对冲订单时间、撤补次数            |
| `is_trade_in_hedge_scope`   | `trade: TradeData`, `hedge_scope`, `mm_orderids`, `manual_orderids`                       | `bool`             | 判断成交是否纳入对冲范围                     |
| `check_hedge_trigger`       | `net_buy_volume`, `net_sell_volume`, 买入/卖出对冲开关与阈值                                         | `str`              | 判断是否触发 `NET_BUY` 或 `NET_SELL` 对冲 |
| `get_base_price_by_type`    | `tick: TickData`, `price_type: str`                                                       | `float`            | 获取对冲基准价                          |
| `calculate_hedge_price`     | `base_price`, `price_offset`, `price_offset_unit`                                         | `float`            | 计算对冲价格                           |
| `resolve_offset`            | `direction`, `offset_mode`, `pos`                                                         | `str`              | 自动判断开仓/平仓                        |
| `generate_hedge_order`      | `hedge_type`, `tick`, `pos`, 标的/组合/方向/价格参数等                                               | `dict \| None`     | 生成对冲订单计划                         |
| `register_hedge_order`      | `vt_orderid`, `order_time`                                                                | `None`             | 记录对冲订单发单时间                       |
| `check_timeout_and_replace` | `active_orders`, `hedge_orderids`, `now`, `hedge_wait_seconds`, `hedge_max_replace_count` | `dict`             | 检查对冲单是否超时，需要撤补或停止策略              |
| `clear_finished_order`      | `vt_orderid`                                                                              | `None`             | 清理已经结束的对冲订单记录                    |
| `check_reject_risk`         | `reject_enabled`, `reject_count`, `max_reject_count`                                      | `tuple[bool, str]` | 检查对冲废单次数是否超限                     |
| `update_last_hedge`         | `hedge_order: dict`                                                                       | `None`             | 更新最近一次对冲记录                       |
| `clear_last_hedge`          | 无                                                                                         | `None`             | 清空最近一次对冲记录                       |
| `get_last_hedge_snapshot`   | 无                                                                                         | `dict`             | 返回最近一次对冲记录                       |

对应对冲 10 条要求：

```text
1. 净买/净卖默认为 0，发生净敞口即可触发
2. 对冲标的默认等于报价标的
3. 对冲组合默认等于报价组合
4. 净买入默认卖单，净卖出默认买单
5. 支持开、平、自动开平
6. 支持 lastPrice / Bid1-5 / Ask1-5
7. 对冲价格 = 基准价 + 偏移量
8. 对冲废单超限停止
9. 对冲超时未全成则撤补，撤补超限停止
10. 支持自动 / 自动+手动对冲范围
```

---

# 九、`ReportManager`

负责：

```text
输出 CSV
统计核心做市指标
```

| 函数名                                | 入参                                                                                                      | 出参     | 作用                      |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------- | ------ | ----------------------- |
| `__init__`                         | `report_dir`, `strategy_name`                                                                           | `None` | 初始化 CSV 报告路径和统计变量       |
| `record_tick_decision`             | `tick: TickData` + 行情、场景、报价、本方订单指标                                                                      | `None` | 记录每个 tick 的策略决策，并更新报价指标 |
| `_update_effective_quote_duration` | `current_datetime`, `current_effective_quote_active`                                                    | `None` | 累计有效报价时长                |
| `record_order`                     | `order: OrderData`, `order_type`, `scenario_id`, `reason`                                               | `None` | 记录订单状态                  |
| `record_trade`                     | `trade: TradeData`, `order_type`, `contract_size`, `trigger_hedge`, `net_buy_volume`, `net_sell_volume` | `None` | 记录成交，并累计成交量/成交额         |
| `get_summary`                      | 无                                                                                                       | `dict` | 生成汇总指标                  |
| `write_all_reports`                | 无                                                                                                       | `None` | 输出所有 CSV                |
| `_write_csv`                       | `filename`, `rows`                                                                                      | `None` | 写单个 CSV 文件              |
| `set_stop_reason`                  | `reason: str`                                                                                           | `None` | 记录策略停止原因                |
| `reset`                            | 无                                                                                                       | `None` | 重置报告缓存和统计变量             |

重点输出 4 个核心指标：

| 指标       | 计算方式                                                                  |
| -------- | --------------------------------------------------------------------- |
| 最优平均报价差  | `sum(本方最优卖价 - 本方最优买价) / 有效双边报价样本数`                                    |
| 平均有效报价深度 | `sum(min(本方买一量, 本方卖一量)) / 有效双边报价样本数`                                  |
| 平均有效报价时长 | `有效双边报价累计秒数 / 3600`                                                   |
| 成交量      | `mm_trade_volume`，也可以同时输出 `total_trade_volume` 和 `hedge_trade_volume` |

---

# 十、主策略类 `SgeMarketMakingStrategy`

这个是总控类，继承 `CtaTemplate`。

| 函数名                           | 入参                                                    | 出参         | 作用                                 |
| ----------------------------- | ----------------------------------------------------- | ---------- | ---------------------------------- |
| `__init__`                    | `cta_engine`, `strategy_name`, `vt_symbol`, `setting` | `None`     | 初始化所有模块、订单集合、状态变量                  |
| `on_init`                     | 无                                                     | `None`     | 策略初始化                              |
| `on_start`                    | 无                                                     | `None`     | 策略启动，获取 `price_tick/contract_size` |
| `on_stop`                     | 无                                                     | `None`     | 策略停止，撤单，输出 report                  |
| `on_tick`                     | `tick: TickData`                                      | `None`     | 行情驱动主逻辑                            |
| `on_order`                    | `order: OrderData`                                    | `None`     | 订单状态更新，维护订单集合，统计废单                 |
| `on_trade`                    | `trade: TradeData`                                    | `None`     | 成交处理，成交风控，触发对冲，触发重算                |
| `on_timer`                    | 无                                                     | `None`     | 对冲撤补、定时检查                          |
| `on_stop_order`               | `stop_order: StopOrder`                               | `None`     | 停止单回报，暂时可以留空                       |
| `activate_mm`                 | 无                                                     | `None`     | 手动激活做市                             |
| `deactivate_mm`               | 无                                                     | `None`     | 取消激活做市，撤做市单但继续累计窗口                 |
| `cancel_market_making_orders` | 无                                                     | `None`     | 只撤做市单，不撤对冲单                        |
| `cancel_hedge_orders`         | 无                                                     | `None`     | 只撤对冲单                              |
| `stop_strategy`               | `reason: str`                                         | `None`     | 风控触发后停止策略                          |
| `update_order_count`          | 无                                                     | `None`     | 更新当前订单数量变量                         |
| `get_own_best_quote`          | 无                                                     | `dict`     | 获取本方最优买卖报价，用于 report               |
| `send_mm_order_by_quote`      | `quote: dict`                                         | `set[str]` | 根据 quote 发做市单                      |
| `send_hedge_order_by_plan`    | `hedge_order: dict`                                   | `set[str]` | 根据 hedge_order 计划发对冲单              |

主策略主要把前面 8 个模块串起来：

```text
on_tick:
    TickData
    → PriceWindowManager
    → OrderBookProcessor
    → ScenarioSelector
    → QuoteGenerator
    → RiskManager
    → OrderManager
    → 发单/撤单
    → ReportManager

on_trade:
    TradeData
    → 统计成交
    → RiskManager 检查成交风控
    → HedgeManager 检查对冲
    → ReportManager 记录成交

on_order:
    OrderData
    → 更新订单集合
    → RiskManager / HedgeManager 检查废单
    → ReportManager 记录订单

on_timer:
    HedgeManager 检查对冲撤补
```

---

# 最后总结

现在整个策略模块可以理解成：

```text
1. PriceWindowManager      价格窗口
2. OrderBookProcessor      非本方盘口
3. ScenarioSelector        8档选择
4. QuoteGenerator          目标报价
5. RiskManager             风控
6. OrderManager            撤补重报
7. HedgeManager            对冲
8. ReportManager           CSV输出
9. SgeMarketMakingStrategy 主策略调度
```

功能类一共大约 **57 个函数**，主策略类大约 **15 个函数**。
但真正第一阶段要先跑通的只有：

```text
PriceWindowManager
OrderBookProcessor
ScenarioSelector
QuoteGenerator
RiskManager 中的价格笼子
OrderManager 的 build_sync_plan
SgeMarketMakingStrategy.on_tick
```
