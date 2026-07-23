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
from config import CSI500_INDEX_CODE, HS300_INDEX_CODE, DATA_DIR, KLINE_CACHE_FILE, CACHE_CONFIG
from config import CACHE_META_FILE, CACHE_VERSION, STATIC_DATA_DIR
from config import HS300_CACHE_FILE, CSI500_CACHE_FILE

# 单只股票 baostock 查询超时（秒），防止个别退市/异常股票无限挂起
_STOCK_TIMEOUT = 30


# ========== 缓存版本校验 ==========

def _check_cache_version() -> bool:
    """检查缓存版本是否匹配，不匹配时返回False触发全量刷新"""
    if not CACHE_META_FILE.exists():
        return False
    try:
        import json
        meta = json.loads(CACHE_META_FILE.read_text(encoding="utf-8"))
        stored = meta.get("kline_version", "")
        if stored == CACHE_VERSION:
            return True
        print(f"  [缓存] 版本不匹配: 缓存={stored}, 当前={CACHE_VERSION}，全量刷新")
        return False
    except Exception as e:
        print(f"  [缓存] 元数据读取失败: {e}，全量刷新")
        return False


def _save_cache_version():
    """保存当前缓存版本标识"""
    import json
    meta = {"kline_version": CACHE_VERSION, "updated_at": datetime.now().isoformat()}
    try:
        CACHE_META_FILE.parent.mkdir(exist_ok=True)
        CACHE_META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  [WARN] 缓存元数据保存失败: {e}")

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
        df.to_csv(CSI500_CACHE_FILE, index=False, encoding="utf-8")
        return df
    except Exception as e:
        print(f"  [ERROR] 拉取成分股失败: {e}")
        cache_file = CSI500_CACHE_FILE
        if cache_file.exists():
            print("  [WARN] 使用本地缓存数据")
            return pd.read_csv(cache_file, dtype={"stock_code": str})
        raise


def fetch_hs300_constituents() -> pd.DataFrame:
    """
    获取沪深300最新成分股列表
    返回: DataFrame 包含 stock_code, stock_name, weight, symbol
    """
    print("[数据获取] 正在拉取沪深300成分股列表...")
    try:
        df = ak.index_stock_cons_weight_csindex(symbol=HS300_INDEX_CODE)
        df = df.rename(columns={
            "成分券代码": "stock_code",
            "成分券名称": "stock_name",
            "权重": "weight"
        })
        df["stock_code"] = df["stock_code"].astype(str).str.zfill(6)
        df["symbol"] = df["stock_code"]
        print(f"  [OK] 获取到 {len(df)} 只成分股")
        df.to_csv(HS300_CACHE_FILE, index=False, encoding="utf-8")
        return df
    except Exception as e:
        print(f"  [ERROR] 拉取成分股失败: {e}")
        cache_file = HS300_CACHE_FILE
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


def _batch_fetch_klines(symbols: list[str], start: str, end: str) -> tuple[list[pd.DataFrame], int]:
    """
    批量拉取K线数据（多进程，3并发）
    返回: (dataframe列表, 失败数)
    """
    if not symbols:
        return [], 0

    all_dfs = []
    fail_count = 0
    total = len(symbols)
    completed = 0

    pool = ProcessPoolExecutor(max_workers=3)
    futures = {}
    idx = 0

    # 初始批次
    while idx < total and len(futures) < 3:
        futures[pool.submit(_fetch_single_bs_klines, symbols[idx], start, end)] = symbols[idx]
        idx += 1

    try:
        while futures:
            done, pending = wait(futures, return_when=FIRST_COMPLETED, timeout=_STOCK_TIMEOUT)

            if not done:
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
                    df = f.result()
                    if df is not None and not df.empty:
                        all_dfs.append(df)
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    print(f"  [WARN] {sym} 异常: {e}")

                if completed % 50 == 0 or completed == total:
                    print(f"  [进度] {completed}/{total} (失败: {fail_count})")

            while idx < total and len(futures) < 3:
                futures[pool.submit(_fetch_single_bs_klines, symbols[idx], start, end)] = symbols[idx]
                idx += 1

            time.sleep(0.05)
    finally:
        pool.shutdown(wait=False)

    return all_dfs, fail_count


