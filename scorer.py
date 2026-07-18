"""
评分排序模块 - 综合估值、量能、动量多因子评分，输出排序结果
"""
import pandas as pd
import numpy as np
from config import SCORE_WEIGHTS


def calculate_final_scores(
    constituents: pd.DataFrame,
    valuation_scores: pd.DataFrame,
    volume_scores: pd.DataFrame,
    fundamental_scores: pd.DataFrame = None,
    capital_flow_scores: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    多因子综合评分

    Parameters
    ----------
    constituents : pd.DataFrame
        成分股列表 (symbol, stock_name, weight)
    valuation_scores : pd.DataFrame
        估值评分结果
    volume_scores : pd.DataFrame
        量能评分结果
    fundamental_scores : pd.DataFrame, optional
        基本面评分结果
    capital_flow_scores : pd.DataFrame, optional
        资金流评分结果

    Returns
    -------
    pd.DataFrame
        综合评分排序
    """
    print("\n[综合评分] 正在计算最终评分...")

    # 1. 合并所有因子
    merged = constituents[["symbol", "stock_name", "weight"]].copy().reset_index(drop=True)

    # 合并估值
    if not valuation_scores.empty:
        val_cols = ["symbol", "valuation_score"]
        val_extra = [c for c in valuation_scores.columns
                     if c not in merged.columns and c != "symbol" and c not in val_cols]
        merged = merged.merge(
            valuation_scores[val_cols + val_extra].reset_index(drop=True),
            on="symbol", how="left"
        )

    # 合并量能
    if not volume_scores.empty:
        vol_cols = ["symbol", "volume_score"]
        vol_extra = [c for c in volume_scores.columns
                     if c not in merged.columns and c != "symbol" and c not in vol_cols]
        merged = merged.merge(
            volume_scores[vol_cols + vol_extra].reset_index(drop=True),
            on="symbol", how="left"
        )

    # 合并基本面
    if fundamental_scores is not None and not fundamental_scores.empty:
        fin_cols = ["symbol", "fundamental_score"]
        fin_extra = [c for c in fundamental_scores.columns
                     if c not in merged.columns and c != "symbol" and c not in fin_cols]
        merged = merged.merge(
            fundamental_scores[fin_cols + fin_extra].reset_index(drop=True),
            on="symbol", how="left"
        )

    # 合并资金流
    if capital_flow_scores is not None and not capital_flow_scores.empty:
        cf_cols = ["symbol", "capital_flow_score"]
        cf_extra = [c for c in capital_flow_scores.columns
                     if c not in merged.columns and c != "symbol" and c not in cf_cols]
        merged = merged.merge(
            capital_flow_scores[cf_cols + cf_extra].reset_index(drop=True),
            on="symbol", how="left"
        )

    # 2. 确保索引无重复
    merged = merged.reset_index(drop=True)

    # 3. 处理缺失值（保守原则：数据不全给低分35而非中分50）
    score_cols = ["valuation_score", "volume_score", "fundamental_score", "capital_flow_score"]
    merged["data_incomplete"] = False
    for c in score_cols:
        if c not in merged.columns:
            merged[c] = 35.0
            merged["data_incomplete"] = True
            print(f"  [WARN] 缺少 {c} 数据，统一填充保守值35分")
        else:
            n_na = merged[c].isna().sum()
            if n_na > 0:
                merged["data_incomplete"] = True
                print(f"  [WARN] {c} 有 {n_na} 只股票缺失，填充保守值35分")
            merged[c] = merged[c].fillna(35).astype(float)

    # 4. 动量因子：用价格趋势计算
    if "price_trend_5d" in merged.columns:
        merged["momentum_score"] = merged["price_trend_5d"].apply(
            _price_trend_to_score
        ).astype(float)
    else:
        merged["momentum_score"] = 35.0
        merged["data_incomplete"] = True
        print(f"  [WARN] 缺少价格趋势数据，动量填充保守值35分")

    # 5. 综合评分（用.values避免索引对齐问题）
    merged["total_score"] = (
        SCORE_WEIGHTS["valuation"] * merged["valuation_score"].values
        + SCORE_WEIGHTS["fundamental"] * merged["fundamental_score"].values
        + SCORE_WEIGHTS["volume"] * merged["volume_score"].values
        + SCORE_WEIGHTS["momentum"] * merged["momentum_score"].values
        + SCORE_WEIGHTS["capital_flow"] * merged["capital_flow_score"].values
    )

    # 6. 亏损股标记（来自基本面）
    if "is_loss" in merged.columns:
        loss_count = merged["is_loss"].sum()
        print(f"  [INFO] 亏损股: {loss_count} 只（已降低评分）")

    # 7. 排序
    merged = merged.sort_values("total_score", ascending=False).reset_index(drop=True)
    merged["rank"] = range(1, len(merged) + 1)

    # 8. 打标签
    merged["action"] = merged["total_score"].apply(_score_to_action)

    # 标记亏损股推荐标签
    if "is_loss" in merged.columns:
        merged.loc[merged["is_loss"], "action"] = "亏损暂避"

    print(f"  [OK] 综合评分完成，最高分: {merged['total_score'].iloc[0]:.1f}, "
          f"最低分: {merged['total_score'].iloc[-1]:.1f}")

    return merged


def _price_trend_to_score(trend_pct: float) -> float:
    """
    5日涨跌幅转评分
    - 涨幅 > 5%: 高分（强势）
    - 跌幅 > 5%: 低分（弱势）
    - 小幅震荡: 中性
    """
    if trend_pct > 10:
        return 80
    elif trend_pct > 5:
        return 70
    elif trend_pct > 2:
        return 60
    elif trend_pct > -2:
        return 50
    elif trend_pct > -5:
        return 30
    elif trend_pct > -10:
        return 20
    else:
        return 10


def _score_to_action(score: float) -> str:
    """根据总分打操作标签"""
    if score >= 75:
        return "推荐关注"
    elif score >= 65:
        return "可以关注"
    elif score >= 50:
        return "持有观望"
    elif score >= 35:
        return "谨慎观察"
    else:
        return "注意风险"


def print_top_bottom(df: pd.DataFrame, top_n: int = 10):
    """打印排名前N和倒数N"""
    print(f"\n{'='*60}")
    print(f"  Top {top_n} 推荐")
    print(f"{'='*60}")
    top = df.head(top_n)
    for i, (_, row) in enumerate(top.iterrows(), 1):
        info = f"  {i:2d}. {row['stock_name']}({row['symbol']})  "
        info += f"总分:{row['total_score']:.1f} | "
        info += f"估:{row.get('valuation_score', 0):.0f} "
        info += f"基:{row.get('fundamental_score', 0):.0f} "
        info += f"量:{row.get('volume_score', 0):.0f} "
        # ROE 显示
        roe = row.get('roe')
        if roe is not None and not pd.isna(roe) and roe != '':
            info += f"ROE:{float(roe)*100:.1f}% "
        info += f"| {row['action']}"
        print(info)

    print(f"\n{'='*60}")
    print(f"  风险关注 (Top {top_n} 最低分)")
    print(f"{'='*60}")
    bottom = df.tail(top_n).iloc[::-1]
    for i, (_, row) in enumerate(bottom.iterrows(), 1):
        info = f"  {i:2d}. {row['stock_name']}({row['symbol']})  "
        info += f"总分:{row['total_score']:.1f} "
        roe = row.get('roe')
        if roe is not None and not pd.isna(roe) and roe != '':
            info += f"ROE:{float(roe)*100:.1f}% "
        info += f"| {row['action']}"
        print(info)
