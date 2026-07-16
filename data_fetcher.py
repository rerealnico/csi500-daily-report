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
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED, TimeoutError as _TimeoutError
from pathlib import Path
from config import CSI500_INDEX_CODE, DATA_DIR, KLINE_CACHE_FILE, CACHE_CONFIG

# 单只股票 baostock 查询超时（秒），防止个别退市/异常股票无限挂起
_STOCK_TIMEOUT = 30


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


def _fetch_single_bs_klines(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """单只股票日线行情（独立login/query/logout，自带超时保护）"""
    bs_code = _to_bs_code(symbol)
    lg = bs.login()
    if lg.error_code != "0":
        return None
    try:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount,turn,pctChg,peTTM,pbMRQ",
            start_date=start, end_date=end,
            frequency="d", adjustflag="3",
        )
        rows = []
        while rs.next():
            rows.append(dict(zip(rs.fields, rs.get_row_data())))
    finally:
        bs.logout()

    if not rows:
        return None

    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg", "peTTM", "pbMRQ"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.rename(columns={
        "peTTM": "pe", "pbMRQ": "pb",
        "turn": "turnover", "pctChg": "pct_chg",
    })
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = symbol
    return df


def fetch_daily_klines(symbols: list[str], end_date: str = None, years: int = 2) -> pd.DataFrame:
    """
    批量获取个股日线行情（baostock，含PE/PB）— 串行拉取避免并发封IP
    - 有缓存 → 增量拉取（只补最新数据）
    - 无缓存 → 全量拉取 years 年
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    # 尝试加载缓存
    cached_df = None
    if KLINE_CACHE_FILE.exists():
        # 检查缓存是否过期
        mtime = datetime.fromtimestamp(Path(KLINE_CACHE_FILE).stat().st_mtime)
        age_hours = (datetime.now() - mtime).total_seconds() / 3600
        if age_hours > CACHE_CONFIG["kline_max_age_hours"]:
            print(f"  [缓存] 缓存已过期 ({age_hours:.0f}小时 > {CACHE_CONFIG['kline_max_age_hours']}小时)，全量刷新")
        else:
            print(f"[数据获取] 发现缓存文件，尝试增量更新...")
            try:
                cached_df = pd.read_parquet(KLINE_CACHE_FILE)
                print(f"  [OK] 缓存包含 {cached_df['symbol'].nunique()} 只股票, {len(cached_df)} 条记录")
            except Exception as e:
                print(f"  [WARN] 缓存文件读取失败: {e}，重新全量拉取")
                cached_df = None

    if cached_df is not None and not cached_df.empty:
        # 检查缓存是否覆盖了所有请求的股票
        cached_symbols = set(cached_df["symbol"].unique())
        requested_symbols = set(symbols)
        if not requested_symbols.issubset(cached_symbols):
            missing = len(requested_symbols - cached_symbols)
            print(f"  [缓存] 缓存缺 {missing} 只股票，自动切换全量模式")
            cached_df = None  # 回退全量（让下面的else处理）

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

    all_dfs = []
    fail_count = 0
    total = len(symbols)

    pool = ProcessPoolExecutor(max_workers=3)
    futures = {}
    idx = 0
    completed = 0

    # 初始批次——3个worker并行
    while idx < total and len(futures) < 3:
        futures[pool.submit(_fetch_single_bs_klines, symbols[idx], start, end)] = symbols[idx]
        idx += 1

    try:
        while futures:
            done, pending = wait(futures, return_when=FIRST_COMPLETED, timeout=_STOCK_TIMEOUT)

            if not done:
                # 3个worker全部挂起（极低概率），跳过剩余
                for f in pending:
                    sym = futures[f]
                    print(f"  [WARN] {sym} 超时（>{_STOCK_TIMEOUT}s），已跳过")
                    fail_count += 1
                    completed += 1
                break

            for f in done:
                sym = futures.pop(f)
                completed += 1
                try:
                    df = f.result()  # 已完成，无需wait
                    if df is not None and not df.empty:
                        all_dfs.append(df)
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    print(f"  [WARN] {sym} 异常: {e}")

                if completed % 50 == 0 or completed == total:
                    print(f"  [进度] {completed}/{total} (失败: {fail_count})")

            # 补充新任务，保持3并发
            while idx < total and len(futures) < 3:
                futures[pool.submit(_fetch_single_bs_klines, symbols[idx], start, end)] = symbols[idx]
                idx += 1

            time.sleep(0.05)
    finally:
        pool.shutdown(wait=False)

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
