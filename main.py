"""
主程序 - 中证500每日复盘分析系统 P0 版
一键运行：python main.py
"""
import io
import sys
# Windows 控制台 UTF-8 编码修复
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
import time
from datetime import datetime

from config import REPORT_CONFIG
from data_fetcher import (
    fetch_csi500_constituents,
    fetch_daily_klines,
    fetch_latest_trade_date,
)
from valuation_analyzer import calculate_valuation_scores
from volume_analyzer import calculate_volume_scores
from fundamental_analyzer import fetch_fundamentals, calculate_fundamental_scores
from scorer import calculate_final_scores, print_top_bottom
from reporter import generate_report, save_report
from visualizer import generate_all_charts
from notifier import push_report
from image_host import upload_images


def run_pipeline(max_stocks: int = None, test_mode: bool = False, cloud_mode: bool = False):
    """
    运行完整分析管线

    Parameters
    ----------
    max_stocks : int, optional
        最多分析的股票数
    test_mode : bool
        是否测试模式
    cloud_mode : bool
        云函数模式：跳过文件保存，仅推送
    """
    start_time = time.time()
    print("=" * 60)
    print(f"  CSI 500 每日复盘分析系统  v0.1 (P0)")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ===== Step 1: 获取成分股 =====
    print("\n[Step 1/7] 获取中证500成分股")
    constituents = fetch_csi500_constituents()

    if test_mode:
        # 测试模式只取前10只
        constituents = constituents.head(10)
        max_stocks = 10

    if max_stocks and max_stocks < len(constituents):
        constituents = constituents.head(max_stocks)

    symbols = constituents["symbol"].tolist()
    print(f"  本次分析 {len(symbols)} 只股票")

    # ===== Step 2: 获取行情数据 =====
    print(f"\n[Step 2/7] 获取日线行情数据")
    trade_date = fetch_latest_trade_date()
    klines = fetch_daily_klines(symbols, end_date=trade_date, years=5)

    # ===== Step 3: 获取基本面数据 =====
    print(f"\n[Step 3/7] 获取财务数据")
    fundamentals = fetch_fundamentals(symbols, year=2025, quarter=4)
    fundamental_scores = calculate_fundamental_scores(fundamentals)

    # ===== Step 4: 分析计算 =====
    print(f"\n[Step 4/7] 分析计算")

    # 4a. 估值分析（PE/PB 已内含在 klines 中）
    valuation_scores = calculate_valuation_scores(klines)

    # 4b. 量能分析
    volume_scores = calculate_volume_scores(klines)

    # 4c. 综合评分（含基本面因子）
    final_scores = calculate_final_scores(
        constituents, valuation_scores, volume_scores, fundamental_scores
    )

    # ===== Step 5: 输出报告 =====
    print(f"\n[Step 5/7] 生成报告")

    top_n = REPORT_CONFIG["top_n"]
    print_top_bottom(final_scores, top_n)

    # 生成文本报告
    top_stocks = final_scores.head(top_n).to_dict("records")
    bottom_stocks = final_scores.tail(top_n).iloc[::-1].to_dict("records")

    report_text = generate_report(
        constituents_count=len(final_scores),
        top_stocks=top_stocks,
        bottom_stocks=bottom_stocks,
        report_date=trade_date,
    )

    if not cloud_mode:
        save_report(report_text)

        # 生成可视化图表
        print(f"\n[Step 6/7] 生成可视化图表")
        chart_files = generate_all_charts(final_scores, klines)
        
        # 上传图表到图床，获取URL用于微信推送
        print(f"\n[图表上传] 上传到图床...")
        image_urls = upload_images(chart_files)
        if image_urls:
            print(f"  [OK] {len(image_urls)} 张图片已上传")
        else:
            print(f"  [INFO] 图床上传跳过，仅推送文本报告")
    else:
        print(f"\n[Step 6/7] 云函数模式：跳过本地文件保存")
        chart_files = None
        image_urls = None

    # ===== 推送报告到微信 =====
    push_report(report_text, report_date=trade_date, image_urls=image_urls)

    # ===== Step 7: 输出统计 =====
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  分析完成！耗时 {elapsed:.1f} 秒")
    print(f"  分析的股票数: {len(final_scores)}")
    print(f"  推荐关注: {top_n} 只")
    print(f"{'='*60}")

    return final_scores


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CSI 500 每日复盘分析")
    parser.add_argument(
        "--test", action="store_true", help="测试模式（只分析10只股票）"
    )
    parser.add_argument(
        "--max", type=int, default=None, help="最多分析的股票数"
    )
    parser.add_argument(
        "--diagnose", type=str, default=None, help="个股基本面诊断，如 --diagnose 000785"
    )
    parser.add_argument(
        "--setup-push", action="store_true", help="配置微信推送"
    )
    args = parser.parse_args()

    if args.setup_push:
        from notifier import setup_wizard
        setup_wizard()
    elif args.diagnose:
        from fundamental_analyzer import diagnose_stock, print_diagnosis
        diag = diagnose_stock(args.diagnose)
        print_diagnosis(diag)
    else:
        print("参数: test=%s, max=%s" % (args.test, args.max))
        run_pipeline(max_stocks=args.max, test_mode=args.test)
