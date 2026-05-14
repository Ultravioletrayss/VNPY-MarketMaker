import csv
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from vnpy.trader.constant import Exchange
from vnpy.trader.object import TickData
from vnpy.trader.database import get_database


# 中国期货市场时间，使用北京时间
CHINA_TZ = ZoneInfo("Asia/Shanghai")


def to_float(value, default: float = 0.0) -> float:
    """安全转换为 float，空值或异常值返回默认值"""

    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    try:
        return float(value)
    except ValueError:
        return default


def get_value(row: dict, *names: str, default: str = "") -> str:
    """
    从 CSV 行里按多个可能字段名取值。

    例如：
    有些文件叫 OpenInterest
    有些文件叫 OpenInt
    """

    for name in names:
        if name in row:
            return row[name]

    return default


def parse_datetime(action_day: str, update_time: str) -> datetime:
    """
    用 ActionDay + UpdateTime 合成 vn.py TickData.datetime。

    例如：
        ActionDay = 20250228
        UpdateTime = 20:59:00.500

    生成：
        2025-02-28 20:59:00.500000+08:00
    """

    action_day = str(action_day).strip()
    update_time = str(update_time).strip()

    dt_text = f"{action_day} {update_time}"

    dt = datetime.strptime(dt_text, "%Y%m%d %H:%M:%S.%f")

    # 加上北京时间时区，避免 MongoDB 里已有 aware datetime 造成比较报错
    return dt.replace(tzinfo=CHINA_TZ)


def detect_delimiter(file_path: str) -> str:
    """判断文件是逗号分隔还是制表符分隔"""

    with open(file_path, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()

    if "\t" in first_line:
        return "\t"

    return ","


def open_csv_reader(file_path: str):
    """
    打开 CSV 文件。

    优先使用 utf-8-sig。
    如果编码不对，再回退到 gbk。
    """

    delimiter = detect_delimiter(file_path)

    try:
        f = open(file_path, "r", encoding="utf-8-sig", newline="")
        reader = csv.DictReader(f, delimiter=delimiter)
        return f, reader
    except UnicodeDecodeError:
        f = open(file_path, "r", encoding="gbk", newline="")
        reader = csv.DictReader(f, delimiter=delimiter)
        return f, reader


def load_shfe_level2_csv(file_path: str) -> list[TickData]:
    """
    读取上期所五档 Level2 CSV，并转换成 vn.py TickData 列表。
    """

    ticks: list[TickData] = []

    f, reader = open_csv_reader(file_path)

    with f:
        for row in reader:
            symbol = str(row["InstrumentID"]).strip()

            dt = parse_datetime(
                action_day=row["ActionDay"],
                update_time=row["UpdateTime"],
            )

            tick = TickData(
                symbol=symbol,
                exchange=Exchange.SHFE,
                datetime=dt,
                gateway_name="DB",

                # 基础行情
                last_price=to_float(row.get("LastPrice")),
                volume=to_float(row.get("Volume")),
                turnover=to_float(row.get("Turnover")),
                open_interest=to_float(
                    get_value(row, "OpenInterest", "OpenInt")
                ),

                # 日内统计
                open_price=to_float(row.get("OpenPrice")),
                high_price=to_float(row.get("HighPrice")),
                low_price=to_float(row.get("LowPrice")),
                pre_close=to_float(row.get("PreClosePrice")),

                # 涨跌停
                limit_up=to_float(row.get("UpperLimitPrice")),
                limit_down=to_float(row.get("LowerLimitPrice")),

                # 买一到买五
                bid_price_1=to_float(row.get("BidPrice1")),
                bid_volume_1=to_float(row.get("BidVolume1")),
                bid_price_2=to_float(row.get("BidPrice2")),
                bid_volume_2=to_float(row.get("BidVolume2")),
                bid_price_3=to_float(row.get("BidPrice3")),
                bid_volume_3=to_float(row.get("BidVolume3")),
                bid_price_4=to_float(row.get("BidPrice4")),
                bid_volume_4=to_float(row.get("BidVolume4")),
                bid_price_5=to_float(row.get("BidPrice5")),
                bid_volume_5=to_float(row.get("BidVolume5")),

                # 卖一到卖五
                ask_price_1=to_float(row.get("AskPrice1")),
                ask_volume_1=to_float(row.get("AskVolume1")),
                ask_price_2=to_float(row.get("AskPrice2")),
                ask_volume_2=to_float(row.get("AskVolume2")),
                ask_price_3=to_float(row.get("AskPrice3")),
                ask_volume_3=to_float(row.get("AskVolume3")),
                ask_price_4=to_float(row.get("AskPrice4")),
                ask_volume_4=to_float(row.get("AskVolume4")),
                ask_price_5=to_float(row.get("AskPrice5")),
                ask_volume_5=to_float(row.get("AskVolume5")),
            )

            ticks.append(tick)

    return ticks


def delete_old_tick_data(symbol: str, exchange: Exchange) -> None:
    """
    删除旧 TickData。

    这个函数是为了防止你上一次导入了前 5000 条，
    现在重新导入时重复。

    如果你的 vn.py 数据库接口不支持 delete_tick_data，
    这里会自动跳过，不影响后续导入。
    """

    database = get_database()

    if not hasattr(database, "delete_tick_data"):
        print("当前数据库接口没有 delete_tick_data 方法，跳过旧数据删除")
        return

    try:
        count = database.delete_tick_data(symbol, exchange)
        print(f"已删除旧 TickData：{symbol}.{exchange.value}，数量：{count}")
    except Exception as e:
        print(f"删除旧 TickData 失败，继续执行导入。原因：{e}")


def save_ticks_to_database(ticks: list[TickData], batch_size: int = 5000) -> None:
    """
    分批写入 vn.py 数据库。

    如果全局配置 database.name 是 mongodb，
    这里就会写入 MongoDB。
    """

    database = get_database()

    total = len(ticks)

    if total == 0:
        print("没有 TickData 可以写入")
        return

    print(f"准备写入 TickData 数量：{total}")

    for start in range(0, total, batch_size):
        batch = ticks[start:start + batch_size]
        database.save_tick_data(batch)

        print(f"已写入：{start + len(batch)} / {total}")

    print("全部写入完成")


def main() -> None:
    file_path = r"C:\Users\ultra\Desktop\20250303\bu2505.csv"

    if not Path(file_path).exists():
        print(f"文件不存在：{file_path}")
        return

    ticks = load_shfe_level2_csv(file_path)

    if not ticks:
        print("CSV 中没有读取到 TickData")
        return

    print("CSV 读取完成")
    print("第一条：", ticks[0].vt_symbol, ticks[0].datetime, ticks[0].last_price)
    print("最后一条：", ticks[-1].vt_symbol, ticks[-1].datetime, ticks[-1].last_price)

    symbol = ticks[0].symbol
    exchange = ticks[0].exchange

    # 重新导入前，先尝试删除旧数据，避免刚才写入的 5000 条造成重复
    delete_old_tick_data(symbol, exchange)

    save_ticks_to_database(ticks)


if __name__ == "__main__":
    main()