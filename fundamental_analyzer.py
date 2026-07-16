"""
基本面分析模块
- 从 baostock 获取 ROE、净利润、负债率、现金流等财务指标
- 计算基本面综合评分
- 亏损股过滤（净利润 < 0 → 自动降级）
"""
import time
import pandas as pd
import numpy as np
import baostock as bs
from config import FUNDAMENTAL_CONFIG
from concurrent.futures import ThreadPoolExecutor, as_completed


# ========== 财务数据获取 ==========

def _fetch_single_profit(code: str, year: int = 2025, quarter: int = 4) -> dict:
    """获取单只股票的利润表数据（ROE、净利润、EPS等）"""
    rs = bs.query_profit_data(code, year=year, quarter=quarter)
    while rs.next():
        row = dict(zip(rs.fields, rs.get_row_data()))
        return row
    return {}


def _fetch_single_balance(code: str, year: int = 2025, quarter: int = 4) -> dict:
    """获取单只股票的资产负债表数据（负债率等）"""
    rs = bs.query_balance_data(code, year=year, quarter=quarter)
    while rs.next():
        return dict(zip(rs.fields, rs.get_row_data()))
    return {}


def _fetch_single_cashflow(code: str, year: int = 2025, quarter: int = 4) -> dict:
    """获取单只股票的现金流量表数据"""
    rs = bs.query_cash_flow_data(code, year=year, quarter=quarter)
    while rs.next():
        return dict(zip(rs.fields, rs.get_row_data()))
    return {}


def _to_bs_code(code: str) -> str:
    if code.startswith("6") or code.startswith("9"):
        return f"sh.{code}"
    return f"sz.{code}"


def _fetch_single_fundamental(bs_code: str, year: int, quarter: int) -> dict:
    """并行用：获取单只股票的三张表数据"""
    profit = _fetch_single_profit(bs_code, year, quarter)
    if not profit:
        return None
    balance = _fetch_single_balance(bs_code, year, quarter)
    cashflow = _fetch_single_cashflow(bs_code, year, quarter)

    def sf(v, default=None):
        try:
            return float(v) if v and v != "" else default
        except (ValueError, TypeError):
            return default

    return {
        "roe": sf(profit.get("roeAvg")),
        "np_margin": sf(profit.get("npMargin")),
        "gp_margin": sf(profit.get("gpMargin")),
        "net_profit": sf(profit.get("netProfit")),
        "eps_ttm": sf(profit.get("epsTTM")),
        "revenue": sf(profit.get("MBRevenue")),
        "liability_ratio": sf(balance.get("liabilityToAsset")),
        "asset_to_equity": sf(balance.get("assetToEquity")),
        "cfo_to_np": sf(cashflow.get("CFOToNP")),
        "cfo_to_or": sf(cashflow.get("CFOToOR")),
        "has_data": True,
    }


def fetch_fundamentals(
    symbols: list[str],
    year: int = 2025,
    quarter: int = 4,
    progress_callback=None,
    max_workers: int = 10,
) -> pd.DataFrame:
    """
    批量获取基本面数据（并行）

    Parameters
    ----------
    symbols : list[str]
        股票代码列表（6位数字）
    year, quarter : int
        财务报告年份和季度（4=年报）

    Returns
    -------
    pd.DataFrame
        包含每只股票的基本面数据
    """
    print(f"\n[基本面] 正在获取 {len(symbols)} 只股票的财务数据（并行{max_workers}线程）...")

    lg = bs.login()
    if lg.error_code != "0":
        raise ConnectionError(f"baostock 登录失败: {lg.error_msg}")

    results = []
    total = len(symbols)
    fail_count = 0

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_fetch_single_fundamental, _to_bs_code(s), year, quarter): s
                for s in symbols
            }
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                symbol = futures[future]
                try:
                    data = future.result()
                    if data:
                        data["symbol"] = symbol
                        results.append(data)
                    else:
                        fail_count += 1
                        results.append({
                            "symbol": symbol,
                            "roe": None, "np_margin": None, "gp_margin": None,
                            "net_profit": None, "eps_ttm": None, "revenue": None,
                            "liability_ratio": None, "asset_to_equity": None,
                            "cfo_to_np": None, "cfo_to_or": None,
                            "has_data": False,
                        })
                except Exception:
                    fail_count += 1

                if done_count % 50 == 0 or done_count == total:
                    pct = done_count / total * 100
                    print(f"  [进度] {done_count}/{total} ({pct:.0f}%) | 失败: {fail_count}")
                    if progress_callback:
                        progress_callback(done_count, total)
    finally:
        bs.logout()

    df = pd.DataFrame(results)
    print(f"  [OK] 基本面数据获取完成，{len(df) - fail_count}/{total} 成功")
    return df


