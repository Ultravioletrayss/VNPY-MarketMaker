from datetime import datetime
from zoneinfo import ZoneInfo

from vnpy.trader.constant import Exchange
from vnpy.trader.database import get_database

database = get_database()

ticks = database.load_tick_data(
    symbol="rb2505",
    exchange=Exchange.SHFE,
    start=datetime(2025, 2, 28, 20, 59, tzinfo=ZoneInfo("Asia/Shanghai")),
    end=datetime(2025, 2, 28, 21, 1, tzinfo=ZoneInfo("Asia/Shanghai")),
)

print("数量：", len(ticks))

for tick in ticks[:5]:
    print(
        tick.vt_symbol,
        tick.datetime,
        tick.datetime.astimezone(ZoneInfo("Asia/Shanghai")),
        tick.last_price,
        tick.bid_price_1,
        tick.ask_price_1,
    )