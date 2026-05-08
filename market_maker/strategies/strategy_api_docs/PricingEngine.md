以下是为您整理的 **`PricingEngine` 定价引擎 API 规范文档**。该类属于盘口微观结构定价组件，负责将原始行情快照转化为策略可用的基准价格（Fair Price），内置多模型路由、异常降级与价格对齐逻辑。

---
## 📐 `PricingEngine` (定价引擎)
**架构定位**：轻量级定价计算模块，支持中间价、微观价格（Micro Price）、多档量价加权价三种核心定价模型。适用于做市报价基准生成、高频信号阈值计算、订单路由价格锚定。内部状态缓存最新计算结果，便于流水线复用。

### 📋 核心方法速查
| 方法名 | 参数类型 | 返回值 | 作用说明 |
|:---|:---|:---|:---|
| `__init__` | *(无)* | `None` | 初始化内部状态：`mid_price`, `micro_price`, `depth_weighted_mid`, `fair_price`（默认 `0.0`） |
| `calculate_mid_price` | `snapshot: dict` | `float` | 📏 **买卖一中间价**。`(bid1 + ask1) / 2`。盘口倒挂或价≤0 时返回 `0.0`，结果同步至 `self.mid_price` |
| `calculate_micro_price` | `snapshot: dict` | `float` | ⚡ **微观价格（Micro Price）**。按对手盘量加权：`(ask1*bid1_vol + bid1*ask1_vol)/total_vol`。反映瞬时盘口压力，无量时自动降级为中间价 |
| `calculate_depth_weighted_mid` | `snapshot: dict`, `depth: int=5` | `float` | 🌊 **多档量价加权中间价**。累加前 `depth` 档价量计算加权均价，内置深度截断与脏数据过滤。两侧均无效时降级为中间价 |
| `calculate_fair_price` | `snapshot: dict`, `pricing_method: str="mid"`, `depth: int=5` | `float` | 🎛️ **统一定价路由**。根据 `pricing_method`（`"mid"`/`"micro"`/`"depth_weighted"`）分发计算，结果存入 `self.fair_price`。未知方法默认 fallback 至中间价 |
| `round_to_tick` | `price: float`, `price_tick: float` | `float` | 🎯 **价格对齐工具**。将理论价格按合约最小变动价位四舍五入，确保报单价格符合交易所规范 |

---
### 📦 `snapshot` 数据契约规范
定价方法依赖统一的市场快照结构，需确保上游行情聚合层已注入以下字段：

| 字段名 | 类型 | 说明 | 依赖方法 |
|:---|:---|:---|:---|
| `bid1`, `ask1` | `float` | 买卖一价 | 全部定价方法 |
| `bid1_volume`, `ask1_volume` | `float` | 买卖一量 | `calculate_micro_price` |
| `bid_prices`, `ask_prices` | `list[float]` | 多档买卖价格序列 | `calculate_depth_weighted_mid` |
| `bid_volumes`, `ask_volumes` | `list[float]` | 多档买卖量序列 | `calculate_depth_weighted_mid` |
| `valid_depth` | `int` | 交易所有效盘口层数 | `calculate_depth_weighted_mid` |

---
### 💡 核心定价逻辑与实盘开发指南

1. **状态缓存特性（非纯函数）**  
   该类会更新 `self.*` 属性缓存最新结果。✅ **优势**：高频循环中可直接读取 `engine.fair_price` 避免重复计算。⚠️ **注意**：若用于多线程策略或分布式回测，需确保实例隔离或改用无状态封装。

2. **微观价格 (Micro Price) 业务意义**  
   公式本质为 **对手盘流动性加权**。当 `ask1_volume` 远大于 `bid1_volume` 时，价格更靠近 `bid1`，暗示卖压沉重。适用于捕捉盘口瞬时失衡，比传统中间价提前 `1~3` 个 Tick 反映趋势转折。

3. **深度加权计算的安全设计**  
   - 自动截断：`depth = min(depth, valid_depth, 5)` 防数组越界。
   - 脏数据过滤：`if bid_price <= 0 or ask_price <= 0 or volume <= 0: continue` 跳过异常档位。
   - 降级保护：两侧有效量均为 `0` 时返回 `self.calculate_mid_price(snapshot)`，避免除零或返回 `0.0` 中断策略。

4. **`round_to_tick` 与交易所报单规范**  
   底层使用 Python 内置 `round()`（银行家舍入法：`0.5` 向偶数靠拢）。实盘中通常可接受，但若策略要求严格 **向上/向下取整**（如买一永远不超卖一），建议替换为：
   ```python
   import math
   def round_to_tick_floor(price: float, tick: float) -> float:
       return math.floor(price / tick) * tick
   ```

5. **防御性调用范式**  
   定价引擎不抛异常，而是返回 `0.0` 作为失败标识。策略层必须拦截：
   ```python
   fair_price = engine.calculate_fair_price(snapshot, pricing_method="micro")
   if fair_price <= 0:
       self.write_log("定价失败或盘口异常，暂停报价")
       return
   ```

---
### 🔄 典型定价与报价流水线
```text
on_tick(tick) 
  → 组装 snapshot (填充多档价量序列与 valid_depth)
  → fair_price = engine.calculate_fair_price(snapshot, pricing_method="depth_weighted", depth=5)
  → if fair_price <= 0: return  # 安全拦截
  → raw_bid = fair_price - (spread_tick * pricetick / 2)
  → raw_ask = fair_price + (spread_tick * pricetick / 2)
  → quote_bid = engine.round_to_tick(raw_bid, pricetick)
  → quote_ask = engine.round_to_tick(raw_ask, pricetick)
  → 提交至 QuoteRiskFilter 校验 → 报价引擎发单
```

> 📌 此规范已完整覆盖您提供的定价逻辑。如需将 `PricingEngine` 与 `QuoteRiskFilter` 封装为统一的 `MarketMakerCore` 工作流、增加动态波动率/库存偏移定价模型（如 Avellaneda-Stoikov），或生成对应 `pytest` 边界测试用例，可提供具体集成需求。