# ========== 基本面评分 ==========

def calculate_fundamental_scores(fundamentals: pd.DataFrame) -> pd.DataFrame:
    """
    根据基本面数据计算评分

    评分维度：
    - 盈利能力（ROE）：越高越好
    - 盈利质量（净利率、毛利率）：越高越好
    - 偿债能力（负债率）：越低越好
    - 现金流质量（经营现金流/净利润）：越高越好
    - 亏损惩罚（净利润<0）：直接低分
    """
    print("\n[基本面] 正在计算基本面评分...")
    df = fundamentals.copy()

    # 1. 亏损标记：净利润 < 0 → 淘汰
    df["is_loss"] = df["net_profit"].apply(
        lambda x: True if x is not None and x < 0 else False
    )

    # 2. ROE 评分（0~100）
    df["roe_score"] = df["roe"].apply(_roe_to_score)

    # 3. 净利率评分
    df["np_margin_score"] = df["np_margin"].apply(_margin_to_score)

    # 4. 负债率评分（越低越好）
    df["debt_score"] = df["liability_ratio"].apply(_debt_to_score)

    # 5. 现金流质量评分
    df["cashflow_score"] = df["cfo_to_np"].apply(_cashflow_to_score)

    # 6. 综合基本面评分
    config = FUNDAMENTAL_CONFIG["scoring"]
    df["fundamental_score"] = (
        config["roe_weight"] * df["roe_score"].values
        + config["margin_weight"] * df["np_margin_score"].values
        + config["debt_weight"] * df["debt_score"].values
        + config["cashflow_weight"] * df["cashflow_score"].values
    )

    # 7. 亏损惩罚：亏损股基础分打3折，且永远不能超过40分
    loss_mask = df["is_loss"]
    df.loc[loss_mask, "fundamental_score"] = df.loc[loss_mask, "fundamental_score"] * 0.3
    df.loc[loss_mask, "fundamental_score"] = df.loc[loss_mask, "fundamental_score"].clip(upper=40)

    # 8. 无数据保护
    df.loc[~df["has_data"], "fundamental_score"] = 30.0

    print(f"  [OK] 基本面评分完成 | 亏损股: {loss_mask.sum()} 只")
    print(f"        得分范围: {df['fundamental_score'].min():.1f} ~ {df['fundamental_score'].max():.1f}")
    return df


def _roe_to_score(roe: float) -> float:
    """ROE 转评分"""
    if roe is None:
        return 30
    roe_pct = roe * 100  # 转为百分比
    if roe_pct >= 20:
        return 95
    elif roe_pct >= 15:
        return 85
    elif roe_pct >= 10:
        return 70
    elif roe_pct >= 6:
        return 55
    elif roe_pct >= 3:
        return 40
    elif roe_pct >= 0:
        return 25
    else:
        return 10  # 负ROE


def _margin_to_score(margin: float) -> float:
    """净利率转评分"""
    if margin is None:
        return 30
    margin_pct = margin * 100
    if margin_pct >= 20:
        return 90
    elif margin_pct >= 10:
        return 70
    elif margin_pct >= 5:
        return 55
    elif margin_pct >= 0:
        return 35
    else:
        return 10


def _debt_to_score(ratio: float) -> float:
    """资产负债率转评分（越低越好）"""
    if ratio is None:
        return 40
    if ratio <= 0.2:
        return 90  # 极低负债
    elif ratio <= 0.4:
        return 80  # 低负债
    elif ratio <= 0.5:
        return 65  # 适中
    elif ratio <= 0.6:
        return 50  # 偏高
    elif ratio <= 0.7:
        return 35  # 高负债
    elif ratio <= 0.85:
        return 20  # 很高
    else:
        return 10  # 资不抵债


def _cashflow_to_score(cfo_to_np: float) -> float:
    """经营现金流/净利润 转评分（>1 说明利润有现金保障）"""
    if cfo_to_np is None:
        return 40
    if cfo_to_np > 2:
        return 90
    elif cfo_to_np > 1.2:
        return 75
    elif cfo_to_np > 0.8:
        return 60
    elif cfo_to_np > 0:
        return 40
    else:
        return 20  # 经营现金流为负


# ========== 个股诊断 ==========

