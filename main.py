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
import traceback
from datetime import datetime

from config import REPORT_CONFIG
from config import FUNDAMENTAL_CONFIG
from data_fetcher import (
    fetch_csi500_constituents,
    fetch_daily_klines,
    fetch_latest_trade_date,
)
from valuation_analyzer import calculate_valuation_scores
from volume_analyzer import calculate_volume_scores
from fundamental_analyzer import fetch_fundamentals, calculate_fundamental_scores
from capital_flow_analyzer import calculate_capital_flow_scores
from scorer import calculate_final_scores, print_top_bottom
from reporter import generate_report, save_report
from report_html import generate_html_report


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
    klines = fetch_daily_klines(symbols, end_date=trade_date, years=10)
    # 以实际数据最新日期作为报告日期
    if klines is not None and not klines.empty:
        trade_date = klines["date"].max().strftime("%Y%m%d")

    # ===== Step 3: 获取基本面数据 =====
    print(f"\n[Step 3/7] 获取财务数据")
    fundamentals = fetch_fundamentals(symbols, year=FUNDAMENTAL_CONFIG["year"], quarter=FUNDAMENTAL_CONFIG["quarter"])
    fundamental_scores = calculate_fundamental_scores(fundamentals)

    # ===== Step 4: 分析计算 =====
    print(f"\n[Step 4/7] 分析计算")

    # 4a. 估值分析（PE/PB 已内含在 klines 中）
    valuation_scores = calculate_valuation_scores(klines)

    # 4b. 量能分析
    volume_scores = calculate_volume_scores(klines)

    # 4c. 资金流分析
    capital_flow_scores = calculate_capital_flow_scores(klines)

    # 4d. 综合评分（含基本面因子）
    final_scores = calculate_final_scores(
        constituents, valuation_scores, volume_scores, fundamental_scores,
        capital_flow_scores
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

        # 提取股价历史数据（用于 HTML 走势图）
        print(f"  [Step 6] 提取股价历史数据")
        price_history = {}
        if klines is not None and not klines.empty:
            for symbol in klines['symbol'].unique():
                stock_klines = klines[klines['symbol'] == symbol].sort_values('date')
                if len(stock_klines) > 0:
                    step = max(1, len(stock_klines) // 200)
                    sampled = stock_klines.iloc[::step]
                    price_history[symbol] = [
                        {"date": row['date'].strftime('%Y-%m-%d'), "close": round(float(row['close']), 2)}
                        for _, row in sampled.iterrows()
                    ]
            print(f"    [OK] 已提取 {len(price_history)} 只股票的历史数据")

        # 生成 HTML 报告（用于 GitHub Pages）
        html_path = generate_html_report(
            top_stocks=top_stocks,
            report_date=trade_date,
            all_stocks=final_scores.to_dict("records"),
            price_history=price_history,
        )
        
        # HTML 报告已包含 base64 内嵌图表，可直接用于 GitHub Pages
        print(f"\n[推送] 微信推送已禁用（你只需要打开网页链接查看）")
    # 微信推送已在 notifier_config.json 中 disabled

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
        try:
            run_pipeline(max_stocks=args.max, test_mode=args.test)
        except Exception as e:
            print(f"\n[FATAL] 分析管线执行异常: {e}")
            traceback.print_exc()
            sys.exit(1)
