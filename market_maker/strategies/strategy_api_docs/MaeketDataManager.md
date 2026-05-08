以下是为您整理的 **`QuoteRiskFilter` 报价风控过滤器 API 规范文档**。该类属于典型的 **盘前/盘中风控模块**，专用于做市或高频报价策略的 `Pre-Trade` 检查环节，确保在安全的市场状态与风控边界内生成报价。

---
## 🛡️ `QuoteRiskFilter` (报价风控过滤器)
**架构定位**：无状态风控组件（Stateless Risk Filter），所有方法均为纯函数逻辑，线程安全，可直接嵌入行情推送或报价生成前置钩子。

### 📋 核心方法速查
| 方法名 | 参数类型 | 返回值 | 作用说明 |
|:---|:---|:---|:---|
| `check_market_data` | `snapshot: dict` | `bool` | 📉 **基础行情有效性校验**。检查买卖一价/量是否 `>0`，且 `ask1 > bid1`（防止盘口倒挂/交叉）。任一条件不满足返回 `False`，阻断报价 |
| `check_depth` | `snapshot: dict`, `min_depth: int=1` | `bool` | 🌊 **流动性深度校验**。验证 `snapshot["valid_depth"]` 是否 `≥ min_depth`。用于过滤盘口极薄、易被扫单的流动性枯竭状态 |
| `check_spread` | `snapshot: dict`, `price_tick: float`, `min_spread_tick: int` | `bool` | 📏 **买卖价差校验**。将市场绝对价差换算为跳数（`spread_tick = market_spread / price_tick`），若低于阈值返回 `False`，防止在低波动/高滑点环境下做市 |
| `filter_by_position` | `buy_quotes: list[dict]`, `sell_quotes: list[dict]`, `pos: float`, `max_position: float` | `tuple[list[dict], list[dict]]` | ⚖️ **持仓限额过滤**。若 `pos ≥ max_position` 则清空买报价队列（禁止多头加仓）；若 `pos ≤ -max_position` 则清空卖报价队列。返回过滤后的报价元组 |

### 📦 `snapshot` 字典结构规范
风控方法依赖统一的市场快照结构，调用前需确保数据网关或行情处理器已注入以下字段：

| 字段名 | 类型 | 说明 | 校验逻辑依赖 |
|:---|:---|:---|:---|
| `bid1` | `float` | 买一价 | `check_market_data`, `check_spread` |
| `ask1` | `float` | 卖一价 | `check_market_data`, `check_spread` |
| `bid1_volume` | `float` | 买一量 | `check_market_data` |
| `ask1_volume` | `float` | 卖一量 | `check_market_data` |
| `valid_depth` | `int` | 有效盘口深度层数 | `check_depth` |
| `market_spread` | `float` | 绝对买卖价差 (`ask1 - bid1`) | `check_spread` |

### 💡 专业开发与风控集成建议

1. **无状态设计优势**  
   该类不包含实例变量，所有状态通过参数传入。✅ **推荐实践**：在策略初始化时实例化一次，在 `on_tick` 或报价循环中重复调用，避免重复创建开销。
   ```python
   risk_filter = QuoteRiskFilter()
   if not risk_filter.check_market_data(snapshot): 
       self.write_log("行情快照异常，跳过本次报价")
       return
   ```

2. **参数调优指南**  
   - `min_depth`：主力合约通常设为 `3~5`，冷门/小盘合约可降至 `1`。
   - `min_spread_tick`：高频做市建议 `2~3` tick，避免价差被手续费/滑点吞噬；趋势或低频策略可设为 `1`。
   - `max_position`：应与资金曲线、合约乘数联动计算，建议通过配置文件动态加载，避免硬编码。

3. **防御性编程提示**  
   - `check_market_data` 已内置 `<=0` 防护，但实盘对接时需防范网关推送 `NaN` 或 `inf`。建议在数据清洗层增加 `math.isfinite()` 校验。
   - `filter_by_position` **不修改原列表对象**，而是返回新引用。若需在原队列上就地过滤，请使用切片赋值：`buy_quotes[:] = []`。

4. **典型调用链路**  
   ```text
   on_tick(tick) 
     → 组装 snapshot 
     → risk_filter.check_market_data(snapshot) 
     → risk_filter.check_spread(snapshot, tick, min_spread) 
     → 生成 buy/sell quotes 
     → buy, sell = risk_filter.filter_by_position(buy, sell, pos, max_pos) 
     → 提交至报价引擎
   ```

> 📌 此文档适用于做市商(MM)、网格(Grid)、高频报价(HFT)等策略架构。如需对接 `vnpy` 的 `OrderRequest` 转换逻辑、增加动态波动率/最大回撤过滤，或需要生成对应的单元测试用例，可提供具体业务场景。