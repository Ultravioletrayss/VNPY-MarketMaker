import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from vnpy.trader.constant import Exchange
from vnpy.trader.object import TickData
from vnpy.trader.database import get_database


CHINA_TZ = ZoneInfo("Asia/Shanghai")

# 改成完整 CSV 文件路径
CSV_FILE_PATH = r"C:\Users\ultra\Desktop\CSV_DATA\RB2505.03.csv"

# 只导入 RB / FU，避免误导入其他品种
ALLOWED_PREFIXES = ("RB", "FU")

# RB / FU 都是上期所
TARGET_EXCHANGE = Exchange.SHFE


def to_float(value, default: float = 0.0) -> float:
    """安全转换 float，空值/异常值返回默认值。"""
    if value is None:
        return default

    value = str(value).strip()

    if value == "":
        return default

    try:
        return float(value)
    except ValueError:
        return default


def to_symbol(value: str) -> str:
    """
    把 CSV 里的 Symbol 转成 vn.py 常用格式。

    例如：
        RB2505 -> rb2505
        FU2505 -> fu2505
    """
    return str(value).strip().lower()


def detect_delimiter(file_path: str) -> str:
    """判断 CSV 是逗号分隔还是制表符分隔。"""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()

    if "\t" in first_line:
        return "\t"

    return ","