def fetch_daily_klines(symbols: list[str], end_date: str = None, years: int = 2) -> pd.DataFrame:
    """
    批量获取个股日线行情（baostock，含PE/PB）
    - 有缓存 → 增量拉取（只补最新数据）
    - 无缓存 → 全量拉取 years 年
    - 缓存缺部分股票 → 缓存部分增量，缺失部分全量拉取
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")

    # === Phase 0: 加载缓存 ===
    cached_df = None
    if KLINE_CACHE_FILE.exists():
        version_ok = _check_cache_version()
        if not version_ok:
            print(f"  [缓存] 版本不匹配，忽略旧缓存，全量刷新")
            cached_df = None
        else:
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

    # 缓存不存在时，尝试从静态基线加载
    if cached_df is None:
        static_kline_file = STATIC_DATA_DIR / "klines_base.parquet"
        if static_kline_file.exists():
            try:
                cached_df = pd.read_parquet(static_kline_file)
                cached_df["symbol"] = cached_df["symbol"].astype(str).str.zfill(6)
                print(f"  [静态基线] 加载静态行情基线: {cached_df['symbol'].nunique()} 只股票, {len(cached_df)} 条")
            except Exception as e:
                print(f"  [WARN] 静态基线加载失败: {e}")
                cached_df = None

    # === Phase 1: 检查缓存覆盖范围，分离缺失股票 ===
    missing_symbols = []
    if cached_df is not None and not cached_df.empty:
        cached_df["symbol"] = cached_df["symbol"].astype(str).str.zfill(6)
        cached_symbols = set(cached_df["symbol"].unique())
        symbols = [str(s).zfill(6) for s in symbols]
        requested_symbols = set(symbols)
        missing_symbols = sorted(requested_symbols - cached_symbols)
        if missing_symbols:
            print(f"  [缓存] 缓存缺 {len(missing_symbols)} 只股票，将单独全量拉取")
        symbols = sorted(cached_symbols & requested_symbols)

    # 预计算全量日期范围（缺失股票或无缓存时使用）
    start_full_date = (datetime.strptime(end_date, "%Y%m%d") -
                       timedelta(days=years * 365 + 50)).strftime("%Y%m%d")
    full_start = f"{start_full_date[:4]}-{start_full_date[4:6]}-{start_full_date[6:]}"
    full_end = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

    result = None

    # === Phase 2: 增量更新缓存中的股票 ===
    if cached_df is not None and not cached_df.empty and symbols:
        max_cached_date = cached_df["date"].max()
        inc_start = (max_cached_date + timedelta(days=1)).strftime("%Y-%m-%d")
        inc_end = datetime.strptime(end_date, "%Y%m%d").strftime("%Y-%m-%d")

        if inc_start > inc_end:
            # 短路：缓存已是最新，无需拉取
            print(f"  [缓存] 缓存已是最新（截止 {max_cached_date.strftime('%Y-%m-%d')}），跳过增量更新")
            result = cached_df
        else:
            print(f"  [增量] 缓存截止 {max_cached_date.strftime('%Y-%m-%d')}，只拉 {inc_start} 之后的数据")
            all_dfs, _ = _batch_fetch_klines(symbols, inc_start, inc_end)
            if all_dfs:
                new_df = pd.concat(all_dfs, ignore_index=True)
                result = pd.concat([cached_df, new_df], ignore_index=True)
                result = result.drop_duplicates(subset=["symbol", "date"], keep="last")
                result = result.sort_values(["symbol", "date"]).reset_index(drop=True)
                print(f"  [OK] 增量更新完成: 新增 {len(new_df)} 条，总计 {len(result)} 条")
            else:
                result = cached_df
                print(f"  [OK] 无新数据，使用缓存（{len(result)} 条）")

    # === Phase 3: 全量拉取缺失股票 ===
    if missing_symbols:
        print(f"  [缺失] 全量拉取 {len(missing_symbols)} 只缺失股票（{full_start} ~ {full_end}）...")
        miss_dfs, _ = _batch_fetch_klines(missing_symbols, full_start, full_end)

        if not miss_dfs:
            if result is not None:
                print(f"  [缺失] 缺失股票全量拉取全部失败，跳过")
            else:
                raise ValueError("未获取到任何股票数据")
        else:
            miss_result = pd.concat(miss_dfs, ignore_index=True)
            print(f"  [缺失] 拉取完成: {miss_result['symbol'].nunique()} 只, {len(miss_result)} 条")

            if result is not None:
                result = pd.concat([result, miss_result], ignore_index=True)
                result = result.drop_duplicates(subset=["symbol", "date"], keep="last")
                result = result.sort_values(["symbol", "date"]).reset_index(drop=True)
            else:
                result = miss_result

    # === Phase 4: 无缓存 — 全量拉取全部股票 ===
    if result is None:
        if not symbols:
            raise ValueError("未获取到任何股票数据")
        print(f"[数据获取] 全量拉取 {len(symbols)} 只股票（{full_start} ~ {full_end}）...")
        all_dfs, fail_count = _batch_fetch_klines(symbols, full_start, full_end)
        if not all_dfs:
            raise ValueError("未获取到任何股票数据")
        result = pd.concat(all_dfs, ignore_index=True)
        print(f"  [OK] 全量拉取完成: {result['symbol'].nunique()} 只股票, {len(result)} 条记录")

    # 保存缓存
    try:
        result["symbol"] = result["symbol"].astype(str).str.zfill(6)
        result.to_parquet(KLINE_CACHE_FILE, index=False)
        print(f"  [缓存] 已保存 {len(result)} 条到 {KLINE_CACHE_FILE.name}")
        _save_cache_version()
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
    weekday = today.weekday()
    if weekday == 0:  # 周一 → 上周五
        delta = 3
    elif weekday == 6:  # 周日 → 上周五
        delta = 2
    elif weekday == 5:  # 周六 → 周五
        delta = 1
    else:  # 周二~周五 → 前一天
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
