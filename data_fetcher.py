"""
数据获取模块
- 成分股: akshare（中证指数官网，正常可用）
- 日线行情 + PE/PB: baostock（更稳定，免费）
"""
import time
import pandas as pd
import akshare as ak
import baostock as bs
from datetime import datetime, timedelta
from config import CSI500_INDEX_CODE, DATA_DIR


# ========== 成分股获取（akshare） ==========

def fetch_csi500_constituents() -> pd.DataFrame:
    """
    获取中证500最新成分股列表
    返回: DataFrame 包含 stock_code, stock_name, weight, symbol
    """
    print("[数据获取] 正在拉取中证500成分股列表...")
    try:
        df = ak.index_stock_cons_weight_csindex(symbol=CSI500_INDEX_CODE)
        df = df.rename(columns={
            "成分券代码": "stock_code",
            "成分券名称": "stock_name",
            "权重": "weight"
        })
        df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
        df["symbol"] = df["stock_code"]
        print(f"  [OK] 获取到 {len(df)} 只成分股")
        df.to_csv(DATA_DIR / "csi500_constituents.csv", index=False, encoding="utf-8")
        return df
    except Exception as e:
        print(f"  [ERROR] 拉取成分股失败: {e}")
        cache_file = DATA_DIR / "csi500_constituents.csv"
        if cache_file.exists():
            print("  [WARN] 使用本地缓存数据")
            return pd.read_csv(cache_file, dtype={"stock_code": str})
        raise


# ========== 工具函数 ==========

def _to_bs_code(code: str) -> str:
    """6位股票代码转 baostock 格式：sz.000001 / sh.600000"""
    if code.startswith("6") or code.startswith("9"):
        return f"sh.{code}"
    else:
        return f"sz.{code}"


# ========== 日线行情获取（baostock） ==========

def _fetch_single_bs_klines(
    symbol: str, start_date: str, end_date: str
) -> pd.DataFrame:
    """通过 baostock 获取单只股票日线（含 PE/PB），无惧限流"""
    bs_code = _to_bs_code(symbol)
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,close,high,low,volume,amount,turn,pctChg,peTTM,pbMRQ",
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag="2"
        )
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=[
            "date", "open", "close", "high", "low",
            "volume", "amount", "turnover", "pct_chg", "pe", "pb"
        ])
        df["symbol"] = symbol
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "close", "high", "low", "volume",
                    "amount", "turnover", "pct_chg", "pe", "pb"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        print(f"  [WARN] {symbol} 获取失败: {e}")
        return pd.DataFrame()


def fetch_daily_klines(symbols: list[str], end_date: str = None, years: int = 5) -> pd.DataFrame:
    """
    批量获取个股日线行情（baostock，含PE/PB）
    500只股票约需 3~5 分钟
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    start_date = (datetime.strptime(end_date, "%Y%m%d") -
                  timedelta(days=years * 365 + 50)).strftime("%Y%m%d")

    # baostock 日期格式 yyyy-mm-dd
    start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
    end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    all_dfs = []
    total = len(symbols)
    fail_count = 0

    print(f"[数据获取] 正在拉取 {total} 只股票的日线行情（baostock）...")

    lg = bs.login()
    if lg.error_code != "0":
        raise ConnectionError(f"baostock 登录失败: {lg.error_msg}")

    try:
        for i, symbol in enumerate(symbols):
            df = _fetch_single_bs_klines(symbol, start, end)
            if df is not None and not df.empty:
                all_dfs.append(df)
            else:
                fail_count += 1

            if (i + 1) % 50 == 0 or (i + 1) == total:
                print(f"  [进度] {i+1}/{total} (失败: {fail_count})")
    finally:
        bs.logout()

    if not all_dfs:
        raise ValueError("未获取到任何股票数据")

    result = pd.concat(all_dfs, ignore_index=True)
    print(f"  [OK] 成功获取 {result['symbol'].nunique()} 只股票，{fail_count} 只失败")
    return result


# ========== 财务指标（已含在日线中） ==========

def fetch_financial_indicators(symbols: list[str]) -> pd.DataFrame:
    """PE/PB 已随日线行情获取，无需单独查询"""
    print("  [INFO] PE/PB 已随日线获取，跳过单独查询")
    return pd.DataFrame()


# ========== 日期工具 ==========

def fetch_latest_trade_date() -> str:
    """获取最近交易日"""
    today = datetime.now()
    if today.weekday() == 5:
        delta = 1
    elif today.weekday() == 6:
        delta = 2
    else:
        delta = 1
    last_date = today - timedelta(days=delta)
    return last_date.strftime("%Y%m%d")


if __name__ == "__main__":
    constituents = fetch_csi500_constituents()
    print(constituents.head())

    symbols = constituents["symbol"].tolist()[:3]
    klines = fetch_daily_klines(symbols)
    print(klines.tail())
    print("\n列名:", klines.columns.tolist())
