**CtaStrategy / CtaTemplate 程序员速查表**

### 1. 策略基础设置（类属性）

| 项目 | 类型 | 说明 |
|------|------|------|
| `author` | str | 策略作者 |
| `parameters` | List[str] | 需要在UI显示/保存的参数列表 |
| `variables` | List[str] | 需要在UI显示/保存的变量列表（状态变量） |

**支持的数据类型**：`str`, `int`, `float`, `bool`

---

### 2. 初始化 `__init__`

```python
def __init__(self, cta_engine, strategy_name: str, vt_symbol: str, setting: dict)
```

- 必须调用 `super().__init__(cta_engine, strategy_name, vt_symbol, setting)`
- 通常在此处初始化：
  - `self.bg = BarGenerator(...)`
  - `self.am = ArrayManager()`

---

### 3. 回调函数（Callback Functions）

| 函数名 | 参数 | 返回值 | 何时被调用 | 常用写法 |
|-------|------|--------|-----------|---------|
| `on_init` | - | None | 策略初始化时 | `write_log("策略初始化")`; `load_bar(...)` |
| `on_start` | - | None | 点击【启动】后 | `write_log("策略启动")` |
| `on_stop` | - | None | 点击【停止】后 | `write_log("策略停止")` |
| `on_tick` | `tick: TickData` | None | 每个新Tick到达 | `self.bg.update_tick(tick)` |
| `on_bar` | `bar: BarData` | None | 每根K线（默认1分钟） | `self.bg.update_bar(bar)` 或直接交易逻辑 |
| `on_xxx_bar` | `bar: BarData` | None | BarGenerator合成的周期K线 | 主要交易逻辑 |
| `on_trade` | `trade: TradeData` | None | 成交回报 | 通常 pass |
| `on_order` | `order: OrderData` | None | 委托回报 | 通常 pass |
| `on_stop_order` | `stop_order: StopOrder` | None | 本地停止单状态更新 | 通常 pass |

---

### 4. 交易下单函数（Trading Functions）

| 函数 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `buy` | `price: float, volume: float, stop=False, lock=False, net=False` | `List[str]` (vt_orderids) | **开多** (LONG + OPEN) |
| `sell` | 同上 | `List[str]` | **平多** (SHORT + CLOSE) |
| `short` | 同上 | `List[str]` | **开空** (SHORT + OPEN) |
| `cover` | 同上 | `List[str]` | **平空** (LONG + CLOSE) |
| `send_order` | `direction: Direction, offset: Offset, price: float, volume: float, stop=False, lock=False, net=False` | `List[str]` | 底层发单函数，一般不直接调用 |
| `cancel_order` | `vt_orderid: str` | None | 撤单 |
| `cancel_all` | - | None | 撤掉策略所有活动委托（常用） |

**常用组合**：
- `stop=True` → 停止单（本地或交易所）
- `lock=True` → 锁仓模式（上期所等）
- `net=True` → 净仓模式（股票、外盘）

---

### 5. 实用功能函数（Utility）

| 函数名 | 参数 | 返回值 | 说明 |
|-------|------|--------|------|
| `write_log` | `msg: str` | None | 输出日志到UI |
| `put_event` | - | None | 刷新UI变量显示（必须写在variables里） |
| `load_bar` | `days: int, interval=Interval.MINUTE, callback=None, use_database=False` | None | 初始化加载K线历史数据 |
| `load_tick` | `days: int` | None | 初始化加载Tick数据 |
| `get_pricetick` | - | `float` 或 `None` | 获取合约最小价格跳动 |
| `get_engine_type` | - | `EngineType` | 判断当前是实盘还是回测引擎 |
| `send_email` | `msg: str` | None | 发送邮件（需全局配置） |
| `sync_data` | - | None | 手动同步变量到json缓存 |

---

### 6. 重要对象

- **`self.bg`**：`BarGenerator` — Tick → Bar 合成
- **`self.am`**：`ArrayManager` — K线序列 + talib指标计算
  - `am.update_bar(bar)`
  - `am.inited`：是否初始化完成
  - `am.boll()`, `am.cci()`, `am.atr()` 等

---

### 7. 常用代码模板片段

**标准 on_xxx_bar 结构**：
```python
def on_15min_bar(self, bar: BarData):
    self.cancel_all()
    am = self.am
    am.update_bar(bar)
    if not am.inited:
        return

    # 计算指标...
    self.put_event()   # 刷新UI
```

**初始化加载历史数据**：
```python
def on_init(self):
    self.write_log("策略初始化")
    self.load_bar(10)        # 默认10天1分钟线
    # self.load_tick(2)      # 如需Tick回测
```

---

**快速记忆口诀**：
- **回调**：`on_init`、`on_start`、`on_tick`、`on_bar`
- **下单**：`buy/sell/short/cover`（带 `stop/lock/net`）
- **刷新**：`put_event()` + `write_log()`
- **加载**：`load_bar()` 在 `on_init`

需要我再拆分成 **Markdown 可复制表格** 或 **单个函数详细签名** 版本吗？