"""
拉取沪深300股票K线数据（3年）并合并到现有缓存
直接使用 baostock，绕过 fetch_daily_klines 的缓存跳过逻辑
"""
import sys, time, json
sys.path.insert(0, '.')
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from data_fetcher import fetch_hs300_constituents, _fetch_single_bs_klines
from config import DATA_DIR, STATIC_DATA_DIR, CACHE_VERSION, KLINE_CACHE_FILE


def main():
    YEARS = 3
    END_DATE = time.strftime("%Y-%m-%d")
    YEAR_NUM = int(time.strftime("%Y"))
    START_DATE = f"{YEAR_NUM - YEARS}-{time.strftime('%m-%d')}"

    # 1. 获取 HS300 成分股
    print("获取沪深300成分股...")
    hs300 = fetch_hs300_constituents()
    symbols = hs300["symbol"].tolist()
    print(f"  HS300: {len(symbols)} 只")

    # 2. 检查已有缓存，找出缺失的股票
    print("\n检查已有缓存...")
    if KLINE_CACHE_FILE.exists():
        old = pd.read_parquet(KLINE_CACHE_FILE)
        old["symbol"] = old["symbol"].astype(str).str.zfill(6)
        existing_symbols = set(old["symbol"].unique())
        new_symbols = [s for s in symbols if s not in existing_symbols]
        print(f"  现有缓存: {len(existing_symbols)} 只, 待拉: {len(new_symbols)} 只")
        if not new_symbols:
            print("全部已有，无需拉取")
            return
        symbols = new_symbols
    else:
        print("  无现有缓存")

    # 3. 拉取 K 线（使用和 data_fetcher 相同的方式）
    print(f"\n开始拉取 {len(symbols)} 只 HS300 股票 K 线（{START_DATE} ~ {END_DATE}）...")
    start = START_DATE
    end = END_DATE

    all_dfs = []
    fail_count = 0
    total = len(symbols)

    pool = ProcessPoolExecutor(max_workers=3)
    futures = {}
    idx = 0
    completed = 0

    # 初始批次
    while idx < total and len(futures) < 3:
        futures[pool.submit(_fetch_single_bs_klines, symbols[idx], start, end)] = symbols[idx]
        idx += 1

    try:
        while futures:
            done, pending = wait(futures, return_when=FIRST_COMPLETED, timeout=300)
            if not done:
                print(f"  [超时] 3个工作进程全部挂起，跳过剩余 {len(futures)} 只")
                for f in pending:
                    sym = futures[f]
                    print(f"    - {sym} 超时跳过")
                break

            for f in done:
                sym = futures.pop(f)
                try:
                    result = f.result()
                    if result is not None and not result.empty:
                        all_dfs.append(result)
                        completed += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    print(f"  [FAIL] {sym}: {e}")

                # 提交新任务
                if idx < total:
                    futures[pool.submit(_fetch_single_bs_klines, symbols[idx], start, end)] = symbols[idx]
                    idx += 1

            progress = completed + fail_count
            if progress % 20 == 0 or progress == total:
                print(f"  进度: {completed}/{total} 成功, {fail_count} 失败")
    finally:
        pool.shutdown(wait=False)

    if not all_dfs:
        print("拉取失败，无数据返回")
        sys.exit(1)

    klines = pd.concat(all_dfs, ignore_index=True)
    print(f"\n新拉取: {len(klines)} 条, {klines['symbol'].nunique()} 只")

    # 4. 合并到现有缓存
    if KLINE_CACHE_FILE.exists():
        old_df = pd.read_parquet(KLINE_CACHE_FILE)
        old_df["symbol"] = old_df["symbol"].astype(str).str.zfill(6)
        merged = pd.concat([old_df, klines], ignore_index=True).drop_duplicates(
            subset=["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
    else:
        merged = klines

    print(f"合并后: {len(merged)} 条, {merged['symbol'].nunique()} 只")

    # 5. 保存到 data/ 缓存
    merged.to_parquet(KLINE_CACHE_FILE, index=False)
    print(f"已保存: {KLINE_CACHE_FILE}")

    # 6. 同时更新静态基线
    static_file = STATIC_DATA_DIR / "klines_base.parquet"
    merged.to_parquet(static_file, index=False)
    print(f"已保存: {static_file}")

    # 7. 更新 cache_meta
    meta = {"kline_version": CACHE_VERSION, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "stock_count": int(merged["symbol"].nunique()), "row_count": int(len(merged))}
    Path(DATA_DIR / "cache_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    print(f"缓存元数据已更新")

    print(f"\n完成! 总计 {merged['symbol'].nunique()} 只股票, {len(merged)} 条记录")


if __name__ == '__main__':
    main()
