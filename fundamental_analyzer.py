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
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED, TimeoutError as _TimeoutError
from pathlib import Path
from datetime import datetime
from config import FUNDAMENTAL_CONFIG, FUNDA_CACHE_FILE, CACHE_CONFIG

# 单只股票基本面查询超时（秒）
_STOCK_TIMEOUT = 30


# ========== 财务数据获取 ==========

def _fetch_single_profit(code: str, year: int = 2025, quarter: int = 4) -> dict:
    """获取单只股票的利润表数据（ROE、净利润、EPS等）"""
    rs = bs.query_profit_data(code, year=year, quarter=quarter)
    while rs.next():
        return dict(zip(rs.fields, rs.get_row_data()))
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




def _fetch_single_fundamental(code: str, year: int = 2025, quarter: int = 4) -> dict:
    """获取单只股票的基本面数据（独立login/query/logout）"""
    lg = bs.login()
    if lg.error_code != "0":
        return {}
    try:
        profit = _fetch_single_profit(code, year, quarter)
        balance = _fetch_single_balance(code, year, quarter)
        cashflow = _fetch_single_cashflow(code, year, quarter)
    finally:
        bs.logout()

    if not profit or not balance:
        return {}

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
) -> pd.DataFrame:
    """
    批量获取基本面数据（串行拉取避免并发封IP）

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
    print(f"\n[基本面] 正在获取 {len(symbols)} 只股票的财务数据...")

    # 尝试加载缓存
    cached_df = None
    if FUNDA_CACHE_FILE.exists():
        mtime = datetime.fromtimestamp(Path(FUNDA_CACHE_FILE).stat().st_mtime)
        age_days = (datetime.now() - mtime).total_seconds() / 86400
        if age_days <= CACHE_CONFIG["funda_max_age_days"]:
            try:
                cached_df = pd.read_parquet(FUNDA_CACHE_FILE)
                cached_symbols = set(cached_df["symbol"].tolist())
                need_fetch = [s for s in symbols if s not in cached_symbols]
                if not need_fetch:
                    print(f"  [缓存] 使用缓存数据 ({len(cached_df)} 条，{age_days:.0f}天前)")
                    return cached_df[cached_df["symbol"].isin(symbols)].reset_index(drop=True)
                print(f"  [缓存] 部分命中: {len(cached_symbols & set(symbols))} 只已缓存，需新获取 {len(need_fetch)} 只")
            except Exception as e:
                print(f"  [WARN] 缓存读取失败: {e}")
                cached_df = None
        else:
            print(f"  [缓存] 缓存已过期 ({age_days:.0f}天 > {CACHE_CONFIG['funda_max_age_days']}天)")



    results = []
    total = len(symbols)
    fail_count = 0

    _empty = {"roe": None, "np_margin": None, "gp_margin": None,
               "net_profit": None, "eps_ttm": None, "revenue": None,
               "liability_ratio": None, "asset_to_equity": None,
               "cfo_to_np": None, "cfo_to_or": None, "has_data": False}

    pool = ProcessPoolExecutor(max_workers=3)
    futures = {}
    idx = 0
    completed = 0

    # 初始批次——3个worker并行
    while idx < total and len(futures) < 3:
        bs_code = _to_bs_code(symbols[idx])
        futures[pool.submit(_fetch_single_fundamental, bs_code, year, quarter)] = symbols[idx]
        idx += 1

    try:
        while futures:
            done, pending = wait(futures, return_when=FIRST_COMPLETED, timeout=_STOCK_TIMEOUT)

            if not done:
                for f in pending:
                    sym = futures[f]
                    print(f"  [WARN] {sym} 基本面超时（>{_STOCK_TIMEOUT}s），已跳过")
                    fail_count += 1
                    completed += 1
                break

            for f in done:
                sym = futures.pop(f)
                completed += 1
                try:
                    data = f.result()
                    if data:
                        data["symbol"] = sym
                        results.append(data)
                    else:
                        fail_count += 1
                        d = {"symbol": sym}
                        d.update(_empty)
                        results.append(d)
                except Exception as e:
                    fail_count += 1
                    d = {"symbol": sym}
                    d.update(_empty)
                    results.append(d)
                    print(f"  [WARN] {sym} 基本面异常: {e}")

                if completed % 50 == 0 or completed == total:
                    pct = completed / total * 100
                    print(f"  [进度] {completed}/{total} ({pct:.0f}%) | 失败: {fail_count}")
                    if progress_callback:
                        progress_callback(completed, total)

            while idx < total and len(futures) < 3:
                bs_code = _to_bs_code(symbols[idx])
                futures[pool.submit(_fetch_single_fundamental, bs_code, year, quarter)] = symbols[idx]
                idx += 1

            time.sleep(0.05)
    finally:
        pool.shutdown(wait=False)

    df = pd.DataFrame(results)
    print(f"  [OK] 基本面数据获取完成，{len(df) - fail_count}/{total} 成功")

    # 保存缓存
    try:
        # 如果有旧缓存，合并后保存
        if cached_df is not None and not cached_df.empty:
            combined = pd.concat([cached_df, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["symbol"], keep="last")
            combined.to_parquet(FUNDA_CACHE_FILE, index=False)
        else:
            df.to_parquet(FUNDA_CACHE_FILE, index=False)
        print(f"  [缓存] 已保存 {len(df)} 条到 {FUNDA_CACHE_FILE.name}")
    except Exception as e:
        print(f"  [WARN] 缓存保存失败: {e}")

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

    result = {"symbol": symbol, "years": {}}

    try:
        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"baostock 登录失败: {lg.error_msg}")

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
        ("营收增长率", None, "%", None),  # 特殊处理：YoY对比
        ("EPS_TTM", "eps_ttm", "", lambda x: f"{x:.3f}" if x else "N/A"),
        ("营收(亿)", "revenue", "", lambda x: f"{x/1e8:.2f}" if x else "N/A"),
        ("负债率", "liability_ratio", "%", lambda x: f"{x*100:.1f}" if x else "N/A"),
        ("现金流/净利润", "cfo_to_np", "", lambda x: f"{x:.2f}" if x else "N/A"),
    ]

    for label, key, unit, fmt in rows:
        if key is None:
            # 营收增长率：特殊计算（YoY）
            revs = []
            for y in ["2023", "2024", "2025"]:
                v = years.get(y, {}).get("revenue")
                revs.append(v)
            growth_vals = []
            for i in range(1, len(revs)):
                if revs[i-1] and revs[i] and revs[i-1] != 0:
                    g = (revs[i] - revs[i-1]) / abs(revs[i-1]) * 100
                    growth_vals.append(f"{g:.1f}")
                else:
                    growth_vals.append("N/A")
            # 3列显示: 前两个为增长率，第3列空白
            vals = [growth_vals[0] if len(growth_vals) > 0 else "N/A",
                    growth_vals[1] if len(growth_vals) > 1 else "N/A",
                    ""]
            # 趋势
            num_g = []
            for v in growth_vals:
                if v != "N/A":
                    num_g.append(float(v))
            trend = "—"
            if len(num_g) >= 2:
                if num_g[-1] > num_g[0] + 5:
                    trend = "↑"
                elif num_g[-1] < num_g[0] - 5:
                    trend = "↓"
                else:
                    trend = "→"
            print(f"  {label:<20} {vals[0]:>10} {vals[1]:>10} {vals[2]:>10} {trend:>8}")
        else:
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


def diagnosis_to_html(diagnosis: dict) -> str:
    """输出个股诊断的 HTML 片段"""
    symbol = diagnosis["symbol"]
    years = diagnosis["years"]

    rows_html = ""
    fields = [
        ("ROE", "roe", "{:.1f}%", lambda x: x * 100 if x is not None else None),
        ("净利率", "np_margin", "{:.1f}%", lambda x: x * 100 if x is not None else None),
        ("毛利率", "gp_margin", "{:.1f}%", lambda x: x * 100 if x is not None else None),
        ("净利润(亿)", "net_profit", "{:.2f}", lambda x: x / 1e8 if x is not None else None),
        ("营收(亿)", "revenue", "{:.2f}", lambda x: x / 1e8 if x is not None else None),
        ("负债率", "liability_ratio", "{:.1f}%", lambda x: x * 100 if x is not None else None),
    ]

    for label, key, fmt, transform in fields:
        vals = []
        for y in ["2023", "2024", "2025"]:
            v = years.get(y, {}).get(key)
            tv = transform(v) if v is not None else None
            vals.append(fmt.format(tv) if tv is not None else "N/A")
        rows_html += f"<tr><td>{label}</td><td>{vals[0]}</td><td>{vals[1]}</td><td>{vals[2]}</td></tr>\n"

    html = f"""<div class="diagnosis-section">
<h3>🔍 个股诊断: {symbol}</h3>
<table>
<thead><tr><th>指标</th><th>2023</th><th>2024</th><th>2025</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>"""
    return html


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