def open_csv_reader(file_path: str):
    """
    打开 CSV 文件。

    优先 utf-8-sig，如果失败再用 gbk。
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


def parse_datetime(row: dict) -> datetime:
    """
    解析 TradingTime。

    你的新 CSV 是：
        TradingTime = 2025.02.28T20:59:00.500
        TradingDate = 2025.03.03

    TradingTime 已经包含真实自然日期和时间，
    所以直接用 TradingTime 作为 TickData.datetime。
    """

    trading_time = str(row["TradingTime"]).strip()

    # 兼容偶尔出现的空格
    trading_time = trading_time.replace(" ", "")

    dt = datetime.strptime(trading_time, "%Y.%m.%dT%H:%M:%S.%f")

    return dt.replace(tzinfo=CHINA_TZ)


def is_allowed_symbol(raw_symbol: str) -> bool:
    """
    只允许 RB / FU 开头的合约。
    """
    raw_symbol = str(raw_symbol).strip().upper()
    return raw_symbol.startswith(ALLOWED_PREFIXES)


def collect_symbols_from_csv(file_path: str) -> set[str]:
    """
    先扫一遍 CSV，收集本文件里出现的 rb/fu 合约代码。

    删除旧数据时只删这些 symbol，避免删到 bu2505。
    """

    symbols: set[str] = set()

    f, reader = open_csv_reader(file_path)

    with f:
        for row in reader:
            raw_symbol = str(row["Symbol"]).strip()

            if not is_allowed_symbol(raw_symbol):
                continue

            symbols.add(to_symbol(raw_symbol))

    return symbols


def delete_old_tick_data(symbols: set[str]) -> None:
    """
    只删除 symbols 里面的旧 TickData。

    例如：
        rb2505.SHFE
        fu2505.SHFE

    不会删除：
        bu2505.SHFE
    """

    database = get_database()

    if not hasattr(database, "delete_tick_data"):
        print("当前数据库接口没有 delete_tick_data 方法，跳过旧数据删除")
        return

    for symbol in sorted(symbols):
        try:
            count = database.delete_tick_data(symbol, TARGET_EXCHANGE)
            print(f"已删除旧 TickData：{symbol}.{TARGET_EXCHANGE.value}，数量：{count}")
        except Exception as e:
            print(f"删除旧 TickData 失败：{symbol}.{TARGET_EXCHANGE.value}，原因：{e}")


def row_to_tick(row: dict) -> TickData | None:
    """
    把 CSV 的一行转换成 vn.py TickData。
    """

    raw_symbol = str(row["Symbol"]).strip()

    if not is_allowed_symbol(raw_symbol):
        return None

    symbol = to_symbol(raw_symbol)
    dt = parse_datetime(row)

    tick = TickData(
        symbol=symbol,
        exchange=TARGET_EXCHANGE,
        datetime=dt,
        gateway_name="DB",

        name=str(row.get("ShortName", "")).strip(),

        # 最新行情与成交统计
        last_price=to_float(row.get("LastPrice")),
        last_volume=to_float(row.get("TradeVolume")),
        volume=to_float(row.get("TotalVolume")),
        turnover=to_float(row.get("TotalAmount")),
        open_interest=to_float(row.get("TotalPosition")),

        # 日内价格统计
        open_price=to_float(row.get("OpenPrice")),
        high_price=to_float(row.get("HighPrice")),
        low_price=to_float(row.get("LowPrice")),
        pre_close=to_float(row.get("PreClosePrice")),

        # 涨跌停
        limit_up=to_float(row.get("PriceUpLimit")),
        limit_down=to_float(row.get("PriceDownLimit")),

        # 买一到买五
        bid_price_1=to_float(row.get("BuyPrice01")),
        bid_volume_1=to_float(row.get("BuyVolume01")),
        bid_price_2=to_float(row.get("BuyPrice02")),
        bid_volume_2=to_float(row.get("BuyVolume02")),
        bid_price_3=to_float(row.get("BuyPrice03")),
        bid_volume_3=to_float(row.get("BuyVolume03")),
        bid_price_4=to_float(row.get("BuyPrice04")),
        bid_volume_4=to_float(row.get("BuyVolume04")),
        bid_price_5=to_float(row.get("BuyPrice05")),
        bid_volume_5=to_float(row.get("BuyVolume05")),

        # 卖一到卖五
        ask_price_1=to_float(row.get("SellPrice01")),
        ask_volume_1=to_float(row.get("SellVolume01")),
        ask_price_2=to_float(row.get("SellPrice02")),
        ask_volume_2=to_float(row.get("SellVolume02")),
        ask_price_3=to_float(row.get("SellPrice03")),
        ask_volume_3=to_float(row.get("SellVolume03")),
        ask_price_4=to_float(row.get("SellPrice04")),
        ask_volume_4=to_float(row.get("SellVolume04")),
        ask_price_5=to_float(row.get("SellPrice05")),
        ask_volume_5=to_float(row.get("SellVolume05")),
    )

    return tick


def save_csv_to_database(file_path: str, batch_size: int = 5000) -> None:
    """
    流式读取 CSV，分批写入 MongoDB。

    不一次性把整个月数据全部塞进内存，适合大文件。
    """

    database = get_database()

    f, reader = open_csv_reader(file_path)

    batch: list[TickData] = []
    total_count = 0

    first_tick: TickData | None = None
    last_tick: TickData | None = None

    with f:
        for row in reader:
            tick = row_to_tick(row)

            if tick is None:
                continue

            if first_tick is None:
                first_tick = tick

            last_tick = tick

            batch.append(tick)
            total_count += 1

            if len(batch) >= batch_size:
                database.save_tick_data(batch)
                print(f"已写入：{total_count}")
                batch.clear()

        if batch:
            database.save_tick_data(batch)
            print(f"已写入：{total_count}")
            batch.clear()

    if first_tick:
        print("第一条：", first_tick.vt_symbol, first_tick.datetime, first_tick.last_price)

    if last_tick:
        print("最后一条：", last_tick.vt_symbol, last_tick.datetime, last_tick.last_price)

    print(f"全部写入完成，总数量：{total_count}")


def main() -> None:
    file_path = CSV_FILE_PATH

    if not Path(file_path).exists():
        print(f"文件不存在：{file_path}")
        return

    print("开始扫描 CSV 中的 RB/FU 合约...")
    symbols = collect_symbols_from_csv(file_path)

    if not symbols:
        print("CSV 里没有发现 RB/FU 开头的合约")
        return

    print("本次将导入以下合约：")
    for symbol in sorted(symbols):
        print(f"  {symbol}.{TARGET_EXCHANGE.value}")

    print("开始删除这些合约的旧 TickData，不会删除其他品种...")
    delete_old_tick_data(symbols)

    print("开始写入新 TickData...")
    save_csv_to_database(file_path)


if __name__ == "__main__":
    main()