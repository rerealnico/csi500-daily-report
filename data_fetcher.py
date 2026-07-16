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
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CSI500_INDEX_CODE, DATA_DIR, KLINE_CACHE_FILE


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


def fetch_daily_klines(symbols: list[str], end_date: str = None, years: int = 2, max_workers: int = 10) -> pd.DataFrame:
    """
    WARNING: 批量获取个股日线行情（baostock，含PE/PB）
    - 有缓存 → 增量拉取（只补最新数据）
    - 无缓存 → 全量拉取 years 年
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    # 尝试加载缓存
    cached_df = None
    if KLINE_CACHE_FILE.exists():
        print(f"[数据获取] 发现缓存文件，尝试增量更新...")
        try:
            cached_df = pd.read_parquet(KLINE_CACHE_FILE)
            print(f"  [OK] 缓存包含 {cached_df['symbol'].nunique()} 只股票, {len(cached_df)} 条记录")
        except Exception as e:
            print(f"  [WARN] 缓存文件读取失败: {e}，重新全量拉取")
            cached_df = None

    if cached_df is not None and not cached_df.empty:
        # 增量模式：只拉缓存中最新日期之后的数据
        max_cached_date = cached_df["date"].max()
        start = (max_cached_date + timedelta(days=1)).strftime("%Y-%m-%d")
        end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        print(f"  [增量] 缓存截止 {max_cached_date.strftime('%Y-%m-%d')}，只拉 {start} 之后的数据")
        is_incremental = True
    else:
        # 全量模式
        start_date = (datetime.strptime(end_date, "%Y%m%d") -
                      timedelta(days=years * 365 + 50)).strftime("%Y%m%d")
        start = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"
        print(f"[数据获取] 全量拉取 {len(symbols)} 只股票（{start} ~ {end}）...")
        is_incremental = False

    lg = bs.login()
    if lg.error_code != "0":
        raise ConnectionError(f"baostock 登录失败: {lg.error_msg}")

    all_dfs = []
    fail_count = 0
    total = len(symbols)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_fetch_single_bs_klines, symbol, start, end): symbol
                for symbol in symbols
            }
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                symbol = futures[future]
                try:
                    df = future.result()
                    if df is not None and not df.empty:
                        all_dfs.append(df)
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    print(f"  [WARN] {symbol} 线程异常: {e}")

                if done_count % 50 == 0 or done_count == total:
                    print(f"  [进度] {done_count}/{total} (失败: {fail_count})")
    finally:
        bs.logout()

    if not all_dfs and cached_df is None:
        raise ValueError("未获取到任何股票数据")

    # 合并新旧数据
    if is_incremental and cached_df is not None:
        new_df = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
        if not new_df.empty:
            # 去重：按 symbol + date 去重，保留新的
            combined = pd.concat([cached_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["symbol", "date"], keep="last")
            combined = combined.sort_values(["symbol", "date"]).reset_index(drop=True)
            result = combined
            print(f"  [OK] 增量更新完成: 新增 {len(new_df)} 条，总计 {len(result)} 条")
        else:
            result = cached_df
            print(f"  [OK] 无新数据，使用缓存（{len(result)} 条）")
    else:
        result = pd.concat(all_dfs, ignore_index=True)
        print(f"  [OK] 全量拉取完成: {result['symbol'].nunique()} 只股票, {len(result)} 条记录")

    # 保存缓存
    try:
        result.to_parquet(KLINE_CACHE_FILE, index=False)
        print(f"  [缓存] 已保存 {len(result)} 条到 {KLINE_CACHE_FILE.name}")
    except Exception as e:
        print(f"  [WARN] 缓存保存失败: {e}")

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