def diagnose_stock(symbol: str) -> dict:
    """
    个股基本面诊断

    Parameters
    ----------
    symbol : str
        6位股票代码

    Returns
    -------
    dict
        诊断结果，含3年财务趋势
    """
    bs_code = _to_bs_code(symbol)
    lg = bs.login()

    result = {"symbol": symbol, "years": {}}

    try:
        for year in [2025, 2024, 2023]:
            profit = _fetch_single_profit(bs_code, year, 4)
            balance = _fetch_single_balance(bs_code, year, 4)
            cashflow = _fetch_single_cashflow(bs_code, year, 4)

            def sf(v):
                try:
                    return round(float(v), 4) if v and v != "" else None
                except:
                    return None

            result["years"][str(year)] = {
                "roe": sf(profit.get("roeAvg")),
                "np_margin": sf(profit.get("npMargin")),
                "gp_margin": sf(profit.get("gpMargin")),
                "net_profit": sf(profit.get("netProfit")),
                "eps_ttm": sf(profit.get("epsTTM")),
                "revenue": sf(profit.get("MBRevenue")),
                "liability_ratio": sf(balance.get("liabilityToAsset")),
                "cfo_to_np": sf(cashflow.get("CFOToNP")),
            }
    finally:
        bs.logout()

    return result


def print_diagnosis(diagnosis: dict):
    """打印个股诊断结果"""
    symbol = diagnosis["symbol"]
    years = diagnosis["years"]

    print(f"\n{'='*60}")
    print(f"  个股基本面诊断: {symbol}")
    print(f"{'='*60}")

    headers = ["指标", "2023", "2024", "2025", "趋势"]
    print(f"  {headers[0]:<20} {headers[1]:>10} {headers[2]:>10} {headers[3]:>10} {headers[4]:>8}")
    print(f"  {'-'*58}")

    rows = [
        ("ROE", "roe", "%", lambda x: f"{x*100:.1f}" if x else "N/A"),
        ("净利率", "np_margin", "%", lambda x: f"{x*100:.1f}" if x else "N/A"),
        ("毛利率", "gp_margin", "%", lambda x: f"{x*100:.1f}" if x else "N/A"),
        ("净利润(亿)", "net_profit", "", lambda x: f"{x/1e8:.2f}" if x else "N/A"),
        ("EPS_TTM", "eps_ttm", "", lambda x: f"{x:.3f}" if x else "N/A"),
        ("营收(亿)", "revenue", "", lambda x: f"{x/1e8:.2f}" if x else "N/A"),
        ("负债率", "liability_ratio", "%", lambda x: f"{x*100:.1f}" if x else "N/A"),
        ("现金流/净利润", "cfo_to_np", "", lambda x: f"{x:.2f}" if x else "N/A"),
    ]

    for label, key, unit, fmt in rows:
        vals = []
        for y in ["2023", "2024", "2025"]:
            v = years.get(y, {}).get(key)
            vals.append(fmt(v))

        # 趋势判断
        num_vals = []
        for y in ["2023", "2024", "2025"]:
            v = years.get(y, {}).get(key)
            if v is not None:
                num_vals.append(v)

        trend = "—"
        if len(num_vals) >= 2:
            if num_vals[-1] > num_vals[0] * 1.05:
                trend = "↑"
            elif num_vals[-1] < num_vals[0] * 0.95:
                trend = "↓"
            else:
                trend = "→"

        print(f"  {label:<20} {vals[0]:>10} {vals[1]:>10} {vals[2]:>10} {trend:>8}")

    print(f"{'='*60}")

    # 综合判断
    latest = years.get("2025", {})
    roe = latest.get("roe")
    net_profit = latest.get("net_profit")
    liability = latest.get("liability_ratio")

    issues = []
    if net_profit is not None and net_profit < 0:
        issues.append("亏损")
    if roe is not None and roe < 0.03:
        issues.append("ROE偏低")
    if liability is not None and liability > 0.7:
        issues.append("负债过高")

    if issues:
        print(f"  [WARN] 风险提示: {' | '.join(issues)}")
    else:
        print(f"  [OK] 基本面正常")


if __name__ == "__main__":
    # 测试
    from data_fetcher import fetch_csi500_constituents
    cons = fetch_csi500_constituents()
    syms = cons["symbol"].tolist()[:10]

    fd = fetch_fundamentals(syms)
    scores = calculate_fundamental_scores(fd)
    print(scores[["symbol", "roe", "net_profit", "is_loss",
                   "roe_score", "fundamental_score"]].to_string())

    # 诊断测试
    diag = diagnose_stock("000785")
    print_diagnosis(diag)
