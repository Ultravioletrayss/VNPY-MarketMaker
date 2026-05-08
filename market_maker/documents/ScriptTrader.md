**ScriptTrader - 脚本策略交易模块 程序员速查表**

### 1. 模块加载

```python
from vnpy_scripttrader import ScriptTraderApp
main_engine.add_app(ScriptTraderApp)   # 在创建 main_engine 后添加
```

---

### 2. 脚本策略模板（核心结构）

```python
from time import sleep
from vnpy_scripttrader import ScriptEngine

def run(engine: ScriptEngine):
    """脚本策略主函数"""
    vt_symbols = ["sc2209.INE", "rb888.SHFE"]

    # 订阅行情
    engine.subscribe(vt_symbols)

    # 获取合约信息
    for vt_symbol in vt_symbols:
        contract = engine.get_contract(vt_symbol)
        engine.write_log(f"合约信息: {contract}")

    # 主循环
    while engine.strategy_active:          # 关键控制变量
        for vt_symbol in vt_symbols:
            tick = engine.get_tick(vt_symbol)
            engine.write_log(f"最新行情: {tick}")
        
        sleep(3)   # 建议使用 sleep，避免 CPU 空转
```

**关键**：`engine.strategy_active` 为 False 时自动退出循环（点击【停止】按钮触发）。

---

### 3. 脚本引擎初始化（Jupyter / CLI 模式）

```python
from vnpy_scripttrader import init_cli_trading
from vnpy_ctp import CtpGateway

engine = init_cli_trading([CtpGateway])   # 支持多接口
```

---

### 4. 核心功能函数速查表

#### **连接接口**
| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `connect_gateway` | `setting: dict, gateway_name: str` | None | 连接交易接口 |

#### **行情订阅**
| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `subscribe` | `vt_symbols: Sequence[str]` | None | 订阅单个或多个合约行情 |

#### **数据查询 - 单条**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_tick` | `vt_symbol: str, use_df=False` | `TickData` 或 `DataFrame` | 最新 Tick |
| `get_contract` | `vt_symbol: str, use_df=False` | `ContractData` 或 `DataFrame` | 合约信息 |
| `get_order` | `vt_orderid: str, use_df=False` | `OrderData` 或 `DataFrame` | 委托信息 |
| `get_account` | `vt_accountid: str, use_df=False` | `AccountData` 或 `DataFrame` | 账户资金 |
| `get_position` | `vt_positionid: str, use_df=False` | `PositionData` 或 `DataFrame` | 持仓（`gateway.vt_symbol.方向`） |

#### **数据查询 - 多条 / 全量**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_ticks` | `vt_symbols: Sequence[str], use_df=False` | List / DataFrame | 多个最新 Tick |
| `get_orders` | `vt_orderids: Sequence[str], use_df=False` | List / DataFrame | 多个委托 |
| `get_trades` | `vt_orderid: str, use_df=False` | List[TradeData] / DataFrame | 该委托的所有成交 |
| `get_bars` | `vt_symbol, start_date, interval, use_df=False` | List[BarData] / DataFrame | 历史 K 线（需数据服务） |
| `get_all_contracts` | `use_df=False` | List / DataFrame | 全市场合约 |
| `get_all_active_orders` | `use_df=False` | List / DataFrame | 所有活动委托 |
| `get_all_accounts` | `use_df=False` | List / DataFrame | 所有账户 |
| `get_all_positions` | `use_df=False` | List / DataFrame | 所有持仓 |

#### **交易委托函数**

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `buy` | `vt_symbol, price, volume, order_type=OrderType.LIMIT` | `vt_orderid: str` | 开多（LONG + OPEN） |
| `sell` | 同上 | `vt_orderid: str` | 平多（SHORT + CLOSE） |
| `short` | 同上 | `vt_orderid: str` | 开空（SHORT + OPEN） |
| `cover` | 同上 | `vt_orderid: str` | 平空（LONG + CLOSE） |
| `send_order` | `vt_symbol, price, volume, direction, offset, order_type` | `vt_orderid: str` | 底层发单函数 |
| `cancel_order` | `vt_orderid: str` | None | 撤单 |

**支持的 `order_type`**：
- `OrderType.LIMIT`（默认）
- `OrderType.MARKET`
- `OrderType.FAK` / `OrderType.FOK`
- `OrderType.STOP`

---

### 5. 辅助功能函数

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `write_log` | `msg: str` | None | 输出日志到界面 |
| `send_email` | `msg: str` | None | 发送邮件（需全局配置邮箱） |

---

### 6. 常用代码片段

**订阅 + 循环监控**：
```python
engine.subscribe(["IF888.CFFEX", "510300.SHSE"])
while engine.strategy_active:
    tick = engine.get_tick("IF888.CFFEX")
    engine.write_log(f"{tick.datetime}  {tick.last_price}")
    sleep(1)
```

**批量下单示例**：
```python
engine.buy("rb888.SHFE", 3450, 2)
engine.short("sc888.INE", 480.5, 1, order_type=OrderType.FAK)
```

**撤单**：
```python
orderid = engine.buy(...)
engine.cancel_order(orderid)
```

---

### 7. 快速记忆口诀

- **订阅**：`engine.subscribe([vt_symbols])`
- **查询**：`get_xxx` / `get_all_xxx`（带 `use_df=True` 可转 DataFrame）
- **下单**：`buy/sell/short/cover`（推荐）
- **控制**：`while engine.strategy_active`
- **日志**：`engine.write_log()`

---

**与 CTA 策略的区别**：
- ScriptTrader 更灵活，支持**多品种、多交易所、跨市场**策略
- 适合**对冲、套利、扫描选股、复杂组合**等场景
- 无需继承模板，直接操作 `engine` 对象

需要我补充 **OrderType / Direction / Offset 枚举表** 或 **完整 Jupyter 示例** 吗？