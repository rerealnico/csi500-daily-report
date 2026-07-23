"""
估值分析模块 - 计算PE/PB分位数、估值吸引力评分
"""
import pandas as pd
import numpy as np
from config import VALUATION_CONFIG


def calculate_valuation_scores(
    klines: pd.DataFrame,
    financials: pd.DataFrame = None
) -> pd.DataFrame:
    """
    计算每只股票的估值评分
    从 klines 中提取最新 PE/PB + 价格百分位
    """
    print("\n[估值分析] 正在计算估值评分...")

    # 1. 计算每只股票最近 N 年的价格百分位
    latest_date = klines["date"].max()
    years = VALUATION_CONFIG["pe_percentile_years"]
    cutoff = latest_date - pd.DateOffset(years=years)

    hist = klines[klines["date"] >= cutoff].copy()

    price_percentiles = (
        hist.groupby("symbol")["close"]
        .agg(["min", "max", "mean", "std",
              lambda x: x.iloc[-1],
              lambda x: x.quantile(0.05),
              lambda x: x.quantile(0.95)])
        .rename(columns={"<lambda_0>": "current_close",
                         "<lambda_1>": "p5",
                         "<lambda_2>": "p95"})
    )
    # 使用 p5-p95 范围计算百分位（避免异常极值扭曲）
    price_percentiles["close_percentile"] = (
        (price_percentiles["current_close"] - price_percentiles["p5"])
        / (price_percentiles["p95"] - price_percentiles["p5"] + 1e-10)
    ).clip(0, 1)

    # 2. 从 klines 提取最新 PE/PB
    latest = klines.sort_values("date").groupby("symbol").last()

    if "pe" in klines.columns and latest["pe"].notna().sum() > 0:
        # 检查 pb 列是否存在
        merge_cols = ["pe"]
        if "pb" in latest.columns:
            merge_cols.append("pb")
        merged = price_percentiles.merge(
            latest[merge_cols], left_index=True, right_index=True, how="left"
        )
        merged["pe_rank"] = merged["pe"].rank(pct=True)
        merged["pb_rank"] = merged["pb"].rank(pct=True)

        pe_median = merged["pe"].median()
        merged["pe_deviation"] = (merged["pe"] - pe_median) / (pe_median + 1e-10)

        # 关键修复：PE为负（亏损股）必须打低分
        # 自动发现亏损股并将其估值评分压到最低
        merged["pe_score"] = np.where(
            merged["pe"].notna() & (merged["pe"] < 0),
            10.0,  # 亏损股：PE为负 → 固定低分
            100 * (1 - merged["pe_rank"])  # 正常PE：越低PE分越高
        )
        merged["pb_score"] = np.where(
            merged["pb"].notna() & (merged["pb"] < 0),
            10.0,  # 资不抵债：PB为负 → 固定低分
            100 * (1 - merged["pb_rank"])  # 正常PB：越低PB分越高
        )
        merged["price_score"] = _price_percentile_to_score(merged["close_percentile"])

        merged["valuation_score"] = (
            0.4 * merged["pe_score"]
            + 0.3 * merged["pb_score"]
            + 0.3 * merged["price_score"]
        )

        print(f"  [OK] 估值评分完成（含PE/PB），得分范围: {merged['valuation_score'].min():.2f} ~ {merged['valuation_score'].max():.2f}")
        return merged.reset_index()[
            ["symbol", "pe", "pb", "pe_rank", "pb_rank",
             "close_percentile", "pe_score", "pb_score",
             "price_score", "valuation_score"]
        ]
    else:
        print("  [WARN] 无PE/PB数据，仅使用价格百分位")
        valuation = price_percentiles.reset_index()
        valuation["pe_score"] = _price_percentile_to_score(
            valuation["close_percentile"]
        )
        valuation["valuation_score"] = valuation["pe_score"]
        return valuation[["symbol", "close_percentile", "pe_score", "valuation_score"]]


def _pe_rank_to_score(rank: float) -> float:
    """
    PE 分位转评分：PE越低越好（越低估）
    rank 0 = 全市场最低PE, rank 1 = 全市场最高PE
    评分 0~100，PE 越低分越高
    """
    # rank 0~0.2: 低估 → 80-100分
    # rank 0.2~0.4: 偏低 → 60-80分
    # rank 0.4~0.6: 中等 → 40-60分
    # rank 0.6~0.8: 偏高 → 20-40分
    # rank 0.8~1.0: 高估 → 0-20分
    return max(0, 100 * (1 - rank))


def _pb_rank_to_score(rank: float) -> float:
    """PB 分位转评分，逻辑同PE"""
    return max(0, 100 * (1 - rank))


def _price_percentile_to_score(percentile: pd.Series) -> pd.Series:
    """
    价格百分位转评分（向量化版本）：
    - 股价处于历史低位(0~0.2) -> 高分(80~100) 低估信号
    - 股价处于历史高位(0.8~1) -> 低分(0~20) 高估信号
    中间线性过渡
    """
    score = np.where(
        percentile <= 0.2,
        80 + 100 * (0.2 - percentile),
        np.where(
            percentile >= 0.8,
            np.maximum(0, 100 * (1 - percentile) * 5),
            np.maximum(0, 80 - 100 * (percentile - 0.2) / 0.6)
        )
    )
    return score


def tag_valuation_level(score: float) -> str:
    """根据估值评分打标签"""
    if score >= 80:
        return "低估"
    elif score >= 60:
        return "偏低"
    elif score >= 40:
        return "合理"
    elif score >= 20:
        return "偏高"
    else:
        return "高估"


if __name__ == "__main__":
    # 测试
    from data_fetcher import fetch_csi500_constituents, fetch_daily_klines, fetch_financial_indicators

    constituents = fetch_csi500_constituents()
    symbols = constituents["symbol"].tolist()[:10]

    klines = fetch_daily_klines(symbols)
    financials = fetch_financial_indicators(symbols)

    result = calculate_valuation_scores(klines, financials)
    print(result.head(10))
