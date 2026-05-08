以下是为您更新的 **`QuoteRiskFilter` 报价风控过滤器 API 规范文档**。新增的盘口量能与失衡度校验已纳入标准风控矩阵，文档保持与前序一致的工程化结构。

---
## 🛡️ `QuoteRiskFilter` (报价风控过滤器)
**架构定位**：无状态盘口风控组件（Stateless Pre-Trade Filter），专用于做市/高频报价策略的 `行情清洗 → 报价生成 → 敞口控制` 链路。所有方法纯函数化，线程安全，可直接嵌入行情推送钩子或报价引擎前置校验。

### 📋 核心方法速查
| 方法名 | 参数类型 | 返回值 | 作用说明 |
|:---|:---|:---|:---|
| `check_market_data` | `snapshot: dict` | `bool` | 📉 **基础有效性校验**。检查买卖一价/量 `>0` 且 `ask1 > bid1`（防盘口倒挂/交叉）。任一异常阻断报价 |
| `check_depth` | `snapshot: dict`, `min_depth: int=1` | `bool` | 🌊 **深度层数校验**。验证 `valid_depth` 是否 `≥ min_depth`，过滤流动性枯竭或交易所断流状态 |
| `check_depth_volume` | `snapshot: dict`, `depth: int=5`, `min_depth_volume: float=1` | `bool` | 📦 **指定深度累计流动性校验**。计算前 `depth` 档买卖盘总量，若任一侧低于阈值返回 `False`，防薄盘滑点与瞬间击穿 |
| `check_spread` | `snapshot: dict`, `price_tick: float`, `min_spread_tick: int` | `bool` | 📏 **价差跳数校验**。将绝对价差换算为跳数，低于设定阈值返回 `False`，控制低波动环境下的做市成本 |
| `check_imbalance` | `snapshot: dict`, `max_imbalance: float=0.9`, `depth: int=5` | `bool` | ⚖️ **盘口买卖失衡度校验**。计算 `(bid_sum - ask_sum) / total`，若绝对值超阈值返回 `False`，防范单边碾压或主力扫盘行情 |
| `filter_by_position` | `buy_quotes: list[dict]`, `sell_quotes: list[dict]`, `pos: float`, `max_position: float` | `tuple[list[dict], list[dict]]` | 🚧 **持仓限额过滤**。根据净持仓 `pos` 与上限 `max_position` 动态清空单边报价队列，严格控制策略敞口风险 |

---
### 📦 `snapshot` 数据契约规范
风控方法依赖统一的市场快照结构，调用前需确保行情网关或数据聚合层已注入以下字段：

| 字段名 | 类型 | 说明 | 依赖方法 |
|:---|:---|:---|:---|
| `bid1`, `ask1` | `float` | 买卖一价 | `check_market_data`, `check_spread` |
| `bid1_volume`, `ask1_volume` | `float` | 买卖一量 | `check_market_data` |
| `valid_depth` | `int` | 交易所推送的有效盘口层数 | `check_depth`, `check_depth_volume`, `check_imbalance` |
| `market_spread` | `float` | 绝对价差 (`ask1 - bid1`) | `check_spread` |
| `bid_volumes` | `list[float]` | 多档买盘量列表（建议长度≥5） | `check_depth_volume`, `check_imbalance` |
| `ask_volumes` | `list[float]` | 多档卖盘量列表（建议长度≥5） | `check_depth_volume`, `check_imbalance` |

---
### 💡 核心风控逻辑与调优指南

1. **安全截断机制 `min(depth, valid_depth, 5)`**  
   `check_depth_volume` 与 `check_imbalance` 均内置三重截断：  
   ✅ 用户设定值 `depth`  
   ✅ 交易所实际深度 `valid_depth`  
   ✅ 硬编码上限 `5`（防数组越界与性能衰减）  
   📌 **开发建议**：上游 `snapshot` 组装时，`bid_volumes`/`ask_volumes` 长度若不足 5，建议用 `0.0` 填充对齐，避免切片索引异常。

2. **失衡度阈值 `max_imbalance` 调参逻辑**  
   - `0.9` 表示允许单侧量能占比达 `95%`（`(1+0.9)/2`），属**宽松过滤**，适合趋势跟踪或宽频做市。  
   - 若用于**中性做市/网格**，建议降至 `0.6~0.75`，提前规避主力单侧扫盘导致的库存倾斜。  
   - 可结合波动率动态调整：`max_imbalance = base_threshold * (1 - vol_ratio)`。

3. **量能阈值 `min_depth_volume` 与合约适配**  
   该值为绝对手数/张数，需按合约乘数与流动性分层配置：  
   - 主力合约（如 IF/IC/螺纹）：`10~50`  
   - 次主力/小品种：`1~5`  
   - 期权/微盘股：`0.1~1`（注意浮点精度）

4. **报价过滤不修改原对象**  
   `filter_by_position` 返回新列表引用，**不执行就地清空**。若需高性能内存复用，可在调用方使用：
   ```python
   buy_quotes.clear() if pos >= max_position else None
   ```

---
### 🔄 典型报价风控流水线
```text
on_tick(tick) 
  → 组装 snapshot (填充 bid/ask_volumes, valid_depth, market_spread)
  → risk.check_market_data(snapshot)          # 基础有效性
  → risk.check_depth(snapshot, min_depth=2)   # 流动性层数
  → risk.check_depth_volume(snapshot, min_depth_volume=5.0) # 盘口厚度
  → risk.check_imbalance(snapshot, max_imbalance=0.7)       # 防单边碾压
  → risk.check_spread(snapshot, pricetick, min_spread=2)    # 成本保护
  → 生成 buy_quotes / sell_quotes
  → buy, sell = risk.filter_by_position(buy, sell, pos, max_pos) # 敞口控制
  → 提交至报价引擎 / Gateway
```

> 📌 此规范已同步您新增的 `check_depth_volume` 与 `check_imbalance` 逻辑。如需生成对应的 `pytest` 边界测试用例、接入 `vnpy` 的 `CtaTemplate` 回调封装，或需将风控参数外置为 YAML/JSON 配置加载模板，可提供具体集成场景。