以下是为您更新的 **`InventorySkewEngine` 库存偏移与被动限价引擎 API 规范文档**。本次升级引入了 `snapshot` 与 `passive` 参数，并新增 `apply_passive_limit` 方法，实现了 **软对冲 + Maker身份保护** 的双层定价调节机制。

---
## 📐 `InventorySkewEngine` (库存偏移与被动限价引擎)
**架构定位**：动态报价调节器，位于 `QuoteEngine` 之后、`QuoteRiskFilter` 之前。结合净持仓比例计算偏移跳数，对双侧报价执行同步平移；可选叠加盘口一价限价保护，确保策略始终维持 `Maker` 身份，避免意外吃单。

### 📋 核心方法速查
| 方法名 | 参数类型 | 返回值 | 作用说明 |
|:---|:---|:---|:---|
| `__init__` | *(无)* | `None` | 初始化状态缓存：`last_skew_tick=0`, `last_pos_ratio=0.0` |
| `apply_skew` | `buy_quotes`, `sell_quotes`, `pos`, `max_position`, `price_tick`<br>`max_skew_tick=3`, `snapshot=None`, `passive=True` | `tuple[list[dict], list[dict]]` | 🎛️ **核心调度**。计算持仓偏移量平移报价，若启用被动模式则二次叠加盘口限价保护 |
| `calculate_pos_ratio` | `pos: float`, `max_position: float` | `float` | 📊 计算持仓比例 `pos/max_position`，强制钳位至 `[-1.0, 1.0]` |
| `calculate_skew_tick` | `pos_ratio: float`, `max_skew_tick: int` | `int` | 📈 计算偏移跳数。使用 `round()` 四舍五入映射，避免截断误差 |
| `move_quotes` | `quotes: list[dict]`, `price_tick: float`, `skew_tick: int` | `list[dict]` | ⬆️⬇️ **整体平移**。执行 `price += skew_tick × price_tick`，过滤 `price≤0` 异常单，注入 `skew_tick` 标识 |
| `apply_passive_limit` | `buy_quotes`, `sell_quotes`, `snapshot: dict` | `tuple[list[dict], list[dict]]` | 🛡️ **被动限价**。强制 `buy_price ≤ bid1`、`sell_price ≥ ask1`，维持挂单(Maker)身份 |
| `get_last_skew_tick` / `get_last_pos_ratio` | *(无)* | `int` / `float` | 🔍 获取最近一次计算状态（仅用于监控/日志，不参与内部计算） |

---
### 📦 报价字典结构更新 (`Quote Dict`)
| 字段名 | 类型 | 说明 |
|:---|:---|:---|
| `skew_tick` | `int` | 当前报价应用的库存偏移跳数。`>0`=价格上移，`<0`=价格下移，`0`=未偏移 |
| `price` | `float` | 经偏移与被动限价双重处理后的最终合规报价 |

> ⚠️ **不可变设计**：所有方法均通过 `quote.copy()` 生成新列表，**绝不修改**上游 `QuoteEngine` 原始输出，符合量化系统函数式编程规范。

---
### 💡 核心逻辑与实盘调优指南

1. **双层价格调节流水线**
   ```text
   原始报价 → 库存偏移 (move_quotes) → 被动限价 (apply_passive_limit) → 最终报价
   ```
   - **第一层（软对冲）**：根据持仓比例平移双侧报价，引导市场自然成交以减仓。
   - **第二层（被动保护）**：若偏移后报价突破盘口一价（常见于高 `max_skew_tick` 或剧烈波动），`apply_passive_limit` 会将其强制拉回 `bid1`/`ask1`，**确保永不主动吃单**，维持 Maker 返佣与低滑点。

2. **`round()` 映射升级**  
   旧版 `int()` 会直接截断小数，新版 `round()` 四舍五入更符合价格对齐直觉，尤其在 `pos_ratio` 较小（如 `0.3`）时能保留更平滑的偏移梯度。

3. **参数 `max_skew_tick` 与 `passive` 联动策略**
   | `passive` | `max_skew_tick` | 适用场景 |
   |:---|:---|:---|
   | `True` | `2~4` | **标准做市**：优先保证挂单身份，偏移受盘口限制，库存调节温和 |
   | `True` | `5~8` | **高波动做市**：允许较大偏移，但触及一价后强制截断，防极端行情吃单 |
   | `False` | `1~3` | **趋势/抢单策略**：放弃 Maker 身份，允许报价穿透盘口，追求快速成交 |
   | `False` | `>3` | ❌ 不推荐：易引发连续吃单与高额滑点，丧失软对冲意义 |

4. **安全与防御设计**
   - `skew_tick > 0` 条件守卫：中性仓或参数非法时直接跳过平移，仅保留被动限价（若启用），避免无效计算。
   - `move_quotes` 内置 `if adjusted_price <= 0: continue`：自动剔除负价格报价，防交易所拒单。
   - `calculate_pos_ratio` 钳位 `[-1.0, 1.0]`：防极端行情下 `pos` 突破 `max_position` 导致偏移失控。

---
### 🔄 标准调用流水线 (Pipeline)
在 `CtaTemplate.on_tick()` 中，模块调用顺序必须严格遵循以下链路：

```python
# 1. 生成基准报价 (QuoteEngine)
buy_quotes, sell_quotes = self.quote_engine.generate_quotes(
    fair_price=fair_price,
    price_tick=self.price_tick,
    quote_levels=self.quote_levels,
    order_volume=self.order_volume,
    quote_mode=self.quote_mode,
    spread_tick=self.spread_tick,
    level_interval_tick=self.level_interval_tick,
    snapshot=snapshot,
    passive=True,  # 基础报价层被动保护
)

# 2. 库存软对冲 + 二次被动限价 (InventorySkewEngine)
buy_quotes, sell_quotes = self.inventory_skew_engine.apply_skew(
    buy_quotes=buy_quotes,
    sell_quotes=sell_quotes,
    pos=self.pos,
    max_position=self.max_position,
    price_tick=self.price_tick,
    max_skew_tick=self.max_skew_tick,
    snapshot=snapshot,      # 传入最新盘口用于被动限价
    passive=True,           # 启用偏移后二次限价保护
)

# 3. 风控过滤 (QuoteRiskFilter)
buy_quotes, sell_quotes = self.quote_risk_filter.filter_by_position(
    buy_quotes=buy_quotes,
    sell_quotes=sell_quotes,
    pos=self.pos,
    max_position=self.max_position,
)

# 4. 防抖校验 & 发单 (QuoteEngine + 策略层)
if self.quote_engine.need_requote(buy_quotes, sell_quotes, self.price_tick, update_tolerance=2):
    self.cancel_all_active_quotes()
    self.send_quotes(buy_quotes + sell_quotes)
    self.quote_engine.update_current_quotes(buy_quotes, sell_quotes)
```

---
### ⚙️ 主策略配置扩展
需在策略类中声明参数并加入监控列表：
```python
class MyMarketMaker(CtaTemplate):
    parameters = ["max_skew_tick"]  # 加入参数列表
    max_skew_tick: int = 3          # 默认值（满仓最大偏移跳数）
```

> 📌 此规范已完整对齐您本次升级的 `passive` 保护、`round()` 映射与双层调节逻辑。如需增加 **动态 `max_skew_tick`（基于波动率/成交速率自适应）**、**非线性偏移曲线（如二次方映射）**，或生成对应的 `pytest` 边界测试用例，可提供具体需求。文档结构已优化为标准 Markdown，PyCharm 可直接渲染预览。