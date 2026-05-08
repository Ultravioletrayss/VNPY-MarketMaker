以下是为您整理的 **`QuoteEngine` 报价生成与状态管理引擎 API 规范文档**。该类是典型做市/网格策略的 `报价调度中枢`，负责将基准价转化为合规的多层买卖报价，并提供防抖重报、被动保护与本地状态快照功能。

---
## 🏭 `QuoteEngine` (报价生成与状态管理引擎)
**架构定位**：无状态报价计算 + 轻量级状态缓存组件。负责基于 `Fair Price` 与合约规格，按跳数(`tick`)或百分比(`percent`)模式生成多层级报价。内置被动单保护、订单拆分、价格对齐、防抖重报校验（Re-quote Tolerance）及本地状态管理，适用于高频低延迟做市与网格交易场景。

### 📋 核心方法速查
| 方法名 | 参数类型 | 返回值 | 作用说明 |
|:---|:---|:---|:---|
| `__init__` | *(无)* | `None` | 初始化本地状态：`current_buy_quotes`, `current_sell_quotes` 为空列表 |
| `generate_quotes` | `fair_price: float`, `price_tick: float`, `quote_levels: int`, `order_volume: float`<br>`quote_mode: str="tick"`, `spread_tick: int=1`, `level_interval_tick: int=1`<br>`spread_percent: float=0.0002`, `level_interval_percent: float=0.0001`<br>`split_count: int=1`, `snapshot: dict\|None=None`, `passive: bool=True` | `tuple[list[dict], list[dict]]` | 🎯 **核心报价生成**。按模式计算多层级买卖价，支持被动保护、订单拆分。参数非法或 `fair_price<=0` 时安全返回空列表，层级硬编码上限为 `5` |
| `_calculate_tick_quote_price` | *(私有)* `fair_price`, `price_tick`, `level`, `spread_tick`, `level_interval_tick` | `tuple[float, float, float]` | 📏 **跳数定价模型**。`offset = spread + (level-1)*interval`，买价向下取整，卖价向上取整，返回 `(buy, sell, offset_tick)` |
| `_calculate_percent_quote_price` | *(私有)* `fair_price`, `price_tick`, `level`, `spread_percent`, `level_interval_percent` | `tuple[float, float, float]` | 📊 **百分比定价模型**。按 `fair_price * (1 ± offset)` 计算并执行 Tick 对齐，返回 `(buy, sell, offset_percent)` |
| `floor_to_tick` / `ceil_to_tick` / `round_to_tick` | `price: float`, `price_tick: float` | `float` | 🎛️ **价格对齐工具**。分别实现向下/向上/四舍五入至最小变动价位，确保报单符合交易所规范 |
| `need_requote` | `new_buy_quotes: list[dict]`, `new_sell_quotes: list[dict]`, `price_tick: float`, `update_tolerance: int` | `bool` | 🔄 **防抖重报校验**。对比新旧报价长度、价格（容忍 `update_tolerance` 跳）与数量。仅当变动超阈值时返回 `True`，大幅降低撤单/追单频率与手续费损耗 |
| `update_current_quotes` | `buy_quotes: list[dict]`, `sell_quotes: list[dict]` | `None` | 💾 **状态快照更新**。浅拷贝新报价至 `self.current_*`，供下次 `need_requote` 比对，防引用污染 |
| `clear_current_quotes` | *(无)* | `None` | 🧹 **清空本地缓存**。策略停止、暂停或切换合约时调用，重置状态机 |

---
### 📦 报价字典结构规范 (`Quote Dict`)
`generate_quotes` 返回的列表元素为统一结构的字典，下游撤单/发单模块可直接解析：

| 字段名 | 类型 | 说明 |
|:---|:---|:---|
| `side` | `str` | `"buy"` 或 `"sell"` |
| `level` | `int` | 报价档位（`1` 为最近档，依次向外） |
| `order_index` | `int` | 拆单序号（`1` ~ `split_count`） |
| `price` | `float` | 对齐后的合规报单价格 |
| `volume` | `float` | 单笔委托数量 |
| `quote_mode` | `str` | 定价模式标识（`"tick"` / `"percent"`） |
| `offset_value` | `float` | 偏离基准价的绝对跳数或百分比值 |

---
### 💡 核心逻辑与实盘调优指南

1. **被动报价保护 (`passive=True`)**  
   逻辑：`buy_price = min(buy_price, bid1)`，`sell_price = max(sell_price, ask1)`。  
   ✅ **意义**：确保报价永不主动穿越盘口一价，维持 Maker 身份赚取返佣。若需切换为 Taker 抢单模式，传入 `passive=False` 或 `snapshot=None`。

2. **防抖死区 (`need_requote` 的 `update_tolerance`)**  
   价格变动需超过 `update_tolerance × price_tick` 才触发重报。  
   📌 **调参建议**：  
   - 高频做市：`1~2` tick（灵敏响应盘口变化）  
   - 网格/中低频：`3~5` tick（过滤微观噪声，降低订单 churn rate）  
   - 注意：`need_requote` 同时校验 `volume` 严格相等，若需动态调整手数，建议在外层控制逻辑中处理。

3. **订单拆分 (`split_count`)**  
   将单档报价拆分为 `N` 笔相同价格/数量的委托。  
   ✅ **应用场景**：冰山单伪装、降低单笔成交对市场冲击、提升部分成交概率。实盘中需结合交易所 `max_order_volume` 限制使用。

4. **价格对齐策略选择**  
   - `floor_to_tick`：买盘专用，确保报价不高于理论值，避免意外吃单。  
   - `ceil_to_tick`：卖盘专用，确保报价不低于理论值。  
   - `round_to_tick`：适用于中性定价或回测场景。  
   ⚠️ **代码已内置安全对齐**：`_calculate_*` 方法自动对买卖盘应用 `floor/ceil`，策略层无需重复处理。

5. **状态管理线程安全提示**  
   `update_current_quotes` 使用 `quote.copy()` 浅拷贝。因报价字典仅含基础类型（int/float/str），浅拷贝已足够安全且性能最优。若未来扩展嵌套结构，需改为 `copy.deepcopy()`。

---
### 🔄 典型报价调度流水线
```text
on_tick(tick) 
  → fair_price = pricing_engine.calculate_fair_price(snapshot, method="micro")
  → if fair_price <= 0: return
  
  → new_buy, new_sell = quote_engine.generate_quotes(
        fair_price, pricetick, levels=3, volume=1.0, 
        spread_tick=2, level_interval_tick=1, passive=True, snapshot=snapshot
    )
  
  → if quote_engine.need_requote(new_buy, new_sell, pricetick, tolerance=2):
        cancel_all_active_quotes()
        send_orders(new_buy + new_sell)
        quote_engine.update_current_quotes(new_buy, new_sell)
```

> 📌 此规范已完整覆盖 `QuoteEngine` 的报价生成、价格对齐、防抖校验与状态管理逻辑。如需与 `QuoteRiskFilter` + `PricingEngine` 封装为完整的 `MarketMakerPipeline`、增加动态库存偏移（Inventory Skew）定价，或生成对应的 `pytest` 压力测试用例，可提供具体集成需求。