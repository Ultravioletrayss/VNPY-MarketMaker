可以，你这个策略的链路图可以画成 **“行情驱动主链路 + 订单回报链路 + 成交对冲链路 + summary 统计链路”** 四条线。

---

## 1. 整体主流程链路图

```mermaid
flowchart TD
    A[TickData 到来] --> B[MarketDataManager<br/>生成原始五档盘口 snapshot]

    B --> C[PriceWindowManager<br/>更新 last_price 窗口]
    C --> D{窗口是否 ready?}

    D -- 否 --> D1[不报价<br/>等待窗口数据充足]
    D1 --> Z[put_event_throttled]

    D -- 是 --> E[OrderBookProcessor<br/>扣除本方做市订单]
    E --> F[得到非本方盘口 other_book]

    F --> G[计算市场状态<br/>market_spread / book_volume / window_diff]

    G --> H[ScenarioSelector<br/>选择 1-8 档场景]

    H --> I[获取场景报价参数<br/>quote_level / price_offset_tick / quote_volume]

    I --> J[QuoteGenerator<br/>生成目标买卖报价]

    J --> K[RiskManager<br/>报价前风控过滤]

    K --> L{报价是否通过风控?}

    L -- 否 --> M[buy_quote=None / sell_quote=None<br/>视为不允许报价]
    L -- 是 --> N[保留过滤后的目标报价]

    M --> O[OrderManager<br/>生成撤单计划]
    N --> O[OrderManager<br/>生成撤单/补单/重报计划]

    O --> P[SgeMarketMakingStrategy<br/>执行真实撤单/发单]

    P --> Q[更新本方最优报价<br/>own_best_bid / own_best_ask]

    Q --> R[ReportManager<br/>记录报价 summary]

    R --> Z[put_event_throttled]
```

这条主链路就是：**Tick 来了 → 看盘口 → 判断场景 → 生成报价 → 风控 → 同步订单 → 记录 summary**。你的主策略就是这个事件驱动流程的编排者。

---

## 2. 单边行情 / 本方订单撑盘口的处理链路

```mermaid
flowchart TD
    A[原始盘口 snapshot] --> B[OrderBookProcessor<br/>扣除本方做市挂单]

    B --> C[得到 other_book]

    C --> D[RiskManager.check_other_book_valid]

    D --> E{非本方盘口是否双边有效?}

    E -- 是 --> F[继续生成/保留报价]

    E -- 否 --> G[RiskManager 返回<br/>buy_quote=None<br/>sell_quote=None]

    G --> H[OrderManager 发现目标报价为空]

    H --> I[撤回普通做市订单]

    I --> J[对冲订单不在 mm_orderids 中<br/>不撤对冲单]

    J --> K[等待后续 Tick 行情恢复后重新报价]
```

这就对应你说的要求：

> 单边行情时撤回做市订单，待行情恢复后重报；对冲订单不撤。
> 如果单边全是本方订单，扣除本方订单后也会被当成单边行情处理。

---

## 3. 订单同步链路

```mermaid
flowchart TD
    A[目标报价 buy_quote / sell_quote] --> B[OrderManager.build_sync_plan]

    B --> C{当前是否有做市订单?}

    C -- 没有 --> D[直接发送目标买卖单]

    C -- 有 --> E{目标报价是否为空?}

    E -- 是 --> F[撤掉对应方向做市订单]

    E -- 否 --> G{目标价与当前挂单价差<br/>是否超过 quote_tolerance?}

    G -- 是 --> H[撤旧单 + 重报新单]

    G -- 否 --> I{剩余数量是否不足?}

    I -- 是 --> J[补挂被动成交部分]

    I -- 否 --> K[不撤不报<br/>保持原订单]
```

这条链路对应你的规则：

> 挂单换挡或价格变化较大时撤单重报；
> 挂单档位没变、价格在容忍度范围内时不撤；
> 如果被动成交导致数量不足，则补挂差额。

---

## 4. 成交后逐笔对冲链路

```mermaid
flowchart TD
    A[on_trade 收到成交回报] --> B[OrderManager.get_order_type<br/>识别订单类型]

    B --> C{是否普通做市单 MM?}

    C -- 否 --> D[不触发逐笔对冲]

    C -- 是 --> E{hedge_enabled 是否开启?}

    E -- 否 --> D

    E -- 是 --> F[HedgeManager<br/>根据成交方向生成对冲单]

    F --> G{做市买单成交?}

    G -- 是 --> H[生成卖出对冲单<br/>price = bid1 - hedge_offset_tick * price_tick]

    G -- 否 --> I[生成买入对冲单<br/>price = ask1 + hedge_offset_tick * price_tick]

    H --> J[SgeMarketMakingStrategy<br/>调用 short 发对冲单]
    I --> K[SgeMarketMakingStrategy<br/>调用 buy 发对冲单]

    J --> L[注册订单类型为 HEDGE]
    K --> L

    L --> M[更新最近一次对冲信息]
```

这说明你的对冲逻辑是：

> 普通做市单成交一笔，就生成一笔反方向对冲单；
> 做市买成交后卖出对冲，做市卖成交后买入对冲。

---

## 5. ReportManager 统计链路

```mermaid
flowchart TD
    A[每个 Tick 处理结束] --> B[OrderManager.get_own_best_quote]

    B --> C[获得本方最优买价/卖价<br/>本方买量/卖量]

    C --> D[ReportManager.record_quote]

    D --> E{是否双边有效报价?}

    E -- 否 --> F[不计入报价差和深度<br/>但更新有效报价时长状态]

    E -- 是 --> G[累计报价差<br/>ask - bid]

    G --> H[累计有效深度<br/>min_bid_volume, ask_volume]

    H --> I[累计有效报价时长]

    J[普通做市成交] --> K[ReportManager.record_trade]
    K --> L[累计 total_trade_volume]

    I --> M[on_stop]
    L --> M

    M --> N[write_summary_csv<br/>输出 4 个 summary 指标]
```

最终输出 4 个值：

```text
1. best_avg_quote_spread
2. avg_effective_quote_depth
3. avg_effective_quote_hours
4. total_trade_volume
```

---

## 6. 一句话版流程

> 策略每收到一个 Tick，就先把原始行情转成五档盘口 snapshot，再扣除本方挂单得到非本方盘口；然后根据非本方价差、盘口量和窗口价格偏离选择 1-8 档场景，并生成对应的双边报价。报价经过 RiskManager 风控后交给 OrderManager 判断是否撤单、补单或重报。普通做市单成交后，HedgeManager 立即生成反方向逐笔对冲单。最后 ReportManager 统计平均报价差、平均有效报价深度、有效报价时长和成交量。
