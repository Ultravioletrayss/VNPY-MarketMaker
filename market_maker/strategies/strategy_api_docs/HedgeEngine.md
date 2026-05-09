以下是为您整理的 **`HedgeEngine` 自动对冲/硬风控引擎 API 规范文档**。该类是策略风险管理的最后一道防线，负责在库存偏移失效或行情单边突破时，强制触发平仓指令。

---
## 🛡️ `HedgeEngine` (自动对冲/硬风控引擎)
**架构定位**：独立风控执行模块。监控净持仓绝对值，当突破硬性阈值时，生成主动吃单(Taker)平仓指令。与 `InventorySkewEngine`（软对冲/引导减仓）形成 **“被动调节 + 主动平仓”** 的双层风控体系，确保极端行情下敞口可控。

### 📋 核心方法速查
| 方法名 | 参数类型 | 返回值 | 作用说明 |
|:---|:---|:---|:---|
| `__init__` | *(无)* | `None` | 初始化状态缓存：`last_hedge_action=""`, `last_hedge_price=0.0`, `last_hedge_volume=0.0` |
| `check_hedge` | `pos: float`, `hedge_threshold: float`, `hedge_volume: float`, `price_tick: float`<br>`snapshot: dict`, `hedge_price_tick: int=1` | `dict \| None` | 🚨 **核心触发器**。检查持仓是否超阈值，计算对冲价量。若触发返回指令字典，否则返回 `None` |
| `calculate_sell_close_price` | `bid1: float`, `price_tick: float`, `hedge_price_tick: int=1` | `float` | 📉 **空头平仓/多头减仓定价**。`bid1 - offset`，生成保证成交的限价单（Marketable Limit Order） |
| `calculate_buy_close_price` | `ask1: float`, `price_tick: float`, `hedge_price_tick: int=1` | `float` | 📈 **多头平仓/空头回补定价**。`ask1 + offset`，穿透卖一价确保快速成交 |
| `update_last_hedge` | `hedge_order: dict` | `None` | 💾 更新最近一次对冲动作的状态缓存（内部自动调用） |
| `clear_last_hedge` | *(无)* | `None` | 🧹 清空对冲状态缓存，策略重启或日终结算时调用 |
| `get_last_hedge_*` | *(无)* | `str` / `float` | 🔍 获取最近一次对冲的动作类型、价格、成交量（供UI/日志监控） |

---
### 📦 对冲指令字典结构 (`Hedge Order Dict`)
`check_hedge` 触发时返回的标准指令结构，下游可直接映射为 `OrderData` 或发送至交易网关：

| 字段名 | 类型 | 说明 |
|:---|:---|:---|
| `action` | `str` | `"SELL_CLOSE"`（平多/空开） 或 `"BUY_CLOSE"`（平空/多开） |
| `price` | `float` | 已对齐合约规格的主动平仓价格 |
| `volume` | `float` | 实际对冲数量（`min(abs(pos), hedge_volume)`） |
| `reason` | `str` | 触发原因标识（如 `"long_position_exceed_threshold"`） |

---
### 💡 核心逻辑与实盘调优指南

1. **软对冲 vs 硬对冲 分工边界**
   | 模块 | 机制 | 订单类型 | 适用场景 |
   |:---|:---|:---|:---|
   | `InventorySkewEngine` | 价格偏移引导成交 | Maker（挂单） | 日常库存管理，赚取点差/返佣 |
   | `HedgeEngine` | 阈值触发强制平仓 | Taker（吃单） | 极端行情/单边突破/软对冲失效时的硬止损 |

2. **参数联动设置建议**
   - `hedge_threshold` **必须小于** `max_position`。建议：`hedge_threshold = max_position × 0.6 ~ 0.8`，为软对冲预留缓冲空间。
   - `hedge_volume` 建议设为策略常规单量的 `50% ~ 100%`。过大易引发冲击成本，过小则需多次触发。
   - `hedge_price_tick` 控制侵略性：`1` = 吃一价（高成交率，低滑点），`2~3` = 穿透多档（极端行情保成交），`0` = 挂一价（不推荐，对冲可能挂单不成交）。

3. **循环执行机制**  
   `check_hedge` **单次仅生成一笔指令**。若 `pos` 远超阈值（如 `pos=10, hedge_volume=2`），主策略需在 `on_tick` 或定时任务中**循环调用**，直至 `pos < hedge_threshold`。

4. **防御性设计**
   - 盘口有效性检查：`bid1 <= 0 or ask1 <= 0 or ask1 <= bid1` 时直接返回 `None`，防止在集合竞价/停牌/断流期间误发对冲单。
   - 价格保护：`calculate_sell_close_price` 内置 `if price <= 0: return bid1`，防负价格废单。
   - 状态缓存仅用于外部监控，**不参与**内部风控判断，保证引擎无副作用。

---
### 🔄 标准调用流水线 (Pipeline)
对冲引擎通常独立于报价流水线，建议在 `on_tick` 末尾或独立心跳循环中执行：

```python
# 1. 执行常规报价逻辑 (Pricing -> Quote -> Skew -> Filter)
# ... (略)

# 2. 硬风控检查 (HedgeEngine)
hedge_order = self.hedge_engine.check_hedge(
    pos=self.pos,
    hedge_threshold=self.hedge_threshold,
    hedge_volume=self.hedge_volume,
    price_tick=self.price_tick,
    snapshot=snapshot,
    hedge_price_tick=self.hedge_price_tick,
)

# 3. 触发平仓执行
if hedge_order:
    if hedge_order["action"] == "SELL_CLOSE":
        self.sell(price=hedge_order["price"], volume=hedge_order["volume"])
    elif hedge_order["action"] == "BUY_CLOSE":
        self.cover(price=hedge_order["price"], volume=hedge_order["volume"])
    
    self.write_log(f"[硬风控] 触发对冲: {hedge_order['reason']} | 价:{hedge_order['price']} 量:{hedge_order['volume']}")
```

---
### ⚙️ 主策略配置扩展
需在策略类中声明参数并加入监控列表：
```python
class MyMarketMaker(CtaTemplate):
    parameters = [
        "hedge_threshold",
        "hedge_volume",
        "hedge_price_tick",
    ]
    hedge_threshold: float = 5.0      # 触发硬对冲的持仓绝对值阈值
    hedge_volume: float = 2.0         # 单笔对冲执行数量
    hedge_price_tick: int = 1         # 对冲价格穿透跳数
```

> 📌 此规范已完整对齐 `HedgeEngine` 的触发逻辑、定价模型与状态管理。如需增加 **动态阈值（基于ATR/波动率调整）**、**分批对冲队列管理**，或与前序模块整合为完整的 `MarketMakerPipeline` 架构，可提供具体需求。文档结构已优化为标准 Markdown，PyCharm 可直接渲染预览。