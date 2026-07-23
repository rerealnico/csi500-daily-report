"""生成基本面静态数据（使用缓存成分股，跳过akshare）"""
import sys, time, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from pathlib import Path
from config import DATA_DIR, FUNDAMENTAL_CONFIG
from fundamental_analyzer import fetch_fundamentals, STATIC_FUNDA_DIR


def main():
    # 使用缓存的成分股列表（CSI500 + HS300 合并）
    csi500_path = DATA_DIR / "csi500_constituents.csv"
    hs300_path = DATA_DIR / "hs300_constituents.csv"
    
    parts = []
    for path, name in [(csi500_path, "中证500"), (hs300_path, "沪深300")]:
        if not path.exists():
            print(f"警告: {name} 缓存文件不存在 ({path.name})")
            continue
        df = pd.read_csv(path, dtype={"stock_code": str})
        df["symbol"] = df["symbol"].astype(str).str.zfill(6)
        parts.append(df)
        print(f"{name}: {len(df)} 只")
    
    if not parts:
        print("错误: 无缓存成分股文件，请先运行 main.py --test 生成")
        sys.exit(1)
    
    constituents = pd.concat(parts, ignore_index=True).drop_duplicates(subset="symbol").reset_index(drop=True)
    symbols = constituents["symbol"].tolist()
    print(f"合并去重后: {len(symbols)} 只股票")

    # 创建静态数据目录
    STATIC_FUNDA_DIR.mkdir(exist_ok=True)

    # 删除旧的运行时缓存，强制从 baostock 全量获取
    funda_cache = DATA_DIR / "fundamentals.parquet"
    if funda_cache.exists():
        funda_cache.unlink()
        print("已删除旧缓存，将强制全量拉取")

    # 获取基本面数据
    t0 = time.time()
    df = fetch_fundamentals(symbols)
    elapsed = time.time() - t0

    success = len(df[df["has_data"]])
    total = len(df)
    print(f"\n结果: {success}/{total} 成功 ({success/total*100:.1f}%)")
    print(f"耗时: {elapsed:.0f} 秒")

    # 保存静态数据
    year = FUNDAMENTAL_CONFIG["year"]
    quarter = FUNDAMENTAL_CONFIG["quarter"]
    output_file = STATIC_FUNDA_DIR / f"fundamentals_{year}_q{quarter}.parquet"
    df.to_parquet(output_file, index=False)
    print(f"\n已保存: {output_file}")
    print(f"大小: {output_file.stat().st_size / 1024:.0f} KB")


if __name__ == '__main__':
    main()
